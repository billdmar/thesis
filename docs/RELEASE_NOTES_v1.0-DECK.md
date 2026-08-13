# DECK — Initiating Coverage v1.0

Initiating coverage of **Deckers Outdoor (DECK)** — the flagship build of an
SEC-EDGAR-driven equity-research platform. This release ships the two
deliverables a reviewer actually reads: the initiating-coverage **report (PDF)**
and the live-formula **valuation model (Excel)**.

## The call
- **Rating: Buy · 12-month price target $128 · +28%** vs. the $99.68 price
  (as of 2026-08-06).
- **DCF fair value ~$118 (Gordon) / ~$136 (exit 11×), midpoint ~$127** — the
  target sits at the midpoint.
- **Trading comps ~$129** on peer-median EV/EBITDA — a sanity check on the DCF
  (peer market data is illustrative, so comps cross-check rather than confirm).
- **Scenarios ~$83 / ~$127 / ~$158** (bear / base / bull); the bear is a genuine
  thesis-break case ~17% below spot, so risk/reward is asymmetric (~+27% vs −17%).
- **WACC 9.55%** (net-cash ⇒ WACC = cost of equity) · **illustrative LBO
  IRR ~13.6% / MOIC ~1.9×**.

The thesis: the market has oversold a net-cash (~$1.9B, zero debt),
~23%-operating-margin compounder on *decelerating* — not declining — growth.

## What's in this release
- **`DECK_initiating_coverage.pdf`** — the 14-page initiating-coverage report:
  rating and target, investment thesis, company and industry analysis, financial
  analysis, full DCF / comps / precedent-transaction / scenario valuation, an
  illustrative LBO, risks, and a statement appendix.
- **`DECK_model.xlsx`** — the live-formula workbook: every computed cell is a
  formula referencing other cells, not a baked value.

## Why the numbers are trustworthy
- **832/832 XBRL tie-out** — every historical statement line reconciles to
  SEC-reported facts to the dollar.
- **38-cell Excel↔Python differential** — the workbook's live formulas
  (income-statement projection chain, WACC build, DCF valuation & EV→equity
  bridge) are recalculated and matched to an independent Python reference engine
  to the cent.
- **Report-number lint** — every figure in every financial exhibit traces back
  to an engine output; a fabricated number fails the build.
- **Accounting invariants + valuation sanity + deterministic rebuild**, all
  gated by 188 tests at ~98% coverage.

Built from public SEC EDGAR XBRL data used under the SEC's fair-access policy,
without implying SEC endorsement. Educational project, not investment advice;
all projections are the author's own assumptions, labeled as such.
