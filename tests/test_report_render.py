"""Tests for the initiating-coverage report (charts + HTML template + PDF).

Headline property: every financial figure rendered comes from the ModelBundle
(single source of truth). We assert the rating, ticker, prices, disclaimer and
section headings are present, and that no ``None`` leaks where a number belongs.

The synthetic bundle mirrors tests/test_workbook_writer.py::_bundle so the two
deliverables are exercised against the same shape.
"""

from __future__ import annotations

import datetime
import importlib.util

import pytest
from src.interfaces import (
    CompsResult,
    DCFResult,
    ModelBundle,
    PeerMultiples,
    PrecedentTransaction,
    ProjectionAssumptions,
    StatementSet,
    TerminalAssumptions,
    WACCInputs,
)
from src.report import build_html
from src.report.charts import (
    build_all_charts,
    comps_scatter_chart,
    football_field_chart,
)
from src.report.template import DISCLAIMER
from src.schema import CompanyMeta, LineItem, Period, PeriodType


def _weasyprint_available() -> bool:
    """True iff weasyprint imports (native libs resolvable) in this env."""
    import os

    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    if importlib.util.find_spec("weasyprint") is None:
        return False
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


def _dur(y):
    return Period(
        PeriodType.DURATION,
        end=datetime.date(y, 3, 31),
        start=datetime.date(y - 1, 4, 1),
        fy=y,
        fp="FY",
    )


def _bundle(empty_peers: bool = False) -> ModelBundle:
    periods = [_dur(2024), _dur(2025), _dur(2026), _dur(2027), _dur(2028)]
    rows = {
        LineItem.REVENUE: [4.0e9, 5.0e9, 5.4e9, 5.8e9, 6.2e9],
        LineItem.COST_OF_REVENUE: [1.8e9, 2.1e9, 2.27e9, 2.44e9, 2.6e9],
        LineItem.GROSS_PROFIT: [2.2e9, 2.9e9, 3.13e9, 3.36e9, 3.6e9],
        LineItem.OPERATING_INCOME: [0.9e9, 1.15e9, 1.24e9, 1.33e9, 1.42e9],
        LineItem.NET_INCOME: [0.7e9, 0.9e9, 0.97e9, 1.04e9, 1.11e9],
        LineItem.EPS_DILUTED: [4.79, 6.16, 6.64, 7.12, 7.60],
        LineItem.CASH: [1.8e9, 1.9e9, 2.0e9, 2.1e9, 2.2e9],
        LineItem.TOTAL_ASSETS: [3.5e9, 3.7e9, 3.9e9, 4.1e9, 4.3e9],
        LineItem.TOTAL_EQUITY: [2.4e9, 2.5e9, 2.6e9, 2.7e9, 2.8e9],
        LineItem.CFO: [1.0e9, 1.18e9, 1.27e9, 1.36e9, 1.45e9],
        LineItem.CAPEX: [-0.08e9, -0.085e9, -0.09e9, -0.095e9, -0.1e9],
        LineItem.DA_CF: [0.1e9, 0.11e9, 0.12e9, 0.13e9, 0.14e9],
    }
    stmts = StatementSet(periods=periods, rows=rows, n_hist=2)
    assum = ProjectionAssumptions(
        n_years=3,
        revenue_growth=[0.08, 0.07, 0.07],
        gross_margin=[0.58] * 3,
        sga_pct_revenue=[0.34] * 3,
        rnd_pct_revenue=[0.0] * 3,
        capex_pct_revenue=[0.02] * 3,
        da_pct_revenue=[0.02] * 3,
        tax_rate=[0.24] * 3,
        dso=[40] * 3,
        dio=[110] * 3,
        dpo=[45] * 3,
        min_cash=400.0e6,
        dividend_payout=[0.0] * 3,
    )
    wacc = WACCInputs(
        risk_free_rate=0.043,
        beta=1.1,
        equity_risk_premium=0.05,
        pretax_cost_of_debt=0.06,
        tax_rate=0.24,
        market_cap=18.0e9,
        total_debt=1.0e9,
    )
    terminal = TerminalAssumptions(
        terminal_growth=0.03, exit_ev_ebitda=15.0, mid_year_convention=True
    )
    dcf = DCFResult(
        wacc=0.098,
        pv_explicit_fcff=3.5e9,
        terminal_value_gordon=20.0e9,
        terminal_value_exit=22.0e9,
        pv_terminal_gordon=12.0e9,
        pv_terminal_exit=13.0e9,
        enterprise_value_gordon=15.5e9,
        enterprise_value_exit=16.5e9,
        net_debt=-1.9e9,
        minority_interest=0.0,
        equity_value_gordon=17.4e9,
        equity_value_exit=18.4e9,
        shares_diluted=146.0e6,
        implied_price_gordon=119.18,
        implied_price_exit=126.03,
        fcff_by_year=[0.7e9, 0.76e9, 0.81e9],
        discount_factors=[0.95, 0.87, 0.79],
    )
    peers = (
        []
        if empty_peers
        else [
            PeerMultiples("NKE", "Nike", 120.0e9, 110.0e9, 3.0, 18.0, 25.0),
            PeerMultiples("CROX", "Crocs", 9.0e9, 7.5e9, 2.5, 9.0, 8.0),
        ]
    )
    comps = CompsResult(
        peers=peers,
        stats={
            "ev_ebitda_ltm": {"median": 13.5, "mean": 13.5},
            "ev_revenue_ltm": {"median": 2.75, "mean": 2.75},
            "pe_ltm": {"median": 16.5, "mean": 16.5},
        },
        implied_price_from_ebitda=112.0,
        implied_price_from_revenue=108.0,
        implied_price_from_pe=115.0,
    )
    precedents = [
        PrecedentTransaction(
            "2025", "3G Capital", "Skechers", 9.4e9, 1.2, 11.0, "press release 2025"
        ),
    ]
    return ModelBundle(
        company=CompanyMeta(cik="0000910521", ticker="DECK", name="Deckers Outdoor"),
        statements=stmts,
        proj_assumptions=assum,
        wacc_inputs=wacc,
        terminal=terminal,
        dcf=dcf,
        comps=comps,
        precedents=precedents,
        lbo=None,
        current_price=100.0,
        price_target=118.0,
        rating="Buy",
    )


