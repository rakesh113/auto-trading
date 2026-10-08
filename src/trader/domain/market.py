"""Normalized market-data events emitted by every MarketDataFeed adapter.

msgspec Structs: cheap to build in the hot path and cheap to serialize for the journal.
"""

from __future__ import annotations

import msgspec

from trader.domain.instrument import InstrumentId
from trader.domain.types import FeedMode, Paise


class DepthLevel(msgspec.Struct, array_like=True, frozen=True):
    price: Paise
    qty: int


class Bar(msgspec.Struct, frozen=True):
    interval: str  # "I1" (1-minute) or "1d" as the venue names it
    ts_ms: int  # bar start, epoch ms
    open: Paise
    high: Paise
    low: Paise
    close: Paise
    volume: int


class Greeks(msgspec.Struct, frozen=True):
    delta: float
    theta: float
    gamma: float
    vega: float
    rho: float


class Quote(msgspec.Struct, kw_only=True):
    """One conflated snapshot for one instrument. Optional fields depend on the mode."""

    iid: InstrumentId | None  # None if the native key is not in today's master
    native: str
    mode: FeedMode
    ts_exch_ms: int  # last trade time (exchange), epoch ms; 0 if unknown
    ts_server_ms: int  # venue server timestamp of the frame
    ts_recv_ns: int  # our receive time
    ltp: Paise
    ltq: int = 0
    prev_close: Paise = 0
    bids: tuple[DepthLevel, ...] = ()
    asks: tuple[DepthLevel, ...] = ()
    atp: Paise | None = None
    volume: int | None = None  # volume traded today
    oi: float | None = None
    iv: float | None = None
    total_buy_qty: float | None = None
    total_sell_qty: float | None = None
    greeks: Greeks | None = None
    bars: tuple[Bar, ...] = ()
    iep: Paise | None = None  # pre-open indicative equilibrium price
    ieq: int | None = None  # pre-open indicative equilibrium quantity
    cas_eligible: bool | None = None
    snapshot: bool = False  # True for the initial snapshot after (re)subscribe

    @property
    def best_bid(self) -> DepthLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> DepthLevel | None:
        return self.asks[0] if self.asks else None


class MarketStatus(msgspec.Struct, kw_only=True):
    ts_server_ms: int
    ts_recv_ns: int
    segments: dict[str, str]  # e.g. {"NSE_EQ": "NORMAL_OPEN"}


class FeedState(msgspec.Struct, kw_only=True):
    """Connection lifecycle. `GAP` means data between `since_ns` and now was missed."""

    connection: str
    state: str  # CONNECTED | DISCONNECTED | GAP | STALE
    ts_recv_ns: int
    since_ns: int = 0
    detail: str = ""


MarketEvent = Quote | MarketStatus | FeedState
