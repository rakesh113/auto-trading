# Final recommendation from the red-team CIO (12 Oct 2026)

Confidence tags: **H**, **M** and **L** mark how strong the evidence is. **[J]** marks my own judgment. "Verified" means I checked the claim on the web today.

## 1. Verdict

**The chassis is fine. The allocation is not.** Several parts are better than most retail systems ever get and should be kept:
- code owns the risk limits;
- paper fills are conservative;
- kill criteria are written down in advance;
- the arena runs paired counterfactual books;
- a drawdown ladder cuts size as losses grow.

As specified, though, the system will most likely lose money net of costs and LLM spend in year 1.

**The biggest weakness:** about 70–75% of build effort, most of the LLM budget and two thirds of the 3% worst-day budget go to the weakest cell, minute-scale intraday cash trading. There:
- the trigger pool's base rate is negative (the design's own figure is about −0.05R; with realistic costs it is nearer −0.10 to −0.15R);
- real friction is 0.25–0.32R at the minimum 45 bps stop, not the 0.2R the gate assumes;
- the LLM would need a ranking skill (information coefficient, IC) of about 0.15 to reach the design's +0.15R target. That is elite-prop performance.

Meanwhile the three cells where evidence, cost and LLM strengths line up are deferred or starved:
- **event-driven stock swing (2–10 days):** about 0.07–0.10R friction, latency doesn't matter, and the LLM reads long filings;
- **commodity trend:** about 0.03R friction, a century of evidence;
- **the overnight index-option volatility risk premium (VRP):** India-specific evidence, now verified.

A linear-sum overnight rule also caps the whole swing book at about ₹1.5L.

**Second weakness: there is no portfolio layer.** Nothing measures the combined book, sizes on the lower confidence bound of a sleeve's edge, or stops spending when nothing works. The fixed costs (LLM ₹60–84k a year, plus infrastructure) are about the same size as the plausible gross edge at R = 0.25%.

**What the six reviews agree on:**
- Build event-swing stock trading now.
- Narrow intraday LLM calls to catalyst names.
- Drop the chart twin V.
- Fix the friction model.
- Replace count-based overnight caps with a scenario stress test.
- Keep options and commodities rules-only.
- Cut scalping.

## 2. Contradictions between the reviews, resolved