# --- HTML content --------------------------------------------------------
def test_build_html_returns_string_with_core_fields(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    assert isinstance(html, str) and len(html) > 2000
    # Rating, ticker, company name.
    assert "Buy" in html
    assert "DECK" in html
    assert "Deckers Outdoor" in html
    # Current price and target (from ModelBundle).
    assert "$100.00" in html  # current price
    assert "$118.00" in html  # target
    # Implied DCF prices from engine.
    assert "$119.18" in html
    assert "$126.03" in html


def test_build_html_contains_disclaimer_verbatim(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    assert DISCLAIMER in html
    assert "not investment advice" in html
    assert "without implying SEC endorsement" in html


def test_build_html_has_all_section_headings(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    for heading in [
        "Executive Summary",
        "Company Overview",
        "Industry &amp; Competitive Analysis",
        "Financial Analysis",
        "Valuation",
        "Risks",
        "Appendix",
    ]:
        assert heading in html, f"missing section: {heading}"


def test_build_html_shows_wacc_and_terminal(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    assert "WACC" in html
    assert "9.8%" in html  # wacc value
    assert "3.0%" in html  # terminal growth
    assert "Terminal growth is below WACC" in html  # sanity note (g < WACC)


def test_build_html_no_none_leak_in_numeric_slots(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    # A well-formed bundle should never render the literal "None"; honest
    # unknowns render as an em dash instead.
    assert "None" not in html
    assert ">$None" not in html


def test_draft_placeholders_marked(tmp_path):
    html = build_html(_bundle(), str(tmp_path / "assets"))
    assert "[DRAFT: thesis" in html
    assert "[DRAFT:" in html


def test_terminal_growth_above_wacc_warns(tmp_path):
    m = _bundle()
    m.terminal.terminal_growth = 0.15  # > wacc 0.098
    html = build_html(m, str(tmp_path / "assets"))
    assert "WARNING" in html


# --- Charts --------------------------------------------------------------
def test_all_charts_produced_nonempty(tmp_path):
    out = str(tmp_path / "charts")
    charts = build_all_charts(_bundle(), out)
    # Always-present charts (segment_revenue is added only when segments load).
    assert {
        "revenue_margin",
        "fcf_trend",
        "comps_scatter",
        "football_field",
        "valuation_bridge",
    } <= set(charts)
    import os

    for name, path in charts.items():
        assert os.path.exists(path), f"{name} not created"
        assert os.path.getsize(path) > 1000, f"{name} suspiciously small"


def test_comps_scatter_handles_empty_peers(tmp_path):
    import os

    path = comps_scatter_chart(_bundle(empty_peers=True), str(tmp_path / "c"))
    assert os.path.exists(path) and os.path.getsize(path) > 1000


def test_football_field_single_comp_method(tmp_path):
    import os

    m = _bundle()
    m.comps.implied_price_from_revenue = None
    m.comps.implied_price_from_pe = None
    path = football_field_chart(m, str(tmp_path / "f"))
    assert os.path.exists(path) and os.path.getsize(path) > 1000


def test_build_html_empty_peers_still_renders(tmp_path):
    html = build_html(_bundle(empty_peers=True), str(tmp_path / "assets"))
    assert "No peer multiples available" in html
    assert "None" not in html


def test_honest_unknowns_render_as_em_dash(tmp_path):
    """Missing engine values must show an em dash, never a fabricated number
    and never the literal 'None' (honest-unknown contract)."""
    m = _bundle()
    m.price_target = None
    m.rating = None
    m.comps.implied_price_from_ebitda = None
    m.comps.implied_price_from_revenue = None
    m.comps.implied_price_from_pe = None
    m.dcf.minority_interest = None
    # Blank out an EPS cell to exercise the em-dash path in the key-fin table.
    m.statements.rows[LineItem.EPS_DILUTED][0] = None
    html = build_html(m, str(tmp_path / "assets"))
    assert "None" not in html
    assert "—" in html
    # Rating placeholder falls back to a labeled draft marker, not "None".
    assert "[DRAFT: rating]" in html


def test_empty_precedents_and_millions_scale(tmp_path):
    """Small-magnitude figures use the mm scale and empty precedents degrade
    gracefully rather than emitting a fake row."""
    m = _bundle()
    m.precedents = []
    # Scale everything down into the millions band.
    for li in list(m.statements.rows):
        m.statements.rows[li] = [None if v is None else v / 1000.0 for v in m.statements.rows[li]]
    html = build_html(m, str(tmp_path / "assets"))
    assert "No precedent transactions loaded." in html
    assert "USD mm" in html
    assert "None" not in html


# --- Full PDF render (skips only if weasyprint native libs unavailable) --
@pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint native libraries not importable in this environment",
)
def test_render_report_produces_pdf(tmp_path):
    from src.report import render_report

    out = str(tmp_path / "DECK_initiating_coverage.pdf")
    result = render_report(_bundle(), out, str(tmp_path / "assets"))
    import os

    assert result == out
    assert os.path.exists(out)
    assert os.path.getsize(out) > 10_000, "PDF should be a real multi-page document"
