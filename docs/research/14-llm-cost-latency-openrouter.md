# LLM systems and cost engineering: running the LLM trader on Rs 5–7k a month through OpenRouter

## 0. Bottom line

1. **The budget is enough.** The Target profile below runs a Sonnet 5.5 trader on 60 moments a day, plus three cheap paired arms, Opus 5.5 pre-market plans and full management. It costs **about Rs 6,650 a month including 15% contingency.** Lean costs about Rs 4.0k and Stretch about Rs 10.6k.
2. **Haiku 5.5 is the cheapest useful model available.** It costs $0.10 in and $0.50 out per million tokens, which is 27× cheaper per decision than Sonnet. A full Haiku arm on every moment costs about Rs 70 a month. The cheap OpenRouter alternatives are only worth having for vendor diversity; none of them saves money.
3. **The biggest cost risk is uncontrolled thinking, not call volume.** Sonnet 5.5 defaults to effort `high`. If OpenRouter does not pass `effort: low` through, Target rises by about Rs 4.6k. If prompt caching does not pass through, it rises by about Rs 2.2k. **Both must be verified in Phase 0.**
4. **Latency should decide the entry design.** A Sonnet decision with thinking takes about 6–10 s. If the system confirms only when the trigger fires, fast breakouts (the winners) run away and slow ones (more often losers) fill. Make the decision **when price approaches the trigger, then execute on the trigger.**
5. **Charts are cheap:** 900 tokens is Rs 0.18 on Sonnet and Rs 0.009 on Haiku. So whether to use them is purely a quality question. Test them as a paired arm; it is nearly free on Haiku. Default decisions stay numeric-first, and charts are always included in the pre-market plan. [J]

## 1. Verified prices and OpenRouter mechanics

**Claude prices (USD per MTok).** Source: Anthropic's pricing page, fetched today [H]. OpenRouter passes these through at the same rates [M, based on aggregator listings, because openrouter.ai is blocked from this sandbox].

| Model | Input | Cache write 5m / 1h | Cache read | Output | Batch |
|---|---|---|---|---|---|
| Fable 5.1 | 10 | 12.50 / 20 | 0.25 | 50 | 5 / 25 |
| Opus 5.5 | 4 | 5 / 8 | **0.20 (0.05×)** | 20 | 2 / 10 |
| Sonnet 5.5 | 2 | 2.50 / 4 | **0.10 (0.05×)** | 10 | 1 / 5 |
| Haiku 5.5 (prompts ≤100k tokens) | 0.10 | 0.125 / 0.20 | 0.01 | 0.50 | 0.05 / 0.25 |

- **Haiku 5.5 prompts over 100k tokens** cost 5× more ($0.50 in, $2.50 out). Keep every Haiku prompt under 100k [H].
- **Minimum cacheable prefix** on the 5.x models is 512 tokens; there are at most 4 breakpoints [H].
- **Tokenizer:** the newer models count about 30% more tokens than the old tokenizer for the same text, so "characters ÷ 4" estimates undercount [H].
- **Tool overhead:** using tools adds 286 tokens per call on the 5.5 models [H].
- **Behaviour on the 5.5 models** [H, bundled claude-api reference]:
  - Opus 5.5 thinking cannot be disabled; its default effort is `medium`.
  - Sonnet 5.5 defaults to effort `high`, and `{type: disabled}` returns an error. Thinking can only be turned off with `between_tools`.
  - Haiku 5.5 has thinking on by default, at default effort `medium`.
  - Non-default sampling parameters are rejected on all three, so temperature cannot be fixed.
- **Correction:** the bundled skill text gives Sonnet 5.5 cache reads as $0.20. Anthropic's pricing page says **$0.10**; use the pricing page.

**Image tokens** [H, Anthropic vision docs]: tokens = ⌈w/28⌉ × ⌈h/28⌉. Claude 4.7 and later use the high-resolution tier (up to 2576 px on the long edge and 4,784 tokens). The 5.5 models are assumed to be in that tier [M].

