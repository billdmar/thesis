# ASSUMPTIONS.md — the defensible assumptions ledger

Every projection driver, WACC input, and terminal assumption gets a 2–4 line
rationale here, sourced to the 10-K / market data where possible. This file is
the owner's "defend your pitch" prep sheet. Projections are **assumptions,
labeled as such** — never facts.

---

## Company selection (the one human decision — W0)

**Chosen: Deckers Outdoor Corporation (DECK), CIK 0000910521.**

Selected from three candidates (DECK, TXRH, CELH), all US non-financial filers
with 5+ years of clean XBRL, understandable drivers, and a live analytical
debate. Rationale for DECK:

- **Thesis tension a report can actually argue.** Two brands pulling in
  different directions — HOKA as the growth engine (running/performance
  footwear taking share) versus UGG as the mature, cash-generative franchise
  with seasonality and fashion-cycle risk. That tension is the whole pitch and
  gives the risk section real teeth.
- **Clean, teachable financials.** Net-cash balance sheet (no meaningful debt)
  makes the EV→equity bridge a clear teaching moment (EV < equity value), and
  the debt schedule / revolver plug still gets exercised by the LBO tab where
  leverage is *introduced*, not assumed away.
- **Pristine, consistent XBRL.** Apparel/footwear filer with a straightforward
  us-gaap tagging history — favorable for the XBRL tie-out gate — and a fiscal
  year ending in March (a nice non-calendar-FY wrinkle to handle correctly).
- **Accepted trade-off:** well-covered by sell-side. We lean into it — the
  differentiator here is the *verified* dual-implementation model, not coverage
  scarcity.

Fiscal year end: **March 31**. Figures below reflect the shipped flagship build
(as-of 2026-08-06), sourced from SEC EDGAR XBRL plus the judgment inputs noted.

---

## Historical anchor (from the committed DECK XBRL fixture, FY end March)
Grounds every assumption below. Source: SEC EDGAR CompanyFacts, CIK 0000910521.

| FY (Mar) | Revenue | Rev growth | Gross margin | Op margin | Capex/rev | Cash | Debt |
|---|---|---|---|---|---|---|---|
| 2022 | $3.15B | +23.8% | 51.0% | 17.9% | 1.6% | $844M | $0 |
| 2023 | $3.63B | +15.1% | 50.3% | 18.0% | 2.2% | $982M | $0 |
| 2024 | $4.29B | +18.2% | 55.6% | 21.6% | 2.1% | $1,502M | $0 |
| 2025 | $4.99B | +16.3% | 57.9% | 23.6% | 1.7% | $1,889M | $0 |
| 2026 | $5.47B | +9.8% | 57.7% | 23.1% | 1.5% | $1,907M | $0 |

Read: a **net-cash, asset-light compounder** whose growth is **decelerating**
(24%→10%) off a larger base, with **structurally higher margins** (gross +700bp
and op +500bp over four years, on HOKA mix + DTC + pricing). The whole debate is
**growth durability vs. margin sustainability at peak**.

## Thesis stance (owner decision, the flagship build): BALANCED / DEFENSIBLE
Base case models continued but **moderating** growth and margins **near peak,
compressing modestly** — a stance defensible against both bulls
(HOKA runway) and bears (law of large numbers, footwear cyclicality). Bull/bear
scenarios bracket it.

