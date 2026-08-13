"""Frozen engine-interface contract.

Shared data contract — edit deliberately; everything builds against it. These are
the typed boundaries between the engines: each codes to these signatures and
dataclasses without depending on another's implementation. Where a shape is an
input to one engine and an output of another, it lives here so there is one
definition.

Signs & conventions (contract — enforced by the audit + invariant gates):
* Values are in raw USD magnitudes (not thousands/millions). The workbook
  applies display scaling; the engine never pre-scales.
* Cash *outflows* on the cash-flow statement are negative (capex, dividends,
  repurchases, debt repaid). Inflows are positive.
* Interest expense is stored positive; the model subtracts it explicitly.
* Shares are share counts, not millions of shares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.schema import CompanyMeta, LineItem, NormalizedFacts, Period


# ===========================================================================
# Assumptions — the blue inputs. Set for the flagship model (the judgment core).
# ===========================================================================
@dataclass
class ProjectionAssumptions:
    """Drivers for the 5-year 3-statement projection.

    Every field is a per-projection-year sequence unless noted. Lists are
    length ``n_years``. Rationale for each flagship value lives in
    docs/ASSUMPTIONS.md (2-4 lines, sourced) — never hard-coded silently.
    """

    n_years: int = 5
    # Revenue: either explicit growth rates or a driver build handed in already.
    revenue_growth: list[float] = field(default_factory=list)  # e.g. [0.12, 0.10, ...]
    # Margins (as % of revenue) unless the name says otherwise.
    gross_margin: list[float] = field(default_factory=list)
    sga_pct_revenue: list[float] = field(default_factory=list)
    rnd_pct_revenue: list[float] = field(default_factory=list)
    # Working-capital drivers (days).
    dso: list[float] = field(default_factory=list)  # days sales outstanding
    dio: list[float] = field(default_factory=list)  # days inventory outstanding
    dpo: list[float] = field(default_factory=list)  # days payables outstanding
    # Capex & D&A.
    capex_pct_revenue: list[float] = field(default_factory=list)
    da_pct_revenue: list[float] = field(default_factory=list)
    # Tax & financing.
    tax_rate: list[float] = field(default_factory=list)
    interest_rate_on_debt: float = 0.0  # avg rate applied to average debt balance
    interest_rate_on_cash: float = 0.0  # yield on cash & ST investments
    min_cash: float = 0.0  # revolver plug maintains at least this cash balance
    dividend_payout: list[float] = field(default_factory=list)  # % of net income


@dataclass
class WACCInputs:
    """CAPM + capital-structure inputs for the discount rate."""

    risk_free_rate: float  # 10Y UST, sourced
    beta: float  # levered beta, with source note in ASSUMPTIONS.md
    equity_risk_premium: float
    pretax_cost_of_debt: float  # from filings (interest expense / avg debt) or rating
    tax_rate: float
    # Capital structure weights use MARKET value of equity, BOOK value of debt.
    market_cap: float
    total_debt: float


@dataclass
class TerminalAssumptions:
    """Terminal-value inputs. Both methods computed; report weights them."""

    method: str = "both"  # "gordon" | "exit_multiple" | "both"
    terminal_growth: float = 0.0  # Gordon g; contract: MUST be < WACC (sanity gate)
    exit_ev_ebitda: float = 0.0  # exit multiple on terminal-year EBITDA
    mid_year_convention: bool = True


# ===========================================================================
# Statement model — output of the statement builder, input to valuation/workbook.
# ===========================================================================
@dataclass
class StatementSet:
    """Historical + projected statements in one object.

    ``periods`` is the ordered list of column headers (historical then
    projected). ``rows`` maps each LineItem to a value-per-period list aligned
    to ``periods``; None entries are honest unknowns. ``n_hist`` marks the
    boundary: periods[:n_hist] are historical (tie out to XBRL), periods[n_hist:]
    are projected (driven by assumptions).
    """

    periods: list[Period]
    rows: dict[LineItem, list[float | None]]
    n_hist: int

    def series(self, li: LineItem) -> list[float | None]:
        return self.rows.get(li, [None] * len(self.periods))


class StatementBuilder(Protocol):
    """the statement builder. Builds historicals from facts, then projects forward."""

    def build_historical(self, facts: NormalizedFacts) -> StatementSet: ...

    def project(self, hist: StatementSet, assumptions: ProjectionAssumptions) -> StatementSet: ...


# ===========================================================================
# Valuation — the valuation engine.
# ===========================================================================
@dataclass
class DCFResult:
    wacc: float
    pv_explicit_fcff: float
    terminal_value_gordon: float
    terminal_value_exit: float
    pv_terminal_gordon: float
    pv_terminal_exit: float
    enterprise_value_gordon: float
    enterprise_value_exit: float
    # EV -> equity bridge
    net_debt: float
    minority_interest: float
    equity_value_gordon: float
    equity_value_exit: float
    shares_diluted: float
    implied_price_gordon: float
    implied_price_exit: float
    fcff_by_year: list[float] = field(default_factory=list)
    discount_factors: list[float] = field(default_factory=list)
    # Normalized steady-state terminal FCFF fed to the Gordon perpetuity (capex
    # set equal to D&A so PP&E doesn't shrink forever). Defaults 0.0 for
    # backward compatibility with hand-built fixtures.
    terminal_fcff_normalized: float = 0.0
    # Full-year discount factor (1+WACC)^-N used for the exit-multiple terminal
    # value (a year-end sale), distinct from the mid-year explicit-period factors.
    discount_factor_exit: float = 0.0


class ValuationEngine(Protocol):
    """the valuation engine. WACC + FCFF DCF with both terminal methods."""

    def wacc(self, inputs: WACCInputs) -> float: ...

    def dcf(
        self,
        statements: StatementSet,
        wacc_inputs: WACCInputs,
        terminal: TerminalAssumptions,
    ) -> DCFResult: ...


# ===========================================================================
# Comps & precedents — the comps engine.
# ===========================================================================
@dataclass
class PeerMultiples:
    ticker: str
    name: str
    enterprise_value: float
    equity_value: float
    ev_revenue_ltm: float | None
    ev_ebitda_ltm: float | None
    pe_ltm: float | None


@dataclass
class CompsResult:
    peers: list[PeerMultiples]
    # Summary stats across the peer set, per multiple.
    stats: dict[str, dict[str, float]]  # e.g. {"ev_ebitda_ltm": {"median":..,"mean":..}}
    # Implied value for the subject from applying peer medians to its metrics.
    implied_ev_from_ebitda: float | None = None
    implied_price_from_ebitda: float | None = None
    implied_price_from_revenue: float | None = None
    implied_price_from_pe: float | None = None


@dataclass
class PrecedentTransaction:
    date: str
    acquirer: str
    target: str
    ev: float
    ev_revenue: float | None
    ev_ebitda: float | None
    source: str  # citation — every precedent row is sourced


class CompsEngine(Protocol):
    """the comps engine."""

    def build_peer_multiples(
        self, subject: NormalizedFacts, peers: list[NormalizedFacts]
    ) -> CompsResult: ...

    def load_precedents(self, csv_path: str) -> list[PrecedentTransaction]: ...


# ===========================================================================
# LBO — the LBO engine .
# ===========================================================================
@dataclass
class LBOAssumptions:
    entry_premium: float  # premium over current price
    entry_ev_ebitda: float | None  # if None, derived from entry equity + net debt
    debt_pct_of_ev: float  # leverage at entry
    debt_rate: float
    cash_sweep_pct: float  # % of FCF sweeping to debt paydown
    exit_ev_ebitda: float
    hold_years: int = 5


@dataclass
class LBOResult:
    sources: dict[str, float]
    uses: dict[str, float]
    debt_schedule: list[dict[str, float]]  # per-year: begin, interest, sweep, end
    exit_equity_value: float
    irr: float
    moic: float

    def sources_equal_uses(self, tol: float = 0.01) -> bool:
        return abs(sum(self.sources.values()) - sum(self.uses.values())) <= tol


class LBOEngine(Protocol):
    """the LBO engine."""

    def run(
        self, statements: StatementSet, assumptions: LBOAssumptions, current_price: float
    ) -> LBOResult: ...


# ===========================================================================
# Workbook writer — the workbook writer. Emits LIVE formulas, never baked values.
# ===========================================================================
class WorkbookWriter(Protocol):
    """the workbook writer. Writes the .xlsx per docs/WORKBOOK_SPEC.md."""

    def write(self, path: str, model: ModelBundle) -> None: ...


# ===========================================================================
# Verification — the verifier . The moat.
# ===========================================================================
@dataclass
class CellDiff:
    sheet: str
    cell: str
    engine_value: float | None
    workbook_value: float | None
    ok: bool


@dataclass
class DifferentialReport:
    cells_checked: int
    mismatches: list[CellDiff]

    @property
    def passed(self) -> bool:
        return len(self.mismatches) == 0


class Verifier(Protocol):
    """the verifier. Recalculates the workbook and diffs it against the engine."""

    def recalc_and_diff(
        self, workbook_path: str, model: ModelBundle, tol: float = 0.01
    ) -> DifferentialReport: ...


# ===========================================================================
# The bundle passed to the workbook writer, report renderer, and verifier.
# ===========================================================================
@dataclass
class ModelBundle:
    """Everything the deliverables need, computed by the engines. Single source
    of truth: the workbook expresses these as formulas, the report renders
    them, the verifier diffs against them. Nothing here is ever hand-typed."""

    company: CompanyMeta
    statements: StatementSet
    proj_assumptions: ProjectionAssumptions
    wacc_inputs: WACCInputs
    terminal: TerminalAssumptions
    dcf: DCFResult
    comps: CompsResult
    precedents: list[PrecedentTransaction]
    lbo: LBOResult | None
    current_price: float
    price_target: float | None = None  # analyst-set, from method weighting
    rating: str | None = None  # analyst-set: Buy / Hold / Sell
    scenarios: ScenarioSet | None = None  # bull/base/bear (optional)
    segments: SegmentSet | None = None  # brand-level detail (optional, sourced)


# ===========================================================================
# Scenarios (bull / base / bear) — src/scenarios.
# ===========================================================================
@dataclass
class Scenario:
    """One scenario's headline outputs, from running the engine on its own
    assumption set."""

    name: str  # "Bull" | "Base" | "Bear"
    revenue_cagr: float
    terminal_growth: float
    exit_ev_ebitda: float
    implied_price_gordon: float
    implied_price_exit: float

    @property
    def implied_price_mid(self) -> float:
        return (self.implied_price_gordon + self.implied_price_exit) / 2.0


@dataclass
class ScenarioSet:
    scenarios: list[Scenario]  # ordered bear, base, bull (low → high)


# ===========================================================================
# Segment data (brand-level) — hand-sourced from the 10-K with citations.
# ===========================================================================
@dataclass
class SegmentYear:
    fiscal_year: int
    revenue: float
    operating_income: float | None = None


@dataclass
class Segment:
    name: str  # e.g. "HOKA", "UGG"
    years: list[SegmentYear]
    source: str  # citation (10-K segment footnote) — every figure is sourced


@dataclass
class SegmentSet:
    segments: list[Segment]
    source_note: str  # overall provenance statement (curated input, not XBRL)
