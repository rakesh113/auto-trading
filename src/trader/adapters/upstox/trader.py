"""UpstoxTrader: live execution on Upstox (design §13). Not used during paper.

* Orders go to the HFT host (`/v3/order/place|modify|cancel`).
* `client_order_id` travels in the broker `tag`. Only orders whose tag starts with
  our prefix are tracked, reconciled or risk-managed (design D13); everything else in
  the account is ignored.
* No automatic resend on timeout: the order is reported UNKNOWN and found again by
  tag during reconciliation.
* Order progress arrives on the portfolio-stream websocket, with an order-book poll as
  a backstop. Both paths go through `_ingest`, which de-duplicates.
* Fills are derived from changes in `filled_quantity`/`average_price` and later
  replaced by trade-book records during reconciliation.

Construction requires `allow_live=True`, which only `build_app` passes, and only after
the live guard in `trader.core.app` has passed.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog
import websockets
from pydantic import BaseModel, ConfigDict

from trader.adapters.upstox.http import UpstoxError, UpstoxHttp, UpstoxTimeout
from trader.core.config import secret
from trader.core.registry import traders
from trader.domain.instrument import InstrumentId
from trader.domain.orders import (
    Fill,
    FillReport,
    Order,
    OrderAmend,
    OrderRequest,
    OrderState,
    OrderUpdate,
    StreamGap,
    SubmitResult,
)
from trader.domain.portfolio import BrokerSnapshot, Funds, Position
from trader.domain.types import OrderType, Product, Side, Validity, to_paise, to_rupees
from trader.ports.clock import Clock
from trader.ports.execution import Trader, TraderCaps
from trader.ports.marketdata import InstrumentMaster

if TYPE_CHECKING:
    from trader.core.app import AppContext

log = structlog.get_logger(__name__)

_PRODUCT ={Product.INTRADAY: "I", Product.DELIVERY: "D"}
_PRODUCT_BACK = {v: k for k, v in _PRODUCT.items()}
_STATUS: dict[str, OrderState] = {
    "put order req received": OrderState.SUBMITTED,
    "validation pending": OrderState.SUBMITTED,
    "open pending": OrderState.SUBMITTED,
    "after market order req received": OrderState.SUBMITTED,
    "open": OrderState.ACCEPTED,
    "trigger pending": OrderState.TRIGGER_PENDING,
    "modify validation pending": OrderState.PENDING_AMEND,
    "modify pending": OrderState.PENDING_AMEND,
    "modified": OrderState.ACCEPTED,
    "not modified": OrderState.ACCEPTED,
    "cancel pending": OrderState.PENDING_CANCEL,
    "not cancelled": OrderState.ACCEPTED,
    "complete": OrderState.FILLED,
    "rejected": OrderState.REJECTED,
    "cancelled": OrderState.CANCELLED,
}


def map_status(status: str, filled: int, qty: int) -> OrderState:
    st = _STATUS.get(status.strip().lower(), OrderState.UNKNOWN)
    if st in (OrderState.ACCEPTED, OrderState.PENDING_AMEND) and 0 < filled < qty:
        return OrderState.PARTIAL
    return st


class UpstoxTraderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_hft_host: bool = True
    order_stream: bool = True
    reconcile_interval_s: float = 5.0


@traders.register("upstox")
class UpstoxTrader(Trader):
    caps = TraderCaps(
        live=True,
        order_types=frozenset({OrderType.LIMIT, OrderType.SL, OrderType.SL_M, OrderType.MARKET}),
        exchanges=frozenset({"NSE", "BSE", "MCX"}),
        sl_m_on_options=False,
        gtt_protects_position=False,
        max_tag_len=20,
    )

    def __init__(
        self,
        clock: Clock,
        *,
        http: UpstoxHttp,
        master: InstrumentMaster,
        tag_prefix: str,
        settings: dict | UpstoxTraderSettings | None = None,
        allow_live: bool = False,
    ) -> None:
        if not allow_live:
            raise PermissionError("UpstoxTrader places real orders; build it through build_app's live guard")
        super().__init__()
        self.clock = clock
        self.http = http
        self.master = master
        self.prefix = tag_prefix
        self.settings = settings if isinstance(settings, UpstoxTraderSettings) else UpstoxTraderSettings(
            **(settings or {}))
        self._orders: dict[str, Order] = {}  # coid -> order
        self._by_broker: dict[str, str] = {}  # broker order id -> coid
        self._fills: list[Fill] = []
        self._tasks: list[asyncio.Task[None]] = []

    @classmethod
    def build(cls, ctx: AppContext, settings: dict[str, Any]) -> UpstoxTrader:
        u = ctx.cfg.upstox
        http = UpstoxHttp(secret(u.access_token_env), api_base=u.api_base, hft_base=u.hft_base,
                          timeout_s=u.timeout_s, rest_per_sec=u.rest_per_sec)
        return cls(ctx.clock, http=http, master=ctx.master, tag_prefix=ctx.cfg.system.tag_prefix,
                   settings=UpstoxTraderSettings(**settings), allow_live=ctx.live_armed)

    # ---- lifecycle -------------------------------------------------------------------------

    async def start(self) -> None:
        if self.settings.order_stream:
            self._tasks.append(asyncio.create_task(self._stream(), name="upstox-order-stream"))
        self._tasks.append(asyncio.create_task(self._poll(), name="upstox-order-poll"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # ---- Trader API ------------------------------------------------------------------------

    def _body(self, req: OrderRequest) -> dict[str, Any]:
        return {
            "quantity": req.qty,
            "product": _PRODUCT[req.product],
            "validity": req.validity.value,
            "price": float(to_rupees(req.price)) if req.price else 0,
            "tag": req.client_order_id,
            "instrument_token": self.master.to_native(req.iid),
            "order_type": req.order_type.value,
            "transaction_type": req.side.value,
            "disclosed_quantity": 0,
            "trigger_price": float(to_rupees(req.trigger_price)) if req.trigger_price else 0,
            "is_amo": False,
            "slice": False,  # we slice ourselves behind the throttle (design §4)
        }

    async def place(self, req: OrderRequest) -> SubmitResult:
        coid = req.client_order_id
        if coid in self._orders:
            o = self._orders[coid]
            return SubmitResult(ok=True, client_order_id=coid, broker_order_id=o.broker_order_id, state=o.state)
        if not coid.startswith(self.prefix) or len(coid) > self.caps.max_tag_len:
            return SubmitResult(ok=False, client_order_id=coid, state=OrderState.REJECTED, error_code="BAD_COID",
                                message=f"client_order_id must start with {self.prefix} and be ≤ 20 chars")
        now = self.clock.now_ns()
        try:
            order = Order.new(req, now)
        except ValueError as e:
            return SubmitResult(ok=False, client_order_id=coid, state=OrderState.REJECTED,
                                error_code="VALIDATION", message=str(e))
        self._orders[coid] = order
        order.transition(OrderState.SUBMITTED, now)
        try:
            body = await self.http.send("POST", "/v3/order/place", json=self._body(req),
                                        hft=self.settings.use_hft_host)
        except UpstoxTimeout as e:
            order.transition(OrderState.UNKNOWN, self.clock.now_ns())
            return SubmitResult(ok=False, client_order_id=coid, state=OrderState.UNKNOWN, error_code="TIMEOUT",
                                message=str(e))
        except UpstoxError as e:
            order.reject_reason = e.message
            order.transition(OrderState.REJECTED, self.clock.now_ns())
            return SubmitResult(ok=False, client_order_id=coid, state=OrderState.REJECTED, error_code=e.code,
                                message=e.message)
        ids = (body.get("data") or {}).get("order_ids") or []
        if ids:
            order.broker_order_id = ids[0]
            self._by_broker[ids[0]] = coid
        latency = (body.get("metadata") or {}).get("latency")
        return SubmitResult(ok=True, client_order_id=coid, broker_order_id=order.broker_order_id,
                            state=OrderState.SUBMITTED, latency_ms=latency)

    async def modify(self, client_order_id: str, amend: OrderAmend) -> SubmitResult:
        o = self._orders.get(client_order_id)
        if o is None or o.broker_order_id is None or o.state.terminal:
            return SubmitResult(ok=False, client_order_id=client_order_id, error_code="NOT_OPEN",
                                message="order not open", state=o.state if o else OrderState.REJECTED)
        otype = amend.order_type or o.request.order_type
        price = amend.price if amend.price is not None else o.price
        trig = amend.trigger_price if amend.trigger_price is not None else o.trigger_price
        body = {
            "order_id": o.broker_order_id,
            "quantity": amend.qty if amend.qty is not None else o.qty,
            "validity": o.request.validity.value,
            "price": float(to_rupees(price)) if price else 0,
            "order_type": otype.value,
            "trigger_price": float(to_rupees(trig)) if trig else 0,
            "disclosed_quantity": 0,
        }
        return await self._mutate("PUT", "/v3/order/modify", o, json_body=body)

    async def cancel(self, client_order_id: str) -> SubmitResult:
        o = self._orders.get(client_order_id)
        if o is None or o.broker_order_id is None or o.state.terminal:
            return SubmitResult(ok=False, client_order_id=client_order_id, error_code="NOT_OPEN",
                                message="order not open", state=o.state if o else OrderState.REJECTED)
        return await self._mutate("DELETE", "/v3/order/cancel", o, params={"order_id": o.broker_order_id})

    async def _mutate(self, method: str, path: str, o: Order, *, json_body: Any = None,
                      params: dict[str, Any] | None = None) -> SubmitResult:
        try:
            body = await self.http.send(method, path, json=json_body, params=params, hft=self.settings.use_hft_host)
        except UpstoxTimeout as e:
            return SubmitResult(ok=False, client_order_id=o.coid, broker_order_id=o.broker_order_id,
                                state=o.state, error_code="TIMEOUT", message=str(e))
        except UpstoxError as e:
            return SubmitResult(ok=False, client_order_id=o.coid, broker_order_id=o.broker_order_id,
                                state=o.state, error_code=e.code, message=e.message)
        latency = (body.get("metadata") or {}).get("latency") if isinstance(body, dict) else None
        return SubmitResult(ok=True, client_order_id=o.coid, broker_order_id=o.broker_order_id, state=o.state,
                            latency_ms=latency)

    async def snapshot(self) -> BrokerSnapshot:
        await self.reconcile()
        positions: dict[tuple[InstrumentId, Product], Position] = {}
        for f in self._fills:
            prod = self._orders[f.client_order_id].request.product
            inst = self.master.find(f.iid)
            mult = float(inst.qty_multiplier) if inst else 1.0
            positions.setdefault((f.iid, prod), Position(iid=f.iid, product=prod)).apply(f, mult)
        funds = await self._funds()
        return BrokerSnapshot(ts_ns=self.clock.now_ns(), orders=list(self._orders.values()), fills=list(self._fills),
                              positions=list(positions.values()), funds=funds)

    async def _funds(self) -> Funds:
        body = await self.http.get("/v2/user/get-funds-and-margin", params={"segment": "SEC"})
        eq = (body.get("data") or {}).get("equity") or {}
        return Funds(available=to_paise(eq.get("available_margin", 0)), used_margin=to_paise(eq.get("used_margin", 0)),
                     payin=to_paise(eq.get("payin_amount", 0)))

    # ---- order progress ----------------------------------------------------------------------

    def _ingest(self, row: dict[str, Any]) -> None:
        """Apply one broker order record (from the stream or the order book)."""
        tag = row.get("tag") or ""
        if not tag.startswith(self.prefix):
            return  # not ours: manual trade or another system (design D13)
        boid = str(row.get("order_id") or "")
        coid = self._by_broker.get(boid) or tag
        o = self._orders.get(coid)
        now = self.clock.now_ns()
        if o is None:
            o = self._adopt(row, coid, now)
            if o is None:
                return
        if boid and o.broker_order_id is None:
            o.broker_order_id = boid
            self._by_broker[boid] = coid
        qty = int(row.get("quantity") or o.qty)
        filled = int(row.get("filled_quantity") or 0)
        avg = float(row.get("average_price") or 0)
        new_state = map_status(str(row.get("status") or ""), filled, qty)
        o.qty = max(qty, o.filled_qty)
        if row.get("price") is not None:
            o.price = to_paise(row["price"]) or o.price
        if row.get("trigger_price"):
            o.trigger_price = to_paise(row["trigger_price"])
        if filled > o.filled_qty:
            delta = filled - o.filled_qty
            prev_value = o.filled_value
            total_value = round(to_paise(avg) * filled)
            px = round((total_value - prev_value) / delta) if total_value > prev_value else to_paise(avg)
            o.filled_qty += delta
            o.filled_value += delta * px
            fill = Fill(client_order_id=coid, trade_id=f"{boid}:{o.filled_qty}", iid=o.request.iid,
                        side=o.request.side, qty=delta, price=px, ts_ns=now)
            self._fills.append(fill)
            self._emit(FillReport(fill=fill))
        if new_state is OrderState.UNKNOWN or (new_state is o.state and filled == o.filled_qty and not row.get("_force")):
            if new_state is OrderState.UNKNOWN:
                log.warning("upstox.unknown_status", status=row.get("status"), coid=coid)
            return
        try:
            o.transition(new_state, now)
        except Exception:  # noqa: BLE001 - venue order of events can differ; log and take the venue's word
            log.warning("upstox.unexpected_transition", coid=coid, frm=o.state, to=new_state)
            o.state = new_state
        if new_state is OrderState.REJECTED:
            o.reject_reason = str(row.get("status_message") or "")
        self._emit(OrderUpdate(client_order_id=coid, broker_order_id=o.broker_order_id, state=o.state, ts_ns=now,
                               filled_qty=o.filled_qty, avg_price=o.avg_price, qty=o.qty, price=o.price,
                               trigger_price=o.trigger_price, message=str(row.get("status_message") or "")))

    def _adopt(self, row: dict[str, Any], coid: str, now: int) -> Order | None:
        """A tagged order we have no record of (e.g. after a restart): rebuild it."""
        iid = self.master.from_native(str(row.get("instrument_token") or row.get("instrument_key") or ""))
        if iid is None:
            log.error("upstox.adopt_unmapped", coid=coid, token=row.get("instrument_token"))
            return None
        price = to_paise(row.get("price") or 0) or None
        trig = to_paise(row.get("trigger_price") or 0) or None
        req = OrderRequest(client_order_id=coid, iid=iid, side=Side(str(row["transaction_type"]).upper()),
                           qty=int(row["quantity"]), order_type=OrderType(str(row["order_type"]).upper()),
                           price=price, trigger_price=trig,
                           product=_PRODUCT_BACK.get(str(row.get("product")), Product.INTRADAY),
                           validity=Validity(str(row.get("validity") or "DAY").upper()), reason="ADOPTED")
        o = Order(request=req, state=OrderState.UNKNOWN, qty=req.qty, price=price, trigger_price=trig,
                  created_ns=now, updated_ns=now)
        self._orders[coid] = o
        log.warning("upstox.adopted_order", coid=coid)
        return o

    async def reconcile(self) -> None:
        body = await self.http.get("/v2/order/retrieve-all")
        rows = body.get("data") or []
        seen = set()
        for row in rows:
            self._ingest(row)
            seen.add(row.get("tag"))
        for coid, o in self._orders.items():
            if o.state is OrderState.UNKNOWN and coid not in seen and self.clock.now_ns() - o.updated_ns > 10e9:
                # Not at the broker 10 s after an ambiguous send: it never arrived.
                o.transition(OrderState.REJECTED, self.clock.now_ns())
                o.reject_reason = "not found at broker after timeout"
                self._emit(OrderUpdate(client_order_id=coid, broker_order_id=None, state=o.state,
                                       ts_ns=o.updated_ns, message=o.reject_reason))

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self.settings.reconcile_interval_s)
            try:
                await self.reconcile()
            except Exception as e:  # noqa: BLE001
                log.warning("upstox.reconcile_failed", error=repr(e))

    async def _stream(self) -> None:
        backoff = 1.0
        while True:
            try:
                body = await self.http.get("/v2/feed/portfolio-stream-feed/authorize",
                                           params={"update_types": "order"})
                data = body.get("data") or {}
                uri = data.get("authorized_redirect_uri") or data["authorizedRedirectUri"]
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                    backoff = 1.0
                    await self.reconcile()  # close any gap before trusting the stream
                    async for msg in ws:
                        try:
                            row = json.loads(msg)
                        except ValueError:
                            continue
                        if row.get("update_type", "order") == "order":
                            self._ingest(row)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("upstox.order_stream_down", error=repr(e))
                self._emit(StreamGap(ts_ns=self.clock.now_ns(), detail=repr(e)))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
