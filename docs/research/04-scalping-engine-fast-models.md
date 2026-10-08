# Scalping Engine (1-10 min holds): quant and microstructure design report

**Date:** 2026-10-08. **Scope:** design only. **Tags:** each fact carries a confidence tag (H = high, M = medium, L = low) and a source. Anything marked **[J]** is my own judgment.

---

## 0. Bottom line

1. **Where a retail edge can exist at 1-10 min [J]:** it comes from choosing what to trade, then waiting for flow that persists. That means trading the 5-15 names whose flow is one-sided and driven by information, at structural levels, when you can see minute-scale persistence (institutional orders split over minutes, stop cascades). At 50-300 ms with a snapshot feed there is no edge in queue position, spread capture, sub-second index lead-lag or reading spoof orders. Colocated tick-by-tick (TBT) players own those.
2. **Recommended engine [J]:** deterministic setup state machines generate the signal. A LightGBM meta-label filter decides trade or no-trade and the size. It is trained only on depth you record yourself. LLMs, including fast ones and "Jev", stay out of the numeric hot path. A fast model's only job is news triage in under a second. It can open a watch on a symbol but can never place a trade.
3. **The binding constraints are not latency [J].** They are:
   - cost relative to stop width ("friction-to-stop");
   - Upstox's 30-level depth mode (full_d30) is capped at about 50 instruments;
   - historical depth is not available from brokers, so you must record from day 1, and ML cannot be trained for roughly 2-6 months.
4. **Budget 2026 STT changes flip the instrument choice.** Stock and index futures are now the worst scalping vehicle. Cash MIS is acceptable only on volatile in-play names. Nifty weekly options are about 5-10x cheaper per unit of 5-minute volatility than cash.
5. **Go-live bar per setup:** at least 200 paper trades with net expectancy of at least +0.15R under a pessimistic fill model. Then at least 100 live micro-size trades with slippage no worse than 1.5x the paper model. (R is the rupee risk of one trade, from entry to stop.)

---

## 1. Verified facts that drive the design

