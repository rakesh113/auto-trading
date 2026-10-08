"""The daily recorder (design D7, Phase 0): runs every trading day, unattended.

Day loop:
  1. Wait for the next trading day (holiday list from Upstox, cached).
  2. 08:50 IST: load the instrument master, build the recording plan, subscribe.
  3. Record raw frames to bronze until 15:50 IST, re-centring the option-greeks
     windows every few minutes as spot moves.
  4. Close files, sleep until the next trading day.

Writes a small status file every 30 s for the supervisor and for humans.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, time, timedelta
from typing import Any

import structlog

from trader.adapters.upstox.http import UpstoxHttp
from trader.core.app import build_app
from trader.core.calendar import MarketCalendar, fetch_holidays
from trader.core.clock import WallClock
from trader.core.config import AppConfig, secret
from trader.core.universe import build_recording_plan, index_constituents, option_window
from trader.domain.instrument import InstrumentId
from trader.domain.market import FeedState, MarketEvent, Quote
from trader.domain.types import IST, Exchange, FeedMode
from trader.ops.power import keep_awake
from trader.ports.clock import now_ist
from trader.recorder.bronze import BronzeRecorder

log = structlog.get_logger(__name__)

START = time(8, 50)
STOP = time(15, 50)
_CLOCK = WallClock()


class _SpotTracker:
    def __init__(self, spots: set[InstrumentId]) -> None:
        self.spots = spots
        self.last: dict[InstrumentId, int] = {}
        self.events = 0
        self.states: list[str] = []

    def __call__(self, ev: MarketEvent) -> None:
        self.events += 1
        if isinstance(ev, Quote) and ev.iid in self.spots and ev.ltp > 0:
            self.last[ev.iid] = ev.ltp
        elif isinstance(ev, FeedState):
            self.states.append(f"{ev.connection}:{ev.state}")


async def _rest_ltp(http: UpstoxHttp, native_keys: list[str]) -> dict[str, int]:
    body = await http.get("/v3/market-quote/ltp", params={"instrument_key": ",".join(native_keys)})
    out: dict[str, int] = {}
    for v in (body.get("data") or {}).values():
        tok = v.get("instrument_token")
        if tok and v.get("last_price"):
            out[tok] = round(float(v["last_price"]) * 100)
    return out


async def _sleep_until(dt: datetime) -> None:
    while True:
        delta = (dt - now_ist(_CLOCK)).total_seconds()
        if delta <= 0:
            return
        await asyncio.sleep(min(delta, 60))


async def record_day(cfg: AppConfig, *, until: datetime | None = None) -> dict[str, Any]:
    """Record one session. Returns a summary."""
    data_dir = cfg.system.data_dir
    recorder = BronzeRecorder(data_dir, rotate_minutes=cfg.recorder.rotate_minutes,
                              zstd_level=cfg.recorder.zstd_level, flush_every_s=cfg.recorder.flush_every_s)
    app = build_app(cfg, recorder=recorder, with_trader=False)
    feed = app.feed
    assert feed is not None
    today = now_ist(app.ctx.clock).date()
    n = await app.master.load(today)
    log.info("recorder.master", instruments=n)
    uni = cfg.universe
    n500 = await index_constituents("nifty500", uni["index_constituents"]["nifty500"]["urls"],
                                    data_dir / "reference" / "indices", today.strftime("%Y-%m"))
    plan = build_recording_plan(app.master, uni, today, n500)
    chains = uni.get("record", {}).get("greeks_chains", [])
    spots = {InstrumentId.parse(c["spot"]) for c in chains}
    tracker = _SpotTracker(spots)
    app.listeners.append(tracker)

    http: UpstoxHttp = feed.http  # type: ignore[attr-defined]

    async def greeks_want() -> dict[InstrumentId, FeedMode]:
        want: dict[InstrumentId, FeedMode] = {}
        missing = [s for s in spots if s not in tracker.last and app.master.find(s)]
        if missing:
            try:
                ltp = await _rest_ltp(http, [app.master.to_native(s) for s in missing])
                for s in missing:
                    p = ltp.get(app.master.to_native(s))
                    if p:
                        tracker.last[s] = p
            except Exception as e:  # noqa: BLE001
                log.warning("recorder.spot_ltp_failed", error=repr(e))
        for c in chains:
            spot = tracker.last.get(InstrumentId.parse(c["spot"]))
            if not spot:
                continue
            for iid in option_window(app.master, c["underlying"], Exchange(c["exchange"]), today, spot,
                                     int(c["strikes_each_side"])):
                want[iid] = FeedMode.OPTION_GREEKS
        return want

    want = dict(plan.want)
    for iid, m in (await greeks_want()).items():
        want.setdefault(iid, m)
    counts: dict[str, int] = {}
    for m in want.values():
        counts[m.value] = counts.get(m.value, 0) + 1
    log.info("recorder.plan", counts=counts, unmapped=len(plan.missing))

    status_path = data_dir / "status" / "recorder.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    stop_at = until or datetime.combine(today, STOP, IST)
    recenter_s = 60 * int(uni.get("record", {}).get("greeks_recenter_min", 5))
    with keep_awake() as awake:
        log.info("recorder.keep_awake", active=awake)
        await app.start(load_master=False)
        await feed.set_subscriptions(want)
        last_recenter = asyncio.get_running_loop().time()
        try:
            while now_ist(_CLOCK) < stop_at:
                await asyncio.sleep(min(30, max(0.1, (stop_at - now_ist(_CLOCK)).total_seconds())))
                h = feed.health()
                status = {
                    "ts": now_ist(_CLOCK).isoformat(timespec="seconds"), "connected": h.connected,
                    "frames": h.frames, "events": h.messages, "reconnects": h.reconnects,
                    "decode_errors": h.decode_errors, "dropped_feed": h.dropped,
                    "recorder_written": recorder.written, "recorder_dropped": recorder.dropped,
                    "subscribed": h.subscribed, "recent_states": tracker.states[-10:],
                }
                status_path.write_text(json.dumps(status, indent=1), encoding="utf-8")
                log.info("recorder.status", **{k: v for k, v in status.items() if k != "recent_states"})
                if asyncio.get_running_loop().time() - last_recenter >= recenter_s:
                    last_recenter = asyncio.get_running_loop().time()
                    g = await greeks_want()
                    if g:
                        new = {k: v for k, v in want.items() if v is not FeedMode.OPTION_GREEKS}
                        for iid, m in g.items():
                            new.setdefault(iid, m)
                        if new != want:
                            want = new
                            await feed.set_subscriptions(want)
                            log.info("recorder.recentered", greeks=len(g))
        finally:
            await app.stop()
    return {"frames": feed.health().frames, "written": recorder.written, "dropped": recorder.dropped,
            "unmapped": plan.missing}


async def run_forever(cfg: AppConfig) -> None:
    http = UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base)
    ref = cfg.system.data_dir / "reference"
    while True:
        now = now_ist(_CLOCK)
        today = now.date()
        cal = MarketCalendar.from_cache(await fetch_holidays(http, ref, today.year))
        start = datetime.combine(today, START, IST)
        stop = datetime.combine(today, STOP, IST)
        if cal.is_trading_day(today) and now < stop:
            if now < start:
                log.info("recorder.waiting", until=start.isoformat())
                await _sleep_until(start)
            try:
                summary = await record_day(cfg)
                log.info("recorder.day_done", **{k: v for k, v in summary.items() if k != "unmapped"})
            except Exception:
                log.exception("recorder.day_failed")
                await asyncio.sleep(30)  # retry within the session; the supervisor also restarts us
                continue
        nxt_day = today + timedelta(days=1)
        if nxt_day.year != today.year:
            await fetch_holidays(http, ref, nxt_day.year)
        cal = MarketCalendar.from_cache(await fetch_holidays(http, ref, nxt_day.year))
        nxt = cal.next_trading_day(today)
        wake = datetime.combine(nxt, START, IST) - timedelta(minutes=5)
        log.info("recorder.sleeping", until=wake.isoformat(), next_trading_day=nxt.isoformat())
        await _sleep_until(wake)


__all__ = ["record_day", "run_forever"]
