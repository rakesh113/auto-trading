# Event-swing and LLM horizon review (role: event-driven swing trader and LLM researcher)

Confidence tags: H/M/L on sourced claims; [J] marks my own judgment. Today is 2026-10-12. I read only the design docs and research reports, not the code.

## 1. Verdict

**The risk and evaluation discipline is excellent. Swing, though, is wrongly specified, not merely rare.** The design points the LLM at the horizon where it is weakest (minutes) and treats the horizon where it is strongest (days) as a rule-gated exception.

**Problems with the current swing path (§7.5, A10):**
1. **It selects on the intraday price path, not on information.** A trade must already be +1.5R at 14:30, in the top 20% of the day's range, with RVOL ≥ 2. That yields roughly 1–4 holds a month [J]. At that rate, 200 trades take more than 4 years. A10 says there are "too few swing decisions to judge", but that follows from this definition, not from the horizon.
2. **It misses the main daily-horizon catalysts:**
   - evening results and filings made after hours;
   - concall guidance, which arrives T+1 to T+5 (audio within 24 h, transcripts within 5 working days under LODR) (M);
   - order wins scaled to revenue, followed over days rather than minutes.
3. **The hard 20/50-DMA uptrend gate excludes turnaround and re-rating surprises,** where drift should be largest [J]. It should be a feature, not a gate.
4. **Swing runs rule-based in season 1,** so the LLM's best skill (reading long documents consistently) gets no evaluation at all.

**The evidence points toward days, not minutes:**
- **Lopez-Lira & Tang (v6, Oct 2025):** on headlines after the training cutoff, GPT-4 captures the initial reaction (~90% portfolio-day hit rate), but that reaction is non-tradable. The tradable part is the subsequent drift, which GPT-4 scores do predict, especially for small stocks and negative news. Strategy returns decline as LLM adoption rises (H for the abstract; M for transfer to India).
- **Ke, Kelly & Xiu:** news is priced with a delay that is worse for small and volatile firms. A secondary summary puts it at about 4 days for fresh news (M).
- **Chen, Kelly & Xiu:** across 16 markets and 13 languages, prices respond slowly to news, and LLMs gain most on complex narratives (M). Results, guidance and concalls are exactly that kind of text.
- **Intraday LLM evidence is poor.** Alpha Arena: 4 of 6 models lost money. FINSABER: most claimed advantages vanished (both in report 17). SEBI: 71% of intraday cash traders lost money in FY23, rising to 80% of those with more than 500 trades a year (H).
- **The Nifty's long-run gains came mostly overnight; intraday has been net negative since 1995** (Capitalmind, M). A flat-by-15:12 book gives up the one session with a positive drift.

**Counter-evidence to respect:**
- **PEAD is fading.** In the US it disappeared for large caps around 2006 and more recently for microcaps (Martineau 2022, H; contested in 2025, M).
- **Indian PEAD evidence is mixed:**
  - drift found in 35 of 37 quarters for 2002–11 (M);
  - drift after bad news lasting over a week, while good news is priced efficiently (Nottingham, M);
  - no drift in 2014–18 (Gupta & Dhusia 2021, M).
- **Transcript models often just learn company identity** ("Same Company, Same Signal", M).
- **Kim, Muhn & Nikolaev (LLM financial-statement analysis) has been withdrawn.** Do not cite it (H).

**Bottom line [J]:** make an **LLM-led Event-Swing sleeve (ES)** a first-class season-1 LLM book, running in parallel with intraday L and scored per event. It is the fastest LLM bet to evaluate and the cheapest to be wrong about. Its rupee upside is modest, because the 1% overnight budget caps it at roughly ₹2.5L gross exposure.

### Intraday L vs ES, head to head

