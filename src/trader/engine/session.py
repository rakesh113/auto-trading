"""The trading engine for one session (design §3 hot plane, §12 counterfactual books).

One engine owns the market state; several *books* consume the same events:

* ``A`` production: setups + risk + the day-type gate (only HIGH_VOL_EVENT blocks in the MVP)
* ``B`` baseline: the same setups and risk with no day-type gate

Each book has its own PaperTrader, order manager and risk status, so paired daily
differences measure what each filter is worth. Everything runs on the event clock
(the receive time of the frame being processed), so a replay of the recorded frames
reproduces the live session's decisions exactly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog

from trader.domain.instrument import InstrumentId
from trader.domain.market import FeedState, MarketEvent, Quote
from trader.market.daytype import DayType, classify
from trader.market.history import DailyContext
from trader.market.selection import Scored, select
from trader.market.state import Bar, SymbolState, minute_of_session
from trader.oms.journal import Journal
from trader.oms.manager import OrderManager, Trade
from trader.ports.clock import Clock
from trader.ports.execution import Trader
from trader.ports.marketdata import InstrumentMaster
from trader.risk.engine import BookStatus, RiskEngine
from trader.strategies.base import MarketView, Strategy, at

log = structlog.get_logger(__name__)

SELECT_AT = (at(9, 12) - 1, at(9, 30), at(10, 30), at(12, 30), at(13, 30))  # 09:11:xx uses the pre-open price
DAYTYPE_AT = (at(9, 30), at(9, 45), at(10, 30), at(13, 30))
END_AT = at(15, 20)


@dataclass
class Book:
    name: str
    code: str
    gated: bool
    trader: Trader
    oms: OrderManager
    strategies: list[Strategy]

    @property
    def status(self) -> BookStatus:
        return self.oms.status


@dataclass
class Engine:
    clock: Clock
    day: date
    master: InstrumentMaster
    contexts: dict[str, DailyContext]
    sectors: dict[str, str]
    shortable: frozenset[InstrumentId]
    risk: RiskEngine
    journal: Journal
    books: list[Book]
    index_iid: InstrumentId
    vix_iid: InstrumentId | None = None
    notify: Callable[[str], None] | None = None
    news: Any = None  # FilingStore: non-routine filings impose a blackout on the symbol
    dayref: Any = None  # DayReference: F&O ban list and price bands
    blackout_min: int = 15
    states: dict[InstrumentId, SymbolState] = field(default_factory=dict)
    primary: list[Scored] = field(default_factory=list)
    watch: list[Scored] = field(default_factory=list)
    day_type: DayType = field(default_factory=lambda: DayType("UNKNOWN", (), {}))
    _done_select: set[int] = field(default_factory=set)
    _done_daytype: set[int] = field(default_factory=set)
    _flattened: set[str] = field(default_factory=set)
    _last_minute: int = -999
    _first_minute: int | None = None
    _news_ns: int = 0
    _blackout: dict[InstrumentId, int] = field(default_factory=dict)
    ended: bool = False
    feed_ok: bool = True

    def __post_init__(self) -> None:
        for key, ctx in self.contexts.items():
            iid = InstrumentId.parse(key)
            inst = self.master.find(iid)
            self.states[iid] = SymbolState(iid, ctx, tick=inst.tick_size if inst else 5)
        for iid in (self.index_iid, self.vix_iid):
            if iid is not None and iid not in self.states:
                self.states[iid] = SymbolState(iid, None)
        for b in self.books:
            for s in b.strategies:
                s.reset()
            b.oms.on_closed = self._closed_hook(b)

    # ---- helpers ----------------------------------------------------------------------------

    @property
    def index(self) -> SymbolState | None:
        return self.states.get(self.index_iid)

    def monitored(self, book: Book) -> set[InstrumentId]:
        names = {s.iid for s in self.primary}
        names |= {t.sig.iid for t in book.oms.open_trades()}
        return names

    def view(self, minute: int) -> MarketView:
        return MarketView(now_ns=self.clock.now_ns(), minute=minute, index=self.index,
                          day_type=self.day_type.label, in_play=frozenset(s.iid for s in self.primary),
                          shortable=self.shortable)

    def _say(self, text: str) -> None:
        if self.notify is not None:
            self.notify(text)

    def _closed_hook(self, book: Book) -> Callable[[Trade], None]:
        def hook(t: Trade) -> None:
            b = book.status
            b.trades_today += 1
            if t.net_pnl < 0:
                b.losers_today += 1
                b.consecutive_losses += 1
                if b.consecutive_losses >= self.risk.cfg.streak_losses_cooloff:
                    b.cooloff_until_ns = self.clock.now_ns() + int(self.risk.cfg.cooloff_min * 60e9)
                    b.reduced_trades_left = 2
                    b.consecutive_losses = 0
            else:
                b.consecutive_losses = 0
            if book.name == "A":
                self._say(f"[{book.name}] closed {t.sig.setup} {t.sig.iid.symbol} {t.side.value} "
                          f"{t.entry_qty} @ {t.avg_entry / 100:.2f}: net ₹{t.net_pnl / 100:,.0f} "
                          f"({t.r_multiple():+.2f}R) — {t.exit_reason}")
        return hook

    # ---- event entry points ---------------------------------------------------------------

    async def on_event(self, ev: MarketEvent) -> None:
        if isinstance(ev, FeedState):
            self.feed_ok = ev.state in ("CONNECTED", "GAP")
            self.journal.write(self.clock.now_ns(), "*", "feed_state", {"conn": ev.connection, "state": ev.state})
            return
        if not isinstance(ev, Quote) or ev.iid is None:
            return
        st = self.states.get(ev.iid)
        if st is None:
            return
        bars = st.on_quote(ev)
        for b in self.books:
            on_market = getattr(b.trader, "on_market", None)
            if on_market is not None:
                on_market(ev)
            await self._drain(b)
            await b.oms.on_quote(st)
        for bar in bars:
            await self._on_bar(st, bar)
        await self.on_time(ev.ts_recv_ns)

    async def _drain(self, b: Book) -> None:
        for e in b.trader.drain_events():
            await b.oms.on_exec(e, self.states)

    async def on_time(self, now_ns: int) -> None:
        """Clock-driven work: bar closes for watched names, schedules, kills, flatten times."""
        minute = minute_of_session(now_ns)
        if minute == self._last_minute:
            await self._kills()
            return
        self._last_minute = minute
        for b in self.books:
            for iid in self.monitored(b):
                st = self.states.get(iid)
                if st is not None:
                    for bar in st.on_time(now_ns):
                        await self._on_bar(st, bar)
        if self.index is not None:
            self.index.on_time(now_ns)
        if self._first_minute is None:
            self._first_minute = minute
        # On a late start, jobs whose time has passed wait for 2 minutes of data, then run once.
        warm = minute >= self._first_minute + 2
        due = [m for m in SELECT_AT if minute >= m and m not in self._done_select and minute < at(14, 0)
               and (warm or m >= self._first_minute + 2)]
        if due:
            self._done_select.update(due)
            self._select(minute)
        due = [m for m in DAYTYPE_AT if minute >= m and m not in self._done_daytype
               and (warm or m >= self._first_minute + 2)]
        if due:
            self._done_daytype.update(due)
            self._classify(minute)
        self._check_news(now_ns)
        await self._flatten_times(minute)
        await self._kills()
        if minute >= END_AT and not self.ended:
            self.ended = True

    async def _on_bar(self, st: SymbolState, bar: Bar) -> None:
        view = self.view(bar.start_min + 1)
        for b in self.books:
            await b.oms.on_bar(st, bar)
            if st.iid not in self.monitored(b) or not self.feed_ok:
                continue
            for strat in b.strategies:
                sig = strat.on_bar(st, bar, view)
                if sig is None:
                    continue
                status = b.oms.refresh_status(self.states)
                gate = "HIGH_VOL_EVENT day" if b.gated and self.day_type.label == "HIGH_VOL_EVENT" else ""
                if self._blackout.get(sig.iid, 0) > self.clock.now_ns():
                    gate = "news blackout (fresh filing, not yet assessed)"
                d = self.risk.evaluate(sig, st, status, now_ns=self.clock.now_ns(), minute=bar.start_min + 1,
                                       shortable=sig.iid in self.shortable, day=self.day, gate_reason=gate,
                                       banned=bool(self.dayref and sig.iid.symbol in self.dayref.ban),
                                       band=self.dayref.band(sig.iid) if self.dayref else None)
                self.journal.write(self.clock.now_ns(), b.name, "signal", {
                    "setup": sig.setup, "iid": str(sig.iid), "side": sig.side.value, "entry": sig.entry,
                    "stop": sig.stop, "targets": [(t.fraction, t.price) for t in sig.targets],
                    "reason": sig.reason, "approved": d.approved, "qty": d.qty, "rule": d.rule,
                    "detail": d.detail, "friction_r": round(d.friction_r, 4), "day_type": self.day_type.label})
                if not d.approved:
                    continue
                if status.reduced_trades_left > 0:
                    status.reduced_trades_left -= 1
                await b.oms.open(sig, d.qty, st, sector=self.sectors.get(sig.iid.symbol, ""))
                if b.name == "A":
                    self._say(f"[A] {sig.setup} {sig.iid.symbol} {sig.side.value} {d.qty} @ ~{sig.entry / 100:.2f} "
                              f"stop {sig.stop / 100:.2f} (risk ₹{d.risk_inr:,.0f}, friction {d.friction_r:.2f}R)")

    def _check_news(self, now_ns: int) -> None:
        """Fresh non-routine filing on a symbol → no new entries in it for `blackout_min` (design §3).
        Uses our first-seen time, so replay applies exactly the blackouts the live run had."""
        if self.news is None:
            return
        upto = now_ns - 5_000_000_000  # 5 s lag: rows are inserted just after first-seen; live == replay
        since = self._news_ns or upto - int(self.blackout_min * 60e9)
        if upto <= since:
            return
        for iid_s, seen_ns, key in self.news.material_candidates(since, upto):
            iid = InstrumentId.parse(iid_s)
            until = seen_ns + int(self.blackout_min * 60e9)
            if until > self._blackout.get(iid, 0):
                self._blackout[iid] = until
                self.journal.write(now_ns, "*", "news_blackout", {"iid": iid_s, "filing": key, "until_ns": until})
        self._news_ns = upto

    def _select(self, minute: int) -> None:
        min_rvol = 1.5 if minute >= at(9, 30) else None
        self.primary, self.watch = select(self.states, self.index, self.sectors, min_rvol=min_rvol)
        self.journal.write(self.clock.now_ns(), "*", "in_play", {
            "minute": minute, "primary": [(str(s.iid), s.score) for s in self.primary],
            "watch": [(str(s.iid), s.score) for s in self.watch]})
        if minute >= at(9, 30) and minute < at(9, 31):
            self._say("In play: " + ", ".join(f"{s.iid.symbol} ({s.score:.0f})" for s in self.primary))

    def _classify(self, minute: int) -> None:
        vix = self.states.get(self.vix_iid) if self.vix_iid else None
        self.day_type = classify(self.index, vix, self.states, minute)
        self.journal.write(self.clock.now_ns(), "*", "day_type", {
            "minute": minute, "label": self.day_type.label, "reasons": list(self.day_type.reasons),
            "inputs": self.day_type.inputs})

    async def _flatten_times(self, minute: int) -> None:
        c = self.risk.cfg
        for key, when, cas in (("cas", c.minute(c.flatten_cas), True), ("all", c.minute(c.flatten_other), False)):
            if minute < when or key in self._flattened:
                continue
            self._flattened.add(key)
            for b in self.books:
                states = {iid: st for iid, st in self.states.items()
                          if not cas or self._is_cas(iid)}
                await b.oms.flatten_all(states, f"flatten time {'CAS ' if cas else ''}{when}")

    def _is_cas(self, iid: InstrumentId) -> bool:
        inst = self.master.find(iid)
        return bool(inst and inst.cas_eligible)

    async def _kills(self) -> None:
        for b in self.books:
            status = b.oms.refresh_status(self.states)
            if status.locked:
                continue
            reason = self.risk.should_flatten(status)
            if reason:
                status.locked = True
                self.journal.write(self.clock.now_ns(), b.name, "kill", {"reason": reason})
                await b.oms.flatten_all(self.states, reason)
                self._say(f"[{b.name}] KILL: {reason}. Flattening and locking the day.")

    # ---- summary ------------------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"day": self.day.isoformat(), "day_type": self.day_type.label,
                               "in_play": [str(s.iid) for s in self.primary], "books": {}}
        for b in self.books:
            st = b.oms.refresh_status(self.states)
            closed = [t for t in b.oms.trades.values() if t.state == "CLOSED" and t.entry_qty]
            wins = [t for t in closed if t.net_pnl > 0]
            out["books"][b.name] = {
                "pnl": st.day_pnl / 100, "realized": st.realized / 100, "trades": len(closed),
                "wins": len(wins), "charges": sum(t.charges for t in closed) / 100,
                "avg_r": round(sum(t.r_multiple() for t in closed) / len(closed), 3) if closed else 0.0,
                "open": len(b.oms.open_trades()), "locked": st.locked,
            }
        return out


async def drain_all(engine: Engine) -> None:
    """Process anything the venues queued without a market event (e.g. at shutdown)."""
    for b in engine.books:
        await engine._drain(b)  # noqa: SLF001
    await asyncio.sleep(0)
