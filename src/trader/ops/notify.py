"""Notifiers: log (default) and Telegram (alerts only; commands come later, tighten-only)."""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from trader.core.config import secret
from trader.core.registry import notifiers
from trader.ports.infra import Notifier, Severity

log = structlog.get_logger(__name__)


@notifiers.register("log")
class LogNotifier(Notifier):
    def __init__(self, **_: object) -> None:
        pass

    async def notify(self, text: str, severity: Severity = Severity.INFO) -> None:
        log.log({"INFO": 20, "WARN": 30, "CRITICAL": 50}[severity.value], "notify", text=text)


@notifiers.register("telegram")
class TelegramNotifier(Notifier):
    def __init__(self, *, token_env: str = "TELEGRAM_BOT_TOKEN", chat_id_env: str = "TELEGRAM_CHAT_ID",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = f"https://api.telegram.org/bot{secret(token_env)}/sendMessage"
        self._chat = secret(chat_id_env)
        self._client = httpx.AsyncClient(timeout=10, transport=transport)

    async def notify(self, text: str, severity: Severity = Severity.INFO) -> None:
        prefix = {"INFO": "", "WARN": "⚠️ ", "CRITICAL": "🛑 "}[severity.value]
        try:
            r = await self._client.post(self._url, json={"chat_id": self._chat, "text": prefix + text})
            r.raise_for_status()
        except httpx.HTTPError as e:  # alerts must never take the system down
            log.error("telegram.failed", error=repr(e), text=text)

    async def send_document(self, path: Path, caption: str = "") -> None:
        url = self._url.replace("/sendMessage", "/sendDocument")
        try:
            with open(path, "rb") as fh:
                r = await self._client.post(url, data={"chat_id": self._chat, "caption": caption[:1000]},
                                            files={"document": (path.name, fh, "text/html")}, timeout=60)
            r.raise_for_status()
        except (httpx.HTTPError, OSError) as e:
            log.error("telegram.document_failed", error=repr(e), path=str(path))