| Issue | Positions | Ruling | Basis |
|---|---|---|---|
| Expiry-day iron fly (O2) | Portfolio: second sleeve and an intraday hedge, +2–3%/yr. Options: about break-even, demote. | **Demote to research** (1 set, max loss ≤ ₹3k, plus an "unconditional" twin that sells every expiry). | Bhat, Pandey and Rao (J. Futures Markets, Aug 2024), **verified**: Nifty sellers earn the premium overnight, and intraday returns to short options are negative (M-H, abstract only). The options reviewer's per-set maths (≈ −₹400 to +₹150 at ₹30/order) holds. The portfolio Monte Carlo overstates combined returns by about 3 points a year as a result. |
| Overnight VRP value | Edge-map: ₹25–60k/yr. Options: ₹3–15k per set per year. | **Use ₹3–15k.** Free counterfactual book only. | An 8-order condor at ₹30 + GST costs ₹283, which is 15–20% of the credit. **You already run a separate strangle/condor agent**, so a second live short-vol engine would double the same tail. |
| Worst-day split | 1.5% intraday + 1.5% overnight now (edge-map, MCX), gated on swing success (swing), or keep 2% + 1% with portfolio stress (portfolio) | **Keep 2% + 1% for now, but measure overnight risk with a scenario stress test.** That alone gives about 1.5–2× capacity. Run 1.5% + 1.5% as a second variant of the composite book (free in paper). You decide at go-live. | Scenario stress fixes most of the starvation without moving the 3% worst day. |
| Swing shorts | Stock futures (portfolio), put debit spreads (edge-map, options), neither (swing) | **No stock futures.** One lot is several lakh of notional, so a 7% gap is ₹25–50k, which breaks the 0.25% per-name stress cap. **Season 1 is long-only in cash (CNC).** Put debit spreads run as a paired shadow (O5). Negative-news reads go to **intraday** shorts on F&O names instead. | Lot notional vs. the per-name stress cap. |
| ES kill rule | Edge-map: IC < 0.02 at 1,500 events. Swing: IC < 0.03, or its 90% upper bound < 0.07, at 1,000 events. Portfolio: about 100 trades. | **The signal is judged on scored events; money is judged on trades.** Interim kill at 1,000 events (swing review's rule). Final verdict at 2,000 events. Live money also needs ≥ 100 trades with LCB > 0. | With trades clustered by date, 1,000 events give a standard error of about 0.045, so a single cut-off at 1,000 is under-powered [J]. |
| MCX momentum evidence | Portfolio: one study found none (M-L). MCX review: Jaiswal & Uchil find positive (M). | **Build it small, as rules only, and gate it on a 30-year CME × USDINR backtest.** | MCX crude, gold and silver are priced off CME, so the global time-series momentum evidence (H) transfers. Paper trading proves the operations, not the edge. |
| Pledged collateral for MCX | Portfolio: not allowed. MCX review: allowed. | **Allowed at Zerodha since 10 Dec 2024 (verified, H).** Check Upstox's own rule. | Zerodha Z-Connect update. |
| Broker saving of "₹59k/yr" | Edge-map and portfolio | **Overstated.** That figure assumes 10 round trips a day; once the stocks-in-play gate applies (1–2 trades a day) it is about ₹10–15k. Upstox Basic is also ₹20; **Plus at ₹30 is what you pay for 30-level depth** (verified). | Brokerage only matters live. On swing, delivery brokerage of ₹0 vs ₹71 per round trip saves about 0.13% per trade, roughly ₹13k/yr. |
| OpenRouter batch discount | Assumed at −50% | **It exists per third-party reports (L-M). Budget without it** and treat it as upside. | I couldn't reach OpenRouter's own docs. |
| Intraday edge assumption | Design +0.15R, portfolio Monte Carlo +0.10R, edge-map +0.05–0.08R, intraday review "loses as specified" | **Plan on 0R as specified, and +0.03–0.08R after the base-rate fixes** if catalyst IC is real. | SEBI FY23: 71% of intraday traders lost money, 80% of those with more than 500 trades a year (H). |
| Market intraday momentum in Nifty (the premise for O1) | Assumed | **I found no Indian study (L).** US evidence is H. Test it offline before any paper capacity. | |
| Kim, Muhn & Nikolaev (LLM financial-statement analysis) | Cited in the research | **Withdrawn (v3, Feb 2025; verified).** Remove it from the docs. | |
| Closing auction | Swing review relies on it | **Live since 3 Aug 2026, 15:15–15:35, F&O stocks only (verified, M).** Only about 2 months of history. | |

## 3. Top 10 improvements, ranked by expected value per unit of effort

**1. Post-cutoff replay, 1 Jul – 9 Oct 2026 (season 0).**
- **Change:** run every NSE/BSE filing in that window, including the Q1 FY27 results season, through the triage, event-swing (ES) and intraday-catalyst prompts.
  - Freeze the prompts first.
  - Seal 30% of the days.
  - Add a memorization probe and a masked-name arm.
  - **Check each model's stated training cutoff.** Any model whose cutoff falls after 1 Jul is contaminated, and Jev 1.13's cutoff is unknown.
- **Effect:** the first honest skill number for the LLM, in about 3 weeks instead of 8–14.
- **Evidence:** H that the control is needed (Lopez-Lira, Tang & Zhu on memorization).
- **Effort:** about 1 week, plus ₹3–5k one-off.
- **Arena:** replay IC and forward IC are reported separately; graduating needs both.
- **Flag:** prompt tuning on replay days. Label it "season 0" and never call it proof.

**2. Build event swing (ES) as a first-class LLM book.**
- **Change:**
  - Jev triages every filing.
  - Code builds the event card.
  - Sonnet does a deep read of 10–25 events a day.
  - One "rank and take k of N" call after the close.
  - Entry at the day-1 close only if day 1 confirms the move. Never trade the day-0 reaction.
  - Stop at the event-day low minus 0.25 ATR (capped at 1.5 ATR), judged on the close. Exit at a 10 EMA trail or after 10 days. No hold through the stock's own results.
  - CNC long only, ₹35–70k a name, at most 6 names. The 20/50-DMA filters become features, not gates.
- **Effect:** +₹4–11k a month if IC is 0.08–0.12; about −₹6k a month including LLM cost if IC ≈ 0 [J].
- **Evidence:** M overall:
  - LLM news scores predict the drift that follows, most for small caps and bad news (Lopez-Lira & Tang, H for the US);
  - Indian drift after results is contested (M).
- **Effort:** 2–3 weeks; about ₹2.2k a month of LLM spend, funded by cutting V.
- **Arena:** ES-L (LLM picks), ES-R (rules), ES-U (take every event), ES-P (placebo), ES-M (masked names). Primary metric: IC on all scored events, with trades clustered by date.
- **Flag:** post-earnings drift is decaying (Martineau, H); a long-only book carries market beta; trades bunch in results season.

**3. Honest friction gate plus a stocks-in-play gate for intraday.**
- **Change:**
  - Friction is the expected cost over all exit paths: live spread, the paper model's stop slippage (5 bps, 20 bps on news), and brokerage per executed order.
  - At most 2 exit legs; stop floor about 70–80 bps; spread ≤ 0.08 × stop.
  - Hard opportunity gate: catalyst materiality ≥ 60, or a gap ≥ 1 ATR with RVOL ≥ 3. Zero-trade days are allowed.
  - No new entries 11:00–13:30.
- **Effect:** +0.05–0.15R on the pool base rate; trade count −40–60% [J].
- **Evidence:** SEBI cost data (H); the stocks-in-play ORB result (M, though gross only, and a replication netted about zero); NSE's U-shaped intraday activity (M).
- **Effort:** 3–5 days.
- **Arena:** split the existing E1/E2 paper trades and the rules book by opportunity class and by entry time, against the non-in-play placebo P2. Pre-register realised/estimated friction ≤ 1.15.
- **Flag:** the thresholds (60, 1 ATR, RVOL 3) are untested. Fix them now and don't tune them on paper.

**4. Cut LLM spend to where text matters.**
- **Change:**
  - Drop the chart twin V (₹1.9k a month) and merge the materiality route into ES.
  - The intraday LLM book (L) is called only on CATALYST moments, and its pre-registered primary metric becomes CATALYST-mode IC.
  - Haiku scores every moment, which keeps K6 (the Haiku-vs-Sonnet test) running.
  - Jev leads triage, with Haiku as fallback.
  - Use Sonnet, not Opus, for routine calls (Opus needs reasoning tokens).
- **Effect:** frees ₹2.5–3k a month (₹30–36k a year, about 3% of capital, which is the size of a plausible edge at L1).
- **Evidence:** FINSABER and Alpha Arena show weak LLM timing skill (M); the text-reading evidence is H for the US.
- **Effort:** about 2 days.
- **Arena:** K6 becomes the **economic** gate: if Haiku's IC is within 0.02 of Sonnet's, switch to Haiku.

**5. Base-rate map in code (2022–26, no LLM).**
- **Change:** measure:
  - overnight vs intraday returns (Nifty, Nifty 500, and recorded option chains);
  - drift over days 0–10 by catalyst type and surprise size;
  - gap fade vs continuation;
  - 1-week reversal after moves with no news.

  Only pools with a base rate ≥ 0 get LLM calls.
- **Effect:** +0.05–0.10R at the same IC [J]. It also answers the O2/O4 question with your own data.
- **Effort:** 3–5 days.
- **Arena:** walk-forward base rates go into the situation report the LLM sees, and placebo P2 checks them.
- **Flag:** multiple testing. Use the map to choose pools, never to mine new setups.

**6. Portfolio layer.**
- **Change:**
  - Add a composite book PF that runs the target allocation through the real risk engine.
  - Overnight risk becomes a scenario stress: Nifty −4% × beta, worst name −12%, VIX +40% on option sleeves, an MCX price-band lock, and USDINR ±2%.
  - Sleeves are funded only when the 10th percentile (q10) of the edge's posterior is above 0.
  - R ramps at 1/8 Kelly on that q10, capped at 0.5%.
  - **Week-14 cost kill:** if no sleeve has LCB > 0, the LLM drops to triage only.
  - Below 10% drawdown, drop the sleeve with the lowest LCB rather than shrinking intraday R below ₹2k.
- **Effect:** removes the −8% to −20% years; 1.5–2× overnight capacity at the same 3% worst day.
- **Evidence:** H for the Kelly and ruin maths; [J] for the scenario set.
- **Effort:** about 1 week.
- **Arena:** daily-stop hit rate, peak margin, risk contribution per sleeve, and stress breaches (target 0).

**7. MCX multi-speed trend, volatility-targeted, rules only.**
- **Change:**
  - Signals: three EWMA crossovers plus a breakout signal on crude, gold and silver (natural gas only with a 1.5% overnight reserve).
  - Remove the ADX/EMA50 filters and the "crude or gold, not both" rule.
  - Positional holdings are exempt from the EIA flatten.
  - Backtest on duty-neutral bullion series.
- **Effect:** +₹10–25k a year at a Sharpe of 0.25–0.4, uncorrelated with equities [J].
- **Evidence:** H globally, M for India.
- **Effort:** 1–2 weeks on top of the operations layer, which you need anyway; ₹0 LLM.
- **Arena:** T0 (as designed) vs T1 (multi-speed); correlation with the equity books < 0.2.
- **Flag:** expect 12–24-month dead spells. Never let the LLM veto trend entries.

**8. Exit brackets in the counterfactual outcome engine (COE) before season 1 is frozen.**
- **Change:** test three brackets on identical entries:
  - B0: the current default;
  - B1: no partial, trail to 14:55 on trend days;
  - B2: a 25-minute time stop, then B1.

  Profit protection ("P&L fell to 50% of peak") should block new risk, not flatten positions whose stops are already in profit.
- **Effect:** ±0.1R; the arena decides.
- **Evidence:** thin (US ORB right tail, M).
- **Effort:** 3–5 days, compute only.
- **Flag:** likely overfit if chosen on fewer than about 300 paired entries.

**9. O1 (intraday long index options) validated offline first.**
- **Change:**
  - Test 10 years of Nifty 1-minute data: breakout continuation, and whether the first 30–60 minutes predict 14:30–15:10.
  - Reprice in options with Black-Scholes and a spread model.
  - Trade the next weekly contract, ITM at Δ0.6–0.7, with a hard flat at 15:10.
  - O1 shares intraday sleeve A's daily loss limit (correlation about +0.5).
- **Effect:** about ₹60k a year at +0.1R; nothing lost at 0R.
- **Evidence:** L for India (I found no study).
- **Effort:** 1–2 weeks; no LLM.
- **Arena:** beat a random-time placebo, and test before and after 3 Aug 2026 (the closing auction) separately.

**10. Auction execution and close-based stops for all overnight stock positions.**
- **Change:**
  - Enter and exit F&O names at the closing auction; slice non-F&O names over 15:00–15:30.
  - Stops are judged on the close, with a catastrophic intraday stop re-armed every morning.
- **Effect:** 5–10 bps saved per side, and paper ≈ live.
- **Effort:** small change to the order system and paper broker.
- **Flag:** auction imbalance on event names (cap limits at ±1% of the indicative price); only 2 months of auction history.

**Flagged and deliberately excluded from the top 10:**
- **O4 live trading:** negative skew, and it duplicates your existing selling agent.
- **O5 live trading:** stock-leg spreads of 2–4%.
- **Results IV-crush selling:** US evidence goes the other way.
- **Scalping ML:** no positive rule base yet.
- **Raising R to 0.5% before q10 > 0:** a 23% chance of hitting the 25% drawdown in the portfolio reviewer's simulation. This is dangerous.

## 4. Season-1 paper portfolio

Each standalone book trades its own ₹10L for evaluation. The composite book PF applies the budget below.

**The 9 cells:**

| | Scalp | Intraday | Swing / positional |
|---|---|---|---|
| **Stocks** | Cut; keep recording depth | **Keep, narrowed** (catalyst / in play, 09:20–10:45) | **Build now (ES)** |
| **Options** | Cut | **O1** offline test, then rules paper; O2 research only | **O4** counterfactual only; **O5** spreads as a shadow vehicle |
| **Commodities** | Cut | C2 paper log, no risk | **Trend** (weeks to months, not 2–10 days), rules |

**Risk budget (PF, worst day stays 3%):**

| Sleeve | Decided by | Budget (2% / 1% variant) | 1.5% / 1.5% variant | Status |
|---|---|---|---|---|
| A: intraday catalyst plus O1 | LLM book L on catalysts; rules (R) and Haiku (Hk) books | Daily loss limit 1.2%, R 0.25%, ≤ 3 entries; O1 sub-cap 40% | DLL 1.0% | Core |
| O2 expiry fly | Rules | Max loss ≤ ₹3k on expiry days | Same | Research |
| ES event swing | LLM | Overnight stress 0.6% | 0.9% | Core, new |
| MCX trend | Rules | Overnight stress 0.3%, sleeve volatility 4% | 0.45%, 6% | Core |
| O4 VRP / O5 spreads | Rules plus LLM veto / shadow | 0.1% (shadow accounting) | 0.15% | Counterfactual |
| Treasury | — | Idle ₹4–6L accrues about 6% (benchmark) | — | Always |

**Your existing options-selling agent is the largest unmanaged tail in your total book.** If it trades real money, either feed its positions into the overnight scenario stress (read-only), or ring-fence its capital and leave it outside this 3%.

**LLM budget in results season** (about ₹4.5k off season):

| Line | ₹ a month |
|---|---|
| ES: Sonnet deep reads, concall second reads, end-of-day rank and management | 2,200 |
| Intraday L: catalyst moments plus a Sonnet game plan | 2,200 |
| Haiku scoring all moments (K6 test) | 500 |
| Jev triage (filings, MCX circulars) | 100 |
| Option vetoes (O4/O2) | 100 |
| Reserve | 600 |
| **Total** | **≈ 5,700** |
| One-off replay | 3–5k |

**Cut or defer:**
- chart twin V;
- the separate materiality route;
- LLM calls on pattern-only triggers;
- scalping as a sleeve, the LightGBM filter, and order-flow index scalps;
- the index-lead catch-up setup (SC2) and wall/absorption setups;
- intraday relative-strength pairs;
- MCX C2 and EIA trades as live risk;
- natural gas until the reserve is 1.5%;
- stock futures in any form;
- routine index or crude put hedges;
- the ₹15–25k a month cloud stack (keep infrastructure ≤ ₹3k a month);
- MCX and index-option LLM books;
- new intraday setups beyond E3.

**Build E3** (news-shock first pullback) within about 3 weeks so it catches the rest of the Q2 season.

## 5. Changes to kill and success criteria, and to the timeline

**Event swing**
- Judge it on events, not trades. Drop the 200-trade gate for swing.
- **Kill** at 1,000 events if IC < 0.03, or if its 90% upper bound is < 0.07.
- **Success** at 2,000 events if:
  - IC ≥ 0.07 in both the replay and the forward sample, and in both halves;
  - the top fifth nets ≥ +0.4% per trade after costs;
  - the placebo fails;
  - live money additionally needs ≥ 100 trades with LCB > 0.

**Intraday L**
- Keep the week-8 IC screen, with CATALYST-mode IC as the primary metric. Pre-register it now, before the arena starts.
- Replace the "+0.15R" money gate with: q10 of net expectancy **after realistic friction and the LLM cost per trade** > 0.
- Plan on +0.05–0.08R.

**Ramp and ladder**
- No R above 0.25% until q10 > 0; full R needs about 400–600 trades (8–12 months).
- The week-14 cost kill applies.
- Remove the 0.35× and 0.25× ladder rungs for intraday; drop the sleeve instead.

**Options**
- **Stress tests before any O4 or O2 capacity:**
  - replay 4 Jun 2024 (Nifty −5.9% at the close, about −8.5% intraday, VIX about +40%; H);
  - Mar 2020, 5 Aug 2024 and Apr 2025;
  - a synthetic overnight Nifty −8% with VIX +60% and spreads ×5;
  - check for an expiry-day margin (ELM) or SPAN spike forcing liquidation;
  - run the scenario jointly with ES and your existing selling agent.
- **O4 kill:** 3 max-loss units in a rolling quarter, or any realised loss above the modelled maximum.
- **O1:** a 60-trade sequential test (SPRT) against the placebo.

**MCX**
- Drop the "≥ 20 trades" and trade-count SPRT gates.
- Gate on the backtest instead:
  - net Sharpe ≥ 0.3;
  - positive in ≥ 60% of rolling 3-year windows;
  - a parameter plateau;
  - long and short sides each non-negative in USD.
- Then 8–12 weeks of clean paper operations (zero missed rolls or delivery cutoffs).

**Timeline**

| When | What |
|---|---|
| Week 0–1 | Start recording all filings and daily bars now: the Q2 season is under way and it is your forward sample. |
| Week 1–2 | Friction gate, opportunity gate, base-rate map, options overnight/intraday split, MCX backtest. |
| By about 26 Oct | Freeze the ES prompt. |
| By about 9 Nov | Replay verdict; ES running in paper. |
| About 7 Dec | Week-8 intraday IC screen. |
| Mid-December | ES interim verdict at 1,000 events. |
| About 18 Jan 2027 | Week-14 cost kill. |
| Feb–Mar 2027 | ES final verdict after the Q3 season. Earliest live step at L0/L1 only for sleeves with q10 > 0. |

## 6. Honest expectations

Composite book PF, ₹10L, paper year 1 [J]:

| Scenario | Probability | Net return, including LLM and infra | Max drawdown |
|---|---|---|---|
| No LLM sleeve has edge (IC ≈ 0–0.04); MCX and options roughly flat | ~55% | −4% to +3%, or −1% to +6% with treasury accrual | 6–12% |
| One catalyst sleeve real (IC ≥ 0.08), MCX positive | ~25–30% | +8% to +15% | 5–10% |
| Bad regime plus no edge | ~15% | −8% to −12%, stopped by the ladder or cost kill by month 4–5 | 12–18% |

**Two caveats on the numbers:**
- The chance of hitting the 25% drawdown stays under 2% only if R stays at 0.25% and the ladder is active.
- **Haircut any paper result by 30–50% for live trading** in year 2: fills, decay of the drift edge as more traders use LLMs, and auction behaviour.

**Rely on a sleeve only when all of these hold:**
1. Replay and forward IC agree in sign and size.
2. q10 > 0 after realistic friction and LLM cost, and the sleeve beats both its placebo and the roughly 6% treasury yield.
3. It has 400 or more trades for full R (100 or more for ES at minimum size).
4. The live-minus-paper shortfall on small live probes (L0) is ≤ 0.05R.
5. It has survived at least one adverse episode (VIX above 20, or a Nifty month of −5% or worse) with zero breaches of the risk rules.
6. Its stress tests pass jointly with your existing options agent.

Until then, success for year 1 means a cheap, fast answer to one question: does the LLM add net edge where it reads text? Making money is not the year-1 test.

**Sources (verified today):**
- Bhat, Pandey & Rao 2024, day vs night option returns in India: [vLex](https://law-journals-books.vlex.com/vid/the-asymmetry-in-day-1115554990)
- Muravyev & Ni, day vs night option returns in the US: [IDEAS](https://ideas.repec.org/a/eee/jfinec/v136y2020i1p219-238.html)
- NSE closing auction session from 3 Aug 2026: [Motilal Oswal](https://www.motilaloswal.com/learning-centre/2026/8/introduction-of-closing-auction-session-cas-from-03-august-2026), [HDFC Sky](https://hdfcsky.com/news/nse-to-extend-equity-derivatives-trading-by-10-minutes-from-august-3-with-launch-of-closing-auction-session)
- Zerodha collateral margin for MCX: [Z-Connect, 10 Dec 2024](https://zerodha.com/z-connect/updates/trade-commodity-fo-on-mcx-and-nse-using-collateral-margin)
- Upstox Plus ₹30 vs Basic ₹20, and 30-level depth for Plus users: [Upstox help](https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/), [Upstox community](https://community.upstox.com/t/market-depth-30-increase-limit-for-more-than-50-instruments/13398)
- Kotak Neo zero-brokerage API orders: [Kotak Neo](https://www.kotakneo.com/about-us/media-and-press/kotak-neo-introduces-zero-brokerage-zero-fee-trade-apis-for-retail-traders/)
- OpenRouter batch pricing (third-party): [aireiter](https://aireiter.com/blog/openrouter-batch-api-pricing-guide)
- SEBI FY26 F&O study (87.7% lost, ₹91,685 cr): [Open Magazine](https://openthemagazine.com/business/sebi-fo-loss-study-explained-why-9-in-10-retail-traders-lost-91685-crore-in-fy26)
- Kim, Muhn & Nikolaev withdrawn: [arXiv v3](https://arxiv.org/abs/2407.17866v3)
- Market intraday momentum (US, no Nifty study found): [Alpha Architect](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)

The other citations come from the six specialist reviews.

**Design docs:**
- /home/user/auto-trading/docs/design/trading-system-design.md
- /home/user/auto-trading/docs/design/ai-trader.md