| Chart size | Tokens | Opus | Sonnet | Haiku |
|---|---|---|---|---|
| 800×500 | 522 | Rs 0.21 | Rs 0.10 | Rs 0.005 |
| **1000×700 (recommended)** | **900** | Rs 0.36 | Rs 0.18 | Rs 0.009 |
| 1280×720 | 1,196 | Rs 0.48 | Rs 0.24 | Rs 0.012 |
| 1456×816 | 1,560 | Rs 0.63 | Rs 0.31 | Rs 0.016 |

**OpenRouter mechanics** (all [M]: from OpenRouter docs and secondary sources found by search; the pages themselves could not be fetched):
- **Prompt caching.**
  - Top-level automatic `cache_control` routes only to Anthropic's own endpoint, not Bedrock or Vertex.
  - Block-level breakpoints (max 4) also work on Bedrock and Vertex. **Use block-level breakpoints** so failover to Bedrock or Vertex stays possible.
  - OpenRouter uses sticky routing so follow-up calls hit the provider that holds the cache.
  - Whether the 1-hour TTL passes through is unverified [L].
- **Structured outputs:** `response_format: {type: "json_schema", strict: true}` plus `provider.require_parameters: true`. Support is decided per endpoint. Anthropic structured outputs cover Sonnet 4.5+ and Opus 4.1+, so the 5.x models are covered.
- **Response-healing plugin:** repairs malformed JSON. It works only on non-streaming calls and cannot fix output cut off by `max_tokens`.
- **Reasoning control:** `reasoning.effort` maps to Anthropic's `output_config.effort` on Claude 4.6+ (doc update of June 2026, seen on mirrors). `effort: "none"` disables reasoning. On Sonnet 5.5 that may produce a 400 error, because Sonnet 5.5 rejects `disabled` [L].
- **Fees:** 5.5% on credit purchases and no markup on inference. Low credit balances add latency, so keep a cushion. Paid rate limits are about 1 request per second per credit, up to a surge ceiling of about 500 requests per second; this is not a constraint for us.
- **Batch:** no batch discount through OpenRouter is assumed [L]. EOD jobs are budgeted at full price.
- **Exchange rate:** Rs 95/USD × 1.055 (OpenRouter fee) ≈ **Rs 100 per list-price dollar.** Card forex markup may add another 2–4%, which the contingency absorbs.

**Cheap alternatives on OpenRouter:**

| Model | Price in/out $/MTok | JSON schema | Images | Use | Confidence |
|---|---|---|---|---|---|
| Qwen3.5-Flash (`qwen/qwen3.5-flash-02-23`) | 0.065 / 0.26 | per endpoint | yes | triage bake-off entrant | M |
| GPT-5.6 Luna | 0.20 / 1.20 (cut 80% on 30 Jul) | yes | yes | **cross-vendor decision arm** | M |
| DeepSeek V4.1 Flash | 0.30 / 1.20 on the main listing (0.15 / 0.60 on the dated slug); cache read 0.006 | per endpoint; ignored `response_format` in Phase 0 when served via the Jev router | text | text-only cheap arm | M/L |
| Gemini 3.1 Flash-Lite / 3.7 Flash | 0.25 / 1.50 and 0.75 / 3.75 | yes | yes | spare | L |

Haiku 5.5 is cheaper than all of them except Qwen Flash. The case for alternatives is **decorrelated errors** (a different vendor as a second opinion), not cost. [J]

## 2. Token budgets per call type

The shared static prefix is about 6k tokens: system prompt, playbook, tactic menu, packet field dictionary, schema and 3 worked examples. It is cached with a 1-hour TTL, and the decision and management routes share it. Costs below are Rs per call.

