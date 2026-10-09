"""Orders, fills and the normalized order state machine (design §10).

`OrderRequest` is what a strategy/OMS asks for (broker-agnostic, idempotent on
`client_order_id`). `Order` is the OMS-owned record whose `state` only moves along
the edges in `_ALLOWED`. Every trader adapter reports progress as `ExecEvent`s.
"""

from __future__ import annotations

from enum import StrEnum

import msgspec

from trader.domain.instrument import InstrumentId
from trader.domain.types import OrderType, Paise, Product, Side, Validity


class OrderState(StrEnum):
    PENDING_NEW = "PENDING_NEW"  # written to our log, not yet sent
    SUBMITTED = "SUBMITTED"  # sent; venue has not confirmed
    ACCEPTED = "ACCEPTED"  # resting at the exchange
    TRIGGER_PENDING = "TRIGGER_PENDING"  # stop order waiting for its trigger
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    PENDING_AMEND = "PENDING_AMEND"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"  # timeout/ambiguity: never resend, reconcile by tag

    @property
    def terminal(self) -> bool:
        return self in _TERMINAL

    @property
    def working(self) -> bool:
        """Could still trade at the exchange."""
        return not self.terminal and self is not OrderState.PENDING_NEW


S = OrderState
_TERMINAL = frozenset({S.FILLED, S.CANCELLED, S.REJECTED, S.EXPIRED})
_LIVE = {S.ACCEPTED, S.TRIGGER_PENDING, S.PARTIAL, S.FILLED, S.CANCELLED, S.EXPIRED, S.REJECTED, S.UNKNOWN}
_ALLOWED: dict[OrderState, frozenset[OrderState]] = {
    S.PENDING_NEW: frozenset({S.SUBMITTED, S.REJECTED, S.UNKNOWN}),
    S.SUBMITTED: frozenset(_LIVE),
    S.ACCEPTED: frozenset(_LIVE | {S.PENDING_CANCEL, S.PENDING_AMEND}),
    S.TRIGGER_PENDING: frozenset(_LIVE | {S.PENDING_CANCEL, S.PENDING_AMEND}),
    S.PARTIAL: frozenset(_LIVE - {S.REJECTED} | {S.PENDING_CANCEL, S.PENDING_AMEND}),
    S.PENDING_CANCEL: frozenset(_LIVE),
    S.PENDING_AMEND: frozenset(_LIVE | {S.PENDING_CANCEL}),
    S.UNKNOWN: frozenset(_LIVE | {S.PENDING_CANCEL}),
    S.FILLED: frozenset(),
    S.CANCELLED: frozenset(),
    S.REJECTED: frozenset(),
    S.EXPIRED: frozenset(),
}


class IllegalTransition(Exception):
    pass


class OrderRequest(msgspec.Struct, frozen=True, kw_only=True):
    client_order_id: str
    iid: InstrumentId
    side: Side
    qty: int
    order_type: OrderType = OrderType.LIMIT
    price: Paise | None = None  # limit price; required for LIMIT and SL
    trigger_price: Paise | None = None  # required for SL and SL-M
    product: Product = Product.INTRADAY
    validity: Validity = Validity.DAY
    strategy: str = ""
    reason: str = ""  # ENTRY | STOP | EXIT | FLATTEN — also the throttle priority

    def validate(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.order_type in (OrderType.LIMIT, OrderType.SL) and (self.price is None or self.price <= 0):
            raise ValueError(f"{self.order_type} needs a positive price")
        if self.order_type in (OrderType.SL, OrderType.SL_M) and (
            self.trigger_price is None or self.trigger_price <= 0
        ):
            raise ValueError(f"{self.order_type} needs a trigger_price")


class OrderAmend(msgspec.Struct, frozen=True, kw_only=True):
    qty: int | None = None
    price: Paise | None = None
    trigger_price: Paise | None = None
    order_type: OrderType | None = None


class Fill(msgspec.Struct, frozen=True, kw_only=True):
    client_order_id: str
    trade_id: str
    iid: InstrumentId
    side: Side
    qty: int
    price: Paise
    ts_ns: int
    charges: Paise = 0  # estimated until reconciled with the contract note


class Order(msgspec.Struct, kw_only=True):
    request: OrderRequest
    state: OrderState = OrderState.PENDING_NEW
    broker_order_id: str | None = None
    qty: int = 0  # current (possibly amended) quantity
    price: Paise | None = None
    trigger_price: Paise | None = None
    filled_qty: int = 0
    filled_value: int = 0  # Σ qty × price in paise, so the average never drifts
    reject_reason: str = ""
    created_ns: int = 0
    updated_ns: int = 0

    @classmethod
    def new(cls, req: OrderRequest, ts_ns: int) -> Order:
        req.validate()
        return cls(
            request=req,
            qty=req.qty,
            price=req.price,
            trigger_price=req.trigger_price,
            created_ns=ts_ns,
            updated_ns=ts_ns,
        )

    @property
    def coid(self) -> str:
        return self.request.client_order_id

    @property
    def remaining(self) -> int:
        return self.qty - self.filled_qty

    @property
    def avg_price(self) -> float | None:
        return self.filled_value / self.filled_qty if self.filled_qty else None

    def transition(self, to: OrderState, ts_ns: int) -> None:
        if to is self.state and to in (S.PARTIAL, S.UNKNOWN, S.ACCEPTED, S.TRIGGER_PENDING):
            self.updated_ns = ts_ns
            return
        if to not in _ALLOWED[self.state]:
            raise IllegalTransition(f"{self.coid}: {self.state} -> {to}")
        if to is S.FILLED and self.filled_qty != self.qty:
            raise IllegalTransition(f"{self.coid}: FILLED with {self.filled_qty}/{self.qty}; apply fills first")
        if to is S.PARTIAL and not 0 < self.filled_qty < self.qty:
            raise IllegalTransition(f"{self.coid}: PARTIAL with {self.filled_qty}/{self.qty}")
        self.state = to
        self.updated_ns = ts_ns

    def apply_fill(self, qty: int, price: Paise, ts_ns: int) -> None:
        if qty <= 0:
            raise ValueError("fill qty must be positive")
        if self.filled_qty + qty > self.qty:
            raise ValueError(f"{self.coid}: overfill {self.filled_qty}+{qty} > {self.qty}")
        self.filled_qty += qty
        self.filled_value += qty * price
        self.transition(S.FILLED if self.filled_qty == self.qty else S.PARTIAL, ts_ns)


# ---- execution events emitted by trader adapters -------------------------------------------


class OrderUpdate(msgspec.Struct, frozen=True, kw_only=True, tag=True):
    client_order_id: str
    broker_order_id: str | None
    state: OrderState
    ts_ns: int
    filled_qty: int = 0
    avg_price: float | None = None
    qty: int | None = None
    price: Paise | None = None
    trigger_price: Paise | None = None
    message: str = ""


class FillReport(msgspec.Struct, frozen=True, kw_only=True, tag=True):
    fill: Fill


class StreamGap(msgspec.Struct, frozen=True, kw_only=True, tag=True):
    """The execution stream dropped; the OMS must reconcile from a snapshot."""

    ts_ns: int
    detail: str = ""


ExecEvent = OrderUpdate | FillReport | StreamGap


class SubmitResult(msgspec.Struct, frozen=True, kw_only=True):
    ok: bool
    client_order_id: str
    broker_order_id: str | None = None
    state: OrderState = OrderState.SUBMITTED
    error_code: str = ""
    message: str = ""
    latency_ms: float | None = None
