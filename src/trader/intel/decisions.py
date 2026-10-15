"""TextDecisionModel port and the Jev adapter (design §7.3, §9).

A decision model answers typed questions about a piece of text (a filing, a news item)
and returns calibrated-looking probabilities instead of prose. Three question types:

* ``YesNo``   → probability of "yes" (Jev calls this type ``noul``)
* ``Choice``  → one label from a fixed set, with per-label probabilities
* ``Score``   → position between two anchored ends, 0..1

Jev is served by OpenRouter on its alpha decisions endpoint, not chat/completions
(verified 2026-10-09 with ``typesafe/jev-1.13``: 0.5-1 s, ~$0.000015 per call).
Scraped text is passed as untrusted `state`; the model has no tools (design §9).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from trader.core.config import secret
from trader.core.registry import Registry


@dataclass(frozen=True, slots=True)
class YesNo:
    instructions: str


@dataclass(frozen=True, slots=True)
class Choice:
    instructions: str
    options: dict[str, str]  # label -> what it means


@dataclass(frozen=True, slots=True)
class Score:
    instructions: str
    low: str  # meaning of 0
    high: str  # meaning of 1


Question = YesNo | Choice | Score


@dataclass(frozen=True, slots=True)
class Answer:
    kind: str  # "yesno" | "choice" | "score"
    value: float | str  # P(yes), chosen label, or score in 0..1
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class DecisionResult:
    model: str
    answers: dict[str, Answer]
    cost_usd: float | None
    latency_ms: float
    request_id: str = ""


class TextDecisionModel(ABC):
    name: str = "abstract"

    @abstractmethod
    async def decide(self, state: str, questions: dict[str, Question], *, timeout_s: float = 8.0
                     ) -> DecisionResult: ...


decision_models: Registry[Any] = Registry("decision model", "trader.decision_models",
                                          {"jev": "trader.intel.decisions"})


def _encode(q: Question) -> dict[str, Any]:
    if isinstance(q, YesNo):
        return {"type": "noul", "instructions": q.instructions}
    if isinstance(q, Choice):
        return {"type": "choice", "instructions": q.instructions, "criteria": dict(q.options)}
    return {"type": "score", "instructions": q.instructions, "criteria": [q.low, q.high]}


def _decode(raw: dict[str, Any]) -> Answer:
    t = raw.get("type")
    if t == "noul":
        return Answer("yesno", float(raw["noul"]), confidence=raw.get("confidence"))
    if t == "choice":
        return Answer("choice", str(raw["choice"]), dict(raw.get("probabilities") or {}), raw.get("confidence"))
    if t == "score":
        return Answer("score", float(raw["score"]), dict(raw.get("probabilities") or {}), raw.get("confidence"))
    raise ValueError(f"unknown answer type {t!r}")


@decision_models.register("jev")
class JevDecisionModel(TextDecisionModel):
    def __init__(self, *, model: str = "typesafe/jev-1.13", api_key_env: str = "OPENROUTER_API_KEY",
                 base_url: str = "https://openrouter.ai/api/alpha",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30, transport=transport,
                                         headers={"Authorization": f"Bearer {secret(api_key_env)}"})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def decide(self, state: str, questions: dict[str, Question], *, timeout_s: float = 8.0
                     ) -> DecisionResult:
        body = {"model": self.model, "state": state, "questions": {k: _encode(q) for k, q in questions.items()}}
        t0 = time.perf_counter()
        r = await self._client.post("/decisions", json=body, timeout=timeout_s)
        r.raise_for_status()
        d = r.json()
        answers = {k: _decode(v) for k, v in (d.get("answers") or {}).items()}
        missing = set(questions) - set(answers)
        if missing:
            raise ValueError(f"decision model skipped questions: {sorted(missing)}")
        return DecisionResult(model=d.get("model", self.model), answers=answers,
                              cost_usd=(d.get("usage") or {}).get("cost"),
                              latency_ms=(time.perf_counter() - t0) * 1000, request_id=d.get("id", ""))
