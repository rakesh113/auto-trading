"""E1: opening-range breakout, entered on the first retest that holds (design §7.1, report 03 S2).

Per symbol, per side, once a day:

  WAIT_OR  → OR15 complete at 09:30; check OR width 0.25–0.8 ATR and RVOL ≥ 2
  ARMED    → a 5-min close beyond the OR on ≥ 1.5× expected 5-min volume  → BROKEN
  BROKEN   → a 1-min bar trades back to the OR edge (within 0.1 ATR)       → RETEST
  RETEST   → a 1-min close back beyond the edge, low still beyond OR mid    → SIGNAL
  any      → a close back through the OR midpoint, or 11:00                → DEAD

Stop: the retest extreme, or the OR midpoint when the retest is too close to entry to be
a real stop (< max(0.25% of price, 0.15 ATR)); skipped if wider than 0.5 ATR.
Exits: half at 1R, the rest at 3R or trailed on 5-min VWAP; time stop 45 min.
Relative strength vs Nifty must agree with the direction.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader.domain.types import Side
from trader.market.state import Bar, SymbolState
from trader.strategies.base import MarketView, Signal, Strategy, Target, at, strategies


@dataclass
class _Track:
    side: Side
    state: str = "ARMED"
    retest_extreme: int = 0


@strategies.register("E1_ORB_RETEST")
class E1OrbRetest(Strategy):
    windows = ((at(9, 30), at(11, 0)),)

    def __init__(self, **params: object) -> None:
        super().__init__(**params)
        self.min_or_atr = float(params.get("min_or_atr", 0.25))
        self.max_or_atr = float(params.get("max_or_atr", 0.8))
        self.min_rvol = float(params.get("min_rvol", 2.0))
        self.break_vol_mult = float(params.get("break_vol_mult", 1.5))
        self.max_stop_atr = float(params.get("max_stop_atr", 0.5))
        self.retest_atr = float(params.get("retest_atr", 0.1))
        self._tracks: dict[object, list[_Track]] = {}
        self._qualified: dict[object, bool] = {}

    def reset(self) -> None:
        self._tracks.clear()
        self._qualified.clear()

    def _qualify(self, st: SymbolState) -> bool:
        if st.iid in self._qualified:
            return self._qualified[st.iid]
        orr = st.opening_range(15)
        ok = False
        if orr and st.atr:
            width = (orr[0] - orr[1]) / st.atr
            rvol = st.rvol() or 0.0
            ok = self.min_or_atr <= width <= self.max_or_atr and rvol >= self.min_rvol
        if orr:
            self._qualified[st.iid] = ok
            if ok:
                self._tracks[st.iid] = [_Track(Side.BUY), _Track(Side.SELL)]
        return ok

    def on_bar(self, st: SymbolState, bar: Bar, view: MarketView) -> Signal | None:
        if bar.start_min < at(9, 29) or not self._qualify(st):
            return None
        orh, orl = st.opening_range(15)  # type: ignore[misc]
        mid = (orh + orl) // 2
        atr = st.atr
        idx_ret = view.index.return_since_open() if view.index else 0.0
        rel = st.return_since_open() - idx_ret
        for tr in self._tracks.get(st.iid, []):
            if tr.state == "DEAD":
                continue
            s = tr.side.sign
            edge = orh if s > 0 else orl
            if bar.start_min >= at(11, 0) or (bar.close - mid) * s < 0:
                tr.state = "DEAD"
                continue
            if tr.state == "ARMED":
                if bar.start_min % 5 == 4 and st.bars5 and st.bars5[-1].start_min == bar.start_min // 5 * 5:
                    b5 = st.bars5[-1]
                    exp = st.expected_bar_volume(b5.start_min, 5)
                    vol_ok = exp is None or b5.volume >= self.break_vol_mult * exp
                    if (b5.close - edge) * s > 0 and vol_ok:
                        tr.state = "BROKEN"
            elif tr.state == "BROKEN":
                near = edge + s * round(self.retest_atr * atr)
                touched = bar.low <= near if s > 0 else bar.high >= near
                if touched:
                    tr.state = "RETEST"
                    tr.retest_extreme = bar.low if s > 0 else bar.high
            if tr.state == "RETEST":
                tr.retest_extreme = min(tr.retest_extreme, bar.low) if s > 0 else max(tr.retest_extreme, bar.high)
                holds = (bar.close - edge) * s > 0 and (tr.retest_extreme - mid) * s > 0
                if holds and rel * s > 0 and self.in_window(bar.start_min):
                    tr.state = "DEAD"  # one entry per side per day
                    entry = bar.close
                    # structural stop: the retest extreme if it is a meaningful distance away,
                    # otherwise the OR midpoint (design: "OR midpoint or retest low, ≤ 0.5 ATR")
                    stop = tr.retest_extreme - s * st.tick
                    min_dist = max(entry * 0.0025, 0.15 * atr)
                    if abs(entry - stop) < min_dist:
                        stop = mid
                    if abs(entry - stop) > self.max_stop_atr * atr:
                        return None
                    risk = abs(entry - stop)
                    return Signal(
                        setup=self.name, iid=st.iid, side=tr.side, entry=entry, stop=stop,
                        targets=(Target(0.5, entry + s * risk), Target(0.5, entry + s * 3 * risk)),
                        trail="vwap5", time_stop_min=45, ts_ns=st.last_ts,
                        reason=f"OR15 {orl / 100:.2f}-{orh / 100:.2f} break+retest hold; rel={rel:+.3%}",
                    )
        return None
