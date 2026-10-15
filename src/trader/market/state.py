"""Per-symbol intraday state built from conflated snapshots (design §7.1, §8).

Bars are bucketed by *receive time* (the Clock), not exchange trade time, so live and
replay produce identical bars. A bar is emitted only after it closes (no look-ahead):
either when a quote from a later minute arrives, or when `on_time` passes the boundary.
VWAP is the exchange's average traded price (`atp`) when the feed provides it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from trader.domain.instrument import InstrumentId
from trader.domain.market import Quote
from trader.domain.types import IST, Paise
from trader.market.history import DailyContext

OPEN_MIN = 9 * 60 + 15  # minutes after midnight IST


@dataclass(slots=True)
class Bar:
    start_min: int  # minutes since 09:15 at bar start
    open: Paise
    high: Paise
    low: Paise
    close: Paise
    volume: int
    vwap: Paise  # VWAP at bar close

    @property
    def range(self) -> int:
        return self.high - self.low


def minute_of_session(ts_ns: int) -> int:
    t = datetime.fromtimestamp(ts_ns / 1e9, IST)
    return t.hour * 60 + t.minute - OPEN_MIN


@dataclass
class SymbolState:
    iid: InstrumentId
    ctx: DailyContext | None = None
    tick: Paise = 5
    ltp: Paise = 0
    bid: Paise = 0
    ask: Paise = 0
    volume: int = 0  # cumulative today
    vwap: Paise = 0
    day_open: Paise = 0
    hod: Paise = 0
    lod: Paise = 0
    iep: Paise = 0  # pre-open equilibrium price
    ieq: int = 0
    last_ts: int = 0
    bars1: list[Bar] = field(default_factory=list)
    bars5: list[Bar] = field(default_factory=list)
    ema20_5m: float | None = None
    vwap_history: deque[tuple[int, Paise]] = field(default_factory=lambda: deque(maxlen=120))  # (minute, vwap)
    _cur: Bar | None = None
    _cur5: Bar | None = None
    _vol_at_bar_start: int = 0
    _pv: float = 0.0  # fallback VWAP accumulator when atp is absent
    _pv_vol: int = 0

    # ---- updates --------------------------------------------------------------------------

    def on_quote(self, q: Quote) -> list[Bar]:
        closed = self.on_time(q.ts_recv_ns)
        m = minute_of_session(q.ts_recv_ns)
        self.last_ts = q.ts_recv_ns
        if q.iep:
            self.iep, self.ieq = q.iep, q.ieq or self.ieq
        if q.bids:
            self.bid = q.bids[0].price
        if q.asks:
            self.ask = q.asks[0].price
        if m < 0 or q.ltp <= 0:  # pre-open: keep the indicative price, no bars
            return closed
        prev_vol = self.volume
        if q.volume is not None:
            self.volume = max(self.volume, q.volume)
        self.ltp = q.ltp
        d1 = next((b for b in q.bars if b.interval == "1d"), None)
        if d1 is not None and d1.open > 0:  # the exchange's own day open/high/low (works on a late start too)
            self.day_open = d1.open
            self.hod = max(self.hod, d1.high) if self.hod else d1.high
            self.lod = min(self.lod, d1.low) if self.lod else d1.low
        elif not self.day_open and m <= 1:  # no daily bar in this mode: trust only a print near the open
            self.day_open = q.ltp
        if self.hod:
            self.hod = max(self.hod, q.ltp)
            self.lod = min(self.lod, q.ltp)
        elif self.day_open:
            self.hod = self.lod = q.ltp
        if q.atp:
            self.vwap = q.atp
        else:
            dv = self.volume - prev_vol
            if dv > 0:
                self._pv += q.ltp * dv
                self._pv_vol += dv
            self.vwap = round(self._pv / self._pv_vol) if self._pv_vol else q.ltp
        if self._cur is None or self._cur.start_min != m:
            self._cur = Bar(m, q.ltp, q.ltp, q.ltp, q.ltp, 0, self.vwap)
            self._vol_at_bar_start = prev_vol if prev_vol else self.volume
        b = self._cur
        b.high = max(b.high, q.ltp)
        b.low = min(b.low, q.ltp)
        b.close = q.ltp
        b.volume = self.volume - self._vol_at_bar_start
        b.vwap = self.vwap
        return closed

    def on_time(self, ts_ns: int) -> list[Bar]:
        """Close the current bar if its minute has ended. Returns newly closed 1-min bars."""
        if self._cur is None or minute_of_session(ts_ns) <= self._cur.start_min:
            return []
        bar = self._cur
        self._cur = None
        self.bars1.append(bar)
        self.vwap_history.append((bar.start_min, bar.vwap))
        self._roll5(bar)
        return [bar]

    def _roll5(self, b: Bar) -> None:
        slot = b.start_min // 5 * 5
        c = self._cur5
        if c is None or c.start_min != slot:
            c = self._cur5 = Bar(slot, b.open, b.high, b.low, b.close, b.volume, b.vwap)
        else:
            c.high, c.low, c.close = max(c.high, b.high), min(c.low, b.low), b.close
            c.volume += b.volume
            c.vwap = b.vwap
        if b.start_min % 5 == 4:  # last minute of the 5-min slot
            self.bars5.append(c)
            self._cur5 = None
            k = 2 / 21
            self.ema20_5m = c.close if self.ema20_5m is None else self.ema20_5m + k * (c.close - self.ema20_5m)

    # ---- derived ---------------------------------------------------------------------------

    @property
    def atr(self) -> int:
        return self.ctx.atr14 if self.ctx else 0

    def opening_range(self, minutes: int) -> tuple[Paise, Paise] | None:
        """(high, low) of the first `minutes` of the session, once complete."""
        bars = [b for b in self.bars1 if b.start_min < minutes]
        if not bars or self.bars1[-1].start_min < minutes - 1:
            return None
        return max(b.high for b in bars), min(b.low for b in bars)

    def rvol(self) -> float | None:
        """Volume so far ÷ the 20-day average volume by this minute."""
        if not self.ctx or not self.bars1:
            return None
        exp = self.ctx.expected_volume_by(self.bars1[-1].start_min + 1)
        return self.volume / exp if exp else None

    def expected_bar_volume(self, start_min: int, width: int) -> float | None:
        if not self.ctx or not self.ctx.vol_curve:
            return None
        hi = self.ctx.expected_volume_by(start_min + width) or 0
        lo = self.ctx.expected_volume_by(start_min) if start_min > 0 else 0
        return (hi - (lo or 0)) or None

    def return_since_open(self) -> float:
        return (self.ltp - self.day_open) / self.day_open if self.day_open else 0.0

    def gap_atr(self) -> float | None:
        ref = self.day_open or self.iep
        if not self.ctx or not self.ctx.atr14 or not ref:
            return None
        return (ref - self.ctx.pdc) / self.ctx.atr14

    def spread_bps(self) -> float | None:
        if self.bid and self.ask and self.ask > self.bid:
            return (self.ask - self.bid) / ((self.ask + self.bid) / 2) * 1e4
        return None

    def vwap_slope(self, minutes: int = 30) -> int:
        """VWAP now minus VWAP `minutes` ago (paise); 0 if unknown."""
        if not self.vwap_history:
            return 0
        now_min, now_v = self.vwap_history[-1]
        for m, v in self.vwap_history:
            if m >= now_min - minutes:
                return now_v - v
        return 0

    def vwap_crosses(self, minutes: int = 30) -> int:
        bars = [b for b in self.bars1 if self.bars1 and b.start_min > self.bars1[-1].start_min - minutes]
        sides = [b.close > b.vwap for b in bars]
        return sum(1 for a, b in zip(sides, sides[1:], strict=False) if a != b)
