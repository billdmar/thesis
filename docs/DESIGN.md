# DESIGN.md — architecture

> Skeleton at W0; tightened at G4. The authoritative contracts are
> `src/schema.py`, `src/interfaces.py`, `docs/WORKBOOK_SPEC.md`,
> `docs/REPORT_SPEC.md`.

## One-line
An SEC-EDGAR-fed Python engine computes an equity valuation; the workbook
expresses it as **live formulas**; the report renders it; a differential
verifier proves the three agree.

## Pipeline
```
EDGAR (XBRL CompanyFacts)                         data/fixtures/ (cached, committed)
        │  src/edgar: client + rate-limit + cache + tag NORMALIZATION
        ▼
NormalizedFacts (src/schema.py)  ── canonical LineItems, periods, provenance
        │  src/statements: historical assembly + 5-yr 3-statement projection
        ▼
StatementSet ──► src/valuation (WACC, FCFF DCF)   src/comps (peers, precedents)
        │                                          src/lbo (S&U, sweep, IRR/MOIC)
        ▼
ModelBundle (src/interfaces.py)  ── single source of truth
        ├──► src/workbook  → out/<TICKER>_model.xlsx        (live formulas)
        ├──► src/report    → out/<TICKER>_initiating_coverage.pdf
        └──► src/verify    → recalc workbook & diff vs engine to the cent
```

## The verifier suite (the moat)
1. XBRL tie-out — historicals reconcile to SEC facts to the dollar.
2. Excel↔Python cell differential — recalc the workbook, match every computed
   cell to the engine to the cent.
3. Accounting invariants — BS balances; CFS ends at BS cash; RE rolls; interest
   ties to debt; LBO sources=uses & sweep ties; IRR/MOIC recompute.
4. Valuation sanity — g<WACC; implied multiples vs comps band; monotone
   sensitivities; football-field consistency.
5. Excel audit — no hardcodes in formula cells; inputs only on Assumptions;
   sign conventions; named ranges present.
6. Report lint + determinism — rebuild → identical numbers; stale figure fails.

## Module layout
| Path | Responsibility |
|---|---|
| `src/edgar/` | EDGAR client, caching, XBRL tag normalization |
| `src/statements/` | 3-statement historical assembly + projection |
| `src/valuation/` | WACC + FCFF DCF |
| `src/comps/` | trading comparables + precedent transactions |
| `src/lbo/` | illustrative LBO (sources & uses, debt schedule, IRR/MOIC) |
| `src/scenarios/` | bull / base / bear scenario engine |
| `src/segments/` | brand-level segment data loader |
| `src/workbook/` | live-formula Excel writer |
| `src/report/` | matplotlib charts + PDF renderer |
| `src/verify/` | tie-out, cell differential, audit, invariants, report-lint |
| `src/schema.py`, `src/interfaces.py` | shared data contracts (edit deliberately — everything builds against them) |