| Fact | Design implication | Conf | Source |
|---|---|---|---|
| Upstox V3 feed `full_d30` = LTPC + 30 depth levels + extended metadata + greeks; `full` = 5 levels. Protobuf encoded. | The recorder decodes protobuf; there are two depth tiers | H | [Upstox V3 feed](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/) |
| Plus tier: full_d30 limited to **50 instrument keys** (1,500 combined across modes), 5 connections per user. A forum reading says the 50 is per user, not per connection. Users report only the first connection receiving d30 data. | **About 50 deep-book slots in total.** The scalping universe must fit inside them | M | [Upstox V3 docs](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/), [WebSocket Plus](https://upstox.com/developer/api-documentation/announcements/websocket-plus/), [forum](https://community.upstox.com/t/subscribe-to-full-d30-mode-websocket/12469) |
| Some Plus users got only 5 levels, or no equity ticks, in d30 mode | Day-1 data-quality check: count levels in every frame | M | [thread 1](https://community.upstox.com/t/market-feed-api/11899), [thread 2](https://community.upstox.com/t/full-d30-mode-not-working/14244) |
| The feed pushes on change, not tick-by-tick. One user measured about 3 messages/s on Nifty. Snapshot data is about 1/s per the Upstox help pages. | All features must survive conflation; aggregate over 10 s or more | M | [Upstox forum](https://community.upstox.com/t/what-is-the-time-between-each-tick/3775), [Upstox help](https://help.upstox.com/support/solutions/articles/263407-what-is-the-difference-between-snapshot-data-and-tick-by-tick-tbt-data-) |
| Kite API: 5-level depth only. 20-depth is not available to API users. At most about 1 tick/s per instrument. | Zerodha is an execution fallback only; it cannot feed the depth model | M | [Kite forum](https://kite.trade/forum/discussion/3574/is-the-websocket-data-sampled-by-1-sec), [Z-Connect](https://zerodha.com/z-connect/kite/introducing-20-depth-or-level-3-data-beta-on-kite) |
| From 1 Apr 2026: static IP mandatory, **one active API app per Upstox user**, market protection on MKT/SL-M orders. API market orders were paused from Oct 2025. | Only marketable-limit and SL-limit orders. **The new system and the existing options agent must share one app, token and IP, or use a separate account** | M | [Upstox Apr-2026 mandates](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822), [MKT pause](https://community.upstox.com/t/regulatory-update-pausing-market-orders-via-apis/11306) |
| SEBI retail algo framework applies to all brokers from 1 Apr 2026. Threshold is 10 orders/s per exchange; modifications count. | Self-imposed token bucket of 5 orders/s; at most 2 modifications per entry | H | [SEBI circular 30-Sep-2025](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf), [Fyers notice](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/) |
| Upstox order API: about 30-40 ms server-side per staff; one user saw about 1 s end to end. v2 limits were 25/s, 250/min, 1,000/30 min. | Measure p50/p99 yourself; plan for tail latency | M/L | [latency thread](https://community.upstox.com/t/query-regarding-api-order-placement-delay/7840), [limits thread](https://community.upstox.com/t/uplink-api-v2-api-call-limit-per-day/3931) |
| STT from 1 Apr 2026: futures 0.05% sell side (was 0.02%); options 0.15% of premium sell side (was 0.10%); equity intraday unchanged at 0.025% sell side | Futures are now more expensive than cash to scalp | H | [PRS India](https://prsindia.org/budgets/parliament/union-budget-2026-27-analysis), [ICICI Direct](https://www.icicidirect.com/ilearn/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-should-know) |
| NSE transaction charges: 0.00297% equity, 0.00173% futures, 0.03503% options premium. Stamp duty 0.003% on intraday buys. SEBI fee Rs 10/crore. GST 18% on brokerage + transaction + SEBI fees. | Inputs to the cost model (re-verify quarterly) | M | [Zerodha charges](https://www.zerodha.com/charges) |
| Tick sizes: Rs 0.01 below Rs 250; 0.05 for Rs 250-1,000; 0.10 for Rs 1,000-5,000; reviewed monthly | Tick-to-price ratio varies about 5x; refresh a per-day tick table | H | [NSE CMTR67133](https://nsearchives.nseindia.com/content/circulars/CMTR67133.pdf) |
| Nifty lot = 65 from Jan 2026; weekly expiry on Tuesday | Option sizing granularity | M | [HDFC Sky](https://hdfcsky.com/news/nse-revises-market-lot-sizes-for-major-index-derivatives-effective-january-2026) |
| NSE historical order/trade data costs about Rs 5-10 lakh per year per segment | Buying depth history is not economical; record it yourself | M | [NSE tariff](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Other_Products_Tariff_01042025_.pdf) |
| 7 in 10 individual intraday cash traders lost money in FY23 (SEBI). Loss-makers' costs equalled 57% of their losses. | Base rate. Costs are the main killer; design around friction | H | [Business Standard](https://www.business-standard.com/markets/news/7-in-10-intraday-traders-in-equity-cash-suffered-losses-in-fy23-sebi-study-124072400975_1.html) |
| **"Jev" is a real product.** It is a "System One" typed-decision model from TypeSafe AI, launched 15-Sep-2026, early access with a waitlist. Vendor claims: 70-500 ms latency, $0.042 per million input tokens, typed outputs (choice/score/boolean) with probabilities, about 68% on the vendor's own 4-workflow benchmark. No independent benchmark yet. | A candidate for the text-triage slot, not for numeric prediction | M | [DataCamp](https://www.datacamp.com/blog/system-one-models-jev), [VKTR](https://www.vktr.com/ai-platforms/chatgpt-cocreator-launches-typesafe-ai-with-jev/), [The Register](https://www.theregister.com/a/5296711) |
| Small LLMs on fast hosts: about 0.16-0.33 s time to first token (Llama-3.1-8B on Groq and others). Groq deprecated some small models in Jun 2026. | Fast LLMs are viable for triage; model availability churns, so keep them pluggable | M | [Artificial Analysis](https://artificialanalysis.ai/models/llama-3-1-instruct-8b/providers) |

---

## 2. "Fast decision models": interpretation and recommendation

**Possible meanings of "Jev":**
- (a) **TypeSafe Jev**. Most likely, since it matches "quick decision model" exactly.
- (b) A typo for XGBoost-style fast ML.
- (c) Fast-hosted LLMs (Groq, Gemini Flash, Haiku).
- (d) JEPA, Meta's joint-embedding architecture, which has no trading relevance.

| Approach | Inference | Data needed | Fit for 1-10 min | Role **[J]** |
|---|---|---|---|---|
| **(d) Rule-based state machines** | µs | None; backtestable on candles | Encodes the setups directly; interpretable; you control it | **Primary signal generator** |
| **(a) GBDT (LightGBM)** | 20-200 µs per row (compile with lleaves/treelite) | ~1-3k events for a meta filter; ~10⁵ effective rows for a dense model | Best for mixed tabular microstructure features; monotone constraints; SHAP audit | **Primary ML: meta-label filter and dense "flow score"** |
| (c) Online/adaptive (river: online logistic regression, ADWIN) | µs | Streaming | Adapts within the day but chases noise | Probability recalibration, drift alarms, adaptive thresholds |
| (b) TCN, small transformer, DeepLOB | 0.2-5 ms on CPU | 10⁶-10⁸ snapshots over many months | Benchmarks of deep order-book models (e.g., the LOBCAST study, Prata et al. 2024; M from memory) show poor transfer to new stocks and periods | Research only, after 6-12 months of data |
| (e) Fast LLMs (0.2-2 s) and Jev (70-500 ms claimed) | — | Zero-shot | Good at text semantics. **No evidence they map order-book numbers to short-horizon returns.** Their calibration is not fitted to your data, and outputs are non-deterministic | **Text triage only:** headline materiality, direction and symbol; scheduled vs surprise event. Run as a shadow challenger with Brier-score scoring |

**Why not put an LLM or Jev in the trade decision even though 500 ms is small relative to a 5-minute hold [J]:**
- Latency is not the problem. Validation is.
- A GBDT trained on your own triple-barrier labels is measurable, deterministic and retrainable.
- A zero-shot model's "probability of a +0.3% move before a −0.2% move" has no grounding.
- A cheap experiment is still worth running: feed Jev anonymized feature snapshots (symbol and date stripped, so no leakage) in shadow mode and compare its Brier score with LightGBM's.

**Interface sketch (plug-and-play):**
```
SignalModel.predict(fv: FeatureVector) -> {p_win, exp_R, model_ver, latency_us}
TextDecisionModel.decide(state: str, questions: [Typed], timeout_ms) -> [Answer{value, prob}]
  # implementations: jev | claude_haiku | openai_mini | local_distilled_classifier (5-20 ms CPU fallback)
```
```yaml
scalping:
  primary: rules_v1
  filter: {type: lightgbm, artifact: meta_v3, min_p: 0.55, min_exp_R: 0.15, shadow_only: true}
  news_triage: {provider: jev, fallback: claude_haiku, timeout_ms: 800, on_timeout: block}
```

---

## 3. Features from 30-level depth and ticks

"Robust" means the signal survives 0.3-1 s of conflation and lag once aggregated over 10 s or more.

| Feature | Definition / window | Robust? |
|---|---|---|
| Distance-weighted depth imbalance | Σ w_k(q^b_k − q^a_k) / Σ w_k(q^b_k + q^a_k), w_k = e^(−λ·dist_bps), for k ≤ 5, 10, 30; EMA over 10-30 s | **H** at k ≤ 10; L beyond (deep levels flicker) |
| L1 imbalance, microprice | mp = (P_a·q_b + P_b·q_a)/(q_b + q_a); (mp − mid)/tick | **H for large-tick names** (spread usually 1 tick, e.g., Rs 1,000-1,500 stocks with a 0.10 tick, or Rs 250-400 with a 0.05 tick); M otherwise |
| OFI (Cont-Kukanov-Stoikov 2014) | e_n = q^b_n·1[P^b_n ≥ P^b_{n−1}] − q^b_{n−1}·1[P^b_n ≤ P^b_{n−1}] − q^a_n·1[P^a_n ≤ P^a_{n−1}] + q^a_{n−1}·1[P^a_n ≥ P^a_{n−1}]; sum over 10/30/120 s; normalize by average depth; multi-level version for levels 1-5 (Xu-Gould-Howison) | **H**. It was designed for snapshot data |
| Whole-book total buy vs total sell quantity | Δ(tbq − tsq) over 1-5 min. Use **changes, not levels**, because levels carry a persistent per-name bias | M |
| Depth slope / asymmetry | Regression of cumulative quantity on distance, per side, levels 1-30 | M |
| Wall persistence | Fraction of the last 60 s in which a level within 0.3% of price held ≥ 3x the median level quantity | M. **Do not build spoof "detection"**: snapshots cannot separate cancels from trades |
| Absorption / iceberg proxy | Volume traded at price P over a window ÷ the drop in displayed quantity at P, while P holds | M |
| Trade aggression | Δvolume between snapshots, signed by quote rule against the *previous* snapshot's bid/ask (tick rule as fallback); add bulk-volume classification (Easley-López de Prado-O'Hara) as a robust cross-check; aggressor ratio over 30/120 s | M |
| Short-horizon realized vol | RV from 5-s mid returns over 5/15/30 min; ratio RV5/RV30 | **H** |
| VWAP distance | (P − VWAP)/ATR_1m; anchored VWAP from the open and from news time; count of VWAP crosses in the last 30 min | **H** |
| Level distances | (P − L)/ATR_1m for ORH/ORL (15 min), PDH/PDL/PDC, round numbers, LLM levels; touch count; time since last touch | **H** |
| Tape speed | Volume per second vs the 20-day median for the same minute ("RVOL_1m") | H (use volume, not message rate, which depends on broker throttling) |
| Index lead-lag | Nifty/BankNifty futures return over 15/30/60 s; stock's beta-adjusted residual | **L-M. Warning:** differing feed delays per instrument create *fake* lead-lag. Research on exchange timestamps (`ltt`); trade on receive time |
| Sector / relative strength | Peer equal-weight return over 1/5 min; relative strength vs Nifty since open | **H** |
| Spread regime | Spread in ticks and bps; z-score vs time of day | **H** (also a gating input) |
| Time and calendar | Minutes since open; expiry Tuesday; event flags | **H** |
| F&O-derived (later) | ΔOI over 5-15 min; Δbasis; IV change | M |

**Verify:** whether V3 d30 levels include order counts (v2 had them). If they don't, average-order-size features are unavailable. (L)

---

## 4. Setup families

Every setup requires permission from the LLM plan, the day type and the risk state. Every trade has a structural stop **plus a time stop**: exit if not at +0.5R by 50% of the maximum hold.

| Setup | Trigger | Stop | Target | Hold | Fails when |
|---|---|---|---|---|---|
| **Level breakout + flow** | Compression (3-5 min range < 0.6x normal) into level L. Last trade > L + 1 tick, OFI_30s z > 1.5, aggressor ratio > 60%, ask depth within 0.2% above L drops > 30% in 30 s, index/sector not opposing | Below L or the breakout micro-swing (typically 0.25-0.4%). Exit on a 1-min close back below L | 1.5-2R or the next level; 50% off at 1R, trail the rest | 2-10 min | Range days, 11:30-13:30, a persistent wall above with no absorption |
| **Absorption reversal at a wall** | Wall ≥ 3x median, persistent ≥ 60 s. Traded volume at the wall ≥ 1.5x its displayed size while price holds. OFI fades, then flips; price prints back through L − 1 tick | Beyond the wall extreme + 2 ticks (0.15-0.3%) | VWAP or the opposite side of the 5-min range; 1.5-3R | 2-8 min | The wall is pulled or eaten (this is the breakout case; the state machine makes the two mutually exclusive); strong trend days |
| **VWAP reclaim momentum** | Bias aligned. Pullback below VWAP, then price > VWAP + 0.05% for 20 s with OFI_60s z > 1 and positive relative strength | Pullback low or VWAP − 0.5·ATR_5m | Day-high retest / 2R | 3-10 min | More than 4 VWAP crosses in 30 min (auto-disable) |
| **Opening-drive continuation** | After 9:20. Gap/news name with a one-way drive on RVOL > 3; first pullback ≤ 50% of the drive on falling volume; book imbalance turns back with the trend; enter on the micro-high break | Pullback low | Drive high + extension / 2R | 2-10 min | Gap-fill days; Nifty reverses at the open |
| **Index-lead catch-up** | Nifty futures move > 0.15% in 60 s with strong OFI; a high-beta peer's residual z < −1.5 with no opposing book | Residual widens another 1σ, or 0.2% | Residual reaches 0 | 1-3 min | Stock-specific news (the residual is informative). **Thinnest edge: paper only until proven** |
| **News-shock first pullback** | News triaged as material with a direction. Impulse > 2x ATR_5m on RVOL > 5; first 30-50% pullback holds the anchored VWAP; OFI turns back; enter on the micro-break | Pullback low | Impulse high / 2R | 3-10 min | News gets reinterpreted; "sell the news"; name near its price band (**restrict the scalping universe to F&O stocks**, which have no hard circuits) |

---

## 5. Labeling, training, validation

- **Executable triple barrier.**
  - Entry is at the ask at t₀ + δ, with δ = measured feed-plus-order latency (about 300 ms), plus the slippage model.
  - The upper barrier is the setup target. The lower barrier is the structural stop. The vertical barrier is H ∈ {3, 5, 10} min per setup.
  - Barrier touches are evaluated on the **exit side** (bid for longs). The target fills only on trade-through; the stop fills at bid minus slippage ticks.
  - Label y = 1[R_net > 0.1R]; keep R_net for regression.
  - This avoids the "mid-price illusion", which inflates scalping backtests the most.
- **Two-stage model [J].**
  1. A *dense* flow model labels every 1-s snapshot of in-play names with P(+0.5σ before −0.5σ within 2 min). About 340k rows per day, but only about 1k effectively independent rows per day. It becomes trainable after roughly 30-40 sessions.
  2. The output feeds an *event* meta-filter (primary = rule fires, thresholds loosened for recall). The event model is pooled across setups with setup type as a categorical feature. It needs ≥ 1,000 events with ≥ 300 positives, which is about 50-100 sessions pooled and about 6 months per setup.
- **Cross-validation.**
  - Use day-blocked walk-forward: train on 60-120 sessions, test on the next 5, with a 1-session embargo.
  - Add combinatorial purged CV over day groups to estimate the probability of backtest overfitting.
  - Report the Deflated Sharpe ratio.
  - Same-symbol events with overlapping holding windows get uniqueness weights (López de Prado, AFML).
- **Leakage checklist:**
  - full-day normalizers (day high/low, full-day RVOL);
  - an in-play list chosen with hindsight (log the list as it existed at 9:10);
  - constituents that are not point-in-time;
  - exchange vs receive timestamps;
  - scalers fitted on the full sample;
  - LLM outputs regenerated after the fact (store only the plan as it was produced live).
- **Imbalance and calibration.** Don't resample. Calibrate with isotonic regression on a held-out fold. Select the threshold p* by expected R per trade, subject to a minimum trade count, not by AUC.
- **Model settings.** LightGBM with num_leaves 15-31, min_data_in_leaf ≥ 100, feature_fraction 0.7, monotone constraints where economics dictate (e.g., friction-to-stop).
- **Retraining and drift.**
  - Retrain weekly on a rolling window with sample-weight half-life of 30 sessions.
  - A challenger runs 5 sessions in shadow before promotion. Never retrain and deploy on the same day.
  - Drift checks: PSI on the top-20 features (alert at 0.2, freeze to rules-only at 0.3); calibration slope outside [0.7, 1.3] over the last 150 trades; ADWIN on rolling R.

---

## 6. The recorder: build first, run every day from day 1

**Connection plan [J], assuming 5 Plus connections and the 50-key d30 cap:**
- d30 for 2 index futures, about 10 heavyweights and 15-30 in-play names (re-subscribed at 9:10 and on news).
- `full` (5-level) for about 200 F&O stocks.
- `full` / greeks for Nifty weekly options, ATM ± 10 strikes.
- LTPC for the Nifty 500, used for breadth.
- One connection left for the existing agent, **if it shares the user**.

**Format:**
- **Bronze layer:** raw protobuf frames, length-prefixed, with `recv_ns` (chrony-synced to AWS Time Sync) and the connection id. Files rotate every 15 min and are zstd-compressed. This is the lossless replay source.
- **Silver layer:** nightly Parquet at `silver/depth/date=YYYY-MM-DD/symbol=X.parquet`. Wide schema: ts_exch, ts_recv, ltp, ltq, vtt, atp, oi, tbq, tsq, bid_px_1..30, bid_qty_1..30, ask_px/qty_1..30. zstd compression, sorted by ts_recv, row groups of about 100k rows.
- **Gold layer:** 1-s/5-s resamples and versioned feature sets for DuckDB/Polars.
- **Also record:** own orders and fills, the order-update stream, a decision ledger (full feature vector, model and plan version for every evaluated signal, including rejected ones), news with arrival time, daily tick-size, ban-list and lot tables.

**Volume estimate** (L-M confidence; measure in week 1):
- Assume about 3 updates/s × 22,500 s = 67.5k snapshots per instrument per day.
- A d30 frame is about 1.1 KB, so 50 instruments ≈ 3.7 GB/day raw.
- A 5-level frame is about 250 B, so 200 instruments ≈ 3.4 GB/day raw.
- **About 7 GB/day raw, about 2 GB/day as zstd bronze, about 0.5-1 GB/day as Parquet silver.**
- Per year: about 150-250 GB silver. Keep bronze hot for 90 days, then move it to cold object storage.

**Data-quality monitors:** levels per frame < 30; crossed books; feed lag (recv − ltt) p50/p95; gaps on reconnect (features over a gap are flagged invalid, never interpolated); stale-instrument alarms.

**Research possible on candles alone meanwhile:**
- Setup base rates and frequency.
- MAE/MFE distributions.
- Stop and time-stop shapes.
- Time-of-day effects.
- In-play selection rules (gap, RVOL, NSE announcement timestamps).
- Day-type classifier.
- Option-scalp research on the expired-contract 1-min history.

Use next-bar entry plus 1-2 ticks plus fees, and when one bar touches both stop and target, assume the stop hit first. **Kill rule [J]:** if a setup is not profitable on candles at +2 bps of extra slippage, depth features will not rescue it. Depth typically adds a few points of win rate as a filter.

---

## 7. Execution and latency

- **Order types.** Limit orders only. Momentum entries (breakout, opening drive, news pullback) use a *marketable limit* at ask + 1-2 ticks. Passive fills on momentum are adversely selected: you get filled when the move fails.
- **Limit-then-chase.** Allowed only for reversal and VWAP setups. Join at the touch. After 1.5 s, re-price once to touch + 1. Hard cap on chase = min(3 ticks, 0.1R). Then cancel; the signal is stale.
- **Exits.**
  - **Always place a broker-side SL-limit** (trigger at the stop, limit 0.3-0.5% through it) within 1 s of each fill, sized to the filled quantity.
  - The target is managed in software: a marketable limit when the bid trades through the target, plus the time stop.
  - This avoids the two-resting-orders problem with no native OCO, where both legs can fill and leave a reversed MIS position.
  - Alarm if any position has been unprotected for more than 2 s.
- **Partial fills.** Protect the filled quantity immediately and cancel the remainder at the deadline. Keep the position only if friction-to-stop at the filled size is ≤ 0.2R. Otherwise exit.
- **Adverse selection.** Log the mid move 5/30/60 s after each fill. If passive fills show more than 0.15R of average post-fill adverse move, disable passive entries for that setup.

**Latency budget:**

| Stage | Target p50 / p99 |
|---|---|
| Exchange event → Upstox snapshot published | Unknown, est. 100-500 ms (**measure**; alarm > 1 s, pause > 2 s) |
| Upstox websocket → Mumbai VPS | 2-10 ms |
| Protobuf decode + feature update | 0.3 / 1 ms |
| LightGBM (compiled) + risk checks | 0.2 / 0.5 ms |
| Order POST on a warm HTTP keep-alive connection → ack | 40-100 / 400 ms |
| **Internal tick-to-order-sent** | **< 2 / < 10 ms** |

**Stack [J].** Python asyncio with uvloop, numpy ring buffers, and Numba only where profiling shows a need. Use separate processes for feed, recorder, strategy and order gateway so disk I/O never blocks decisions. Call `gc.freeze()` after warm-up. **Rust is not needed.** Internal compute is less than 1% of a budget dominated by feed lag and the broker.

---

## 8. Instrument choice

These are my calculations from the verified rates. Assumptions: Rs 20/order brokerage, Nifty ≈ 25,000, ATM weekly premium ≈ Rs 120.

| Vehicle (1 round trip) | All-in fees | + spread | Cost vs 5-min σ | Verdict |
|---|---|---|---|---|
| Cash MIS, Rs 10L notional | ≈ Rs 400 = **4.0 bps** | 1-3 bps for large caps | ≈ 0.3σ (normal large cap); ≈ 0.15σ (in-play, 3% daily vol) | OK **only on in-play names** |
| Stock futures, Rs 10L | ≈ Rs 610 = **6.1 bps** (STT 0.05%) | Often wider than cash | Worse than cash | **Avoid for scalps** |
| Nifty futures, 1 lot (~Rs 16L) | ≈ Rs 960 ≈ **15 Nifty pts** | 1-2 pts | ≈ 0.65σ (σ₅ₘ ≈ 23 pts) | **Avoid** |
| Nifty weekly ATM option, 10 lots (Rs 78k premium) | ≈ Rs 230 ≈ **0.36 pts/unit** | 0.1-0.2 pts | ≈ 0.04-0.05σ (option σ₅ₘ ≈ 11 pts); theta ≈ 0.3 pts per 5 min | **Most cost-efficient**; huge depth |

**Friction-to-stop is the key rule.** With R fixed, friction f(R) = (fee_bps + slip_bps) / stop_bps. Cash: (4 + 3)/30 = 0.23R, but a 15 bps stop gives 0.47R, which is lethal. The breakeven win rate is (1 + f)/(1 + T); with f = 0.25 and target T = 1.5R that is **50%**. So:
- **Hard filter: f ≤ 0.2R**, which in practice means cash stops of at least about 30-35 bps.
- Trade only names with 5-min σ of at least about 30 bps.

**Capacity at Rs 10L × 4x.**
- R = Rs 2,500 with a 30 bps stop gives about Rs 8L notional.
- Caps: notional ≤ min(Rs 15L, 25% of the displayed top-5 opposite depth, 3% of the trailing 5-min traded value).
- Capacity is fine in large caps. In mid caps the participation cap binds.

**Recommendation [J]:**
- Phase 1 live candidate: cash MIS on in-play F&O stocks (your stated priority).
- In parallel, **paper-trade index-direction scalps through Nifty ATM or 1-strike-ITM weekly options**, driven by Nifty futures order flow, because the cost math is far better.
- No futures scalping.

---

## 9. Gating: how the LLM plan and the fast engine interact

- **Subtractive-only principle.** The LLM can narrow permissions (symbols, direction, setups, size multiplier 0-1, blackout windows). It can never expand beyond the static risk config, never force a trade, and never touch the order path.
- **Plan snapshot.**
  - The plan is an immutable, versioned JSON object.
  - Each symbol entry holds: bias, conviction, levels with type, invalidation conditions expressed as price rules, event times, and allowed setups.
  - Updates arrive asynchronously every 15-30 min or on news, after schema and bounds validation.
  - The hot path never waits on an LLM. A plan older than 45 min means no new entries.
- **Direction matrix:**
  - setup aligned with bias → 1.0x size;
  - neutral bias → 0.5x;
  - opposed → blocked, except an absorption reversal at an LLM level explicitly allowed.
- **Day type.**
  - Computed deterministically at 9:30, 9:45, 11:00 and 13:30 from: opening range width / ATR, gap, 15-min RVOL, Nifty 500 breadth, VWAP slope and India VIX change. The LLM can only restrict it.
  - **Trend day:** breakout, opening drive, VWAP reclaim, news.
  - **Range day:** absorption only.
  - **Volatile two-way day:** absorption and news at 0.5x size.
  - **Event day:** blackout for 15 min after the event, then news-shock only.
- **News path.**
  - Headline → Jev or fallback triage in under 1 s.
  - The symbol is added to the d30 watchlist and the news-shock setup goes into observe-only mode.
  - The deep LLM must confirm within 30 s. If the two disagree, no trade.
- **Blackouts:** 9:15-9:20; no new entries after 15:00 (MIS square-off; verify Upstox's exact time); results announcement ± 15 min; RBI policy window; last 60 min of expiry Tuesday for index-sensitive names.

---

## 10. Risk, evaluation and kill criteria

- **Scalping sub-budget [J].**
  - R = Rs 2,500 (0.25%).
  - Daily scalping stop of −4R = Rs 10k, inside your overall Rs 20-30k limit.
  - At most 2 concurrent positions, 1 per sector, 3 trades or 2 losses per symbol per day.
  - After 3 consecutive losses, 20-min cooldown. After a −2R day, R is halved for the rest of the day.
  - Total of about 10-25 trades per day.
- **Sample size.** n ≈ (1.96σ/μ)² with σ ≈ 1.1R per trade. Proving +0.1R needs about 465 trades; +0.15R about 207; +0.2R about 116. **Use at least 200 per setup** before trusting expectancy.
- **Metrics per setup:**
  - n; win rate; average win/loss in R; net expectancy with 95% CI; profit factor;
  - MAE/MFE; exit mix (stop/target/time); entry and exit slippage in bps and in R;
  - post-fill adverse move; result by time bucket, day type and LLM alignment;
  - **counterfactual P&L of LLM-blocked trades**, to prove the gate adds value.
- **Paper fill model.**
  - Marketable orders walk the d30 book snapshot arriving ≥ δ ms after the decision, consuming displayed quantity.
  - Passive orders run two models: an optimistic queue model and a **pessimistic trade-through-only** model. Report both and decide on the pessimistic one.
  - Restrict scalping to d30-subscribed names so fills are simulable.
- **Live calibration.**
  - Run 1-10-share micro-probes, about Rs 50 per trade all-in, to measure real latency and fill behaviour.
  - Fit implementation shortfall by spread regime, size/depth and volatility, and feed it back into the paper simulator monthly.
- **Kill criteria.**
  - **Immediate:** feed lag p95 > 1 s for 2 min; reject rate > 5%; any fill unprotected > 2 s; daily stop hit.
  - **Setup pause:** rolling 50-trade expectancy < −0.1R; drawdown > 10R per setup or 15R for the subsystem; live slippage > 1.5x paper over 30 trades; SPRT rejects H₀ (+0.15R) in favour of H₁ (0R); PSI > 0.3.

---

## 11. Phased plan

| Phase | Weeks | Build / do | Exit gate |
|---|---|---|---|
| **P0 Recorder** | 0-2 | Upstox V3 multi-connection recorder (bronze/silver), clock sync, data-quality dashboard, cost/tick/lot tables, point-in-time universe | 10 clean sessions; 30 levels confirmed; feed-lag distribution known |
| **P1 Candle research** | 1-6 | Base rates for the 6 setups on 1-min history; day-type classifier; in-play selector; option-scalp study on expired contracts | Setups pruned to those positive at +2 bps slippage |
| **P2 Live paper, rules only** | 4-12 | State machines, paper broker (pessimistic and optimistic fills), risk manager, decision ledger, LLM plan in shadow, news triage in shadow (Jev vs Haiku vs local) | ≥ 20 sessions; system stable |
| **P3 ML** | ~8-20 | Dense flow model at 30-40 sessions; pooled meta-filter at 60-100 sessions; champion/challenger | Meta-filter improves out-of-sample expectancy by ≥ 0.05R without halving trade count |
| **P4 Live micro** | after gate | 1/4 R (~Rs 600), real Upstox orders, micro-probes | Per setup: ≥ 200 paper trades over ≥ 30 sessions, **≥ +0.15R net (pessimistic fills)**, PF ≥ 1.3, max DD ≤ 10R, positive in ≥ 2 of 3 time-split thirds, still positive after removing the best 5% of trades |
| **P5 Scale** | +2-3 months | R steps 1/4 → 1/2 → full, each after ≥ 100 live trades | Live expectancy ≥ 70% of paper; slippage ≤ 1.5x model |

**Realistic target [J]:** +0.1 to +0.25R net per trade. At 10 trades/day and R = Rs 2,500, that is roughly Rs 2.5-6k/day of expectancy. Plan for the real possibility that 3-4 of the 6 setups never pass P4.

---

## 12. Open questions for you

1. **Same Upstox user as the options-selling agent?** Since April 2026 Upstox allows one API app per user and requires a registered static IP. The two systems would share the token, the 5 connections, the 50 d30 slots and possibly margin and netting. Is a second account (for example a family member's, under the family-IP rule) acceptable, or do we build one shared broker gateway?
2. Can **Nifty weekly options scalping move earlier**, as a paper track from P2? The cost math strongly favours it over stocks and futures.
3. **VPS:** can we run a Mumbai cloud VPS (e.g., AWS ap-south-1) with a static IP around the clock during market hours? The latency and recorder design assume it.
4. Do you accept a **2-6 month recording-and-paper period** before any ML filter influences trades, and about 3-4 months before scalping goes live?
5. **Jev access:** are you on TypeSafe's early-access list? If not, the news-triage slot launches on Claude Haiku or a local classifier, with Jev as a later challenger.
6. **Split of the Rs 20-30k daily limit** between scalping and the LLM-driven intraday/swing book. I assumed Rs 10k for scalping.
7. Is **short selling via MIS** acceptable? Absorption reversals and half of the breakouts are shorts.
8. Is **Rs 15-25k/year for storage and VPS** acceptable, and do you want the raw depth archive kept indefinitely? It is your only depth history.
9. **Instrument scope:** will you limit scalping to F&O-eligible stocks (no hard circuits, deeper books)? Most in-play small caps would then be excluded.