# Red-team review: Intraday Options Module (as of 2026-10-08)

**Verdict:** The facts are mostly sound. The STT hike, the expiry calendar, freeze quantities, the expiry-day ELM and the stock calendar-spread margin change all check out. The weak spots are elsewhere:
- The economics of the non-expiry selling module don't work.
- The catastrophe sizing contradicts the R budget.
- Some data-cadence and convention assumptions are wrong.

Build fewer strategies, and narrow them.

---

## 1. Fact check

| Claim in report | Verdict | Correction |
|---|---|---|
| STT on options 0.15%, futures 0.05% | **Correct** | Also confirmed: STT on exercised options rose from 0.125% to 0.15%. Intraday cash STT is unchanged [a]. |
| Nifty 22,776, VIX 13.6 (Oct 6) | **Correct** | One source [b]. |
| Lot sizes Nifty 65, Sensex 20 | **Correct today, unstable** | At today's levels, 65 × 22,776 = ₹14.8L and 20 × ~72k ≈ ₹14.4L. Both are **below SEBI's ₹15–20L band** [c]. The six-monthly review is due about now, so an *upward* revision (Nifty ~70–75, Sensex ~25) is plausible. During the transition, different expiries carry different lot sizes [d]. Size from the **per-contract** lot, never the per-underlying lot. |
| Freeze quantities from 5-Oct | **Correct** | NSE circular 76693 [e]. |
| NSE options transaction charge 0.03553% | **Unverified** | The Oct-2024 true-to-label revision says **0.03503%** [f]. Make it a config value. The difference is negligible. |
| "OI updates at 1–3 min granularity" | **Too optimistic** | Vendors and brokers consistently report that NSE refreshes OI about **every 3 minutes** for most strikes [g]. |
| Algo rules | **Partly incomplete** | The static IP is checked on *order* endpoints only. IP changes are limited to about once a week. Daily 2FA means refresh-token sessions are gone. **Plain market orders are not allowed for algo orders;** they must carry a protection limit (MPP). Slices count toward the 10 OPS cap. Upstox's 25-child `slice=true` can breach that cap by itself [h]. |
| Upstox Plus multi-leg discount (4 legs ₹120 → ₹60) | **Probably unusable** | It applies to Strategy Builder orders, which are listed as Android-only [i]. Assume ₹30 × 8 per condor through the API. |
| 30-level depth recorder | **Capacity limit** | Community reports put D30 at about **50 instruments per connection**. Users report that extra D30 connections connect but receive no data [j]. The whitelist plan (≈25 stocks × ATM±2 × CE/PE = 250 instruments) doesn't fit. Rotate subscriptions, or use 5-level `full` mode for whitelisting. |
| Stock calendar-spread margin removal | **Correct** | SEBI circular of 5-Feb-2026, effective 4/5 May 2026 [k]. |
| Expired-contract data | **Roughly correct** | Requires Plus. Intervals 1/3/5/15/30 min and daily. Data starts around Oct 2024–Feb 2025 depending on user, and **some weekly expiries are missing** [l]. |
| BSE share ~25–30% | **About right** | NSE index-option share was 66.7–72% in Jan–Mar 2026 [m]. Sensex liquidity is concentrated on **Thursday**, so its non-expiry days are thin. |
| "Weekly ATM options 6–8× cheaper per delta than futures for holds under 1–2 h" | **Wrong framing** | 6–8× holds only at *zero* hold time. At ~22,800 and VIX 14 with DTE 3–5, 2 ATM lots bleed about ₹350–450 of theta per hour. The cost advantage over futures (~₹750) is gone after about **1.5–2 h**, or **~1 h on expiry day**. |
| Implied daily move uses `S·IV·√(1/252)` while IV uses calendar minutes (365 basis) | **Inconsistent** | This creates a ~20% bias, so the RV/IV day-type thresholds (0.8 / 0.35) are miscalibrated. Pick one clock and refit the thresholds. |

The break-even table (₹55/63/78) and the futures STT figure (₹741 per lot) recompute correctly.

---

## 2. Strategies likely to lose money after costs

