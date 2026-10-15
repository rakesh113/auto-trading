"""Telegram commands for the owner (design §14): allow-listed chat, PIN, tighten-only.

    /status            positions and P&L (no PIN needed)
    /pause <PIN>       stop new entries for the rest of the session (exits continue)
    /flatten <PIN>     flatten every position and lock the day
    /help

There is deliberately no resume or "loosen" command: a pause lasts until the next
session. Messages carrying the PIN are deleted after reading. Every command is
written to the journal as a human override (audit log).
"""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Awaitable, Callable

import httpx
import structlog

log = structlog.get_logger(__name__)

Handler = Callable[[], Awaitable[str]]


class CommandBot:
    def __init__(self, *, token: str, chat_id: str, pin: str | None, status: Handler, pause: Handler,
                 flatten: Handler, audit: Callable[[str, bool], None],
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat = str(chat_id)
        self._pin = pin
        self._handlers = {"/status": (status, False), "/pause": (pause, True), "/flatten": (flatten, True)}
        self._audit = audit
        self._client = httpx.AsyncClient(timeout=40, transport=transport)
        self._offset = 0

    async def _send(self, text: str) -> None:
        try:
            await self._client.post(f"{self._base}/sendMessage", json={"chat_id": self._chat, "text": text})
        except httpx.HTTPError as e:
            log.warning("commands.reply_failed", error=repr(e))

    async def handle(self, msg: dict) -> None:
        chat = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat != self._chat or not text.startswith("/"):
            if chat != self._chat:
                log.warning("commands.foreign_chat", chat=chat)
            return
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        if cmd == "/help":
            await self._send("Commands: /status, /pause <PIN>, /flatten <PIN>. Tighten-only; no resume from phone.")
            return
        entry = self._handlers.get(cmd)
        if entry is None:
            await self._send(f"Unknown command {cmd}. Try /help.")
            return
        fn, needs_pin = entry
        if needs_pin:
            given = parts[1] if len(parts) > 1 else ""
            if msg.get("message_id"):
                try:  # don't leave the PIN in the chat history
                    await self._client.post(f"{self._base}/deleteMessage",
                                            json={"chat_id": self._chat, "message_id": msg["message_id"]})
                except httpx.HTTPError:
                    pass
            if not self._pin:
                await self._send("Commands are disabled: set TELEGRAM_COMMAND_PIN in .env.")
                self._audit(cmd, False)
                return
            if not hmac.compare_digest(given, self._pin):
                await self._send("Wrong PIN.")
                self._audit(cmd, False)
                return
        self._audit(cmd, True)
        await self._send(await fn())

    async def run(self) -> None:
        # skip anything sent while we were not running: stale commands must not act
        try:
            r = await self._client.get(f"{self._base}/getUpdates", params={"offset": -1, "timeout": 0})
            res = r.json().get("result") or []
            self._offset = res[-1]["update_id"] + 1 if res else 0
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        while True:
            try:
                r = await self._client.get(f"{self._base}/getUpdates",
                                           params={"offset": self._offset, "timeout": 25, "allowed_updates": '["message"]'})
                for upd in r.json().get("result") or []:
                    self._offset = upd["update_id"] + 1
                    if "message" in upd:
                        await self.handle(upd["message"])
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - keep polling
                log.warning("commands.poll_failed", error=repr(e))
                await asyncio.sleep(5)