## Projection drivers — base case (5-yr, FY2027–FY2031)
| Driver | Y1 | Y2 | Y3 | Y4 | Y5 | Rationale (2–4 lines) |
|---|---|---|---|---|---|---|
| Revenue growth | 9% | 8% | 7% | 6% | 5% | Continues the observed deceleration (FY26 already +9.8%). HOKA keeps taking share but off a bigger base; UGG ~flat. A smooth glide to a GDP-plus terminal rate avoids a cliff the data doesn't support. |
| Gross margin | 57.5% | 57.5% | 57.0% | 57.0% | 56.5% | Holds near the FY25–26 peak (~58%) then eases ~100bp as promotional intensity normalizes and freight/mix tailwinds fade. Not modeling further expansion — margins are already at record highs. |
| SG&A % rev | 34.5% | 34.5% | 34.5% | 34.5% | 34.5% | Roughly the recent run-rate (implies op margin low-20s%, consistent with FY24–26). DECK reinvests into DTC/marketing, so no operating-leverage windfall assumed. |
| R&D % rev | 0% | — | — | — | — | DECK does not separately tag material R&D (design costs sit in SG&A). Honest-zero, not fabricated. |
| Capex % rev | 1.6% | 1.6% | 1.6% | 1.6% | 1.6% | Asset-light (outsourced manufacturing); 5-yr history 1.3–2.2%, recent ~1.5–1.7%. Retail build-out keeps it modest. |
| D&A % rev | 1.8% | 1.8% | 1.8% | 1.8% | 1.8% | Tracks recent D&A/revenue; slightly above capex% given lease/ROU amortization. |
| Tax rate | 23.5% | 23.5% | 23.5% | 23.5% | 23.5% | Near the FY24–26 effective rate; US statutory 21% + state/foreign mix. |
| Dividend payout | 0% | — | — | — | — | DECK pays **no dividend** (confirmed: no PaymentsOfDividends XBRL tag); returns cash via buybacks. Honest-zero. |
| Working capital | DSO ~40, DIO ~110, DPO ~45 | | | | | Inventory-heavy footwear model; days set to recent norms. WC builds with growth (a real FCF drag the DCF captures — the FY1 ΔWC is material). |

## WACC inputs — base case
| Input | Value | Source / rationale |
|---|---|---|
| Risk-free rate | **4.3%** | 10-yr Treasury as of 2026-08-06. |
| Beta | ~1.05 | Consumer-discretionary footwear; levered beta near market (2-yr weekly vs. S&P 500). Net-cash, so asset≈equity beta. |
| Equity risk premium | 5.0% | Standard US ERP assumption (Damodaran range 4.5–5.5%). |
| Pre-tax cost of debt | 6.0% | Illustrative (DECK has no debt); used only for the LBO/theoretical Kd. |
| Capital structure | ~100% equity | **Net-cash, zero debt** → WACC = cost of equity. This is a genuine teaching point: no debt tax shield, EV < equity value. |

## Terminal assumptions
- **Gordon g = 3.0%** — below WACC (guard enforces g<WACC); ~long-run nominal GDP; a deliberate step-down from the 5% Y5 growth.
- **Exit EV/EBITDA = 11.0x** — DECK trades at ~8.7x today (a trough, near its
  52-wk low after the growth-deceleration selloff). 11x assumes a **modest
  re-rating** as durable high-single-digit growth + record margins reassert —
  deliberately well below the ~15–16x that premium footwear compounders command
  at peak, to keep the base case defensible rather than heroic. Cross-checked
  vs. the comps band (the flagship build sanity gate).
- **Mid-year convention: ON** — standard for a going concern.

## Valuation output & 12-month target (as-of 2026-08-06, price $99.68)
- **WACC = 9.55%** (net-cash ⇒ = cost of equity; no debt shield).
- **DCF fair value ≈ $118–136/sh** (Gordon $118 on a **normalized** steady-state
  terminal FCFF, exit-11x $136; midpoint ~$127). The Gordon terminal FCFF is
  normalized via the **reinvestment-rate identity**: terminal FCFF = NOPAT ×
  (1 − g/RONIC), with RONIC = WACC + 3%. A perpetuity growing at g must reinvest
  g/RONIC of NOPAT, so terminal FCFF is a disciplined fraction of NOPAT (~76%),
  not the raw final-year FCFF (which a banker would correctly reject as a
  non-steady-state base). The exit-multiple terminal value is discounted at the
  **full-year** factor (a year-end sale), not the mid-year factor used for the
  going-concern stream.
  Per **current** diluted share count **136.2M** — an as-of assumption (paired
  with the $99.68 price, ≈ a $13.56B market cap), below the FY26 reported 145.8M
  weighted-avg because of ongoing buybacks — a documented "value per current
  share" choice, stamped as-of (not reverse-solved from the cap).
