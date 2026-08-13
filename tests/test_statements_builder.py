"""Tests for the statement builder: historical assembly + 3-statement projection.

Self-contained: constructs synthetic ``NormalizedFacts`` / ``StatementSet`` and
does NOT depend on ``src/edgar``.
"""

from __future__ import annotations

import random
from datetime import date

from src.interfaces import ProjectionAssumptions, StatementSet
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
from src.statements import ThreeStatementBuilder, balance_check

_PROV = Provenance("Synthetic", "us-gaap", Unit.USD, "acc-test", "10-K", date(2024, 5, 1))


def _fy(end_year: int) -> Period:
    return Period(
        PeriodType.DURATION,
        end=date(end_year, 12, 31),
        start=date(end_year, 1, 1),
        fy=end_year,
        fp="FY",
    )


def _instant(end_year: int) -> Period:
    return Period(PeriodType.INSTANT, end=date(end_year, 12, 31), fy=end_year, fp="FY")


def _make_facts(duration_vals: dict, instant_vals: dict, years: list[int]) -> NormalizedFacts:
    """Build NormalizedFacts. ``*_vals`` map LineItem -> {year: value}."""
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="TST", name="Test Co"))
    for yr in years:
        for li, per_year in duration_vals.items():
            if yr in per_year:
                nf.add(Fact(li, _fy(yr), float(per_year[yr]), _PROV))
        for li, per_year in instant_vals.items():
            if yr in per_year:
                nf.add(Fact(li, _instant(yr), float(per_year[yr]), _PROV))
    return nf


# --------------------------------------------------------------------------- #
# Historical assembly
# --------------------------------------------------------------------------- #
def test_build_historical_aligns_periods_and_values():
    facts = _make_facts(
        duration_vals={
            LineItem.REVENUE: {2022: 1000, 2023: 1100},
            LineItem.COST_OF_REVENUE: {2022: 600, 2023: 640},
            LineItem.NET_INCOME: {2022: 120, 2023: 150},
        },
        instant_vals={
            LineItem.CASH: {2022: 300, 2023: 350},
            LineItem.RETAINED_EARNINGS: {2022: 500, 2023: 620},
        },
        years=[2022, 2023],
    )
    hist = ThreeStatementBuilder().build_historical(facts)
    assert hist.n_hist == 2
    assert [p.fy for p in hist.periods] == [2022, 2023]
    assert hist.series(LineItem.REVENUE) == [1000.0, 1100.0]
    assert hist.series(LineItem.CASH) == [300.0, 350.0]
    # gross profit derived where reported value absent
    assert hist.series(LineItem.GROSS_PROFIT) == [400.0, 460.0]


def test_build_historical_honest_unknown_stays_none():
    facts = _make_facts(
        duration_vals={LineItem.REVENUE: {2023: 1000}},
        instant_vals={},
        years=[2023],
    )
    hist = ThreeStatementBuilder().build_historical(facts)
    # A never-provided line is None, not fabricated.
    assert hist.series(LineItem.GOODWILL) == [None]
    assert hist.series(LineItem.INVENTORY) == [None]
    # gross profit not derivable without COGS -> stays None
    assert hist.series(LineItem.GROSS_PROFIT) == [None]


def test_build_historical_does_not_overwrite_reported_gross_profit():
    facts = _make_facts(
        duration_vals={
            LineItem.REVENUE: {2023: 1000},
            LineItem.COST_OF_REVENUE: {2023: 600},
            LineItem.GROSS_PROFIT: {2023: 390},  # filer-reported, differs from 400
        },
        instant_vals={},
        years=[2023],
    )
    hist = ThreeStatementBuilder().build_historical(facts)
    assert hist.series(LineItem.GROSS_PROFIT) == [390.0]


# --------------------------------------------------------------------------- #
# Golden tiny model
# --------------------------------------------------------------------------- #
def _one_year_hist() -> StatementSet:
    """A single balanced historical year, built by hand."""
    rows: dict[LineItem, list[float | None]] = {li: [None] for li in LineItem}
    rows[LineItem.REVENUE] = [1000.0]
    rows[LineItem.COST_OF_REVENUE] = [600.0]
    rows[LineItem.GROSS_PROFIT] = [400.0]
    rows[LineItem.NET_INCOME] = [150.0]
    # Balance sheet (balanced: assets 1000 = liab 400 + equity 600)
    rows[LineItem.CASH] = [200.0]
    rows[LineItem.ACCOUNTS_RECEIVABLE] = [100.0]
    rows[LineItem.INVENTORY] = [150.0]
    rows[LineItem.PPE_NET] = [550.0]
    rows[LineItem.ACCOUNTS_PAYABLE] = [80.0]
    rows[LineItem.SHORT_TERM_DEBT] = [20.0]
    rows[LineItem.LONG_TERM_DEBT] = [300.0]
    rows[LineItem.RETAINED_EARNINGS] = [400.0]
    rows[LineItem.COMMON_STOCK] = [200.0]
    return StatementSet(periods=[_fy(2023)], rows=rows, n_hist=1)


