"""Build and run a trading session: live paper (from the recorder's broadcast) or replay.

    trader paper              # every trading day, unattended
    trader replay --date D    # re-run a recorded day; prints the journal digest

Both use the same `Engine`, the same decoder and the event clock, so a replay of a
recorded day must produce the identical journal digest (design §10, Phase 1 exit).
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import structlog

from trader.adapters.local.feed import LocalFrameFeed, ReplayFeed
from trader.adapters.paper.trader import PaperSettings, PaperTrader
from trader.adapters.upstox.http import UpstoxHttp
from trader.adapters.upstox.instruments import UpstoxInstrumentMaster
from trader.core.clock import SimClock, WallClock
from trader.core.config import CONFIG_DIR, AppConfig, secret
from trader.core.costs import CostModel
from trader.core.registry import notifiers
from trader.core.universe import fno_stock_underlyings, index_constituents
from trader.domain.instrument import InstrumentId
from trader.domain.types import IST, Exchange, InstrumentKind, to_paise
from trader.engine.session import Book, Engine, drain_all
from trader.intel.filings import FilingStore
from trader.market.history import ContextStore, fetch_contexts
from trader.market.reference import DayReference, ensure_day_reference
from trader.oms.journal import Journal
from trader.oms.manager import OrderManager
from trader.ports.infra import Severity
from trader.risk.engine import BookStatus, RiskConfig, RiskEngine
from trader.strategies.base import strategies

log = structlog.get_logger(__name__)

INDEX = InstrumentId.parse("NSE:IDX:NIFTY50")
VIX = InstrumentId.parse("NSE:IDX:INDIAVIX")
BOOKS = (("A", True), ("B", False))  # (name, day-type gated)
SETUPS = ("E1_ORB_RETEST", "E2_VWAP_RECLAIM")


def load_sectors(data_dir: Path) -> dict[str, str]:
    files = sorted((Path(data_dir) / "reference" / "indices").glob("nifty500-*.csv"))
    if not files:
        return {}
    rows = csv.DictReader(io.StringIO(files[-1].read_text(encoding="utf-8-sig")))
    return {r["Symbol"].strip().upper(): (r.get("Industry") or "").strip() for r in rows if r.get("Symbol")}


@dataclass
class BookLedger:
    """Persistent paper equity per book: compounding P&L, high-water mark, history."""

    path: Path
    equity: int
    hwm: int
    history: list[dict[str, Any]]

    @classmethod
    def load(cls, data_dir: Path, name: str, start_equity: int) -> BookLedger:
        p = Path(data_dir) / "state" / f"book-{name}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return cls(p, d["equity"], d["hwm"], d.get("history", []))
        return cls(p, start_equity, start_equity, [])

    def period_pnl(self, day: date) -> tuple[int, int]:
        wk = day - timedelta(days=day.weekday())
        week = sum(h["pnl"] for h in self.history if date.fromisoformat(h["day"]) >= wk)
        month = sum(h["pnl"] for h in self.history if h["day"][:7] == day.isoformat()[:7])
        return week, month

    def close_day(self, day: date, pnl: int, summary: dict[str, Any]) -> None:
        self.history = [h for h in self.history if h["day"] != day.isoformat()]
        self.history.append({"day": day.isoformat(), "pnl": pnl, **summary})
        self.equity += pnl
        self.hwm = max(self.hwm, self.equity)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"equity": self.equity, "hwm": self.hwm, "history": self.history},
                                        indent=1), encoding="utf-8")


def _http(cfg: AppConfig) -> UpstoxHttp:
    return UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base,
                      rest_per_sec=cfg.upstox.rest_per_sec)


async def load_dayref(cfg: AppConfig, master: UpstoxInstrumentMaster, day: date, contexts: dict[str, Any],
                      *, fetch: bool) -> DayReference | None:
    path = Path(cfg.system.data_dir) / "reference" / f"dayref-{day.isoformat()}.json"
    if not fetch:
        return DayReference.load(path) if path.exists() else None
    iids = [InstrumentId.parse(k) for k in contexts if k.startswith("NSE:EQ:")]
    return await ensure_day_reference(cfg.system.data_dir, day, lambda: _http(cfg), master, iids)


async def ensure_contexts(cfg: AppConfig, master: UpstoxInstrumentMaster, day: date) -> dict[str, Any]:
    store = ContextStore(cfg.system.data_dir)
    if store.path(day).exists():
        return store.load(day)
    universe = [InstrumentId(Exchange.NSE, InstrumentKind.EQ, s) for s in sorted(fno_stock_underlyings(master))]
    universe = [i for i in universe if master.find(i)] + [i for i in (INDEX, VIX) if master.find(i)]
    http = UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base,
                      rest_per_sec=cfg.upstox.rest_per_sec)
    try:
        ctx = await fetch_contexts(http, master, universe, day)
    finally:
        await http.aclose()
    store.save(day, ctx)
    return ctx


def load_master(cfg: AppConfig, day: date) -> UpstoxInstrumentMaster:
    m = UpstoxInstrumentMaster(data_dir=cfg.system.data_dir, url=cfg.upstox.instruments_url)
    p = m.path_for(day)
    if not p.exists():
        raise FileNotFoundError(f"no instrument master saved for {day} ({p}); the recorder saves one daily")
    m.load_rows(json.loads(gzip.decompress(p.read_bytes())))
    m.day = day
    return m


def build_engine(cfg: AppConfig, day: date, clock: Any, master: UpstoxInstrumentMaster, contexts: dict[str, Any],
                 journal: Journal, *, notify: Any = None, ledgers: dict[str, BookLedger] | None = None,
                 dayref: DayReference | None = None) -> Engine:
    risk_cfg = RiskConfig.load(CONFIG_DIR / "risk.yaml")
    paper = PaperSettings(**cfg.venue_settings("paper"))
    costs = CostModel.load(CONFIG_DIR / "costs.yaml", paper.cost_profile)
    sectors = load_sectors(cfg.system.data_dir)
    risk = RiskEngine(risk_cfg, costs, sectors=sectors)
    shortable = frozenset(InstrumentId(Exchange.NSE, InstrumentKind.EQ, s) for s in fno_stock_underlyings(master))
    books = []
    for name, gated in BOOKS:
        led = (ledgers or {}).get(name)
        equity = led.equity if led else to_paise(risk_cfg.equity_inr)
        week, month = led.period_pnl(day) if led else (0, 0)
        status = BookStatus(equity=equity, hwm=led.hwm if led else equity, week_pnl=week, month_pnl=month)
        # never start()ed: no background poll, so fills happen only on market events (deterministic)
        trader = PaperTrader(clock, settings=paper.model_copy(update={"starting_capital_inr": equity / 100}),
                             master=master, costs=costs)
        oms = OrderManager(book=name, code=name, trader=trader, clock=clock, journal=journal,
                           tag_prefix=cfg.system.tag_prefix, status=status, stop_attach_s=risk_cfg.stop_attach_s)
        strats = [strategies.create(s) for s in SETUPS]
        books.append(Book(name, name, gated, trader, oms, strats))
    news_db = Path(cfg.system.data_dir) / "intel" / "filings.sqlite"
    news = FilingStore(news_db) if news_db.exists() else None
    return Engine(clock=clock, day=day, master=master, contexts=contexts, sectors=sectors, shortable=shortable,
                  risk=risk, journal=journal, books=books, index_iid=INDEX, vix_iid=VIX, notify=notify, news=news,
                  dayref=dayref)


# ---- replay -----------------------------------------------------------------------------------


async def replay_day(cfg: AppConfig, day: date, *, journal_path: Path | None = None) -> tuple[str, dict[str, Any]]:
    master = load_master(cfg, day)
    contexts = await ensure_contexts(cfg, master, day)
    start = int(datetime.combine(day, time(9, 0), IST).timestamp() * 1e9)
    clock = SimClock(start)
    journal = Journal(journal_path)
    dayref = await load_dayref(cfg, master, day, contexts, fetch=False)
    engine = build_engine(cfg, day, clock, master, contexts, journal, dayref=dayref)
    for ev in ReplayFeed(cfg.system.data_dir, day, master, clock, start_ns=start):
        await engine.on_event(ev)
    end = int(datetime.combine(day, time(15, 30), IST).timestamp() * 1e9)
    if clock.now_ns() < end:
        clock.set(end)
    await engine.on_time(end)
    await drain_all(engine)
    digest = journal.digest()
    summary = engine.summary()
    summary["journal_events"] = journal.count
    journal.close()
    return digest, summary


# ---- live paper -----------------------------------------------------------------------------------


class EventClock(SimClock):
    """Event time in live mode: set from each frame's receive time; a heartbeat moves it
    forward with wall time when the feed is quiet, so schedules still fire."""


async def run_paper_day(cfg: AppConfig, day: date) -> dict[str, Any]:
    data_dir = cfg.system.data_dir
    master = load_master(cfg, day)
    contexts = await ensure_contexts(cfg, master, day)
    await index_constituents("nifty500", cfg.universe["index_constituents"]["nifty500"]["urls"],
                             data_dir / "reference" / "indices", day.strftime("%Y-%m"))
    ncls = notifiers.get(cfg.notifier.provider)
    notifier = ncls(**cfg.notifier.settings.get(cfg.notifier.provider, {}))
    pending: set[asyncio.Task[None]] = set()

    def notify(text: str, sev: Severity = Severity.INFO) -> None:
        t = asyncio.create_task(notifier.notify(text, sev))
        pending.add(t)
        t.add_done_callback(pending.discard)

    wall = WallClock()
    clock = EventClock(wall.now_ns())
    journal = Journal(data_dir / "journal" / f"{day.isoformat()}.sqlite")
    ledgers = {name: BookLedger.load(data_dir, name, to_paise(RiskConfig.load(CONFIG_DIR / "risk.yaml").equity_inr))
               for name, _ in BOOKS}
    carried = _prior_session(journal)
    dayref = await load_dayref(cfg, master, day, contexts, fetch=True)
    engine = build_engine(cfg, day, clock, master, contexts, journal, notify=notify, ledgers=ledgers, dayref=dayref)
    if carried["restarted"]:
        # In-memory positions from before the restart are gone. Be conservative and honest:
        # lock both books for the day, carry the realized P&L, and tell the owner.
        for b in engine.books:
            b.status.locked = True
        journal.write(clock.now_ns(), "*", "restart", {"orphans": carried["orphans"]})
        notify(f"Paper process restarted mid-session; books locked for the rest of {day}. "
               f"Abandoned open paper positions: {', '.join(carried['orphans']) or 'none'}.", Severity.WARN)
    feed = LocalFrameFeed(master=master, clock=clock, port=cfg.recorder.broadcast_port)
    await feed.start()
    if not carried["restarted"]:
        notify(f"Paper trading started {day}: {len(engine.states)} symbols, books A (gated) and B (baseline), "
               f"setups {', '.join(SETUPS)}")
    end = datetime.combine(day, time(15, 25), IST)

    last_alert = [0]

    def failed(where: str) -> None:
        log.exception("paper.engine_error", where=where)
        if wall.now_ns() - last_alert[0] > 600e9:  # at most one alert per 10 minutes
            last_alert[0] = wall.now_ns()
            notify(f"Paper engine error in {where}; continuing. See logs.", Severity.WARN)

    async def heartbeat() -> None:
        while not engine.ended:
            await asyncio.sleep(1.0)
            now = wall.now_ns()
            if now > clock.now_ns() + 1_500_000_000:
                clock.set(now)
                try:
                    await engine.on_time(now)
                except Exception:  # noqa: BLE001
                    failed("on_time")

    hb = asyncio.create_task(heartbeat())
    bot_task = _start_command_bot(cfg, engine, clock, journal)
    try:
        async for ev in feed.events():
            ts = getattr(ev, "ts_recv_ns", 0)
            if ts > clock.now_ns():
                clock.set(ts)
            try:
                await engine.on_event(ev)
            except Exception:  # noqa: BLE001 - one bad event must not end the session
                failed("on_event")
            if engine.ended or clock.now_ns() >= end.timestamp() * 1e9:
                break
    finally:
        hb.cancel()
        if bot_task is not None:
            bot_task.cancel()
        await feed.stop()
        await drain_all(engine)
    summary = engine.summary()
    for name, b in summary["books"].items():
        b["pnl"] += carried["realized"].get(name, 0) / 100
        b["realized"] += carried["realized"].get(name, 0) / 100
        b["trades"] += carried["trades"].get(name, 0)
        b["wins"] += carried["wins"].get(name, 0)
    summary["restarted"] = carried["restarted"]
    for name, led in ledgers.items():
        b = summary["books"][name]
        led.close_day(day, round(b["pnl"] * 100), {"trades": b["trades"], "wins": b["wins"]})
    summary["equity"] = {n: led.equity / 100 for n, led in ledgers.items()}
    summary["digest"] = journal.digest()
    journal.close()
    from trader.reports.daily import send_daily_report

    await send_daily_report(cfg, day, summary, notifier)
    await asyncio.gather(*pending, return_exceptions=True)
    return summary


def _prior_session(journal: Journal) -> dict[str, Any]:
    """What an earlier run of today's session left in the journal (crash/restart recovery)."""
    rows = journal.rows()
    out: dict[str, Any] = {"restarted": any(k == "order" for _t, _b, k, _d in rows),
                           "realized": {}, "trades": {}, "wins": {}, "orphans": []}
    if not out["restarted"]:
        return out
    entered: dict[str, str] = {}
    closed: set[str] = set()
    for _t, book, kind, d in rows:
        if kind == "fill" and d.get("role") == "entry":
            entered[d["trade"]] = f"{book}:{d['fill']['iid'].split(':')[2]}"
        elif kind == "trade_closed":
            closed.add(d["trade"])
            out["realized"][book] = out["realized"].get(book, 0) + d["net"]
            out["trades"][book] = out["trades"].get(book, 0) + 1
            out["wins"][book] = out["wins"].get(book, 0) + int(d["net"] > 0)
    out["orphans"] = sorted({v for k, v in entered.items() if k not in closed})
    return out


