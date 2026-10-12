# Portfolio and sleeves: the profitability plan (v1)

**Status:** design, 2026-10-12. It is part of system design v0.4.
**Precedence:**
- **This document decides** which sleeves run, how risk and the LLM budget are split between them, how overnight risk is measured, how size ramps, and the season-1 timeline.
- [`ai-trader.md`](ai-trader.md) decides how the LLM makes decisions inside a sleeve.
- [`trading-system-design.md`](trading-system-design.md) holds everything else.
- This document also decides the kill and success criteria for each sleeve (§12).
- Where they conflict on the points above, this document wins.

**Why it exists:** the owner asked, "is this fine, or what would make it profitable?" across stocks, options and commodities at scalping, intraday and swing horizons. Six specialist reviews and a red-team ruling answered (reports 19–25 in [`docs/research/`](../research/)).

---

## 0. Verdict and decisions at a glance

**Verdict: the chassis is fine; the allocation is not.** These pieces are better than most retail systems and stay:
- code owns risk;
- paper fills are conservative;
- kill criteria are pre-registered;
- the arena compares books paired on the same moments;
- a drawdown ladder.

As specified in v0.3, though, the system would most likely lose money net of costs and LLM spend in year 1:
- About 70–75% of the effort, most of the LLM budget and two thirds of the worst-day budget go to the weakest cell: **minute-scale intraday cash**.
  - Its trigger pool's base rate is negative, about −0.10 to −0.15R with realistic costs.
  - Real friction at the minimum stop is 0.25–0.32R, not the 0.2R the gate assumed.
  - It would need elite selection skill (IC ≈ 0.15) to reach the old +0.15R target.
- Three cells where evidence, cost and LLM strengths line up are deferred or starved:
  - event-driven stock swing;
  - commodity trend;
  - the overnight index-option premium.

| # | Decision |
|---|---|
| P1 | **Keep the chassis; move effort and risk to where the evidence is.** The rest of this table says how. |
| P2 | **Season 0: freeze the ES and intraday-catalyst prompts first (about 26 Oct), then replay the post-cutoff period (1 Jul – 9 Oct 2026) with them.** Replay results never feed back into season-1 prompts. It is the first honest measure of LLM skill, available in about 3–4 weeks instead of 8–14. |
| P3 | **Event swing (ES) becomes a first-class LLM book.** The LLM reads results, orders and concalls after the close and buys confirmed continuation at the next day's close, holding 2–10 days. This is the LLM's best-evidenced skill, at about half the friction of intraday. |
| P4 | **Intraday is narrowed to stocks in play.** A hard opportunity gate, an honest friction gate (stop floor about 75–80 bps at R = ₹2.5k), at most 2 exit legs, at most 3 entries a day, trading 09:25–10:45 (no new entries 11:00–13:30), shorts as first-class setups, and exit brackets tested before the freeze. **The LLM is called only on catalyst moments**; everything else goes to the free rules and Haiku books. |
| P5 | **Commodity trend becomes a core diversifying sleeve.** Rules only (multi-speed, volatility-targeted, crude + gold + silver), gated on a 30-year backtest. ₹0 LLM. |
| P6 | **Options:** O1 (intraday long index options) is validated offline first. O2 (expiry-day fly) is demoted to research. O4 (overnight premium) runs as a counterfactual book only. O5 (debit spreads) is a shadow vehicle for swing views. Before any selling sleeve goes live, the options cost stack has to be fixed. |
| P7 | **Scalping is cut as a sleeve.** The depth recorder keeps running. A fast-exit variant of the news setups is the only scalp-like trade. |
| P8 | **A portfolio layer:** a composite book, scenario-based overnight stress, funding only where the 10th percentile of the edge estimate (q10) is above 0, an R ramp at ⅛ Kelly on q10, dropping a sleeve instead of shrinking everything, and a week-14 cost kill. **The overnight split matters more than it looks:** at 2% + 1% the stress check holds ES to about half the capacity its profit estimate assumes (§8). |
| P9 | **The chart twin V is deferred to season 2.** Its ₹1.9k a month funds ES. The separate materiality route (Haiku → Sonnet, about ₹270 a month) is cut: Jev triage scores materiality, and deep reads happen in ES. |
| P10 | **Cost programme:** realistic friction, fewer trades, LLM spend ≤ 15–20% of a sleeve's expected gross once the sleeve is funded live (in paper season 1 the ES and L lines are research spend above that ratio, bounded by the hard cap and the week-14 cost kill), cheap execution venues, infrastructure ≤ ₹3k a month, closing-auction execution for overnight positions, and yield on idle cash. |
| P11 | **A base-rate map in code decides which trade pools are worth LLM calls.** Pools are chosen by evidence, never mined for new setups. |
| P12 | **Honest expectations.** Year 1 answers one question cheaply: does the LLM add net edge where it reads text? Making money is not the year-1 test. |

---

## 1. The edge map

**Friction** is the round-trip cost plus slippage as a share of R at the sleeve's typical stop. Evidence ratings: **H** high, **M** medium, **L** low.

