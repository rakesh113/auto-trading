"""Setup state machines produce `Signal`s; risk turns them into sized orders (design §3, §7.1).

Strategies are deterministic and bar-driven: they see only closed bars and current
state, never future data. They do not size, check limits or place orders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trader.core.registry import Registry
from trader.domain.instrument import InstrumentId
from trader.domain.types import Paise, Side
from trader.market.state import Bar, SymbolState


@dataclass(frozen=True, slots=True)
class Target:
    fraction: float  # of the original quantity
    price: Paise


@dataclass(frozen=True, slots=True)
class Signal:
    setup: str
    iid: InstrumentId
    side: Side
    entry: Paise  # reference price at signal time
    stop: Paise
    targets: tuple[Target, ...]
    trail: str | None = None  # "vwap5": exit remainder on a 5-min close through VWAP
    time_stop_min: int = 45
    ts_ns: int = 0
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_share(self) -> int:
        return abs(self.entry - self.stop)

    def r_multiple(self, price: Paise) -> float:
        rps = self.risk_per_share
        return (price - self.entry) * self.side.sign / rps if rps else 0.0


@dataclass
class MarketView:
    """Shared, read-only context strategies may consult."""

    now_ns: int
    minute: int  # minutes since 09:15
    index: SymbolState | None  # Nifty 50
    day_type: str = "UNKNOWN"
    in_play: frozenset[InstrumentId] = frozenset()
    shortable: frozenset[InstrumentId] = frozenset()


class Strategy(ABC):
    name: str = "abstract"
    windows: tuple[tuple[int, int], ...] = ()  # allowed entry windows, minutes since 09:15

    def __init__(self, **params: Any) -> None:
        self.params = params

    def in_window(self, minute: int) -> bool:
        return any(a <= minute < b for a, b in self.windows)

    @abstractmethod
    def on_bar(self, st: SymbolState, bar: Bar, view: MarketView) -> Signal | None:
        """Called for every closed 1-minute bar of a monitored symbol."""

    def reset(self) -> None:  # noqa: B027 - optional
        """Start-of-day reset."""


strategies: Registry[Any] = Registry(
    "strategy", "trader.strategies",
    {"E1_ORB_RETEST": "trader.strategies.e1_orb", "E2_VWAP_RECLAIM": "trader.strategies.e2_vwap"},
)


def hhmm(minute: int) -> str:
    t = 9 * 60 + 15 + minute
    return f"{t // 60:02d}:{t % 60:02d}"


def at(hh: int, mm: int) -> int:
    """Clock time → minutes since 09:15."""
    return hh * 60 + mm - (9 * 60 + 15)
