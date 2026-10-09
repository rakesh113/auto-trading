"""In-play selection (design §7.1): which 5–8 names the setups watch today.

Deterministic score 0–100 from the components the system can measure itself. The
catalyst-materiality component (an LLM score) is added once the triage bake-off has
proven a model in shadow; until then its weight is redistributed proportionally.

Tier B eligibility: 20-day median turnover ≥ ₹75 cr, price ₹100–10,000, spread ≤ 8 bps.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader.domain.instrument import InstrumentId
from trader.market.state import SymbolState

WEIGHTS = {"catalyst": 25, "gap": 15, "preopen": 10, "rvol": 15, "rs": 10, "location": 10, "oi": 10, "deals": 5}


@dataclass(frozen=True)
class Scored:
    iid: InstrumentId
    score: float
    parts: dict[str, float]
    sector: str


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_symbol(st: SymbolState, index: SymbolState | None, *, catalyst: float | None = None) -> dict[str, float]:
    """Component scores in 0..1 (None components are skipped)."""
    parts: dict[str, float] = {}
    ctx = st.ctx
    if ctx is None or not ctx.atr14:
        return parts
    g = st.gap_atr()
    if g is not None:
        parts["gap"] = _clip(abs(g) / 1.0)  # 1 ATR gap = full marks
    if st.ieq and ctx.pd_volume:
        parts["preopen"] = _clip(st.ieq / (ctx.pd_volume * 0.02) / 2)  # ~1% of a day pre-open is typical
    rv = st.rvol()
    if rv is not None:
        parts["rvol"] = _clip((rv - 1) / 3)  # RVOL 4 = full marks
    if index is not None and st.day_open and index.day_open:
        rel = abs(st.return_since_open() - index.return_since_open())
        parts["rs"] = _clip(rel / 0.02)
    px = st.ltp or st.iep
    if px:
        near = min(abs(px - ctx.pdh), abs(px - ctx.pdl), abs(px - ctx.high_52w)) / ctx.atr14
        parts["location"] = _clip(1 - near / 0.5)
    if catalyst is not None:
        parts["catalyst"] = _clip(catalyst / 10)
    return parts


def penalties(st: SymbolState) -> float:
    p = 0.0
    sp = st.spread_bps()
    if sp is not None and sp > 8:
        p += 20
    if st.ctx and st.ctx.atr14 and st.day_open and abs(st.ltp - st.ctx.pdc) / st.ctx.atr14 > 2.5:
        p += 25  # exhausted: already moved > 2.5 ATR
    return p


def eligible(st: SymbolState) -> bool:
    ctx = st.ctx
    px = st.ltp or st.iep or (ctx.pdc if ctx else 0)
    return bool(ctx and ctx.median_turnover_cr >= 75 and 10_000 <= px <= 1_000_000)


def select(states: dict[InstrumentId, SymbolState], index: SymbolState | None, sectors: dict[str, str], *,
           primary: int = 5, watch: int = 12, per_sector: int = 2,
           catalysts: dict[InstrumentId, float] | None = None, min_rvol: float | None = None,
           ) -> tuple[list[Scored], list[Scored]]:
    scored: list[Scored] = []
    for iid, st in states.items():
        if not eligible(st):
            continue
        if min_rvol is not None and (st.rvol() or 0) < min_rvol:
            continue
        parts = score_symbol(st, index, catalyst=(catalysts or {}).get(iid))
        if not parts:
            continue
        wsum = sum(WEIGHTS[k] for k in parts)
        score = sum(WEIGHTS[k] * v for k, v in parts.items()) / wsum * 100 - penalties(st)
        scored.append(Scored(iid, round(score, 2), parts, sectors.get(iid.symbol, "")))
    scored.sort(key=lambda s: (-s.score, str(s.iid)))
    chosen: list[Scored] = []
    per: dict[str, int] = {}
    for s in scored:
        if len(chosen) >= primary:
            break
        if s.sector and per.get(s.sector, 0) >= per_sector:
            continue
        chosen.append(s)
        per[s.sector] = per.get(s.sector, 0) + 1
    rest = [s for s in scored if s not in chosen][:watch]
    return chosen, rest