| Cell | Best-documented edge | India evidence | Friction | What the LLM adds | Decision |
|---|---|---|---|---|---|
| Stocks × scalp | Order-flow persistence, owned by colocated players | L. 71% of intraday cash traders lost money in FY23 (H) | 0.2–0.5R | None | **Cut**; keep recording |
| Stocks × intraday | Second-leg news continuation; opening-range breakout on stocks in play | L–M. No India study. The US stocks-in-play ORB paper charged commissions only; an index ORB replication reproduced the gross edge but netted ≈ 0 | 0.15–0.32R | Medium: judging catalyst size, yes; reading patterns, no | **Keep, narrowed** (§3) |
| **Stocks × swing (2–10 d)** | Post-event and news drift; short-horizon momentum | M. Drift after bad news lasts over a week; post-earnings drift (PEAD) is contested and decaying | **0.07–0.10R** | **High:** reads long filings at the end of the day; latency is irrelevant | **Build now** (§4) |
| Options × scalp | Cost advantage only | L. 87.7% of individual F&O traders lost money in FY26 (H) | 0.04–0.08R plus theta | None | **Cut** |
| Options × intraday | O1: intraday momentum (no Nifty study found). O2: expiry-day theta | L. Short Nifty options *lose* intraday on average (Bhat, Pandey & Rao 2024, M-H) | 0.03–0.1R | Low: event veto | O1 offline test; O2 research (§6) |
| Options × swing (1–5 nights) | The index volatility risk premium (VRP), earned **overnight** | M-H (Bhat et al. 2024) | 15–20% of the credit at ₹30/order | Low–medium: event veto | **Counterfactual only** (§6): the owner has a separate selling agent (not running now) that would carry this tail |
| Commodities × scalp | None at retail | L | 0.4–0.8 × 1-min σ | None | **Cut** |
| Commodities × intraday | Evening crude breakout; EIA trades | L | 0.15–0.5R | Low | Paper log only |
| **Commodities × positional** | Time-series momentum: a century of evidence, positive in every decade (H). MCX survives costs (M) | M (MCX is priced off CME) | **≈ 0.03R** | Low: calendar, shrink-only flags | **Core diversifier** (§5) |

**Why the pool's base rate decides everything.** The expected result of a taken trade is about μ₀ + 1.87ρ, where μ₀ is the trigger pool's base rate and ρ is the LLM's ranking skill (IC).
- **Intraday triggers:** μ₀ ≈ −0.10R, so +0.15R needs ρ ≈ 0.13–0.15.
- **Swing events:** friction is lower and the pool is near zero, so the same +0.15R needs ρ ≈ 0.05–0.08.

The same LLM skill pays roughly twice as much where the pool isn't negative.

---

## 2. The season-1 portfolio of sleeves

| Sleeve | Instrument × horizon | Decided by | Risk budget (2% / 1% split) | Status |
|---|---|---|---|---|
| **A: intraday catalyst** (+ O1 later) | Cash MIS, 09:25–10:45 mainly | LLM book L on catalyst moments; rules book R and Haiku book Hk on all moments | Daily loss limit 1.2%, R = 0.25%, ≤ 3 entries a day; O1 sub-cap 40% of A once validated | Core |
| **ES: event swing** | CNC long, 2–10 days | LLM | Overnight: priority share 0.6% of the 1% stress budget (§8) | **Core, new** |
| **T: commodity trend** | MCX minis and micros, weeks to months | Rules | Overnight: priority share 0.3% (§8); sleeve volatility 4% a year | Core |
| O2: expiry-day fly | Nifty/Sensex, expiry afternoon | Rules | Max loss ≤ ₹3k on expiry days | Research |
| O4 / O5 | Overnight VRP / debit spreads | Rules (+ LLM veto) / shadow | Share 0.1% (counterfactual accounting only) | Counterfactual |
| Treasury | Liquid fund / LIQUIDBEES | — | Idle ₹4–6L earning about 6% | Always |

**Paper evaluation:**
- **Standalone books:** each trades its own full virtual ₹10L, as before.
- **Composite book PF** (§8): applies this allocation through the real risk engine.
- **A second PF variant:** runs a 1.5% intraday / 1.5% overnight split at no cost (shares become ES 0.9%, T 0.45%, O4 0.15%; sleeve A's daily loss limit 1.0%, i.e. its sub-cap rises to two-thirds of the 1.5% DLL; T's volatility target 6%). The owner chooses at go-live (§15).
- **Overnight shares are priorities, not caps.** The binding rule is the joint scenario check in §8: a sleeve can use most of the budget in scenarios where the others lose nothing. The shares decide who gives way when the check binds.

**The owner's separate options-selling agent** (not running now, per the owner) would be the largest unmanaged tail in the owner's total book. If it trades real money, either feed its positions read-only into the overnight scenario stress, or ring-fence its capital outside this system's 3% worst day.

---

## 3. Sleeve A: intraday, narrowed to stocks in play

This changes how [`ai-trader.md`](ai-trader.md) is used for intraday equity.

1. **Hard opportunity gate.** A new equity entry needs one of:
   - catalyst materiality ≥ 60, or
   - a gap ≥ 1 ATR from the pre-open price **and** RVOL15 ≥ 3.

   Shorts are F&O names only. If nothing qualifies by 10:30, the equity book stands down. **Zero-trade days are allowed and expected.** The thresholds are fixed now and are not tuned on paper.
2. **Honest friction gate.**
   - **The estimate:** friction = expected cost over all exit paths, using live spread from recorded depth (by symbol and time of day), the paper model's stop slippage (5 bps; 20 bps on news), and brokerage per executed order.
   - **The limits:** still ≤ 0.2R on that realistic number. In practice that means a **stop floor of about 75–80 bps at R = ₹2.5k** (65–70 bps at ₹5k), a spread no wider than 0.08 × the stop, and **at most 2 exit legs** (50% at T1, 50% trailed).
3. **Time windows.**
   - **Primary window 09:25–10:45. No new equity entries 11:00–13:30.** (Report 24 says 09:20; no tactic can enter before 09:25, main design §8.)
   - 13:45–14:40 only for leaders already in play, on a confirmed trend label.
   - **09:25–09:31:** only opening-drive pullbacks (T7) pre-approved by the **09:12 pre-open call** for the top 2 catalyst names, so the first entries don't wait for the 09:31 open read. (OR15 and RVOL15 complete at 09:30; opening-range acceptance, T3, can't fire before about 09:40 and is approved at the open read.)
4. **Shorts are first-class:**
   - setups: failed rally to VWAP, prior-day-low break and retest, first bounce after a results miss;
   - negative catalysts weigh as much as positive ones: misses, guidance cuts, blocks at a discount, regulatory action, pledge invocations;
   - negative reads from the ES pipeline feed these intraday shorts, because cash can't be shorted overnight and stock futures are too lumpy at ₹10L.