def _simple_assumptions(n: int = 5) -> ProjectionAssumptions:
    return ProjectionAssumptions(
        n_years=n,
        revenue_growth=[0.10] * n,
        gross_margin=[0.40] * n,
        sga_pct_revenue=[0.10] * n,
        rnd_pct_revenue=[0.05] * n,
        dso=[36.5] * n,
        dio=[36.5] * n,
        dpo=[36.5] * n,
        capex_pct_revenue=[0.05] * n,
        da_pct_revenue=[0.04] * n,
        tax_rate=[0.21] * n,
        interest_rate_on_debt=0.05,
        interest_rate_on_cash=0.02,
        min_cash=100.0,
        dividend_payout=[0.20] * n,
    )


def test_golden_revenue_and_income_path():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    assert stmts.n_hist == 1
    assert len(stmts.periods) == 6

    rev = stmts.series(LineItem.REVENUE)
    # 1000 * 1.1^t
    assert rev[1] == 1000.0 * 1.1
    assert abs(rev[5] - 1000.0 * 1.1**5) < 1e-6
    assert [p.fy for p in stmts.periods[1:]] == [2024, 2025, 2026, 2027, 2028]

    # Year 1 income-statement hand math.
    r1 = 1100.0
    cogs1 = r1 * 0.60
    gp1 = r1 - cogs1
    ebit1 = gp1 - 0.10 * r1 - 0.05 * r1
    assert abs(stmts.series(LineItem.OPERATING_INCOME)[1] - ebit1) < 1e-6
    assert abs(stmts.series(LineItem.COST_OF_REVENUE)[1] - cogs1) < 1e-6
    assert abs(stmts.series(LineItem.GROSS_PROFIT)[1] - gp1) < 1e-6


def test_golden_retained_earnings_roll():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    re = stmts.series(LineItem.RETAINED_EARNINGS)
    ni = stmts.series(LineItem.NET_INCOME)
    div = stmts.series(LineItem.DIVIDENDS_PAID)  # stored negative
    prev = 400.0  # last historical RE
    for t in range(1, 6):
        expected = prev + ni[t] + div[t]  # div negative -> subtracts
        assert abs(re[t] - expected) < 1e-6
        prev = re[t]


def test_golden_ppe_roll():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    ppe = stmts.series(LineItem.PPE_NET)
    capex = stmts.series(LineItem.CAPEX)  # negative
    da = stmts.series(LineItem.DEP_AMORT)  # positive
    prev = 550.0
    for t in range(1, 6):
        # PP&E_t = PP&E_{t-1} + capex_abs - D&A ; capex stored negative
        expected = prev + (-capex[t]) - da[t]
        assert abs(ppe[t] - expected) < 1e-6
        prev = ppe[t]


def test_dividends_capex_signs_negative():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    for t in range(1, 6):
        assert stmts.series(LineItem.CAPEX)[t] < 0
        assert stmts.series(LineItem.DIVIDENDS_PAID)[t] < 0


def test_cfs_ending_cash_ties_to_bs_cash():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    cash = stmts.series(LineItem.CASH)
    net_change = stmts.series(LineItem.NET_CHANGE_IN_CASH)
    prev = 200.0
    for t in range(1, 6):
        assert abs(cash[t] - (prev + net_change[t])) < 1e-6
        prev = cash[t]


def test_min_cash_floor_respected():
    hist = _one_year_hist()
    a = _simple_assumptions()
    a.min_cash = 500.0  # force revolver draws
    stmts = ThreeStatementBuilder().project(hist, a)
    cash = stmts.series(LineItem.CASH)
    for t in range(1, 6):
        assert cash[t] >= 500.0 - 1e-6


def test_balance_check_zero_on_golden():
    hist = _one_year_hist()
    stmts = ThreeStatementBuilder().project(hist, _simple_assumptions())
    resid = balance_check(stmts)
    for t in range(1, 6):
        assert abs(resid[t]) < 1e-3