def _start_command_bot(cfg: AppConfig, engine: Engine, clock: Any, journal: Journal) -> asyncio.Task[None] | None:
    """Phone control (owner choice: same bot, PIN, tighten-only). Only the paper process polls."""
    import os

    from trader.ops.commands import CommandBot

    if cfg.notifier.provider != "telegram":
        return None
    try:
        token, chat = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
    except Exception:  # noqa: BLE001
        return None
    pin = os.environ.get("TELEGRAM_COMMAND_PIN", "").strip() or None

    async def status() -> str:
        s = engine.summary()
        lines = [f"Day type {s['day_type']}; in play: {', '.join(i.split(':')[2] for i in s['in_play'])}"]
        for name, b in s["books"].items():
            lines.append(f"{name}: ₹{b['pnl']:+,.0f}, {b['trades']} closed, {b['open']} open"
                         + (" LOCKED" if b["locked"] else ""))
        for b in engine.books:
            for t in b.oms.open_trades():
                lines.append(f"  [{b.name}] {t.sig.iid.symbol} {t.side.value} {t.open_qty} @ {t.avg_entry / 100:.2f} "
                             f"stop {t.stop / 100:.2f}")
        return "\n".join(lines)

    async def pause() -> str:
        for b in engine.books:
            b.status.paused = True
        return "Paused: no new entries for the rest of the session. Exits and stops continue."

    async def flatten() -> str:
        for b in engine.books:
            b.status.locked = True
            await b.oms.flatten_all(engine.states, "owner flatten (Telegram)")
        return "Flattening all positions and locking the day."

    def audit(cmd: str, accepted: bool) -> None:
        journal.write(clock.now_ns(), "*", "human_override", {"cmd": cmd, "accepted": accepted, "via": "telegram"})

    bot = CommandBot(token=token, chat_id=chat, pin=pin, status=status, pause=pause, flatten=flatten, audit=audit)
    return asyncio.create_task(bot.run(), name="telegram-commands")


