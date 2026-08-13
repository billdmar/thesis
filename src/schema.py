"""Frozen data contract: the normalized shape of SEC XBRL facts.

Shared data contract — edit deliberately; everything builds against it. The
guiding ideas:

* **One canonical vocabulary.** Companies tag the same economic concept with
  different XBRL tags across filings and eras (e.g. ``Revenues`` vs
  ``RevenueFromContractWithCustomerExcludingAssessedTax``). The normalization
  layer maps every accepted tag to exactly one ``LineItem`` here.
  Downstream engines never see a raw XBRL tag — only ``LineItem``.

* **Provenance is mandatory.** Every value keeps a pointer back to the XBRL
  tag, unit, accession, and form it came from, so the XBRL tie-out gate can
  reconcile each historical statement line to the SEC-reported fact.

* **Restatements resolve to latest.** When multiple accessions report the same
  (LineItem, Period), the fact from the most recent accession wins; superseded
  facts are retained in ``superseded`` for auditability, never silently dropped.

* **Honest unknowns.** A concept the filer did not report is simply absent from
  the facts map. Engines must treat "missing" as missing (None) — never
  fabricate or interpolate a value to fill a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


# ---------------------------------------------------------------------------
# Canonical line items — the single vocabulary downstream engines consume.
# ---------------------------------------------------------------------------
class Statement(StrEnum):
    """Which financial statement a line item belongs to."""

    INCOME = "income_statement"
    BALANCE = "balance_sheet"
    CASHFLOW = "cash_flow_statement"


class LineItem(StrEnum):
    """Canonical financial-statement concepts.

    The value is a stable snake_case key used in serialized fixtures and as
    workbook row identifiers. Members are grouped by statement. This list is
    the contract: the EDGAR layer's tag-alias map must resolve to exactly these, and
    the statement builder builds statements from exactly these. Adding a member is an
    maintainer-owned contract change.
    """

    # --- Income statement ---
    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    SGA = "sga_expense"  # selling, general & administrative
    RND = "rnd_expense"  # research & development
    OTHER_OPERATING_EXPENSE = "other_operating_expense"
    OPERATING_INCOME = "operating_income"  # EBIT
    INTEREST_EXPENSE = "interest_expense"
    INTEREST_INCOME = "interest_income"
    OTHER_NONOPERATING = "other_nonoperating_income"
    PRETAX_INCOME = "pretax_income"
    INCOME_TAX_EXPENSE = "income_tax_expense"
    NET_INCOME = "net_income"
    DEP_AMORT = "depreciation_amortization"  # D&A (often disclosed on CF)
    EPS_BASIC = "eps_basic"
    EPS_DILUTED = "eps_diluted"
    SHARES_BASIC = "weighted_avg_shares_basic"
    SHARES_DILUTED = "weighted_avg_shares_diluted"

    # --- Balance sheet ---
    CASH = "cash_and_equivalents"
    SHORT_TERM_INVESTMENTS = "short_term_investments"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    INVENTORY = "inventory"
    OTHER_CURRENT_ASSETS = "other_current_assets"
    TOTAL_CURRENT_ASSETS = "total_current_assets"
    PPE_NET = "property_plant_equipment_net"
    GOODWILL = "goodwill"
    INTANGIBLES = "intangible_assets"
    OPERATING_LEASE_ROU = "operating_lease_right_of_use_asset"
    OTHER_NONCURRENT_ASSETS = "other_noncurrent_assets"
    TOTAL_ASSETS = "total_assets"
    ACCOUNTS_PAYABLE = "accounts_payable"
    ACCRUED_LIABILITIES = "accrued_liabilities"
    SHORT_TERM_DEBT = "short_term_debt"  # incl. current portion of LT debt
    CURRENT_OPERATING_LEASE = "operating_lease_liability_current"
    OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
    TOTAL_CURRENT_LIABILITIES = "total_current_liabilities"
    LONG_TERM_DEBT = "long_term_debt"
    NONCURRENT_OPERATING_LEASE = "operating_lease_liability_noncurrent"
    DEFERRED_TAX_LIABILITIES = "deferred_tax_liabilities"
    OTHER_NONCURRENT_LIABILITIES = "other_noncurrent_liabilities"
    TOTAL_LIABILITIES = "total_liabilities"
    COMMON_STOCK = "common_stock_and_apic"  # par + additional paid-in capital
    RETAINED_EARNINGS = "retained_earnings"
    TREASURY_STOCK = "treasury_stock"
    AOCI = "accumulated_other_comprehensive_income"
    TOTAL_EQUITY = "total_stockholders_equity"
    SHARES_OUTSTANDING = "common_shares_outstanding"  # period-end, for EV bridge

    # --- Cash flow statement ---
    CFO = "cash_from_operations"
    DA_CF = "depreciation_amortization_cf"  # D&A as shown on CF
    STOCK_COMP = "stock_based_compensation"
    CHANGE_IN_WC = "change_in_working_capital"
    CAPEX = "capital_expenditures"
    CFI = "cash_from_investing"
    DIVIDENDS_PAID = "dividends_paid"
    SHARE_REPURCHASES = "share_repurchases"
    DEBT_ISSUED = "debt_issued"
    DEBT_REPAID = "debt_repaid"
    CFF = "cash_from_financing"
    FX_EFFECT = "fx_effect_on_cash"
    NET_CHANGE_IN_CASH = "net_change_in_cash"


# Which statement each line item rolls up to (used by tie-out & workbook layout).
STATEMENT_OF: dict[LineItem, Statement] = {
    **dict.fromkeys(
        [
            LineItem.REVENUE,
            LineItem.COST_OF_REVENUE,
            LineItem.GROSS_PROFIT,
            LineItem.SGA,
            LineItem.RND,
            LineItem.OTHER_OPERATING_EXPENSE,
            LineItem.OPERATING_INCOME,
            LineItem.INTEREST_EXPENSE,
            LineItem.INTEREST_INCOME,
            LineItem.OTHER_NONOPERATING,
            LineItem.PRETAX_INCOME,
            LineItem.INCOME_TAX_EXPENSE,
            LineItem.NET_INCOME,
            LineItem.DEP_AMORT,
            LineItem.EPS_BASIC,
            LineItem.EPS_DILUTED,
            LineItem.SHARES_BASIC,
            LineItem.SHARES_DILUTED,
        ],
        Statement.INCOME,
    ),
    **dict.fromkeys(
        [
            LineItem.CASH,
            LineItem.SHORT_TERM_INVESTMENTS,
            LineItem.ACCOUNTS_RECEIVABLE,
            LineItem.INVENTORY,
            LineItem.OTHER_CURRENT_ASSETS,
            LineItem.TOTAL_CURRENT_ASSETS,
            LineItem.PPE_NET,
            LineItem.GOODWILL,
            LineItem.INTANGIBLES,
            LineItem.OPERATING_LEASE_ROU,
            LineItem.OTHER_NONCURRENT_ASSETS,
            LineItem.TOTAL_ASSETS,
            LineItem.ACCOUNTS_PAYABLE,
            LineItem.ACCRUED_LIABILITIES,
            LineItem.SHORT_TERM_DEBT,
            LineItem.CURRENT_OPERATING_LEASE,
            LineItem.OTHER_CURRENT_LIABILITIES,
            LineItem.TOTAL_CURRENT_LIABILITIES,
            LineItem.LONG_TERM_DEBT,
            LineItem.NONCURRENT_OPERATING_LEASE,
            LineItem.DEFERRED_TAX_LIABILITIES,
            LineItem.OTHER_NONCURRENT_LIABILITIES,
            LineItem.TOTAL_LIABILITIES,
            LineItem.COMMON_STOCK,
            LineItem.RETAINED_EARNINGS,
            LineItem.TREASURY_STOCK,
            LineItem.AOCI,
            LineItem.TOTAL_EQUITY,
            LineItem.SHARES_OUTSTANDING,
        ],
        Statement.BALANCE,
    ),
    **dict.fromkeys(
        [
            LineItem.CFO,
            LineItem.DA_CF,
            LineItem.STOCK_COMP,
            LineItem.CHANGE_IN_WC,
            LineItem.CAPEX,
            LineItem.CFI,
            LineItem.DIVIDENDS_PAID,
            LineItem.SHARE_REPURCHASES,
            LineItem.DEBT_ISSUED,
            LineItem.DEBT_REPAID,
            LineItem.CFF,
            LineItem.FX_EFFECT,
            LineItem.NET_CHANGE_IN_CASH,
        ],
        Statement.CASHFLOW,
    ),
}


# ---------------------------------------------------------------------------
# Periods & units
# ---------------------------------------------------------------------------
class PeriodType(StrEnum):
    """XBRL contexts are either a point-in-time (instant) or a span (duration)."""

    INSTANT = "instant"  # balance-sheet items: value AT end date
    DURATION = "duration"  # income/cash-flow items: value OVER [start, end]


class Unit(StrEnum):
    """Reporting unit for a fact. Normalization stores raw magnitudes (USD, not
    thousands/millions); the workbook applies display scaling."""

    USD = "USD"
    SHARES = "shares"
    USD_PER_SHARE = "USD/shares"
    PURE = "pure"  # ratios, counts (e.g. store counts if ever tagged)


@dataclass(frozen=True)
class Period:
    """A fiscal period. For INSTANT, ``start`` is None and ``end`` is the date.

    ``fy`` is the fiscal year and ``fp`` the fiscal period ("FY", "Q1".."Q4").
    Two periods are equal iff their (type, start, end) match — fy/fp are labels.
    """

    ptype: PeriodType
    end: date
    start: date | None = None
    fy: int | None = None
    fp: str | None = None

    def __post_init__(self) -> None:
        if self.ptype is PeriodType.DURATION and self.start is None:
            raise ValueError("DURATION period requires a start date")
        if self.ptype is PeriodType.INSTANT and self.start is not None:
            raise ValueError("INSTANT period must not have a start date")

    @property
    def key(self) -> tuple:
        """Identity used for de-duplication and dict keys."""
        return (self.ptype.value, self.start, self.end)


@dataclass(frozen=True)
class Provenance:
    """Where a normalized value came from, for the XBRL tie-out gate."""

    xbrl_tag: str  # the raw us-gaap/dei tag actually used
    taxonomy: str  # "us-gaap", "dei", etc.
    unit: Unit
    accession: str  # SEC accession no. (e.g. "0000910521-24-000012")
    form: str  # "10-K", "10-Q"
    filed: date  # filing date (for latest-accession resolution)
    frame: str | None = None  # XBRL frame if sourced via the frames API


@dataclass(frozen=True)
class Fact:
    """A single normalized datapoint: one LineItem, one Period, one value."""

    line_item: LineItem
    period: Period
    value: float
    provenance: Provenance
    # Facts from older accessions that were superseded by this one (restatements).
    superseded: tuple[Provenance, ...] = ()

    @property
    def key(self) -> tuple:
        return (self.line_item.value, self.period.key)


@dataclass
class CompanyMeta:
    """Identity of the filer."""

    cik: str  # zero-padded 10-digit CIK, e.g. "0000910521"
    ticker: str  # e.g. "DECK"
    name: str  # e.g. "Deckers Outdoor Corp"
    fiscal_year_end: str | None = None  # "MM-DD", e.g. "03-31"
    sic: str | None = None  # standard industrial classification code


@dataclass
class NormalizedFacts:
    """The output of the EDGAR layer and the input to every engine.

    ``facts`` is keyed by (LineItem, Period.key) -> Fact so lookups are O(1).
    Helper accessors keep engines from touching the raw dict shape.
    """

    company: CompanyMeta
    facts: dict[tuple, Fact] = field(default_factory=dict)

    def add(self, fact: Fact) -> None:
        """Insert a fact, resolving restatements to the latest accession.

        If a fact for the same (LineItem, Period) already exists, the one with
        the later filing date wins; the loser is recorded under ``superseded``.
        """
        existing = self.facts.get(fact.key)
        if existing is None:
            self.facts[fact.key] = fact
            return
        newer, older = (
            (fact, existing)
            if fact.provenance.filed >= existing.provenance.filed
            else (existing, fact)
        )
        merged_superseded = newer.superseded + older.superseded + (older.provenance,)
        self.facts[fact.key] = Fact(
            line_item=newer.line_item,
            period=newer.period,
            value=newer.value,
            provenance=newer.provenance,
            superseded=merged_superseded,
        )

    def get(self, line_item: LineItem, period: Period) -> Fact | None:
        return self.facts.get((line_item.value, period.key))

    def value(self, line_item: LineItem, period: Period) -> float | None:
        """Value or None. Honest-unknown contract: missing means missing."""
        f = self.facts.get((line_item.value, period.key))
        return f.value if f is not None else None

    def annual_periods(self) -> list[Period]:
        """Fiscal-year DURATION periods, sorted ascending by end date."""
        seen: dict[tuple, Period] = {}
        for f in self.facts.values():
            p = f.period
            if p.ptype is PeriodType.DURATION and p.fp == "FY":
                seen[p.key] = p
        return sorted(seen.values(), key=lambda p: p.end)

    def instant_periods(self) -> list[Period]:
        """Balance-sheet INSTANT periods (period-ends), sorted ascending."""
        seen: dict[tuple, Period] = {}
        for f in self.facts.values():
            if f.period.ptype is PeriodType.INSTANT:
                seen[f.period.key] = f.period
        return sorted(seen.values(), key=lambda p: p.end)
