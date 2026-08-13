"""Tests for the illustrative LBO engine.

Self-contained: synthetic ``StatementSet`` + ``LBOAssumptions``, no fixtures.
The centrepiece is a golden hand-computed case where sources & uses, the swept
debt schedule, exit equity, MOIC and IRR are all worked out by hand and the
engine is asserted to match to the cent (IRR to ~1e-7).
"""

from __future__ import annotations

from datetime import date

import pytest
from src.interfaces import LBOAssumptions, StatementSet
from src.lbo import LBOModelEngine
from src.lbo.engine import _at, _irr
from src.schema import LineItem, Period, PeriodType


def _period(year: int) -> Period:
    """A fiscal-year DURATION period ending in ``year`` (labels only matter to
    the engine as ordered columns)."""
    return Period(
        ptype=PeriodType.DURATION,
        start=date(year, 1, 1),
        end=date(year, 12, 31),
        fy=year,
        fp="FY",
    )


def _make_statements(
    *,
    n_hist: int,
    n_proj: int,
    rows: dict[LineItem, list[float | None]],
) -> StatementSet:
    """Build a StatementSet with ``n_hist + n_proj`` DURATION columns.

    Each row in ``rows`` must already be length ``n_hist + n_proj``.
    """
    n = n_hist + n_proj
    periods = [_period(2020 + i) for i in range(n)]
    for li, series in rows.items():
        assert len(series) == n, f"{li} row length {len(series)} != {n}"
    return StatementSet(periods=periods, rows=dict(rows), n_hist=n_hist)


def _golden_statements() -> StatementSet:
    """1 historical + 3 projected periods for the golden case.

    Historical (idx 0): OPERATING_INCOME=80, DEP_AMORT=20 -> EBITDA=100.
    Projected (idx 1..3): OPERATING_INCOME=100, DEP_AMORT=20, CAPEX=-40,
    PRETAX_INCOME=100, INCOME_TAX_EXPENSE=20 (-> tax rate 20%) each year.
    """
    return _make_statements(
        n_hist=1,
        n_proj=3,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0, 100.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0, 20.0],
            LineItem.CAPEX: [None, -40.0, -40.0, -40.0],
            LineItem.PRETAX_INCOME: [None, 100.0, 100.0, 100.0],
            LineItem.INCOME_TAX_EXPENSE: [None, 20.0, 20.0, 20.0],
            LineItem.SHARES_DILUTED: [10.0, None, None, None],
        },
    )


def _golden_assumptions() -> LBOAssumptions:
    return LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.6,
        debt_rate=0.05,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=3,
    )


# ---------------------------------------------------------------------------
# Golden hand-computed case (LEVERED sweep: interest reduces the sweep base and
# un-swept cash accumulates to exit, netted against debt).
# ---------------------------------------------------------------------------
def test_golden_case_hand_computed():
    """Full worked example with the levered-sweep methodology.

    Entry EBITDA = 80 + 20 = 100; entry_ev = 10 * 100 = 1000.
    new_debt = 0.6 * 1000 = 600; sponsor_equity = 1000 - 600 = 400.
    Operating FCF each proj year = 100*(1-0.2) + 20 - 40 = 60. Debt rate 5%.
    Levered FCF = 60 - interest; sweep = 0.5 * levered FCF; cash builds by the rest.
      Y1: begin 600, int 30.0, lFCF 30.0,   sweep 15.0,    end 585.0,   cash 15.0
      Y2: begin 585, int 29.25, lFCF 30.75, sweep 15.375,  end 569.625, cash 30.375
      Y3: begin 569.625, int 28.48125, lFCF 31.51875, sweep 15.759375,
          end 553.865625, cash 46.134375
    Exit EBITDA = 120; exit_ev = 1200. net debt = 553.865625 - 46.134375 = 507.73125.
    exit_equity = 1200 - 507.73125 = 692.26875. MOIC = 692.26875 / 400 = 1.7306...
    IRR = MOIC**(1/3) - 1 (single-in/single-out; cash accrues to exit).
    """
    engine = LBOModelEngine()
    result = engine.run(_golden_statements(), _golden_assumptions(), current_price=50.0)

    # Sources & Uses
    assert result.uses["purchase_enterprise_value"] == pytest.approx(1000.0)
    assert result.sources["new_debt"] == pytest.approx(600.0)
    assert result.sources["sponsor_equity"] == pytest.approx(400.0)
    assert result.sources_equal_uses()

    # Debt schedule (levered sweep + cash build), hand-computed above.
    expected = [
        {"begin": 600.0, "interest": 30.0, "sweep": 15.0, "end": 585.0, "cash_balance": 15.0},
        {
            "begin": 585.0,
            "interest": 29.25,
            "sweep": 15.375,
            "end": 569.625,
            "cash_balance": 30.375,
        },
        {
            "begin": 569.625,
            "interest": 28.48125,
            "sweep": 15.759375,
            "end": 553.865625,
            "cash_balance": 46.134375,
        },
    ]
    assert len(result.debt_schedule) == 3
    for got, exp in zip(result.debt_schedule, expected, strict=True):
        for key, val in exp.items():
            assert got[key] == pytest.approx(val), f"{key}: {got[key]} != {val}"

    # Exit + returns
    assert result.exit_equity_value == pytest.approx(692.26875)
    assert result.moic == pytest.approx(692.26875 / 400.0)
    assert result.irr == pytest.approx(result.moic ** (1.0 / 3.0) - 1.0, abs=1e-7)


