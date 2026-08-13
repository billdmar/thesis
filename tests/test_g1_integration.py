"""G1 integration gate — end-to-end on the fixture company (DECK), offline.

This is the sequential integration gate: it wires the four
engines together on committed fixtures and asserts the two hard G1 gates:

* **XBRL tie-out** — every historical statement line reconciles to the
  SEC-reported fact to the dollar (tol=0.0).
* **Accounting invariants** — on a projected model, the balance sheet balances,
  the CFS ties to BS cash, and the RE and PP&E rolls hold.

It runs fully offline on the DECK fixture (no live EDGAR).
"""

from __future__ import annotations

import pytest
from src.edgar import load_normalized_facts
from src.interfaces import ProjectionAssumptions, TerminalAssumptions, WACCInputs
from src.schema import LineItem
from src.statements import ThreeStatementBuilder
from src.valuation import DCFValuationEngine
from src.verify.invariants import run_all
from src.verify.tieout import balance_sheet_ties, tie_out_historical


@pytest.fixture(scope="module")
def deck_facts():
    return load_normalized_facts("DECK")


@pytest.fixture(scope="module")
def deck_hist(deck_facts):
    return ThreeStatementBuilder().build_historical(deck_facts)


def _placeholder_assumptions() -> ProjectionAssumptions:
    # Rough, non-final drivers — enough to exercise the projection linkages.
    # The real, sourced judgment-core assumptions are set when building the flagship model.
    return ProjectionAssumptions(
        n_years=5,
        revenue_growth=[0.10, 0.09, 0.08, 0.07, 0.06],
        gross_margin=[0.575] * 5,
        sga_pct_revenue=[0.35] * 5,
        rnd_pct_revenue=[0.0] * 5,
        dso=[40] * 5,
        dio=[110] * 5,
        dpo=[45] * 5,
        capex_pct_revenue=[0.02] * 5,
        da_pct_revenue=[0.02] * 5,
        tax_rate=[0.24] * 5,
        interest_rate_on_debt=0.06,
        interest_rate_on_cash=0.03,
        min_cash=400e6,
        dividend_payout=[0.0] * 5,
    )


def test_xbrl_tieout_to_the_dollar(deck_hist, deck_facts):
    report = tie_out_historical(deck_hist, deck_facts, tol=0.0)
    assert report.checked > 200, "expected many historical lines to reconcile"
    assert report.passed, "\n".join(
        f"{m.line_item.value} FY{m.fy}: stmt={m.statement_value} fact={m.fact_value} ({m.note})"
        for m in report.mismatches[:25]
    )


def test_known_revenue_ties_out(deck_hist):
    # Spot-check the headline number against the SEC-reported FY2026 revenue.
    rev = deck_hist.series(LineItem.REVENUE)
    fy_labels = [p.fy for p in deck_hist.periods[: deck_hist.n_hist]]
    idx = fy_labels.index(2026)
    assert rev[idx] == 5_472_296_000


def test_balance_sheet_identity_from_raw_facts(deck_facts):
    residuals = balance_sheet_ties(deck_facts)
    assert residuals, "expected instant periods with BS data"
    assert all(abs(r) <= 1.0 for _, r in residuals)


def test_projection_invariants_hold(deck_hist):
    proj = ThreeStatementBuilder().project(deck_hist, _placeholder_assumptions())
    report = run_all(proj, tol=1.0)
    assert report.passed, report.summary()


def test_full_pipeline_runs_and_wacc_reasonable(deck_hist):
    # End-to-end: statements -> DCF. Net-cash subject, so WACC == cost of equity.
    proj = ThreeStatementBuilder().project(deck_hist, _placeholder_assumptions())
    engine = DCFValuationEngine()
    wacc_inputs = WACCInputs(
        risk_free_rate=0.043,
        beta=1.1,
        equity_risk_premium=0.05,
        pretax_cost_of_debt=0.06,
        tax_rate=0.24,
        market_cap=18e9,
        total_debt=0.0,
    )
    wacc = engine.wacc(wacc_inputs)
    assert abs(wacc - (0.043 + 1.1 * 0.05)) < 1e-9  # net-cash -> Ke
    terminal = TerminalAssumptions(
        method="both", terminal_growth=0.03, exit_ev_ebitda=15.0, mid_year_convention=True
    )
    result = engine.dcf(proj, wacc_inputs, terminal)
    assert result.implied_price_gordon > 0
    assert result.implied_price_exit > 0
    # g < WACC guard already enforced by the engine; sanity here.
    assert terminal.terminal_growth < wacc
