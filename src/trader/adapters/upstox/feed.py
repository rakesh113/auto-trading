"""Upstox Market Data Feed V3 over our own websocket client (design §11).

* One `_Connection` per configured socket (C1 full_d30, C2 full, C3 ltpc, C4 greeks).
* Subscriptions are declarative: `set_subscriptions(want)` diffs against what is live.
* Every received frame goes to the RawRecorder *before* decoding (bronze tier), so a
  decoder bug never loses data. Outgoing sub/unsub messages are recorded too, so a
  replay knows exactly what was subscribed when.
* Reconnects with backoff; after a reconnect it re-subscribes and emits a GAP event.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from trader.adapters.upstox.decode import decode_frame
from trader.adapters.upstox.http import UpstoxHttp
from trader.core.config import secret
from trader.core.registry import feeds
from trader.domain.instrument import InstrumentId
from trader.domain.market import FeedState, MarketEvent
from trader.domain.types import FeedMode
from trader.ports.clock import Clock
from trader.ports.infra import NullRecorder, RawRecorder
from trader.ports.marketdata import FeedHealth, InstrumentMaster, MarketDataFeed

if TYPE_CHECKING:
    from trader.core.app import AppContext

log = structlog.get_logger(__name__)

AUTHORIZE_PATH = "/v3/feed/market-data-feed/authorize"
KIND_FRAME = 1  # recorder record kinds
KIND_SENT = 2
KIND_STATE = 3
_CHUNK = 100  # keys per subscribe message


class _Connection:
    def __init__(self, name: str, modes: list[FeedMode], feed: UpstoxMarketFeed) -> None:
        self.name = name
        self.modes = modes
        self.feed = feed
        self.want: dict[str, FeedMode] = {}  # native key -> mode
        self.live: dict[str, FeedMode] = {}
        self.ws: websockets.ClientConnection | None = None
        self.task: asyncio.Task[None] | None = None
        self.health = FeedHealth()
        self._lock = asyncio.Lock()
        self._disconnected_since: int = 0

    async def _send(self, method: str, mode: FeedMode | None, keys: list[str]) -> None:
        assert self.ws is not None
        for i in range(0, len(keys), _CHUNK):
            data: dict[str, object] = {"instrumentKeys": keys[i:i + _CHUNK]}
            if mode is not None:
                data["mode"] = mode.value
            msg = json.dumps({"guid": uuid.uuid4().hex[:20], "method": method, "data": data}).encode()
            self.feed.recorder.write(self.name, KIND_SENT, self.feed.clock.now_ns(), msg)
            await self.ws.send(msg)  # Upstox V3 expects the JSON as a binary frame

    async def sync(self) -> None:
        """Bring the live subscription set in line with `want`."""
        async with self._lock:
            if self.ws is None:
                return
            remove = [k for k in self.live if k not in self.want]
            if remove:
                await self._send("unsub", None, remove)
                for k in remove:
                    del self.live[k]
            by_mode: dict[FeedMode, list[str]] = {}
            change: dict[FeedMode, list[str]] = {}
            for k, m in self.want.items():
                cur = self.live.get(k)
                if cur is None:
                    by_mode.setdefault(m, []).append(k)
                elif cur is not m:
                    change.setdefault(m, []).append(k)
            for m, keys in change.items():
                await self._send("change_mode", m, keys)
            for m, keys in by_mode.items():
                await self._send("sub", m, keys)
            self.live = dict(self.want)
            self.health.subscribed = {m.value: sum(1 for v in self.live.values() if v is m) for m in self.modes}

    async def run(self) -> None:
        backoff = 1.0
        while True:
            while not self.want:  # don't hold one of the account's 5 sockets for nothing
                await asyncio.sleep(0.5)
            try:
                uri = await self.feed.authorize()
                async with websockets.connect(uri, max_size=8 * 2**20, ping_interval=20, ping_timeout=20,
                                              open_timeout=15, close_timeout=5) as ws:
                    self.ws = ws
                    self.live = {}
                    now = self.feed.clock.now_ns()
                    self.health.connected = True
                    state = "CONNECTED" if not self._disconnected_since else "GAP"
                    self.feed._publish(FeedState(connection=self.name, state=state, ts_recv_ns=now,
                                                 since_ns=self._disconnected_since))
                    self.feed.recorder.write(self.name, KIND_STATE, now, state.encode())
                    self._disconnected_since = 0
                    log.info("feed.connected", conn=self.name, state=state)
                    await self.sync()
                    backoff = 1.0
                    async for frame in ws:
                        ts = self.feed.clock.now_ns()
                        if isinstance(frame, str):
                            frame = frame.encode()
                        self.feed.recorder.write(self.name, KIND_FRAME, ts, frame)
                        self.health.frames += 1
                        self.health.last_msg_ns = ts
                        try:
                            events = decode_frame(frame, ts, self.feed.resolve)
                        except Exception:  # noqa: BLE001 - a bad frame must not kill the feed
                            self.health.decode_errors += 1
                            log.exception("feed.decode_error", conn=self.name)
                            continue
                        self.health.messages += len(events)
                        for ev in events:
                            self.feed._publish(ev)
            except asyncio.CancelledError:
                raise
            except (OSError, ConnectionClosed, websockets.InvalidHandshake, TimeoutError) as e:
                log.warning("feed.disconnected", conn=self.name, error=repr(e))
            except Exception as e:  # noqa: BLE001 - keep reconnecting; authorize may fail transiently
                log.exception("feed.error", conn=self.name, error=repr(e))
            finally:
                if self.health.connected or not self._disconnected_since:
                    self._disconnected_since = self.feed.clock.now_ns()
                    self.feed._publish(FeedState(connection=self.name, state="DISCONNECTED",
                                                 ts_recv_ns=self._disconnected_since))
                    self.feed.recorder.write(self.name, KIND_STATE, self._disconnected_since, b"DISCONNECTED")
                self.health.connected = False
                self.ws = None
            self.health.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.feed.max_backoff_s)


@feeds.register("upstox")
class UpstoxMarketFeed(MarketDataFeed):
    def __init__(
        self,
        *,
        http: UpstoxHttp,
        master: InstrumentMaster,
        clock: Clock,
        connections: list[tuple[str, list[FeedMode]]],
        max_keys: Mapping[FeedMode, int],
        recorder: RawRecorder | None = None,
        queue_size: int = 200_000,
        max_backoff_s: float = 30.0,
    ) -> None:
        self.http = http
        self.master = master
        self.clock = clock
        self.recorder = recorder or NullRecorder()
        self.max_keys = dict(max_keys)
        self.max_backoff_s = max_backoff_s
        self._conns = [_Connection(n, m, self) for n, m in connections]
        self._q: asyncio.Queue[MarketEvent] = asyncio.Queue(maxsize=queue_size)
        self._dropped = 0
        self._started = False

    @classmethod
    def build(cls, ctx: AppContext) -> UpstoxMarketFeed:
        u, f = ctx.cfg.upstox, ctx.cfg.feed
        http = UpstoxHttp(secret(u.analytics_token_env), api_base=u.api_base, hft_base=u.hft_base,
                          timeout_s=u.timeout_s, rest_per_sec=u.rest_per_sec)
        return cls(http=http, master=ctx.master, clock=ctx.clock, recorder=ctx.recorder,
                   connections=[(c.name, list(c.modes)) for c in f.connections], max_keys=f.max_keys,
                   queue_size=f.queue_size, max_backoff_s=f.reconnect_max_backoff_s)

    # ---- plumbing used by connections -------------------------------------------------------

    async def authorize(self) -> str:
        body = await self.http.get(AUTHORIZE_PATH)
        data = body.get("data", {})
        return data.get("authorized_redirect_uri") or data["authorizedRedirectUri"]

    def resolve(self, native: str) -> InstrumentId | None:
        return self.master.from_native(native)

    def _publish(self, ev: MarketEvent) -> None:
        try:
            self._q.put_nowait(ev)
        except asyncio.QueueFull:
            self._dropped += 1

    def _conn_for(self, mode: FeedMode) -> _Connection:
        for c in self._conns:
            if mode in c.modes:
                return c
        raise ValueError(f"no connection configured for mode {mode}")

    # ---- MarketDataFeed ---------------------------------------------------------------------

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for c in self._conns:
            c.task = asyncio.create_task(c.run(), name=f"feed-{c.name}")

    async def stop(self) -> None:
        for c in self._conns:
            if c.task:
                c.task.cancel()
        await asyncio.gather(*(c.task for c in self._conns if c.task), return_exceptions=True)
        self._started = False

    async def set_subscriptions(self, want: Mapping[InstrumentId, FeedMode]) -> None:
        counts: dict[FeedMode, int] = {}
        for m in want.values():
            counts[m] = counts.get(m, 0) + 1
        for m, n in counts.items():
            cap = self.max_keys.get(m)
            if cap is not None and n > cap:
                raise ValueError(f"{n} keys in {m.value} exceeds the configured cap of {cap}")
        per_conn: dict[str, dict[str, FeedMode]] = {c.name: {} for c in self._conns}
        for iid, mode in want.items():
            per_conn[self._conn_for(mode).name][self.master.to_native(iid)] = mode
        for c in self._conns:
            c.want = per_conn[c.name]
        await asyncio.gather(*(c.sync() for c in self._conns))

    async def events(self) -> AsyncIterator[MarketEvent]:
        while True:
            yield await self._q.get()

    def health(self) -> FeedHealth:
        h = FeedHealth(dropped=self._dropped)
        h.connected = all(c.health.connected for c in self._conns if c.want)
        for c in self._conns:
            h.frames += c.health.frames
            h.messages += c.health.messages
            h.reconnects += c.health.reconnects
            h.decode_errors += c.health.decode_errors
            h.last_msg_ns = max(h.last_msg_ns, c.health.last_msg_ns)
            for k, v in c.health.subscribed.items():
                h.subscribed[k] = h.subscribed.get(k, 0) + v
        return h

    def connection_health(self) -> dict[str, FeedHealth]:
        return {c.name: c.health for c in self._conns}
