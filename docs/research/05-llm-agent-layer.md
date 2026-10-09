# LLM and agent layer design: AI-assisted intraday trading system (NSE)

**Scope:** the LLM/agent layer only. It is built so the model can be swapped, and the LLM is never in the execution hot path.
**Confidence tags:** [H] high, [M] medium, [L] low. A "Source" tag marks a verified fact. Untagged design statements are my judgement.

---

## 0. Main positions

1. **The LLM decides where to look and what is allowed. It never decides how much or when to the second.** Sizing, entry timing and exits are deterministic. LLM outputs can only restrict permissions inside the risk caps in config, never widen them. I call this the monotone-restriction principle.
2. **Plans refer to price levels by ID, not by number.** The context builder gives the LLM a table of computed levels (`L.ORH15`, `L.PDH`, `L.VWAP`…). A plan must use these IDs plus small ATR offsets, and code turns them into prices. This removes most hallucinated numbers before any validator runs.
3. **Most agents are single calls with pre-built context, not agentic loops.** Only the Pre-market Strategist and the Materiality Analyst get tools. This keeps latency bounded, cost predictable and replays reproducible.
4. **Two of the proposed items need to change:**
   - **Day-type classification** should be deterministic. Opening-range width/ATR, gap, breadth, VIX change and the trend efficiency of the first 30 minutes classify better than an LLM reading numbers. The LLM adds an event prior and may only downgrade the label (for example to `EVENT_WAIT` before an RBI policy announcement).
   - **The fixed 15-minute re-assessment** wastes calls. Use a delta gate plus event triggers, and keep 15–30 minutes only as a maximum-staleness backstop.
5. **Be honest about news latency.** Ingestion takes about 5–15 s, triage about 2–5 s and materiality analysis about 15–40 s. LLM-driven entries therefore come 30–60 s or more after dissemination. The edge has to come from the continuation or second leg of a move and from avoiding traps, not from the first tick. Setup definitions must reflect this.
6. **On Rs 10 lakh, LLM cost matters.** The "Standard" profile costs about Rs 19–23k a month, roughly 1.9–2.3% of capital per month (§7). I recommend a lean-plus routing (about Rs 11–13k a month). Every agent has to prove its value against a no-LLM arm during paper trading.
7. **Paper mode lets you test several arms in parallel for free.** With no market impact, the deterministic-only, LLM-gated and LLM-plan arms can all run on the same live data at once. Only the LLM spend is extra.

---

## 1. Agent roster

| # | Agent | Default tier | Cadence (IST) | Latency p95 / hard timeout | Inputs | Output | Behaviour on failure |
|---|---|---|---|---|---|---|---|
| 1 | **Pre-market Strategist** (tools) | strong: `claude-opus-5-5`, effort high | 08:30, must finish by 09:05; light re-run at 09:10 using pre-open IEP data | 8 min / 12 min | Market sitrep; overnight story clusters; FilingAssessments since previous close; event calendar; F&O ban, ASM/GSM and T2T lists; yesterday's debrief notes | `MarketBrief` with ≤25 candidates and an avoid list | Deterministic brief (ranked by gap × RVOL), `risk_mode=REDUCED` |
| 2 | **Filings/News Triage** | fast: `claude-haiku-5-5`, effort low, thinking off | Event-driven, after a rule pre-filter | 4 s / 8 s | Item text (≤1.5k tokens) plus a symbol mini-context | `FilingAssessment` (lite) | Secondary fast model, then rules (whitelisted categories escalate automatically) |
| 3 | **Materiality Analyst** (tools, ≤4 calls) | standard: `claude-sonnet-5-5` medium; moves to Opus if materiality ≥80 or the item is ambiguous | On escalation (about 5–10% of items) | 40 s / 60 s | Parsed document; ratios computed by code; price reaction since t0; precedents | `FilingAssessment` (full) | Symbol gets `news_state=UNASSESSED`, which blocks news-driven entries |
| 4 | **Stock Analyst / Plan Writer** | standard: Sonnet 5.5 medium | Per candidate from 09:10–09:25; on a material event; on plan expiry. Max 3 plans per symbol per day | 45 s / 75 s | Symbol sitrep; MarketBrief; assessments; setups allowed by the day-type; precedents | 0–2 `TradePlan` | No plan (fails closed) |
| 5 | **Intraday Re-assessor** | fast: Haiku, which escalates to Sonnet when it sets `needs_escalation` | When the delta gate fires (open plans and positions only); immediately on events; backstop every 30 min | 5 s (Haiku) or 20 s / 30 s | Plan plus a sitrep delta since plan creation | `PlanUpdate` | `NO_CHANGE` (the broker-side SL still protects the position) |
| 6 | **Trade Critic** | strong, ideally a different vendor from the plan writer | Plans with `risk_tier=1.0`, any swing candidate, confidence ≥0.75, or a new trade after 2 losses that day | 60 s / 90 s | Same evidence as the plan writer (see the independent-first protocol below) | `CriticVerdict` {APPROVE, DOWNSIZE, REJECT} | Intraday: downsize to 0.5×. Swing: reject |
| 7 | **Post-market Reviewer & Coach** | Sonnet per trade, Opus for the daily synthesis, both via Batch API | 15:45–18:00 | async | Journal, fills, tick-path summaries, plans, full LLM I/O | `Review[]`, `DailyDebrief`, lesson candidates | Retry next morning |
| 8 | **Weekly Playbook Tuner** | Opus 5.5 via Batch (Fable 5.1 only if an ablation shows it adds value) | Saturday | async | 4–8 weeks of journal statistics computed by code | `ParameterChangeProposal[]` with evidence, sent for human approval | None |