async def run_paper_forever(cfg: AppConfig) -> None:
    from trader.core.calendar import MarketCalendar, fetch_holidays

    http = UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base)
    wall = WallClock()
    while True:
        now = datetime.fromtimestamp(wall.now_ns() / 1e9, IST)
        day = now.date()
        cal = MarketCalendar.from_cache(await fetch_holidays(http, cfg.system.data_dir / "reference", day.year))
        start = datetime.combine(day, time(8, 55), IST)
        stop = datetime.combine(day, time(15, 20), IST)
        if cal.is_trading_day(day) and now < stop:
            while datetime.fromtimestamp(wall.now_ns() / 1e9, IST) < start:
                await asyncio.sleep(20)
            for _ in range(60):  # the recorder saves the day's master shortly after 08:50
                if UpstoxInstrumentMaster(data_dir=cfg.system.data_dir, url="").path_for(day).exists():
                    break
                await asyncio.sleep(10)
            summary = await run_paper_day(cfg, day)
            log.info("paper.day_done", summary=summary)
            return  # exit; the supervisor restarts us on the latest code for the next day
        nxt = cal.next_trading_day(day)
        while datetime.fromtimestamp(wall.now_ns() / 1e9, IST) < datetime.combine(nxt, time(8, 30), IST):
            await asyncio.sleep(60)
