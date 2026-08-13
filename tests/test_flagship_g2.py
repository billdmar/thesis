"""G2 gate — the flagship DECK model, end-to-end and offline.

Builds the real flagship ``ModelBundle`` (src/flagship.py), writes the
live-formula workbook, and runs the full verification gate:

* **Differential** — recalc the workbook with the ``formulas`` library; every
  mapped cell matches the Python engine to the cent.
* **Excel audit** — banker conventions: formulas (not baked values) in the
  computed region, blue inputs only on Assumptions + Cover, named ranges present.
* **XBRL tie-out** — historicals reconcile to SEC facts to the dollar.
* **Accounting invariants** — BS balances, CFS ties, RE & PP&E rolls.
* **Valuation sanity** — g < WACC, LBO IRR recompute, sensitivity monotonicity.

Runs on committed fixtures only (no live EDGAR). This also covers the flagship
builder and locks the headline valuation against regression.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from src.edgar import load_normalized_facts
from src.flagship import (
    CURRENT_PRICE,
    CURRENT_SHARES,
    PRICE_TARGET,
    base_assumptions,
    build_flagship,
    wacc_inputs,
)
from src.interfaces import TerminalAssumptions
from src.statements import ThreeStatementBuilder
from src.valuation import DCFValuationEngine
from src.verify import WorkbookVerifier, audit_workbook
from src.verify.invariants import run_all
from src.verify.tieout import tie_out_historical
from src.workbook import ExcelWorkbookWriter


@pytest.fixture(scope="module")
def flagship():
    return build_flagship()


@pytest.fixture(scope="module")
def workbook_path(flagship, tmp_path_factory):
    path = tmp_path_factory.mktemp("out") / "DECK_model.xlsx"
    ExcelWorkbookWriter().write(str(path), flagship)
    return str(path)


def test_g2_differential_to_the_cent(flagship, workbook_path):
    report = WorkbookVerifier().recalc_and_diff(workbook_path, flagship, tol=0.01)
    # The differential covers the full Model-IS chain + WACC + DCF, not just the
    # 12 valuation-summary cells — guard the widened scope against regression.
    assert report.cells_checked >= 30
    assert report.passed, "\n".join(
        f"{m.sheet}!{m.cell}: engine={m.engine_value} wb={m.workbook_value}"
        for m in report.mismatches
    )


def test_g2_excel_audit(flagship, workbook_path):
    report = audit_workbook(workbook_path, model=flagship)
    assert report.passed, report.violations


def test_g2_xbrl_tieout(flagship):
    nf = load_normalized_facts("DECK")
    report = tie_out_historical(flagship.statements, nf, tol=0.0)
    assert report.passed
    assert report.checked > 200


def test_g2_invariants(flagship):
    report = run_all(flagship.statements, tol=1.0)
    assert report.passed, report.summary()


def test_g2_valuation_sanity_g_lt_wacc(flagship):
    assert flagship.terminal.terminal_growth < flagship.dcf.wacc


def test_g2_lbo_irr_recompute(flagship):
    lbo = flagship.lbo
    n = len(lbo.debt_schedule)
    # Single-in/single-out: IRR must equal MOIC^(1/n) - 1.
    assert abs(lbo.irr - (lbo.moic ** (1 / n) - 1)) < 1e-3
    assert lbo.sources_equal_uses()


def test_g2_sensitivity_monotonicity():
    # Implied price falls as WACC rises (via beta) and rises as g rises.
    nf = load_normalized_facts("DECK")
    proj = ThreeStatementBuilder().project(
        ThreeStatementBuilder().build_historical(nf), base_assumptions()
    )
    engine = DCFValuationEngine()

    def price(beta: float, g: float) -> float:
        w = replace(wacc_inputs(), beta=beta)
        t = TerminalAssumptions(terminal_growth=g, exit_ev_ebitda=11.0, mid_year_convention=True)
        return engine.dcf(proj, w, t).equity_value_gordon / CURRENT_SHARES

    by_wacc = [price(b, 0.03) for b in (0.9, 1.0, 1.1, 1.2)]
    assert all(by_wacc[i] > by_wacc[i + 1] for i in range(len(by_wacc) - 1))
    by_g = [price(1.05, g) for g in (0.02, 0.025, 0.03, 0.035)]
    assert all(by_g[i] < by_g[i + 1] for i in range(len(by_g) - 1))


def test_g2_headline_valuation_locked(flagship):
    # Lock the headline so a silent engine/assumption drift is caught.
    d = flagship.dcf
    assert flagship.rating == "Buy"
    assert flagship.price_target == PRICE_TARGET
    assert flagship.current_price == CURRENT_PRICE
    # DCF fair value in the defensible band. Gordon uses the reinvestment-rate
    # normalized terminal FCFF (~$118); exit-11x (~$136); midpoint ~$127 ≈ the
    # $128 target and the ~$129 comps read.
    assert 110.0 < d.implied_price_gordon < 124.0
    assert 128.0 < d.implied_price_exit < 143.0
    # Net-cash: WACC == cost of equity, net debt negative.
    assert d.net_debt < 0
    assert abs(d.wacc - (0.043 + 1.05 * 0.05)) < 1e-9