**Critic independent-first protocol.** The critic first states its own stance from the evidence alone, without seeing the plan. Only then does it see the plan and give a verdict. If the critic's direction disagrees with the plan, the plan is downsized automatically. Critics from the same model family tend to make the same mistakes, so a different vendor or a blind first pass is how you get a real second opinion.

**Delta gate for the re-assessor** (computed in code). Call the LLM only when one of these is true:
- price moved more than 0.5×ATR(5m) since the last assessment
- a new filing or news item arrived for the symbol
- the sector or Nifty moved more than 0.4% in 15 min
- the plan validity has less than 10 min left
- an OI or IV regime flag flipped
- price came within 0.3 ATR of the stop or target

---

## 2. Context engineering

**Rules**
- Code computes every number. The LLM never sees raw ticks, raw depth or raw candles.
- Every block carries `as_of` and `data_lag_s`. The LLM must echo `sitrep_as_of` back, and any plan built on a sitrep more than 120 s old is rejected.
- Use percentiles and multiples (for example "RVOL 2.8x, 94th percentile") rather than bare levels where that reads better.
- Explicit units everywhere (bps, %, ×ATR, ₹ crore).
- Stable content goes first so prompt caching works. Order: system prompt + schema + playbook (cached) → market brief (cached per 15-min slot, shared across symbols) → symbol sitrep last.

**Token budgets** (enforced by the context builder, which truncates in priority order)

| Block | Token cap |
|---|---|
| Market sitrep | 2.5k |
| Symbol sitrep | 1.5k |
| News digest per symbol (≤5 clustered stories, 2 lines each) | 1.2k |
| Precedents (3 cases plus base rates) | 1.0k |
| Playbook notes (≤30 active) | 1.5k |
| Total plan-writer input | ≤12k |
| Re-assessor input | ≤4k |

**News reaction block.** Code computes all of this relative to t0 = exchange dissemination time:
- returns at +1m, +5m, +15m and now
- abnormal return vs Nifty and vs the sector index (beta-adjusted)
- volume multiple since t0 vs the same time of day
- maximum adverse and favourable excursion
- **pre-t0 drift**: abnormal return in the 30 min before t0, used as a leak indicator
- the share of the expected move already realised, which becomes the basis for the `priced_in` estimate

**Example symbol sitrep** (about 450 tokens; illustrative values)
```
SITREP v3 | RELIANCE NSE_EQ|INE002A01018 | as_of 2026-10-08T10:31:00+05:30 | lag_s 1
px: ltp 1412.3 | d +2.41% | gap +1.10% | vwap 1405.6 (ltp +0.62 ATR5) | hi 1416.0 lo 1394.2
vol: rvol_tod 2.8x (p94) | turnover_cr 1820 | spread_bps 1.2 (p20)
atr: atr5m 10.8 | atr_d14 24.5 | range/atr_d 0.89
rs: vs_nifty_30m +0.9% | vs_ENERGY_30m +0.6% | beta60 1.05
mtf: D UP (>20/50/200dma) 20d +6.2% 52wH -1.8% | 15m HH/HL x3 | 5m >vwap 14/16 bars
bars5m_ret_bps(last6): +12 -4 +18 +9 -6 +21 | vol_mult: 1.6 1.1 2.4 1.9 1.0 2.7
levels: L.PDH 1404.5 | L.PDC 1379.0 | L.ORH15 1408.2 | L.ORL15 1394.2 | L.VWAP 1405.6
        L.VWAP+1SD 1414.9 | L.R1 1418.0 | L.RND1400 1400.0 | L.SWH_D 1438.0
fno: basis_bps +38 | fut_oi +4.1% w/ px↑ => LONG_BUILDUP | atm_iv 22.4 (pctl1y 41, d +1.2)
     pcr_oi 0.92 (+0.08) | call_oi_max 1450 (+12%) | put_oi_max 1400 (+18%) | ban no
depth30(1m avg): imb@0.25% +0.31 | imb@1% +0.12 | ask_wall 1420 x6.1 (persist 210s)
     bid_wall 1400 x4.3 (persist 540s) | cancel_rate p55
news: [N1] T0 NSE 09:52:14 "Board approves capex…" cat=CAPEX mat=72 dir=POS
     since_t0 +1.3% (abn +0.9%) volx3.4 | pre_t0_30m abn +0.1% | realised/expected 0.55
state: plan none | trades_sym 0 | sym_pnl_R 0
```

