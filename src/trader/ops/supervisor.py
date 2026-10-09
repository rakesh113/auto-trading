"""Tiny process supervisor for the laptop (design §10): start children, restart on crash.

Run at logon by Windows Task Scheduler (deploy/windows/install-tasks.ps1). Each child is
a `trader` sub-command; a child that exits is restarted with exponential backoff
(reset after it has stayed up for 10 minutes).
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


@dataclass
class Child:
    name: str
    args: list[str]
    proc: subprocess.Popen[bytes] | None = None
    started: float = 0.0
    backoff: float = 2.0
    restarts: int = 0
    next_start: float = field(default=0.0)


def supervise(children: dict[str, list[str]], *, poll_s: float = 2.0) -> None:
    kids = [Child(n, a) for n, a in children.items()]
    try:
        while True:
            now = time.monotonic()
            for k in kids:
                if k.proc is not None and k.proc.poll() is not None:
                    up = now - k.started
                    log.warning("supervisor.child_exited", child=k.name, code=k.proc.returncode, up_s=round(up))
                    k.proc = None
                    if up > 600:
                        k.backoff = 2.0
                    k.next_start = now + k.backoff
                    k.backoff = min(k.backoff * 2, 300.0)
                    k.restarts += 1
                if k.proc is None and now >= k.next_start:
                    cmd = [sys.executable, "-m", "trader.apps.cli", *k.args]
                    k.proc = subprocess.Popen(cmd)  # noqa: S603 - fixed argv, no shell
                    k.started = now
                    log.info("supervisor.started", child=k.name, pid=k.proc.pid, cmd=" ".join(k.args))
            time.sleep(poll_s)
    except KeyboardInterrupt:
        pass
    finally:
        for k in kids:
            if k.proc is not None and k.proc.poll() is None:
                k.proc.terminate()
                try:
                    k.proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    k.proc.kill()
