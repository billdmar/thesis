"""Unit tests for the verify harness itself (tie-out + invariants).

Beyond the DECK end-to-end gate, these exercise the harness on tiny synthetic
inputs — importantly the NEGATIVE cases, proving the gates actually FAIL when a
value drifts or the balance sheet doesn't balance (a gate that can't fail is
worthless).
"""

from __future__ import annotations

from datetime import date

from src.interfaces import StatementSet
from src.schema import (
    CompanyMeta,
    Fact,
    LineItem,
    NormalizedFacts,
    Period,
    PeriodType,
    Provenance,
    Unit,
)
from src.verify.invariants import (
    check_balance_sheet,
    check_cfs_ties_to_cash,
    check_ppe_roll,
    check_retained_earnings_roll,
    run_all,
)
from src.verify.tieout import tie_out_historical


def _dur(y: int) -> Period:
    return Period(PeriodType.DURATION, end=date(y, 3, 31), start=date(y - 1, 4, 1), fy=y, fp="FY")


def _inst(y: int) -> Period:
    return Period(PeriodType.INSTANT, end=date(y, 3, 31), fy=y)


def _prov(tag: str) -> Provenance:
    return Provenance(tag, "us-gaap", Unit.USD, "acc-1", "10-K", date(2024, 5, 1))


def test_tieout_passes_when_matching():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    p = _dur(2024)
    nf.add(Fact(LineItem.REVENUE, p, 1000.0, _prov("Revenues")))
    stmts = StatementSet(periods=[p], rows={LineItem.REVENUE: [1000.0]}, n_hist=1)
    rpt = tie_out_historical(stmts, nf, tol=0.0)
    assert rpt.passed
    assert rpt.checked == 1


def test_tieout_fails_on_drift():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    p = _dur(2024)
    nf.add(Fact(LineItem.REVENUE, p, 1000.0, _prov("Revenues")))
    stmts = StatementSet(periods=[p], rows={LineItem.REVENUE: [1001.0]}, n_hist=1)
    rpt = tie_out_historical(stmts, nf, tol=0.0)
    assert not rpt.passed
    assert rpt.mismatches[0].line_item is LineItem.REVENUE


def test_tieout_balance_item_resolves_via_instant():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    d, i = _dur(2024), _inst(2024)
    nf.add(Fact(LineItem.CASH, i, 500.0, _prov("CashAndCashEquivalentsAtCarryingValue")))
    # Statement column is the DURATION period; CASH must resolve to the instant.
    stmts = StatementSet(periods=[d], rows={LineItem.CASH: [500.0]}, n_hist=1)
    rpt = tie_out_historical(stmts, nf, tol=0.0)
    assert rpt.passed


def test_tieout_derived_gross_profit_reconciles():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    p = _dur(2024)
    nf.add(Fact(LineItem.REVENUE, p, 1000.0, _prov("Revenues")))
    nf.add(Fact(LineItem.COST_OF_REVENUE, p, 400.0, _prov("CostOfGoodsAndServicesSold")))
    # GROSS_PROFIT has no raw fact but equals REVENUE - COST_OF_REVENUE.
    stmts = StatementSet(
        periods=[p],
        rows={
            LineItem.REVENUE: [1000.0],
            LineItem.COST_OF_REVENUE: [400.0],
            LineItem.GROSS_PROFIT: [600.0],
        },
        n_hist=1,
    )
    rpt = tie_out_historical(stmts, nf, tol=0.0)
    assert rpt.passed
    # A wrong derived subtotal (beyond the $1 rounding allowance) must fail.
    stmts.rows[LineItem.GROSS_PROFIT] = [650.0]
    assert not tie_out_historical(stmts, nf, tol=0.0).passed


def test_tieout_unknown_line_without_fact_fails():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    p = _dur(2024)
    stmts = StatementSet(periods=[p], rows={LineItem.GOODWILL: [123.0]}, n_hist=1)
    rpt = tie_out_historical(stmts, nf, tol=0.0)
    assert not rpt.passed  # a value with no backing fact and not derived


# --- Invariants ---
def _proj_statements(balanced: bool = True) -> StatementSet:
    """Two periods: 1 historical seed + 1 projected, hand-built to satisfy
    (or violate) the identities."""
    h, pj = _dur(2024), _dur(2025)
    rows = {
        LineItem.TOTAL_ASSETS: [1000.0, 1100.0],
        LineItem.TOTAL_LIABILITIES: [400.0, 430.0],
        LineItem.TOTAL_EQUITY: [600.0, 670.0 if balanced else 999.0],
        LineItem.CASH: [200.0, 250.0],
        LineItem.NET_CHANGE_IN_CASH: [None, 50.0],
        LineItem.RETAINED_EARNINGS: [500.0, 570.0],
        LineItem.NET_INCOME: [None, 70.0],
        LineItem.DIVIDENDS_PAID: [None, 0.0],
        LineItem.PPE_NET: [300.0, 320.0],
        LineItem.CAPEX: [None, -40.0],
        LineItem.DEP_AMORT: [None, 20.0],
        LineItem.DA_CF: [None, 20.0],
    }
    return StatementSet(periods=[h, pj], rows=rows, n_hist=1)


def test_invariants_pass_on_balanced_model():
    rep = run_all(_proj_statements(balanced=True), tol=1.0)
    assert rep.passed, rep.summary()


def test_balance_sheet_invariant_catches_imbalance():
    res = check_balance_sheet(_proj_statements(balanced=False), tol=1.0)
    assert not res.ok
    assert res.max_abs > 1.0


def test_cfs_re_ppe_rolls_pass():
    s = _proj_statements(balanced=True)
    assert check_cfs_ties_to_cash(s).ok
    assert check_retained_earnings_roll(s).ok
    assert check_ppe_roll(s).ok


def test_retained_earnings_roll_catches_break():
    # RE_t must equal RE_{t-1} + NI_t - div_t; break the roll and assert it FAILS.
    s = _proj_statements(balanced=True)
    s.rows[LineItem.RETAINED_EARNINGS] = [500.0, 900.0]  # should be 500 + 70 - 0 = 570
    assert not check_retained_earnings_roll(s).ok


def test_ppe_roll_catches_break():
    # PP&E_t must equal PP&E_{t-1} + capex_t - D&A_t; break it and assert it FAILS.
    s = _proj_statements(balanced=True)
    s.rows[LineItem.PPE_NET] = [300.0, 500.0]  # should be 300 + (-40) - 20... roll = 280
    assert not check_ppe_roll(s).ok


def test_invariant_summary_reports_fail_and_residual():
    # The summary() must surface a FAILING check (exercises the failure-reporting path,
    # not just the happy 'all OK' string).
    rep = run_all(_proj_statements(balanced=False), tol=1.0)
    assert not rep.passed
    assert "FAIL" in rep.summary()
