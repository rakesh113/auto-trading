"""Keep the machine awake while it is recording or trading (design §10, laptop operation).

Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED). The request lasts
while the calling thread lives, so the context manager holds it for the whole block.
macOS/Linux: no-op here; use `caffeinate` / `systemd-inhibit` in the launcher.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


@contextmanager
def keep_awake() -> Iterator[bool]:
    if sys.platform != "win32":
        yield False
        return
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    ok = bool(k32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED))
    try:
        yield ok
    finally:
        k32.SetThreadExecutionState(ES_CONTINUOUS)
