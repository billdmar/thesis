"""Excel<->Python cell-level differential (the moat), offline on DECK.

Builds a real DECK ModelBundle from committed fixtures, writes the live-formula
workbook, RECALCULATES it with the ``formulas`` library, and asserts every cell
in ``build_verifier_cell_map`` matches the Python engine to the cent. This is
the verification gate in miniature and runs in CI (fixtures only, no live EDGAR).
"""

from __future__ import annotations

import formulas
from src.comps import CompsEngine
from src.edgar import load_normalized_facts
from src.interfaces import (
    ModelBundle,
    ProjectionAssumptions,
    TerminalAssumptions,
    WACCInputs,
)
from src.statements import ThreeStatementBuilder
from src.valuation import DCFValuationEngine
from src.workbook import ExcelWorkbookWriter, build_verifier_cell_map


def _build_bundle() -> ModelBundle:
    nf = load_normalized_facts("DECK")
    hist = ThreeStatementBuilder().build_historical(nf)
    a = ProjectionAssumptions(
        n_years=5,
        revenue_growth=[0.10, 0.08, 0.07, 0.06, 0.05],
        gross_margin=[0.577] * 5,
        sga_pct_revenue=[0.345] * 5,
        rnd_pct_revenue=[0.0] * 5,
        dso=[40] * 5,
        dio=[110] * 5,
        dpo=[45] * 5,
        capex_pct_revenue=[0.016] * 5,
        da_pct_revenue=[0.018] * 5,
        tax_rate=[0.235] * 5,
        interest_rate_on_debt=0.0,
        interest_rate_on_cash=0.04,
        min_cash=400e6,
        dividend_payout=[0.0] * 5,
    )
    proj = ThreeStatementBuilder().project(hist, a)
    w = WACCInputs(
        risk_free_rate=0.043,
        beta=1.05,
        equity_risk_premium=0.05,
        pretax_cost_of_debt=0.06,
        tax_rate=0.235,
        market_cap=18e9,
        total_debt=0.0,
    )
    t = TerminalAssumptions(terminal_growth=0.03, exit_ev_ebitda=16.0, mid_year_convention=True)
    dcf = DCFValuationEngine().dcf(proj, w, t)
    comps = CompsEngine().build_peer_multiples(nf, [], market_data=None)
    return ModelBundle(
        company=nf.company,
        statements=proj,
        proj_assumptions=a,
        wacc_inputs=w,
        terminal=t,
        dcf=dcf,
        comps=comps,
        precedents=[],
        lbo=None,
        current_price=100.0,
        price_target=None,
        rating=None,
    )


def test_workbook_recalc_matches_engine_to_the_cent(tmp_path):
    bundle = _build_bundle()
    path = tmp_path / "DECK_model.xlsx"
    ExcelWorkbookWriter().write(str(path), bundle)

    xl = formulas.ExcelModel().loads(str(path)).finish()
    sol = xl.calculate()
    fname = path.name  # formulas keys use the on-disk file name, original case

    def recalc(sheet: str, coord: str):
        node = sol.get(f"'[{fname}]{sheet.upper()}'!{coord}")
        return None if node is None else float(node.value[0, 0])

    cell_map = build_verifier_cell_map(bundle)
    mismatches = []
    for (sheet, coord), engine_value in cell_map.items():
        wb_value = recalc(sheet, coord)
        # Currency to the cent; the two per-share prices to a tenth of a cent.
        tol = 0.01
        if wb_value is None or abs(wb_value - engine_value) > tol:
            mismatches.append((sheet, coord, engine_value, wb_value))

    assert not mismatches, "differential mismatches:\n" + "\n".join(
        f"  {s}!{c}: engine={ev:.4f} workbook={wv}" for s, c, ev, wv in mismatches
    )
    # The docs/report advertise "38 formula cells" differentially verified; guard
    # that headline against silent shrinkage (a loose >=12 bound would let the map
    # halve while the claim stayed 38). Additions are fine; a drop below 38 fails.
    assert len(cell_map) >= 38, f"differential cell map shrank to {len(cell_map)} (< advertised 38)"
