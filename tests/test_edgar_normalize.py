"""Offline tests for XBRL normalization against committed fixtures.

Covers: the alias map's shape, tag-drift resolution (two raw tags -> one
LineItem, latest accession wins), the DECK revenue tie-out series, balance-sheet
instant capture, and the honest-unknown contract.
"""

from __future__ import annotations

from datetime import date

import pytest
from src.edgar import ALIAS_MAP, load_normalized_facts
from src.edgar.normalize import _normalize_line_item
from src.schema import (
    CompanyMeta,
    LineItem,
    NormalizedFacts,
    Period,
    PeriodType,
)

# DECK fiscal-year-end revenue, as reported in the latest 10-K (SEC facts).
# FY here is labeled by the March-31 end date's year.
DECK_REVENUE_TIEOUT = {
    2021: 2_545_641_000.0,
    2022: 3_150_339_000.0,
    2023: 3_627_286_000.0,
    2024: 4_287_763_000.0,
    2025: 4_985_612_000.0,
    2026: 5_472_296_000.0,
}


# --- Alias map shape -------------------------------------------------------
def test_alias_map_covers_all_line_items():
    # Every canonical LineItem should have at least one candidate tag.
    missing = [li.name for li in LineItem if li not in ALIAS_MAP or not ALIAS_MAP[li]]
    assert not missing, f"LineItems with no alias candidates: {missing}"


def test_alias_map_entries_are_taxonomy_tag_pairs():
    for li, tags in ALIAS_MAP.items():
        for entry in tags:
            assert isinstance(entry, tuple) and len(entry) == 2, f"{li}: bad entry {entry}"
            tax, tag = entry
            assert tax in {"us-gaap", "dei", "srt"}, f"{li}: unexpected taxonomy {tax}"
            assert isinstance(tag, str) and tag


# --- DECK end-to-end -------------------------------------------------------
def test_load_deck_company_meta():
    nf = load_normalized_facts("DECK")
    assert nf.company.cik == "0000910521"
    assert nf.company.ticker == "DECK"
    assert "DECKERS" in nf.company.name.upper()


def test_deck_annual_revenue_series_and_monotonic():
    nf = load_normalized_facts("DECK")
    periods = nf.annual_periods()
    rev = [(p.end.year, nf.value(LineItem.REVENUE, p)) for p in periods]
    rev = [(y, v) for y, v in rev if v is not None]
    # >= 5 annual revenue periods.
    assert len(rev) >= 5
    # Recent fiscal years (FY2021-FY2026) tie out to the reported facts.
    by_year = dict(rev)
    for year, expected in DECK_REVENUE_TIEOUT.items():
        assert by_year[year] == expected, f"FY{year} revenue mismatch: {by_year.get(year)}"


def test_deck_latest_fy2026_revenue_exact():
    nf = load_normalized_facts("DECK")
    periods = nf.annual_periods()
    latest = periods[-1]
    assert latest.end == date(2026, 3, 31)
    assert nf.value(LineItem.REVENUE, latest) == 5_472_296_000.0


def test_deck_annual_fy_labels_are_strictly_increasing_and_end_year_based():
    # Fiscal-year label must be derived from each period's own end date, not the
    # raw SEC `fy` attribute (which repeats across a 10-K's comparative years).
    # Result: annual fy labels are unique, strictly increasing, and end at 2026.
    nf = load_normalized_facts("DECK")
    periods = nf.annual_periods()
    fys = [p.fy for p in periods]
    # Each fy label equals its period's end-year.
    assert all(p.fy == p.end.year for p in periods)
    # Strictly increasing => unique, no repeated fy across distinct years.
    assert fys == sorted(fys)
    assert len(fys) == len(set(fys)), f"duplicate fy labels: {fys}"
    assert fys[-1] == 2026
    # The three years that previously all carried fy=2026 are now distinct.
    by_end = {p.end: p.fy for p in periods}
    assert by_end[date(2024, 3, 31)] == 2024
    assert by_end[date(2025, 3, 31)] == 2025
    assert by_end[date(2026, 3, 31)] == 2026


def test_deck_fy2026_revenue_period_labeled_correctly():
    nf = load_normalized_facts("DECK")
    fy2026 = [p for p in nf.annual_periods() if p.fy == 2026]
    assert len(fy2026) == 1
    p = fy2026[0]
    assert p.end == date(2026, 3, 31)
    assert p.fp == "FY"
    assert nf.value(LineItem.REVENUE, p) == 5_472_296_000.0


