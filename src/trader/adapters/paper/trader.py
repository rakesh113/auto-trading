"""PaperTrader: a drop-in Trader that fills against the live (or replayed) book (design D6, §12).

Fill model by tier (decide go-live on `conservative` only):

=============  =============  ===========================  ==========
tier           participation  passive limit fills when      latency
=============  =============  ===========================  ==========
optimistic     100% of level  last trade touches the limit  0
base           85%            last trade touches the limit  lognormal
conservative   70%            last trade goes *through* it  lognormal
=============  =============  ===========================  ==========

* Marketable orders walk the displayed depth seen *after* the simulated latency, taking
  at most `participation` of each level. A liquidity ledger stops two orders consuming
  the same displayed size within one snapshot.
* Stops trigger on LTP. A stop-limit whose limit is gapped through stays resting,
  exactly like the real exchange (design §7.2).
* Cancels and amends take effect after latency too, so a fill can beat a cancel.
* Broker quirks emulated for `emulate: upstox`: SL-M rejected on options; MARKET
  converted to a protected limit (market price protection).

Market data arrives through `on_market()`; the app wires the feed to it.
"""

from __future__ import annotations

import asyncio
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from trader.core.config import REPO_ROOT
from trader.core.costs import CostModel, category
from trader.core.registry import traders
from trader.domain.instrument import InstrumentId
from trader.domain.market import MarketEvent, Quote
from trader.domain.orders import (
    Fill,
    FillReport,
    Order,
    OrderAmend,
    OrderRequest,
    OrderState,
    OrderUpdate,
    SubmitResult,
)
from trader.domain.portfolio import BrokerSnapshot, Funds, Position
from trader.domain.types import (
    InstrumentKind,
    OrderType,
    Paise,
    Product,
    Side,
    Validity,
    round_to_tick,
    to_paise,
)
from trader.ports.clock import Clock, today_ist
from trader.ports.execution import Trader, TraderCaps
from trader.ports.marketdata import InstrumentMaster

if TYPE_CHECKING:
    from trader.core.app import AppContext

FillTier = Literal["optimistic", "base", "conservative"]


class PaperSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emulate: str = "upstox"
    cost_profile: str = "upstox_plus"
    fill_tier: FillTier = "conservative"
    starting_capital_inr: float = 1_000_000
    latency_median_ms: float = 150.0
    latency_p95_ms: float = 450.0
    market_protection_pct: float = 1.0  # MARKET → limit at LTP ± this
    intraday_margin_pct: float = 20.0  # equity MIS; derivatives use the same until SPAN is modelled
    seed: int = 7
    poll_ms: int = 50  # how often pending cancels/amends/activations are processed in wall mode


_TIER = {
    "optimistic": (1.0, False),  # (participation, require trade-through)
    "base": (0.85, False),
    "conservative": (0.70, True),
}


@dataclass(slots=True)
class _Book:
    quote: Quote | None = None
    consumed: dict[tuple[Side, Paise], int] = field(default_factory=dict)  # this snapshot only
    last_volume: int | None = None


@dataclass(slots=True)
class _Action:
    at_ns: int
    kind: Literal["activate", "cancel", "amend"]
    coid: str
    amend: OrderAmend | None = None