**Market sitrep fields:** Nifty and BankNifty (same layout), India VIX level and change, advance/decline breadth, sector heatmap (15m and day), GIFT Nifty gap, FII/DII previous day, USDINR, Brent, US futures, event calendar with blackout windows, and the day-type label with its features.

**Depth summary.** The 30-level depth is aggregated per minute. It shows imbalance at bands of 0.25%, 0.5% and 1% from mid, walls (as a multiple of average level size, with persistence), and a spread percentile. The LLM uses depth only as context; the scalping models consume raw depth.

**Option-chain summary.** ATM IV and its 1-year percentile, IV change, PCR(OI) and its change, top-3 call and put OI strikes with change, futures OI-buildup class, and basis. Max pain is shown but marked low weight.

---

## 3. Output contracts

There is one Pydantic source of truth, exported to each provider's JSON-Schema dialect. Claude structured outputs reject `minimum`/`maximum`/`minLength`, so those constraints go into the field descriptions and are validated in code. Compiled grammars are cached for 24 h. Source: [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) [H].

```
MarketBrief/1 { as_of, day_type_prior: enum[TREND_UP,TREND_DOWN,RANGE,VOLATILE_2WAY,EVENT_WAIT],
  prior_conf: 0-1, risk_mode: enum[NORMAL,REDUCED,DEFENSIVE,NO_NEW] (may only lower config),
  events[{ts,name,impact:enum,blackout_before_min,blackout_after_min}],
  sector_bias[{sector,bias:-2..2,evidence_ids[]}],
  candidates[≤25]{symbol,catalyst_ids[],thesis≤25w,dir_bias:enum,priority:1-5,setup_hints[enum]},
  avoid[{symbol,reason_code}], unknowns[str] }

FilingAssessment/1 { filing_id, symbol, isin, dissem_ts, category: enum[RESULTS,ORDER_WIN,M&A,
  FUNDRAISE,MGMT_CHANGE,REG_ACTION,RATING,PLEDGE,BUYBACK_DIV,GUIDANCE,LITIGATION,PLANT_EVENT,ROUTINE,OTHER],
  routine: bool, materiality: 0-100, direction: enum[POS,NEG,MIXED,NEUTRAL],
  magnitude: enum[<0.5σ,0.5-1σ,1-2σ,>2σ]   // σ = stock daily vol, computed by code
  horizon: enum[INTRADAY,1-3D,LONGER], surprise: enum[BEAT,INLINE,MISS,NA] + expectation_source,
  priced_in: 0-1 + basis: enum[REACTION_SINCE_T0,PRE_T0_DRIFT,PRIOR_NEWS],
  key_facts[{name,value,unit,source_span}],  // code computes ratios such as order_value/TTM revenue
  rumour_status: enum[NA,RUMOUR,CONFIRMED,DENIED], confidence: 0-1,
  escalate: bool, injection_suspected: bool }

TradePlan/1 { plan_id, symbol, sitrep_as_of, valid_from, valid_until (≤90 min, ≤14:45),
  setup_type: enum (must be in allowed_setups[day_type]), direction: LONG|SHORT,
  entry{trigger: enum[BREAK_ABOVE,BREAK_BELOW,RECLAIM,REJECT,HOLD_AT], level_ref,
        offset_atr: -0.2..0.2, confirmations[{feature∈whitelist, op, value}], max_chase_atr ≤0.3},
  invalidation{stop_level_ref | stop_atr: 0.3..1.5, time_stop_min: 5..90,
        thesis_invalidators[{feature,op,value}]},
  targets[{level_ref | r_multiple: 1..4, scale_pct}], risk_tier: enum[0.25,0.5,1.0],
  holding: INTRADAY|SWING_CANDIDATE, p_t1_before_stop: 0-1,
  wrong_if[≥1 {text, feature,op,value}], thesis ≤60w, evidence_ids[] }

PlanUpdate/1 { plan_id, as_of, action: enum[NO_CHANGE,TIGHTEN_STOP,PARTIAL_EXIT,EXIT_NOW,CANCEL_PENDING],
  new_stop_level_ref?, reason_codes[enum], evidence_ids[], confidence }
  // Monotonic: stops can only tighten; size and validity can only shrink. There is no EXTEND or WIDEN.

Review/1 { trade_id, grade_plan: A-F, grade_exec: A-F, outcome_R, mfe_R, mae_R,
  error_type: enum[THESIS_WRONG,TIMING,CHASE,STOP_TIGHT,STOP_WIDE,IGNORED_CONTEXT,SLIPPAGE,VARIANCE,NONE],
  lesson_candidate{text, generalizable, evidence_trade_ids[]} }
```