def test_deck_revenue_broadly_increasing():
    # Deckers grew almost every year; require a strong majority of up-years
    # rather than strict monotonicity (FY2017 dipped from FY2016).
    nf = load_normalized_facts("DECK")
    vals = [
        nf.value(LineItem.REVENUE, p)
        for p in nf.annual_periods()
        if nf.value(LineItem.REVENUE, p) is not None
    ]
    up = sum(1 for a, b in zip(vals, vals[1:], strict=False) if b > a)
    assert up >= len(vals) - 2


def test_deck_balance_sheet_instants_present():
    nf = load_normalized_facts("DECK")
    fy26_bs = Period(PeriodType.INSTANT, end=date(2026, 3, 31))
    assert nf.value(LineItem.TOTAL_ASSETS, fy26_bs) == 3_687_765_000.0
    assert nf.value(LineItem.CASH, fy26_bs) is not None
    assert nf.value(LineItem.SHARES_OUTSTANDING, nf.instant_periods()[-1]) is not None


def test_deck_provenance_carries_tag_and_accession():
    nf = load_normalized_facts("DECK")
    latest = nf.annual_periods()[-1]
    fact = nf.get(LineItem.REVENUE, latest)
    assert fact is not None
    assert fact.provenance.taxonomy == "us-gaap"
    assert fact.provenance.xbrl_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert fact.provenance.accession  # non-empty accession
    assert fact.provenance.form.startswith("10-K")


def test_deck_shares_outstanding_from_dei():
    nf = load_normalized_facts("DECK")
    # dei is the highest-priority source for shares outstanding.
    latest_instant = nf.instant_periods()[-1]
    fact = nf.get(LineItem.SHARES_OUTSTANDING, latest_instant)
    assert fact is not None
    assert fact.provenance.taxonomy == "dei"


def test_honest_unknown_for_unreported_concept():
    # DECK reports no dividends and no treasury stock (it retires repurchases).
    # Honest-unknown contract: these must be absent (None), never fabricated.
    nf = load_normalized_facts("DECK")
    for p in nf.annual_periods():
        assert nf.value(LineItem.DIVIDENDS_PAID, p) is None
    for p in nf.instant_periods():
        assert nf.value(LineItem.TREASURY_STOCK, p) is None


# --- Tag-drift: two raw tags -> one LineItem, latest accession wins --------
def _fake_facts(points_by_tag: dict[str, list[dict]]) -> dict:
    return {"us-gaap": {tag: {"units": {"USD": pts}} for tag, pts in points_by_tag.items()}}


def test_tag_drift_across_periods_on_real_deck_cost_of_revenue():
    # Real DECK tag drift: cost of revenue is tagged `CostOfGoodsSold` in the
    # older filings and `CostOfGoodsAndServicesSold` from FY2017 on. Both map to
    # COST_OF_REVENUE, so a single continuous series must span both raw tags.
    nf = load_normalized_facts("DECK")
    by_year_tag = {}
    for p in nf.annual_periods():
        f = nf.get(LineItem.COST_OF_REVENUE, p)
        if f is not None:
            by_year_tag[p.end.year] = f.provenance.xbrl_tag
    # Early years use the legacy tag; recent years use the drifted tag.
    assert by_year_tag[2013] == "CostOfGoodsSold"
    assert by_year_tag[2026] == "CostOfGoodsAndServicesSold"
    # And the series is unbroken across the drift boundary.
    assert set(range(2018, 2027)).issubset(by_year_tag.keys())


def test_within_tag_restatement_latest_accession_wins():
    # Same tag, same period, two filings: the later-filed accession wins and the
    # superseded earlier filing is retained (restatement audit trail). This is
    # the `NormalizedFacts.add` contract, exercised through the normalizer.
    period = {"start": "2018-04-01", "end": "2019-03-31", "fp": "FY", "form": "10-K", "fy": 2019}
    old = {**period, "val": 1000.0, "accn": "acc-2019", "filed": "2019-05-30"}
    restated = {**period, "val": 1010.0, "accn": "acc-2020", "filed": "2020-05-30"}
    facts = _fake_facts({"CostOfGoodsAndServicesSold": [old, restated]})
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    _normalize_line_item(nf, facts, LineItem.COST_OF_REVENUE, ALIAS_MAP[LineItem.COST_OF_REVENUE])

    p = Period(PeriodType.DURATION, end=date(2019, 3, 31), start=date(2018, 4, 1), fy=2019, fp="FY")
    got = nf.get(LineItem.COST_OF_REVENUE, p)
    assert got is not None
    assert got.value == 1010.0
    assert got.provenance.accession == "acc-2020"
    assert any(s.accession == "acc-2019" for s in got.superseded)