5. **The LLM is called only on catalyst moments.**
   - L's pre-registered primary metric becomes **CATALYST-mode IC**.
   - Generic momentum and fade moments go only to the free rules book R and to the Haiku shadow book Hk, which scores *all* moments so the general IC is still measured.
   - The model-tier test K6 (Haiku vs Sonnet) becomes the **economic gate:** if Haiku's CATALYST-mode IC is at least Sonnet's − 0.02 with ≥ 85% take/pass agreement (K6, [`ai-trader.md`](ai-trader.md) §16), Haiku takes over at the next season boundary.
6. **Exits tested before the freeze.**
   - **Brackets:** the counterfactual outcome engine (COE) compares three on identical entries:
     - B0, the default: 50% at T1 and 50% trailed on the 5-minute swing, 45-minute time stop. With at most 2 legs and trail legs counted at ≤ 2R, T1 must be at least 1 + 5 × friction_R to clear the blended-target gate (about 1.75R at 0.15R), so v1.1's "half out at 1R" is retired (main design §5);
     - B1, no partial, trailing on the 15-minute swing (or a 1.5 × ATR(15m) chandelier), held to 14:55 on trend days;
     - B2, exit if not at +0.5R by 25 minutes, otherwise B1.
   - **Choosing one:** decide on at least 300 paired entries.
   - **Profit protection changes:** "P&L fell to 50% of the peak" now **blocks new risk** but no longer flattens positions whose stops are already in profit.
7. **Build E3 next** (news-shock first pullback), within about 3 weeks so it catches the rest of the Q2 results season. Restrict E2 (VWAP reclaim) to catalyst names and trend-day leaders.

**Plan on 0R as originally specified, and +0.03–0.08R per trade after these fixes if catalyst IC is real** (report 25; its summary table says +0.05–0.08R).

---

## 4. Sleeve ES: event swing (new LLM book)

**Universe:**
- Nifty 500 plus liquid names with median turnover ≥ ₹10 cr.
- Excluded: price bands below 10% (unless F&O), ASM/GSM/ESM, T2T, listed less than 30 days ago.
- No new entry within 3 sessions before the stock's own results.

**Catalysts, in priority order:**
1. **Quarterly results.** Code computes surprise against the company's own trend, margin change, the options-implied move (F&O names), 10-day pre-event drift and peer read-across. The LLM judges quality (one-off or recurring) and guidance.
2. **Orders**, measured as value ÷ TTM revenue, ÷ order book, ÷ market cap and ÷ 20-day turnover.
3. **Concall "second read" at T+1 to T+5** (audio within 24 h, transcript within 5 working days): changes in tone and guidance. This is the purest LLM advantage.
4. **Rating changes, promoter or insider buying (PIT/SAST), block and bulk deals.**
5. **Sector and policy read-across** to second-order beneficiaries.

**Pipeline:**
1. A rule pre-filter on filing categories.
2. **Jev 1.13 triages every filing** (about $0.00002 each, 0.5–0.9 s), with Haiku as fallback.
3. Code builds the numeric event card.
4. **Sonnet 5.5 (low effort) deep-reads 10–25 events a day** and returns an `EventScore`: `exp_abn_ret_5d`, `p_up_5d`, direction, `surprise_quality`, `guidance_delta`, `priced_in`, invalidation, numbers by ID only. **Every event is scored, traded or not.**
5. After the close, one "rank and take ≤ k of N" call applies portfolio limits.

**Entry:**
- **Never trade the day-0 reaction** (the non-tradable part).
- Buy at the **day-1 close** if day 1 holds at least 50% of the day-0 move, closes in the top half of its range, and volume is at least 2× normal. For results released after the close, the first session after the release is day 0 (its gap and close are the non-tradable reaction) and the next session is day 1.
- **Variants scored free in the arena:** day-2 close, and day-1 open (pre-open auction).

**Execution:**
- F&O names: limit orders entered from 15:20 into the **closing auction** (no entry, modify or cancel 15:15–15:20; matching by 15:35; it sets the official close), capped at ±1% from the indicative price.
- **Confirmation timing:** the day-1 test is checked at about 15:15–15:20 on the last continuous-session price and the day's range so far, because the official close isn't known until matching. Close-based stops are judged on the official close and executed in the next session's auction.
- Non-F&O names: sliced over 15:00–15:30.
- Paper therefore matches live almost exactly.

**Exits:**
- **Initial stop:** the event-day low minus 0.25 ATR, capped at 1.5 × ATR14. It is **judged on the close** and executed in the next auction. A catastrophic intraday stop at twice that distance is re-armed every morning after 09:15. SL orders are cancelled at 15:15 and not accepted in pre-open, so close-based stops are also the honest choice.
- **Profit and time:** one-third off at +2R; trail the rest on a close below the 10 EMA after day 3; time stop at day 10. Never hold through the stock's own results.
- **News on a held name:** a new filing triggers a Sonnet management call; otherwise Haiku reviews each held name once a day.
- **Calendar:** halve the book before weekends or binary events when the geopolitical score is 2 or higher.

