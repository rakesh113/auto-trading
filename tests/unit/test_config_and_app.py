from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trader.adapters.paper.trader import PaperTrader
from trader.core.app import LIVE_ARM_ENV, LiveTradingBlocked, build_app
from trader.core.config import load_config
from trader.core.registry import traders
from trader.domain.instrument import InstrumentId


def test_paper_profile_builds_paper_trader(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", "x")
    cfg = load_config("paper", overrides={"system": {"data_dir": str(tmp_path)}, "notifier": {"provider": "log"}},
                      env_file=None)
    app = build_app(cfg, with_feed=False)
    assert isinstance(app.trader, PaperTrader)


def test_live_venue_refused_without_live_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(LIVE_ARM_ENV, "yes")
    cfg = load_config("paper", overrides={"execution": {"venue": "upstox"}, "system": {"data_dir": str(tmp_path)}},
                      env_file=None)
    with pytest.raises(LiveTradingBlocked):
        build_app(cfg, with_feed=False)


def test_live_profile_refused_until_armed(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(LIVE_ARM_ENV, raising=False)
    cfg = load_config("live", overrides={"system": {"data_dir": str(tmp_path)}}, env_file=None)
    assert cfg.execution.venue == "upstox"
    with pytest.raises(LiveTradingBlocked):
        build_app(cfg, with_feed=False)


def test_unknown_venue_lists_known() -> None:
    with pytest.raises(KeyError, match="paper"):
        traders.get("nope")


def test_registry_accepts_new_trader() -> None:
    from trader.ports.execution import TraderCaps

    @traders.register("dummy_test_venue")
    class Dummy(PaperTrader):
        caps = TraderCaps(live=False)

    assert traders.get("dummy_test_venue") is Dummy


def test_master_mapping(master) -> None:
    rel = InstrumentId.parse("NSE:EQ:RELIANCE")
    assert master.to_native(rel) == "NSE_EQ|INE002A01018"
    assert master.from_native("NSE_FO|48704") == InstrumentId.parse("NSE:FUT:NIFTY:2026-10-27")
    assert master.get(rel).tick_size == 10 and master.get(rel).cas_eligible
    opt = master.from_native("NSE_FO|50978")
    assert opt == InstrumentId.parse("NSE:OPT:NIFTY:2026-12-29:27000:CE")
    assert master.get(opt).underlying == "NSE:IDX:NIFTY50"
    crude = master.from_native("MCX_FO|584953")
    assert master.get(crude).qty_multiplier == Decimal(10)
    assert master.find(InstrumentId.parse("NSE:EQ:749RJ35")) is None  # bonds filtered out
    assert master.expiries("NIFTY", on_or_after=date(2026, 10, 1)) == [date(2026, 12, 29)]
