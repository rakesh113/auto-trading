# Red-Team Review: Indian Markets Trading System Design (as of 2026-10-08)

**Reviewer stance:** sceptical prop-desk head and senior SRE. **[V]** means I checked it by web search today. Everything else is my judgment.

---

## 0. Verdict

1. **The architecture is sound. The strategy scope is not.** The core choices are right: ports and adapters, the LLM can only narrow what the system does, risk rules are deterministic, and paper and live share one engine. But the seven reports together specify about 18 setups, 8 LLM agents, two ML models, three counterfactual paper books and a 10-service infrastructure stack. That is far too much for one developer and ₹10L of capital.
2. **1–10 minute cash scalping is the weakest bet.** At a 30 bps stop, friction is about 0.28R per trade (R = the rupees lost if the stop is hit). The feed sends conflated snapshots, not every trade, and no historical depth data exists. Run scalping as a recording-and-research track for months. It should not be a phase-1 deliverable.
3. **The biggest unresolved risk is operational: the Upstox account.**
   - Upstox allows only one active API app per user. When a new app is created, older apps are deleted [V].
   - The workspace's skill list says the existing options-selling agent runs on the owner's Upstox account through a local custom Upstox MCP.
   - If the new system generates a token or creates an app on that account, it can blind or delete the live agent.
4. **The go-live gates cannot be met as written.** "200 trades per setup" across about 14 setups, at roughly 8 trades a day, needs about 350 sessions. Cut to 2–3 setups.
5. **Timing:** the recorder should run in weeks 1–2, and a minimal paper system should trade unattended by week 4–5.

---

## 1. Contradictions between reports