| Call | Model / effort | Input (cached + variable) | Output incl. thinking | Rs/call |
|---|---|---|---|---|
| Pre-market plan (index + 8 stocks, 9 charts) | Opus 5.5, medium; fan-out | 36k + 8.1k image | 14k | 45.7 (Sonnet: 20.9) |
| 09:12 refresh with pre-open data | Sonnet low | 9k | 2.5k | 4.3 |
| In-play candidate ranking (×30) | Haiku, reasoning off | 1.5k | 150 | 0.02 |
| Filing triage | Haiku, reasoning off | 2.5k cached + 1.2k | 150 | 0.022 |
| Materiality (focus or position symbols only) | Sonnet low / Haiku medium | 6k | 2k / 1.2k | 3.2 / 0.12 |
| **Decision at a moment** | Sonnet low | 6k + 3k | 850 (about 350 visible) | **1.51** (with chart 1.74) |
| Decision, cheap arm | Haiku, reasoning off | 6k + 3k | 400 | 0.056 (with chart 0.065) |
| Decision, high-stakes second opinion | Opus | 6k + 3.5k + chart | 1.5k | 4.9 |
| Cross-vendor arm | Luna / DeepSeek | 6k + 3k | 600 | 0.14 / 0.17 |
| Position management | Sonnet low / Haiku | 6k + 2k | 550 / 300 | 1.01 / 0.04 |
| Per-trade EOD review | Haiku | 8k | 1.5k | 0.16 |
| EOD synthesis | Sonnet / Opus | 30k | 5–6k | 11.0 / 24.1 |
| Weekly lessons | Opus | 80k | 16k | 64 |

**Decision output schema:** keep the output to about 200–350 visible tokens, because output tokens drive both cost and latency.

```
{action: TAKE|PASS|WAIT, side, tactic_id, entry_level_id, stop_level_id, target_level_ids[],
 size_tier: 0|25|50|100 (% of plan max R), valid_for_s, thesis_break: [{type, level_id|value}],
 confidence: 0-100, reason_codes: [≤3 packet-field refs]}
```

**Prompt layout**, chosen so that caching works:
- **Breakpoint 1** (1-hour TTL): the static prefix.
- **Variable tail**:
  - the chart, if any, placed before the text (Anthropic recommends image-then-text) [H];
  - the symbol's plan card (about 1k);
  - the moment packet: trigger, levels table with IDs, the last 30 one-minute bars as compact CSV (about 400 tokens), VWAP and RVOL, a top-5/30-level depth summary, Nifty and sector, news flags;
  - the risk state: open risk, remaining daily loss limit, trades today.
- Risk state and timestamps are never placed in the cached part.

## 3. Monthly cost model

Assumptions: 21 trading days; Opus weekly lessons ×4.3 a month; 1-hour prefix rewrites about 7 times a day per model. Rs per month:

| Line | Lean | Target | Stretch |
|---|---|---|---|
| Pre-market plan + refresh | Sonnet: 442 | Opus + Sonnet: 1,052 | 1,052 |
| Ranking + triage (Haiku; 300 / 400 / 400 items a day) | 153 | 199 | 204 |
| Materiality | Haiku 10/day: 25 | Sonnet 6 + Haiku 10: 429 | Sonnet 10 + Haiku 10: 699 |
| **Primary decisions (Sonnet)** | 50/day: 1,589 | 60/day: 1,907 | 80/day: 2,543 |
| Paired arms | Haiku numeric + Haiku chart, 100% of moments: 127 | Haiku numeric + chart 100%; Sonnet-chart 33%; Luna 33%: 946 | Haiku ×2; Sonnet-chart 50%; Luna 100%; Opus 5/day; self-consistency votes: 2,459 |
| Management | Sonnet 8 + Haiku 25: 192 | Sonnet 15 + Haiku 20: 336 | Sonnet 35 + Haiku 10: 753 |
| 1-hour cache writes | 372 | 372 | 675 |
| EOD + weekly | 541 | 547 | 820 (Opus EOD) |
| **Total incl. 15% contingency** | **≈ 3,960** | **≈ 6,650** | **≈ 10,580** |

The contingency also serves as the research and replay bucket. Prompt development runs on Haiku replays (1,000 moments ≈ Rs 56); Sonnet validation on 300 moments costs about Rs 450.

Lean lands below the Rs 4–5k band. The spare room should go to more Sonnet moments, not new agents. [J]

**Sensitivities (Target):**

| Scenario | Effect |
|---|---|
| Sonnet thinks at default effort `high` (about 2.5k tokens) | +Rs 4.6k |
| Caching does not pass through OpenRouter | +Rs 2.2k |
| 80 moments a day instead of 60 | +Rs 730 |
| Switch the primary trader from Sonnet to Haiku | −Rs 2.1k |

