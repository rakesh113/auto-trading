"""Feeds that decode raw Upstox frames from a local source instead of a broker socket.

* ``LocalFrameFeed`` ("local"): live, from the recorder's broadcast on 127.0.0.1.
* ``ReplayFeed``: a recorded day from bronze files, in receive-time order, driving a
  SimClock. Same decoder, same events as live (design §10 replay parity).

Subscriptions are owned by the recorder (it subscribes the superset), so
`set_subscriptions` only records what the consumer is interested in.
"""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from trader.adapters.upstox.decode import decode_frame
from trader.adapters.upstox.feed import KIND_FRAME, KIND_STATE
from trader.core.clock import SimClock
from trader.core.registry import feeds
from trader.domain.instrument import InstrumentId
from trader.domain.market import FeedState, MarketEvent
from trader.domain.types import FeedMode
from trader.ports.clock import Clock
from trader.ports.marketdata import FeedHealth, InstrumentMaster, MarketDataFeed
from trader.recorder.broadcast import DEFAULT_PORT, read_record
from trader.recorder.bronze import read_frames

if TYPE_CHECKING:
    from trader.core.app import AppContext

log = structlog.get_logger(__name__)


@feeds.register("local")
class LocalFrameFeed(MarketDataFeed):
    def __init__(self, *, master: InstrumentMaster, clock: Clock, port: int = DEFAULT_PORT,
                 queue_size: int = 200_000) -> None:
        self.master = master
        self.clock = clock
        self.port = port
        self._q: asyncio.Queue[MarketEvent] = asyncio.Queue(maxsize=queue_size)
        self._task: asyncio.Task[None] | None = None
        self._health = FeedHealth()
        self.wanted: dict[InstrumentId, FeedMode] = {}

    @classmethod
    def build(cls, ctx: AppContext) -> LocalFrameFeed:
        return cls(master=ctx.master, clock=ctx.clock, queue_size=ctx.cfg.feed.queue_size)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="local-feed")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def set_subscriptions(self, want: Mapping[InstrumentId, FeedMode]) -> None:
        self.wanted = dict(want)

    async def events(self) -> AsyncIterator[MarketEvent]:
        while True:
            yield await self._q.get()

    def health(self) -> FeedHealth:
        return self._health

    def _publish(self, ev: MarketEvent) -> None:
        try:
            self._q.put_nowait(ev)
        except asyncio.QueueFull:
            self._health.dropped += 1

    async def _run(self) -> None:
        backoff = 1.0
        down_since = 0
        while True:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            except OSError:
                if not down_since:
                    down_since = self.clock.now_ns()
                    self._publish(FeedState(connection="local", state="DISCONNECTED", ts_recv_ns=down_since,
                                            detail="recorder broadcast not reachable"))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
                continue
            backoff = 1.0
            self._health.connected = True
            self._publish(FeedState(connection="local", state="GAP" if down_since else "CONNECTED",
                                    ts_recv_ns=self.clock.now_ns(), since_ns=down_since))
            down_since = 0
            try:
                while True:
                    stream, kind, ts, payload = await read_record(reader)
                    for ev in _decode(stream, kind, ts, payload, self.master, self._health):
                        self._publish(ev)
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                pass
            finally:
                writer.close()
                self._health.connected = False
                down_since = self.clock.now_ns()
                self._publish(FeedState(connection="local", state="DISCONNECTED", ts_recv_ns=down_since))


def _decode(stream: str, kind: int, ts: int, payload: bytes, master: InstrumentMaster,
            health: FeedHealth) -> list[MarketEvent]:
    if kind == KIND_STATE:
        state = payload.decode(errors="replace")
        return [FeedState(connection=stream, state=state, ts_recv_ns=ts)]
    if kind != KIND_FRAME:
        return []
    health.frames += 1
    health.last_msg_ns = ts
    try:
        evs = decode_frame(payload, ts, master.from_native)
    except Exception:  # noqa: BLE001
        health.decode_errors += 1
        return []
    health.messages += len(evs)
    return evs


def recorded_records(data_dir: Path, day: date) -> Iterator[tuple[int, str, int, bytes]]:
    """(ts, stream, kind, payload) for a recorded day, merged across streams by receive time."""
    root = Path(data_dir) / "bronze" / day.isoformat()

    def stream_iter(sdir: Path) -> Iterator[tuple[int, str, int, bytes]]:
        for f in sorted(sdir.glob("*.frames.zst")):
            for ts, kind, payload in read_frames(f):
                yield ts, sdir.name, kind, payload

    iters = [stream_iter(d) for d in sorted(p for p in root.iterdir() if p.is_dir())]
    yield from heapq.merge(*iters, key=lambda r: r[0])


class ReplayFeed:
    """Drives a SimClock through a recorded day and yields decoded events in order."""

    def __init__(self, data_dir: Path, day: date, master: InstrumentMaster, clock: SimClock,
                 *, start_ns: int = 0, end_ns: int = 2**63 - 1) -> None:
        self.data_dir = data_dir
        self.day = day
        self.master = master
        self.clock = clock
        self.start_ns = start_ns
        self.end_ns = end_ns
        self.health = FeedHealth()

    def __iter__(self) -> Iterator[MarketEvent]:
        for ts, stream, kind, payload in recorded_records(self.data_dir, self.day):
            if ts < self.start_ns:
                continue
            if ts > self.end_ns:
                break
            if ts > self.clock.now_ns():
                self.clock.set(ts)
            yield from _decode(stream, kind, ts, payload, self.master, self.health)
