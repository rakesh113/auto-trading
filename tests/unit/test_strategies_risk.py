"""Setups, risk sizing and vetoes on synthetic data."""

from __future__ import annotations

from datetime import date

import pytest

from tests.engine_helpers import Tape, ctx, ts
from trader.core.config import CONFIG_DIR
from trader.core.costs import CostModel
from trader.domain.instrument import InstrumentId
from trader.domain.types import Side
from trader.market.state import SymbolState
from trader.risk.engine import BookStatus, OpenPosition, RiskConfig, RiskEngine
from trader.strategies.base import MarketView, Signal, Target
from trader.strategies.e1_orb import E1OrbRetest
from trader.strategies.e2_vwap import E2VwapReclaim

STOCK = "NSE:EQ:RELIANCE"


def feed(st: SymbolState, tape: Tape, path: list[tuple[int, int, int, int]], strat, view_fn):
    """path: (hour, minute, price, volume) — one quote per 20 s inside each minute."""
    sigs = []
    for h, m, p, v in path:
        for k, s in enumerate((5, 25, 45)):
            q = tape.quote(ts(h, m, s), p, v // 3)
            for bar in st.on_quote(q):
                sig = strat.on_bar(st, bar, view_fn(bar))
                if sig:
                    sigs.append(sig)
    return sigs


def minutes(h0: int, m0: int, prices: list[int], vol: int) -> list[tuple[int, int, int, int]]:
    out = []
    for i, p in enumerate(prices):
        t = h0 * 60 + m0 + i
        out.append((t // 60, t % 60, p, vol))
    return out


def test_bars_close_only_after_the_minute() -> None:
    st = SymbolState(InstrumentId.parse(STOCK), ctx(STOCK), tick=10)
    tape = Tape(STOCK)
    assert st.on_quote(tape.quote(ts(9, 15, 5), 100000, 100)) == []
    assert st.on_quote(tape.quote(ts(9, 15, 50), 100200, 100)) == []
    closed = st.on_quote(tape.quote(ts(9, 16, 1), 100100, 100))
    assert len(closed) == 1 and closed[0].high == 100200 and closed[0].start_min == 0


def test_e1_long_breakout_retest_hold() -> None:
    st = SymbolState(InstrumentId.parse(STOCK), ctx(STOCK, atr=2000, vol_per_min=1000), tick=10)
    tape = Tape(STOCK)
    strat = E1OrbRetest()
    # OR15 09:15-09:29: range 100000-100800 (0.4 ATR); heavy volume → RVOL > 2
    orng = [100000, 100400, 100800, 100300, 100500] * 3
    path = minutes(9, 15, orng, 3000)
    # 09:30-09:34 break above with a 5-min close at 101000 on high volume
    path += minutes(9, 30, [100700, 100850, 100900, 100950, 101000], 9000)
    # retest back to the OR high (within 0.1 ATR = 200), then a close back above
    path += minutes(9, 35, [100900, 100850, 101050, 101100], 4000)
    sigs = feed(st, tape, path, strat, lambda bar: MarketView(0, bar.start_min + 1, None))
    assert len(sigs) == 1
    s = sigs[0]
    assert s.side is Side.BUY and s.setup == "E1_ORB_RETEST"
    assert 100400 <= s.stop < s.entry and s.entry > 100800  # stop under the retest low, above OR mid
    assert s.targets[0].price - s.entry == s.entry - s.stop  # 1R partial


def test_e2_vwap_reclaim_long() -> None:
    st = SymbolState(InstrumentId.parse(STOCK), ctx(STOCK), tick=10)
    tape = Tape(STOCK)
    strat = E2VwapReclaim()
    up = [100000 + 40 * i for i in range(45)]  # rising all morning → VWAP slopes up, stock strong
    path = minutes(9, 15, up, 3000)
    t = 9 * 60 + 15 + 45
    # dip below VWAP for one bar, then a reclaim on higher volume
    path += [(t // 60, t % 60, 100500, 3000), ((t + 1) // 60, (t + 1) % 60, 101300, 6000),
             ((t + 2) // 60, (t + 2) % 60, 101350, 3000)]
    sigs = feed(st, tape, path, strat, lambda bar: MarketView(0, bar.start_min + 1, None))
    assert len(sigs) == 1 and sigs[0].side is Side.BUY and sigs[0].stop < 100500


# ---- risk ---------------------------------------------------------------------------------------


@pytest.fixture
def risk() -> RiskEngine:
    return RiskEngine(RiskConfig.load(CONFIG_DIR / "risk.yaml"),
                      CostModel.load(CONFIG_DIR / "costs.yaml", "upstox_plus"))


def _state(price: int = 300000, atr: int = 5400) -> SymbolState:
    st = SymbolState(InstrumentId.parse(STOCK), ctx(STOCK, pdc=price, atr=atr), tick=10)
    st.ltp, st.bid, st.ask, st.last_ts = price, price - 10, price + 10, ts(10, 0)
    return st


def _sig(entry: int, stop: int, side: Side = Side.BUY, t2r: float = 3.0) -> Signal:
    r = abs(entry - stop)
    s = side.sign
    return Signal("E2_VWAP_RECLAIM", InstrumentId.parse(STOCK), side, entry, stop,
                  (Target(0.5, entry + s * r), Target(0.5, entry + s * round(t2r * r))))


def _book() -> BookStatus:
    return BookStatus(equity=100_000_000, hwm=100_000_000)


def _eval(risk: RiskEngine, sig: Signal, st: SymbolState, b: BookStatus, **kw):
    args = {"now_ns": ts(10, 0), "minute": 45, "shortable": True, "day": date(2026, 10, 12)} | kw
    return risk.evaluate(sig, st, b, **args)


def test_report_example_b_sizing(risk) -> None:
    """Report 03 example B: ₹3,000 stock, stop ₹11.5 → about 344 shares at R = ₹5,000."""
    d = _eval(risk, _sig(300600, 299450), _state(300600), _book())
    assert d.approved, d
    assert 330 <= d.qty <= 400
    assert d.friction_r <= 0.2


def test_stop_floor_and_friction_vetoes(risk) -> None:
    assert _eval(risk, _sig(300000, 299800), _state(), _book()).rule == "stop_floor"  # 0.07% stop


def test_invariant_blocks_report_example_d(risk) -> None:
    b = _book()
    b.realized = -500_000  # −₹5k
    for i, rk in enumerate((400_000, 500_000, 300_000)):  # open risk ₹4k + ₹5k + ₹3k
        b.positions.append(OpenPosition(InstrumentId.parse(f"NSE:EQ:X{i}"), Side.BUY, 1000, 10000, 10000 - rk // 1000,
                                        10000))
    d = _eval(risk, _sig(300600, 299450), _state(300600), b)
    assert not d.approved and d.rule in ("invariant", "open_risk")


def test_short_needs_fno_and_time_cutoff(risk) -> None:
    st = _state()
    assert _eval(risk, _sig(300000, 301200, Side.SELL), st, _book(), shortable=False).rule == "short_not_allowed"
    assert _eval(risk, _sig(300000, 298800), st, _book(), minute=330).rule == "time"


def test_reward_risk_gate(risk) -> None:
    assert _eval(risk, _sig(300600, 299450, t2r=1.2), _state(300600), _book()).rule == "reward_risk"


def test_kill_on_daily_loss(risk) -> None:
    b = _book()
    b.realized = -2_000_000  # −₹20k = 2% DLL
    assert "daily loss" in risk.should_flatten(b)
