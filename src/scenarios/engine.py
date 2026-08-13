"""Bull / base / bear scenario engine.

Runs the SAME statement builder + DCF engine over three assumption sets and
tabulates the implied share price for each. This is the standard institutional
"scenario table" — it makes the DCF's sensitivity to the core drivers explicit
and bounds the base case. Every number is engine-computed; only the assumption
sets differ.

The per-share bridge uses the same current-share-count override the flagship
applies, so scenario prices are directly comparable to the base-case headline.
"""

from __future__ import annotations

from dataclasses import replace

from src.interfaces import (
    ProjectionAssumptions,
    Scenario,
    ScenarioSet,
    StatementSet,
    TerminalAssumptions,
    WACCInputs,
)
from src.schema import LineItem, NormalizedFacts
from src.statements import ThreeStatementBuilder
from src.valuation import DCFValuationEngine


def _revenue_cagr(statements: StatementSet, n_hist: int) -> float:
    rev = statements.series(LineItem.REVENUE)
    base = rev[n_hist - 1]
    last = rev[-1]
    n = len(rev) - n_hist
    if not base or not last or n <= 0:
        return 0.0
    return (last / base) ** (1.0 / n) - 1.0


def run_scenario(
    name: str,
    facts: NormalizedFacts,
    assumptions: ProjectionAssumptions,
    wacc_inputs: WACCInputs,
    terminal: TerminalAssumptions,
    current_shares: float,
) -> Scenario:
    """Run one scenario end-to-end and return its headline outputs."""
    builder = ThreeStatementBuilder()
    hist = builder.build_historical(facts)
    proj = builder.project(hist, assumptions)
    dcf = DCFValuationEngine().dcf(proj, wacc_inputs, terminal)
    return Scenario(
        name=name,
        revenue_cagr=_revenue_cagr(proj, proj.n_hist),
        terminal_growth=terminal.terminal_growth,
        exit_ev_ebitda=terminal.exit_ev_ebitda,
        implied_price_gordon=dcf.equity_value_gordon / current_shares,
        implied_price_exit=dcf.equity_value_exit / current_shares,
    )


def build_scenarios(
    facts: NormalizedFacts,
    base_assumptions: ProjectionAssumptions,
    base_wacc: WACCInputs,
    base_terminal: TerminalAssumptions,
    current_shares: float,
    *,
    bull: dict | None = None,
    bear: dict | None = None,
) -> ScenarioSet:
    """Build the bull/base/bear set.

    ``bull``/``bear`` are override dicts with optional keys: ``growth_delta``
    (added to every revenue-growth year), ``gross_margin_delta`` (added to every
    gross-margin year), ``terminal_growth``, ``exit_ev_ebitda``. Defaults give a
    sensible symmetric spread when not provided.
    """
    # Clamp the bull terminal growth strictly below WACC — otherwise a subject
    # whose base g sits within ~50bp of WACC would push bull g >= WACC and trip
    # the Gordon g<WACC guard, raising and taking down the whole build.
    wacc = DCFValuationEngine().wacc(base_wacc)
    bull_g = min(base_terminal.terminal_growth + 0.005, wacc - 0.005)
    bull = bull or {
        "growth_delta": 0.03,
        "gross_margin_delta": 0.01,
        "terminal_growth": bull_g,
        "exit_ev_ebitda": base_terminal.exit_ev_ebitda + 2.0,
    }
    bear = bear or {
        "growth_delta": -0.03,
        "gross_margin_delta": -0.02,
        "terminal_growth": base_terminal.terminal_growth - 0.005,
        "exit_ev_ebitda": base_terminal.exit_ev_ebitda - 2.0,
    }

    def _apply(a: ProjectionAssumptions, ov: dict) -> ProjectionAssumptions:
        gd = ov.get("growth_delta", 0.0)
        md = ov.get("gross_margin_delta", 0.0)
        return replace(
            a,
            revenue_growth=[max(g + gd, -0.5) for g in a.revenue_growth],
            gross_margin=[min(max(m + md, 0.0), 0.95) for m in a.gross_margin],
        )

    def _term(ov: dict) -> TerminalAssumptions:
        return replace(
            base_terminal,
            terminal_growth=ov.get("terminal_growth", base_terminal.terminal_growth),
            exit_ev_ebitda=ov.get("exit_ev_ebitda", base_terminal.exit_ev_ebitda),
        )

    bear_s = run_scenario(
        "Bear", facts, _apply(base_assumptions, bear), base_wacc, _term(bear), current_shares
    )
    base_s = run_scenario("Base", facts, base_assumptions, base_wacc, base_terminal, current_shares)
    bull_s = run_scenario(
        "Bull", facts, _apply(base_assumptions, bull), base_wacc, _term(bull), current_shares
    )
    return ScenarioSet(scenarios=[bear_s, base_s, bull_s])
