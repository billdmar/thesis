"""Normalization: raw SEC XBRL company-facts -> canonical ``NormalizedFacts``.

The heart of the EDGAR layer. Companies tag the same economic concept with different
XBRL tags across eras and filings (tag drift), and sometimes report *different*
concepts under tags that both plausibly map to one canonical line (e.g. a
``PrepaidExpenseCurrent`` sub-line vs the broader ``OtherAssetsCurrent``). We
resolve both problems with a **priority-ordered alias map**:

* ``ALIAS_MAP[LineItem]`` is a list of ``(taxonomy, tag)`` ordered best-first.
* For each fiscal period we take the value from the *highest-priority* tag that
  actually reported it. Lower-priority tags only fill periods the better tags
  never covered. This is what keeps two genuinely different concepts from being
  conflated by a naive latest-filing merge.
* Within the winning tag, restatements resolve to the latest accession via
  ``NormalizedFacts.add`` (older filings retained under ``superseded``).

Sign convention: values are stored EXACTLY as SEC reports them (raw magnitudes,
payments positive). The tie-out gate reconciles these to SEC-reported facts;
sign normalization for the model's cash-flow convention is the statement
builder's job, not ours. Honest-unknown: a concept the filer never reported is
simply absent from the result — never fabricated or interpolated.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from config.settings import FIXTURES_DIR

from src.schema import (
    STATEMENT_OF,
    CompanyMeta,
    Fact,
    LineItem,
    NormalizedFacts,
    Period,
    PeriodType,
    Provenance,
    Statement,
    Unit,
)

# ---------------------------------------------------------------------------
# Priority-ordered tag alias map.
# Built from the tags that actually appear in the DECK fixture, plus common
# peer aliases (Nike, Crocs, VFC, Wolverine, Steve Madden, Columbia, ...).
# Order matters: earlier = higher priority when tags overlap on a period.
# ---------------------------------------------------------------------------
ALIAS_MAP: dict[LineItem, list[tuple[str, str]]] = {
    # --- Income statement (DURATION) ---
    LineItem.REVENUE: [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "SalesRevenueGoodsNet"),
    ],
    LineItem.COST_OF_REVENUE: [
        ("us-gaap", "CostOfGoodsAndServicesSold"),
        ("us-gaap", "CostOfRevenue"),
        ("us-gaap", "CostOfGoodsSold"),
        ("us-gaap", "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"),
    ],
    LineItem.GROSS_PROFIT: [
        ("us-gaap", "GrossProfit"),
    ],
    LineItem.SGA: [
        ("us-gaap", "SellingGeneralAndAdministrativeExpense"),
        ("us-gaap", "SellingGeneralAndAdministrativeExpenses"),
        ("us-gaap", "GeneralAndAdministrativeExpense"),
    ],
    LineItem.RND: [
        ("us-gaap", "ResearchAndDevelopmentExpense"),
    ],
    LineItem.OTHER_OPERATING_EXPENSE: [
        ("us-gaap", "OtherOperatingIncomeExpenseNet"),
        ("us-gaap", "OtherCostAndExpenseOperating"),
    ],
    LineItem.OPERATING_INCOME: [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
    LineItem.INTEREST_EXPENSE: [
        ("us-gaap", "InterestExpense"),
        ("us-gaap", "InterestExpenseNonoperating"),
        ("us-gaap", "InterestAndDebtExpense"),
    ],
    LineItem.INTEREST_INCOME: [
        ("us-gaap", "InvestmentIncomeInterest"),
        ("us-gaap", "InterestIncomeOther"),
        ("us-gaap", "InterestAndDividendIncomeOperating"),
    ],
    LineItem.OTHER_NONOPERATING: [
        ("us-gaap", "OtherNonoperatingIncomeExpense"),
        ("us-gaap", "NonoperatingIncomeExpense"),
    ],
    LineItem.PRETAX_INCOME: [
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ),
    ],
    LineItem.INCOME_TAX_EXPENSE: [
        ("us-gaap", "IncomeTaxExpenseBenefit"),
    ],
    LineItem.NET_INCOME: [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
        ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"),
    ],
    LineItem.DEP_AMORT: [
        ("us-gaap", "DepreciationDepletionAndAmortization"),
        ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
        ("us-gaap", "DepreciationAndAmortization"),
        ("us-gaap", "Depreciation"),
    ],
    LineItem.EPS_BASIC: [
        ("us-gaap", "EarningsPerShareBasic"),
    ],
    LineItem.EPS_DILUTED: [
        ("us-gaap", "EarningsPerShareDiluted"),
    ],
    LineItem.SHARES_BASIC: [
        ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
    ],
    LineItem.SHARES_DILUTED: [
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
    ],
    # --- Balance sheet (INSTANT) ---
    LineItem.CASH: [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ("us-gaap", "Cash"),
    ],
    LineItem.SHORT_TERM_INVESTMENTS: [
        ("us-gaap", "ShortTermInvestments"),
    ],
    LineItem.ACCOUNTS_RECEIVABLE: [
        ("us-gaap", "AccountsReceivableNetCurrent"),
        ("us-gaap", "ReceivablesNetCurrent"),
    ],
    LineItem.INVENTORY: [
        ("us-gaap", "InventoryNet"),
    ],
    LineItem.OTHER_CURRENT_ASSETS: [
        ("us-gaap", "OtherAssetsCurrent"),
        ("us-gaap", "PrepaidExpenseAndOtherAssetsCurrent"),
        ("us-gaap", "PrepaidExpenseCurrent"),
    ],
    LineItem.TOTAL_CURRENT_ASSETS: [
        ("us-gaap", "AssetsCurrent"),
    ],
    LineItem.PPE_NET: [
        ("us-gaap", "PropertyPlantAndEquipmentNet"),
    ],
    LineItem.GOODWILL: [
        ("us-gaap", "Goodwill"),
    ],
    LineItem.INTANGIBLES: [
        ("us-gaap", "IntangibleAssetsNetExcludingGoodwill"),
        ("us-gaap", "FiniteLivedIntangibleAssetsNet"),
    ],
    LineItem.OPERATING_LEASE_ROU: [
        ("us-gaap", "OperatingLeaseRightOfUseAsset"),
    ],
    LineItem.OTHER_NONCURRENT_ASSETS: [
        ("us-gaap", "OtherAssetsNoncurrent"),
    ],
    LineItem.TOTAL_ASSETS: [
        ("us-gaap", "Assets"),
    ],
    LineItem.ACCOUNTS_PAYABLE: [
        ("us-gaap", "AccountsPayableTradeCurrent"),
        ("us-gaap", "AccountsPayableCurrent"),
    ],
    LineItem.ACCRUED_LIABILITIES: [
        ("us-gaap", "AccruedLiabilitiesCurrent"),
        ("us-gaap", "OtherAccruedLiabilitiesCurrent"),
        ("us-gaap", "EmployeeRelatedLiabilitiesCurrent"),
    ],
    LineItem.SHORT_TERM_DEBT: [
        ("us-gaap", "LongTermDebtCurrent"),
        ("us-gaap", "DebtCurrent"),
        ("us-gaap", "ShortTermBorrowings"),
        ("us-gaap", "LinesOfCreditCurrent"),
        ("us-gaap", "NotesPayableCurrent"),
    ],
    LineItem.CURRENT_OPERATING_LEASE: [
        ("us-gaap", "OperatingLeaseLiabilityCurrent"),
    ],
    LineItem.OTHER_CURRENT_LIABILITIES: [
        ("us-gaap", "OtherLiabilitiesCurrent"),
    ],
    LineItem.TOTAL_CURRENT_LIABILITIES: [
        ("us-gaap", "LiabilitiesCurrent"),
    ],
    LineItem.LONG_TERM_DEBT: [
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebt"),
        ("us-gaap", "LongTermNotesPayable"),
        ("us-gaap", "NotesPayable"),
    ],
    LineItem.NONCURRENT_OPERATING_LEASE: [
        ("us-gaap", "OperatingLeaseLiabilityNoncurrent"),
    ],
    LineItem.DEFERRED_TAX_LIABILITIES: [
        ("us-gaap", "DeferredIncomeTaxLiabilitiesNet"),
        ("us-gaap", "DeferredTaxLiabilitiesNoncurrent"),
        ("us-gaap", "DeferredIncomeTaxLiabilities"),
    ],
    LineItem.OTHER_NONCURRENT_LIABILITIES: [
        ("us-gaap", "OtherLiabilitiesNoncurrent"),
    ],
    LineItem.TOTAL_LIABILITIES: [
        ("us-gaap", "Liabilities"),
    ],
    # Par value (CommonStockValue) is immaterial for DECK (~$0.01 par) and is
    # a separate raw tag; provenance is single-tag, so we key this canonical
    # "par + APIC" line on the APIC tag. The statement builder folds in par if
    # a balance requires it.
    LineItem.COMMON_STOCK: [
        ("us-gaap", "AdditionalPaidInCapitalCommonStock"),
        ("us-gaap", "AdditionalPaidInCapital"),
        ("us-gaap", "CommonStockValue"),
    ],
    LineItem.RETAINED_EARNINGS: [
        ("us-gaap", "RetainedEarningsAccumulatedDeficit"),
    ],
    LineItem.TREASURY_STOCK: [
        ("us-gaap", "TreasuryStockValue"),
        ("us-gaap", "TreasuryStockCommonValue"),
    ],
    LineItem.AOCI: [
        ("us-gaap", "AccumulatedOtherComprehensiveIncomeLossNetOfTax"),
    ],
    LineItem.TOTAL_EQUITY: [
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ],
    LineItem.SHARES_OUTSTANDING: [
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ],
    # --- Cash flow statement (DURATION) ---
    LineItem.CFO: [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ],
    LineItem.DA_CF: [
        ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
        ("us-gaap", "DepreciationDepletionAndAmortization"),
        ("us-gaap", "DepreciationAndAmortization"),
        ("us-gaap", "Depreciation"),
    ],
    LineItem.STOCK_COMP: [
        ("us-gaap", "ShareBasedCompensation"),
        ("us-gaap", "AllocatedShareBasedCompensationExpense"),
    ],
    LineItem.CHANGE_IN_WC: [
        ("us-gaap", "IncreaseDecreaseInOperatingCapital"),
    ],
    LineItem.CAPEX: [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsToAcquireProductiveAssets"),
    ],
    LineItem.CFI: [
        ("us-gaap", "NetCashProvidedByUsedInInvestingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"),
    ],
    LineItem.DIVIDENDS_PAID: [
        ("us-gaap", "PaymentsOfDividendsCommonStock"),
        ("us-gaap", "PaymentsOfDividends"),
    ],
    LineItem.SHARE_REPURCHASES: [
        ("us-gaap", "PaymentsForRepurchaseOfCommonStock"),
        ("us-gaap", "PaymentsForRepurchaseOfEquity"),
    ],
    LineItem.DEBT_ISSUED: [
        ("us-gaap", "ProceedsFromIssuanceOfLongTermDebt"),
        ("us-gaap", "ProceedsFromIssuanceOfDebt"),
        ("us-gaap", "ProceedsFromShortTermDebt"),
    ],
    LineItem.DEBT_REPAID: [
        ("us-gaap", "RepaymentsOfLongTermDebt"),
        ("us-gaap", "RepaymentsOfDebt"),
        ("us-gaap", "RepaymentsOfShortTermDebt"),
    ],
    LineItem.CFF: [
        ("us-gaap", "NetCashProvidedByUsedInFinancingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"),
    ],
    LineItem.FX_EFFECT: [
        (
            "us-gaap",
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        ("us-gaap", "EffectOfExchangeRateOnCashAndCashEquivalents"),
        ("us-gaap", "EffectOfExchangeRateOnCashAndCashEquivalentsContinuingOperations"),
    ],
    LineItem.NET_CHANGE_IN_CASH: [
        (
            "us-gaap",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        ),
        ("us-gaap", "CashAndCashEquivalentsPeriodIncreaseDecrease"),
    ],
}

# Minimum / maximum day-span for a fact to count as a full fiscal year.
_MIN_ANNUAL_DAYS = 300
_MAX_ANNUAL_DAYS = 400

# Expected reporting unit per line item (drives which units bucket we read).
_SHARE_ITEMS = {LineItem.SHARES_BASIC, LineItem.SHARES_DILUTED, LineItem.SHARES_OUTSTANDING}
_PER_SHARE_ITEMS = {LineItem.EPS_BASIC, LineItem.EPS_DILUTED}

_UNIT_FOR_KEY = {
    "USD": Unit.USD,
    "shares": Unit.SHARES,
    "USD/shares": Unit.USD_PER_SHARE,
    "pure": Unit.PURE,
}


def _expected_unit_key(line_item: LineItem) -> str:
    if line_item in _SHARE_ITEMS:
        return "shares"
    if line_item in _PER_SHARE_ITEMS:
        return "USD/shares"
    return "USD"


def _is_annual_duration(pt: dict) -> bool:
    """True if a fact point is a full-fiscal-year (FY) 10-K duration."""
    if pt.get("fp") != "FY":
        return False
    if not str(pt.get("form", "")).startswith("10-K"):
        return False
    start = pt.get("start")
    end = pt.get("end")
    if not start or not end:
        return False
    span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return _MIN_ANNUAL_DAYS < span < _MAX_ANNUAL_DAYS


def _is_annual_instant(pt: dict) -> bool:
    """True if a fact point is a balance-sheet instant from a 10-K filing."""
    if "start" in pt and pt.get("start"):
        return False  # a duration, not an instant
    if not str(pt.get("form", "")).startswith("10-K"):
        return False
    return bool(pt.get("end"))


def _make_period(pt: dict, ptype: PeriodType) -> Period:
    # Fiscal-year label is derived from the period's OWN end date, not the raw
    # SEC `fy` attribute (which reflects the filing's fiscal-year focus and is
    # wrong for the period itself — it repeats across the 3 comparative years in
    # one 10-K). Banker convention: a fiscal year is named for the calendar year
    # in which it ENDS. This also correctly labels DECK's pre-2014 December-end
    # periods and its post-2014 March-end periods by their own end year.
    end = date.fromisoformat(pt["end"])
    if ptype is PeriodType.DURATION:
        return Period(
            PeriodType.DURATION,
            end=end,
            start=date.fromisoformat(pt["start"]),
            fy=end.year,
            fp="FY",
        )
    return Period(PeriodType.INSTANT, end=end, fy=end.year, fp=pt.get("fp"))


def _make_fact(line_item: LineItem, pt: dict, ptype: PeriodType, tax: str, tag: str) -> Fact:
    unit_key = _expected_unit_key(line_item)
    return Fact(
        line_item=line_item,
        period=_make_period(pt, ptype),
        value=float(pt["val"]),
        provenance=Provenance(
            xbrl_tag=tag,
            taxonomy=tax,
            unit=_UNIT_FOR_KEY[unit_key],
            accession=str(pt.get("accn", "")),
            form=str(pt.get("form", "")),
            filed=date.fromisoformat(pt["filed"]),
            frame=pt.get("frame"),
        ),
    )


def _ptype_for(line_item: LineItem) -> PeriodType:
    """Balance-sheet items are instants; income/cash-flow items are durations."""
    if STATEMENT_OF[line_item] is Statement.BALANCE:
        return PeriodType.INSTANT
    return PeriodType.DURATION


def _points_by_period(
    facts_by_tax: dict, tax: str, tag: str, ptype: PeriodType, unit_key: str
) -> dict[tuple, list[dict]]:
    """Return {period.key: [all accepted filings]} for one tag, annual-filtered.

    All filings for a period are kept (not pre-deduped) so the caller can feed
    every one to ``NormalizedFacts.add``, which builds the restatement trail
    (latest accession wins; older filings retained under ``superseded``).
    """
    taxonomy = facts_by_tax.get(tax)
    if not taxonomy or tag not in taxonomy:
        return {}
    units = taxonomy[tag].get("units", {})
    if unit_key not in units:
        return {}
    accept = _is_annual_duration if ptype is PeriodType.DURATION else _is_annual_instant
    by_period: dict[tuple, list[dict]] = {}
    for pt in units[unit_key]:
        if pt.get("val") is None or not accept(pt):
            continue
        key = _make_period(pt, ptype).key
        by_period.setdefault(key, []).append(pt)
    return by_period


def _normalize_line_item(
    nf: NormalizedFacts, facts_by_tax: dict, line_item: LineItem, tags: list[tuple[str, str]]
) -> None:
    """Populate one LineItem into ``nf`` using priority-ordered tag selection."""
    ptype = _ptype_for(line_item)
    unit_key = _expected_unit_key(line_item)

    # Per priority rank, all accepted filings for each period this tag covers.
    per_rank: list[dict[tuple, list[dict]]] = [
        _points_by_period(facts_by_tax, tax, tag, ptype, unit_key) for tax, tag in tags
    ]

    # For every period any tag covered, the winning tag is the lowest rank with data.
    all_period_keys: set[tuple] = set()
    for coverage in per_rank:
        all_period_keys.update(coverage.keys())

    for period_key in all_period_keys:
        for rank, (tax, tag) in enumerate(tags):
            if period_key in per_rank[rank]:
                # Feed every filing of the winning tag: add() resolves restatements
                # (latest accession wins) and keeps the superseded audit trail.
                for pt in per_rank[rank][period_key]:
                    nf.add(_make_fact(line_item, pt, ptype, tax, tag))
                break  # winning tag found; do not let lower-priority tags override


def load_normalized_facts(
    ticker: str, *, facts_dir: Path | str = FIXTURES_DIR / "raw"
) -> NormalizedFacts:
    """Read cached companyfacts JSON for ``ticker`` and normalize to canonical facts.

    Fully offline: reads only the committed fixture. Missing file -> clear error.
    """
    facts_dir = Path(facts_dir)
    matches = sorted(facts_dir.glob(f"companyfacts_{ticker.upper()}_*.json"))
    if not matches:
        raise FileNotFoundError(
            f"no cached companyfacts for {ticker!r} under {facts_dir} "
            f"(expected companyfacts_{ticker.upper()}_<CIK>.json)"
        )
    path = matches[0]
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    cik = str(raw.get("cik", "")).zfill(10)
    company = CompanyMeta(cik=cik, ticker=ticker.upper(), name=str(raw.get("entityName", "")))
    nf = NormalizedFacts(company=company)

    facts_by_tax = raw.get("facts", {})
    for line_item, tags in ALIAS_MAP.items():
        _normalize_line_item(nf, facts_by_tax, line_item, tags)
    return nf
