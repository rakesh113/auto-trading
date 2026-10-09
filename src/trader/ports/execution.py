"""The Trader port: where orders go. Paper and live venues implement the same contract.

Add a new venue by subclassing `Trader`, registering it, and passing the shared
conformance suite in `tests/contract/test_trader_conformance.py`::

    from trader.core.registry import traders

    @traders.register("mybroker")
    class MyBrokerTrader(Trader):
        caps = TraderCaps(live=True, ...)
        ...

then set `execution.venue: mybroker` in config. Nothing else changes.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from trader.domain.orders import ExecEvent, OrderAmend, OrderRequest, SubmitResult
from trader.domain.portfolio import BrokerSnapshot
from trader.domain.types import OrderType, Product

if TYPE_CHECKING:
    from trader.core.app import AppContext


@dataclass(frozen=True, slots=True)
class TraderCaps:
    """What a venue supports. Strategies declare `requires`; startup checks them (design §10)."""

    live: bool  # True if orders reach a real exchange
    order_types: frozenset[OrderType] = frozenset({OrderType.LIMIT, OrderType.SL})
    products: frozenset[Product] = frozenset({Product.INTRADAY, Product.DELIVERY})
    exchanges: frozenset[str] = frozenset({"NSE", "BSE"})
    sl_m_on_options: bool = False
    gtt_protects_position: bool = False  # Zerodha single-leg GTT can; Upstox cannot
    max_tag_len: int = 20
    extra: dict[str, object] = field(default_factory=dict)


class Trader(ABC):
    """Execution venue. All methods are idempotent on `client_order_id`.

    Semantics every implementation must honour:
      * `place` returning ok=True means *sent*, not *accepted*. Acceptance, rejection
        and fills arrive as `ExecEvent`s from `events()`.
      * A timeout must never be retried blindly; report state UNKNOWN and let the OMS
        reconcile through `snapshot()`.
      * `snapshot()` covers only orders this system placed (tag prefix), never manual
        or other-agent orders in the same account (design D13).
    """

    name: str = "abstract"
    caps: TraderCaps

    def __init__(self) -> None:
        self._events: asyncio.Queue[ExecEvent] = asyncio.Queue(maxsize=100_000)

    @classmethod
    @abstractmethod
    def build(cls, ctx: AppContext, settings: dict[str, Any]) -> Trader:
        """Construct from the app context and this venue's `execution.settings.<name>` block."""

    async def start(self) -> None:  # noqa: B027 - optional hook
        """Open sessions/streams. Called once by the app before trading."""

    async def stop(self) -> None:  # noqa: B027 - optional hook
        """Close sessions/streams. Must not cancel or flatten anything by itself."""

    @abstractmethod
    async def place(self, req: OrderRequest) -> SubmitResult: ...

    @abstractmethod
    async def modify(self, client_order_id: str, amend: OrderAmend) -> SubmitResult: ...

    @abstractmethod
    async def cancel(self, client_order_id: str) -> SubmitResult: ...

    @abstractmethod
    async def snapshot(self) -> BrokerSnapshot: ...

    async def margin_for(self, reqs: Sequence[OrderRequest]) -> int | None:
        """Required margin in paise, or None if the venue cannot say."""
        return None

    async def events(self) -> AsyncIterator[ExecEvent]:
        while True:
            yield await self._events.get()

    def _emit(self, ev: ExecEvent) -> None:
        self._events.put_nowait(ev)