**Validation pipeline** (all in code, in this order)
1. **Schema.** Guaranteed by structured outputs on Claude, OpenAI and Gemini. Local models use guided decoding.
2. **Semantic checks.** The symbol is on today's watchlist and tradable: not BE/T2T, not ASM stage ≥2, not in an F&O ban. The setup is allowed for the day-type. Timestamps are coherent.
3. **Numeric grounding:**
   - every `level_ref` resolves
   - long plans satisfy stop < entry < T1, short plans the reverse
   - entry is within 1.5×ATR(5m) of LTP and inside the circuit band
   - stop distance is inside the setup's ATR band
   - **net R:R to T1 is at least 1.5 after estimated costs and slippage**
4. **Fact check of the prose.** Code pulls every number out of `thesis` and `wrong_if` by regex. Each must match a sitrep value within rounding tolerance (±2%), otherwise the plan fails.
5. **Policy.** `risk_tier` must be allowed under the current `risk_mode`. Critic routing is applied here.

**Retry policy**
- One repair attempt, with the list of violations appended to the conversation (append-only, so the cache is kept).
- A second failure means the plan is rejected and logged. There is no fallback to looser rules.
- If an agent's rejection rate goes above 20% in a day, it is downgraded to advisory-only and an alert fires.

---

## 4. Provider abstraction

```
class LLMProvider(Protocol):
    name: str; caps: Capabilities  # structured_output, strict_tools, cache: explicit|auto|none,
                                   # server_web_search, batch, effort_control, sampling_control,
                                   # pdf_input, max_context, knowledge_cutoff
    async def generate(req: LLMRequest) -> LLMResponse
    async def submit_batch(reqs) -> BatchHandle
    def count_tokens(req) -> int
LLMRequest  { route, system_blocks[{text, cacheable}], messages, tools, output_schema,
              effort, max_output_tokens, deadline_ts, prompt_version, trace_ids }
LLMResponse { parsed, raw, stop_reason, refused, usage{in, cache_read, cache_write, out},
              cost_usd, latency{ttft_ms, total_ms}, provider, model_id, request_hash }
```

**Routing config** (my recommendation; model IDs verified for Claude, [M] for OpenAI)
```yaml
llm:
  budget_usd_day: 8.0          # degrade ladder at 80% / 100% of budget
  routes:
    triage:      {primary: anthropic/claude-haiku-5-5, effort: low, thinking: off, timeout_s: 8,
                  fallbacks: [openai/gpt-5.6-luna, rules]}
    materiality: {primary: anthropic/claude-sonnet-5-5, effort: medium, escalate: anthropic/claude-opus-5-5,
                  timeout_s: 60, fallbacks: [openai/gpt-5.6-terra]}
    plan_writer: {primary: anthropic/claude-sonnet-5-5, effort: medium, timeout_s: 75, on_fail: no_plan}
    reassess:    {primary: anthropic/claude-haiku-5-5, effort: low, escalate: anthropic/claude-sonnet-5-5,
                  timeout_s: 30, on_fail: no_change}
    critic:      {primary: openai/gpt-5.6-sol, fallbacks: [anthropic/claude-opus-5-5], timeout_s: 90}
    strategist:  {primary: anthropic/claude-opus-5-5, effort: high, max_tool_calls: 12, timeout_s: 720}
    review:      {primary: anthropic/claude-sonnet-5-5, mode: batch}
```

**Verified Claude facts**

| Model | Input $/MTok | Output $/MTok | Cache read $/MTok |
|---|---|---|---|
| Haiku 5.5 (≤100k-token prompts; $0.50/$2.50 above that) | 0.10 | 0.50 | 0.01 |
| Sonnet 5.5 | 2 | 10 | 0.10 |
| Opus 5.5 | 4 | 20 | 0.20 |
| Fable 5.1 | 10 | 50 | 0.25 |