1. **Non-expiry intraday iron condor (S2 at 10:45, DTE ≥ 1).** This is internally inconsistent. A "take profit at 40–50% of credit" target is rarely reachable between 10:45 and 15:00 on a 2–5 DTE weekly; realistic intraday decay is about 10–25% of credit.
   - Example: ₹30 credit × 65 = ₹1,950. A winner nets about ₹300–500 minus ₹230–250 in fees and spread. A stop at 1× credit costs about −₹2.2k.
   - Break-even win rate is **over 85–90%**. Even with TP reachable, it is about 78%.
   - Short strikes at only 0.5× the remaining implied move have about a 60% intraday touch probability, and the stop rule "underlying within 0.2 × ATR of the short strike" fires on top of that.
2. **Selling after an IV spike** (gap with VIX up 8% or more). In a market down 7% in five weeks with live geopolitical risk, this sells vol at the start of trend-continuation days. It has the same TP problem as item 1. **Drop it.**
3. **0DTE momentum bursts (9:45–13:00).**
   - The hurdle: ATM 0DTE theta is about 7–8 points per hour by late morning. With a 10–15 minute hold, plus spread and fees, the trade needs roughly **6 Nifty points just to break even**.
   - False breaks are frequent around OI walls on expiry days.
   - Run this only as a variant of S1 once S1 shows an edge.
4. **OTM buys (Δ 0.30–0.40) on trend days.** These carry worse spread%, skew-inflated IV and faster % theta. **Drop them.**
5. **Stock options on news or results.** IV pops 5–15 points and spreads run 1–3%, so cash MIS dominates. Keep this as paper measurement only (S3).
6. **The OI "chain confirmation" as a hard gate in S1.** OI is up to about 3 minutes stale at a 5-minute close. The premium × OI writer/buyer classification is folklore with no validated edge. Log it and test it offline. Don't gate on it.

---

## 3. Gaps and failure modes

- **Double-exit race.** A resting SL-L catastrophe order plus a software exit can sell twice. The second sale is either rejected or **opens a naked short**.
  - Exit by *modifying* the resting order (cancel-replace).
  - Add a risk veto that rejects any option sell whose quantity exceeds the net long position.
- **Catastrophe sizing contradicts R.** `max_premium_per_trade: 60000` × 35% = ₹21k, which is 4.2R. Open long premium of ₹150k × 35% = ₹52k, about 2× the daily stop.
  - Cap premium so that cap% × premium ≤ 2R. With R = ₹5k that is about ₹28k.
  - Cap aggregate premium against the remaining daily budget.
- **Book delta is too loose.** A ₹20L Nifty-equivalent limit means a 1.5% shock costs ₹30k, which exceeds the daily stop. Set the limit by stress test (1.5% instantaneous move plus 30% IV move ≤ remaining budget), which gives about ₹12–15L.
- **SL-L orders trigger on option LTP.** A stray print in a thin strike can trigger one. In a crash the order can be skipped if limit = trigger − 5%.
  - Alert when an order shows "triggered but open" for more than N seconds.
  - Clamp exit ladders to the live price band. The "bid − 5%" step can be rejected outright.
- **The leftover-option exception must be index-only.** An OTM *stock* option left open can finish ITM and create a physical-delivery obligation.
- **Inconsistent stock-option cut-offs.** §6 says "final 2 sessions" but S3 says "≥ 5 sessions". Brokers raise delivery margin from about 4 days before expiry. Use a single rule: **no front-month stock options in expiry week.**
- **Chain data quality.**
  - REST chain snapshots are non-atomic and LTP-based.
  - Vendor greeks are computed off spot with unknown r and T, which produces fake put/call IV gaps and fake skew.
  - Compute IV in-house from synchronized **mid** quotes against the synthetic forward. Reject quotes older than 2 s, NaN/intrinsic violations, and premiums under ₹2.
- **Expiry-day detection** must come from the contract master's expiry date, not the weekday. Holiday shifts and Muhurat sessions break weekday logic.
- **Lot-size change mid-pipeline.** Backtest, risk and paper fills must all key on the contract-level lot.
- **News latency.** Scrapers and the LLM lag the market. The hard veto should key on *market* signals: VIX jump, 1-minute futures range, spread blowout.
- **Range classification at 10:45.** European-open moves (~12:30–13:30 IST) often break quiet mornings. Validate the classifier's afternoon hit rate before anything sells on it.
- **Paper fills** need injected latency (≥ 200–300 ms) and a queue model. Mid-price limits fill only when the market trades through.

