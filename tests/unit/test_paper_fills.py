"""Paper fill-model behaviour specific to the simulator (design §12)."""

from __future__ import annotations

from trader.adapters.paper.trader import PaperTrader
from trader.domain.instrument import InstrumentId
from trader.domain.market import DepthLevel, Quote
from trader.domain.orders import OrderAmend, OrderRequest, OrderState
from trader.domain.types import FeedMode, OrderType, Side, Validity

REL = InstrumentId.parse("NSE:EQ:RELIANCE")
OPT = InstrumentId.parse("NSE:OPT:NIFTY:2026-12-29:27000:CE")


def quote(clock, bids, asks, ltp=None, volume=None, iid=REL) -> Quote:
    return Quote(iid=iid, native="x", mode=FeedMode.FULL_D30, ts_exch_ms=0, ts_server_ms=0,
                 ts_recv_ns=clock.now_ns(), ltp=ltp or (bids[0][0] if bids else 0),
                 bids=tuple(DepthLevel(p, q) for p, q in bids), asks=tuple(DepthLevel(p, q) for p, q in asks),
                 volume=volume, ltq=1)


def make(clock, master, tier="conservative") -> PaperTrader:
    return PaperTrader(clock, master=master, settings={"fill_tier": tier})


async def _place(t: PaperTrader, clock, **kw) -> str:
    base = {"client_order_id": f"AT{clock.now_ns()}", "iid": REL, "side": Side.BUY, "qty": 100, "price": 140050}
    base.update(kw)
    await t.place(OrderRequest(**base))
    clock.advance(5)
    t.process()
    return base["client_order_id"]


async def test_marketable_walks_depth_with_participation_cap(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 50)], [(140010, 50), (140020, 50), (140100, 1000)]))
    c = await _place(t, clock, qty=100, price=140050)
    snap = await t.snapshot()
    o = next(o for o in snap.orders if o.coid == c)
    # 70% of 50 at each of the two levels inside the limit = 35 + 35
    assert o.filled_qty == 70 and o.state is OrderState.PARTIAL
    assert [f.price for f in snap.fills] == [140010, 140020]


async def test_liquidity_ledger_prevents_double_consumption(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 50)], [(140010, 100)]))
    a = await _place(t, clock, qty=70, price=140010)
    b = await _place(t, clock, qty=70, price=140010)
    snap = await t.snapshot()
    filled = {o.coid: o.filled_qty for o in snap.orders}
    assert filled[a] + filled[b] == 70


async def test_passive_needs_trade_through_when_conservative(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(139990, 100)], [(140010, 100)], ltp=140000, volume=1000))
    c = await _place(t, clock, qty=10, price=139990)
    t.on_market(quote(clock, [(139980, 100)], [(140000, 100)], ltp=139990, volume=1100))  # touch only
    assert (await t.snapshot()).orders[0].filled_qty == 0
    t.on_market(quote(clock, [(139970, 100)], [(139990, 100)], ltp=139980, volume=1200))  # through
    o = next(o for o in (await t.snapshot()).orders if o.coid == c)
    assert o.state is OrderState.FILLED and (await t.snapshot()).fills[0].price == 139990


async def test_optimistic_fills_on_touch(clock, master) -> None:
    t = make(clock, master, tier="optimistic")
    t.on_market(quote(clock, [(139990, 100)], [(140010, 100)], ltp=140000, volume=1000))
    await _place(t, clock, qty=10, price=139990)
    t.on_market(quote(clock, [(139980, 100)], [(140000, 100)], ltp=139990, volume=1100))
    assert (await t.snapshot()).orders[0].state is OrderState.FILLED


async def test_stop_limit_gapped_through_stays_open(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 100)], [(140010, 100)]))
    c = await _place(t, clock, side=Side.SELL, qty=10, order_type=OrderType.SL, trigger_price=139500,
                     price=139400)
    assert (await t.snapshot()).orders[0].state is OrderState.TRIGGER_PENDING
    t.on_market(quote(clock, [(138000, 100)], [(138010, 100)], ltp=138000))  # gap below the limit
    o = next(o for o in (await t.snapshot()).orders if o.coid == c)
    assert o.state is OrderState.ACCEPTED and o.filled_qty == 0  # triggered, but limit not reachable


async def test_sl_m_rejected_on_options_like_upstox(clock, master) -> None:
    t = make(clock, master)
    await _place(t, clock, iid=OPT, qty=65, order_type=OrderType.SL_M, trigger_price=10000, price=None)
    assert (await t.snapshot()).orders[0].state is OrderState.REJECTED


async def test_ioc_remainder_cancelled(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 10)], [(140010, 10)]))
    c = await _place(t, clock, qty=100, price=140010, validity=Validity.IOC)
    o = next(o for o in (await t.snapshot()).orders if o.coid == c)
    assert o.state is OrderState.CANCELLED and o.filled_qty == 7


async def test_fill_can_beat_cancel_latency(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(139990, 100)], [(140010, 100)], ltp=140000, volume=1000))
    c = await _place(t, clock, qty=10, price=139990)
    await t.cancel(c)  # takes effect only after simulated latency
    t.on_market(quote(clock, [(139970, 100)], [(139990, 100)], ltp=139980, volume=1500))
    clock.advance(5)
    t.process()
    o = next(o for o in (await t.snapshot()).orders if o.coid == c)
    assert o.state is OrderState.FILLED


async def test_charges_and_cash(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 1000)], [(140010, 1000)]))
    await _place(t, clock, qty=100, price=140010)
    snap = await t.snapshot()
    f = snap.fills[0]
    assert f.charges > 3000  # ₹30 brokerage + GST + statutory on a ₹1.4L buy
    assert snap.funds.used_margin == round(100 * 140010 * 0.2)


async def test_amend_qty_below_filled_rejected(clock, master) -> None:
    t = make(clock, master)
    t.on_market(quote(clock, [(140000, 10)], [(140010, 10)]))
    c = await _place(t, clock, qty=100, price=140010)
    res = await t.modify(c, OrderAmend(qty=5))
    assert not res.ok