**Paired arms: marginal Rs per month at 60 moments a day (100% / 33% sampled):**

| Arm | 100% | 33% |
|---|---|---|
| Haiku | 71 | 23 |
| Haiku + chart | 82 | 27 |
| Luna | 182 | 60 |
| DeepSeek | 209 | 69 |
| Sonnet + chart | 2,197 | 725 |
| Opus | 6,163 | 2,034 |

How to fit paired arms inside the budget:
- **Sample the expensive arms** at random, by a hash of the moment ID.
- **Run cheap arms on 100% of moments.**
- **Score arms on the disagreement set only** (a McNemar-style comparison). Every arm's decision is simulated by the paper broker using tick-recorder data, so no arm needs real capital. At about 15% disagreement, 60 moments a day gives about 190 informative moments a month. [J]
- **One call can feed several books.** From each single decision record, derive:
  - **B1, LLM trader:** LLM tactic, LLM size tier, LLM management.
  - **B2, rules-propose / LLM-approve:** the rule's default tactic at fixed size, executed only if the LLM says TAKE.
  - **B3, LLM selects, rules exit.**
  - **B0, rules-only control.**

  B2 and B3 cost nothing extra, and the comparison separates the value of selection, tactic and management. Only different inputs or models (chart, model, vendor) need a second call. [J]

## 4. Latency

These are estimates [J] unless noted. Known data points:
- Phase 0 measured Haiku at about 2 s for a small call [H; one sample].
- An aggregator lists Sonnet-5.x speed at about 89 tokens/s with time to first token about 0.9 s [L].
- The route from India through OpenRouter (Cloudflare edge) to a US provider adds about 0.3–0.6 s with connection reuse. A cold edge cache can add delay for 1–2 minutes [M].

| Call | p50 | p95 | Hard timeout | On timeout or failure |
|---|---|---|---|---|
| Triage (Haiku) | 1.5–2 s | 4 s | 6 s | 1 retry, then the symbol stays FRESH_UNASSESSED (blackout) |
| Decision on approach (Sonnet low) | 6–10 s | 15–20 s | 25 s | nothing armed; on trigger, use the confirm path or skip |
| Decision on trigger (Haiku, or Sonnet with no thinking) | 2–3 s / 3.5–5 s | 5 s / 8 s | 6 s / 10 s | PASS (fail closed) |
| Management (Sonnet / Haiku) | 4–7 s / 2 s | 12 s / 4 s | 15 s / 6 s | broker stop stays; apply the plan's default management rule |
| Pre-market plan (9 parallel calls on a cached shared prefix) | 1–2 min wall time | 6 min | done by 09:05 | fall back to Sonnet, else a rules-only day for LLM books |

**Three entry modes:**
1. **ARMED:** the scenario was approved in the plan or refresh within the last 30 minutes and still passes deterministic validity checks. Code enters on the trigger with zero LLM latency. The LLM gets a post-fill keep/abort call within 60 s.
2. **APPROACH (the default):** the call fires when price comes within about 0.3 ATR of the trigger, or the setup starts forming. The answer arms an order valid for up to 5 minutes. LLM latency is hidden.
3. **CONFIRM:** only for setups that resolve on a bar close (reversals, fades, VWAP reclaim). A chase guard applies: if price is more than 0.25 × the stop distance past the trigger when the answer arrives, convert to a retest limit valid 3 minutes, or skip.

Log **decision-latency slippage** per book.

**Outages:**
- **Circuit breaker:** opens after 3 consecutive failures, more than 20% errors in 2 minutes, or p95 above 2× budget. A tiny Haiku probe every 60 s tests recovery.
- **Same-model provider failover** (Anthropic, then Bedrock, then Vertex, via OpenRouter provider routing) is allowed; it costs a cache miss.
- **Switching to a different model is never allowed for entries,** because it would contaminate the arms. It is allowed for management (Sonnet, then Haiku, then deterministic rules).
- **If OpenRouter is fully down:** LLM books stop opening trades. Open positions run on broker-side stops, the plan's default trailing rule and time flattens. Telegram alerts, and the arena tags those days.
- A dormant direct-Anthropic break-glass key is an owner decision. It stays off by default, since all LLM calls go through OpenRouter.