---

## 4. Build order

**Build first:**
1. **S1: index level-break momentum, long Δ 0.55–0.65.** Nifty only, **non-expiry days first**.
   - Add Sensex only on Wednesday/Thursday after it passes the whitelist.
   - OI is logged, not used as a gate.
   - Cap premium by R.
   - Test a debit-spread variant for expected holds over about 45 minutes or IVP above 60.
2. **S2 narrowed: expiry-day (DTE 0) afternoon iron fly/condor only.**
   - Nifty on Tuesday, Sensex on Thursday.
   - 1–2 sets, entry 12:45–14:00, flat by 15:00, ELM-inclusive margin check, pin rule kept.
   - This is the only window where TP at 50% of credit is realistic.
3. **S3: cash-vs-option shadow, paper only.** It costs nothing and answers the "options vs cash for stocks" question with data. Cash MIS stays the default stock vehicle.

**Defer:**
- 0DTE momentum bursts (later, as an S1 variant at 50% size).
- Non-expiry intraday condors.
- BankNifty monthly.
- Live stock-option news trades.

**Drop:**
- Selling after an IV spike.
- OTM directional buys.
- Gamma scalping (already dropped).
- Max pain and GEX as signals.
- FinNifty and Midcap.

---

**Sources**
[a] [5paisa](https://www.5paisa.com/news/stt-hike-on-fo-to-take-effect-from-april-1-amid-rising-options-activity), [Moneylife](https://moneylife.in/article/stt-hike-applies-only-to-options-and-futures-it-dept-clarifies/79539.html) · [b] [JM Financial](https://www.jmfinancialservices.in/market-news-and-insights/1735386) · [c] [ICICI Direct](https://icicidirect.com/research/equity/finace/nse-raises-minimum-contract-value-for-index-derivatives), [AlgoTest](https://algotest.in/blog/sensex-lot-size/) · [d] [Kotak Neo](https://www.kotakneo.com/bulletins/lot-size-changes-in-index-derivatives-effective-december-30-2025/) · [e] [NSE FAOP76693](https://nsearchives.nseindia.com/content/circulars/FAOP76693.pdf), [Choice](https://choiceindia.com/news/nse-revises-quantity-freeze-limit-for-index-fno-contracts-from-october-5-2026) · [f] [Zerodha bulletin](https://zerodha.com/marketintel/bulletin/391488/revision-in-transactions-charges-from-1st-october-2024), [Zerodha support](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/exchange-transaction-charges) · [g] [TrueData](https://feedback.truedata.in/knowledge-base/article/data-update-frequencies-in-brief), [Fyers community](https://fyers.in/community/t/option-chain-update-frequqency/21050) · [h] [Kite forum](https://www.kite.trade/forum/discussion/comment/52157), [Fyers](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026), [TradingQnA](https://tradingqna.com/t/api-market-protection-parameter-clarification-needed-on-correct-usage/193504) · [i] [Upstox Plus T&C](https://upstox.com/files/terms-and-condition/plus-pack.pdf), [Upstox help](https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/) · [j] [Upstox community D30](https://community.upstox.com/t/market-depth-30-increase-limit-for-more-than-50-instruments/13398), [connections](https://community.upstox.com/t/market-data-feed-v3-multiple-web-socket-connections/10465) · [k] [ICICI Direct](https://www.icicidirect.com/ilearn/futures-and-options/articles/removal-of-calendar-spread-margin-benefit-for-single-stock-derivatives-on-expiry), [TradingQnA](https://tradingqna.com/t/calendar-spread-margin-benefit-removed-for-single-stock-derivatives-on-expiry-day/191319) · [l] [Upstox community](https://community.upstox.com/t/historical-availability-retrieval-limit-per-query-for-expired-options-contract/9245), [missing data](https://community.upstox.com/t/missing-historical-data-for-multiple-option-instruments/9232) · [m] [Business Today](https://www.businesstoday.in/amp/opinion/story/behind-the-numbers-why-nses-derivatives-dominance-remains-intact-531683-2026-05-15), [Business Standard](https://www.business-standard.com/markets/news/bse-to-sustain-mkt-share-gains-says-motilal-oswal-amid-regulatory-clouds-125101300234_1.html)