**Sizing:**
- **Positions:** per-name stress ≤ 0.25% of equity (₹2.5k), with shock = max(2 × P95 overnight gap, floor 5% large cap / 7% mid cap / 10% small cap, +2% if the geopolitical score is ≥ 2). That allows about ₹25–50k a name. (Reports 20 and 25 quote ₹35–70k, but the 5% floor caps a large cap at ₹50k; report 19's option of a 0.4% per-name cap would allow up to ₹80k.) At most 6 names, at most 2 per sector.
- **The joint scenario stress (§8) usually binds first:** at the 2% + 1% split it holds the sleeve to about ₹1.5–1.8L (3 names of ₹50k or 5 of ₹35k), and to about ₹0.8–1L when T holds its share; at 1.5% + 1.5%, about ₹2.75L (5–6 names). The old 20/50-DMA trend gates become features, not gates.
- **Instrument:** **long-only cash (CNC) in season 1.** No stock futures: one lot is several lakh of notional, so a 7% gap costs ₹25–50k.
- **Debit spreads:** O5 runs as a paired shadow vehicle: each long pick as a bull call spread, and each negative read on an F&O name as a bear put spread (§6).
- **Hedges:** index puts only before high-risk weekends and binary events; a continuous hedge would cost about as much as the sleeve earns.

**Arena books:**

| Book | Definition |
|---|---|
| **ES-L** | LLM top picks, within risk limits |
| ES-R | Rules baseline: day-1 abnormal return ≥ 1.5σ, volume ≥ 3×, positive surprise against the company's own trend |
| ES-U | Take every event (the pool mean) |
| ES-P | Random picks at L's take rate (placebo) |
| ES-M | Names masked (a check against memorised company identity) |
| ES-J/Hk | Jev or Haiku as the scorer |
| ES-O5 | The same signals as debit spreads (shadow): bull call spreads for long picks, bear put spreads for negative reads on F&O names |

**Primary metric:** the date-clustered Spearman IC of `exp_abn_ret_5d` against the realised 5-day abnormal return after costs, across **all** scored events. Kill and success rules are in §12.

**Expected** (before its ~₹2.2k a month LLM cost unless stated):
- **About 20 trades a month** (report 20's assumption, about ₹2.5–3L in the book): +₹4–11k a month if IC is 0.08–0.12; about −₹6k a month including LLM cost if IC ≈ 0. That capacity needs the 1.5% + 1.5% split (§8).
- **At the 2% + 1% split** the stress check holds ES to about ₹1.5L (less when T holds its share), roughly 8–12 trades a month in results season. Expect about half: +₹2–5k a month before LLM cost if IC is 0.08–0.12, i.e. roughly break-even to +₹3k after its ₹2.2k LLM cost.
- **Breakeven IC:** about 0.04–0.05 on trading costs alone, at any capacity. After the fixed LLM cost it is about 0.06 at full capacity and about 0.08–0.10 at 8–12 trades a month [J].
- **The verdict is unaffected by capacity:** the signal is judged on every scored event (§12), not on trades.

Trades: 15–30 a month in results season at full capacity (8–12 at 2% + 1%), 5–12 off season.

---

## 5. Sleeve T: commodity trend (rules only)

**Signals:**
- Three EWMA crossovers (16/64, 32/128, 64/256 days) plus a normalised 40/80/160-day breakout, equally weighted.
- Combined into a forecast capped at ±2.

**Sizing:**
- **Volatility:** a 35-day-span EWMA, blended 30% with 10-year volatility.
- **Position:** lots = forecast × (instrument risk target ÷ daily σ per lot), rounded.
- **Buffer:** trade only when |desired − held| ≥ 0.75 lot.
- **Targets:** sleeve volatility of 4% a year at L1 and 6% at L3; instrument weights 1/N with a diversification multiplier of about 1.4.

**Removed from C1:**
- the ADX and EMA50 filters;
- the no-Friday rule;
- the expiry-proximity skip (enter in the next contract instead);
- "crude or gold, not both" (replaced by the scenario stress, §8).

| Contract | Cap | Rule |
|---|---|---|
| CRUDEOILM | 1 lot (2 only if annualised volatility < 30%); at a ₹85k lot it fits the stress check only at 1.5% + 1.5%, and 2 lots don't fit at today's price | Roll at T−6 sessions or when next-month OI exceeds front, both legs in the 19:00–22:00 window. Never near expiry (the April 2020 contract settled negative). |
| Gold | GOLDTEN 1 lot (1.5% + 1.5% only), or GOLDPETAL 6–12 lots in one order (above about 8 lots, 1.5% + 1.5% only) | Compulsory delivery: roll at broker cutoff − 2 sessions |
| Silver | SILVER100, 2–4 lots | Only if the spread is ≤ 2 ticks; SILVERMIC only when one lot's σ ≤ 1.5× the target |
| NATGASMINI | 0 | Only with a 1.5% overnight reserve and a backtested marginal Sharpe > 0.05 |

**Gold and silver** (correlation 0.75–0.85) are one cluster, capped at 50% of sleeve risk.

**What fits the overnight budget (§8):**
- **Crude:** one CRUDEOILM lot (about ₹85k) loses about ₹10.2k long in the −12% de-escalation scenario (G−) and about ₹12.75k short in the +15% escalation scenario (G+). Either way that is more than the whole 1% budget on its own, so **at 2% + 1% T cannot hold crude at today's price** (a long lot fits only below about ₹83k, a short lot below about ₹67k). Two lots never fit at today's price under either split.
- **Gold:** GOLDTEN (about ₹11.9k in the duty-cut scenario D) does not fit at 2% + 1%; GOLDPETAL fits up to about 8 lots (about ₹1.2L notional).
- **So at 2% + 1% T is the gold/silver cluster only**, capped at 50% of sleeve risk, and only while ES leaves room (§8). The 1.5% + 1.5% variant fits a crude lot alongside a smaller ES book.

**Gap control without paying for hedges:**
- **Event shrinks:** halve positions before OPEC+ weekends, the Budget and duty news (when `duty_change_risk` is high), and long weekends.
- **Disaster stop:** a wide stop at 4–5 × ATR, re-armed daily **after 10:00** (spreads are wide in the morning session); if price opens through it, a protected exit after the first 15 minutes.
- **No routine puts.** A monthly crude put costs more than the expected trend profit.

**EIA:** positional holdings are **exempt** from the EIA flatten, because the move is already inside the gap sizing. The flatten still applies to intraday MCX positions.

**Crude carry tilt:** annualised (front − next) ÷ front, volatility-scaled, at 20–25% of crude's forecast weight. No carry signal on bullion (its contango is just interest rates) and no seasonality.

**LLM role:**
- Jev parses MCX circulars and broker bulletins into the contract calendar; code validates it.
- Shrink-only event flags.
- **No direction and no veto on trend entries for at least 12 months.** Trend P&L is concentrated in a few big moves.

**Gate:** a backtest on 30+ years of CME × USDINR plus MCX bhavcopy, with **duty-neutral bullion series** (the 6% → 15% duty step otherwise looks like a trend). It must show:
- net Sharpe ≥ 0.3;
- positive in ≥ 60% of rolling 3-year windows;
- a parameter plateau (±50% speed changes move Sharpe by less than 0.1);
- longs and shorts each non-negative in USD terms.

Then **8–12 weeks of clean paper operations** (zero missed rolls or delivery cutoffs, 100% stop coverage). Paper proves operations; it cannot prove the edge at 20–40 entries a year.

**Arena:** T0 (C1 as specified, the control) against T1 (multi-speed), plus T1+C (carry tilt) and T1+E (shrink flags). Targets: correlation with the equity books < 0.2; implementation shortfall against a same-day backtest < 10% of gross; realised against modelled roll cost tracked (reports 22 and 25).

**Expected:** +₹10–25k a year at Sharpe 0.25–0.4 when crude fits (the 1.5% + 1.5% split); roughly +₹3–9k a year at 2% + 1%, where T runs bullion and silver only [J]. Uncorrelated with equities, with 12–24-month flat spells.

---

## 6. Options

**The day/night fact that reshapes the options module:** in Nifty, short-option sellers earn the premium **overnight**, and short options lose on average **intraday** (Bhat, Pandey & Rao, *J. Futures Markets* 2024; the US matches, Muravyev & Ni 2020). **Brokerage, not STT, is the binding options cost:** an 8-order condor at ₹30 + GST is about ₹283, or 15–20% of a 1-lot credit.

| ID | Strategy | Season-1 status | Rules |
|---|---|---|---|
| **O1** | Intraday long index options on trend days | **Offline validation first**, then rules paper | Test 10 years of Nifty 1-minute data first: breakout continuation, and whether the first 30–60 minutes predict 14:30–15:10. Reprice in options with Black-Scholes plus a spread model. Trade the **next weekly** contract, ITM at Δ0.6–0.7, when the current one has ≤ 2 days left. Hard flat at 15:10. Shares sleeve A's daily cap (correlation about +0.5). Gate: a 60-trade SPRT against a **random-time placebo**, tested separately before and after the closing auction began (3 Aug 2026). |
| **O2** | Expiry-day iron fly | **Research** | 1 set, max loss ≤ ₹3k. A 2-leg credit-spread variant. An **unconditional twin** that sells every eligible expiry. Shorts flat by 15:00. Expiry day is also where large players have moved index levels (SEBI's Jane Street order), so treat results with suspicion. |
| **O4** | Overnight defined-risk VRP | **Counterfactual book only** | Enter Wednesday or Thursday 14:30–15:00 for the next Tuesday expiry. Shorts at about Δ0.15 with 100-point wings. Exit at 50% of credit or Monday 15:00, so it never meets expiry-day margin or auction settlement. Enter only if IV ÷ forecast RV ≥ 1.15, VIX is not up more than 15% over 5 days, and no binary event falls in the window. Broken-wing butterflies, never naked ratios. **Live only by explicit owner decision,** because the owner's separate selling agent would carry the same tail if it runs. |
| **O5** | Debit spreads as the swing vehicle | **Shadow, paired with ES** | Index first, then the top ~20 liquid stocks. At least 7 sessions to expiry; never in expiry week (physical settlement). ES-O5 books each ES long pick as a bull call spread and each negative ES read on an F&O name as a bear put spread. Bear put spreads are preferred where a short view exists, because they sell the rich side of the skew. Debit = max loss, counted against the overnight stress. |

**Do first, at no cost:** split the recorded option-chain P&L for ATM and OTM weeklies into overnight (15:25 → 09:20) and intraday segments. That confirms or refutes the day/night finding on our own data, and decides O2 and O4 together.

**Cost stack** (before any selling sleeve goes live):
- Find a zero- or low-brokerage API venue for the options account and verify static-IP and algo-ID support.
- Use 2-leg structures, and let OTM legs expire instead of buying them back.
- Put all lots in one order.
- Run every options paper book under two tariffs: ₹30 and ₹0.

**Stress tests before any O2 or O4 capacity:**
- replay 4 Jun 2024 (Nifty −5.9% at the close, about −8.5% intraday, VIX about +40%), Mar 2020, 5 Aug 2024 and Apr 2025;
- a synthetic overnight Nifty −8% with VIX +60% and spreads ×5;
- an expiry-day margin (ELM/SPAN) spike that forces liquidation;
- all run jointly with ES and, if it is running, with the owner's separate selling agent.

**O4 kill:** 3 max-loss units in a rolling quarter, or any loss above the modelled maximum.

**LLM role in options:**
- A veto and shrink before events and risky weekends;
- choosing a structure from a closed menu;
- ranking event uncertainty for results (|actual| ÷ implied move).

It never sets strikes, greeks or size.

---

## 7. Scalping: cut as a sleeve

At ₹2.5k R, a 2R target on a 45 bps stop needs a 90 bps move within 10 minutes. On a normal day that is 2–3σ even for 3%-ATR stocks, and Tier-A scalp names rarely move that much.

**What happens instead:**
- **Recorder:** keeps recording depth.
- **The only scalp-like trade:** a fast-exit variant of E3/T7 on news names.
- **Dropped:** order-flow index-option scalps (order-flow imbalance explains simultaneous moves, not future ones, and the feed's lag kills any lead); SC2 index-lead catch-up; wall and absorption setups; intraday relative-strength pairs; the LightGBM scalp filter, until some rule setup is positive at realistic friction.

---

## 8. The portfolio layer

1. **Composite book PF.** It runs the §2 allocation through the real risk engine and reports:
   - daily-stop hit rate;
   - peak margin;
   - risk contribution per sleeve;
   - stress breaches (target 0);
   - drawdown.
2. **Overnight risk is a scenario stress, not a sum of worst cases.**
   - **The binding rule:** for every scenario below, the loss of *all* overnight positions together must fit the overnight budget (1% = ₹10k; ₹15k in the 1.5% + 1.5% variant). Each scenario applies to every position at once.
   - **Scenarios:**

     | ID | Scenario | Moves |
     |---|---|---|
     | E | Equity gap | Nifty −4% × each stock's beta, with the largest stock position at −12% instead; VIX +40% on option positions |
     | D | Duty cut | Bullion −8% |
     | G− | Gulf de-escalation weekend | Crude −12%, gold −2% |
     | G+ | Escalation | Crude +15%, gold +4% |
     | FX | Rupee | USDINR ±2% on MCX positions |
     | LK | MCX band lock | A position cannot exit for a session and moves by its price band against us |
     | C | Combined weekend (report 19's joint scenario) [J] | E together with LK on every MCX position (first band from the contract calendar, e.g. gold 3%) |

   - **Shares decide who gives way** (priority shares: ES 0.6%, T 0.3%, O4 0.1%):
     1. A new position that would breach any scenario is **rejected**, unless its own sleeve would stay within its share in every breached scenario.
     2. In that case it **waits**, and the sleeve with the most rupees over its share, in the scenario with the largest breach, is reduced in its own next execution window (ES: the closing auction; T: the evening session) until every scenario fits.
     3. Existing positions are never force-closed outside their sleeve's execution window, so the book never sits over budget overnight because of this rule.
     4. O4's share counts only in its counterfactual accounting, not in the real check.
     5. Shares are re-split at season boundaries by measured return per unit of stress.
   - **Why it helps:** E hits ES, while D and G− hit T, and those shocks don't coincide. Summing per-name and per-contract worst cases was 1.5–2× too conservative. This replaces "at most 1 swing name while MCX positional is open" and "crude or gold, not both".
   - **What fits at 2% + 1% (₹10k)**, with β ≈ 1. Scenario E costs 0.04 × the ES book plus 0.08 × its largest name:
     - **ES alone:** about ₹1.5L with ₹50k names (3 names), or about ₹1.8L with ₹35k names (5 names).
     - **T alone:** one CRUDEOILM lot (about ₹85k) costs about ₹10.2k in G−, more than the whole budget, so crude does not fit at today's price; GOLDTEN (about ₹11.9k in D) does not fit either; 6 GOLDPETAL lots (about ₹90k) cost about ₹7.2k in D.
     - **Together, C binds** (C contains all of E): ES at its full ₹1.5L leaves no room for MCX. ES at ₹1L (₹8k in E) plus 4 GOLDPETAL lots (about ₹1.8k at a 3% band) fits. With T at its 0.3% share, ES fits about ₹0.8–1L.
   - **What fits at 1.5% + 1.5% (₹15k):** ES alone about ₹2.75L (5–6 names), close to report 20's capacity; or ES at about ₹1.25L plus a crude lot and a little bullion (depending on crude's band in C).
   - **So the split is a profit lever, not a formality:** 1.5% + 1.5% roughly doubles what ES and T can hold together, and sleeve A rarely uses more than 1% of daily loss at R = 0.25% with at most 3 entries. Both variants run in PF from day 1 (§15).
   - **Stops on overnight positions:** ES uses close-based stops plus a catastrophic stop re-armed after 09:15; T uses a disaster stop re-armed after 10:00. Neither has a broker-side stop at every moment (SL orders are cancelled at 15:15 and not accepted in pre-open), which is why sizing by this stress check is their real protection.
3. **Funding and sizing.**
   - **Funding:** a sleeve gets live risk only when the **10th percentile (q10) of its posterior edge** is above 0. The prior is N(0, 0.1R), worth about 170 trades, with day-clustered σ.
   - **R ramp:** R = min(0.5%, ⅛ × q10 ÷ σ², the volatility-target cap), changed only at month boundaries.
   - **How long it takes:** full R (0.5%) takes roughly 400–750 trades only if the true edge is +0.15–0.20R (report 23's examples). At the planning edge of +0.03–0.08R, funding (q10 > 0) alone needs several hundred to over a thousand trades, and full R is out of reach in year 1 at 1–2 intraday trades a day. While the formula gives less than the intraday R floor (item 5), the sleeve stays unfunded.
   - **Why ⅛ Kelly:** it keeps the chance of ever falling to 75% of equity near 1.3%. If the edge is overstated 2×, it behaves like ¼ Kelly (about 13%), still far below ½ Kelly's 42%.
   - **No R above 0.25% until q10 > 0.** Raising R early is the single biggest risk to the account: about a 23% chance of reaching the 25% drawdown in simulation.
4. **Volatility targeting as a risk control, not an alpha source:** an ex-ante portfolio σ of 8% a year at L1, 12% at L3, never above 15%. Each sleeve's size is scaled by min(1, target ÷ its 20-day EWMA σ).
5. **Drop a sleeve instead of shrinking everything.**
   - The drawdown ladder keeps its 5% (0.75×) and 10% (0.5×) rungs.
   - **Intraday base R floor ₹2k:** at R = 0.25% (₹2.5k) the 5% and 10% rungs would give ₹1.875k and ₹1.25k, so sleeve A's base R is held at ₹2k at both rungs while the other sleeves take the 0.75× / 0.5× cut; at R = 0.5% the rungs apply as written. Below about ₹2k the fixed brokerage takes a large share of the 0.2R friction budget and the stop floor climbs toward 90–100 bps. The S/M size tiers and day-type multipliers still apply per trade, and the friction gate is computed on each trade's actual risk.
   - At 15% and 20%, instead of the 0.35× and 0.25× rungs, **switch off the sleeve with the lowest lower confidence bound (LCB)**.
   - The 25% full stop is unchanged.
   - LLM spend steps down one degrade level per drawdown rung.
6. **Week-14 cost kill:** if no sleeve has LCB > 0 by week 14 counted from 12 Oct 2026 (about 18 Jan 2027, roughly 12 weeks of forward paper; report 25's timeline), LLM spend drops to triage only (Jev with Haiku fallback, a few hundred rupees a month; hard cap ₹1.5k), saving roughly ₹50k a year against the §11 budget.
7. **Correlation monitor:** re-estimate sleeve correlations from PF after 60 days. Starting assumptions:
   - A vs O1: +0.5, one bet;
   - A vs ES: +0.2;
   - A vs T: ≈ 0;
   - ES vs short-vol: +0.3, rising in crashes.

   Books correlated above 0.6 are treated as one bet.
8. **Treasury:** idle cash goes in a liquid fund or LIQUIDBEES at about 6%. Pledged collateral counts toward MCX margin at Zerodha (since Dec 2024); check the live broker's own rule. **Paper books credit about 6% on idle cash, so "profitable" means beating it.**

---

## 9. Cost programme

| Lever | Change | Effect |
|---|---|---|
| Realistic friction and a wider stop floor | §3 | Removes trades that lose by construction |
| Fewer, better trades | Opportunity gate, lunch ban, ≤ 3 intraday entries | Trade count −40–60% |
| LLM spend scaled to risk | ≤ 15–20% of a sleeve's expected gross once funded live (paper season 1 is research spend above that, bounded by the cap and the cost kill); Jev/Haiku first; no chart twin in season 1 | About ₹2.5–3k a month freed |
| Execution venue | Upstox Plus stays as the **data** account (it is what provides 30-level depth). At go-live, execute on a cheaper venue: Zerodha delivery at ₹0 (worth about 0.13% per swing round trip), ₹20 intraday, and a verified zero-brokerage API venue for options | About ₹10–25k a year at the new trade counts |
| Closing-auction execution | All overnight stock entries and exits | Saves 5–10 bps a side; paper ≈ live |
| Infrastructure | ≤ ₹3k a month live (laptop, static IP, small deadman VPS). The ₹15–25k a month cloud stack is rejected. | — |
| Treasury yield | §8 | About ₹25–35k a year on idle cash |

---

## 10. Season 0: research around the freeze

| Item | What | Effort | Output |
|---|---|---|---|
| **Post-cutoff replay** (runs on the frozen prompts) | Every NSE/BSE filing from 1 Jul to 9 Oct 2026 (including the Q1 FY27 results season) through the triage, ES and intraday-catalyst prompts. Prompts frozen first and never tuned on replay days; 30% of days sealed; a memorisation probe; a masked-name arm. **Check each model's stated training cutoff**: anything after 1 Jul is contaminated, and Jev 1.13's cutoff is unknown, so it is reported separately. Haiku/Jev score every event; Sonnet scores a stratified ~500. | ~1 week, about ₹3–5k one-off (budgeted without the batch discount; report 25) | The first honest skill number. Replay IC and forward IC are always reported separately; graduating needs both. |
| **Base-rate map** (code, 2022–26; before the freeze) | Overnight vs intraday returns (Nifty, Nifty 500); drift over days 0–10 by catalyst type and surprise size; gap fade vs continuation; 1-week reversal after moves with no news | 3–5 days | Which pools get LLM calls (base rate ≥ 0), and walk-forward base rates for the situation reports. Used to choose pools, never to mine setups. |
| **Exit brackets** (before the freeze) | B0/B1/B2 on identical entries (§3) | 3–5 days | One bracket per sleeve, chosen before the freeze |
| **Option day/night split** | Recorded chains (§6) | 1–2 days | The O2/O4 decision |
| **MCX backtest** | §5 | 1–2 weeks | Sleeve T's gate |
| **O1 offline test** | §6 | 1–2 weeks | O1's gate |

---

## 11. LLM budget (replaces the split in `ai-trader.md` §11)

| Line | ₹/month (results season) |
|---|---|
| ES: Sonnet deep reads (~15 a day), concall second reads, end-of-day rank and daily management | ~2,200 |
| Intraday L: catalyst moments only, game plan (Sonnet), pre-open call, open read and re-plan, management | ~2,200 |
| Haiku shadow scoring of all moments, plus repeat probes | ~500 |
| Jev triage (filings, MCX circulars) | ~100 |
| Option vetoes (O4/O2 counterfactual) | ~100 |
| Reserve | ~600 |
| **Total** | **≈ 5,700** (≈ 4,500 off season; hard cap ₹7,000) |
| One-off season-0 replay | ₹3–5k, outside the monthly cap |

- **Season-1 game plan:** it moves to Sonnet, because the narrowed sleeve has only 3–5 catalyst names. Opus returns only if the plan check (K4) shows the plan adds value and the budget allows. Opus also refuses requests with reasoning turned off.
- **Chart twin V:** deferred to season 2, and only if L shows IC.

---

## 12. Kill and success criteria (additions and changes)

**ES (event swing).** Judged on scored events for the signal and on trades for money; the 200-trade gate does not apply.
- **Kill** at 1,000 events: IC < 0.03, or its 90% upper bound < 0.07.
- **Success** at 2,000 events, all of:
  - IC ≥ 0.07 in both the replay and the forward sample, and in both halves;
  - the top fifth nets ≥ +0.4% per trade after costs;
  - ES-P (random picks at L's take rate) fails the same test: its trades do not net ≥ +0.4% per trade after costs;
  - ES-M's IC is reported alongside as a memorisation check, with the ES-L minus ES-M gap that counts as failure pre-registered before the arena starts.
- **Live money** also needs ≥ 100 trades with LCB > 0.

**Intraday L.**
- Keep the week-8 IC screen ([`ai-trader.md`](ai-trader.md) §16), with **CATALYST-mode IC as the primary metric**, pre-registered before the arena starts.
- Replace the "+0.15R" money gate with: **q10 of net expectancy after realistic friction and LLM cost per trade > 0.**

**Sleeve T:** gated on the backtest plus clean paper operations (§5). The trade-count gates are dropped.

**Options:** O1 by a 60-trade SPRT against its placebo. O4 and O2 stress tests and the O4 kill (§6).

**Portfolio:** the week-14 cost kill, sleeve funding on q10 > 0, and no R above 0.25% until q10 > 0 (§8).

**"Rely on a sleeve"** requires all of:
1. Replay IC and forward IC agree in sign and size.
2. q10 > 0 after realistic friction and LLM cost, and the sleeve beats both its placebo and the ~6% treasury yield.
3. 400 or more trades for full R (100 or more for ES at minimum size).
4. A live-minus-paper shortfall of ≤ 0.05R on small live probes (L0).
5. It survived at least one adverse episode (VIX above 20, or a Nifty month of −5% or worse) with zero risk-rule breaches.
6. Its stress tests pass jointly with the owner's separate options agent, if that agent is running.

---

## 13. Timeline

Early rows count weeks from 12 Oct 2026; arena checkpoints count from arena day 1 (about 26 Oct).

| When (2026–27) | What |
|---|---|
| Now (week 0–1) | Record all filings and daily bars; the Q2 season is under way and is the forward sample |
| Weeks 1–2 | Friction gate and opportunity gate; base-rate map; option day/night split; MCX backtest; exit brackets |
| By about 26 Oct | Freeze the ES and intraday-catalyst prompts (season 1 identities) |
| By about 9 Nov | Replay verdict; ES running in paper; E3 in paper |
| About 14–21 Dec | Week-8 intraday screen (CATALYST-mode IC): week 8 of the arena, once ≥ 35 sessions and ≥ 400 scored catalyst moments exist |
| Mid-December | ES interim verdict at 1,000 events (later if forward events come in slower) |
| About 18 Jan 2027 | Week-14 cost kill (week 14 counted from 12 Oct) |
| Feb–Mar 2027 | ES final verdict after the Q3 season. Earliest live step (L0 probes, then L1) only for sleeves with q10 > 0 |

---

## 14. Honest expectations

Composite book PF, ₹10L, paper year 1 (judgment):

| Scenario | Probability | Net return incl. LLM and infrastructure | Max drawdown |
|---|---|---|---|
| No LLM sleeve has edge (IC ≈ 0–0.04); trend and options roughly flat | ~55% | −4% to +3% (−1% to +6% with treasury yield) | 6–12% |
| One catalyst sleeve is real (IC ≥ 0.08) and trend is positive | ~25–30% | +8% to +15% | 5–10% |
| Bad regime and no edge | ~15% | −8% to −12%, stopped by the ladder or the cost kill by month 4–5 | 12–18% |

- **Drawdown risk:** the chance of reaching the 25% drawdown stays under 2% only while R stays at 0.25% and the ladder is active.
- **Capacity caveat:** these ranges are the red team's. If the gain comes from ES, its size depends on the overnight split: at 2% + 1%, ES runs at about half the capacity report 20 assumed, and T can't hold crude (§8). That takes roughly 2–6 points off the middle scenario. The 1.5% + 1.5% variant restores most of it.
- **Live haircut:** cut any paper result by 30–50% for live trading in year 2. Fills, decay of the drift edge as more traders use LLMs, and auction behaviour all erode it.

---

## 15. Owner decisions this plan asks for

1. **Worst-day split at go-live:** keep 2% intraday + 1% overnight, or move to 1.5% + 1.5%. The worst day stays 3% either way. At 2% + 1% the stress check holds ES to about ₹1.5L and leaves no room for crude at today's price (§8); 1.5% + 1.5% roughly doubles what ES and T can hold together, at little cost to intraday. Both run as composite-book variants in paper, so the choice can be made on evidence. Report 25 keeps 2% + 1% for now and leaves the switch to go-live. **My recommendation: switch to 1.5% + 1.5% once ES passes its success test at 2,000 events** (report 20's gate), not just the interim kill check, which only rules out IC ≈ 0.
2. **Live execution venues:** Upstox Plus stays as the data account. Execution can move to cheaper venues: Zerodha for delivery and intraday, and a zero-brokerage API venue for options. This is decided at go-live.
3. **The separate options-selling agent** (not running now): if it runs with real money, feed its positions read-only into the overnight stress, or ring-fence its capital outside this system's 3%.
4. **Owner tradebook** (optional, recommended): 12 months of your own trades set the bar for "instead of my manual trading".

---

## 16. Research behind this plan

| # | Report | Topic |
|---|---|---|
| 19 | [profitability-edge-map](../research/19-profitability-edge-map.md) | The 3 × 3 edge map and sleeve ranking |
| 20 | [event-swing-sleeve](../research/20-event-swing-sleeve.md) | Why the LLM's edge is at the daily horizon; the ES specification |
| 21 | [options-profitability](../research/21-options-profitability.md) | Day/night VRP, O1/O2/O4/O5, the cost stack |
| 22 | [commodity-trend-sleeve](../research/22-commodity-trend-sleeve.md) | Multi-speed trend, scenario stress, MCX costs |
| 23 | [portfolio-and-risk](../research/23-portfolio-and-risk.md) | Composite book, Kelly and LCB sizing, Monte Carlo, cost drag |
| 24 | [intraday-scalping-profitability](../research/24-intraday-scalping-profitability.md) | Realistic friction, opportunity gate, exits, cuts |
| 25 | [red-team-profitability](../research/25-red-team-profitability.md) | Final rulings, top-10 list, expectations |
