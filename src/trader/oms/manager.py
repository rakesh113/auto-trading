"""Order manager and position manager for one book (design §6 hard rules, §10 OMS).

Lifecycle of a trade::

    approve → ENTRY (marketable IOC limit) → fill(s) → STOP placed for the filled qty
            → OPEN: watch targets, trail, time stop, flatten times, gap-through-stop
            → to exit: cancel the stop, *wait for the cancel confirmation*, then send the
              exit for what is still open (and a new stop for any remainder)
            → CLOSED

Waiting for the cancel confirmation means a stop fill and an exit can never both
execute (no accidental short / oversell), on any broker. The gap without a stop is one
round trip (~150 ms). A position that has no working stop for longer than
`stop_attach_s` is flattened (naked-position invariant).

The manager is driven synchronously: `on_quote()` for prices and `on_exec()` for venue
events, both called by the engine in a fixed order, so replay reproduces live exactly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from trader.core.throttle import Priority
from trader.domain.instrument import InstrumentId
from trader.domain.orders import FillReport, OrderRequest, OrderState, OrderUpdate, StreamGap
from trader.domain.types import IST, OrderType, Product, Side, Validity, round_to_tick
from trader.market.state import Bar, SymbolState
from trader.oms.journal import Journal
from trader.ports.clock import Clock
from trader.ports.execution import Trader
from trader.risk.engine import BookStatus, OpenPosition
from trader.strategies.base import Signal

log = structlog.get_logger(__name__)

ENTRY_BAND = 0.0015  # marketable entry limit: up to 0.15% through the signal price
EXIT_BANDS = (0.0015, 0.003, 0.006, 0.01, 0.02)  # widening IOC exit limits
STOP_CUSHION = 0.004  # stop-limit price this far beyond the trigger


@dataclass
class Trade:
    id: str
    sig: Signal
    book: str
    qty_wanted: int
    sector: str = ""
    state: str = "PENDING_ENTRY"  # PENDING_ENTRY | OPEN | CLOSED
    entry_qty: int = 0
    entry_value: int = 0
    exit_qty: int = 0
    exit_value: int = 0
    charges: int = 0
    stop: int = 0
    stop_coid: str | None = None
    stop_live: bool = False  # accepted at the venue
    no_stop_since_ns: int = 0
    pending: tuple[str, int, str] | None = None  # (kind, qty, reason) waiting for stop cancel
    exit_coid: str | None = None
    exit_band_i: int = 0
    targets_done: int = 0
    opened_ns: int = 0
    closed_ns: int = 0
    exit_reason: str = ""

    @property
    def side(self) -> Side:
        return self.sig.side

    @property
    def open_qty(self) -> int:
        return self.entry_qty - self.exit_qty

    @property
    def avg_entry(self) -> float:
        return self.entry_value / self.entry_qty if self.entry_qty else 0.0

    @property
    def gross_pnl(self) -> int:
        s = self.side.sign
        return s * (self.exit_value - self.exit_qty * self.avg_entry) if self.exit_qty else 0

    @property
    def net_pnl(self) -> int:
        return round(self.gross_pnl) - self.charges

    def r_multiple(self) -> float:
        risk = self.sig.risk_per_share * self.entry_qty
        return self.net_pnl / risk if risk else 0.0


@dataclass
class OrderManager:
    book: str
    code: str  # one letter, part of every client order id
    trader: Trader
    clock: Clock
    journal: Journal
    tag_prefix: str
    status: BookStatus
    throttle: Callable[[Priority], Awaitable[None]] | None = None
    stop_attach_s: float = 5.0
    trades: dict[str, Trade] = field(default_factory=dict)
    _by_coid: dict[str, tuple[str, str]] = field(default_factory=dict)  # coid -> (trade id, role)
    _seq: int = 0
    on_closed: Callable[[Trade], None] | None = None

    # ---- ids & orders ---------------------------------------------------------------------

    def _coid(self) -> str:
        self._seq += 1
        d = datetime.fromtimestamp(self.clock.now_ns() / 1e9, IST)
        return f"{self.tag_prefix}{self.code}{d:%y%m%d}{self._seq:05d}"

    async def _send(self, t: Trade, role: str, side: Side, qty: int, *, price: int,
                    order_type: OrderType = OrderType.LIMIT, trigger: int | None = None,
                    validity: Validity = Validity.IOC, prio: Priority = Priority.ENTRY) -> str:
        coid = self._coid()
        self._by_coid[coid] = (t.id, role)
        req = OrderRequest(client_order_id=coid, iid=t.sig.iid, side=side, qty=qty, order_type=order_type,
                           price=price, trigger_price=trigger, product=Product.INTRADAY, validity=validity,
                           strategy=t.sig.setup, reason=role.upper())
        if self.throttle is not None:
            await self.throttle(prio)
        self.journal.write(self.clock.now_ns(), self.book, "order", {"trade": t.id, "role": role, "req": req})
        res = await self.trader.place(req)
        if not res.ok:
            self.journal.write(self.clock.now_ns(), self.book, "order_rejected",
                               {"trade": t.id, "role": role, "coid": coid, "error": res.error_code, "msg": res.message})
        return coid

    # ---- entry ----------------------------------------------------------------------------

    async def open(self, sig: Signal, qty: int, st: SymbolState, sector: str = "") -> Trade:
        tid = self._coid()
        t = Trade(id=tid, sig=sig, book=self.book, qty_wanted=qty, sector=sector, stop=sig.stop,
                  opened_ns=self.clock.now_ns())
        self.trades[tid] = t
        s = sig.side.sign
        ref = st.ask if s > 0 and st.ask else st.bid if s < 0 and st.bid else st.ltp
        limit = round_to_tick(round(ref * (1 + s * ENTRY_BAND)), st.tick, up=s > 0)
        await self._send(t, "entry", sig.side, qty, price=limit, prio=Priority.ENTRY)
        return t

    # ---- events from the venue --------------------------------------------------------------

    async def on_exec(self, ev: Any, states: dict[InstrumentId, SymbolState]) -> None:
        if isinstance(ev, StreamGap):
            self.journal.write(self.clock.now_ns(), self.book, "stream_gap", {"detail": ev.detail})
            return
        coid = ev.fill.client_order_id if isinstance(ev, FillReport) else ev.client_order_id
        ref = self._by_coid.get(coid)
        if ref is None:
            return
        t = self.trades[ref[0]]
        role = ref[1]
        if isinstance(ev, FillReport):
            f = ev.fill
            self.journal.write(self.clock.now_ns(), self.book, "fill", {"trade": t.id, "role": role, "fill": f})
            t.charges += f.charges
            if role == "entry":
                t.entry_qty += f.qty
                t.entry_value += f.qty * f.price
                t.state = "OPEN"
            else:
                t.exit_qty += f.qty
                t.exit_value += f.qty * f.price
                if role == "stop":
                    t.exit_reason = t.exit_reason or "stop"
            return
        assert isinstance(ev, OrderUpdate)
        st = states.get(t.sig.iid)
        if role == "stop":
            if ev.state in (OrderState.ACCEPTED, OrderState.TRIGGER_PENDING) and coid == t.stop_coid:
                t.stop_live = True
                t.no_stop_since_ns = 0
            elif ev.state.terminal and coid == t.stop_coid:
                t.stop_coid, t.stop_live = None, False
                if t.open_qty > 0:
                    t.no_stop_since_ns = t.no_stop_since_ns or self.clock.now_ns()
                if ev.state is OrderState.REJECTED:
                    await self._flatten(t, st, f"stop rejected: {ev.message}")
                    return
                if t.pending and t.open_qty > 0 and st is not None:
                    await self._run_pending(t, st)
        elif role == "entry" and ev.state.terminal:
            if t.entry_qty == 0:
                t.state = "CLOSED"
                t.exit_reason = f"entry not filled ({ev.state.value})"
                t.closed_ns = self.clock.now_ns()
                self.journal.write(self.clock.now_ns(), self.book, "entry_unfilled", {"trade": t.id})
                return
            if st is not None:
                await self._place_stop(t, st)
        elif role == "exit" and ev.state.terminal:
            t.exit_coid = None
            if t.open_qty > 0 and st is not None and t.pending is None:
                if t.state == "OPEN" and t.stop_coid is None and t.exit_reason.startswith("partial"):
                    await self._place_stop(t, st)
                else:
                    t.exit_band_i = min(t.exit_band_i + 1, len(EXIT_BANDS) - 1)
                    await self._exit_now(t, st, t.exit_reason or "exit retry")
        await self._maybe_closed(t, states)

    async def _place_stop(self, t: Trade, st: SymbolState) -> None:
        if t.open_qty <= 0 or t.stop_coid is not None:
            return
        s = t.side.sign
        limit = round_to_tick(round(t.stop * (1 - s * STOP_CUSHION)), st.tick, up=s < 0)
        t.stop_coid = await self._send(t, "stop", t.side.opposite, t.open_qty, price=limit, trigger=t.stop,
                                       order_type=OrderType.SL, validity=Validity.DAY, prio=Priority.STOP)
        t.no_stop_since_ns = t.no_stop_since_ns or self.clock.now_ns()

    async def _maybe_closed(self, t: Trade, states: dict[InstrumentId, SymbolState]) -> None:
        if t.state == "OPEN" and t.entry_qty > 0 and t.open_qty == 0 and t.exit_coid is None:
            t.state = "CLOSED"
            t.closed_ns = self.clock.now_ns()
            if t.stop_coid is not None:
                await self.trader.cancel(t.stop_coid)
            self.journal.write(self.clock.now_ns(), self.book, "trade_closed", {
                "trade": t.id, "setup": t.sig.setup, "iid": str(t.sig.iid), "side": t.side.value,
                "qty": t.entry_qty, "entry": t.avg_entry, "exit": t.exit_value / t.exit_qty if t.exit_qty else 0,
                "net": t.net_pnl, "charges": t.charges, "r": round(t.r_multiple(), 3), "reason": t.exit_reason})
            if self.on_closed:
                self.on_closed(t)

    # ---- exits ----------------------------------------------------------------------------

    async def request_exit(self, t: Trade, st: SymbolState, qty: int, reason: str) -> None:
        """Exit `qty` (or everything if qty ≥ open). Cancels the stop first, then acts."""
        if t.state != "OPEN" or t.pending is not None or t.exit_coid is not None:
            return
        kind = "full" if qty >= t.open_qty else "partial"
        t.pending = (kind, min(qty, t.open_qty), reason)
        self.journal.write(self.clock.now_ns(), self.book, "exit_requested",
                           {"trade": t.id, "kind": kind, "qty": t.pending[1], "reason": reason})
        if t.stop_coid is not None:
            await self.trader.cancel(t.stop_coid)  # → _run_pending on the CANCELLED update
        else:
            await self._run_pending(t, st)

    async def _run_pending(self, t: Trade, st: SymbolState) -> None:
        kind, qty, reason = t.pending  # type: ignore[misc]
        t.pending = None
        qty = min(qty, t.open_qty)
        if qty <= 0:
            return
        t.exit_reason = reason
        if kind == "partial":
            t.targets_done += 1
            await self._exit_order(t, st, qty)
            t.stop = round(t.avg_entry)  # after the first target the stop moves to breakeven
        else:
            await self._exit_now(t, st, reason)

    async def _exit_now(self, t: Trade, st: SymbolState, reason: str) -> None:
        t.exit_reason = reason
        if t.open_qty > 0:
            await self._exit_order(t, st, t.open_qty)

    async def _exit_order(self, t: Trade, st: SymbolState, qty: int) -> None:
        s = t.side.sign
        band = EXIT_BANDS[t.exit_band_i]
        ref = st.bid if s > 0 and st.bid else st.ask if s < 0 and st.ask else st.ltp
        limit = round_to_tick(round(ref * (1 - s * band)), st.tick, up=s < 0)
        t.exit_coid = await self._send(t, "exit", t.side.opposite, qty, price=limit, prio=Priority.EXIT)

    async def _flatten(self, t: Trade, st: SymbolState | None, reason: str) -> None:
        if st is None or t.state != "OPEN":
            return
        if t.exit_coid is None and t.pending is None:
            await self.request_exit(t, st, t.open_qty, reason)

    async def flatten_all(self, states: dict[InstrumentId, SymbolState], reason: str) -> None:
        for t in list(self.trades.values()):
            if t.state == "PENDING_ENTRY":
                continue
            await self._flatten(t, states.get(t.sig.iid), reason)

    # ---- per-quote / per-bar management ---------------------------------------------------

    async def on_quote(self, st: SymbolState) -> None:
        now = self.clock.now_ns()
        for t in list(self.trades.values()):
            if t.state != "OPEN" or t.sig.iid != st.iid or t.open_qty <= 0:
                continue
            s = t.side.sign
            # naked position: no working stop for too long → flatten
            if t.stop_coid is None and t.pending is None and t.exit_coid is None and t.no_stop_since_ns and \
                    now - t.no_stop_since_ns > self.stop_attach_s * 1e9:
                await self._place_stop(t, st)
            # gap through the stop-limit: the resting SL may never fill → exit actively
            if t.stop_live and (t.stop - st.ltp) * s > t.stop * STOP_CUSHION:
                await self.request_exit(t, st, t.open_qty, "gapped through stop")
                continue
            if t.targets_done < len(t.sig.targets) - 1:
                tgt = t.sig.targets[t.targets_done]
                if (st.ltp - tgt.price) * s >= 0:
                    await self.request_exit(t, st, max(1, round(t.entry_qty * tgt.fraction)),
                                            f"partial target {t.targets_done + 1}")
                    continue
            final = t.sig.targets[-1]
            if (st.ltp - final.price) * s >= 0:
                await self.request_exit(t, st, t.open_qty, "final target")

    async def on_bar(self, st: SymbolState, bar: Bar) -> None:
        for t in list(self.trades.values()):
            if t.state != "OPEN" or t.sig.iid != st.iid:
                continue
            s = t.side.sign
            held_min = (self.clock.now_ns() - t.opened_ns) / 60e9
            if t.targets_done == 0 and held_min >= t.sig.time_stop_min:
                await self.request_exit(t, st, t.open_qty, "time stop")
            elif t.targets_done > 0 and t.sig.trail == "vwap5" and bar.start_min % 5 == 4 and st.bars5:
                b5 = st.bars5[-1]
                if (b5.close - b5.vwap) * s < 0:
                    await self.request_exit(t, st, t.open_qty, "trail: 5-min close through VWAP")

    # ---- status for risk ------------------------------------------------------------------

    def refresh_status(self, states: dict[InstrumentId, SymbolState]) -> BookStatus:
        b = self.status
        realized = unreal = 0
        positions = []
        for t in self.trades.values():
            if t.entry_qty == 0:
                continue
            if t.state == "CLOSED":
                realized += t.net_pnl
                continue
            st = states.get(t.sig.iid)
            ltp = st.ltp if st else round(t.avg_entry)
            realized += round(t.gross_pnl) - t.charges
            unreal += round((ltp - t.avg_entry) * t.open_qty * t.side.sign)
            positions.append(OpenPosition(t.sig.iid, t.side, t.open_qty, round(t.avg_entry), t.stop, ltp,
                                          t.sector))
        b.realized, b.unrealized, b.positions = realized, unreal, positions
        b.equity_module_loss = max(0, -(realized + unreal))
        b.peak_pnl = max(b.peak_pnl, b.day_pnl)
        return b

    def open_trades(self) -> list[Trade]:
        return [t for t in self.trades.values() if t.state != "CLOSED"]
