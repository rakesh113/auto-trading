"""Composition root (design §10): the one place where config becomes objects.

    cfg = load_config("paper")
    app = build_app(cfg)
    await app.start()

Swapping a broker, feed or notifier is a config change: each is looked up by name in
its registry and constructed through the class's `build(ctx, ...)` hook.

Live guard: a trader whose `caps.live` is True is only built when *all* hold:
  1. profile is `live`;
  2. env `TRADER_LIVE_ARMED=yes` (set by the owner for the session, never in .env);
  3. the venue's own credentials are present (checked by its `build`).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from trader.core.clock import WallClock
from trader.core.config import CONFIG_DIR, AppConfig
from trader.core.registry import feeds, masters, notifiers, traders
from trader.domain.market import MarketEvent
from trader.ports.clock import Clock, today_ist
from trader.ports.execution import Trader
from trader.ports.infra import Notifier, NullRecorder, RawRecorder
from trader.ports.marketdata import InstrumentMaster, MarketDataFeed

log = structlog.get_logger(__name__)

LIVE_ARM_ENV = "TRADER_LIVE_ARMED"


class LiveTradingBlocked(RuntimeError):
    pass


@dataclass
class AppContext:
    """What adapters may use while being built."""

    cfg: AppConfig
    clock: Clock
    master: InstrumentMaster
    recorder: RawRecorder
    config_dir: Path = CONFIG_DIR
    live_armed: bool = False


@dataclass
class App:
    ctx: AppContext
    trader: Trader | None
    feed: MarketDataFeed | None
    notifier: Notifier
    listeners: list[Callable[[MarketEvent], None]] = field(default_factory=list)
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    @property
    def cfg(self) -> AppConfig:
        return self.ctx.cfg

    @property
    def master(self) -> InstrumentMaster:
        return self.ctx.master

    async def start(self, *, load_master: bool = True) -> None:
        if load_master:
            n = await self.master.load(today_ist(self.ctx.clock))
            log.info("app.master_loaded", instruments=n)
        if self.trader is not None:
            await self.trader.start()
            on_market = getattr(self.trader, "on_market", None)
            if on_market is not None:  # paper venues fill against the live book
                self.listeners.append(on_market)
        if self.feed is not None:
            await self.feed.start()
            self._tasks.append(asyncio.create_task(self._pump(), name="market-pump"))

    async def _pump(self) -> None:
        assert self.feed is not None
        async for ev in self.feed.events():
            for fn in self.listeners:
                try:
                    fn(ev)
                except Exception:  # noqa: BLE001 - one bad listener must not stop the data
                    log.exception("app.listener_failed", listener=getattr(fn, "__qualname__", fn))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.feed is not None:
            await self.feed.stop()
        if self.trader is not None:
            await self.trader.stop()
        self.ctx.recorder.close()


def check_live_guard(cfg: AppConfig, trader_cls: type[Trader]) -> bool:
    """Return True if a live venue may be built; raise if it was asked for but not armed."""
    if not trader_cls.caps.live:
        return False
    problems = []
    if cfg.profile != "live":
        problems.append(f"profile is {cfg.profile!r}, not 'live'")
    if os.environ.get(LIVE_ARM_ENV) != "yes":
        problems.append(f"{LIVE_ARM_ENV}=yes is not set for this session")
    if problems:
        raise LiveTradingBlocked(f"venue {cfg.execution.venue!r} sends real orders; refused: " + "; ".join(problems))
    return True


def build_app(
    cfg: AppConfig,
    *,
    clock: Clock | None = None,
    recorder: RawRecorder | None = None,
    with_feed: bool = True,
    with_trader: bool = True,
    config_dir: Path = CONFIG_DIR,
) -> App:
    clock = clock or WallClock()
    master_cls = masters.get(cfg.instruments.provider)
    ctx = AppContext(cfg=cfg, clock=clock, master=None, recorder=recorder or NullRecorder(),  # type: ignore[arg-type]
                     config_dir=config_dir)
    ctx.master = master_cls.build(ctx)

    trader: Trader | None = None
    if with_trader:
        trader_cls = traders.get(cfg.execution.venue)
        ctx.live_armed = check_live_guard(cfg, trader_cls)
        trader = trader_cls.build(ctx, cfg.venue_settings())
        log.info("app.trader", venue=cfg.execution.venue, live=trader_cls.caps.live)

    feed = feeds.get(cfg.feed.provider).build(ctx) if with_feed else None

    ncls = notifiers.get(cfg.notifier.provider)
    notifier = ncls(**cfg.notifier.settings.get(cfg.notifier.provider, {}))
    return App(ctx=ctx, trader=trader, feed=feed, notifier=notifier)
