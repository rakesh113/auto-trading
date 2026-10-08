"""Core enums and money helpers shared by every module.

Prices are int64 **paise** everywhere in the hot path (design §10). Convert at the
edges only: adapters turn broker floats into paise, reports turn paise into rupees.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

IST = timezone(timedelta(hours=5, minutes=30), "IST")

Paise = int


def to_paise(rupees: float | Decimal | str) -> Paise:
    """Rupees → paise, rounding half-up (floats like 2512.35 are not exact in binary)."""
    return int((Decimal(str(rupees)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_rupees(paise: Paise) -> Decimal:
    return Decimal(paise) / 100


def round_to_tick(price: Paise, tick: Paise, *, up: bool) -> Paise:
    """Snap a price onto the tick grid, rounding away from the trade's favour by choice of `up`."""
    if tick <= 0:
        return price
    q, r = divmod(price, tick)
    if r == 0:
        return price
    return (q + 1) * tick if up else q * tick


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"


class InstrumentKind(StrEnum):
    EQ = "EQ"
    IDX = "IDX"
    FUT = "FUT"
    OPT = "OPT"


class OptionRight(StrEnum):
    CE = "CE"
    PE = "PE"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"  # allowed by the port, but hard rules send marketable LIMITs only (design §6)
    SL = "SL"  # stop-limit: trigger_price + limit price
    SL_M = "SL-M"  # stop-market: blocked on options by brokers


class Product(StrEnum):
    INTRADAY = "INTRADAY"  # MIS / Upstox "I"
    DELIVERY = "DELIVERY"  # CNC / NRML / Upstox "D"


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class FeedMode(StrEnum):
    """Subscription depth. Ordered from cheapest to richest."""

    LTPC = "ltpc"
    OPTION_GREEKS = "option_greeks"
    FULL = "full"  # 5-level depth
    FULL_D30 = "full_d30"  # 30-level depth (Upstox Plus)
