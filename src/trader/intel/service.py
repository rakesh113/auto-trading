"""The intel process (design §10 `intel-worker`): filings ingestion, triage bake-off and the
pre-market brief. Separate from the trading process so the hot path never waits on a model.

Writes to `<data_dir>/intel/filings.sqlite`; the engine reads non-routine filings from
there to impose a news blackout on the symbol (design §3: news creates a blackout, not
a signal). Exits after the evening session; the supervisor restarts it the next day.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import date, datetime, time, timedelta

import structlog

from trader.core.clock import WallClock
from trader.core.config import AppConfig
from trader.core.registry import notifiers
from trader.core.universe import fno_stock_underlyings
from trader.domain.types import IST
from trader.intel.brief import run_brief, situation_report
from trader.intel.filings import BseFilings, Filing, FilingStore, NseFilings
from trader.intel.openrouter import OpenRouterProvider
from trader.intel.triage import TriageBakeoff, state_text
from trader.market.history import ContextStore

log = structlog.get_logger(__name__)

START, BRIEF_AT, END = time(8, 0), time(8, 35), time(23, 30)


def _now(c: WallClock) -> datetime:
    return datetime.fromtimestamp(c.now_ns() / 1e9, IST)


class SymbolMap:
    """NSE symbol / BSE scrip code → canonical NSE equity id, from the day's raw Upstox master."""

    def __init__(self, raw_rows: list[dict]) -> None:
        nse_by_isin = {r["isin"]: r["trading_symbol"] for r in raw_rows
                       if r.get("segment") == "NSE_EQ" and r.get("instrument_type") in ("EQ", "BE") and r.get("isin")}
        self.nse = set(nse_by_isin.values())
        self.bse = {str(r["exchange_token"]): nse_by_isin[r["isin"]] for r in raw_rows
                    if r.get("segment") == "BSE_EQ" and r.get("isin") in nse_by_isin}

    def iid(self, f: Filing) -> str | None:
        sym = f.symbol if f.exchange == "NSE" else self.bse.get(f.symbol)
        return f"NSE:EQ:{sym}" if sym and sym in self.nse else None


async def run_intel_day(cfg: AppConfig, day: date) -> None:
    from trader.engine.runner import ensure_contexts, load_master

    data_dir = cfg.system.data_dir
    clock = WallClock()
    master = load_master(cfg, day)
    raw = json.loads(gzip.decompress(master.path_for(day).read_bytes()))
    smap = SymbolMap(raw)
    tradable = {f"NSE:EQ:{s}" for s in fno_stock_underlyings(master)}
    try:  # build the day's context early so the 08:35 brief and the paper trader share it
        contexts = await ensure_contexts(cfg, master, day)
    except Exception:  # noqa: BLE001
        log.exception("intel.context_failed")
        ctx_store = ContextStore(data_dir)
        contexts = ctx_store.load(day) if ctx_store.path(day).exists() else {}
    store = FilingStore(data_dir / "intel" / "filings.sqlite")
    routes = list((cfg.llm.routes.get("triage") or {}).get("bakeoff") or [])
    bake = TriageBakeoff(routes, api_key_env=cfg.llm.api_key_env) if routes else None
    nse, bse = NseFilings(), BseFilings()
    ncls = notifiers.get(cfg.notifier.provider)
    notifier = ncls(**cfg.notifier.settings.get(cfg.notifier.provider, {}))
    backfilled = False
    brief_done = (data_dir / "intel" / f"brief-{day.isoformat()}.json").exists()
    stats = {"seen": 0, "non_routine": 0, "triaged": 0}

    async def triage(f: Filing, iid: str) -> None:
        if bake is None:
            return
        c = contexts.get(iid)
        ctx = state_text(f, last_price=c.pdc / 100 if c else None, turnover_cr=c.median_turnover_cr if c else None)
        results = await bake.run(f, ctx)
        for route, (res, lat, cost, err) in results.items():
            store.record_triage(f.key, route, clock.now_ns(), lat, cost, res or {"error": err})
        stats["triaged"] += 1

    while True:
        now = _now(clock)
        if now.time() >= END or now.date() != day:
            break
        if not brief_done and now.time() >= BRIEF_AT:
            brief_done = True
            try:
                await _brief(cfg, day, store, contexts, notifier)
            except Exception:
                log.exception("intel.brief_failed")
        fetched: list[Filing] = []
        for name, coro in (("nse", nse.fetch(clock.now_ns(), day if not backfilled else None)),
                           ("bse", bse.fetch(clock.now_ns(), day))):
            try:
                fetched += await coro
            except Exception as e:  # noqa: BLE001
                log.warning("intel.fetch_failed", source=name, error=repr(e))
        backfilled = True
        jobs = []
        for f in sorted(fetched, key=lambda x: x.ts_exchange_ns):
            if store.seen(f.key):
                continue
            iid = smap.iid(f)
            if not store.add(f, iid):
                continue
            stats["seen"] += 1
            if f.routine or iid is None:
                continue
            stats["non_routine"] += 1
            if iid in tradable:
                jobs.append(triage(f, iid))
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        market = time(9, 0) <= now.time() <= time(15, 30)
        await asyncio.sleep(8 if market else 45)
    log.info("intel.day_done", **stats)
    store.close()


