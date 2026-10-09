# Indian market regulation, margin and transaction costs: report for the AI trading system (as of 2026-10-08)

**How this was researched.** Direct fetches of nseindia.com, zerodha.com, upstox.com and kite.trade were blocked by the sandbox proxy. Every fact below comes from web-search summaries of those pages and of broker, exchange and news coverage. Confidence tags reflect that:
- **[H]** high: several sources agree, or the item is a long-standing rule.
- **[M]** medium: one or two good sources, or the sources conflict a little.
- **[L]** low: one weak source.
- **[J]** marks my own judgment, not a verified fact.

---

## 0. Six findings that change the design

1. **Upstox allows only one active API app per user since 1 Apr 2026.** When a newer app is created, the older ones are deleted [M] ([Upstox community](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822), [summary](https://www.quotaguard.com/blog/configure-upstox-algo-trading-my-apps)). The existing options-selling agent probably already uses that app. If the new system creates its own app, it may delete the old agent's app.
   - **[J]** "Separate system" cannot mean a separate Upstox app. Options:
     - (a) One shared execution-gateway service owns the Upstox app, its token and the static IP, and both agents send orders through it.
     - (b) The new system trades through Zerodha, and Upstox stays its data source.
   - Both agents also share the client-level limit of 10 orders per second (OPS).
2. **The static IP rule applies to orders only.** Data and read-only calls can come from any IP [H] ([Zerodha support](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip)).
   - **[J]** So the system can be split: the execution adapter runs on one static-IP host (for example a Mumbai-region cloud VM), and data, LLM and feature services can run anywhere. Paper mode needs no static IP.
3. **Closing Auction Session (CAS), live since 3 Aug 2026.** For stocks with F&O contracts (most liquid Nifty 500 names), continuous trading ends at **15:15**. The 15:15–15:35 auction has no continuous matching. Resting stop-loss and iceberg orders are **cancelled automatically** at the switch to the auction [M-H] ([Angel One day-1](https://www.angelone.in/news/market-updates/nse-reports-strong-participation-on-day-1-of-closing-auction-session-for-f-o-stocks), [Geojit](https://support.geojit.com/support/solutions/articles/89000020950-what-is-closing-auction-session-cas-), [Outlook](https://www.outlookmoney.com/invest/nse-extended-fo-timings-and-new-closing-auction-session-rules-explained)). F&O now trades until **15:40**.
   - **[J]** Stop-losses resting at the broker give no protection after 15:15 for these stocks. Hard rule: be flat in stocks eligible for the auction by about 15:05.
4. **Stock futures now cost more per round trip than cash intraday.** Budget 2026 raised STT on futures sale value from 0.02% to 0.05% from 1 Apr 2026 [H]. Cash intraday STT is unchanged. The gap is about +2.1 bps per round trip.
   - **[J]** Do not scalp single-stock futures. Use cash with MIS (intraday product).
5. **Bought index options are about 10x cheaper than cash equity for scalping**, measured in R (one R = the rupee risk taken on a trade). The reason is that STT is charged on premium, not on the exposure the option gives (delta times notional). Cash equity scalps carry 0.15–0.5R of friction per trade unless the stop is wide (section 5d).
6. **Market orders are converted to protected orders.** Brokers turn them into "market price protection" (MPP) orders. Zerodha rejects them if `market_protection` is 0 [M] ([Kite forum](https://kite.trade/forum/discussion/comment/52082/)). In the pre-open, market orders are rejected from 09:05 to 09:10 (since 7 Sep 2026) [M].
   - **[J]** The execution layer should send only limit or marketable-limit orders with an explicit price cap.

---

## 1. SEBI retail algo framework: status in late 2026

**Verified facts**
- **Timeline** [H]
  - SEBI circular dated 4 Feb 2025. NSE implementation standards NSE/INVG/67858 dated 5 May 2025.
  - The deadline moved from Aug 2025 to Oct 2025, then to a glide path. It became fully binding on all brokers from **1 Apr 2026** ([Upstox news](https://upstox.com/news/market-news/financial-regulations/sebi-extends-timeline-for-retail-algo-trading-framework-sets-glide-path-for-brokers/article-182285/), [Fyers](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/)).
  - NSE/INVG/73992 (30 Apr 2026) covers broker filings for the "Client Direct API" category [M] ([NSE page](https://www.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading)).
  - I found no newer change to the core rules [M].
- **Threshold: 10 OPS per exchange (some sources say per segment) per client** [H].
  - Placing, modifying and cancelling orders all count. Fyers says stop-loss and target legs count too.
  - Above 10 OPS the strategy must be registered with the exchange through the broker. Brokers reject excess orders, and Zerodha returns HTTP 429 [M].
  - Sources differ on whether the one-second window is rolling or calendar-based [L].
- **Algo ID** [M]
  - Below the threshold there is no strategy registration. The exchange gives orders a **generic algo ID**, and the broker applies it.
  - Registered strategies get their own ID ([NSE FAQ Nov 2025](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail_Algo_03112025_NSE.pdf), [Zerodha explainer](https://zerodha.com/z-connect/featured/explaining-the-latest-sebi-algo-trading-regulations)).
  - Upstox has an `X-Algo-Name` header. Sources conflict on whether it carries the algo name or the ID, and whether it is needed only for exchange-approved strategies [L] ([Upstox JS SDK](https://unpkg.com/upstox-js-sdk@2.29.0/README.md)).
- **Static IP** [H]
  - One primary and one secondary IP, mapped to the API key.
  - The IP can change about once a week. On Upstox, changing it invalidates the current access token.
  - Orders from IPs not on the list are rejected. An IP can be shared only within the family (self, spouse, dependent children or parents) after the broker approves.
  - Kotak also requires the login session to come from the same IP [M].
- **Daily 2FA login, no long-lived refresh tokens.** Sessions are logged out at the end of each day [H].
- **White box vs black box** [H]
  - This matters only if the algo is offered to other people.
  - White box (logic disclosed) needs exchange registration.
  - Black box (logic hidden) needs the provider to register as a SEBI Research Analyst (RA), keep a research report for each algo, and re-register when the logic changes.
  - A self-built algo for personal use under 10 OPS needs no RA registration and no empanelment. A registered algo may be used by the household.
- **Hosting.** Retail algos are meant to run on the broker's infrastructure. The exception is "tech-savvy" clients who host their own logic behind a registered static IP. That exception is this system [M].
- **Brokers in practice**
  - **Upstox** [M]:
    - Static IP is required for place, modify and cancel only. It is set under My Apps → Static IPs.
    - One active app per user.
    - Market and SL-M orders go through market protection, with an optional `market_protection` parameter.
    - The v3 order endpoint is on `api-hft.upstox.com`.
    - Older Upstox order rate limits were 25/s, 250/min and 1000 per 30 min [L]. In practice the 10 OPS rule now binds first.
  - **Zerodha Kite** [M]:
    - The IP whitelist is in the developer profile, with one change per calendar week.
    - 10 OPS limit.
    - Market orders need `market_protection` above 0. Check the SDK version, because older pykiteconnect lacked the parameter.
    - The Connect plan is about ₹500/month per key with data. The personal tier is free for orders but has no data [L].

**[J] Recommendations**
- **Compliance gateway** as a module inside the execution layer, shared by every strategy and agent on the same client code:
  - A token bucket at **≤5 OPS per exchange**, counting place, modify and cancel. This leaves room for emergency flattening.
  - Throttle stop-loss changes: at most one modify per order every 2–3 s, so trailing stops cannot burn the OPS budget.
  - Reject any market order and convert it to a capped limit order.
  - Keep a full audit log for 5 years (brokers must; we should too).
- **Daily login** through a Telegram-pushed OAuth link. Check each broker's terms before automating TOTP 2FA.

---

## 2. F&O structure

**Expiry days** [H]
- Nifty 50 weekly: Tuesday. Monthly, quarterly and half-yearly: last Tuesday of the month.
- Sensex weekly: Thursday. Monthly: last Thursday.
- If the day is a holiday, expiry moves to the previous trading day.
- Bank Nifty, FinNifty and Midcap Select are monthly only. Weekly contracts for them were stopped on 20 Nov 2024 under the rule of one weekly index per exchange ([share.market](https://www.share.market/buzz/insights/weekly-expiry-days-in-indian-fo-markets/)).
- SEBI said in Oct 2025 that a consultation on weekly expiries would come. There is no decision yet [M] ([IANS](https://ianslive.in/cannot-just-shut-down-weekly-fo-expiries-tuhin-kanta-pandey--20251031130253)). **[J]** Build the expiry calendar from the daily instrument master. Never hard-code weekdays.

**Lot sizes** [M]
- From the Jan 2026 series: Nifty **65**, Bank Nifty **30**, FinNifty **60**, Midcap Select **120**, Sensex **20** ([Business Standard](https://www.business-standard.com/amp/markets/news/key-f-o-changes-from-today-lower-nifty-bank-nifty-lots-swiggy-3-more-to-debut-125123100084_1.html), [AlgoTest Jul/Sep 2026](https://algotest.in/blog/nifty-lot-size.md)).
- Lot sizes are reviewed about every six months. Stock lot sizes changed for the May and July 2026 expiries.
- **[J]** Always read lot size, tick size and freeze quantity from the instrument master each morning.

**Freeze quantity**
- Nifty was 1,800 through the first half of 2026. The NSE circular dated 1 Oct 2026 sets it at **3,510 (54 lots) from 5 Oct 2026** [M; one source] ([Choice](https://choiceindia.com/news/nse-revises-quantity-freeze-limit-for-index-fno-contracts-from-october-5-2026)).
- This is irrelevant at ₹10L capital, but the order splitter should still enforce it.

**F&O ban** [M-H]
- A ban starts when market-wide open interest reaches 95% of the market-wide position limit (MWPL) and ends when it falls to 80%.
- Since about 6 Dec 2025 the test uses **delta-weighted open interest ("FutEq OI")**. Options count by their delta.
- MWPL is the lower of 15% of free float or 65x average daily delivery value, with a floor of 10% of free float. It is recalculated quarterly.
- During a ban, only trades that reduce delta are allowed. The penalty is 1% of the excess value, minimum ₹5k and maximum ₹1L per day, plus GST. The exchange checks intraday with random snapshots ([Zerodha](https://zerodha.com/z-connect/updates/understanding-the-new-delta-oi-based-mwpl-framework), [Kotak](https://www.kotakneo.com/bulletins/sebi-new-f-o-rules-explained-delta-based-oi-new-mwpl-what-it-means-for-your-trading/)).
- The cash market is not affected by a ban.

**Intraday position limits for index options** [M-H]
- ₹5,000 cr net and ₹10,000 cr gross per side, in FutEq terms. Effective 1 Oct 2025, with penalties from 6 Dec 2025 ([TaxGuru](https://taxguru.in/sebi/sebi-tightens-intraday-position-limits-derivatives.html)).
- Not binding for this account.

**Expiry-day rules** [H] ([Zerodha](https://zerodha.com/z-connect/business-updates/sebis-new-rules-for-index-derivatives-heres-whats-changing))
- Extra **2% ELM (extreme loss margin) on short options** on expiry day (since 20 Nov 2024).
- No calendar-spread margin benefit on expiry day (since 10 Feb 2025).
- Option premium is collected upfront from buyers (Feb 2025).

**Other 2025–26 changes**
- **F&O pre-open** [H]: 09:00–09:15 call auction for current-month futures since 8 Dec 2025. Options are excluded.
- **Revised pre-open** for cash and F&O from 7 Sep 2026 [M]:
  - 09:00–09:05: market and limit orders.
  - 09:05–09:10: limit orders only, with a random close between 09:08 and 09:10.
  - 09:10–09:12: matching.
  - 09:12–09:15: buffer.
  - Source: [5paisa](https://www.5paisa.com/blog/nse-pre-open-session-rules).
- **CAS** and the 15:40 F&O close (see §0.3). On day 1, Nifty's official close was about 200 points above its 15:15 last traded price [M].
  - **[J]** The feature engine must treat the official close of auction-eligible stocks as an auction price, not as the last continuous trade. This affects prior-day close, VWAP anchors and backtest labels after 3 Aug 2026.
- **Stock F&O eligibility** [H], from SEBI's 30 Aug 2024 circular:
  - Median quarter-sigma order size (MQSOS) at least ₹75L.
  - MWPL at least ₹1,500 cr.
  - Average daily delivery value (ADDV) at least ₹35 cr.
  - Exits keep happening, for example Exide and Nuvama after 29 Jul 2026 ([Kotak](https://www.kotakneo.com/news/stocks/nse-remove-exide-nuvama-wealth-fo-segment-july-2026/)). **[J]** "Has stock F&O" is a good liquidity filter for the scalping universe.

---

## 3. Intraday equity margin and leverage

- **Exchange minimum margin** [H]: the higher of **20%** of trade value or VaR+ELM (plus any ad hoc margin), for both intraday and delivery. That caps intraday leverage at **5x**. For volatile names VaR+ELM is higher and leverage is lower ([Zerodha](https://support.zerodha.com/category/trading-and-markets/margins/margin-leverage-and-product-and-order-types/articles/different-types-of-margin)).
- Peak-margin snapshots apply. Brokers block margin when the order is placed.
- **Upstox** [M]: up to 5x on equity intraday. F&O intraday is 1x, meaning the normal NRML margin with no extra leverage.
- **Zerodha** [M]: up to 5x on equity MIS. Leverage varies by stock, so check the live margin calculator.
- **Auto square-off**
  - **Upstox** [M], from 11 Sep 2026: **15:10 for stocks eligible for the closing auction**, 15:25 for other stocks and for F&O. The charge is **₹75+GST (₹88.5)** on the basic plan and ₹50+GST on Plus ([Upstox notice](https://upstox.com/announcements/revised-timings/important-update-intraday-square-off-timings-are-changing/), [charges](https://upstox.com/help-center/what-are-auto-square-off-charges-248671/)). The cutoff for new intraday orders comes a few minutes earlier.
  - **Zerodha**: ₹50+GST per order, with large positions split at 30,000 quantity [H]. The square-off time is 15:20/15:25 on older pages and probably changed after CAS [L] ([Zerodha](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/auto-square-off)).
  - **[J]** The system should be flat by **15:05** in auction-eligible stocks and by **15:15** in other stocks. It should never leave a position for the broker to auto-square-off.
- **Price bands** [H; standing rule, not re-verified today]:
  - Stocks without F&O have fixed 2/5/10/20% bands.
  - F&O stocks have dynamic bands of about 10% that the exchange widens in steps.
  - Market-wide circuit breakers sit at 10%, 15% and 20%.
  - **[J]** Block new entries within about 1% of a band. A locked circuit leaves the position impossible to exit.
- **Exclude from MIS** [H]:
  - Trade-to-Trade stocks (BE/BZ series): no intraday trading.
  - ASM/GSM surveillance stages with 50–100% margin.
  - **[J]** The universe builder should load the ASM/GSM lists, the T2T series and the F&O ban list every morning.
- **MTF (margin trading facility) for swing** [M]:
  - Zerodha: 0.04%/day (about 14.6% a year), up to 5x on eligible NSE stocks, pledge ₹15+GST ([Zerodha](https://support.zerodha.com/category/trading-and-markets/margins/margin-trading-facility/articles/interest-calculation-for-mtf)).
  - Upstox: about ₹20/day per ₹40k funded (about 18% a year), up to 4x [L].
  - **[J]** The owner's main fear is gaps from war or geopolitical news. Run swing trades unleveraged, as CNC delivery. MTF interest is minor; a leveraged overnight gap is the real risk.
- **Owner's 4x limit [J].** Keep it as a gross-exposure policy limit, below the broker's 5x. In practice the per-trade risk budget will be the tighter limit (see §5d).

---

## 4. Current transaction costs

| Component | Equity intraday | Stock/index futures | Options (on premium) | Confidence |
|---|---|---|---|---|
| Brokerage, Zerodha | min(₹20, 0.03%) per order | min(₹20, 0.03%) | ₹20 flat | H |
| Brokerage, Upstox | min(₹20, 0.1%) (one page says 0.05%) | min(₹20, 0.05%) | ₹20 flat | M |
| STT | 0.025% sell side | **0.05% sell side** (was 0.02%) | **0.15% sell side** (was 0.10%). Exercised options: 0.15% of intrinsic value | H |
| NSE transaction charge, from 1 Mar 2026 | **0.00307%** | **0.00183%** | **0.03553%** | M-H |
| BSE transaction charge | 0.00375% (groups A/B) | 0 | 0.0325% Sensex/Bankex; 0.005% stock options | M |
| SEBI fee | 0.0001% (₹10/cr) | same | same | H |
| Stamp duty, buy side | 0.003% | 0.002% | 0.003% | H |
| GST | 18% on brokerage + transaction charge + SEBI fee (Upstox adds DP charges) | | | H |
| IPFT (Investor Protection Fund Trust) | about ₹0.01/cr, now folded into the NSE rate | | | M |
| DP charge (delivery sell only) | Upstox ₹18.5 per scrip per day; Zerodha about ₹13.5+GST | | | M |

Sources for the table:
- NSE rates: the 27 Feb 2026 circular NSE/FA/73061 rolled back the IPFT increase and raised transaction charges by the same amount. That turned the Oct-2024 rates (0.00297 / 0.00173 / 0.03503) into the figures above ([NSE circular](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf), [Zerodha support](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/exchange-transaction-charges)).
- STT: [ICICI Direct](https://www.icicidirect.com/ilearn/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-should-know).
- Stamp duty: [NSE](https://www.nseindia.com/static/invest/first-time-investor-stamp-duty-charges-taxes).
- Upstox brokerage: [Upstox](https://upstox.com/brokerage-charges/).
- Ticks since 15 Apr 2025 [H]: below ₹250, ₹0.01; ₹250–1,000, ₹0.05; ₹1,000–5,000, ₹0.10; ₹5,000–10,000, ₹0.50. Options tick at ₹0.05 ([Zerodha](https://zerodha.com/marketintel/bulletin/408151/revision-in-tick-size-for-nse-derivatives-and-cash-segment-from-april-15-2025)).

**[J] Cost-model plug-in.** Rates changed three times in 18 months (Oct 2024, Mar 2026, Apr 2026). Keep the cost schedules as data with effective dates. The paper broker and the backtester both use them. Live fills are reconciled against the broker's contract notes.

```yaml
cost_schedules:
  - id: nse_2026_04
    effective_from: 2026-04-01
    eq_intraday: {stt_sell: 0.00025, txn: 0.0000307, stamp_buy: 0.00003}
    futures:     {stt_sell: 0.0005,  txn: 0.0000183, stamp_buy: 0.00002}
    options:     {stt_sell_premium: 0.0015, txn_premium: 0.0003553, stamp_buy: 0.00003}
    sebi_fee: 0.000001
    gst: 0.18
brokers:
  upstox: {eq_intraday: {flat: 20, pct: 0.001}, futures: {flat: 20, pct: 0.0005}, options: {flat: 20}}
  zerodha: {eq_intraday: {flat: 20, pct: 0.0003}, futures: {flat: 20, pct: 0.0003}, options: {flat: 20}}
```

---

## 5. Round-trip costs and break-evens (computed)

Definitions:
- B = brokerage for both legs. Above about ₹67k notional this is ₹40 at both brokers.
- T = transaction charge × 2N, where N is notional.
- S = SEBI fee × 2N.
- GST = 18% × (B + T + S).

### (a) Equity intraday round trip

| Item | ₹2L notional | ₹4L notional |
|---|---|---|
| Brokerage (2 × ₹20) | 40.00 | 40.00 |
| NSE transaction (0.00307% × 2N) | 12.28 | 24.56 |
| SEBI fee | 0.40 | 0.80 |
| STT (0.025% × N) | 50.00 | 100.00 |
| Stamp duty (0.003% × N) | 6.00 | 12.00 |
| GST | 9.48 | 11.76 |
| **Total** | **₹118.16 = 5.91 bps** | **₹189.12 = 4.73 bps** |

- General form: cost ≈ **3.55 bps × N + ₹47.2 fixed**. At ₹10L that is 4.0 bps.
- Example: ₹4L of a ₹1,000 stock (400 shares) breaks even at **+₹0.47 per share**, before spread.

### (b) Stock futures, ₹10L notional, one round trip

- Brokerage 40 + transaction 36.60 + SEBI 2.00 + **STT 500.00** + stamp 20.00 + GST 14.15 = **₹612.75 = 6.13 bps**.
- Before April 2026 the same trade cost ₹312.75 (3.13 bps). STT is now 82% of the cost.
- General form: **5.66 bps × N + ₹47.2**, which is about 2.1 bps more than cash intraday at every size.

### (c) Nifty option, 1 lot (65 units), bought at ₹100

- Buy premium ₹6,500.
- **Sold at ₹110** (sale premium ₹7,150): brokerage 40 + transaction 4.85 + STT 10.72 + stamp 0.20 + SEBI 0.01 + GST 8.08 = **₹63.86**.
  - Gross ₹650. **Net ₹586.14.**
- **Sold at ₹105** (sale premium ₹6,825): charges **₹63.23**.
  - Gross ₹325. **Net ₹261.77.**
- **Fee-only break-even exit price: ₹100.97** (+0.97 premium points).
  - At delta 0.5 that is about 2 Nifty points.
  - Adding a 0.05–0.10 bid-ask spread and 0.05–0.10 slippage per side, the realistic break-even is **about 1.2–1.5 premium points, or about 2.5–3 Nifty points**.
- At 3 lots the fee break-even falls to 0.50 points, because the ₹40 brokerage is fixed.

### (d) 1–10 minute scalp in a liquid Nifty 500 stock

**Assumptions [J]:**
- Bid-ask spread of 1–3 bps. A Rs 1,000 stock with a ₹0.10 tick has a 1 bp minimum spread.
- Aggressive entry and exit (marketable limit orders), so the full spread is paid once per round trip.
- Slippage and impact of 1 bp per side in normal conditions, 2–3 bps per side in a fast tape.

**Minimum gross move to break even:**

| Notional | Fees | + spread | + slippage | **Minimum gross move** |
|---|---|---|---|---|
| ₹2L | 5.9 bps | 1–3 | 2–6 | **9–15 bps** (₹0.9–1.5 on a ₹1,000 stock) |
| ₹4L | 4.7 | 1–3 | 2–6 | **8–14 bps** |
| ₹12.5L | 3.9 | 1–3 | 2–6 | **7–13 bps** |

Fully passive limit orders save the spread. They pay instead through adverse selection and missed fills, and the paper simulator must model that honestly using queue position from the 30-level depth.

**Friction in R terms.** This is the number that matters. Assume risk per trade of ₹5,000 (0.5% of capital). Then notional = 5,000 / stop distance. With a 2 bp spread and 1 bp slippage per side:

| Stop distance | Notional | Cash equity friction | Stock futures friction |
|---|---|---|---|
| 15 bps | ₹33.3L | ₹2,563 = **0.51R** | 0.65R |
| 25 bps | ₹20.0L | ₹1,557 = 0.31R | 0.40R |
| 40 bps | ₹12.5L | ₹991 = **0.20R** | 0.25R |
| 60 bps | ₹8.3L | ₹676 = 0.14R | 0.17R |

- Rule of thumb: **friction in R ≈ (3.55 + spread + 2 × slippage) / stop in bps**.
- Compare a **Nifty ATM option at ₹100 premium, 5 lots, 15-point premium stop.** The stop is about 30 index points, roughly 12 bps of the index.
  - Fees ₹124.
  - Normal market: about ₹222 all-in, **0.044R**.
  - Stressed market (0.30 spread, 0.25 slippage per side): about ₹384, 0.077R.
- **Annual friction example.** 6 cash-equity trades a day at a 40 bp stop × 250 days = 1,500 trades × ₹991 ≈ **₹14.9L a year, about 149% of capital**. The strategy needs an edge of about 0.2R per trade before costs just to break even.

**[J] What this means for scalping, by instrument**
- **Cash equity (MIS).** Viable only for stocks clearly in play (news, gap, RVOL above 3), where the expected 1–10 minute move is **at least 40–60 bps and the stop at least 40 bps**. Limit to about 3–6 trades a day.
  - Hard gate in the setup engine: **reject any trade where expected friction / stop distance exceeds 0.20, or expected move / friction is below 3.**
- **Stock futures.** Do not scalp them. They are strictly worse than cash for round trips since April 2026. Use them only for overnight short swings.
- **Index options, long, Nifty weekly.** Cheapest in R by about 10x, so this is the best vehicle for index-direction scalps. The risks are crowding, vega and IV-crush, expiry-day gamma, and gappy option stops. Avoid entries in the last 60–90 minutes of an expiry day unless the strategy is designed for it.
  - Note that this conflicts with the owner's stated focus on stocks. Raise it with the owner.
- **Stock options.** Avoid for scalping. Spreads of 0.5–2% of premium beyond the top few dozen names wipe out the STT advantage.
- **Option selling as a scalp.** Not suitable. The margin per lot is large, the expiry-day 2% ELM adds to it, and it overlaps with the existing agent.

---

## 6. Tax notes affecting the design (brief; confirm with a CA)

- The **Income-tax Act, 2025 took effect on 1 Apr 2026**. Treatment of trading income is unchanged; section numbers changed, and the old 44AB audit section is now **Section 63** [M] ([Upstox](https://upstox.com/news/personal-finance/tax/income-tax-act-2025-f-and-o-taxation-turnover-calculation-loss-set-off-and-carry-forward-explained/article-200609/)).
- **Intraday equity is speculative business income.** Losses can only be set off against speculative income and carried forward 4 years [H].
- **F&O is non-speculative business income.** Losses can be set off against other business income (not salary) and carried forward 8 years [H].
- **Audit threshold** [M] ([CAalley](https://caalley.com/news-updates/indian-news/stock-traders-alert-when-income-tax-audit-becomes-mandatory-for-ay-2026-27)):
  - ₹1 cr turnover, or **₹10 cr if cash transactions are 5% or less**. Trading through a broker is all digital, so ₹10 cr effectively applies.
  - Turnover = sum of absolute profits and absolute losses, per the ICAI guidance note. Sources differ on whether premium from options sold is included.
  - Example: 1,500 trades at an average absolute P&L of ₹2k gives about ₹30L turnover, far below the threshold.
  - An audit can also be triggered by declaring profit below the presumptive rate while income exceeds the basic exemption [M].
- **Swing trades** held a few days in delivery are short-term capital gains at 20%, or business income if frequent. The CA should decide which.
- **[J] Journal requirements:**
  - Tag every fill with a tax bucket: SPEC (intraday cash), NONSPEC (F&O) or STCG/BUSINESS (delivery).
  - Store each charge component per fill, reconciled to the contract note.
  - Compute ICAI turnover per bucket.
  - STT is deductible as a business expense when the income is business income.

---

## Open questions for the owner

1. **Upstox app conflict.** Does the existing options-selling agent use an Upstox API app today? If yes, which do you prefer:
   - (a) one shared execution gateway for both agents, with one OPS budget, one token and one static IP; or
   - (b) the new system executes through Zerodha, with Upstox for data only?
2. **Instrument scope for scalping.** The cost math strongly favours bought Nifty weekly options over cash equity for 1–10 minute holds. Are index options allowed in phase 1, or only Nifty 500 cash?
3. **Risk per trade.** Is ₹5k (0.5%) per trade with a ₹20–30k daily stop right? It sets notional size, and through that the friction ratio and the realistic number of trades per day (about 4–6 before the daily stop is at risk).
4. **Upstox plan.** Which plan are you on: basic, where auto square-off costs ₹88.5, or Plus, where it costs ₹59 and brokerage may differ? I need it to fix the paper cost model.
5. **Hosting.** Can you run a cloud VM with a static IP in the Mumbai region? It is needed for live orders only, not for paper trading.
6. **Daily login.** Is it acceptable to tap a Telegram link each morning for 2FA login, or do you want automated TOTP? The second depends on each broker's terms.
7. **Swing trades.** Unleveraged CNC only, or is MTF allowed? Is there a maximum overnight gross exposure, for example 30% of capital?
8. **Tax status.** Do you have other business income for F&O losses to offset, and does the existing agent's F&O turnover share the same PAN? Both affect the audit and set-off planning.