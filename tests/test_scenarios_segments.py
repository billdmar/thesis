"""Tests for the scenario engine and segment loader (Phase 5 additions)."""

from __future__ import annotations

import pytest
from src.flagship import SOTP_EV_REVENUE, build_flagship
from src.segments import load_segments
from src.segments.sotp import compute_sotp


def test_scenarios_are_ordered_and_bracket_the_base(tmp_path):
    m = build_flagship()
    sc = m.scenarios
    assert sc is not None
    names = [s.name for s in sc.scenarios]
    assert names == ["Bear", "Base", "Bull"]
    bear, base, bull = sc.scenarios
    # Bull > Base > Bear on the implied midpoint (monotone by construction).
    assert bear.implied_price_mid < base.implied_price_mid < bull.implied_price_mid
    # Base scenario reproduces the flagship DCF midpoint.
    flagship_mid = (m.dcf.implied_price_gordon + m.dcf.implied_price_exit) / 2
    assert abs(base.implied_price_mid - flagship_mid) < 0.01


def test_scenario_drivers_differ():
    m = build_flagship()
    bear, base, bull = m.scenarios.scenarios
    assert bull.revenue_cagr > base.revenue_cagr > bear.revenue_cagr
    assert bull.exit_ev_ebitda > bear.exit_ev_ebitda


def test_segments_load_with_citations():
    m = build_flagship()
    seg = m.segments
    assert seg is not None
    names = {s.name for s in seg.segments}
    assert {"HOKA", "UGG"} <= names
    # HOKA grows over the window; every segment carries a source citation.
    hoka = next(s for s in seg.segments if s.name == "HOKA")
    revs = [y.revenue for y in hoka.years]
    assert revs == sorted(revs)  # monotonically increasing
    for s in seg.segments:
        assert s.source  # cited
    assert "10-K" in seg.source_note


def test_segment_totals_tie_to_reported_revenue():
    """Brand-level net sales must reconcile to the SEC-reported total revenue
    each year — the integrity anchor for the (curated) brand split."""
    from src.edgar import load_normalized_facts
    from src.schema import LineItem
    from src.statements import ThreeStatementBuilder

    m = build_flagship()
    nf = load_normalized_facts("DECK")
    hist = ThreeStatementBuilder().build_historical(nf)
    fy_to_rev = {
        p.fy: hist.series(LineItem.REVENUE)[i] for i, p in enumerate(hist.periods[: hist.n_hist])
    }
    by_year: dict[int, float] = {}
    for s in m.segments.segments:
        for y in s.years:
            by_year[y.fiscal_year] = by_year.get(y.fiscal_year, 0.0) + y.revenue
    for fy, brand_total in by_year.items():
        reported = fy_to_rev.get(fy)
        if reported is not None:
            assert abs(brand_total - reported) < 1.0, f"FY{fy}: {brand_total} != {reported}"


def test_segment_loader_handles_blank_operating_income(tmp_path):
    csv = tmp_path / "seg.csv"
    csv.write_text(
        "segment,fiscal_year,revenue,operating_income,source\n"
        "A,2024,100,,src-a\n"
        "A,2025,120,30,src-a\n"
    )
    ss = load_segments(str(csv))
    a = ss.segments[0]
    assert a.years[0].operating_income is None  # honest unknown
    assert a.years[1].operating_income == 30.0


# --- Loader guardrails: the CSV is a curated exception to the engine-only rule,
# so its "never fabricate a figure" validation must actually reject bad input. ---
def test_segment_loader_rejects_missing_required_column(tmp_path):
    csv = tmp_path / "seg.csv"
    csv.write_text("segment,fiscal_year,source\nA,2024,src-a\n")  # no 'revenue' column
    with pytest.raises(ValueError, match="missing required column"):
        load_segments(str(csv))


def test_segment_loader_rejects_blank_revenue(tmp_path):
    csv = tmp_path / "seg.csv"
    csv.write_text("segment,fiscal_year,revenue,source\nA,2024,,src-a\n")  # blank revenue
    with pytest.raises(ValueError, match="revenue is required"):
        load_segments(str(csv))


def test_segment_loader_rejects_non_numeric_revenue(tmp_path):
    csv = tmp_path / "seg.csv"
    csv.write_text("segment,fiscal_year,revenue,source\nA,2024,not-a-number,src-a\n")
    with pytest.raises(ValueError, match="row 2"):
        load_segments(str(csv))


def test_bear_case_is_meaningfully_below_spot():
    # The bear must be a genuine downside, not pinned to the current price.
    m = build_flagship()
    bear = next(s for s in m.scenarios.scenarios if s.name == "Bear")
    # At least ~10% below spot (calibrated to ~17%); guards against reverting to
    # the cosmetic symmetric bear that landed at spot.
    assert bear.implied_price_mid < m.current_price * 0.90


def test_sotp_reconciles_to_consolidated_dcf():
    # The sum-of-the-parts cross-check must land near the consolidated DCF Gordon
    # value (multiples are anchored to reconcile) — within ~15%.
    m = build_flagship()
    r = compute_sotp(m, SOTP_EV_REVENUE)
    assert r is not None
    assert r.implied_price is not None
    gordon = m.dcf.implied_price_gordon
    assert abs(r.implied_price - gordon) / gordon < 0.15
    # Net cash is added back (equity > EV for this net-cash name).
    assert r.equity_value > r.total_ev