Source: [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) [H].

- 5-minute cache writes cost 1.25× the input price and 1-hour writes cost 2×. Batch API is 50% off and stacks with caching. Web search costs $10 per 1,000 searches plus tokens; web fetch has no extra fee. Source: same pricing page [H].
- All four current models have a **June 2026 training cutoff**, a 1M context and 128K max output. Source: [models overview](https://platform.claude.com/docs/en/about-claude/models/overview) [H].
- **You cannot get determinism by setting temperature:**
  - Opus 5.5 rejects sampling parameters, and thinking cannot be disabled on it.
  - Sonnet 5.5 and Haiku 5.5 reject non-default sampling values.
  - Forced `tool_choice` (`any`/`tool`) returns a 400 on Opus 5.5 and Sonnet 5.5, so use structured outputs for the final answer.
  - Source: bundled claude-api reference, cached 2026-10-06 [H].
- Mid-conversation `role: system` messages work on Opus 5.5, Sonnet 5.5 and Haiku 5.5. They give a prompt-injection-safe operator channel (for example "risk_mode now REDUCED") without breaking the cache. Source: same reference [H].
- Opus 5.5 and Sonnet 5.5 support a server-side refusal fallback (`fallbacks: "default"`, beta). Source: same reference [M].

**OpenAI and Gemini equivalents**
- OpenAI GPT-5.6: Sol $5/$30, Terra $2/$12, Luna $0.20/$1.20; Batch is 50% off. Sources: [EdenAI](https://www.edenai.co/post/openai-cuts-gpt-5-6-api-prices-luna-falls-80-terra-20-sol-holds), [Kylon](https://kylon.io/blog/gpt-5-6-pricing-update-july-2026) [M].
- Gemini: 3.1 Pro at about $2/$12; Flash-Lite at about $0.25/$1.50. Source: [Morph](https://www.morphllm.com/gemini-api-pricing) [L-M].

**Fallbacks and determinism**
- **Circuit breaker per provider:** opens for 5 min if the error rate is above 20% over 2 min, or if p95 latency exceeds 2× budget.
- **Hedged requests** for triage only: if the primary has not answered by its p90 latency, fire the secondary.
- **If every provider is down,** the system enters LLM-degraded mode. No catalyst-driven plans are made. Technical setups on the existing watchlist run at 0.5× risk. Deterministic exits keep managing open positions.
- **Determinism replacement:**
  - pin model IDs, hash and version every prompt, and record every call for replay
  - use 3-vote self-consistency only for borderline materiality (50–80)
  - in evals, run each input 5× and target a flip rate below 10% on action fields
- **Telemetry per call:** tokens by type, $ cost (from a versioned price table in config), TTFT and total latency, cache-hit ratio, retries. Dashboard metrics: $/agent/day, $/plan, $/trade, and **LLM cost as a % of gross P&L**.

---

## 5. Tool design

All tools are read-only. They use `strict: true`, run in parallel, and return results wrapped as untrusted data with `as_of` and `source_tier`.

| Tool | Returns | Cache TTL | Timeout |
|---|---|---|---|
| `get_situation_report(symbol, sections[])` | Sitrep (≤1.5k tokens) | 60 s | 2 s |
| `get_market_sitrep()` | Market block | 60 s | 2 s |
| `get_option_chain_summary(underlying, expiry="near")` | Option-chain summary block | 180 s | 3 s |
| `get_filings(symbol, since_h≤72, categories[])` | Stored FilingAssessments | 30 s | 2 s |
| `search_news(query, since_h, max_tier)` | Story clusters from the **internal** news store | 300 s | 3 s |
| `get_fundamentals(symbol, fields[])` | Ratios, last 8 quarters, shareholding | 24 h | 3 s |
| `get_sector_snapshot(sector)` | Constituents' RS, breadth | 60 s | 2 s |
| `get_similar_cases(setup, catalyst, regime)` | Journal precedents plus base rates computed by code | 1 day | 2 s |
| `web_search` (server tool) | Strategist and Materiality Analyst only; `allowed_domains` = exchanges, SEBI, RBI, PIB and T1 press | — | 15 s |

**Caps on tool calls**

| Agent | Max tool calls | Of which web searches |
|---|---|---|
| Strategist | 12 | 3 |
| Materiality Analyst | 4 | 1 |
| Plan Writer | 2 | 0 |
| Re-assessor | 0 | 0 |

When a tool times out, it returns `is_error` and the agent has to continue without it.

---

## 6. News and filings pipeline

**Sources and polling cadence**
- NSE and BSE announcement JSON feeds, both unofficial. NSE needs a browser-style cookie session, which in community clients is cached for about 7 minutes. Sources: [india-market-mcp](https://glama.ai/mcp/servers/icharshal/india-market-mcp/tools/get_nse_announcements), [nse-bse-api](https://github.com/bshada/nse-bse-api) [M].
- Poll every 5–10 s with jitter from 09:00 to 15:30, every 30–60 s from 07:00–09:00 and 15:30–22:00 (results come in the evenings), and every 5 min overnight.
- Check NSE's terms of use. Budget for a paid feed as a backup; one forum post says about Rs 3 lakh a year [L].
- Track **dissemination → fetch → decision latency** as first-class metrics. I found no published figure for NSE's publishing lag, so measure it yourself [M].

**Volume reduction:** restrict to Nifty 500 and drop routine categories by rule before any LLM call. Examples: trading-window closure, Reg 74(5) certificates, newspaper ads, lost share certificates. I estimate this leaves about 150–400 items a day [L].

**Deduplication and clustering**
- A filing sent to both NSE and BSE is matched by ISIN + normalised subject + attachment SHA within 30 min.
- News articles are grouped into a `story_id` by MinHash or embedding cosine >0.85 within 24 h for the same entity.
- A cluster's timestamp is its **earliest credible source time**.

**Timestamps:** store three, and don't merge them.
1. Exchange dissemination time. This is authoritative for t0.
2. The article's published time, which is often edited later.
3. Our first-seen time.

If abnormal price movement started before t0, flag the event as "already reacting".

**Source credibility tiers**
- **T0:** exchange filings and regulators.
- **T1:** wires and top business press.
- **T2:** other media.
- **T3:** social media and Telegram. T3 never triggers anything on its own.

**Rumours**
- An item phrased as "sources said" is labelled RUMOUR and becomes CONFIRMED or DENIED when a clarification filing arrives.
- Under LODR Reg 30(11), the top-250 companies must confirm or deny a rumour within 24 h of a material price movement. Sources: [SEBI circular Jan 2024](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/SEBI%20Circular_25012024.pdf), [Argus](https://www.argus-p.com/updates/updates/sebis-framework-on-companies-dealing-with-market-rumours/) [M-H].
- Recommendation: **don't trade rumours in v1.**

**Staleness rules**
- Intraday, a filing older than 30 min whose price has already moved more than 1.5×ATR in the expected direction is marked "priced-in likely".
- News older than 1 session is not a catalyst unless it brings new facts.

**Attachments**
- Extract text with PyMuPDF. Fall back to OCR for scanned letters, which are common.
- For results, prefer the XBRL filing so numbers are extracted deterministically [M].
- Code computes YoY/QoQ change, order value as % of TTM revenue, and % of market cap. The LLM does no arithmetic.
- Send the full PDF to Claude only on escalation. The limit is 32 MB / 600 pages [H].

**Entity resolution**
- A daily instrument master maps NSE symbol ↔ BSE scrip code ↔ ISIN ↔ Upstox `instrument_key` ↔ Kite token.
- An alias dictionary covers brands, abbreviations and subsidiary-to-parent links (for example Jio → RELIANCE).
- Group-level news maps to several symbols. Policy or commodity news maps to a sector table.

**Prompt injection**
- Scraped content enters only inside delimited "untrusted document" blocks, after stripping HTML, scripts and zero-width characters, with a length cap.
- The triage model has **no tools**, and its output is schema-constrained.
- A heuristic flags documents that contain instruction-like text.
- Even a fully hijacked output would still have to pass the deterministic gates and the risk caps, so the damage is limited to a rejected or capped plan.

---

## 7. Cost and latency estimate

**Assumptions** (estimates):
- triage: about 600 filings and 400 news items a day; prefix 3–3.5k tokens cached, 1–1.5k variable, 250 out
- materiality: 9k input, 2.5k out including thinking
- plan writer: 7k cached + 7k variable input, 4k out
- re-assessor: 4k cached + 2.5k variable input, 0.7k out
- reviews via Batch API
- +10% for retries; 21 trading days a month; ₹95/USD ([HDFC Sky](https://hdfcsky.com/news/rupee-rises-24-paise-to-close-at-95-46-against-us-dollar) [M]); 18% GST on top [L]

| Profile | Routing | $/day | $/month | ₹/month incl. GST |
|---|---|---|---|---|
| **Lean** | Haiku for triage and re-assessor (60 calls); Sonnet for materiality (20), plan writer (15), critic and strategist | 4.0 | 85 | about 9.5k |
| **Standard** | Haiku triage; Sonnet for materiality (45), plans (25), re-assessor (150); Opus for strategist and critic (5) | 9.7 | 203 | about 22.7k |
| **Premium** | Opus for materiality, plans and critic; Fable for reviews | 19.7 | 414 | about 46k |

**What drives the cost:** in Standard, materiality analysis is about 26% of the bill and the Sonnet re-assessor about 22%. Triage across 1,000 items costs only about $0.32 a day on Haiku 5.5.

**Recommended "Lean+" profile:** Lean, plus Opus for the strategist and critic, materiality on about 30 items, and a Haiku re-assessor that escalates to Sonnet. That comes to about **$5.7 a day, or ₹11–13k a month**, roughly a 1.1–1.3% monthly hurdle on Rs 10 lakh.

**Ways to cut cost further**
1. Rule pre-filter on filing categories.
2. Delta-gated re-assessment (cuts 50–70% of those calls).
3. Cache-ordered prompts, with a market-brief prefix shared across symbols.
4. Batch API for all post-market work.
5. Effort set to low on the re-assessor.
6. No web search inside intraday loops.
7. Output limits: thesis ≤60 words.
8. Later, distil triage into a local classifier trained on Claude labels: under 50 ms and near-zero marginal cost.
9. A hard daily budget with a degrade ladder: at 80% of budget, Opus is replaced by Sonnet; at 100%, plan writing stops and only triage and exits continue.

**End-to-end news latency:** ingestion 5–15 s + triage 2–5 s + materiality 15–40 s + plan 20–45 s gives an actionable plan about 45–100 s after dissemination. This is my estimate [L]; measure it during the paper phase.

---

## 8. Evaluation and safety

**Leakage**
- Every current Claude model has a June 2026 cutoff [H]. Any test of return prediction on events before July 2026 is contaminated.
- Usable post-cutoff data today is roughly July to 7 October 2026. That includes the **Q1 FY27 results season**, about 500 Nifty 500 results, which makes the core of the golden set.
- The paper phase will overlap the Q2 FY27 results season starting mid-October, which is a good stress test.
- Pre-cutoff data is still fine for **extraction accuracy**, which predicts nothing.
- Mitigations from the literature:
  - Anonymise company names. Glasserman & Lin found that knowing the company distracts the model more than look-ahead does. Source: [arXiv 2309.17322](https://arxiv.org/abs/2309.17322) [H].
  - Chronologically consistent models. Source: [arXiv 2502.21206](https://arxiv.org/abs/2502.21206) [H].
  - A statistical test for lookahead propensity. Source: [arXiv 2512.23847](https://arxiv.org/abs/2512.23847) [H].
- The model registry stores each model's cutoff, and the golden-set window is re-cut whenever a model changes.

**Golden set**
- 800+ post-cutoff filings with ground-truth extracted numbers and realised abnormal returns at +5m, +30m, end of day and +1d. A subset of 200 also gets human materiality labels.

**Eval targets**

| Metric | Target |
|---|---|
| Number-extraction accuracy | ≥98% |
| Triage recall on events with \|AR\| > 2σ | ≥95%, while escalating ≤15% of items |
| Direction hit-rate on material events | Report it; no target set |
| Magnitude estimate vs realised move | Spearman correlation |
| Confidence fields | Brier score and ECE |

**Calibration**
- Each plan carries `p_t1_before_stop`. After 100 or more resolved plans, fit an isotonic regression from raw to calibrated probability and refit it monthly.
- **Confidence has no effect on sizing until calibration exists.** Even after that, it can only pick a `risk_tier`.

**A/B tests via shadow runs**
- The challenger runs on identical inputs, and its plans go through the same engine and fill simulator.
- To resolve a 0.1R difference in expectancy (σ of the difference ≈1R), you need n ≈ (1.96 × 1 / 0.1)² ≈ **380 paired plans**, about 5–6 weeks. Only test big changes.
- **Always keep a no-LLM arm.** An agent that doesn't beat its deterministic baseline by more than its cost gets switched off.

**Guardrails**
- No order tools anywhere in the LLM layer.
- `risk_tier` is an enum; quantity is computed by the risk manager.
- Updates are monotonic, plans expire, and plans are capped per symbol per day.
- The kill switch is independent of the LLM layer.

**Audit**
- Append-only log of the full request (prompt version and hash, messages, tools) and response, usage, latency and validator verdicts, linked by `plan_id`/`trade_id`.
- Retain it for multiple years; confirm the tax retention period with a CA.

---

## 9. Learning loop

**Journal record per trade:** the exact sitrep the model saw, the LLM I/O, fills, outcome in R, MFE/MAE, time to T1 or stop, slippage, and an `error_type` that separates a bad plan, bad execution and plain variance.

**Retrieval of precedents**
- Combine structured filters (setup, day-type, catalyst category, volatility regime, sector) with embeddings to find the top 3 precedents.
- **Code computes the base rates**, shrunk toward a Beta prior. They are shown only when n ≥ 15, together with a confidence interval.

**Playbook notes**
- At most 30 active notes. Each has an evidence link, a sample size, the date added and a review-by date.
- New notes are added only with human approval via Telegram or a dashboard.

**Weekly tuner rules**
- Proposals come as diffs with walk-forward evidence: fit on the last 8 weeks, hold out the final 2.
- No more than a ±20% change per parameter per month, and nothing based on fewer than 30 trades.
- Each change is shadowed for 1–2 weeks before it goes live, and every version is recorded.

**Guarding against overfitting**
- Older data decays with a half-life of about 60 sessions, with a floor.
- Outlier days (circuits, Budget day) are excluded.
- The LLM never edits its own prompt. Prompt changes go through the eval suite in git.

---

## 10. Interface to the fast scalping models

I couldn't resolve "Jev"; I've read it as "fast decision model" (Open Question 9). The scalping engine is a pluggable `SignalModel`, such as LightGBM or logistic regression on tick and depth features with about 1 ms inference.

Even the fastest LLMs (Haiku 5.5, GPT-5.6 Luna, Flash-Lite) take about 0.5–3 s with heavy latency tails [L]. That rules them out for entry timing on 1–10 minute scalps.

**Contract** (written to an in-memory key-value store and read locally on every tick)
```
ScalpPermit/1 { symbol, as_of, expires_at (≤20 min), regime: enum, allowed_dirs[LONG|SHORT],
  allowed_setups[enum], level_refs[], news_state: enum[NONE,FRESH_UNASSESSED,ASSESSED_POS,
  ASSESSED_NEG,RUMOUR], blackouts[{from,to,reason}], size_mult: 0..1, reason_codes[] }
```

**Rules**
- **If the permit has expired or is missing, the engine makes no new entries.** Exits stay deterministic.
- When a T0 filing hits a watchlist symbol, a deterministic handler immediately sets `FRESH_UNASSESSED`, which pauses new scalps on that symbol until triage (and materiality, if needed) clears it. **The LLM's latency defines a blackout window, not a signal.**
- `size_mult ≤ 1`: the LLM can only scale risk down.
- Use LLM labels as **gates, not model features**, until there are at least 3 months of labels logged under a frozen prompt version. After that, regime and news labels can be retrained as features.

**Regulatory constraints the execution layer must handle**
- The SEBI retail algo framework has been fully applicable since 1 April 2026.
- Below 10 orders per second, no strategy registration is needed, but orders are tagged as algo.
- Other requirements: a static IP, daily 2FA, and market orders converted to MPP.
- Sources: [FYERS notice](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/), [Sansa Legal](https://www.sansalegal.com/post/sebi-algorithmic-trading-framework-2026-what-retail-traders-in-india-must-know) [M].

---

## Verified vs judgement

- **Verified:** Claude prices, cutoffs, API constraints and structured-output limits [H]; OpenAI and Gemini prices [M/L]; SEBI rumour and algo rules [M]; the leakage papers [H].
- **Judgement:** all latency budgets, item volumes, token sizes, thresholds and routing choices. Calibrate them in the first 2 weeks of paper trading.

## Open questions for the owner

1. **Monthly budget for LLM and data APIs:** about ₹10k, ₹20k or ₹40k? This picks Lean+, Standard or Premium.
2. **Will you be available during market hours** to approve trades on Telegram within about 60 s? This decides whether a missing critic verdict means downsize or reject.
3. **Paid news or filings feeds** (Reuters, CMOTS, Trendlyne, a vendor API), or scraping only? This drives news latency and reliability.
4. **A source for results consensus estimates?** Without one, "surprise" on results is weak, and the results setups lose most of their value.
5. **Hosting:** a Mumbai VPS with a static IP (the algo framework requires a static IP anyway), or home? Is a GPU available for a later local triage model?
6. **Are you comfortable sending positions and plans to US-hosted LLM APIs?** If not, a local model is needed.
7. **Maximum trades per day, and is every swing/overnight trade manual-approval only?** (I recommend yes.)
8. **Trade rumours or unconfirmed news at all in v1?** (I recommend no.)
9. **What did "Jev" mean?** A specific model or library would change the §10 interface.
10. **Should this system read the existing options-selling agent's positions** so it can cap correlated index exposure?