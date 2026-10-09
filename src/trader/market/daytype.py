"""Deterministic day-type labeller (design §8, report 03 §3).

Evaluated at 09:30 (provisional), 09:45, 10:30 and 13:30. In the MVP the label is
logged for every book, but only HIGH_VOL_EVENT blocks entries (design §7.1); the full
allow/block matrix switches on once the labeller is validated against end-of-day labels.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader.domain.instrument import InstrumentId
from trader.market.state import SymbolState


@dataclass(frozen=True)
class DayType:
    label: str
    reasons: tuple[str, ...]
    inputs: dict[str, float]


def breadth(states: dict[InstrumentId, SymbolState]) -> float | None:
    """Advance/decline ratio across everything with a previous close."""
    adv = dec = 0
    for st in states.values():
        if st.ctx and st.ltp:
            if st.ltp > st.ctx.pdc:
                adv += 1
            elif st.ltp < st.ctx.pdc:
                dec += 1
    if adv + dec < 20:
        return None
    return adv / max(dec, 1)


def classify(index: SymbolState | None, vix: SymbolState | None, states: dict[InstrumentId, SymbolState],
             minute: int) -> DayType:
    if index is None or index.ctx is None or not index.ctx.atr14 or not index.day_open:
        return DayType("UNKNOWN", ("no index data",), {})
    atr = index.ctx.atr14
    gap = (index.day_open - index.ctx.pdc) / atr
    inputs: dict[str, float] = {"gap_atr": round(gap, 3)}
    reasons: list[str] = []
    vix_lvl = vix.ltp / 100 if vix and vix.ltp else None
    vix_chg = (vix.ltp - vix.ctx.pdc) / vix.ctx.pdc if vix and vix.ctx and vix.ctx.pdc and vix.ltp else None
    if vix_lvl is not None:
        inputs["vix"] = vix_lvl
    if vix_chg is not None:
        inputs["vix_chg"] = round(vix_chg, 4)
    if (vix_lvl is not None and vix_lvl >= 20) or (vix_chg is not None and vix_chg >= 0.08) or abs(gap) >= 1.0:
        reasons.append(f"vix={vix_lvl} vix_chg={vix_chg} gap={gap:.2f}ATR")
        return DayType("HIGH_VOL_EVENT", tuple(reasons), inputs)
    or30 = index.opening_range(30)
    ad = breadth(states)
    if ad is not None:
        inputs["ad"] = round(ad, 2)
    closes = [b for b in index.bars5 if b.start_min >= 30]
    above = sum(1 for b in closes if b.close > b.vwap)
    share = max(above, len(closes) - above) / len(closes) if closes else 0.0
    inputs["vwap_side_share"] = round(share, 2)
    if or30 is None:
        return DayType("UNKNOWN", ("opening range not complete",), inputs)
    width = (or30[0] - or30[1]) / atr
    inputs["or30_atr"] = round(width, 3)
    broke_up = index.ltp > or30[0]
    broke_dn = index.ltp < or30[1]
    if abs(gap) >= 0.5:
        held = (index.ltp - index.day_open) * (1 if gap > 0 else -1) >= 0
        return DayType("GAP_AND_GO" if held else "GAP_AND_FADE", (f"gap {gap:.2f} ATR, held={held}",), inputs)
    if width <= 0.35 and (broke_up or broke_dn) and share >= 0.8 and ad is not None and \
            ((broke_up and ad >= 2.5) or (broke_dn and ad <= 0.4)):
        return DayType("TREND_UP" if broke_up else "TREND_DOWN", ("narrow OR broken with breadth",), inputs)
    if width >= 0.5 or index.vwap_crosses(60) >= 4 or (ad is not None and 0.7 <= ad <= 1.4):
        return DayType("RANGE", ("wide OR / VWAP crosses / flat breadth",), inputs)
    if width <= 0.2:
        return DayType("COMPRESSED", ("very narrow opening range",), inputs)
    return DayType("UNKNOWN", ("no rule matched",), inputs)