| | Intraday L (current) | Event-swing ES (proposed) |
|---|---|---|
| Edge the LLM uses | Ranking rule triggers within seconds, against algos, 45–100 s after news | Reading 20–60 pages (results, presentation, transcript); latency irrelevant |
| Friction per trade | 0.11–0.20R (gate 0.2R) | **≈ 0.07–0.10R**: ₹50k position, 4.5% stop, ~0.35–0.45% all-in round trip |
| Paper-to-live gap | Resting-limit fills are the biggest gap | Entries and exits at closing-auction or pre-open prices, which paper reproduces almost exactly |
| Scored units a month | ~600 moments | 300–600 events in results season [J] |
| Can it be replayed today? | No: needs recorded depth | **Yes:** post-cutoff Jul–Oct 2026 from daily bars and the filings archive, ~1,200–2,000 events [J] |
| Time to an IC screen | ~8 weeks, forward only | **~3 weeks on replay**, then 6–8 weeks of forward confirmation |
| Trades a month | 40–60 | 15–30 in season, 5–12 off season |
| Monthly cost if IC ≈ 0 | ≈ 0.15R × 50 × ₹2.5k ≈ ₹19k, plus LLM ₹4–6.6k | ≈ 0.4% × ₹55k × 20 ≈ ₹4.4k, plus LLM ~₹2k |
| Upside | IC 0.08 → +0.10R ≈ ₹12k/mo; IC 0.11 → ₹19k/mo | IC 0.08–0.12 → +0.4–0.8% net per trade ≈ ₹4–11k/mo |

Basis for the ES upside: excess return of the top quintile ≈ ρ × σ₅d (≈7%) × 1.40, minus ~0.4% costs, assuming a pool mean of 0. Breakeven IC is about 0.04–0.05 [J].

**At equal IC, intraday earns roughly 2× more rupees,** because it has a 2% budget against 1% and more trades. ES wins on four other counts: a higher prior probability that its IC is above zero, evaluation speed, the cost of being wrong, and paper realism. **Run both; they share the catalyst reads.**

---

## 2. The ES sleeve: specification

**Universe**
- Nifty 500 plus liquid names with median turnover ≥ ₹10 cr.
- Excluded: price band below 10% (unless F&O), ASM/GSM/ESM, T2T, listed less than 30 days ago.
- No new entry within 3 sessions before the stock's own results.
- Capacity is not a constraint: a ₹50k ticket is under 0.5% of ₹10 cr of daily turnover. Drift should be stronger lower down the cap curve (Ke-Kelly-Xiu, Lopez-Lira), but gap sizing gives small caps small tickets.

**Catalysts, in priority order**
1. **Quarterly results.** Code computes surprise against the company's own trend, margin change, the options-implied move (F&O names), 10-day pre-event drift, and peer read-across. The LLM judges quality (one-off or recurring) and guidance.
2. **Orders.** Code computes value ÷ TTM revenue, ÷ order book, ÷ market cap and ÷ 20-day turnover. No rigorous Indian study exists (L), so let ES-R (below) measure it.
3. **Concall "second read" at T+1 to T+5:** changes in tone and guidance. This is the purest LLM advantage [J].
4. **Credit or broker rating changes, promoter or insider buying (PIT/SAST), and block or bulk deals** (L–M).
5. **Sector and policy read-across** (duties, PLI, regulation) to second-order beneficiaries [J].

**Scoring pipeline**
- Rule pre-filter on filing categories.
- **Jev 1.13** typed triage on every filing (~$0.00002 each, 0.5–0.9 s). The bake-off with Haiku should be scored on event IC, not only on Brier score.
- Code builds the numeric event card.
- **Sonnet (low effort) deep read** on 10–25 events a day returns `EventScore`:
  - `exp_abn_ret_5d`, `p_up_5d`, direction;
  - `surprise_quality`, `guidance_delta`, `priced_in`;
  - invalidation; numbers by ID only.
- **Every event is scored, whether traded or not.**
- After the close, one "rank and take ≤ k of N" call applies portfolio constraints.

**Entry timing**
- Never trade the day-0 reaction for swing purposes; that is the non-tradable part.
- **Default:** buy at the day-1 close if day 1 holds at least 50% of the day-0 move, closes in the top half of its range, and volume is at least 2× normal. For evening results, day 1 is the reaction day.
- **Paired variants scored for free:** day-2 close, and day-1 open via the pre-open auction.
- **Mechanics:**
  - F&O stocks: limit orders in the **closing auction** (entry 15:20–15:30 with a random close, matching 15:30–15:35; it sets the official close; M-H).
  - Non-F&O stocks: slice across 15:00–15:30 to match their 30-minute-VWAP close.
  - This replaces the 14:30 MIS→CNC conversion.