def test_sources_equal_uses_helper():
    engine = LBOModelEngine()
    result = engine.run(_golden_statements(), _golden_assumptions(), current_price=50.0)
    assert result.sources_equal_uses(tol=0.01)
    assert sum(result.sources.values()) == pytest.approx(sum(result.uses.values()))


def test_irr_matches_closed_form_invariant():
    """Required invariant: for the single-in/single-out case the reported IRR
    equals MOIC**(1/hold_years) - 1, recomputed independently here."""
    engine = LBOModelEngine()
    assumptions = _golden_assumptions()
    result = engine.run(_golden_statements(), assumptions, current_price=50.0)
    independent = result.moic ** (1.0 / assumptions.hold_years) - 1.0
    assert result.irr == pytest.approx(independent, abs=1e-6)


# ---------------------------------------------------------------------------
# Debt-sweep behaviour
# ---------------------------------------------------------------------------
def test_sweep_monotonic_and_floored_at_zero():
    """Sweep never drives the balance negative and the schedule is monotonically
    non-increasing; begin_{t+1} == end_t."""
    engine = LBOModelEngine()
    # Small debt, full sweep, large FCF -> sweep must be floored at the balance.
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.05,  # new_debt = 0.05 * 1000 = 50
        debt_rate=0.10,
        cash_sweep_pct=1.0,  # desired sweep = FCF = 60 > 50
        exit_ev_ebitda=10.0,
        hold_years=3,
    )
    result = engine.run(_golden_statements(), assumptions, current_price=50.0)

    prev_end = None
    for row in result.debt_schedule:
        assert row["end"] >= 0.0
        assert row["end"] <= row["begin"]  # monotonic non-increasing
        if prev_end is not None:
            assert row["begin"] == pytest.approx(prev_end)
        prev_end = row["end"]

    # Year 1 sweep floored to the opening balance (50), fully repaid.
    assert result.debt_schedule[0]["sweep"] == pytest.approx(50.0)
    assert result.debt_schedule[0]["end"] == pytest.approx(0.0)
    # Once repaid, no negative balance and no phantom sweep.
    assert result.debt_schedule[1]["sweep"] == pytest.approx(0.0)
    assert result.debt_schedule[-1]["end"] == pytest.approx(0.0)


