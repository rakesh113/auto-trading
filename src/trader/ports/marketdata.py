"""Market-data and reference-data ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from trader.domain.instrument import Instrument, InstrumentId
from trader.domain.market import MarketEvent
from trader.domain.types import FeedMode


@dataclass(slots=True)
class FeedHealth:
    connected: bool = False
    last_msg_ns: int = 0
    messages: int = 0
    frames: int = 0
    reconnects: int = 0
    dropped: int = 0  # events dropped because consumers fell behind
    decode_errors: int = 0
    subscribed: dict[str, int] = field(default_factory=dict)  # mode -> count


class MarketDataFeed(ABC):
    """Live (or replayed) market data. Subscriptions are declarative: pass the full
    wanted set and the adapter works out the diff."""

    name: str = "abstract"
    max_keys: Mapping[FeedMode, int] = {}

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def set_subscriptions(self, want: Mapping[InstrumentId, FeedMode]) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[MarketEvent]: ...

    @abstractmethod
    def health(self) -> FeedHealth: ...


class InstrumentMaster(ABC):
    """Daily reference data and the canonical ↔ native mapping."""

    venue: str = "abstract"

    @abstractmethod
    async def load(self, day: date, *, refresh: bool = False) -> int:
        """Load the master for `day`; returns the number of instruments."""

    @abstractmethod
    def get(self, iid: InstrumentId) -> Instrument: ...

    @abstractmethod
    def find(self, iid: InstrumentId) -> Instrument | None: ...

    @abstractmethod
    def from_native(self, native: str) -> InstrumentId | None: ...

    @abstractmethod
    def to_native(self, iid: InstrumentId) -> str: ...

    @abstractmethod
    def all(self) -> Iterable[Instrument]: ...