**Exits**
- **Initial stop:** the event-day low minus 0.25 ATR, capped at 1.5 × ATR14. It is evaluated on the **close** and executed in the next auction. A catastrophic intraday stop at 2× distance is re-armed at 09:15. (SL orders are cancelled at 15:15 and not accepted in pre-open, so close-based stops are also the honest choice.)
- **Profit and time:** one-third off at +2R; trail the rest on a close below the 10 EMA after day 3; time stop at day 10. The arena compares 5 days, 10 days and the trail.
- **News on a held name:** a new filing triggers a Sonnet management call. Otherwise Haiku reviews each held name once a day.
- **Calendar:** halve the book before weekends or binary events when the geopolitical score is 2 or higher (as now).

**Sizing and overnight risk**
- Keep the design's formula: per-name stress ≤ 0.25% of equity, with shock = max(2 × P95 overnight gap, floor of 5%, 7% or 10%).
- That means ₹35–70k per name, at most 6 names, at most 2 per sector.
- Under a beta-adjusted Nifty −4% gap, the whole sleeve must fit its share of the 1% reserve. Unhedged, that caps ES at **≈ ₹2.5L beta-notional**.
- Track the regime (Nifty below its 50 DMA, breadth) as a size feature, not a gate. A long-only sleeve bleeds beta in a market that has fallen 8 weeks in a row.

**Instrument choice**
- **Cash CNC is the default.**
- **Stock futures: no.** Their STT is cheaper (0.05% sell side against 0.1% on both sides for delivery), but one lot is several lakh of notional, so a 7% gap costs ₹25–50k. That breaks the per-name budget. (Stock lot sizes are not verified; the ₹15L minimum applies to index contracts, H.)
- **Stock-option debit spreads only as a paired shadow,** like O3, before any real use:
  - liquid whitelist names only;
  - entered after results, once IV has been crushed;
  - expiry at least 2 weeks away, never in expiry week (physical settlement);
  - spread ≤ 1% of premium per leg;
  - debit ≤ 0.5% of equity.
  - The reason for caution: 4 legs × ₹20 plus spreads can eat 30–70% of a small debit on second-tier names [J].
- **Index hedge: tactical only.** A Nifty lot is about ₹14.8L of notional (65 × 22,776). A 2-week put costs about ₹5k a lot at 3% OTM or about ₹2k at 5% OTM [J, Black-Scholes at 17–19% IV]. Hedging continuously at 3% OTM costs about ₹10k a month, roughly the sleeve's whole expected profit. Buy puts only for weekends with a geopolitical score of 2 or more, and before binary events.

