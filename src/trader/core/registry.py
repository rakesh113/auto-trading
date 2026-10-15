"""Plugin registries: adapters register by name, config picks them by name.

Built-ins register with a decorator when their module is imported. Third-party
packages can add more through entry points (group = registry's `group`), so a new
broker can be shipped as a separate package without editing this repository.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from importlib.metadata import entry_points
from typing import Any


class Registry[T]:
    def __init__(self, kind: str, group: str, builtins: dict[str, str]) -> None:
        self.kind = kind
        self.group = group
        self._builtins = builtins  # name -> module that registers it (imported lazily)
        self._items: dict[str, type[T]] = {}

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        def deco(cls: type[T]) -> type[T]:
            existing = self._items.get(name)
            if existing is not None and existing is not cls:
                raise ValueError(f"{self.kind} {name!r} already registered by {existing}")
            self._items[name] = cls
            cls.name = name  # type: ignore[attr-defined]
            return cls

        return deco

    def get(self, name: str) -> type[T]:
        if name not in self._items and name in self._builtins:
            import_module(self._builtins[name])
        if name not in self._items:
            for ep in entry_points(group=self.group):
                if ep.name == name:
                    self._items[name] = ep.load()
                    break
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"unknown {self.kind} {name!r}; known: {sorted(self.names())}") from None

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        return self.get(name)(*args, **kwargs)

    def names(self) -> set[str]:
        return set(self._items) | set(self._builtins) | {ep.name for ep in entry_points(group=self.group)}


traders: Registry[Any] = Registry(
    "trader",
    "trader.traders",
    {"paper": "trader.adapters.paper.trader", "upstox": "trader.adapters.upstox.trader"},
)
feeds: Registry[Any] = Registry(
    "feed", "trader.feeds",
    {"upstox": "trader.adapters.upstox.feed", "local": "trader.adapters.local.feed"},
)
masters: Registry[Any] = Registry(
    "instrument master", "trader.masters", {"upstox": "trader.adapters.upstox.instruments"}
)
notifiers: Registry[Any] = Registry(
    "notifier", "trader.notifiers", {"log": "trader.ops.notify", "telegram": "trader.ops.notify"}
)
llm_providers: Registry[Any] = Registry(
    "llm provider", "trader.llm", {"openrouter": "trader.intel.openrouter"}
)
