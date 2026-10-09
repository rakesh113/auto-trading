"""Infrastructure ports: raw recorder and notifier."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum


class RawRecorder(ABC):
    """Append-only store of raw venue frames. `write` must never block the caller."""

    @abstractmethod
    def write(self, stream: str, kind: int, ts_recv_ns: int, payload: bytes) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class NullRecorder(RawRecorder):
    def write(self, stream: str, kind: int, ts_recv_ns: int, payload: bytes) -> None:
        pass

    def close(self) -> None:
        pass


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class Notifier(ABC):
    @abstractmethod
    async def notify(self, text: str, severity: Severity = Severity.INFO) -> None: ...
