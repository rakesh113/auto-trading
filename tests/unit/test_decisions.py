from __future__ import annotations

import json

import httpx

from trader.intel.decisions import Choice, JevDecisionModel, Score, YesNo, decision_models

# Response shapes copied from live typesafe/jev-1.13 calls on 2026-10-09.
LIVE = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "material": {"type": "noul", "noul": 0.6},
        "direction": {"type": "choice", "choice": "up", "probabilities": {"up": 0.99, "down": 0, "none": 0.01},
                      "confidence": 0.98},
        "materiality": {"type": "score", "score": 0.87, "probabilities": {"0": 0.13, "1": 0.87},
                        "confidence": 0.74},
    },
    "usage": {"input_tokens": 362, "output_tokens": 38, "cost": 1.5e-05},
    "id": "gen-dec-1",
}


async def test_jev_request_and_answers(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    sent: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/alpha/decisions"
        sent.update(json.loads(req.content))
        return httpx.Response(200, json=LIVE)

    m = JevDecisionModel(transport=httpx.MockTransport(handler))
    res = await m.decide("filing text", {
        "material": YesNo("Is it material?"),
        "direction": Choice("Direction", {"up": "rises", "down": "falls", "none": "flat"}),
        "materiality": Score("How material", "routine", "transformational"),
    })
    assert sent["questions"]["material"] == {"type": "noul", "instructions": "Is it material?"}
    assert sent["questions"]["materiality"]["criteria"] == ["routine", "transformational"]
    assert res.answers["material"].value == 0.6
    assert res.answers["direction"].value == "up" and res.answers["direction"].confidence == 0.98
    assert res.answers["materiality"].value == 0.87
    assert res.cost_usd == 1.5e-05
    assert decision_models.get("jev") is JevDecisionModel
