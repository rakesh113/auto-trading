"""structlog setup: human-readable console, JSON lines in <data_dir>/logs/."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(level: str = "INFO", log_dir: Path | None = None, name: str = "trader") -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / f"{name}.jsonl", encoding="utf-8"))
    logging.basicConfig(level=level, handlers=[], force=True)
    root = logging.getLogger()
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )
    for i, h in enumerate(handlers):
        renderer = structlog.dev.ConsoleRenderer(colors=False) if i == 0 else structlog.processors.JSONRenderer()
        h.setFormatter(structlog.stdlib.ProcessorFormatter(
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.processors.format_exc_info, renderer],
            foreign_pre_chain=shared,
        ))
        root.addHandler(h)
    for noisy in ("httpx", "httpcore", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