async def _brief(cfg: AppConfig, day: date, store: FilingStore, contexts: dict, notifier) -> None:
    route = (cfg.llm.routes.get("strategist") or {}).get("primary")
    if not route:
        return
    lines = []
    for key, label in (("NSE:IDX:NIFTY50", "Nifty 50"), ("NSE:IDX:INDIAVIX", "India VIX")):
        c = contexts.get(key)
        if c:
            lines.append(f"- {label}: close {c.pdc / 100:,.2f}, ATR14 {c.atr14 / 100:,.2f}, 52w {c.low_52w / 100:,.0f}"
                         f"-{c.high_52w / 100:,.0f}")
    since = int((datetime.combine(day, time(0, 0), IST) - timedelta(hours=18)).timestamp() * 1e9)
    rows = store.material_candidates(since, 2**62)
    filings = [{"symbol": iid.split(":")[2], "category": store.get(k).category, "headline": store.get(k).headline}
               for iid, _ts, k in rows]
    llm = OpenRouterProvider(api_key_env=cfg.llm.api_key_env)
    out = await run_brief(llm, route, situation_report(day, lines, filings), cfg.system.data_dir / "intel", day)
    await llm.aclose()
    b = out.get("brief") or {}
    if b:
        await notifier.notify(f"Pre-market brief (shadow, {out['model']}): prior {b['day_prior']}, risk "
                              f"{b['risk_level']}/3. Watch: {', '.join(b['watch'][:8]) or '-'}. {b['summary']}")


async def run_intel_forever(cfg: AppConfig) -> None:
    from trader.adapters.upstox.http import UpstoxHttp
    from trader.adapters.upstox.instruments import UpstoxInstrumentMaster
    from trader.core.calendar import MarketCalendar, fetch_holidays
    from trader.core.config import secret

    clock = WallClock()
    http = UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base)
    while True:
        now = _now(clock)
        day = now.date()
        cal = MarketCalendar.from_cache(await fetch_holidays(http, cfg.system.data_dir / "reference", day.year))
        if cal.is_trading_day(day) and now.time() < END:
            while _now(clock).time() < START:
                await asyncio.sleep(30)
            m = UpstoxInstrumentMaster(data_dir=cfg.system.data_dir, url=cfg.upstox.instruments_url)
            if not m.path_for(day).exists():
                await m.download(day)
            await run_intel_day(cfg, day)
            return
        nxt = cal.next_trading_day(day)
        while _now(clock) < datetime.combine(nxt, START, IST):
            await asyncio.sleep(60)