def test_project_requires_history():
    empty = StatementSet(periods=[], rows={li: [] for li in LineItem}, n_hist=0)
    try:
        ThreeStatementBuilder().project(empty, _simple_assumptions())
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# --------------------------------------------------------------------------- #
# PROPERTY TEST — the headline invariant
# --------------------------------------------------------------------------- #
def _random_hist(rng: random.Random) -> StatementSet:
    rev = rng.uniform(500, 5000)
    rows: dict[LineItem, list[float | None]] = {li: [None] for li in LineItem}
    rows[LineItem.REVENUE] = [rev]
    cash = rng.uniform(50, 800)
    ar = rng.uniform(20, 500)
    inv = rng.uniform(20, 500)
    ppe = rng.uniform(100, 3000)
    other_nca = rng.uniform(0, 500)
    ap = rng.uniform(20, 400)
    std = rng.uniform(0, 300)
    ltd = rng.uniform(0, 2000)
    rows[LineItem.CASH] = [cash]
    rows[LineItem.ACCOUNTS_RECEIVABLE] = [ar]
    rows[LineItem.INVENTORY] = [inv]
    rows[LineItem.PPE_NET] = [ppe]
    rows[LineItem.OTHER_NONCURRENT_ASSETS] = [other_nca]
    rows[LineItem.ACCOUNTS_PAYABLE] = [ap]
    rows[LineItem.SHORT_TERM_DEBT] = [std]
    rows[LineItem.LONG_TERM_DEBT] = [ltd]
    rows[LineItem.RETAINED_EARNINGS] = [rng.uniform(0, 1000)]
    rows[LineItem.COMMON_STOCK] = [rng.uniform(0, 1000)]
    return StatementSet(periods=[_fy(2023)], rows=rows, n_hist=1)


def _random_assumptions(rng: random.Random, n: int = 5) -> ProjectionAssumptions:
    return ProjectionAssumptions(
        n_years=n,
        revenue_growth=[rng.uniform(0.0, 0.20) for _ in range(n)],
        gross_margin=[rng.uniform(0.20, 0.70) for _ in range(n)],
        sga_pct_revenue=[rng.uniform(0.05, 0.20) for _ in range(n)],
        rnd_pct_revenue=[rng.uniform(0.0, 0.15) for _ in range(n)],
        dso=[rng.uniform(20, 90) for _ in range(n)],
        dio=[rng.uniform(20, 120) for _ in range(n)],
        dpo=[rng.uniform(20, 90) for _ in range(n)],
        capex_pct_revenue=[rng.uniform(0.02, 0.10) for _ in range(n)],
        da_pct_revenue=[rng.uniform(0.02, 0.08) for _ in range(n)],
        tax_rate=[rng.uniform(0.15, 0.30) for _ in range(n)],
        interest_rate_on_debt=rng.uniform(0.02, 0.10),
        interest_rate_on_cash=rng.uniform(0.0, 0.05),
        min_cash=rng.uniform(0, 500),
        dividend_payout=[rng.uniform(0.0, 0.60) for _ in range(n)],
    )


def test_property_balance_sheet_always_balances():
    rng = random.Random(20260805)
    builder = ThreeStatementBuilder()
    n_iters = 2000
    max_resid = 0.0
    for _ in range(n_iters):
        hist = _random_hist(rng)
        a = _random_assumptions(rng)
        stmts = builder.project(hist, a)
        resid = balance_check(stmts)
        for t in range(1, a.n_years + 1):
            max_resid = max(max_resid, abs(resid[t]))
            assert abs(resid[t]) < 1.0, f"BS off by {resid[t]} in period {t}"
    # Surface the observed worst-case residual for the report.
    assert max_resid < 1.0
    print(f"\n[property] {n_iters} iters, max BS residual = {max_resid:.3e}")


def test_property_re_and_ppe_rolls_hold_randomized():
    rng = random.Random(11)
    builder = ThreeStatementBuilder()
    for _ in range(300):
        hist = _random_hist(rng)
        a = _random_assumptions(rng)
        stmts = builder.project(hist, a)
        re = stmts.series(LineItem.RETAINED_EARNINGS)
        ni = stmts.series(LineItem.NET_INCOME)
        div = stmts.series(LineItem.DIVIDENDS_PAID)
        ppe = stmts.series(LineItem.PPE_NET)
        capex = stmts.series(LineItem.CAPEX)
        da = stmts.series(LineItem.DEP_AMORT)
        re_prev = hist.series(LineItem.RETAINED_EARNINGS)[0]
        ppe_prev = hist.series(LineItem.PPE_NET)[0]
        for t in range(1, a.n_years + 1):
            assert abs(re[t] - (re_prev + ni[t] + div[t])) < 1e-4
            assert abs(ppe[t] - (ppe_prev + (-capex[t]) - da[t])) < 1e-4
            re_prev, ppe_prev = re[t], ppe[t]