**Costs on a ₹50k round trip**
- STT ₹100, stamp ₹7.5, exchange ₹3, DP about ₹22–24.
- Brokerage ₹0–40 (Upstox's delivery rate conflicts between ₹20 and "₹20 or 2.5%"; M).
- Slippage at the auction is about 0; exits at the open cost 3–5 bps.
- **Total ≈ 0.30–0.45%.** Cost schedules stay as effective-dated data.

**LLM budget**

| Line | ₹ a month |
|---|---|
| Jev triage | ≈ 0 |
| Sonnet deep reads (~15 a day × ~₹5) | ~1,600 |
| Concall second reads | ~500 |
| Daily ranking call and Haiku management | ~200 |
| **Total in season** | **≈ ₹2–2.5k** (≈ ₹1k off season) |

Fund it by deferring V (₹1.9k) and folding in the separate materiality line (₹270).

**Trade count:** 15–30 a month in results season, 5–12 off season; about 200 a year.

---

## 3. Improvements, ranked by expected impact on profitability

### #1. Make ES a season-1 LLM book scored per event
- **What:** event table, `EventScore` on every material event, and a daily counterfactual engine (COE) built from daily bars and auction prices.
- **Why:** the evidence above points to days, not minutes. Friction in R is about half of intraday's.
- **Expected effect:** the most likely source of positive net LLM edge in the system [J]: +₹4–11k a month if IC is 0.08–0.12. It also improves the catalyst cards feeding intraday plans.
- **Cost and effort:** 2–3 weeks; the COE on daily bars is far simpler than the depth-based one. LLM ≈ ₹2–2.5k a month.
- **Risk:**
  - Drift may be decaying (Martineau; Lopez-Lira v6).
  - The sleeve is long-only, so it misses the stronger negative-news drift.
  - Beta exposure in a bear market.
- **Arena books:**
  - **ES-L:** LLM top-k, with risk limits.
  - **ES-R:** rules PEAD and order baseline: day-1 abnormal return ≥ 1.5σ, volume ≥ 3×, positive surprise against the company's own trend.
  - **ES-U:** take every event (the pool mean).
  - **ES-P:** random picks at L's take rate.
  - **ES-J/Hk:** cheap scorer.
  - **ES-M:** names masked.
- **Pre-registered tests:**
  - Primary: the date-clustered Spearman IC of `exp_abn_ret_5d` against realised 5-day abnormal return after costs.
  - Secondary: ES-L minus ES-R on paired events, and top quintile minus pool, after costs.
  - **Kill** at 1,000 events if IC < 0.03 or its 90% upper bound < 0.07.
  - **Success** if IC ≥ 0.07, the top quintile nets ≥ +0.4% per trade, the result is positive in both replay and forward samples and in both halves, and the placebo fails.

### #2. A post-cutoff replay harness with leakage controls
- **What:**
  - Score Jul 1 – Oct 9 2026 events with point-in-time text only, after the June 2026 training cutoff. That window includes the Q1 FY27 results season.
  - Freeze the prompt first, and seal 30% of the days.
  - Run a memorization probe: ask the model for post-cutoff closing prices; any recall means leakage.
  - Run a masked-name arm.
- **Why:**
  - Pre-cutoff tests cannot tell skill from memory (Lopez-Lira, Tang & Zhu 2025, H).
  - The distraction effect outweighs look-ahead bias, especially for large caps (Glasserman & Lin, H).
- **Expected effect:** an IC answer in about 3 weeks instead of 8. Combined with the forward Q2 season, about 2,000–3,000 events by mid-December. Day clustering halves the effective N, giving an SE of about 0.03.
- **Cost:** one-off Haiku/Jev on all events plus Sonnet on a stratified ~500, via OpenRouter Batch (~50% off): about ₹1.5k.
- **Risk:** a cutoff that is not clean, or revised fundamentals data. Use exchange-filed text only.
- **Arena:** report replay IC and forward IC separately. Graduation requires both.

### #3. Auction execution and close-based stops for every overnight position
- **What:** CAS limit entries and exits for F&O names, VWAP slicing for non-F&O names, pre-open auction exits, and close-evaluated stops with a catastrophic intraday backstop.
- **Why:**
  - Zero spread against the official close.
  - The COE outcome is the printed price, so paper ≈ live.
  - It removes the 15:15 SL-cancellation problem.
- **Effect:** saves ~5–10 bps a side and closes the paper-to-live gap almost completely.
- **Cost:** small change to the OMS and paper broker. Note that "v1 never trades the auction" must change for this sleeve only.
- **Risk:** auction imbalance on event names. Cap the limit at ±1% from the indicative price.
- **Arena:** live-minus-paper shortfall on L0 probes in the auction should be ≤ 0.02R.

### #4. Split the overnight budget by evidence
- **What:**
  - Replace "at most 1 swing name while any MCX positional is open" with per-sleeve stress budgets: ES 0.6–0.7%, MCX 0.3–0.4%.
  - Re-split at season boundaries by measured return per unit of stress.
  - Owner option, gated on ES reaching success: move from 2% intraday + 1% overnight to 1.5% + 1.5%. The 3% worst day is unchanged.
- **Why:** one CRUDEOILM lot alone uses ~75% of the overnight reserve and would starve ES.
- **Effect:** ES capacity rises 1.5–2×, from about ₹1.5L to ₹2.5–3.75L.
- **Cost:** a risk-config change, signed by the owner.
- **Risk:** correlated overnight shocks across equity and commodities. Keep the joint Nifty −4% stress scenario.

### #5. Feed ES reads into the intraday plan
- **What:**
  - ES event cards drive the Opus game plan's day-1 and day-2 continuation scenarios.
  - Negative-news reads drive intraday shorts in F&O names, because cash cannot be shorted overnight and stock futures are too lumpy.
- **Why:** negative news drifts most (Lopez-Lira; Nottingham, M), and intraday shorting is the only way to capture it at ₹10L [J].
- **Effect:** better catalyst moments for L at no extra LLM cost.
- **Arena:** the IC of L's CATALYST mode tag on names with an ES card, against names without one.

### #6. Concall second-read moments
- **What:** re-score held and watchlist names when the transcript lands (T+1 to T+5). A large change in guidance creates a new entry or exit moment.
- **Why:** this is long, nuanced text, where LLMs beat word-based methods (Chen-Kelly-Xiu, M), and it arrives after the fast money has acted.
- **Cost:** ~₹500 a month.
- **Arena:** IC of the second-read change against the T+3 → T+10 abnormal return.

---

## 4. Cut or de-prioritise
- **The intraday-winner carry gate as the definition of swing.** Keep it only as an exploratory "carry" variant inside ES.
- **Hard 20/50-DMA, sector and RVOL gates for event swings.** Make them features and let the arena price them.
- **The V chart twin in season 1** (₹1.9k a month). Charts add nothing to reading filings, and its own early stop will probably fire. Spend the money on ES reads.
- **Continuous index-put hedging** (≈ ₹10k a month at 3% OTM), and **swing through stock futures**.
- **Real-money stock-option spreads** before the paired shadow shows that net friction is ≤ 0.15R.
- **The separate "materiality analysis" route.** Merge it into ES scoring.
- **"Swing and MCX LLM books only after equity is proven" (A10, §16).** Reverse it for ES: ES evaluates faster than intraday L, and should not wait on L.

---

## 5. Top 5 recommendations
1. **Build ES now** as a season-1 LLM book scored per event: IC on 5-day net abnormal returns, with ES-R, ES-U, ES-P and ES-M as paired controls. Kill and success rules as in #1.
2. **Run the post-cutoff replay (Jul–Oct 2026) within 3 weeks,** with a frozen prompt, sealed days, a memorization probe and a masked arm. That gives the first honest LLM-skill number in the project, before intraday L's week-8 screen.
3. **Execute overnight positions in the auctions** (closing auction in, pre-open or closing auction out), with close-based stops. This is the cheapest way to make paper match live.
4. **Allocate the overnight budget by evidence** (ES 0.6–0.7%, MCX 0.3–0.4%). Pre-register the owner option to move to 1.5% intraday + 1.5% overnight if ES succeeds.
5. **Fund ES (≈ ₹2–2.5k a month) by deferring V,** and route its event cards and negative-news reads into the intraday plan. Expect, honestly: +₹4–11k a month if IC is 0.08–0.12, about −₹6k a month including LLM cost if IC ≈ 0, and a verdict by mid-December 2026.

**Sources:**
- [Lopez-Lira & Tang v6](https://arxiv.org/html/2304.07619v6)
- [Lopez-Lira, Tang & Zhu, Memorization Problem](https://papers.ssrn.com/abstract=5217505)
- [Glasserman & Lin](https://arxiv.org/abs/2309.17322)
- [Ke, Kelly & Xiu, NBER w26186](https://www.nber.org/papers/w26186)
- [Chen, Kelly & Xiu, seminar abstract](https://rsfas.anu.edu.au/node/21554)
- [Martineau, CFR 2022](https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf)
- [UCLA brief on the PEAD debate](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/)
- [Gupta & Dhusia, NSE PEAD](https://journals.vutbr.cz/index.php/trends/article/view/541)
- [Nottingham event study](https://eprints.nottingham.ac.uk/26569)
- [IIMB event-based trades](https://repository.iimb.ac.in/handle/2074/20501)
- [Kim, Muhn & Nikolaev (withdrawn)](https://arxiv.org/abs/2407.17866v3)
- [Same Company, Same Signal](https://arxiv.org/pdf/2412.18029)
- [SEBI FY23 intraday study](https://www.business-standard.com/amp/markets/news/7-in-10-intraday-traders-in-equity-cash-suffered-losses-in-fy23-sebi-study-124072400975_1.html)
- [Capitalmind, overnight vs intraday](https://premium.capitalmind.in/2019/10/while-you-were-sleeping-what-stocks-do-overnight-versus-in-trading-hours/)
- [Closing auction session (FundsIndia)](https://fundsindia.com/blog/investor-key-notes/introduction-of-closing-auction-session/35062)
- [LODR concall recording and transcript timelines](https://money9.com/news/equities/sebi-asks-listed-cos-to-make-analyst-call-recording-public-in-24-hours-19397.html)
- [Index ₹15L minimum contract value](https://www.icicidirect.com/research/equity/finace/nse-raises-minimum-contract-value-for-index-derivatives)
- [Upstox charges](https://upstox.com/help-center/257373)

Internal sources: `/home/user/auto-trading/docs/design/trading-system-design.md` (§5, §6, §7.5, §12), `/home/user/auto-trading/docs/design/ai-trader.md` (§0 A10, §1, §11, §12, §16), and research reports 02, 03, 07, 09 and 17 in `/home/user/auto-trading/docs/research/`.