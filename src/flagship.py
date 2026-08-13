"""Flagship model builder (deterministic entry point).

Assembles the DECK ``ModelBundle`` deterministically from committed fixtures +
the analyst's judgment-core assumptions (documented in docs/ASSUMPTIONS.md) + the
as-of market data. This is the single source that produces the deliverable
workbook and feeds the verifier, so a full rebuild reproduces identical numbers
(determinism, the determinism requirement).

Market-data inputs are stamped as-of 2026-08-06 (owner-provided live quote).
Every projection value is an assumption, labeled as such in ASSUMPTIONS.md.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.comps import CompsEngine
from src.edgar import load_normalized_facts
from src.interfaces import (
    LBOAssumptions,
    ModelBundle,
    ProjectionAssumptions,
    TerminalAssumptions,
    WACCInputs,
)
from src.lbo import LBOModelEngine
from src.scenarios import build_scenarios
from src.segments import load_segments
from src.statements import ThreeStatementBuilder
from src.valuation import DCFValuationEngine

# --- As-of market data (owner-provided live quote, 2026-08-06 ~10:53 ET) ------
AS_OF = "2026-08-06"
CURRENT_PRICE = 99.68
# Current diluted shares implied by the $13.56B market cap (below the FY26
# reported 145.8M weighted-avg because of ongoing buybacks) — a documented
# "value per current share" choice.
CURRENT_SHARES = 136.2e6
MARKET_CAP = CURRENT_PRICE * CURRENT_SHARES

# Repo root (for the precedents CSV path).
ROOT = Path(__file__).resolve().parent.parent

# --- Peer set + as-of market data ---------------------------------------------
# Footwear/apparel comparables with committed CompanyFacts fixtures. Peer market
# data (price, shares) is external to SEC XBRL and stamped as-of 2026-08-06 —
# ILLUSTRATIVE approximate quotes for the comps triangulation; swap for live
# quotes before sharing. Used only for the comps EV/P-E cross-check, not the DCF.
PEER_TICKERS = ["NKE", "CROX", "WWW", "SHOO", "COLM", "VFC", "BOOT", "CAL"]
PEER_MARKET_DATA = {
    "NKE": {"price": 72.0, "shares": 1480e6},
    "CROX": {"price": 95.0, "shares": 57e6},
    "WWW": {"price": 18.0, "shares": 80e6},
    "SHOO": {"price": 30.0, "shares": 71e6},
    "COLM": {"price": 62.0, "shares": 56e6},
    "VFC": {"price": 14.0, "shares": 390e6},
    "BOOT": {"price": 165.0, "shares": 30e6},
    "CAL": {"price": 20.0, "shares": 34e6},
}

# --- Analyst 12-month call --------------------------------------------------------
RATING = "Buy"
PRICE_TARGET = 128.0  # ≈ the DCF midpoint (~$127; $118 Gordon / $136 exit), on the comps read

# Illustrative brand EV/revenue multiples for the HOKA/UGG sum-of-the-parts
# cross-check (report only; NOT the basis of the target). Anchored so the blended
# SOTP reconciles to the consolidated DCF EV (~$14B): HOKA carries a growth
# premium (still-compounding performance brand), UGG a mature-franchise multiple,
# Other a low residual. Brand EBITDA is not disclosed (honest unknown), so this
# is an EV/revenue cross-check on SOURCED brand net sales — analyst judgment,
# documented in docs/ASSUMPTIONS.md and tunable.
SOTP_EV_REVENUE: dict[str, float] = {"HOKA": 3.75, "UGG": 2.1, "Other": 1.0}


def base_assumptions() -> ProjectionAssumptions:
    """Balanced/defensible base case. Rationale: docs/ASSUMPTIONS.md."""
    return ProjectionAssumptions(
        n_years=5,
        revenue_growth=[0.09, 0.08, 0.07, 0.06, 0.05],
        gross_margin=[0.575, 0.575, 0.570, 0.570, 0.565],
        sga_pct_revenue=[0.345] * 5,
        rnd_pct_revenue=[0.0] * 5,  # DECK does not tag material R&D (in SG&A)
        dso=[40] * 5,
        dio=[110] * 5,
        dpo=[45] * 5,
        capex_pct_revenue=[0.016] * 5,
        da_pct_revenue=[0.018] * 5,
        tax_rate=[0.235] * 5,
        interest_rate_on_debt=0.0,  # net-cash, no debt
        interest_rate_on_cash=0.04,
        min_cash=400e6,
        dividend_payout=[0.0] * 5,  # DECK pays no dividend
    )


def wacc_inputs() -> WACCInputs:
    return WACCInputs(
        risk_free_rate=0.043,  # 10Y UST, as-of (owner to confirm exact level)
        beta=1.05,
        equity_risk_premium=0.05,
        pretax_cost_of_debt=0.06,  # illustrative (no debt outstanding)
        tax_rate=0.235,
        market_cap=MARKET_CAP,
        total_debt=0.0,
    )


def terminal_assumptions() -> TerminalAssumptions:
    return TerminalAssumptions(
        method="both",
        terminal_growth=0.03,  # < WACC (guard enforces)
        exit_ev_ebitda=11.0,  # modest re-rating from ~8.7x today
        mid_year_convention=True,
    )


def lbo_assumptions() -> LBOAssumptions:
    """Illustrative LBO on a net-cash target — 'what leverage could do'."""
    return LBOAssumptions(
        entry_premium=0.25,
        entry_ev_ebitda=None,  # derive from entry equity + (negative) net debt
        debt_pct_of_ev=0.50,
        debt_rate=0.07,
        cash_sweep_pct=0.75,
        exit_ev_ebitda=11.0,
        hold_years=5,
    )


def build_flagship() -> ModelBundle:
    """Build the full DECK ModelBundle. Deterministic."""
    nf = load_normalized_facts("DECK")
    builder = ThreeStatementBuilder()
    hist = builder.build_historical(nf)
    assumptions = base_assumptions()
    proj = builder.project(hist, assumptions)

    w = wacc_inputs()
    terminal = terminal_assumptions()
    dcf = DCFValuationEngine().dcf(proj, w, terminal)
    # Analyst override: value per CURRENT diluted share (as-of), not the FY26
    # reported weighted-avg. Documented in ASSUMPTIONS.md.
    dcf = replace(
        dcf,
        shares_diluted=CURRENT_SHARES,
        implied_price_gordon=dcf.equity_value_gordon / CURRENT_SHARES,
        implied_price_exit=dcf.equity_value_exit / CURRENT_SHARES,
    )

    # Load the peer set (committed fixtures) + as-of market data for each.
    peers = [load_normalized_facts(t) for t in PEER_TICKERS]
    market_data = {"DECK": {"price": CURRENT_PRICE, "shares": CURRENT_SHARES}, **PEER_MARKET_DATA}
    comps_engine = CompsEngine()
    comps = comps_engine.build_peer_multiples(nf, peers, market_data=market_data)
    precedents = comps_engine.load_precedents(str(ROOT / "data" / "precedents_footwear.csv"))

    lbo = LBOModelEngine().run(proj, lbo_assumptions(), CURRENT_PRICE)

    # Bull / base / bear scenarios (same engine, three assumption sets).
    # The bear is a GENUINE downside, not a symmetric nudge: it models the actual
    # thesis-breaking risk — HOKA momentum stalls and growth decelerates to a
    # ~2% CAGR, gross margin reverts ~3pts toward the FY22 low-50s as promotion
    # normalizes, and the multiple stays at a trough 8x. That lands the bear
    # meaningfully BELOW today's price (~$83 vs $99.68 spot), so the risk/reward
    # is asymmetric on a defensible bad case — not a bear conveniently pinned to
    # spot. Deltas are analyst judgment; see docs/ASSUMPTIONS.md (tunable).
    scenarios = build_scenarios(
        nf,
        assumptions,
        w,
        terminal,
        CURRENT_SHARES,
        bear={
            "growth_delta": -0.05,
            "gross_margin_delta": -0.03,
            "terminal_growth": 0.02,
            "exit_ev_ebitda": 8.0,
        },
    )

    # Segment (HOKA/UGG) detail — hand-sourced from the 10-K, cited.
    segments = load_segments(str(ROOT / "data" / "deck_segments.csv"))

    return ModelBundle(
        company=nf.company,
        statements=proj,
        proj_assumptions=assumptions,
        wacc_inputs=w,
        terminal=terminal,
        dcf=dcf,
        comps=comps,
        precedents=precedents,
        lbo=lbo,
        current_price=CURRENT_PRICE,
        price_target=PRICE_TARGET,
        rating=RATING,
        scenarios=scenarios,
        segments=segments,
    )
