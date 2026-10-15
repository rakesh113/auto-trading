"""Synthetic market data for engine tests: deterministic quote paths minute by minute."""

from __future__ import annotations

from datetime import date, datetime

from trader.domain.instrument import InstrumentId
from trader.domain.market import Bar as FeedBar
from trader.domain.market import DepthLevel, Quote
from trader.domain.types import IST, FeedMode
from trader.market.history import DailyContext

DAY = date(2026, 10, 12)


def ts(h: int, m: int, s: float = 0.0) -> int:
    return int(datetime(2026, 10, 12, h, m, int(s), int((s % 1) * 1e6), tzinfo=IST).timestamp() * 1e9)


def ctx(iid: str, *, pdc: int = 100000, atr: int = 2000, vol_per_min: float = 10_000) -> DailyContext:
    return DailyContext(iid=iid, atr14=atr, pdh=pdc + 1000, pdl=pdc - 1000, pdc=pdc, pd_volume=int(vol_per_min * 375),
                        median_turnover_cr=500.0, high_52w=pdc + 20000, low_52w=pdc - 20000, sma20=pdc, sma50=pdc,
                        vol_curve=[vol_per_min * (i + 1) for i in range(360)])


class Tape:
    """Builds quotes for one instrument with cumulative volume and a running VWAP."""

    def __init__(self, iid: str, *, spread: int = 10, depth_qty: int = 5000, day_open: int | None = None) -> None:
        self.iid = InstrumentId.parse(iid)
        self.spread = spread
        self.depth_qty = depth_qty
        self.volume = 0
        self.pv = 0.0
        self.day_open = day_open
        self.hi = 0
        self.lo = 0

    def quote(self, t: int, price: int, vol: int = 0) -> Quote:
        self.volume += vol
        self.pv += price * vol
        if self.day_open is None:
            self.day_open = price
        self.hi = max(self.hi or price, price)
        self.lo = min(self.lo or price, price)
        vwap = round(self.pv / self.volume) if self.volume else price
        half = self.spread // 2
        return Quote(iid=self.iid, native=str(self.iid), mode=FeedMode.FULL, ts_exch_ms=t // 1_000_000,
                     ts_server_ms=t // 1_000_000, ts_recv_ns=t, ltp=price, ltq=1, volume=self.volume, atp=vwap,
                     bids=(DepthLevel(price - half, self.depth_qty),), asks=(DepthLevel(price + half, self.depth_qty),),
                     bars=(FeedBar("1d", 0, self.day_open, self.hi, self.lo, price, self.volume),))