## 5. Determinism and quality controls

- **Schema enforcement:** strict structured outputs + `require_parameters` + response healing → Pydantic validation → semantic validators (every level ID resolves; stop, entry and targets correctly ordered; net R:R ≥ 1.5; size tier ≤ plan maximum) → one repair attempt (violations appended) → otherwise PASS.
  - Claude's schemas ignore `minimum`/`maximum` [M, report 05], so those limits are enforced in code.
  - Any arm with more than 5% schema failures in a week is fixed or cut.
- **Measure non-determinism, since it cannot be removed** (temperature is locked on the 5.5 models [H]). Weekly, re-run 50 logged moments 3 times each.
  - Action flips should stay under 10%.
  - Any moment class above 25% flips is treated as a PASS zone.
- **Self-consistency, only for high-stakes calls:** options buys, size ≥ 0.5R, overnight swing or MCX positional, or confidence between 40 and 65. Use 2 extra Haiku votes (Rs 0.11) or 1 extra Sonnet (Rs 1.5).
  - Run it in shadow first.
  - Use it for sizing ("split vote → half size") only after agreement is shown to predict outcomes over at least 100 moments.
- **Cache hygiene:**
  - Keep the prefix frozen: no timestamps, sorted JSON keys, fixed tool order.
  - Read cached-token counts from every response.
  - Alert if the decision route's cache-hit share of input falls below 70%.
- **Deduplication:**
  - Memoize exact requests by hash.
  - Fingerprint each moment as (symbol, scenario, trigger type, side, price bucket of 0.2 ATR, 3-minute bucket). A repeat within 10 minutes reuses a prior PASS unless the delta gate fires.
  - 3-minute cooldown per symbol; at most 8 decisions per symbol per day; a global cap per profile.
  - Expected saving: 20–35% of raw triggers. [J]
- **Concurrency:** at most 6 calls in flight. Priority order: management, then entry decisions, then focus-symbol triage, then everything else.

## 6. Budget governance

- **Caps (Target):**
  - Monthly hard cap Rs 7,000.
  - Daily soft cap = (remaining monthly budget − weekly reserve) ÷ remaining trading days, about Rs 300.
  - Daily hard cap 1.4× the soft cap.
  - Per-route sub-budgets: decisions 45%, plan 16%, paired arms 14%, management 6%, triage and materiality 9%, review 10%.
  - Separate OpenRouter keys for live, research/replay and EOD, each with a credit limit as a hard backstop [M].
  - Keep the OpenRouter balance at $15 or more, because low balances add latency.
- **Degrade ladder:**

| Level | Trigger | Action |
|---|---|---|
| L1 | 70% of daily cap, or month-to-date pace over 110% | Turn off the Sonnet-chart and Luna arms; per-trade reviews on Haiku only |
| L2 | 85% | Non-focus decisions move to Haiku; cap decisions at 40 a day; materiality only for open positions |
| L3 | 100% | No new LLM entries; open positions managed by Haiku; the rules control book continues |
| L4 | 120%, or OpenRouter balance under $5 | LLM off; deterministic management only |

- **Telemetry for every call:** route, book or arm, model and provider served, prompt version, tokens (input, cache read, cache write, output, reasoning, image), cost from OpenRouter's `usage`, time to first token and total latency, schema result, moment ID, trade ID. Reconcile daily against OpenRouter credits.
- **Dashboard metrics:**
  - Rs per decision, Rs per TAKE, Rs per closed trade.
  - LLM cost as % of each book's gross paper P&L.
  - **Value-add ROI** = (LLM book net P&L − control book net P&L) ÷ LLM cost.
  - Cache-hit share, p95 latency, timeout %, flip rate, deduplication savings.
