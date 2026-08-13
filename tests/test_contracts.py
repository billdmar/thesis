"""Contract-freeze guardrails.

These tests protect the W0-frozen contracts (src/schema.py, src/interfaces.py):
they fail loudly if a downstream change breaks a foundational invariant. They
also give CI something meaningful to run from the very first commit.
"""

from __future__ import annotations

from datetime import date

from src import interfaces as I  # noqa: N812
from src.schema import (
    STATEMENT_OF,
    CompanyMeta,
    Fact,
    LineItem,
    NormalizedFacts,
    Period,
    PeriodType,
    Provenance,
    Unit,
)


def test_every_line_item_is_classified_to_a_statement():
    unclassified = [li for li in LineItem if li not in STATEMENT_OF]
    assert not unclassified, f"LineItems missing from STATEMENT_OF: {unclassified}"


def test_period_validation():
    # DURATION requires a start.
    try:
        Period(PeriodType.DURATION, end=date(2024, 3, 31))
        raise AssertionError("expected ValueError for DURATION without start")
    except ValueError:
        pass
    # INSTANT must not have a start.
    try:
        Period(PeriodType.INSTANT, end=date(2024, 3, 31), start=date(2023, 4, 1))
        raise AssertionError("expected ValueError for INSTANT with start")
    except ValueError:
        pass


def _fy(end_year: int) -> Period:
    return Period(
        PeriodType.DURATION,
        end=date(end_year, 3, 31),
        start=date(end_year - 1, 4, 1),
        fy=end_year,
        fp="FY",
    )


def test_restatement_resolves_to_latest_accession():
    nf = NormalizedFacts(company=CompanyMeta(cik="0000910521", ticker="DECK", name="Deckers"))
    p = _fy(2024)
    old = Provenance("Revenues", "us-gaap", Unit.USD, "acc-2024", "10-K", date(2024, 5, 1))
    new = Provenance(
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap",
        Unit.USD,
        "acc-2025",
        "10-K",
        date(2025, 5, 1),
    )
    # Insert older first, then the restated (later) fact.
    nf.add(Fact(LineItem.REVENUE, p, 4000.0, old))
    nf.add(Fact(LineItem.REVENUE, p, 4288.0, new))
    got = nf.get(LineItem.REVENUE, p)
    assert got is not None
    assert got.value == 4288.0
    assert got.provenance.accession == "acc-2025"
    assert [s.accession for s in got.superseded] == ["acc-2024"]

    # Insertion order must not matter: latest filing always wins.
    nf2 = NormalizedFacts(company=CompanyMeta(cik="0000910521", ticker="DECK", name="Deckers"))
    nf2.add(Fact(LineItem.REVENUE, p, 4288.0, new))
    nf2.add(Fact(LineItem.REVENUE, p, 4000.0, old))
    assert nf2.value(LineItem.REVENUE, p) == 4288.0


def test_missing_value_is_honest_none():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    assert nf.value(LineItem.GOODWILL, _fy(2024)) is None


def test_period_helpers_sorted():
    nf = NormalizedFacts(company=CompanyMeta(cik="1", ticker="X", name="X"))
    prov = Provenance("Revenues", "us-gaap", Unit.USD, "a", "10-K", date(2024, 5, 1))
    for yr in (2022, 2024, 2023):
        nf.add(Fact(LineItem.REVENUE, _fy(yr), float(yr), prov))
    ends = [p.end.year for p in nf.annual_periods()]
    assert ends == [2022, 2023, 2024]


def test_lbo_sources_equal_uses_helper():
    r = I.LBOResult(
        sources={"debt": 60.0, "equity": 40.0},
        uses={"purchase_ev": 95.0, "fees": 5.0},
        debt_schedule=[],
        exit_equity_value=0.0,
        irr=0.0,
        moic=0.0,
    )
    assert r.sources_equal_uses()
    r.uses["fees"] = 5.5
    assert not r.sources_equal_uses()