| Topic | What the reports say | Most likely correct | Why it matters |
|---|---|---|---|
| Upstox brokerage | Regulation, scalping, paper-sim and playbook use ₹20/order. Broker-apis says ₹30 on Plus. | **₹30 or 0.1% (whichever is lower) on Plus** [V]. The owner uses 30-level depth, which is a Plus feature, so the owner is on Plus. | Fixed cost per round trip is ₹70.8 including GST, against ₹47.2 at Zerodha. At 10 round trips a day that is about ₹59k a year, roughly 6% of capital. Every cost table needs redoing. |
| NSE cash transaction charge | Scalping and playbook use 0.00297%. Regulation and paper-sim use 0.00307%. | **0.00307% from 1 Mar 2026** (circular FA73061, which offset the IPFT rollback) [V]. | The cost difference is small. The real lesson is that cost schedules must be stored with effective dates. |
| Broker MIS square-off | Paper-sim: Upstox 15:05/15:20. Regulation and playbook: 15:10/15:25. | **Upstox 15:10 for CAS stocks and 15:25 for others, from 11 Sep 2026** [V]. **Zerodha 15:12 for CAS stocks** [V]. The Upstox help page is out of date. | The architecture report's plan to flatten MIS at 15:10 lands exactly on the broker's square-off, after the broker's cutoff for new orders. That is wrong. |
| System flatten deadline | 14:55, 15:00, 15:05 and 15:10 across the reports | **No new entries after 14:40–14:45. CAS names flat by 15:00. Non-CAS names flat by 15:15.** | Exits need room for retries, and resting SL orders are cancelled at 15:15 [V]. |
| Pre-open session | Playbook: order entry 09:00–09:08 | **New rules since 7 Sep 2026** [V]: market and limit orders 09:00–09:05; limit orders only 09:05–09:10, closing at a random time between 09:08 and 09:10; matching 09:10–09:12. SL orders are not accepted in pre-open. | The final pre-open price (IEP) arrives around 09:12. The watchlist should be built then, not at 09:08. |
| Order-rate cap | 8/s (architecture), 5/s (regulation, scalping), 2/s (playbook) | **5/s with priority** (flatten > stop > exit > entry), shared with the other agent if both use one account. | At 2/s, flattening 6 positions (12 orders) takes 6 seconds. At these trade counts, 5/s never binds otherwise. |
| Upstox REST limits | Broker-apis: 1,000 per 30 minutes for the whole account | **25/s, 250/min, 1,000 per 30 minutes, applied per endpoint per user** [V-M] | Option-chain polling does not use up the historical-data budget. The ~14-hour 1-minute backfill estimate still holds. All limits are shared with the existing agent. |
| Overnight stops via GTT | Playbook: re-arm CAS swing stops through GTT | **Upstox's GTT API requires an ENTRY leg, so it cannot protect a position already held** [V-M]. Zerodha's single-leg GTT can. | The swing-protection plan works only on Zerodha. Otherwise a 09:15 job places stops, and positions are unprotected through the pre-open. |
| "Jev" | Architecture, playbook and LLM layer treat it as a typo | **A real product**: TypeSafe AI's "System One" typed-decision model, in early access since 15–16 Sep 2026, with vendor-claimed latency of 70–500 ms. It is listed in DigitalOcean's model catalogue [V]. | The scalping report is right. Use Jev only as a shadow challenger for news triage, never on numbers in the trading hot path. |
| Risk per trade | Intraday: 0.5% (playbook), 0.4% (architecture). Scalps: 0.15–0.2% (playbook), 0.25% (scalping, architecture). | **Intraday 0.5% cap, run at 0.25% in the first live phase. Scalps 0.25%.** | Below ₹2,500, the fixed ₹70.8 brokerage alone costs 0.03–0.05R. |
| Daily stops and scalp budget | Architecture: −1.5/−2/−2.5%. Playbook: −1.2/−2% (flatten and lock)/−3% (kill). Scalp budget ₹10k (scalping) vs ₹5k (playbook). | **The playbook's ladder plus its open-risk invariant.** Scalping gets ₹5k while unproven. | The invariant counts open risk to stops, so a new trade cannot make a breach of the daily limit possible. |
| Go-live gates | Playbook: ≥30 sessions and ≥150 trades in total. Scalping: ≥200 trades per setup. Paper-sim: SPRT per setup. | **SPRT per setup on the conservative fill tier** | 150 trades in total gives a confidence interval of about ±0.18R, which proves nothing. Per-setup gates are right, but only with few setups. |
| Stop floor vs scalp examples | Playbook sets a 0.25% stop floor, then its Example C and SC2 use 0.12–0.15%. The scalping report requires friction ≤0.2R (stops of 30–35 bps or more), then its index-lead and absorption setups use 0.15–0.3%. | **Enforce the friction-to-stop gate in code.** | Several of the specified scalps fail the reports' own cost rule by construction. |
| News-to-decision latency | Scalping: the deep LLM must confirm within 30 s. LLM layer: materiality analysis p95 40 s, and an actionable plan 45–100 s after the news. | **The LLM layer's figures** | The news-shock setup has to work on fast triage plus price confirmation, or accept a 60–100 s delay. |
| Day-type timing | Playbook classifies at 09:45 on the 30-minute opening range. Yet ORB and opening drive (09:20–11:00) are called "60–70% of the edge". | **Contradiction** | The gate does not exist when most setups fire. Use the pre-market prior plus a provisional 09:30 label at reduced size. |
| Bars built from snapshots | Architecture builds bars locally from snapshot ticks. Research uses broker 1-minute candles. | **Skew** | Snapshots miss highs and lows between frames, so research bars and live bars differ. Use the feed's own 1-minute OHLC fields and reconcile them against broker candles. |
| Claude prices | LLM report: Sonnet 5.5 cache reads $0.10/MTok | **$0.20** (Claude pricing reference cached 2026-10-06). The other Claude prices and model IDs are correct. | Cost estimates are slightly low. |

---

## 2. Unrealistic assumptions: where it loses money or breaks

- **Scalping edge after costs.** Example: R = ₹2,500 with a 30 bps stop gives ₹8.3L of notional.
  - Costs: ₹296 statutory, ₹71 brokerage (Upstox Plus), about ₹333 for spread plus slippage.
  - Total ≈ ₹700, or **0.28R per trade**.
  - At a 1.5R target, the strategy needs a **51% win rate just to break even**.
  - SEBI's own study found 70% of individual intraday traders lose money.
  - Compare intraday setups held 10–60 minutes with 0.6–1% stops: friction is about 0.1R. **That is where to look for edge first.**
- **Feed granularity.**
  - The feed sends 1–4 conflated snapshots per second.
  - Some users report receiving only 5 levels in 30-level mode.
  - Order-flow and queue features are coarse at about 1 Hz.
  - Trades are inferred from volume deltas, so the "absorption" and "wall" setups are only research-grade.
- **ML timeline.**
  - About 1,000 independent rows per day.
  - The meta-filter needs 50–100 pooled sessions.
  - Any ML influencing trades before month 4–6 is unjustified.
- **Candle research across regime breaks.** Upstox 1-minute history since 2022 spans:
  - the tick-size change (Apr 2025);
  - weekly-expiry consolidation (Nov 2024);
  - the STT increase (Apr 2026);
  - the closing auction (Aug 2026), which makes the last 15 minutes before Aug 2026 unrepresentative;
  - the pre-open revision (Sep 2026).

  Weight post-April 2025 data, and treat everything before as low-confidence.