@traders.register("paper")
class PaperTrader(Trader):
    caps = TraderCaps(
        live=False,
        order_types=frozenset({OrderType.LIMIT, OrderType.SL, OrderType.SL_M, OrderType.MARKET}),
        exchanges=frozenset({"NSE", "BSE", "MCX"}),
    )

    def __init__(
        self,
        clock: Clock,
        *,
        settings: dict | PaperSettings | None = None,
        master: InstrumentMaster | None = None,
        costs: CostModel | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings if isinstance(settings, PaperSettings) else PaperSettings(**(settings or {}))
        self.clock = clock
        self.master = master
        self.costs = costs or CostModel.load(REPO_ROOT / "config" / "costs.yaml", self.settings.cost_profile)
        self._participation, self._need_through = _TIER[self.settings.fill_tier]
        self._rng = random.Random(self.settings.seed)
        self._orders: dict[str, Order] = {}
        self._active: set[str] = set()  # coids that are live at the simulated exchange
        self._actions: list[_Action] = []
        self._books: dict[InstrumentId, _Book] = defaultdict(_Book)
        self._fills: list[Fill] = []
        self._positions: dict[tuple[InstrumentId, Product], Position] = {}
        self._brokerage_charged: dict[str, float] = defaultdict(float)
        self._turnover: dict[str, float] = defaultdict(float)
        self._cash: float = to_paise(self.settings.starting_capital_inr)
        self._trade_seq = 0
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def build(cls, ctx: AppContext, settings: dict[str, Any]) -> PaperTrader:
        s = PaperSettings(**settings)
        return cls(ctx.clock, settings=s, master=ctx.master,
                   costs=CostModel.load(ctx.config_dir / "costs.yaml", s.cost_profile))

    # ---- lifecycle -------------------------------------------------------------------------

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._poll(), name="paper-poll")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self.settings.poll_ms / 1000)
            self.process()

    # ---- Trader API ------------------------------------------------------------------------

    async def place(self, req: OrderRequest) -> SubmitResult:
        if req.client_order_id in self._orders:  # idempotent replay
            o = self._orders[req.client_order_id]
            return SubmitResult(ok=True, client_order_id=o.coid, broker_order_id=o.broker_order_id, state=o.state)
        now = self.clock.now_ns()
        try:
            order = Order.new(req, now)
        except ValueError as e:
            return SubmitResult(ok=False, client_order_id=req.client_order_id, state=OrderState.REJECTED,
                                error_code="VALIDATION", message=str(e))
        order.broker_order_id = f"P{len(self._orders) + 1:08d}"
        order.transition(OrderState.SUBMITTED, now)
        self._orders[order.coid] = order
        self._schedule("activate", order.coid)
        self.process()
        return SubmitResult(ok=True, client_order_id=order.coid, broker_order_id=order.broker_order_id,
                            state=OrderState.SUBMITTED, latency_ms=0.0)

    async def modify(self, client_order_id: str, amend: OrderAmend) -> SubmitResult:
        o = self._orders.get(client_order_id)
        if o is None or o.state.terminal:
            return SubmitResult(ok=False, client_order_id=client_order_id, error_code="NOT_OPEN",
                                message="order not open", state=o.state if o else OrderState.REJECTED)
        if amend.qty is not None and amend.qty <= o.filled_qty:
            return SubmitResult(ok=False, client_order_id=client_order_id, error_code="BAD_QTY",
                                message="qty must exceed filled qty", state=o.state)
        self._schedule("amend", client_order_id, amend)
        self.process()
        return SubmitResult(ok=True, client_order_id=client_order_id, broker_order_id=o.broker_order_id,
                            state=o.state)

    async def cancel(self, client_order_id: str) -> SubmitResult:
        o = self._orders.get(client_order_id)
        if o is None or o.state.terminal:
            return SubmitResult(ok=False, client_order_id=client_order_id, error_code="NOT_OPEN",
                                message="order not open", state=o.state if o else OrderState.REJECTED)
        self._schedule("cancel", client_order_id)
        self.process()
        return SubmitResult(ok=True, client_order_id=client_order_id, broker_order_id=o.broker_order_id,
                            state=o.state)

    async def snapshot(self) -> BrokerSnapshot:
        used = sum(self._margin(p.iid, p.product, abs(p.qty), round(p.avg_price)) for p in self._positions.values())
        return BrokerSnapshot(
            ts_ns=self.clock.now_ns(),
            orders=[Order(**{f: getattr(o, f) for f in o.__struct_fields__}) for o in self._orders.values()],
            fills=list(self._fills),
            positions=[Position(**{f: getattr(p, f) for f in p.__struct_fields__}) for p in self._positions.values()],
            funds=Funds(available=round(self._cash) - used, used_margin=used),
        )

    # ---- market data -----------------------------------------------------------------------

    def on_market(self, ev: MarketEvent) -> None:
        if not isinstance(ev, Quote) or ev.iid is None:
            return
        book = self._books[ev.iid]
        prev_vol = book.last_volume
        book.quote = ev
        book.consumed.clear()  # a new snapshot shows fresh displayed size
        vol_delta: int | None = None
        if ev.volume is not None:
            if prev_vol is not None and ev.volume > prev_vol:
                vol_delta = ev.volume - prev_vol
            book.last_volume = ev.volume
            traded = vol_delta is not None
        else:
            traded = ev.ltq > 0  # ltpc mode: no volume field, any print counts
        self.process()
        for coid in sorted(self._active):
            o = self._orders[coid]
            if o.request.iid == ev.iid:
                self._match(o, book, trade_print=traded, vol_delta=vol_delta)

    # ---- internals -------------------------------------------------------------------------

    def _latency_ns(self) -> int:
        if self.settings.fill_tier == "optimistic":
            return 0
        m = self.settings.latency_median_ms
        sigma = math.log(max(self.settings.latency_p95_ms, m * 1.0001) / m) / 1.645
        return int(self._rng.lognormvariate(math.log(m), sigma) * 1e6)

    def _schedule(self, kind: Literal["activate", "cancel", "amend"], coid: str, amend: OrderAmend | None = None) -> None:
        self._actions.append(_Action(self.clock.now_ns() + self._latency_ns(), kind, coid, amend))

    def process(self) -> None:
        """Apply every scheduled action whose time has come, in time order."""
        now = self.clock.now_ns()
        due = sorted((a for a in self._actions if a.at_ns <= now), key=lambda a: a.at_ns)
        if not due:
            return
        self._actions = [a for a in self._actions if a.at_ns > now]
        for a in due:
            o = self._orders[a.coid]
            if o.state.terminal:
                continue
            if a.kind == "activate":
                self._activate(o)
            elif a.kind == "cancel":
                self._active.discard(o.coid)
                self._update(o, OrderState.CANCELLED, "cancelled by user")
            elif a.kind == "amend" and a.amend is not None:
                self._apply_amend(o, a.amend)

    def _update(self, o: Order, state: OrderState, msg: str = "") -> None:
        o.transition(state, self.clock.now_ns())
        if state is OrderState.REJECTED:
            o.reject_reason = msg
        self._emit(OrderUpdate(
            client_order_id=o.coid, broker_order_id=o.broker_order_id, state=o.state, ts_ns=o.updated_ns,
            filled_qty=o.filled_qty, avg_price=o.avg_price, qty=o.qty, price=o.price,
            trigger_price=o.trigger_price, message=msg,
        ))

    def _tick(self, iid: InstrumentId) -> Paise:
        inst = self.master.find(iid) if self.master else None
        return inst.tick_size if inst else 5

    def _multiplier(self, iid: InstrumentId) -> float:
        inst = self.master.find(iid) if self.master else None
        return float(inst.qty_multiplier) if inst else 1.0

    def _margin(self, iid: InstrumentId, product: Product, qty: int, price: Paise) -> int:
        notional = qty * price * self._multiplier(iid)
        if product is Product.DELIVERY and iid.kind is InstrumentKind.EQ:
            return round(notional)
        return round(notional * self.settings.intraday_margin_pct / 100)

    def _activate(self, o: Order) -> None:
        req = o.request
        quote = self._books[req.iid].quote
        if self.settings.emulate == "upstox" and req.order_type is OrderType.SL_M and req.iid.kind is InstrumentKind.OPT:
            self._update(o, OrderState.REJECTED, "SL-M not allowed on options (UDAPI100500)")
            return
        if req.order_type is OrderType.MARKET:
            if quote is None or quote.ltp <= 0:
                self._update(o, OrderState.REJECTED, "no market price for MARKET order")
                return
            band = quote.ltp * self.settings.market_protection_pct / 100
            raw = quote.ltp + band if req.side is Side.BUY else quote.ltp - band
            o.price = round_to_tick(round(raw), self._tick(req.iid), up=req.side is Side.SELL)
        ref_price = o.price or o.trigger_price or (quote.ltp if quote else 0)
        if not self._reduces_position(req) and ref_price:
            need = self._margin(req.iid, req.product, req.qty, ref_price)
            snapshot_used = sum(
                self._margin(p.iid, p.product, abs(p.qty), round(p.avg_price)) for p in self._positions.values()
            )
            if need > self._cash - snapshot_used:
                self._update(o, OrderState.REJECTED, f"insufficient margin: need {need / 100:.0f}")
                return
        self._active.add(o.coid)
        if req.order_type in (OrderType.SL, OrderType.SL_M):
            self._update(o, OrderState.TRIGGER_PENDING)
        else:
            self._update(o, OrderState.ACCEPTED)
        self._match(o, self._books[req.iid], trade_print=False, vol_delta=None, on_arrival=True)

    def _reduces_position(self, req: OrderRequest) -> bool:
        p = self._positions.get((req.iid, req.product))
        return p is not None and p.qty * req.side.sign < 0 and abs(p.qty) >= req.qty

    def _apply_amend(self, o: Order, a: OrderAmend) -> None:
        if a.qty is not None:
            if a.qty <= o.filled_qty:
                self._emit(OrderUpdate(client_order_id=o.coid, broker_order_id=o.broker_order_id, state=o.state,
                                       ts_ns=self.clock.now_ns(), filled_qty=o.filled_qty, message="amend rejected"))
                return
            o.qty = a.qty
        if a.price is not None:
            o.price = a.price
        if a.trigger_price is not None:
            o.trigger_price = a.trigger_price
        self._update(o, o.state, "amended")
        self._match(o, self._books[o.request.iid], trade_print=False, vol_delta=None, on_arrival=True)

    def _match(self, o: Order, book: _Book, *, trade_print: bool, vol_delta: int | None,
               on_arrival: bool = False) -> None:
        q = book.quote
        if q is None or o.coid not in self._active or o.state.terminal:
            self._finish_ioc(o)
            return
        req = o.request
        if o.state is OrderState.TRIGGER_PENDING:
            trig = o.trigger_price or 0
            hit = q.ltp >= trig if req.side is Side.BUY else q.ltp <= trig
            if not hit:
                return
            if req.order_type is OrderType.SL_M:
                band = q.ltp * self.settings.market_protection_pct / 100
                raw = q.ltp + band if req.side is Side.BUY else q.ltp - band
                o.price = round_to_tick(round(raw), self._tick(req.iid), up=req.side is Side.SELL)
            self._update(o, OrderState.ACCEPTED, "triggered")
            on_arrival = True
        limit = o.price
        assert limit is not None
        levels = q.asks if req.side is Side.BUY else q.bids
        crosses = (lambda px: px <= limit) if req.side is Side.BUY else (lambda px: px >= limit)
        if levels and crosses(levels[0].price):
            for lvl in levels:
                if o.remaining <= 0 or not crosses(lvl.price):
                    break
                key = (req.side, lvl.price)
                avail = int(lvl.qty * self._participation) - book.consumed.get(key, 0)
                take = min(o.remaining, max(avail, 0))
                if take > 0:
                    book.consumed[key] = book.consumed.get(key, 0) + take
                    self._fill(o, take, lvl.price)
        elif not levels and on_arrival and crosses(q.ltp):
            # No depth in this mode (ltpc): assume one tick of slippage past LTP, capped at the limit.
            tick = self._tick(req.iid)
            px = min(q.ltp + tick, limit) if req.side is Side.BUY else max(q.ltp - tick, limit)
            self._fill(o, o.remaining, px)
        elif trade_print and not on_arrival:
            through = q.ltp < limit if req.side is Side.BUY else q.ltp > limit
            touch = q.ltp == limit
            if through or (touch and not self._need_through):
                take = o.remaining if vol_delta is None else min(o.remaining, int(vol_delta * self._participation))
                if take > 0:
                    self._fill(o, take, limit)
        self._finish_ioc(o)

    def _finish_ioc(self, o: Order) -> None:
        if o.request.validity is Validity.IOC and o.coid in self._active and not o.state.terminal:
            self._active.discard(o.coid)
            self._update(o, OrderState.CANCELLED, "IOC remainder cancelled")

    def _fill(self, o: Order, qty: int, price: Paise) -> None:
        req = o.request
        now = self.clock.now_ns()
        mult = self._multiplier(req.iid)
        day = today_ist(self.clock)
        stat = self.costs.statutory(req.iid, req.side, qty, price, req.product, day, mult)
        cat = category(req.iid, req.product)
        self._turnover[o.coid] += qty * price * mult
        brokerage_total = self.costs.brokerage(cat, self._turnover[o.coid])
        brokerage = brokerage_total - self._brokerage_charged[o.coid]
        self._brokerage_charged[o.coid] = brokerage_total
        charges = stat.total + round(brokerage * (1 + self.costs.gst_rate(day) / 100))
        self._trade_seq += 1
        fill = Fill(client_order_id=o.coid, trade_id=f"PT{self._trade_seq:09d}", iid=req.iid, side=req.side,
                    qty=qty, price=price, ts_ns=now, charges=charges)
        o.apply_fill(qty, price, now)
        pos = self._positions.setdefault((req.iid, req.product), Position(iid=req.iid, product=req.product))
        before = pos.realized
        pos.apply(fill, mult)
        self._cash += (pos.realized - before) - charges
        self._fills.append(fill)
        if o.state is OrderState.FILLED:
            self._active.discard(o.coid)
        self._emit(FillReport(fill=fill))
        self._emit(OrderUpdate(client_order_id=o.coid, broker_order_id=o.broker_order_id, state=o.state, ts_ns=now,
                               filled_qty=o.filled_qty, avg_price=o.avg_price, qty=o.qty, price=o.price))

    def end_of_day(self) -> None:
        """Expire every DAY order still working (the exchange does this at close)."""
        for coid in sorted(self._active):
            self._active.discard(coid)
            self._update(self._orders[coid], OrderState.EXPIRED, "end of day")
