# Trading Playbook and Risk Framework: Rs 10L intraday-first system (head-of-risk view)

**Who is writing:** the head of risk / senior discretionary trader on the design team. This is a design document only; no code. Facts carry a source and a confidence level (H/M/L). Anything marked **[J]** is my own judgment.

---

## 0. Verified facts that change the design

| # | Fact | Design consequence | Conf. |
|---|---|---|---|
| F1 | Intraday equity margin is the higher of 20% of trade value or VaR+ELM, so leverage tops out at 5x. Exchanges can add ad-hoc margins. ([Zerodha](https://support.zerodha.com/category/trading-and-markets/margins/margin-leverage-and-product-and-order-types/articles/different-types-of-margin)) | 4x fits inside the limit. Volatile names get less than 5x. Keep a margin buffer. | H |
| F2 | **Closing Auction Session (CAS) has been live since 3 Aug 2026 for F&O stocks.** Continuous trading ends at 15:15 and the auction runs 15:15–15:35. Pending SL and iceberg orders are cancelled. The auction price is held within ±3% of the 15:00–15:15 VWAP. F&O contracts trade until 15:40. ([Sahi](https://www.sahi.com/blogs/closing-auction-session-cas-explained-nse-bse-closing-price-rules-2026), [Geojit](https://support.geojit.com/support/solutions/articles/89000021005-closing-auction-session-cas-key-details-every-investor-should-know), [Angel One](https://www.angelone.in/news/market-updates/nse-reports-strong-participation-on-day-1-of-closing-auction-session-for-f-o-stocks)) | Intraday positions in F&O stocks must be flat before 15:10. Resting SL orders on swing positions in CAS stocks disappear at 15:15. | M-H |
| F3 | Upstox MIS auto square-off from 11 Sep 2026 is **15:10 for CAS stocks** and 15:25 for non-CAS stocks and F&O. A missed square-off costs a Rs 59–88.5 fee. ([Upstox notice](https://upstox.com/announcements/revised-timings/important-update-intraday-square-off-timings-are-changing/)) | The system's own flatten deadlines must come earlier (section 7). | M |
| F4 | Pre-open: order entry 9:00–9:08 with a random close in the 7th–8th minute, matching 9:08–9:12, buffer to 9:15. A **pre-open session for stock and index futures** has run since 8 Dec 2025. ([Business Standard](https://www.business-standard.com/markets/capital-market-news/nse-to-commence-pre-opening-session-in-f-o-segment-from-december-08-125110400728_1.html), [Jainam](https://www.jainam.in/blog/nse-pre-open-session-fo-segment/)) | The futures indicative equilibrium price and imbalance become in-play inputs at 9:08. | H |
| F5 | NSE weekly and monthly expiries fall on Tuesday (stock F&O on the last Tuesday). BSE expires on Thursday. ([Business Standard](https://www.business-standard.com/amp/markets/news/nse-bids-adieu-to-thursday-expiry-as-dates-swap-come-into-effect-explained-125082800635_1.html)) | Tuesday rules in section 7. | H |
| F6 | STT on intraday equity is 0.025% on the sell side. **Futures rose to 0.05% and option premium to 0.15% (sell side) from 1 Apr 2026.** ([ICICI Direct](https://www.icicidirect.com/ilearn/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-should-know), [Groww](https://groww.in/blog/what-is-stt)) | For intraday, stock futures now cost about 2x what cash MIS costs. Cash is the default vehicle. | Equity H, derivatives M |
| F7 | Other charges: NSE transaction about 0.00297%, SEBI fee 0.0001%, stamp duty 0.003% (buy side), GST 18% on brokerage plus fees. Upstox brokerage is Rs 20 per order or a % cap, whichever is lower. ([Motilal](https://www.motilaloswal.com/learning-centre/2023/5/apart-from-brokerage-what-fees-i-am-charged), [Upstox calc](https://upstox.com/tools-and-calculators/brokerage-calculator/)) | Fees come to about **4–4.5 bps per round trip** on a Rs 5L ticket (my arithmetic). | M |
| F8 | Tick sizes: Rs 0.01 below Rs 250, 0.05 for Rs 250–1,000, 0.10 for Rs 1,000–5,000, 0.50 for Rs 5,000–10,000. Reviewed monthly. ([Zerodha](https://zerodha.com/marketintel/bulletin/408151/revision-in-tick-size-for-nse-derivatives-and-cash-segment-from-april-15-2025)) | Spread in bps must be computed per symbol. | H |
| F9 | F&O stocks have no fixed band. They start at a 10% dynamic band that flexes 5%, 5%, 3%, 3%, then 2%. Non-F&O stocks sit in fixed 2/5/10/20% bands. ([Fyers](https://fyers.in/notice-board/revised-dynamic-price-bands-and-fo-segment-rules/)) | Shorts are allowed only in F&O stocks or 20%-band stocks. | M-H |
| F10 | F&O ban now uses futures-equivalent (delta-based) OI. MWPL = min(15% of free float, 65x average daily delivery value), with the 95% trigger kept. ([Zerodha](https://zerodha.com/z-connect/updates/understanding-the-new-delta-oi-based-mwpl-framework), [Business Today](https://www.businesstoday.in/amp/markets/story/sebi-equity-fo-rules-futeq-method-mwpl-risk-management-478321-2025-05-29)) | Ban-list feed needed daily. | M |
| F11 | ESM Stage II means a 2% band, call auction and no intraday. GSM Stage II and above means T2T and no intraday. ([NSE ESM FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQs%20-%20Enhanced%20Surveillance%20Measure%20%28ESM%29_25.7.2025.pdf), [Upstox GSM](https://upstox.com/learning-center/share-market/what-is-graded-surveillance-measure/article-1884/)) | Hard exclusion. | M |
| F12 | The SEBI retail-algo framework applies from 1 Apr 2026: static IP, a 10 orders-per-second threshold before registration, daily API logout. ([SEBI circular](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf), [5paisa](https://www.5paisa.com/news/sebi-tightens-algo-trading-rules-with-mandatory-2fa-and-audit-trails-from-april-1)) | Throttle orders, run on a static-IP host, and enforce a daily re-auth. | M-H |
| F13 | **Current regime:** Nifty about 22,776 on 6 Oct 2026, near a six-month low after an 8-week losing streak. VIX 13.6–14.7. Brent around $100. FIIs have been net sellers for 15 straight months. On 8 Jul 2026 an Iran "ceasefire over" remark sent VIX up 26% and Nifty down 2.12% in one day. ([Kotak Neo](https://www.kotakneo.com/news/market-news/stock-market-update-1-october-2026-sensex-nifty/), [Trendlyne](https://trendlyne.com/posts/5871790/daily-news-report), [Business Today](https://www.businesstoday.in/markets/stocks/story/india-vix-surges-26-as-trumps-iran-ceasefire-over-remark-rattles-markets-sensex-nifty-slump-over-2-541766-2026-07-08), [Bajaj Broking](https://investmentguruindia.com/newsdetail/commentary-on-monthly-fii-and-dii-02nd-october-2026-by-pabitro-mukherjee-deputy-vice-president-research-bajaj-broking909459)) | Gaps driven by headlines are real, so intraday-first is correct. Q2 results season starts now. | M |

**Friction math [J, built on F6–F8].** On a Rs 5L round trip: brokerage 40 + STT 125 + exchange 29.7 + SEBI 1 + stamp 15 + GST 12.7 = **Rs 223, about 4.5 bps**. Add slippage of about 1–3 bps per side in liquid names (5–10 bps in news shocks). All-in cost runs **6–15 bps per round trip**. This one number decides which scalps are worth taking.

---

## 1. Capital and risk math

### 1.1 Recommended limits [J]

| Parameter | Value | Rationale |
|---|---|---|
| Daily loss limit (DLL), hard | **2.0% = Rs 20k**, realized plus unrealized | When it is hit: flatten, lock for the day |
| Catastrophic ceiling | **3.0% = Rs 30k** | Only reachable through gaps or slippage. Trips the kill switch; manual reset next day only |
| Soft warning | -1.2% (Rs 12k) | Size drops to 0.5x and only A+ setups are allowed |
| Intraday R (momentum/news) | **0.5% = Rs 5,000** | Allows about 3 full losses before the bucket stops |
| Scalp R | 0.15–0.20% = Rs 1,500–2,000 | Tight stops, so friction takes a larger share |
| Swing R | 0.5% to the stop, plus a gap budget (section 6) | |
| Max open risk (sum over open positions) | 1.5% = Rs 15k | |
| Max concurrent positions | 4 momentum + 2 scalps; max 3 in the same direction with beta above 0.8 | |
| Gross intraday exposure | Normal cap **3x (Rs 30L)**, hard cap **4x (Rs 40L)** | Keep a free-margin buffer of at least 20% for ad-hoc VaR hikes (F1) |
| Per-symbol notional | ≤ min(1.2x equity = Rs 12L, 0.5% of 20-day median turnover, 3x median 1-min traded value) | Lets the system exit in about 3 minutes at 33% or less of the flow |
| Per-sector | Max 2 positions; sector open risk ≤ 1.0% | |
| Equity base | Start-of-week mark-to-market equity, recomputed Monday; sizes drop immediately on drawdown | Size down fast, size up slowly |

I am deliberately stricter than the 3% the owner mentioned. Five 3% days already make a 15% drawdown, and a new, unvalidated system will have those days.

### 1.2 The core invariant (code-enforced)

```
allow_new_trade  iff  realized_today + Σ open_risk_i + risk_new ≥ −0.9 × DLL
open_risk_i = qty_i × |LTP_i − stop_i| + est_exit_cost_i   (0 if stop is in profit; locked gains count 50%)
```

### 1.3 Position sizing

```
eff_risk_per_share = |entry − stop| + friction_per_share      (friction ≈ 0.10% × price default; per-symbol estimate later)
stop_distance ≥ max(0.25% × price, 0.15 × ATR14_daily, 3 × median_spread + 2 ticks)   # floor; else widen or skip
qty = floor(min( R / eff_risk_per_share,
                 cap_symbol_notional / price,
                 (gross_cap − current_gross) / price,
                 free_margin × leverage_eff / price ))
```

The key identity is **notional ÷ equity = R% ÷ stop%**. With R = 0.5%, a 0.5% stop gives 1x and a 0.125% stop gives 4x. Leverage is the result of the stop distance, not a target. Using the full 4x on one name requires a stop so tight that noise usually takes it out. That is why the per-symbol cap is 1.2x.

**Example A: Rs 500 stock, daily ATR Rs 14 (2.8%), ORB long.**
- Entry 502.0, stop at the opening-range midpoint 497.6, so the distance is Rs 4.4 (0.88%, 0.31 ATR). Friction about Rs 0.5, giving an effective risk of Rs 4.9.
- qty = 5,000 / 4.9 = **1,020 shares**. Notional Rs 5.12L (0.51x). Margin at 5x is about Rs 1.02L.

**Example B: Rs 3,000 stock, daily ATR Rs 54 (1.8%), VWAP reclaim.**
- Entry 3,006, stop 2,994.5, so the distance is Rs 11.5 (0.38%). The floor is max(7.5, 8.1, spread) = 8.1, so the stop passes. Friction about Rs 3, giving an effective risk of Rs 14.5.
- qty = **344 shares**. Notional Rs 10.3L (1.03x).
- If the stop were only Rs 6, it would fail the floor: widen it to Rs 8.1, which gives 450 shares and Rs 13.5L, then the per-symbol cap of 1.2x cuts that to **400 shares**.

**Example C: scalp in the same Rs 3,000 stock.**
- R = Rs 2,000, stop 0.15% (Rs 4.5), friction Rs 3, effective risk Rs 7.5, qty 266, notional Rs 8L.
- Friction is **40% of the risk**. A 0.3% target nets only 0.8R. Scalps therefore need targets of at least 0.4% (2.5–3x the stop) and a win rate of at least 55%. This is the main reason scalping is a gated bucket (section 5).

**Example D: invariant block.**
- Realized today is -Rs 5k and open risk is 4k + 5k + 3k = 12k.
- A new Rs 5k trade would make the total -22k, which is worse than -18k (0.9 × DLL). **Blocked.** The remaining room is Rs 1k, which is below the 0.25% minimum R, so the system skips the trade.

### 1.4 Strategy budget split (share of the Rs 20k DLL)

| Bucket | Phase 1 (paper → first live) | Once proven | Bucket daily stop |
|---|---|---|---|
| News/momentum intraday | 60% (Rs 12k) | 55% | -Rs 12k (about 2.4R) |
| Scalping (after the gate in section 5) | 25% (Rs 5k) | 20% | -Rs 5k |
| Slippage reserve | 15% | — | — |
| F&O options (defined risk) | 0 | 15% | — |
| MCX commodities | 0 | 10% (counts toward the same calendar-day DLL) | — |
| Swing (overnight) | Separate gap budget: total overnight shock ≤ 1% of capital | Same | — |

### 1.5 Drawdown ladder and limits

| Trigger | Action |
|---|---|
| Weekly loss -4% (Rs 40k) | Stop live trading for the rest of the week (paper continues) |
| Monthly loss -8% (Rs 80k) | Halt live trading. At least 10 paper sessions plus a written post-mortem before restarting |
| Drawdown from high-water mark 5% / 8% / 12% | Size 0.75x / 0.5x / 0.25x with the top-2 setups only |
| Drawdown from high-water mark 15% (Rs 1.5L) | Full stop and strategy review |
| Stepping back up | Recover 50% of the drawdown **and** 10 sessions of positive expectancy at the reduced size |
| 3 consecutive losing trades | 30-minute cool-off, next 2 trades at 0.5x |
| 4 losing trades in a day | Intraday done for the day |
| 2 consecutive days each losing ≥ 75% of the DLL | Next day 0.5x, A+ setups only |

**Profit protection:**
- Once the day's peak P&L reaches at least +Rs 10k: no new entries if P&L falls to 60% of the peak; flatten everything at 50% of the peak.
- Once the peak reaches at least +Rs 25k: the remaining trades run at 0.5x and the floor rises to 70% of the peak.
- There is no daily profit cap.

---

## 2. Universe and in-play selection

**Static universe (rebuilt monthly from the Nifty 500)** [J thresholds]:
- **Tier A (scalp-eligible):** 20-day median turnover ≥ Rs 300 Cr, median spread ≤ 3 bps (9:30–15:00), F&O stock.
- **Tier B (momentum-eligible):** turnover ≥ Rs 75 Cr, spread ≤ 8 bps, price Rs 100–10,000.
- **Exclusions (hard):** ASM, GSM or ESM at any stage; T2T/BE series; fixed band ≤ 10% (F11, F9); listed less than 30 days ago; ex-date for split, bonus or demerger today.
- **Shorts:** only in F&O stocks or 20%-band stocks.
- **F&O ban stocks:** cash longs only, at 0.5x (OI unwinds make price behaviour erratic). No derivative trades.

**In-play score (0–100), computed at 08:45, 09:10 (after pre-open), 09:30, 10:30, 12:30 and 13:30, plus on any new filing:**

| Component | Weight | Measure |
|---|---|---|
| Catalyst materiality (LLM 0–10, rubric in section 4) | 25 | |
| Gap ÷ ATR14 | 15 | 0.5–1 ATR moderate, above 1 ATR strong; uses the pre-open equilibrium price |
| Pre-open volume ÷ 20-day pre-open average, plus futures pre-open imbalance (F4) | 10 | |
| RVOL: first 15 minutes vs 20-day same-time average (from 09:30) | 15 | |
| Relative strength vs Nifty and vs sector (z-score) | 10 | |
| Location: near PDH/PDL, multi-day range edge, 52-week high/all-time high | 10 | |
| Derivatives: OI change by price quadrant (long buildup / short covering) | 10 | |
| Block or bulk deals, index inclusion, MSCI/FTSE flows | 5 | |

**Penalties:** spread above threshold, a move already larger than 2.5 ATR (exhaustion), news more than one day old.

**Output:** **5 primary names (max 8)** with depth subscription and full setup monitoring, plus **10–15 watchlist names** at bar level only. Max 2 per sector in the primary list. At 09:30, names with RVOL below 1.5 are dropped.

---

## 3. Day-type classification (deterministic; the LLM supplies only a prior)

Inputs: the Nifty ATR14 in %, OR30 (the first 30-minute range), Nifty 500 advance/decline ratio, the share of 5-minute closes on one side of VWAP, first-hour volume ÷ 20-day average, VIX change, Nifty vs BankNifty vs Midcap divergence, and intraday shifts in index option OI. Rough scale: VIX ÷ 15.87 is about the daily sigma, so VIX 14 implies about 0.88%.

| Type | Criteria (evaluate 09:45, confirm 10:30, recheck 13:30) | Allowed | Blocked | Size |
|---|---|---|---|---|
| **Trend up/down** | OR30 ≤ 0.35 ATR, broken on a 5-min close; A/D ≥ 2.5 (≤ 0.4 for down); ≥ 80% of 5-min closes on one side of VWAP after 09:45; first-hour volume ≥ 1.2x; VIX moves the expected way | S1–S5, S8, SC2, SC3 | S6, counter-trend scalps | 1.0x |
| **Gap-and-go** | \|gap\| ≥ 0.5 ATR, extends in the first 30 min, holds the open, A/D ≥ 2 in the gap direction | Same as trend | S6 | 1.0x |
| **Gap-and-fade** | \|gap\| ≥ 0.5 ATR, no extension, back through the open and VWAP by 10:30, breadth flips | S6, SC4, inverse S5 | S2 in the gap direction | 0.75x |
| **Range/rotational** | OR30 ≥ 0.5 ATR or 2 failed OR breaks; A/D 0.7–1.4; ≥ 4 VWAP crosses by 11:30; volume ≤ 0.9x | S1 (stock-specific only), S3 on in-play names, S6, SC1, SC4 | S2 in heavyweights, SC2, S8 | 0.75x |
| **Dispersion** | \|Nifty\| ≤ 0.3% but cross-sectional sigma of returns ≥ 1.3x the 20-day average | S1, S4, S5 | SC2 | 1.0x |
| **High-vol event** | VIX ≥ 20, or VIX +8% at the open, or \|gap\| ≥ 1 ATR, or a binary event (RBI 10:00, Budget, election), or geopolitical score 3 | S1 A+ only with wider stops; S6 only after 10:30 | All scalps, ORB, new swing trades | 0.5x |
| **Compressed / pre-event** | OR30 ≤ 0.2 ATR, VIX falling, volume ≤ 0.7x, a major event within 24 hours | S1 and S4 on stock-specific names only | SC2, ORB on names without a catalyst | 0.5–0.75x |

**Secondary tells:**
- Nifty up while midcap breadth is weak means a narrow rally: trade the leaders only, no midcap longs.
- Fresh put writing at or below ATM (intraday PCR rising from 0.8 to above 1.0) supports a trend-up label.
- A large pile of call writing at the strike just above spot means a cap: range day.
- Unclassified by 10:00: label it "unknown", allow the top-2 setups at 0.5x.

---

## 4. Intraday setup playbook

Expectancy figures are my priors **[J]**. The system has to measure its own.

**Catalyst materiality rubric (for LLM scoring):**
- **Order wins:** order ÷ trailing-12-month revenue below 5% is minor, 5–15% moderate, above 15% major. Also compare to the order book (more than 10% is material). Discount repeat PSU order announcements.
- **Results:** EBITDA vs consensus and margin direction matter more than PAT, which one-offs distort. Guidance changes count most.
- **Penalties or litigation:** above 1% of market cap is material.
- **Blocks:** a block at more than a 3% discount signals supply.
- **Broker upgrades:** low weight.
- **Market-cap scaling:** a Rs 500 Cr event is about 10% of a Rs 5,000 Cr company but noise for a Rs 2L Cr company.

**Signs the news is priced in:**
- A 5–20 day run-up more than 2x the sector's before the event.
- The news was leaked or circulated the previous day (check prior-day volume).
- A gap into resistance with the first 15-minute candle closing below the open on heavy volume.
- IV crushes and the stock fails to extend.

**S1. News-shock first pullback.**
- **Context:** catalyst score ≥ 7, move ≥ 1 ATR, RVOL ≥ 3, the index not strongly against.
- **Trigger and entry:** after the first impulse, the first pullback to VWAP, the 5-min 20 EMA or a 38–50% retrace, on pullback volume below 60% of the impulse. Enter on a stop-limit 1 tick above the reclaim bar, with the limit capped at +0.1%.
- **Stop:** pullback low minus 0.1 ATR. Skip if the stop would be more than 0.6 ATR.
- **Targets:** 40% at the impulse high, 30% at 2R, trail the rest on 5-min higher lows.
- **Time stop:** 20 min without reaching +0.5R. **Invalidation:** retrace beyond 61.8% or a loss of VWAP.
- **Expectancy:** 45–55% wins at about 1.8R average.
- **Failure modes:** sell-the-news, block sellers supplying the second leg, a broad market reversal.

**S2. Opening range breakout (15-minute ORB) on in-play names.**
- **Context:** OR15 width 0.25–0.8 ATR, RVOL ≥ 2, relative strength aligned.
- **Trigger and entry:** a 5-min close beyond the OR on at least 1.5x average volume. Entering on the first retest that holds gives a higher win rate.
- **Stop:** OR midpoint or the retest low, capped at 0.5 ATR.
- **Targets:** 1R, then 2R, then trail on VWAP.
- **Time stop:** 45 min. No entries after 11:00.
- **Expectancy:** 40–50% wins at about 1.8R.
- **Failure mode:** midcaps routinely fake the first break between 9:30 and 9:45.

**S3. VWAP reclaim or reject.**
- **Context:** after 10:00, VWAP sloping in the trade direction, positive relative strength.
- **Trigger and entry:** a tag of VWAP (within 0.1 ATR) or a dip below it reclaimed within 2 bars on rising volume. Enter above the reclaim bar's high.
- **Stop:** the dip low or VWAP minus 0.2 ATR.
- **Target:** the high of day, then extension.
- **Expectancy:** 50–55% wins at about 1.5R.
- **Failure mode:** on range days VWAP acts as a magnet, not support.

**S4. PDH/PDL acceptance.**
- **Trigger:** two consecutive 5-min closes beyond PDH (or PDL, multi-day range edge, 52-week high) after 10:00 with relative strength, or a break-retest-hold.
- **Stop:** back inside, PDH minus 0.25 ATR.
- **Targets:** the next level or 2R. A 52-week or all-time-high break with RVOL above 2 is also a swing candidate.
- **Failure mode:** breakouts at lunch on thin volume.

**S5. Relative-strength divergence.**
- **Setup:** Nifty falls at least 0.4% in 30 min while the stock holds VWAP with higher lows.
- **Entry:** when Nifty prints a 5-min higher low, buy the stock's break of its local high.
- **Stop:** the low made during the index dip.
- **Target:** 2R or the high of day.
- **Expectancy:** about 50% wins at 1.8R.
- **Failure mode:** on a true trend-down day the strong names eventually give way, with catch-up selling after 14:00.

**S6. Gap-fill fade.**
- **Context:** a 0.5–1.5 ATR gap without a material catalyst (sympathy or index-driven), into resistance.
- **Trigger:** the first 15-min candle closes below the open in its lower half, then a 5-min close below the OR low and VWAP.
- **Stop:** above the OR high.
- **Targets:** 50% gap fill, then the full fill.
- **Time stop:** 11:30.
- **Expectancy:** 55–60% wins at about 1.3R.
- **Blocked:** when the catalyst is material, and on trend days in the gap direction.

**S7. Results-day play.**
- **Hard rule:** no new position in a stock in the 30 min before its scheduled board outcome. Close any intraday position in it 15 min before the meeting starts.
- **After results:** wait 3–5 min. The LLM summarises the PDF in 60–120 seconds, deterministic code checks the numbers vs consensus, then trade the S1 logic.
- **Gap quality test:** gap aligned with the surprise and the first 30 min holding above the open means continuation (S1 or S2). Gap up with the first 30 min closing below the open means fade (S6) or avoid.

**S8. Post-lunch range break.**
- **Context:** a trend day; the stock has held a tight range (≤ 0.3 ATR) near the high of day from 12:00 to 13:30.
- **Trigger:** a break after 13:30 on at least 1.5x volume.
- **Stop:** the range low.
- **Target:** 1.5–2R by the flatten deadline.
- **Expectancy:** about 45% wins at 2R.

---

## 5. Scalping playbook (holds of 1–10 minutes)

**Where the fast model fits.** The LLM is never in the scalp decision loop: a 1–5 second call is fatal at this horizon. The LLM supplies, before the open and at each rescan, the scalp list, key levels and directional bias. The trigger itself is deterministic code plus, optionally, a small model such as gradient-boosted trees on order-book features. That model must decide in under 1 ms. This is how I read the owner's "quick decision models".

**Favourability gate (all must hold):**
- Spread ≤ 2 ticks and ≤ 4 bps.
- Exit-side top-5 depth ≥ 5x the order quantity.
- Median absolute 5-min move over the last 60 min ≥ 3x the estimated round-trip friction.
- VIX between 11 and 20 (above 22: off; below 10: moves too small).
- Time windows **09:25–11:15 and 13:45–14:40**. Off during lunch and after 14:40.
- Not within 15 min of scheduled news (for example 9:55–10:15 on RBI day).

**Scalp types:**
- **SC1. Depth-wall absorption or break.** A wall qualifies only if it is at least 5x the average level size, has persisted at least 60 seconds, and does not shrink by more than 50% as price comes within 3 ticks. That last test filters spoofing, which is common.
  - *Absorption:* at least 50% of the wall gets executed against without breaking and bids refill. Stop 2–3 ticks beyond the wall, target 2.5–3x the stop.
  - *Break:* the wall gets eaten through. Stop back inside the wall, target 0.3–0.5%.
- **SC2. Index-lead in heavyweights.** Nifty futures make a 1-min impulse of at least 0.15% on at least 3x volume, while a heavyweight has moved less than 50% of its beta-implied move. Stop 0.12–0.15%, target 0.25–0.3%, time stop 3 min. This is the edge most likely to be competed away at retail latency, so it needs tick-replay proof before it goes live.
- **SC3. Micro-pullback** in an in-play trend: a 1-min pullback to the 9 EMA or VWAP with top-5 bid/ask quantity ratio ≥ 1.5.
- **SC4. Failed-breakout snap:** price pokes less than 0.15% through the high of day or PDH, then a 1-min close back inside with the book flipping. Stop above the poke, target VWAP or 0.3–0.4%.

**Strict rules:**
- Max 6 scalps a day initially (8 later), max 3 per symbol.
- 2 consecutive losses: 15-min cool-off. 3 consecutive losses, or the bucket down Rs 5k: scalping off for the day.
- Net expected reward-to-risk ≥ 1.5. Hard max hold 10 min; exit at 3–5 min if not at +0.3R.
- Entries use marketable limits with IOC. The broker-side SL goes in immediately after the fill, backed by a local tick-level stop.
- **Go-live gate:** at least 200 paper scalps with net expectancy ≥ +0.15R under the pessimistic fill model (section 9).

---

## 6. Swing exception rules

**To qualify, all of these must hold:**
- The trade is already at least +1.5R by 14:30 and closing in the top 20% of the day's range on RVOL ≥ 2.
- There is a multi-day catalyst: a results beat with a guidance raise, an order above 15% of revenue, a policy re-rating, or a weekly 52-week/all-time-high breakout on at least 2x the 50-day average volume.
- Price is above a rising 20 and 50 DMA, and the sector index is above its 20 DMA.
- VIX is below 18 and not up more than 10% on the day.
- No binary event inside the holding window: the stock's own results, RBI, FOMC, US CPI, or a known geopolitical deadline.
- The LLM thesis names an explicit invalidation.

**Sizing:**

```
shock% = max(2 × P95|overnight gap| over 1y, floor)   floor: large 5% / mid 7% / small 10%; +2% if geo score ≥ 2
qty = floor(min(0.5% E / (price × shock%), 0.5% E / (entry − stop)))
Portfolio: Σ beta-adjusted shock under a Nifty −4% gap scenario ≤ 1.0% E;  max 3 overnight names
```

**Example:** a Rs 1,200 midcap with a 7% shock budget has Rs 84/share at risk on a shock, so qty = 59 shares, **about Rs 71k notional**. In this geopolitical regime, overnight cash positions are small sideline trades. Defined-risk option structures can express a swing thesis better (section 10).

**Rules:**
- **No leverage overnight and no MTF.** Cash delivery (CNC) only.
- Holding period 1–5 days, with a time stop on day 5 and a partial exit at +2R.
- Exit on a close below the 10 EMA.
- Cut the overnight book by 50% before weekends when the geopolitical score is 2 or higher.
- Never add to an overnight loser.
- SL orders on CAS stocks are cancelled at 15:15 (F2), so stops are re-armed through broker-side triggered orders (GTT) or a pre-open job each morning.

**Hedging:** one lot of Nifty futures far exceeds this book, so the hedge is an OTM Nifty put, used only when the overnight book is at least Rs 3L and the geopolitical score is at least 2. Cost capped at 0.15% of capital per week.

---

## 7. Time-of-day rules

| Window | Behaviour | System rule |
|---|---|---|
| 08:30–09:00 | Brief finalised | Health check (token, feed, margin). Any failure means no trading |
| 09:00–09:08 / 09:08–09:12 | Pre-open order entry, then matching (F4) | No orders. Read the indicative equilibrium price and imbalance for cash and futures |
| 09:15–09:25 | Wide spreads, leftover pre-open orders, stop hunts | Observe and build the OR. **No entries** |
| 09:25–11:30 | Best trend window, roughly 60–70% of the day's edge | All setups by day type |
| 11:30–13:15 | Lunch chop | No ORB or breakouts. S3 and S6 only; scalps off |
| 12:30 IST (until 25 Oct, then 13:30) | European open | Re-run day type; S8 window from 13:30 |
| 14:30–15:00 | Institutional closing flows; trend days extend, range days reverse | No new entries after **14:40 in CAS stocks** or **14:50 in non-CAS stocks** |
| 15:00–15:15 | Continuous trading for CAS stocks ends at 15:15; 15:00–15:15 sets the auction reference VWAP (F2) | **Flatten CAS stocks by 15:00 and non-CAS by 15:12** (broker deadlines are 15:10 / 15:25, F3) |

**Calendar effects:**
- **Nifty expiry Tuesdays:** heavyweights pin or whipsaw around the max-OI strikes after 13:30, so SC2 is off after 13:00.
- **Monthly expiry (last Tuesday):** no fresh positions in high-OI F&O stocks after 14:00.
- **The week after expiry:** new OI buildups carry the most signal.
- **Results season** (mid-Oct to mid-Nov, now starting): the in-play list will be dominated by results. Raise LLM PDF-parsing capacity and apply S7 rules strictly.
- **MSCI or Nifty rebalance days:** avoid affected names into the close.

---

## 8. Pre-market context checklist (LLM output, schema-validated)

```
market_context {
  global: {spx, ndx, us10y, dxy, brent, gold, nikkei, hsi, kospi: {chg_pct}},
  gift_nifty_implied_gap_pct, usdinr,
  flows: {fii_cash_prev, dii_cash_prev, fii_index_fut_long_pct, participant_oi_shift},
  vix: {level, chg_pct}, index_options: {max_call_oi_strike, max_put_oi_strike, pcr},
  events: [{time, type: results|board_mtg|RBI|CPI|FOMC|EIA|expiry|rebalance, symbol?, binary: bool}],
  sector_rs: [{sector, rs_1d, rs_5d, rs_20d}],
  geo_risk: {score: 0-3, items: ["Iran ceasefire status", "Brent>100", ...]},
  ban_list, surveillance_changes,
  filings_ranked: [{symbol, headline, materiality: 0-10, priced_in_flags, direction}],
  day_type_prior, risk_posture: normal|reduced|defensive   // may only REDUCE vs config
}
```

**Intraday re-assessment triggers (event-driven, not polling):**
- Nifty more than 0.5% from the open within 30 min, or more than 0.8% intraday.
- VIX up 5%.
- A/D crosses 1.0 after having been above 2 or below 0.5.
- Brent ±2% or USDINR ±0.3%.
- A material new filing on a watchlist name or a sector peer.
- Headline keywords: war, ceasefire, sanctions, RBI, SEBI, tariff.
- A position hits -1R abnormally fast (check the news).
- Peers hitting circuits.
- Scheduled checks at 09:30, 10:30, 12:30, 13:30 and 14:30.

---

## 9. Hard rules vs soft parameters

**Hard rules.** These live in code, the LLM cannot override them, and they change only by owner-signed config outside market hours.
1. DLL of 2% leads to flatten and lock; 3% trips the kill switch. Weekly 4%, monthly 8%, and the drawdown ladder.
2. Per-trade R ≤ 0.5% (scalps ≤ 0.2%), the stop-distance floor, and the open-risk invariant.
3. Every position has a broker-side stop within 5 seconds of the fill, or it is flattened.
4. Never average down, never widen a stop. Stops move only in the trade's favour.
5. Gross ≤ 4x (normally 3x), per-symbol ≤ 1.2x, sector and concurrency caps, a 20% free-margin buffer.
6. Intraday positions are flat by 15:00 (CAS) or 15:12 (non-CAS). Nothing is held overnight on intraday leverage, and there is no MTF.
7. Universe exclusions (section 2); shorts only in F&O or 20%-band stocks.
8. No entries 09:15–09:25 or after the 14:40/14:50 cutoffs. No trades in a stock in the 30 min before its results.
9. Limit or marketable-limit orders only. Order rate ≤ 2 per second (well under the SEBI 10/s threshold, F12). Duplicate-order guard. Broker position reconciliation every 5 seconds; any mismatch halts trading.
10. Stale feed (no ticks for more than 3 seconds on an active name, or more than 10 seconds on the index) means no new entries.
11. The LLM never creates orders. Its plans go through schema validation and then the risk veto.
12. Kill switch: manual via Telegram, plus automatic on the loss limits, more than 3 rejects in 5 minutes, or a latency spike.
13. **Paper fill realism:**
    - Cross the spread on marketable orders.
    - Fill limit orders only on a trade-through, or after the volume ahead in the queue has traded.
    - Stop slippage of max(2 ticks, 0.05%), or 0.2% in news shocks.
    - Charge the full costs from F6–F7.

**Soft parameters** the LLM may tune within bounds (every change logged):
- Disable setups (it cannot enable a blocked one).
- Size multiplier 0.25–1.0 (never above 1).
- In-play ranking and materiality scores.
- Targets of 1–4R and the choice of trailing method.
- Time stops of 10–60 min.
- Scalping on or off.
- Swing nominations (hard gates still apply).
- The day-type prior.

**Go-live gates [J]:**
- At least 30 paper sessions and at least 150 trades.
- Profit factor ≥ 1.3 net of costs, average ≥ +0.15R, max drawdown ≤ 6%, zero rule breaches.
- Then live at 25% size (R = Rs 1,250) for 4 weeks, then 50%, then 100%.
- If live slippage runs more than 30% worse than paper, step back down a size level.

---

## 10. F&O and commodities (later phases)

**F&O:**
- Since Budget 2026 (F6), stock futures cost more than cash for intraday, so they are not the default vehicle.
- **First:** (a) defined-risk directional option buys on Nifty for trend or event days, with the premium equal to R; (b) **debit spreads on stock options** for results and news continuation, and as the gap-proof way to express swing trades.
- Option selling stays with the existing agent. **If both agents share an account, one global risk ledger and DLL must cover both.**
- **Allocation once proven:** 15% of the risk budget, premium ≤ 0.5% of capital per trade, total premium outstanding ≤ 2%.

**MCX:**
- **First Crude Oil Mini**, then a gold mini contract, then Natural Gas Mini last (the most volatile).
  - Crude Oil Mini is driven by the current geopolitics and has a liquid evening session; the EIA inventory release is Wednesday at 20:00 IST (21:00 in US winter).
  - Gold mini works as a risk-off instrument.
- MCX trades 9:00 to 23:30 IST (to about 23:55 in US winter). A crude mini lot needed about Rs 27k margin in Sep 2026 ([Sahi](https://www.sahi.com/blogs/commodity-margin-lot-size-2026), M/L).
- R = Rs 2.5–3k, 1–2 lots, flat by 23:15.
- **The DLL is per calendar day across sessions.** If the equity session hit its limit, the evening session is blocked, which also prevents revenge trading.
- **Allocation:** 10% of the risk budget.

---

## Open questions for the owner

1. Do you accept a **2% hard DLL with a 3% catastrophic ceiling**, a weekly 4% and monthly 8% limit, and a **maximum tolerable drawdown** of, for example, 15% (Rs 1.5L), at which the system shuts down?
2. Will the existing options-selling agent use the **same Upstox account or margin**? If so, risk has to be aggregated across both agents and the budgets above shrink.
3. Is the Rs 10L entirely free cash, or partly pledged collateral? That changes the MIS headroom and the margin buffer.
4. During market hours, can you **approve trades on Telegram within about 30 seconds**? If not, semi-auto mode works only for S1/S7 and swing trades, and scalps must go fully automatic after the gate.
5. What exactly is **"Jev"**? Is it a specific fast model you have in mind? That decides the scalp decision layer.
6. **Shorting:** do you want short-side setups intraday? They roughly double the opportunity set, especially in the current FII-selling regime.
7. **Swing:** are you OK with small cash positions (about Rs 60k–1.25L each, given the gap budget), or would you rather express swing trades only through defined-risk option spreads?
8. **MCX evening session:** are you comfortable with automated trading until 23:15, given that commodities share the same daily limit?
9. **Hosting:** the SEBI framework needs a static IP and a daily re-login (F12). Where will the system run (a Mumbai-region VM?), and who does the daily 2FA?
10. What are your **live-capital go-live criteria**? I proposed 30 sessions, at least 150 trades, profit factor ≥ 1.3, drawdown ≤ 6%, then a 25% → 50% → 100% ramp.