"""Positions, funds and the point-in-time view a trader adapter reports."""

from __future__ import annotations

import msgspec

from trader.domain.instrument import InstrumentId
from trader.domain.orders import Fill, Order
from trader.domain.types import Paise, Product


class Position(msgspec.Struct, kw_only=True):
    iid: InstrumentId
    product: Product
    qty: int = 0  # signed: + long, − short
    avg_price: float = 0.0  # paise, average of the open quantity
    realized: Paise = 0  # gross of charges
    charges: Paise = 0
    buy_qty: int = 0
    sell_qty: int = 0

    def apply(self, fill: Fill, multiplier: float = 1.0) -> None:
        """Average-cost accounting. `multiplier` is the contract's qty multiplier (MCX)."""
        signed = fill.qty * fill.side.sign
        if fill.side.sign > 0:
            self.buy_qty += fill.qty
        else:
            self.sell_qty += fill.qty
        self.charges += fill.charges
        if self.qty == 0 or (self.qty > 0) == (signed > 0):
            new_qty = self.qty + signed
            self.avg_price = (self.avg_price * abs(self.qty) + fill.price * fill.qty) / abs(new_qty)
            self.qty = new_qty
            return
        closing = min(abs(signed), abs(self.qty))
        direction = 1 if self.qty > 0 else -1
        self.realized += round((fill.price - self.avg_price) * closing * direction * multiplier)
        self.qty += signed
        if self.qty == 0:
            self.avg_price = 0.0
        elif (self.qty > 0) != (direction > 0):  # flipped through zero
            self.avg_price = float(fill.price)

    def unrealized(self, ltp: Paise, multiplier: float = 1.0) -> Paise:
        return round((ltp - self.avg_price) * self.qty * multiplier) if self.qty else 0


class Funds(msgspec.Struct, kw_only=True):
    available: Paise
    used_margin: Paise = 0
    payin: Paise = 0


class BrokerSnapshot(msgspec.Struct, kw_only=True):
    """Everything a trader knows right now, restricted to this system's own orders."""

    ts_ns: int
    orders: list[Order]
    fills: list[Fill]
    positions: list[Position]
    funds: Funds
