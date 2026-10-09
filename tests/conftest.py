from __future__ import annotations

from datetime import datetime

import pytest

from trader.adapters.upstox.instruments import UpstoxInstrumentMaster
from trader.core.clock import SimClock
from trader.domain.types import IST

# Real rows from the Upstox master (2026-10-09), trimmed.
SAMPLE_ROWS = [
    {"segment": "NSE_EQ", "name": "RELIANCE INDUSTRIES LTD", "exchange": "NSE", "isin": "INE002A01018",
     "instrument_type": "EQ", "instrument_key": "NSE_EQ|INE002A01018", "lot_size": 1, "freeze_quantity": 100000.0,
     "exchange_token": "2885", "tick_size": 10.0, "trading_symbol": "RELIANCE", "qty_multiplier": 1.0,
     "cas_eligible": True},
    {"segment": "NSE_EQ", "name": "SDL RJ 7.49% 2035", "exchange": "NSE", "isin": "IN2920250163",
     "instrument_type": "SG", "instrument_key": "NSE_EQ|IN2920250163", "lot_size": 100, "tick_size": 1.0,
     "trading_symbol": "749RJ35"},
    {"segment": "NSE_INDEX", "name": "Nifty 50", "exchange": "NSE", "instrument_type": "INDEX",
     "instrument_key": "NSE_INDEX|Nifty 50", "exchange_token": "26000", "trading_symbol": "NIFTY"},
    {"weekly": False, "segment": "NSE_FO", "name": "NIFTY", "exchange": "NSE", "expiry": 1793125799000,
     "instrument_type": "FUT", "asset_symbol": "NIFTY", "underlying_symbol": "NIFTY",
     "instrument_key": "NSE_FO|48704", "lot_size": 65, "freeze_quantity": 3510.0, "exchange_token": "48704",
     "underlying_key": "NSE_INDEX|Nifty 50", "tick_size": 10.0, "trading_symbol": "NIFTY FUT 27 OCT 26",
     "strike_price": 0.0, "qty_multiplier": 1.0},
    {"weekly": False, "segment": "NSE_FO", "name": "NIFTY", "exchange": "NSE", "expiry": 1798568999000,
     "instrument_type": "CE", "asset_symbol": "NIFTY", "underlying_symbol": "NIFTY",
     "instrument_key": "NSE_FO|50978", "lot_size": 65, "freeze_quantity": 3510.0, "exchange_token": "50978",
     "underlying_key": "NSE_INDEX|Nifty 50", "tick_size": 5.0, "trading_symbol": "NIFTY 27000 CE 29 DEC 26",
     "strike_price": 27000.0, "qty_multiplier": 1.0},
    {"segment": "MCX_FO", "name": "CRUDE OIL", "exchange": "MCX", "expiry": 1792088999000, "instrument_type": "CE",
     "asset_symbol": "CRUDEOILM", "underlying_symbol": "CRUDEOILM", "instrument_key": "MCX_FO|584953",
     "lot_size": 10, "freeze_quantity": 1000.0, "exchange_token": "584953", "underlying_key": "MCX_FO|569901",
     "tick_size": 5.0, "trading_symbol": "CRUDEOILM 12700 CE 15 OCT 26", "strike_price": 12700.0,
     "qty_multiplier": 10.0},
]


@pytest.fixture
def master(tmp_path) -> UpstoxInstrumentMaster:
    m = UpstoxInstrumentMaster(data_dir=tmp_path, url="http://unused")
    m.load_rows(SAMPLE_ROWS)
    return m


@pytest.fixture
def clock() -> SimClock:
    return SimClock(int(datetime(2026, 10, 12, 10, 0, tzinfo=IST).timestamp() * 1e9))