- **Paper optimism the reports underweight.**
  - Unknown behaviour of the unfilled remainder under market price protection.
  - "Phantom" target fills.
  - The α = 0.7 displayed-liquidity factor is a guess.
  - No modelling of how other participants react to our orders.
  - Paper results that ignore human-approval delay.
- **Semi-auto (Telegram approval) stage.** An approval delay of 20–90 seconds kills 1–10 minute scalps and degrades opening setups. Use approvals only for overnight and swing decisions.
- **Expected returns.** The scalping report's ₹2.5–6k a day works out to 60–150% a year. That is not a planning number. Treat **break-even after costs in year 1** as success.
- **Leverage.** With risk-based sizing, gross exposure only reaches 4x through tight stops, and tight stops are what friction rules out. Expect 1–2.5x in practice. The owner should not read unused leverage as a missed opportunity.
- **Operating costs against capital.**
  - LLM "Lean+" profile: ₹11–13k a month.
  - Two VPS machines, Kite data and storage: ₹5–8k a month.
  - Possible news feed: about ₹25k a month.
  - Total: **₹15–25k a month, or 18–30% of capital a year**, before trading costs. LLM spend should stay at or below ₹5k a month during paper trading.
- **Adaptive loops.** Three loops run at once: weekly LightGBM retraining, the weekly LLM playbook tuner, and monthly fill recalibration. Add model upgrades and the system changes faster than evidence accumulates. Freeze parameters for each evaluation window.
- **Upstox app creation.** A forum thread reports "API app creation paused for retail clients" [L]. Do not plan on getting a second app.

---

## 3. Gaps no report covered (or covered only in passing)

1. **Calendar.**
   - Muhurat trading is on Sunday 8 Nov 2026, time not yet announced [V].
   - **Tuesday 10 Nov 2026 is a holiday, so that week's Nifty weekly expiry moves to Monday 9 Nov** [V].
   - Special sessions: DR-site live sessions, and the special pre-open for IPO listings, relistings and demergers.
   - Default: the system is disabled in any special session. Expiry dates are read from the instrument master.
2. **Interactions with the existing agent.**
   - F&O positions net per client at the exchange.
   - Margin is shared: a margin spike in the option book can trigger MIS square-off or peak-margin penalties.
   - Loss caps must be combined.
   - Manual orders placed through the MCP will look like "external" orders to reconciliation.
   - If the static IP is the owner's home IP, the new VM uses up the backup slot that the standby-VPS plan assumed was free.
3. **MCX.** Upstox temporarily disabled API trading on MCX in April 2026 [V-M]. The MCX roadmap may need Zerodha.
4. **NSE scraping.** Community reports say NSE blocks cloud IP ranges (including AWS), and scripted access appears to be against NSE's terms [V-M]. A filings scraper on a Mumbai VM may simply fail. Options: BSE feeds, the exchanges' CSV and RSS downloads, a paid feed, or ingestion from home.
5. **Broker-outage runbook.** The dead-man process uses the same broker API. If that API is down, only exchange-resident stops, the broker's mobile app and its call-and-trade desk remain. Write the manual runbook and rehearse it.
6. **Exchange outages and extended sessions.** Derive the session clock from market-status messages. Never hard-code square-off times.
7. **Corporate actions intraday.** Adjust levels on ex-dates (previous close, previous high, VWAP anchors). Handle symbol and ISIN changes, and stocks leaving F&O.
8. **Control-plane security.**
   - Telegram commands: chat-ID allowlist, a PIN, and tighten-only actions (nothing that enables trading or loosens risk).
   - Use separate bots for alerts and for commands.
   - Rotate API secrets. Never store TOTP seeds.
   - The Upstox token webhook is unsigned, so it needs verification.
   - Audit-log every human override.
9. **Human-override UX.** A "manual takeover" action that disowns a position but keeps its stop. A per-symbol pause. A daily end-of-day attestation.
10. **LLM model drift.** Pinned models get retired, and defaults change (Opus 5.5 defaults to medium effort, for example). Pin effort explicitly, and re-run the golden set on every model change.
11. **Disaster recovery for the recorder.** Recorded depth cannot be replaced. Replicate it to object storage daily and run a restore drill.
12. **Regulatory and tax.** Keep order and LLM logs for at least 5 years. Confirm the broker's algo-declaration requirements (`X-Algo-Name` on Upstox, `algo_id` on Kite). If both agents trade under one PAN, ICAI turnover and set-off must be computed together.

---

