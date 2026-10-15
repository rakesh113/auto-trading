"""Order manager lifecycle against the PaperTrader, and engine determinism."""

from __future__ import annotations

from tests.engine_helpers import DAY, Tape, ctx, ts
from trader.adapters.paper.trader import PaperTrader
from trader.core.clock import SimClock
from trader.core.config import CONFIG_DIR
from trader.core.costs import CostModel
from trader.domain.instrument import InstrumentId
from trader.domain.orders import OrderState
from trader.domain.types import Side
from trader.engine.session import Book, Engine
from trader.market.state import SymbolState
from trader.oms.journal import Journal
from trader.oms.manager import OrderManager
from trader.risk.engine import BookStatus, RiskConfig, RiskEngine
from trader.strategies.base import Signal, Target
from trader.strategies.e1_orb import E1OrbRetest
from trader.strategies.e2_vwap import E2VwapReclaim

STOCK = "NSE:EQ:RELIANCE"
IID = InstrumentId.parse(STOCK)


class Rig:
    def __init__(self, master) -> None:
        self.clock = SimClock(ts(10, 0))
        self.trader = PaperTrader(self.clock, master=master, settings={"fill_tier": "base", "latency_median_ms": 100,
                                                                       "latency_p95_ms": 200})
        self.journal = Journal(None)
        self.oms = OrderManager(book="A", code="A", trader=self.trader, clock=self.clock, journal=self.journal,
                                tag_prefix="AT", status=BookStatus(equity=100_000_000, hwm=100_000_000))
        self.st = SymbolState(IID, ctx(STOCK, pdc=140000, atr=2800), tick=10)
        self.tape = Tape(STOCK, spread=10, depth_qty=100_000)
        self.states = {IID: self.st}

    async def px(self, price: int, dt: float = 1.0) -> None:
        self.clock.advance(dt)
        q = self.tape.quote(self.clock.now_ns(), price, 100)
        self.st.on_quote(q)
        self.trader.on_market(q)
        for _ in range(3):  # cancels/acks may cascade into new orders
            for e in self.trader.drain_events():
                await self.oms.on_exec(e, self.states)
            self.clock.advance(0.5)
            self.trader.process()
        await self.oms.on_quote(self.st)

    def sig(self, entry=140000, stop=139300, t2r=3.0) -> Signal:
        r = entry - stop
        return Signal("E2_VWAP_RECLAIM", IID, Side.BUY, entry, stop,
                      (Target(0.5, entry + r), Target(0.5, entry + round(t2r * r))), trail=None)

    def orders(self):
        return {o.coid: o for o in self.trader._orders.values()}  # noqa: SLF001


async def test_target_then_breakeven_then_final(master) -> None:
    r = Rig(master)
    await r.px(140000)
    t = await r.oms.open(r.sig(), 100, r.st)
    await r.px(140000)
    assert t.state == "OPEN" and t.entry_qty == 100
    stop = r.orders()[t.stop_coid]
    assert stop.state is OrderState.TRIGGER_PENDING and stop.qty == 100 and stop.trigger_price == 139300
    await r.px(140720)  # +1R → partial
    await r.px(140720)
    assert t.targets_done == 1 and t.open_qty == 50
    new_stop = r.orders()[t.stop_coid]
    assert new_stop.qty == 50 and new_stop.trigger_price == round(t.avg_entry)  # breakeven
    await r.px(142200)  # +3R → final
    await r.px(142200)
    assert t.state == "CLOSED" and t.net_pnl > 0 and t.exit_reason == "final target"
    sells = sum(o.filled_qty for o in r.orders().values() if o.request.side is Side.SELL)
    assert sells == 100  # never oversold


async def test_stop_hit_closes_with_loss(master) -> None:
    r = Rig(master)
    await r.px(140000)
    t = await r.oms.open(r.sig(), 100, r.st)
    await r.px(140000)
    await r.px(139250)  # through the trigger, inside the stop-limit cushion
    await r.px(139250)
    assert t.state == "CLOSED" and t.net_pnl < 0 and t.exit_reason == "stop"
    assert r.oms.status.positions == [] or r.oms.refresh_status(r.states).positions == []


async def test_gap_through_stop_exits_actively(master) -> None:
    r = Rig(master)
    await r.px(140000)
    t = await r.oms.open(r.sig(), 100, r.st)
    await r.px(140000)
    await r.px(137000)  # gaps far below the stop-limit price
    for _ in range(4):
        await r.px(137000)
    assert t.state == "CLOSED" and t.exit_reason in ("gapped through stop", "stop")
    sells = sum(o.filled_qty for o in r.orders().values() if o.request.side is Side.SELL)
    assert sells == 100


async def test_flatten_all(master) -> None:
    r = Rig(master)
    await r.px(140000)
    t = await r.oms.open(r.sig(), 100, r.st)
    await r.px(140000)
    await r.oms.flatten_all(r.states, "flatten time")
    await r.px(140010)
    await r.px(140010)
    assert t.state == "CLOSED" and t.exit_reason == "flatten time"


# ---- engine determinism ------------------------------------------------------------------------


def _engine(master, clock) -> Engine:
    costs = CostModel.load(CONFIG_DIR / "costs.yaml", "upstox_plus")
    risk = RiskEngine(RiskConfig.load(CONFIG_DIR / "risk.yaml"), costs)
    journal = Journal(None)
    books = []
    for name, gated in (("A", True), ("B", False)):
        tr = PaperTrader(clock, master=master, costs=costs)
        oms = OrderManager(book=name, code=name, trader=tr, clock=clock, journal=journal, tag_prefix="AT",
                           status=BookStatus(equity=100_000_000, hwm=100_000_000))
        books.append(Book(name, name, gated, tr, oms, [E1OrbRetest(), E2VwapReclaim()]))
    return Engine(clock=clock, day=DAY, master=master, contexts={STOCK: ctx(STOCK, pdc=100000, atr=2000,
                                                                              vol_per_min=1000)},
                  sectors={}, shortable=frozenset({IID}), risk=risk, journal=journal, books=books,
                  index_iid=InstrumentId.parse("NSE:IDX:NIFTY50"))


async def _run(master) -> tuple[str, dict]:
    clock = SimClock(ts(9, 0))
    eng = _engine(master, clock)
    tape = Tape(STOCK, depth_qty=50_000)
    prices = ([100000, 100400, 100800, 100300, 100500] * 3 + [100700, 100850, 100900, 100950, 101000]
              + [100900, 100850, 101050, 101400, 101800, 102200, 102600, 103000, 103400] + [103400] * 60)
    for i, p in enumerate(prices):
        for s in (5, 25, 45):
            t = ts(9, 15) + int((i * 60 + s) * 1e9)
            clock.set(t)
            await eng.on_event(tape.quote(t, p, 3000))
    clock.set(ts(15, 30))
    await eng.on_time(ts(15, 30))
    return eng.journal.digest(), eng.summary()


async def test_engine_is_deterministic(master) -> None:
    d1, s1 = await _run(master)
    d2, s2 = await _run(master)
    assert d1 == d2 and s1 == s2
    assert s1["books"]["A"]["trades"] >= 1 and s1["books"]["A"]["pnl"] > 0  # the scenario must actually trade
