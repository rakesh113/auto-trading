from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trader.domain.instrument import InstrumentId
from trader.domain.orders import Fill
from trader.domain.portfolio import Position
from trader.domain.types import Exchange, InstrumentKind, OptionRight, Product, Side, round_to_tick, to_paise


@pytest.mark.parametrize("s", [
    "NSE:EQ:RELIANCE", "NSE:EQ:M&M", "NSE:IDX:NIFTY50", "NSE:FUT:NIFTY:2026-10-27",
    "NSE:OPT:NIFTY:2026-10-13:25000:CE", "NSE:OPT:RELIANCE:2026-10-27:1412.5:PE", "MCX:FUT:CRUDEOILM:2026-10-19",
])
def test_instrument_id_roundtrip(s: str) -> None:
    assert str(InstrumentId.parse(s)) == s


@pytest.mark.parametrize("s", ["NSE:EQ", "NSE:FUT:NIFTY", "NSE:OPT:NIFTY:2026-10-13:25000", "XXX:EQ:A",
                               "NSE:EQ:A:2026-01-01"])
def test_instrument_id_rejects(s: str) -> None:
    with pytest.raises(ValueError):
        InstrumentId.parse(s)


@given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&-", min_size=1, max_size=12),
       st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 1, 1)),
       st.decimals(min_value=Decimal("0.05"), max_value=Decimal("200000"), places=2, allow_nan=False),
       st.sampled_from(list(OptionRight)))
def test_option_id_roundtrip_property(sym, exp, strike, right) -> None:
    iid = InstrumentId(Exchange.NSE, InstrumentKind.OPT, sym, exp, strike, right)
    assert InstrumentId.parse(str(iid)) == iid


def test_paise_conversion_is_exact() -> None:
    assert to_paise(2512.35) == 251235
    assert to_paise("0.05") == 5
    assert round_to_tick(251237, 5, up=True) == 251240
    assert round_to_tick(251237, 5, up=False) == 251235


def _fill(side: Side, qty: int, price: int) -> Fill:
    return Fill(client_order_id="x", trade_id="t", iid=InstrumentId.parse("NSE:EQ:RELIANCE"), side=side, qty=qty,
                price=price, ts_ns=0)


def test_position_average_cost_and_flip() -> None:
    p = Position(iid=InstrumentId.parse("NSE:EQ:RELIANCE"), product=Product.INTRADAY)
    p.apply(_fill(Side.BUY, 10, 1000))
    p.apply(_fill(Side.BUY, 10, 1100))
    assert p.qty == 20 and p.avg_price == 1050
    p.apply(_fill(Side.SELL, 5, 1200))
    assert p.realized == 750 and p.qty == 15
    p.apply(_fill(Side.SELL, 25, 1000))  # close 15 at a loss, open 10 short
    assert p.realized == 750 - 750 and p.qty == -10 and p.avg_price == 1000
    assert p.unrealized(900) == 1000