- **12-month price target: $128** — sits at the DCF midpoint (~$127) and right on
  the comps EV/EBITDA read (~$129). Implies **~+28% upside**; **Rating: Buy**.
  Between the street average (~$122) and high (~$161) — the call is "the selloff
  is overdone," not a contrarian moonshot.
- Net cash of ~$1.9B makes **EV < equity value** (the EV-bridge teaching point).

## Scenario deltas (bull / base / bear)
Each scenario reruns the same statement + DCF engine on its own driver set.
- **Bull** (~$158 mid): +3pts revenue growth each year, +1pt gross margin, g=3.5%,
  13× exit — HOKA sustains, margins hold at the record.
- **Base** (~$127 mid): the assumptions above.
- **Bear** (~$83 mid, ~17% below spot): a GENUINE thesis-break, not a symmetric
  nudge — revenue growth −5pts (to a ~2% CAGR: HOKA momentum stalls), gross margin
  −3pts (reverting toward the FY22 low-50s as promotion normalizes), terminal g
  cut to 2%, and the multiple stuck at a trough 8×. Deliberately calibrated to
  land meaningfully below today's price so the risk/reward is honestly asymmetric
  (~+27% to target vs ~−17%), not a bear conveniently pinned to spot. **Deltas are
  analyst judgment — tune in `flagship.py` (`build_scenarios(..., bear=...)`).**

## Sum-of-the-parts cross-check (HOKA / UGG) — illustrative
A report cross-check on the consolidated call, **not** the target basis. Sourced
brand net sales (10-K) × illustrative per-brand EV/revenue multiples — HOKA **3.75×**
(growth premium), UGG **2.1×** (mature franchise), Other **1.0×** — anchored so the
blend (~$116/sh) reconciles to the consolidated DCF (~$118 Gordon). Brand EBITDA is
not disclosed (honest unknown), so this is deliberately an EV/revenue build, never a
fabricated brand-EBITDA one. **Multiples are analyst judgment — tune in `flagship.py`
(`SOTP_EV_REVENUE`).** Growth-contribution context: FY22→FY25, HOKA compounded ~36%
and drove the majority of incremental revenue; UGG ~12% — the "two ways to compound."

## LBO assumptions (illustrative — net-cash target)
Framed explicitly as "what leverage *could* do to a clean-balance-sheet name."
- Entry premium ~25% over market; leverage introduced (DECK has none today);
  debt ~50% of EV; debt rate ~7%; cash-sweep ~75% of **levered** FCF (i.e. after
  cash interest); un-swept cash accumulates and nets against debt at exit; exit
  at entry multiple; 5-yr hold.
- **Result: IRR ~13.6%, MOIC ~1.9x.** Modest by LBO standards — which is the
  honest read for a net-cash, high-multiple asset: cash interest on the ~$8B of
  introduced debt consumes much of the operating FCF, so returns come mostly from
  EBITDA growth, not deleveraging. That is exactly why DECK is not a natural LBO
  candidate, and the tab is labeled illustrative throughout.

## Comp set & precedent selection
- **Peers:** NKE, CROX, WWW, SHOO, COLM, VFC, BOOT, CAL — footwear/apparel
  brand-and-retail names with comparable driver stories. (Skechers excluded:
  taken private 2025, no current XBRL.) Purest reads are CROX and NKE (brand +
  DTC footwear); VFC/COLM/WWW are diversified apparel comps; BOOT/CAL add a
  footwear-retail angle.
- **Precedents:** 6 sourced footwear/apparel M&A deals (3G/Skechers, ABG/Reebok,
  VFC/Supreme, WWW/Collective PLG, VFC/Timberland, Steve Madden/Kurt Geiger).
  Headline EVs sourced to press releases; deal-level multiples left blank where
  not reliably public (honest-unknown, per the no-fabrication rule).

> All projections are **assumptions, labeled as such** — not forecasts of fact.
> Market-data inputs are stamped **as-of 2026-08-06**.
