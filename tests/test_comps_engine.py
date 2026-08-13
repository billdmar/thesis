"""the comps engine tests: golden multiples, implied value, honest-None handling,
and precedent CSV parsing. All fixtures are synthetic NormalizedFacts built
in-test (no dependency on the EDGAR layer / src/edgar)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.comps import CompsEngine
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

_PROV = Provenance("synthetic", "us-gaap", Unit.USD, "acc-test", "10-K", date(2024, 5, 1))
_FY = Period(
    PeriodType.DURATION,
    end=date(2024, 3, 31),
    start=date(2023, 4, 1),
    fy=2024,
    fp="FY",
)
_INSTANT = Period(PeriodType.INSTANT, end=date(2024, 3, 31), fy=2024, fp="FY")


def _facts(ticker: str, **lines: float | None) -> NormalizedFacts:
    """Build synthetic NormalizedFacts. Each kwarg is a LineItem name -> value;
    the correct period (DURATION vs INSTANT) is chosen from the schema, so
    balance-sheet lines land on the instant period and flow lines on the FY."""
    nf = NormalizedFacts(company=CompanyMeta(cik="0", ticker=ticker, name=f"{ticker} Inc"))
    instant_items = {
        LineItem.CASH,
        LineItem.SHORT_TERM_INVESTMENTS,
        LineItem.SHORT_TERM_DEBT,
        LineItem.LONG_TERM_DEBT,
        LineItem.TOTAL_EQUITY,
        LineItem.SHARES_OUTSTANDING,
    }
    for name, val in lines.items():
        if val is None:
            continue
        li = LineItem[name]
        period = _INSTANT if li in instant_items else _FY
        nf.add(Fact(li, period, float(val), _PROV))
    return nf


def _peer(ticker: str, *, revenue, op_income, da, net_income, cash, lt_debt):
    return _facts(
        ticker,
        REVENUE=revenue,
        OPERATING_INCOME=op_income,
        DEP_AMORT=da,
        NET_INCOME=net_income,
        CASH=cash,
        LONG_TERM_DEBT=lt_debt,
    )


# ---------------------------------------------------------------------------
# Golden multiples: three peers with hand-computed EV, EV/Rev, EV/EBITDA, P/E.
# ---------------------------------------------------------------------------
def test_golden_multiples_and_stats():
    peers = [
        _peer("AAA", revenue=1000, op_income=200, da=50, net_income=100, cash=100, lt_debt=200),
        _peer("BBB", revenue=2000, op_income=300, da=100, net_income=150, cash=200, lt_debt=300),
        _peer("CCC", revenue=1500, op_income=250, da=50, net_income=120, cash=50, lt_debt=100),
    ]
    market = {
        "AAA": {"price": 10.0, "shares": 100.0},  # equity 1000
        "BBB": {"price": 20.0, "shares": 100.0},  # equity 2000
        "CCC": {"price": 15.0, "shares": 100.0},  # equity 1500
    }
    subject = _facts("SUB")  # empty subject: only peer stats under test here
    res = CompsEngine().build_peer_multiples(subject, peers, market_data=market)

    by = {p.ticker: p for p in res.peers}
    # EV = equity + total_debt - cash.  AAA: 1000+200-100 = 1100
    assert by["AAA"].enterprise_value == 1100
    assert by["AAA"].ev_revenue_ltm == 1100 / 1000
    assert by["AAA"].ev_ebitda_ltm == 1100 / 250  # EBITDA = 200 + 50
    assert by["AAA"].pe_ltm == 1000 / 100
    # BBB: 2000+300-200 = 2100
    assert by["BBB"].enterprise_value == 2100
    assert by["BBB"].ev_ebitda_ltm == 2100 / 400
    assert by["BBB"].pe_ltm == 2000 / 150
    # CCC: 1500+100-50 = 1550
    assert by["CCC"].enterprise_value == 1550
    assert by["CCC"].ev_ebitda_ltm == 1550 / 300

    ev_ebitda = sorted([1100 / 250, 2100 / 400, 1550 / 300])
    stats = res.stats["ev_ebitda_ltm"]
    assert stats["median"] == ev_ebitda[1]
    assert stats["mean"] == sum(ev_ebitda) / 3
    assert stats["min"] == ev_ebitda[0]
    assert stats["max"] == ev_ebitda[2]


# ---------------------------------------------------------------------------
# Implied value: peer median EV/EBITDA applied to the subject's own EBITDA.
# ---------------------------------------------------------------------------
def test_implied_price_from_median_ev_ebitda():
    # Two peers -> median = mean of the two multiples.
    # X: EV 1000 / EBITDA 200 = 5.0 ; Y: EV 1400 / EBITDA 200 = 7.0 ; median 6.0
    peers = [
        _peer("X", revenue=800, op_income=150, da=50, net_income=80, cash=0, lt_debt=0),
        _peer("Y", revenue=900, op_income=150, da=50, net_income=90, cash=0, lt_debt=0),
    ]
    market = {
        "X": {"price": 10.0, "shares": 100.0},  # equity 1000 -> EV 1000
        "Y": {"price": 14.0, "shares": 100.0},  # equity 1400 -> EV 1400
    }
    # Subject: EBITDA = 400 + 100 = 500 ; net_debt = 300 - 100 = 200 ; shares 100.
    subject = _facts(
        "SUB",
        REVENUE=1000,
        OPERATING_INCOME=400,
        DEP_AMORT=100,
        NET_INCOME=200,
        CASH=100,
        LONG_TERM_DEBT=300,
    )
    market["SUB"] = {"price": 25.0, "shares": 100.0}

    res = CompsEngine().build_peer_multiples(subject, peers, market_data=market)

    assert res.stats["ev_ebitda_ltm"]["median"] == 6.0
    # implied EV = 6 * 500 = 3000 ; implied equity = 3000 - 200 = 2800 ; /100 = 28
    assert res.implied_ev_from_ebitda == 3000
    assert res.implied_price_from_ebitda == 28.0


# ---------------------------------------------------------------------------
# Honest-None handling: a peer with no EBITDA is kept in the list but excluded
# from the EBITDA stats (still counted for EV/Revenue).
# ---------------------------------------------------------------------------
def test_missing_ebitda_excluded_from_stats_but_peer_kept():
    good = _peer("GOOD", revenue=1000, op_income=200, da=50, net_income=100, cash=0, lt_debt=0)
    # NODA reports no D&A at all -> EBITDA is an honest unknown.
    noda = _facts(
        "NODA",
        REVENUE=1000,
        OPERATING_INCOME=200,
        NET_INCOME=100,
        CASH=0,
        LONG_TERM_DEBT=0,
    )
    market = {"GOOD": {"price": 10.0, "shares": 100.0}, "NODA": {"price": 10.0, "shares": 100.0}}
    res = CompsEngine().build_peer_multiples(_facts("SUB"), [good, noda], market_data=market)

    tickers = {p.ticker for p in res.peers}
    assert tickers == {"GOOD", "NODA"}  # NODA still present
    noda_row = next(p for p in res.peers if p.ticker == "NODA")
    assert noda_row.ev_ebitda_ltm is None
    assert noda_row.ev_revenue_ltm is not None
    # Only GOOD contributes to the EBITDA stat.
    assert res.stats["ev_ebitda_ltm"]["median"] == 1000 / 250
    assert res.stats["ev_ebitda_ltm"]["min"] == res.stats["ev_ebitda_ltm"]["max"]
    # Both contribute to EV/Revenue.
    assert res.stats["ev_revenue_ltm"]["median"] == 1000 / 1000


# ---------------------------------------------------------------------------
# Book-equity fallback: no market_data -> equity from TOTAL_EQUITY, P/E is None.
# ---------------------------------------------------------------------------
def test_book_equity_fallback_and_pe_none():
    peer = _peer("BK", revenue=1000, op_income=200, da=50, net_income=100, cash=100, lt_debt=200)
    peer.add(Fact(LineItem.TOTAL_EQUITY, _INSTANT, 800.0, _PROV))
    res = CompsEngine().build_peer_multiples(_facts("SUB"), [peer])  # no market_data

    row = res.peers[0]
    assert row.equity_value == 800.0  # book equity
    assert row.enterprise_value == 800 + 200 - 100  # 900
    assert row.pe_ltm is None  # book "P/E" would mislead
    assert "pe_ltm" not in res.stats  # nothing to aggregate


def test_peer_without_equity_is_excluded():
    # No market data and no TOTAL_EQUITY -> cannot value -> dropped.
    peer = _peer("NONE", revenue=1000, op_income=200, da=50, net_income=100, cash=0, lt_debt=0)
    res = CompsEngine().build_peer_multiples(_facts("SUB"), [peer])
    assert res.peers == []


# ---------------------------------------------------------------------------
# Implied value from revenue and P/E medians.
# ---------------------------------------------------------------------------
def test_implied_price_from_revenue_and_pe():
    # Two identical peers so every median is exact.
    p = {"revenue": 1000, "op_income": 200, "da": 50, "net_income": 100, "cash": 0, "lt_debt": 0}
    peers = [_peer("P1", **p), _peer("P2", **p)]
    market = {"P1": {"price": 10.0, "shares": 100.0}, "P2": {"price": 10.0, "shares": 100.0}}
    # Each peer: EV 1000, revenue 1000 -> EV/Rev 1.0 ; equity 1000, NI 100 -> P/E 10.
    subject = _facts(
        "SUB",
        REVENUE=2000,
        OPERATING_INCOME=300,
        DEP_AMORT=100,
        NET_INCOME=200,
        CASH=50,
        LONG_TERM_DEBT=150,
    )
    market["SUB"] = {"price": 0.0, "shares": 100.0}
    res = CompsEngine().build_peer_multiples(subject, peers, market_data=market)

    # EV/Rev median 1.0 -> implied EV 2000 ; net_debt = 150-50 = 100 -> equity 1900 -> /100 = 19
    assert res.implied_price_from_revenue == 19.0
    # P/E median 10 -> implied equity 10*200 = 2000 -> /100 = 20
    assert res.implied_price_from_pe == 20.0


# ---------------------------------------------------------------------------
# Subject shares fall back to SHARES_OUTSTANDING when market shares absent.
# ---------------------------------------------------------------------------
def test_implied_uses_shares_outstanding_when_no_market_shares():
    peers = [
        _peer("X", revenue=800, op_income=150, da=50, net_income=80, cash=0, lt_debt=0),
        _peer("Y", revenue=900, op_income=150, da=50, net_income=90, cash=0, lt_debt=0),
    ]
    market = {"X": {"price": 10.0, "shares": 100.0}, "Y": {"price": 14.0, "shares": 100.0}}
    subject = _facts(
        "SUB",
        REVENUE=1000,
        OPERATING_INCOME=400,
        DEP_AMORT=100,
        NET_INCOME=200,
        CASH=100,
        LONG_TERM_DEBT=300,
        SHARES_OUTSTANDING=100,
    )
    # subject NOT in market_data -> shares come from SHARES_OUTSTANDING.
    res = CompsEngine().build_peer_multiples(subject, peers, market_data=market)
    assert res.implied_price_from_ebitda == 28.0


# ---------------------------------------------------------------------------
# Precedent CSV parsing: real curated file; every row carries a source.
# ---------------------------------------------------------------------------
def _precedents_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "data" / "precedents_footwear.csv")


def test_load_precedents_every_row_sourced():
    rows = CompsEngine().load_precedents(_precedents_path())
    assert len(rows) >= 5
    for r in rows:
        assert r.source.strip(), f"missing source for {r.acquirer}/{r.target}"
        assert r.acquirer and r.target and r.date
        assert r.ev > 0


def test_load_precedents_optional_fields_are_none_when_blank():
    rows = CompsEngine().load_precedents(_precedents_path())
    # The curated file leaves ev_revenue / ev_ebitda blank (announced EVs only).
    assert all(r.ev_revenue is None for r in rows)
    assert all(r.ev_ebitda is None for r in rows)


def test_load_precedents_parses_optional_floats(tmp_path):
    csv_file = tmp_path / "p.csv"
    csv_file.write_text(
        "date,acquirer,target,ev,ev_revenue,ev_ebitda,source\n"
        "2020-01-01,A,B,1000,2.5,,src-1\n"
        "2021-01-01,C,D,2000,,8.0,src-2\n",
        encoding="utf-8",
    )
    rows = CompsEngine().load_precedents(str(csv_file))
    assert rows[0].ev_revenue == 2.5
    assert rows[0].ev_ebitda is None
    assert rows[1].ev_revenue is None
    assert rows[1].ev_ebitda == 8.0
    assert rows[1].source == "src-2"
