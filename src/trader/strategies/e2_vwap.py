"""E2: VWAP reclaim (long) / reject (short) after 10:00 (design §7.1, report 03 S3).

Long: VWAP rising over 30 min and the stock stronger than Nifty. A 1-min close below
VWAP (the dip), then within 2 bars a 1-min close back above VWAP on rising volume →
signal. Short is the mirror. Stop: the dip extreme (never wider than VWAP ∓ 0.6 ATR).
Exits: half at 1R, the rest at the high of day if that is ≥ 2R away, else 2R; trail on
5-min VWAP; time stop 45 min. Disabled for a symbol after > 4 VWAP crosses in 30 min.
At most 2 entries per symbol per day.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader.domain.types import Side
from trader.market.state import Bar, SymbolState
from trader.strategies.base import MarketView, Signal, Strategy, Target, at, strategies


@dataclass
class _Dip:
    side: Side
    bars_since: int = 0
    extreme: int = 0


@strategies.register("E2_VWAP_RECLAIM")
class E2VwapReclaim(Strategy):
    windows = ((at(10, 0), at(11, 30)), (at(13, 30), at(14, 30)))  # lunch chop excluded (design §8)

    def __init__(self, **params: object) -> None:
        super().__init__(**params)
        self.max_crosses = int(params.get("max_crosses", 4))
        self.max_stop_atr = float(params.get("max_stop_atr", 0.6))
        self.max_entries = int(params.get("max_entries", 2))
        self._dip: dict[object, _Dip | None] = {}
        self._entries: dict[object, int] = {}

    def reset(self) -> None:
        self._dip.clear()
        self._entries.clear()

    def on_bar(self, st: SymbolState, bar: Bar, view: MarketView) -> Signal | None:
        if bar.start_min < at(9, 45) or not st.atr or not bar.vwap:
            return None
        if self._entries.get(st.iid, 0) >= self.max_entries or st.vwap_crosses(30) > self.max_crosses:
            self._dip[st.iid] = None
            return None
        slope = st.vwap_slope(30)
        idx_ret = view.index.return_since_open() if view.index else 0.0
        rel = st.return_since_open() - idx_ret
        side = Side.BUY if slope > 0 and rel > 0 else Side.SELL if slope < 0 and rel < 0 else None
        dip = self._dip.get(st.iid)
        if side is None:
            self._dip[st.iid] = None
            return None
        s = side.sign
        below = (bar.close - bar.vwap) * s < 0
        if dip is None or dip.side is not side:
            self._dip[st.iid] = _Dip(side, 0, bar.low if s > 0 else bar.high) if below else None
            return None
        dip.bars_since += 1
        dip.extreme = min(dip.extreme, bar.low) if s > 0 else max(dip.extreme, bar.high)
        if below:
            if dip.bars_since > 2:  # stayed under too long: restart the dip count
                self._dip[st.iid] = _Dip(side, 0, dip.extreme)
            return None
        prev = st.bars1[-2] if len(st.bars1) >= 2 else None
        rising_vol = prev is not None and bar.volume > prev.volume
        self._dip[st.iid] = None
        if dip.bars_since > 2 or not rising_vol or not self.in_window(bar.start_min):
            return None
        entry = bar.close
        stop = dip.extreme - s * st.tick
        if abs(entry - stop) > self.max_stop_atr * st.atr or abs(entry - stop) == 0:
            return None
        risk = abs(entry - stop)
        hod_target = st.hod if s > 0 else st.lod
        final = hod_target if (hod_target - entry) * s >= 2 * risk else entry + s * 2 * risk
        self._entries[st.iid] = self._entries.get(st.iid, 0) + 1
        return Signal(
            setup=self.name, iid=st.iid, side=side, entry=entry, stop=stop,
            targets=(Target(0.5, entry + s * risk), Target(0.5, final)),
            trail="vwap5", time_stop_min=45, ts_ns=st.last_ts,
            reason=f"VWAP {'reclaim' if s > 0 else 'reject'} after {dip.bars_since}-bar dip; slope={slope}; rel={rel:+.3%}",
        )
