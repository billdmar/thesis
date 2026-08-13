# WORKBOOK_SPEC.md — Excel deliverable layout contract

**Shared data contract — edit deliberately; everything builds against it.** the workbook writer writes exactly this;
the verifier diffs against exactly this. The workbook is `out/<TICKER>_model.xlsx`.

## Banker conventions (non-negotiable — enforced by the Excel audit gate)
- **Blue font** = hard-coded input. Blue cells appear **only on the Assumptions
  tab** (and the two market-data inputs on the Cover). Nowhere else.
- **Black font** = formula. Every computed cell is a *live Excel formula*
  referencing other cells / named ranges — never a baked value. The verifier
  recalculates the file; a baked number is a defect.
- **No hardcodes inside formula cells.** A formula never contains a literal
  magic number except true constants (e.g. `365` for day-count, `12` for
  months) and even those prefer a named cell where one exists.
- **Signs:** costs/outflows negative where the statement shows them so; totals
  are `SUM`/arithmetic of their parts, never re-keyed.
- **Units:** values carried in raw USD; display scaling to `$000s` via number
  format, not by dividing in formulas. Number format: `#,##0;(#,##0)` for
  currency, `0.0%` for rates, `0.00` for per-share, `0.0x` for multiples.
- **Named ranges** for every key output (see §Named ranges).

## Tab order & contents
1. **Cover** — company, ticker, date; **Rating**, **12-mo Price Target**,
   **Current Price** (blue input), **Implied Upside** (formula); valuation
   triangulation mini-table (DCF Gordon / DCF exit / Comps / LBO implied) each
   pulling from its tab; disclaimer footer.
2. **Assumptions** — the ONLY input tab. Sections: projection drivers (revenue
   growth, margins, WC days, capex/D&A %, tax, payout), WACC inputs (rf, beta,
   ERP, pre-tax Kd, tax), terminal (g, exit EV/EBITDA, mid-year toggle), LBO
   inputs. Every input blue. Each has a comment/note cell citing ASSUMPTIONS.md.
3. **Historical IS/BS/CF** — historical periods tied to XBRL, one column per
   fiscal year. These are the tie-out surface (values here reconcile to SEC
   facts to the dollar). Presented as values with provenance notes; totals are
   formulas summing their components.
4. **Income Statement (Model)** — historical + 5-yr projection, fully linked:
   revenue = prior × (1+growth from Assumptions); GM, SG&A, R&D from
   Assumptions; EBIT; interest from Debt schedule; taxes; net income.
5. **Balance Sheet (Model)** — projected via WC days, capex→PP&E roll, RE roll
   (`RE_t = RE_{t-1} + NI_t − Div_t`), cash & **revolver plug** to hold min
   cash; assets = liabilities + equity every column (invariant gate).
6. **Cash Flow (Model)** — CFO (NI + D&A + SBC − ΔWC), CFI (capex), CFF
   (dividends, buybacks, debt Δ); ending cash **must equal** BS cash (invariant).
7. **WACC** — CAPM cost of equity, after-tax cost of debt, market weights → WACC.
8. **DCF** — FCFF = EBIT×(1−tax) + D&A − capex − ΔWC; mid-year discounting
   toggle; **both** terminal methods (Gordon `FCFF×(1+g)/(WACC−g)` and exit
   `EBITDA_T × exit multiple`); PV; EV; EV→equity bridge (−net debt −minority);
   implied price. Named outputs.
9. **Trading Comps** — peer rows: EV build (mkt cap + debt − cash),
   EV/Revenue, EV/EBITDA, P/E (LTM; NTM where available); median/mean/min/max;
   implied subject value from applying peer median to subject metric.
10. **Precedent Transactions** — sourced deal rows (date, acquirer, target, EV,
    EV/Rev, EV/EBITDA, source); summary stats; implied value.
11. **LBO** — sources & uses (sources=uses check cell), 5-yr debt schedule with
    cash sweep, exit equity, **IRR** (`IRR`/`XIRR`) and **MOIC**.
12. **Sensitivities** — WACC×g grid on implied price; price×gross-margin grid;
    both as live data-table-style formula grids (monotonic — sanity gate).
13. **Football Field** — horizontal ranges: DCF (Gordon–exit), comps
    (min–max), precedents, LBO; current price and target as marker lines.

## Named ranges (the verifier & report key off these)
`CurrentPrice`, `PriceTarget`, `Rating`, `WACC`, `TerminalGrowth`,
`ExitMultiple`, `EV_Gordon`, `EV_Exit`, `EquityValue_Gordon`,
`EquityValue_Exit`, `ImpliedPrice_Gordon`, `ImpliedPrice_Exit`,
`NetDebt`, `SharesDiluted`, `Comps_ImpliedPrice_EBITDA`, `LBO_IRR`, `LBO_MOIC`,
`RevenueCAGR`. Each maps to exactly one cell.

## Verifier contract (what "differential green" means)
the verifier recalculates the workbook (via the `formulas` library; LibreOffice
headless fallback) and, for **every computed cell** that corresponds to a
`ModelBundle` value, asserts `abs(workbook − engine) <= 0.01` (one cent) for
currency, tighter relative tol for rates/multiples. The map from cells to
engine values is declared alongside the writer so both sides stay in sync. A
mismatch, a baked value where a formula is required, or a blue cell off the
Assumptions tab fails the gate.
