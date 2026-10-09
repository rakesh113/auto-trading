from __future__ import annotations

import json

import httpx

from trader.ops.commands import CommandBot

CHAT = "12345"


def make(pin: str | None):
    sent: list[str] = []
    deleted: list[int] = []
    audit: list[tuple[str, bool]] = []
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/sendMessage"):
            sent.append(json.loads(req.content)["text"])
        elif req.url.path.endswith("/deleteMessage"):
            deleted.append(json.loads(req.content)["message_id"])
        return httpx.Response(200, json={"ok": True, "result": []})

    async def act(name: str) -> str:
        calls.append(name)
        return f"done {name}"

    bot = CommandBot(token="t", chat_id=CHAT, pin=pin, status=lambda: act("status"), pause=lambda: act("pause"),
                     flatten=lambda: act("flatten"), audit=lambda c, ok: audit.append((c, ok)),
                     transport=httpx.MockTransport(handler))
    return bot, sent, deleted, audit, calls


def msg(text: str, chat: str = CHAT, mid: int = 7) -> dict:
    return {"chat": {"id": int(chat)}, "text": text, "message_id": mid}


async def test_pin_required_and_message_deleted() -> None:
    bot, sent, deleted, audit, calls = make("4321")
    await bot.handle(msg("/flatten 1111"))
    assert calls == [] and sent[-1] == "Wrong PIN." and deleted == [7] and audit == [("/flatten", False)]
    await bot.handle(msg("/flatten 4321", mid=8))
    assert calls == ["flatten"] and deleted == [7, 8] and audit[-1] == ("/flatten", True)


async def test_foreign_chat_ignored_and_status_without_pin() -> None:
    bot, sent, _d, _a, calls = make("4321")
    await bot.handle(msg("/pause 4321", chat="999"))
    assert calls == [] and sent == []
    await bot.handle(msg("/status"))
    assert calls == ["status"]


async def test_disabled_without_pin_configured() -> None:
    bot, sent, _d, audit, calls = make(None)
    await bot.handle(msg("/pause 1"))
    assert calls == [] and "disabled" in sent[-1]