## 4. Top 10 risks to the project, with mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **No net edge after costs**, especially in scalping. | Friction-to-stop gate (≤0.2R) in code. Prioritise 10–60 minute in-play setups. Kill rule: a setup that is unprofitable on candles at +2 bps of extra slippage is dropped. Scalping stays paper-only until it passes SPRT. |
| 2 | **Shared Upstox app, token and IP** blinds or deletes the existing agent. | The new system never creates an Upstox app or generates trading tokens there. Data comes through the Analytics Token, after Upstox confirms in writing that it leaves the existing app and token alone. Execution runs on a separate Zerodha account. |
| 3 | **The gap between paper and live** leads to a false go-live. | Decide only on the conservative fill tier. Start 1-share live probes by week 5–6. Run a paper "shadow twin" of every live order. Calibrate until the live-minus-paper shortfall is ≤0.03R. |
| 4 | **Too little data and too many setups** to tell skill from luck. | At most 3 setups at the first gate. SPRT per setup. A registry of every variant tried. Parameters frozen per evaluation window. |
| 5 | **Build complexity**: the project never reaches stable paper trading. | Build the MVP in §6. No NATS, Loki, critic agent, tuner or ML until the paper system has run unattended for 20 days. |
| 6 | **An unprotected or un-flattened position**: SLs cancelled at 15:15, broker outage, OMS bug. | Exchange-resident SL within 2–5 s of every fill. The naked-position invariant. CAS names flat by 15:00. The dead-man process. A manual runbook. Property tests on the order state machine. |
| 7 | **The LLM layer adds cost without measurable uplift.** | A permanent no-LLM baseline book. LLM spend capped at ₹5k a month in paper. Any agent that does not beat its cost is switched off. |
| 8 | **Tail and regime risk**: a geopolitical shock (VIX +26% in one day, Jul 2026), a locked circuit, an ad hoc margin hike, correlation with the short-volatility agent. | VIX and event gates. Shorts only in F&O stocks. A 20% free-margin buffer. A combined loss ledger across both agents. |
| 9 | **Fragile data sources**: NSE blocking, unofficial endpoints, incomplete 30-level frames, instrument master changes. | Count depth levels in every frame. Run the instrument master build and mapping check at 07:30, and refuse to trade if they fail. Keep a second source for filings. |
| 10 | **Rule churn**: 7 relevant rule changes in the past 8 months. | Effective-dated session and cost tables. A weekly conformance test against the broker sandbox. A watcher on exchange and broker circulars. |

---

## 5. Open questions for the owner (deduplicated, design-changing only)

| # | Question | Recommended default |
|---|---|---|
| 1 | Is the existing agent on the same Upstox account and app? The workspace suggests yes. | Assume yes. The new system executes on **Zerodha** (the Personal API is free) and uses Upstox for data only, through the Analytics Token. |
| 2 | Do you have a funded Zerodha account, and will the capital be separate? | ₹10L in its own account. No margin shared with the options agent. |
| 3 | What instruments are allowed in phase 1? | Live: cash MIS on F&O stocks only. Nifty option-buying scalps as a paper track, and only on a separate account. |
| 4 | What are the risk limits? | 2% hard daily loss limit (not 3%). R of 0.25% for the first live month, then 0.5%. Scalp R of 0.25%. Shut down at a 15% drawdown. |
| 5 | Are short trades allowed? | Yes, intraday in F&O stocks only. |
| 6 | Swing and overnight trades? | Deferred past the MVP. Later: CNC (delivery) only, approved by you, within a 1% gap-risk budget. |
| 7 | Can you do the daily broker login, and can you be reached during market hours? | No login by 09:05 means a paper-only day. No semi-auto approvals for intraday trades. |
| 8 | What is the monthly operating budget? | ≤₹10k during paper trading, of which LLM ≤₹5k. Revisit at go-live. |
| 9 | Will you trade manually in this account? | No. Any untagged order halts new entries. |
| 10 | Do you accept the timeline? | At least 8–12 weeks of paper before real money on intraday setups, and 4–6 months for scalping. |
| 11 | Where will it run? | Paper runs anywhere, including home (no static IP needed, and NSE access works better from a home connection). Live runs on a Mumbai VM with a static IP, plus a registered backup IP. |
| 12 | Do you have Jev access, or a paid news feed? | Neither is required. Use Haiku for triage, with Jev as a shadow challenger when available. Defer results setups that depend on consensus estimates. |

---

## 6. Phase order and the minimum viable version

**What the specialists got right:** record first, paper before ML, and the LLM kept out of the order path.