- **The hurdle the owner should know:** Rs 6.65k a month is **about 8% a year of Rs 10L.** Per trade, at about 170 trades a month, that is about Rs 40, or 0.016R at 0.25% R.
- **Kill rules.** These apply after at least 200 decisions and 40 paper trades, or 6 weeks.
  1. If value-add ROI is below 1 and the bootstrap probability that value-add exceeds cost is below 0.3: drop a model tier, then kill.
  2. If, on at least 60 disagreements, the arm's side loses 55% or more: kill the arm.
  3. For approve/veto agents: if trades it vetoed do as well as trades it approved, on 80 or more vetoes: kill.
  4. Management agent: if it does not beat the replayed deterministic management by at least 0.05R per trade over 40 trades: revert to rules.
  5. If LLM cost exceeds 30% of a book's gross positive P&L over a rolling 20 days: that book goes to L1.

## Top 5 recommendations

1. **Adopt Target (≈ Rs 6.65k):** Opus for the pre-market plan with charts, a Sonnet 5.5 low-effort trader on approach-armed moments, Haiku for triage and routine management, and Haiku numeric and Haiku chart arms on 100% of moments.
2. **Phase-0 gate through OpenRouter, before any paper trading:**
   - Block-level `cache_control` with 1-hour TTL is honoured; check cached tokens in usage.
   - `reasoning.effort: low` is honoured on Sonnet 5.5; check reasoning tokens.
   - Strict `json_schema` works.
   - Billed image tokens match ⌈w/28⌉ × ⌈h/28⌉.
   - Measure p50/p95 latency over 200 calls per route from the laptop.
3. **Decide on approach, execute on trigger.** Use confirm-on-trigger only for bar-close setups, always with the chase guard.
4. **Use one call for many books** (B0–B3), and pay for second calls only for chart, model or vendor arms. Score arms on disagreements.
5. **Charts:** numeric packet by default. A 1000×700, two-panel chart with level IDs goes into the plan and into the randomized arms. After 300 paired moments, promote charts if the chart arm wins at least 60% of the disagreements; drop them if agreement with the numeric arm is 90% or more.

## Risks and unknowns

- **OpenRouter pass-through is unconfirmed:** caching TTL, effort mapping, Sonnet 5.5 `between_tools`, structured outputs per endpoint. openrouter.ai is blocked from this sandbox, so all OpenRouter claims are [M/L].
- **Latency figures are estimates** except the Haiku Phase-0 sample. Sonnet thinking length varies by moment.
- **No batch discount** through OpenRouter (assumed).
- **OpenRouter is a single point of failure** by owner decision.
- **Statistical power:** about 190 informative moments a month means arm verdicts take 1–2 months.
- **Alternative-model prices** come from aggregators [M/L].
- **Haiku's place in the high-resolution image tier** is assumed [M].

**Sources:** [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Anthropic vision](https://platform.claude.com/docs/en/build-with-claude/vision), bundled claude-api reference (cached 2026-10-06); OpenRouter docs via search: [prompt caching](https://openrouter.ai/docs/prompt-caching), [structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [response healing](https://openrouter.ai/docs/features/response-healing), [latency](https://openrouter.ai/docs/features/latency-and-performance), [model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks), [Claude 4.6 reasoning migration](https://openrouter.ai/docs/guides/guides/model-migrations/claude-4-6); fees and limits from [TrueFoundry](https://www.truefoundry.com/blog/openrouter-pricing) and [fast.io](https://fast.io/resources/openrouter-rate-limit/); prices for [Qwen3.5-Flash](https://openrouter.ai/qwen/qwen3.5-flash-02-23/pricing), [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash), [GPT-5.6 Luna](https://propakistani.pk/2026/08/01/openai-cuts-gpt-5-6-luna-price-by-80-soon-after-launch/), [Gemini](https://www.morphllm.com/gemini-api-pricing), [Sonnet speed (aggregator)](https://computeprices.com/models/claude-sonnet-5-5); Phase-0 results in `/home/user/auto-trading/docs/design/trading-system-design.md` §7.3; report 05 in `/home/user/auto-trading/docs/research/05-llm-agent-layer.md`.

The cost model is in [`scripts/llm_cost_model.py`](scripts/llm_cost_model.py); [`scripts/llm_cost_profiles.py`](scripts/llm_cost_profiles.py) holds the tuned profiles above.