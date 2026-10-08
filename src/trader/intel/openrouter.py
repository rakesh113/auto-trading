"""OpenRouter LLM provider: one key for every model (owner decision, design §9).

Minimal for Phase 0: chat completion with optional JSON-schema structured output,
token/cost accounting and a timeout. Agents, budget guard and call recording come
in Phase 1.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from trader.core.config import secret
from trader.core.registry import llm_providers


@dataclass(frozen=True, slots=True)
class LLMResult:
    model: str
    text: str
    parsed: Any | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    latency_ms: float


@llm_providers.register("openrouter")
class OpenRouterProvider:
    def __init__(self, *, api_key_env: str = "OPENROUTER_API_KEY", base_url: str = "https://openrouter.ai/api/v1",
                 app_name: str = "auto-trading", transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {secret(api_key_env)}", "X-Title": app_name},
            timeout=60,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(self, model: str, messages: list[dict[str, str]], *, schema: dict[str, Any] | None = None,
                       max_tokens: int = 1024, temperature: float = 0.0, timeout_s: float = 30.0) -> LLMResult:
        body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens,
                                "temperature": temperature, "usage": {"include": True}}
        if schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "output", "strict": True, "schema": schema}}
        t0 = time.perf_counter()
        r = await self._client.post("/chat/completions", json=body, timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        parsed = None
        if schema is not None:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        return LLMResult(model=data.get("model", model), text=text, parsed=parsed,
                         prompt_tokens=int(usage.get("prompt_tokens", 0)),
                         completion_tokens=int(usage.get("completion_tokens", 0)),
                         cost_usd=usage.get("cost"), latency_ms=(time.perf_counter() - t0) * 1000)
