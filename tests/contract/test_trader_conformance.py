"""Adapter conformance suite (design D9): every Trader must pass the same tests.

To add a venue, write a Harness for it below and add it to HARNESSES. A harness
wraps the trader plus whatever is needed to make the "exchange" act: a quote for
the paper trader, a fake broker behind a mocked HTTP layer for Upstox.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import httpx
import pytest

from trader.adapters.paper.trader import PaperTrader
from trader.adapters.upstox.http import UpstoxHttp
from trader.adapters.upstox.trader import UpstoxTrader
from trader.domain.instrument import InstrumentId
from trader.domain.market import DepthLevel, Quote
from trader.domain.orders import FillReport, OrderAmend, OrderRequest, OrderState, OrderUpdate
from trader.domain.types import FeedMode, Side
from trader.ports.execution import Trader

RELIANCE = InstrumentId.parse("NSE:EQ:RELIANCE")
_seq = itertools.count(1)


def coid() -> str:
    return f"AT{next(_seq):010d}"


def req(**kw: Any) -> OrderRequest:
    base: dict[str, Any] = {"client_order_id": coid(), "iid": RELIANCE, "side": Side.BUY, "qty": 10,
                            "price": 139000}
    base.update(kw)
    return OrderRequest(**base)


class Harness:
    trader: Trader

    async def settle(self) -> None:
        """Let the venue process everything pending."""

    async def make_fill(self, client_order_id: str, qty: int, price: int) -> None:
        """Cause the venue to fill `qty` of an open order at `price`."""
        raise NotImplementedError

    async def state(self, client_order_id: str) -> OrderState:
        await self.settle()
        snap = await self.trader.snapshot()
        return next(o.state for o in snap.orders if o.coid == client_order_id)

    def drain(self) -> list[Any]:
        out = []
        q = self.trader._events  # noqa: SLF001 - test access
        while not q.empty():
            out.append(q.get_nowait())
        return out


class PaperHarness(Harness):
    def __init__(self, clock, master) -> None:
        self.clock = clock
        self.trader = PaperTrader(clock, master=master, settings={"fill_tier": "conservative"})
        self._quote(140000, 140010)

    def _quote(self, bid: int, ask: int, qty: int = 1000) -> None:
        self.trader.on_market(Quote(iid=RELIANCE, native="NSE_EQ|INE002A01018", mode=FeedMode.FULL, ts_exch_ms=0,
                                    ts_server_ms=0, ts_recv_ns=self.clock.now_ns(), ltp=(bid + ask) // 2,
                                    bids=(DepthLevel(bid, qty),), asks=(DepthLevel(ask, qty),)))

    async def settle(self) -> None:
        self.clock.advance(5)
        self.trader.process()

    async def make_fill(self, client_order_id: str, qty: int, price: int) -> None:
        await self.settle()
        self._quote(price - 10, price, qty=int(qty / 0.7) + 1)  # an ask at the limit with enough size


class FakeUpstox:
    """Just enough of the Upstox order API to exercise the adapter."""

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self._ids = itertools.count(1)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if path == "/v3/order/place":
            b = json.loads(request.content)
            if b["quantity"] <= 0:
                return httpx.Response(400, json={"status": "error", "errors": [
                    {"errorCode": "UDAPI1000", "message": "bad qty"}]})
            oid = f"2610{next(self._ids):08d}"
            self.orders[oid] = {**b, "order_id": oid, "status": "open", "filled_quantity": 0, "average_price": 0}
            return httpx.Response(200, json={"status": "success", "data": {"order_ids": [oid]},
                                             "metadata": {"latency": 12}})
        if path == "/v3/order/modify":
            b = json.loads(request.content)
            o = self.orders[b["order_id"]]
            o.update({k: b[k] for k in ("quantity", "price", "trigger_price", "order_type")})
            return httpx.Response(200, json={"status": "success", "data": {"order_id": o["order_id"]}})
        if path == "/v3/order/cancel":
            o = self.orders[request.url.params["order_id"]]
            o["status"] = "cancelled"
            return httpx.Response(200, json={"status": "success", "data": {"order_id": o["order_id"]}})
        if path == "/v2/order/retrieve-all":
            manual = {"order_id": "999", "tag": None, "status": "open", "quantity": 1, "filled_quantity": 0,
                      "instrument_token": "NSE_EQ|INE002A01018", "transaction_type": "BUY", "order_type": "LIMIT",
                      "price": 1.0, "product": "D", "validity": "DAY"}
            return httpx.Response(200, json={"status": "success", "data": [*self.orders.values(), manual]})
        if path == "/v2/user/get-funds-and-margin":
            return httpx.Response(200, json={"status": "success", "data": {"equity": {
                "available_margin": 1000000.0, "used_margin": 0.0}}})
        return httpx.Response(404, json={"status": "error", "errors": [{"errorCode": "404", "message": path}]})


class UpstoxHarness(Harness):
    def __init__(self, clock, master) -> None:
        self.fake = FakeUpstox()
        http = UpstoxHttp("token", transport=httpx.MockTransport(self.fake.handler), rest_per_sec=1e6)
        self.trader = UpstoxTrader(clock, http=http, master=master, tag_prefix="AT",
                                   settings={"order_stream": False}, allow_live=True)

    async def settle(self) -> None:
        await self.trader.reconcile()

    async def make_fill(self, client_order_id: str, qty: int, price: int) -> None:
        o = next(o for o in self.fake.orders.values() if o["tag"] == client_order_id)
        prev_q, prev_avg = o["filled_quantity"], o["average_price"]
        o["filled_quantity"] = prev_q + qty
        o["average_price"] = (prev_q * prev_avg + qty * price / 100) / o["filled_quantity"]
        o["status"] = "complete" if o["filled_quantity"] == o["quantity"] else "open"


HARNESSES = {"paper": PaperHarness, "upstox": UpstoxHarness}


@pytest.fixture(params=sorted(HARNESSES))
def h(request, clock, master) -> Harness:
    return HARNESSES[request.param](clock, master)


async def test_place_is_acknowledged_then_working(h: Harness) -> None:
    r = req()
    res = await h.trader.place(r)
    assert res.ok and res.broker_order_id
    assert await h.state(r.client_order_id) is OrderState.ACCEPTED


async def test_place_is_idempotent(h: Harness) -> None:
    r = req()
    a = await h.trader.place(r)
    b = await h.trader.place(r)
    assert a.broker_order_id == b.broker_order_id
    snap = await h.trader.snapshot()
    assert sum(1 for o in snap.orders if o.coid == r.client_order_id) == 1


async def test_invalid_order_rejected_without_exception(h: Harness) -> None:
    res = await h.trader.place(req(price=None))
    assert not res.ok and res.state is OrderState.REJECTED


async def test_cancel(h: Harness) -> None:
    r = req()
    await h.trader.place(r)
    await h.settle()
    res = await h.trader.cancel(r.client_order_id)
    assert res.ok
    assert await h.state(r.client_order_id) is OrderState.CANCELLED
    again = await h.trader.cancel(r.client_order_id)
    assert not again.ok


async def test_cancel_unknown(h: Harness) -> None:
    assert not (await h.trader.cancel("AT_NOPE")).ok


async def test_modify_price(h: Harness) -> None:
    r = req()
    await h.trader.place(r)
    await h.settle()
    assert (await h.trader.modify(r.client_order_id, OrderAmend(price=139500))).ok
    await h.settle()
    snap = await h.trader.snapshot()
    assert next(o for o in snap.orders if o.coid == r.client_order_id).price == 139500


async def test_fill_emits_events_and_position(h: Harness) -> None:
    r = req(price=139000)  # resting: not marketable against the opening quote
    await h.trader.place(r)
    await h.settle()
    assert await h.state(r.client_order_id) is OrderState.ACCEPTED
    h.drain()
    await h.make_fill(r.client_order_id, 10, 139000)
    assert await h.state(r.client_order_id) is OrderState.FILLED
    evs = h.drain()
    fills = [e.fill for e in evs if isinstance(e, FillReport)]
    assert sum(f.qty for f in fills) == 10 and all(f.price == 139000 for f in fills)
    assert any(isinstance(e, OrderUpdate) and e.state is OrderState.FILLED for e in evs)
    snap = await h.trader.snapshot()
    pos = next(p for p in snap.positions if p.iid == RELIANCE)
    assert pos.qty == 10


async def test_snapshot_only_contains_own_orders(h: Harness) -> None:
    await h.trader.place(req())
    await h.settle()
    snap = await h.trader.snapshot()
    assert snap.orders and all(o.coid.startswith("AT") for o in snap.orders)