def test_priority_does_not_conflate_disagreeing_tags():
    # Two tags map to OTHER_CURRENT_ASSETS but report DIFFERENT concepts/values
    # for the same period. Priority selection must take the higher-priority tag
    # only and never let the lower one overwrite it (no value blending).
    period_a = {
        "end": "2025-03-31",
        "fp": "FY",
        "form": "10-K",
        "fy": 2025,
    }
    high = {**period_a, "val": 67_282_000.0, "accn": "a", "filed": "2025-05-01"}
    low = {**period_a, "val": 39_294_000.0, "accn": "b", "filed": "2025-05-01"}
    facts = _fake_facts(
        {
            "OtherAssetsCurrent": [high],  # rank 0 for OTHER_CURRENT_ASSETS
            "PrepaidExpenseCurrent": [low],  # lower rank
        }
    )
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    _normalize_line_item(
        nf, facts, LineItem.OTHER_CURRENT_ASSETS, ALIAS_MAP[LineItem.OTHER_CURRENT_ASSETS]
    )
    p = Period(PeriodType.INSTANT, end=date(2025, 3, 31))
    got = nf.get(LineItem.OTHER_CURRENT_ASSETS, p)
    assert got is not None
    assert got.value == 67_282_000.0
    assert got.provenance.xbrl_tag == "OtherAssetsCurrent"


def test_lower_priority_tag_fills_uncovered_period():
    # When the top tag has no data for a period but a lower-priority tag does,
    # the lower tag fills that period (coverage), without clobbering periods the
    # top tag does cover.
    top_only = {
        "end": "2025-03-31",
        "fp": "FY",
        "form": "10-K",
        "fy": 2025,
        "val": 100.0,
        "accn": "a",
        "filed": "2025-05-01",
    }
    low_only = {
        "end": "2020-03-31",
        "fp": "FY",
        "form": "10-K",
        "fy": 2020,
        "val": 50.0,
        "accn": "b",
        "filed": "2020-05-01",
    }
    facts = _fake_facts(
        {
            "IntangibleAssetsNetExcludingGoodwill": [top_only],
            "FiniteLivedIntangibleAssetsNet": [low_only],
        }
    )
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    _normalize_line_item(nf, facts, LineItem.INTANGIBLES, ALIAS_MAP[LineItem.INTANGIBLES])
    assert (
        nf.value(LineItem.INTANGIBLES, Period(PeriodType.INSTANT, end=date(2025, 3, 31))) == 100.0
    )
    got_low = nf.get(LineItem.INTANGIBLES, Period(PeriodType.INSTANT, end=date(2020, 3, 31)))
    assert got_low is not None
    assert got_low.value == 50.0
    assert got_low.provenance.xbrl_tag == "FiniteLivedIntangibleAssetsNet"


# --- Peer smoke test -------------------------------------------------------
def test_peer_normalization_runs_and_ties_revenue_nonempty():
    # The alias map must also work on peers (Nike, Crocs). Just assert we get a
    # sane, non-empty annual revenue series — proves the map isn't DECK-only.
    for ticker in ("NKE", "CROX"):
        nf = load_normalized_facts(ticker)
        rev = [
            nf.value(LineItem.REVENUE, p)
            for p in nf.annual_periods()
            if nf.value(LineItem.REVENUE, p) is not None
        ]
        assert len(rev) >= 5, f"{ticker}: only {len(rev)} revenue periods"
        assert all(v > 0 for v in rev)


def test_missing_companyfacts_file_raises(tmp_path):
    # No cached fixture for the ticker -> loud, clear error (never a live call).
    with pytest.raises(FileNotFoundError):
        load_normalized_facts("ZZZZ", facts_dir=tmp_path)