def test_negative_fcf_sweeps_nothing():
    """A year with negative levered FCF sweeps 0 (debt is not paid down), and
    the un-swept cash deficit accumulates against net debt at exit (not floored
    away). Uses a mild deficit so the deal still exits solvent."""
    engine = LBOModelEngine()
    # Capex makes operating FCF mildly negative (80 + 20 - 130 = -30/yr).
    statements = _make_statements(
        n_hist=1,
        n_proj=2,
        rows={
            LineItem.OPERATING_INCOME: [100.0, 100.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0],
            LineItem.CAPEX: [None, -130.0, -130.0],
            LineItem.PRETAX_INCOME: [None, 100.0, 100.0],
            LineItem.INCOME_TAX_EXPENSE: [None, 20.0, 20.0],
            LineItem.SHARES_DILUTED: [10.0, None, None],
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.6,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=2,
    )
    result = engine.run(statements, assumptions, current_price=50.0)
    for row in result.debt_schedule:
        assert row["sweep"] == pytest.approx(0.0)  # negative FCF -> no sweep
        assert row["end"] == pytest.approx(row["begin"])  # debt not paid down
    # The cash deficit accumulated (negative) and increased net debt at exit —
    # it was NOT floored to zero. Net debt > ending debt confirms it.
    ending_debt = result.debt_schedule[-1]["end"]
    net_debt = ending_debt - result.debt_schedule[-1]["cash_balance"]
    assert result.debt_schedule[-1]["cash_balance"] < 0
    assert net_debt > ending_debt


# ---------------------------------------------------------------------------
# Entry EV via the equity + net-debt branch (entry_ev_ebitda is None)
# ---------------------------------------------------------------------------
def test_entry_ev_from_equity_plus_net_debt():
    """When entry_ev_ebitda is None, EV = offer-price*shares + net debt."""
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=2,
        rows={
            LineItem.OPERATING_INCOME: [100.0, 100.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0],
            LineItem.CAPEX: [None, -40.0, -40.0],
            LineItem.SHARES_DILUTED: [100.0, None, None],
            # Net debt = (STD 0 + LTD 200) - (cash 50 + STI 0) = 150.
            LineItem.LONG_TERM_DEBT: [200.0, None, None],
            LineItem.CASH: [50.0, None, None],
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.2,  # offer price = 10 * 1.2 = 12; equity = 12 * 100 = 1200
        entry_ev_ebitda=None,
        debt_pct_of_ev=0.5,
        debt_rate=0.08,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=9.0,
        hold_years=2,
    )
    result = engine.run(statements, assumptions, current_price=10.0)
    # entry_ev = equity(1200) + net_debt(150) = 1350
    assert result.uses["purchase_enterprise_value"] == pytest.approx(1350.0)
    assert result.sources["new_debt"] == pytest.approx(675.0)
    assert result.sources["sponsor_equity"] == pytest.approx(675.0)
    assert result.sources_equal_uses()


def test_da_falls_back_to_da_cf():
    """EBITDA uses DA_CF when DEP_AMORT is absent."""
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=1,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0],
            LineItem.DA_CF: [20.0, 20.0],  # no DEP_AMORT row at all
            LineItem.CAPEX: [None, -40.0],
            LineItem.SHARES_DILUTED: [10.0, None],
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.5,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=1,
    )
    result = engine.run(statements, assumptions, current_price=50.0)
    # Entry EBITDA = 80 + 20 = 100 -> entry_ev = 1000.
    assert result.uses["purchase_enterprise_value"] == pytest.approx(1000.0)


def test_shares_fallback_to_outstanding():
    """Entry equity uses SHARES_OUTSTANDING when SHARES_DILUTED is absent
    (exercised via the equity+net-debt EV branch where shares drive EV)."""
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=1,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0],
            LineItem.CAPEX: [None, -40.0],
            LineItem.SHARES_OUTSTANDING: [50.0, None],
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=None,  # EV = equity + net debt, so shares matter
        debt_pct_of_ev=0.5,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=1,
    )
    result = engine.run(statements, assumptions, current_price=20.0)
    # equity = 20 * 50 = 1000; net debt = 0 -> entry_ev = 1000.
    assert result.uses["purchase_enterprise_value"] == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Input-guard / honest-unknown validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_premium": 0.0, "debt_pct_of_ev": 1.5},  # leverage out of range
        {"entry_premium": 0.0, "cash_sweep_pct": -0.1},  # sweep out of range
    ],
)
def test_invalid_assumption_ranges_raise(kwargs):
    engine = LBOModelEngine()
    base = {
        "entry_premium": 0.0,
        "entry_ev_ebitda": 10.0,
        "debt_pct_of_ev": 0.6,
        "debt_rate": 0.10,
        "cash_sweep_pct": 0.5,
        "exit_ev_ebitda": 10.0,
        "hold_years": 3,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        engine.run(_golden_statements(), LBOAssumptions(**base), current_price=50.0)


def test_bad_current_price_raises():
    engine = LBOModelEngine()
    with pytest.raises(ValueError):
        engine.run(_golden_statements(), _golden_assumptions(), current_price=0.0)


def test_bad_hold_years_raises():
    engine = LBOModelEngine()
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.6,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=0,
    )
    with pytest.raises(ValueError):
        engine.run(_golden_statements(), assumptions, current_price=50.0)


def test_insufficient_projected_periods_raises():
    engine = LBOModelEngine()
    # Only 1 projected period but hold_years=3.
    statements = _make_statements(
        n_hist=1,
        n_proj=1,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0],
            LineItem.SHARES_DILUTED: [10.0, None],
        },
    )
    with pytest.raises(ValueError):
        engine.run(statements, _golden_assumptions(), current_price=50.0)


