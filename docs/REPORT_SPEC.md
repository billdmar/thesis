# REPORT_SPEC.md — Initiating-coverage report layout contract

**Shared data contract — edit deliberately; everything builds against it.** the report renderer renders exactly
this structure; the report-lint gate asserts every rendered number originates
from a `ModelBundle`/engine output (nothing hand-typed). Output:
`out/<TICKER>_initiating_coverage.pdf`, house style, generated via WeasyPrint from
an HTML/CSS template + matplotlib charts. The shipped DECK report is 14 pages — a
deliberate choice of real appendix depth (full projected statements, DCF detail,
LBO) over filler to pad a page target.

## Single-source-of-truth rule
Every figure in the PDF is injected from engine outputs at render time. The
template contains **no numeric literals** for financial data — only
placeholders bound to `ModelBundle` fields. Report-lint scans the rendered
output's number set against the engine's number set; an unsourced figure fails
the build (determinism gate).

## Section order (industry standard — CFI / Financial-Edge equity-research format)
1. **Cover page** — company name, ticker, exchange; report date; **Rating**
   (Buy/Hold/Sell); **12-month price target** and **current price** with
   **% upside/downside**; a market-data block (mkt cap, EV, shares, 52-wk
   context if available from filings); analyst line = the owner; the
   educational / **not-investment-advice disclaimer** and a note that SEC data
   is used per fair-access policy **without implying SEC endorsement**.
2. **Executive summary** — the **thesis in 3–5 sentences** (the maintainer-written);
   key-financials snapshot table (revenue, EBIT margin, EPS, FCF — historical +
   forecast); **catalysts** (bulleted, the maintainer-written); one-line valuation
   summary (target, method triangulation).
3. **Company overview** — what the business does, segments/drivers, revenue
   mix; grounded in the 10-K (the maintainer-written narrative, engine figures).
4. **Industry & competitive analysis** — market context, competitive position,
   the comp set and why those peers (the maintainer-written; comps table from engine).
5. **Financial analysis** — historical performance narrative + charts:
   revenue & margin history/forecast, FCF bridge, returns/leverage trend.
   Every number from the statement model; the analyst writes the interpretation.
6. **Valuation** — DCF (explicit **WACC** derivation with CAPM inputs shown;
   **terminal growth** and exit multiple stated; both methods; EV→equity
   bridge → implied price), trading comps (implied range), precedent
   transactions, and the **football field**. **Target derivation and method
   weighting are stated explicitly** (the maintainer-written).
7. **Risks** — what would break the thesis: operational, financial,
   regulatory, competitive (the maintainer-written; each risk concrete to this company).
8. **Appendix** — model summary (condensed statements), methodology notes,
   assumptions ledger pointer, full disclaimer, data-source citation (SEC EDGAR
   XBRL CompanyFacts), and the verification summary (XBRL tie-out, N cells
   differentially verified, invariants, coverage).

## Chart suite (all matplotlib, house style, generated from engine outputs)
- Revenue & gross/EBIT-margin, history + forecast (bar + line combo).
- FCF / FCFF bridge or trend.
- Comps scatter (EV/EBITDA vs growth or margin) with the subject highlighted.
- **Football field** (horizontal valuation ranges + current price + target).
- Optional price/volume from filings-derived data **only if available** — never
  from a paid/scraped feed.

## House style
- Serif body, sans headings; restrained accent color; page header with
  ticker + "Initiating Coverage"; page numbers; consistent table styling;
  figures numbered and captioned. Print/PDF sizing per WeasyPrint `@page`.

## Disclaimer (verbatim requirement)
A clearly visible statement that the report is an **educational project**, **not
investment advice**, produced from **public SEC EDGAR data used under the SEC's
fair-access policy without implying SEC endorsement**, and that projections are
the author's assumptions, labeled as such — never presented as fact.
