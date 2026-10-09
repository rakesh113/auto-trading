from __future__ import annotations

import json

import httpx

from trader.intel.openrouter import OpenRouterProvider, extract_json


def test_extract_json_tolerates_fences_and_prose() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure. {"material": true} hope that helps') == {"material": True}
    assert extract_json('{"material": true,') is None  # truncated
    assert extract_json("no json here") is None


async def test_generate_disables_reasoning_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": '{"x": 1}'}}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.0001}})

    p = OpenRouterProvider(transport=httpx.MockTransport(handler))
    r = await p.generate("m", [{"role": "user", "content": "hi"}], schema={"type": "object"})
    assert seen["reasoning"] == {"enabled": False} and seen["response_format"]["type"] == "json_schema"
    assert r.parsed == {"x": 1} and r.cost_usd == 0.0001