def test_no_historical_period_raises():
    engine = LBOModelEngine()
    statements = StatementSet(periods=[], rows={}, n_hist=0)
    with pytest.raises(ValueError):
        engine.run(statements, _golden_assumptions(), current_price=50.0)


def test_missing_shares_raises():
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=3,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0, 100.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0, 20.0],
            LineItem.CAPEX: [None, -40.0, -40.0, -40.0],
        },
    )
    with pytest.raises(ValueError):
        engine.run(statements, _golden_assumptions(), current_price=50.0)


def test_missing_operating_income_raises():
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=3,
        rows={
            # No OPERATING_INCOME row -> EBITDA cannot be computed.
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0, 20.0],
            LineItem.SHARES_DILUTED: [10.0, None, None, None],
        },
    )
    with pytest.raises(ValueError):
        engine.run(statements, _golden_assumptions(), current_price=50.0)


def test_nonpositive_entry_ebitda_raises():
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=3,
        rows={
            LineItem.OPERATING_INCOME: [-30.0, 100.0, 100.0, 100.0],  # EBIT + D&A <= 0
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0, 20.0],
            LineItem.SHARES_DILUTED: [10.0, None, None, None],
        },
    )
    with pytest.raises(ValueError):
        engine.run(statements, _golden_assumptions(), current_price=50.0)


def test_sponsor_equity_nonpositive_raises():
    engine = LBOModelEngine()
    # debt_pct_of_ev = 1.0 with zero fees -> sponsor equity plug == 0.
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=1.0,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=3,
    )
    with pytest.raises(ValueError):
        engine.run(_golden_statements(), assumptions, current_price=50.0)


def test_negative_exit_equity_raises():
    engine = LBOModelEngine()
    # Tiny exit multiple leaves exit EV below remaining debt -> negative equity.
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.6,
        debt_rate=0.10,
        cash_sweep_pct=0.0,  # no paydown; remaining debt stays 600
        exit_ev_ebitda=1.0,  # exit EV = 1 * 120 = 120 < 600
        hold_years=3,
    )
    with pytest.raises(ValueError):
        engine.run(_golden_statements(), assumptions, current_price=50.0)


# ---------------------------------------------------------------------------
# _irr solver directly
# ---------------------------------------------------------------------------
def test_irr_solver_simple_doubling():
    # Double your money in 1 year -> IRR = 100%.
    assert _irr([-100.0, 200.0]) == pytest.approx(1.0, abs=1e-6)


def test_irr_solver_unbracketed_raises():
    # All-positive cash flows: NPV never crosses zero -> not bracketed.
    with pytest.raises(ValueError):
        _irr([100.0, 100.0, 100.0])


def test_at_out_of_range_returns_none():
    assert _at([1.0, 2.0], -1) is None
    assert _at([1.0, 2.0], 5) is None
    assert _at([1.0, 2.0], 1) == 2.0


def test_nonpositive_entry_ev_raises():
    """Equity+net-debt EV branch driven below zero by deep negative net debt
    (huge net cash) -> entry EV must be > 0."""
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=1,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0],
            LineItem.DEP_AMORT: [20.0, 20.0],
            LineItem.SHARES_DILUTED: [1.0, None],
            LineItem.CASH: [10000.0, None],  # net debt = -10000 dominates equity
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=None,  # equity + net-debt branch
        debt_pct_of_ev=0.5,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=1,
    )
    with pytest.raises(ValueError):
        engine.run(statements, assumptions, current_price=1.0)


def test_missing_operating_income_in_sweep_year_raises():
    """OPERATING_INCOME present historically but absent in a projected sweep
    year -> the unlevered-FCF path raises (honest unknown)."""
    engine = LBOModelEngine()
    statements = _make_statements(
        n_hist=1,
        n_proj=2,
        rows={
            LineItem.OPERATING_INCOME: [80.0, 100.0, None],  # missing in proj year 2
            LineItem.DEP_AMORT: [20.0, 20.0, 20.0],
            LineItem.CAPEX: [None, -40.0, -40.0],
            LineItem.SHARES_DILUTED: [10.0, None, None],
        },
    )
    assumptions = LBOAssumptions(
        entry_premium=0.0,
        entry_ev_ebitda=10.0,
        debt_pct_of_ev=0.6,
        debt_rate=0.10,
        cash_sweep_pct=0.5,
        exit_ev_ebitda=10.0,
        hold_years=2,
    )
    with pytest.raises(ValueError):
        engine.run(statements, assumptions, current_price=50.0)