**What I disagree with:**
- Scalping as the anchor of the plan.
- The full infrastructure stack built up front.
- The live adapter left until weeks 8–12. Calibration depends on live probes, so the account decision and probes are needed by week 5–6.
- A semi-auto stage for scalps.

**MVP: paper trading live, unattended, by the end of week 4–5**

- **Data:**
  - Upstox V3 feed on the Analytics Token: 30-level depth for 40 or fewer focus names, 5-level for 200 or fewer, and last price for the Nifty 500.
  - Raw recorder plus nightly Parquet files.
  - Daily instrument master with flags (F&O ban, ASM/GSM, trade-to-trade, price bands, lot and tick sizes).
  - Session calendar covering the closing auction, pre-open and holidays.
  - Effective-dated cost tables for Upstox at ₹30 and Zerodha at ₹20.
- **Selection:** a deterministic in-play score at 09:12 and 09:30, built from gap/ATR, the pre-open price, relative volume and filing count. It picks 5–8 names.
- **Strategy:**
  - Two setups only, each held 5–60 minutes: an ORB retest or first pullback on in-play names, and a VWAP reclaim.
  - A deterministic day-type label, logged. It blocks trading only on "high-volatility event" days.
- **Execution and risk:**
  - Paper broker on the conservative tier only: walks the order book, fills limits only on trade-through, and models latency, market price protection and the closing-auction cutoffs.
  - Order state machine with a synthetic bracket (stop plus target managed by our code).
  - Hard risk rules: 2% daily loss limit, the open-risk invariant, and the flatten times above.
- **LLM:**
  - One pre-market brief plus Haiku filings triage.
  - **Shadow only**: plans are logged and scored against the no-LLM book.
- **Ops:**
  - Two processes: trader and recorder.
  - Postgres or SQLite plus Parquet.
  - Telegram alerts and a kill switch, plus a daily HTML report.

**Then:**
- **Weeks 5–8:** live execution adapter on the account you decide on; 1-share probes; reconciliation; the dead-man process. An A/B test of LLM gating against the baseline. Rules-only scalping in paper on the 30-level-depth names.
- **Weeks 10–14:** setups that pass SPRT go live at 25% of R.
- **Months 4–6:** an ML filter for scalps (after 60+ recorded sessions), the option-scalp paper track, and CNC swing trades.
- **Later:** MCX, once Upstox's MCX API status is verified, or on Zerodha.

---

**Sources:**
- [Upstox square-off timings change](https://upstox.com/announcements/revised-timings/important-update-intraday-square-off-timings-are-changing/)
- [Zerodha product update, 10 Aug 2026](https://zerodha.com/z-connect/updates/track-closing-auction-session-on-kite-web)
- [Upstox Plus T&C](https://upstox.com/files/terms-and-condition/plus-pack.pdf)
- [Upstox Plus brokerage](https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/)
- [Upstox rate limits](https://upstox.com/developer/api-documentation/rate-limiting)
- [Upstox rate-limit thread](https://community.upstox.com/t/rate-limits-on-api-usage/3384)
- [NSE FA73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf)
- [Zerodha transaction charges](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/exchange-transaction-charges)
- [Tradejini pre-open](https://www.tradejini.com/blogs/a-new-preopen-rulebook-what-investors-need-to-know-from-september-7)
- [Rupeezy pre-open](https://support.rupeezy.in/support/solutions/articles/21000005415-what-is-changing-in-the-pre-open-session-from-september-7-2026-)
- [DigitalOcean: what is Jev](https://www.digitalocean.com/resources/articles/what-is-jev)
- [The New Stack: Jev](https://thenewstack.io/typesafe-jev-system-one/)
- [Upstox GTT entry-leg thread](https://community.upstox.com/t/gtt-trailing-stoploss-order-via-api-enforces-me-to-include-a-rule-with-entry-strategy/10453)
- [Upstox Apr-2026 mandates](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822)
- [Upstox changes live (MCX API disabled)](https://community.upstox.com/t/important-update-regulatory-changes-for-api-and-algo-trading-are-now-live/14874)
- [App creation paused thread](https://community.upstox.com/t/api-app-creation-paused-for-retail-clients/13462)
- [Upstox Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/)
- [NSE 2026 holiday circular](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf)
- [Sahi NSE holidays 2026](https://sahi.com/blogs/nse-trading-holidays-2026-complete-list-of-stock-market-holidays)
- [Kite forum: NSE blocks AWS](https://kite.trade/forum/discussion/14939/fetch-stock-in-f-o-ban-list)
- [NSEPython cloud block](https://forum.unofficed.com/t/update-nsepython-not-working-in-aws-google-cloud-and-webservers/670)