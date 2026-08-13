"""the statement builder: historical assembly + fully-linked 5-year 3-statement projection.

Builds against the frozen contracts in ``src/schema.py`` and ``src/interfaces.py``.

Conventions (from ``src/interfaces.py``):
* Values are raw USD magnitudes; no display scaling here.
* Cash-flow outflows (capex, dividends, debt repaid) are stored NEGATIVE.
* Interest expense / income are stored POSITIVE; the model subtracts/adds them.
* ``COST_OF_REVENUE`` and operating expenses are stored positive; subtotals net.

Honest-unknown rule: a concept never provided stays ``None`` in the historical
rows. In the projection, lines the model does not drive (e.g. ``STOCK_COMP``,
``EPS_BASIC``) are left ``None`` rather than fabricated.

Linkage / revolver plug
-----------------------
Every projected balance-sheet line is either driven (revenue-linked, WC-days,
PP&E roll, RE roll) or held flat at its last-historical value. Interest expense
uses the *average* of prior- and current-year total debt and interest income the
*average* cash balance, which makes financing circular (debt/cash depend on net
income, which depends on interest). We resolve the loop by fixed-point iteration
per year. The revolver is the single flexing debt instrument: if projected cash
would fall below ``min_cash`` we draw the revolver; if there is excess cash we
repay outstanding revolver (down to zero). This keeps ``Assets = Liabilities +
Equity`` in every projected period by construction (see ``balance_check``).
"""

from __future__ import annotations

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from src.interfaces import ProjectionAssumptions, StatementSet
from src.schema import (
    STATEMENT_OF,
    LineItem,
    NormalizedFacts,
    Period,
    PeriodType,
    Statement,
)

# --- Balance-sheet component groupings (used for totals & the balance identity) ---
_CURRENT_ASSETS = [
    LineItem.CASH,
    LineItem.SHORT_TERM_INVESTMENTS,
    LineItem.ACCOUNTS_RECEIVABLE,
    LineItem.INVENTORY,
    LineItem.OTHER_CURRENT_ASSETS,
]
_NONCURRENT_ASSETS = [
    LineItem.PPE_NET,
    LineItem.GOODWILL,
    LineItem.INTANGIBLES,
    LineItem.OPERATING_LEASE_ROU,
    LineItem.OTHER_NONCURRENT_ASSETS,
]
_CURRENT_LIABILITIES = [
    LineItem.ACCOUNTS_PAYABLE,
    LineItem.ACCRUED_LIABILITIES,
    LineItem.SHORT_TERM_DEBT,
    LineItem.CURRENT_OPERATING_LEASE,
    LineItem.OTHER_CURRENT_LIABILITIES,
]
_NONCURRENT_LIABILITIES = [
    LineItem.LONG_TERM_DEBT,
    LineItem.NONCURRENT_OPERATING_LEASE,
    LineItem.DEFERRED_TAX_LIABILITIES,
    LineItem.OTHER_NONCURRENT_LIABILITIES,
]
_EQUITY = [
    LineItem.COMMON_STOCK,
    LineItem.RETAINED_EARNINGS,
    LineItem.TREASURY_STOCK,
    LineItem.AOCI,
]

_DAYS = 365.0
_MAX_ITERS = 200
_TOL = 1e-9


def _num(x: float | None) -> float:
    """Coerce an honest-unknown ``None`` to 0.0 for internal arithmetic."""
    return 0.0 if x is None else x


class ThreeStatementBuilder:
    """Concrete ``StatementBuilder`` (see ``src/interfaces.py``)."""

    # ------------------------------------------------------------------ #
    # Historical assembly
    # ------------------------------------------------------------------ #
    def build_historical(self, facts: NormalizedFacts) -> StatementSet:
        """Assemble annual historical statements from normalized facts.

        Columns are the fiscal-year DURATION periods. Income/cash-flow lines are
        read from the FY duration period; balance-sheet lines from the INSTANT
        period whose end date matches the fiscal-year end. Standard subtotals are
        derived only when their parts exist and the subtotal was not reported.
        """
        annual = facts.annual_periods()
        instant_by_end = {p.end: p for p in facts.instant_periods()}

        rows: dict[LineItem, list[float | None]] = {li: [] for li in LineItem}
        for p in annual:
            inst = instant_by_end.get(p.end)
            for li in LineItem:
                if STATEMENT_OF[li] is Statement.BALANCE:
                    val = facts.value(li, inst) if inst is not None else None
                else:
                    val = facts.value(li, p)
                rows[li].append(val)

        self._derive_historical_subtotals(rows, len(annual))
        return StatementSet(periods=list(annual), rows=rows, n_hist=len(annual))

    @staticmethod
    def _derive_historical_subtotals(rows: dict[LineItem, list[float | None]], n: int) -> None:
        """Fill standard subtotals when parts exist but the subtotal is missing.

        Kept deliberately narrow (gross profit only): deriving deeper subtotals
        would risk fabricating values where the filer disclosed something the
        simple arithmetic does not capture. Truly-missing items stay ``None``.
        """
        for i in range(n):
            rev = rows[LineItem.REVENUE][i]
            cogs = rows[LineItem.COST_OF_REVENUE][i]
            if rows[LineItem.GROSS_PROFIT][i] is None and rev is not None and cogs is not None:
                rows[LineItem.GROSS_PROFIT][i] = rev - cogs

    # ------------------------------------------------------------------ #
    # Projection
    # ------------------------------------------------------------------ #
    def project(self, hist: StatementSet, assumptions: ProjectionAssumptions) -> StatementSet:
        """Append ``assumptions.n_years`` fully-linked projected periods."""
        if hist.n_hist == 0:
            raise ValueError("cannot project without at least one historical period")

        a = assumptions
        n = a.n_years
        j = hist.n_hist - 1  # last historical column index

        def seed(li: LineItem) -> float:
            series = hist.rows.get(li, [None] * len(hist.periods))
            return _num(series[j])

        # --- seed balances carried forward ---
        rev_prev = seed(LineItem.REVENUE)
        cash_prev = seed(LineItem.CASH)
        ar_prev = seed(LineItem.ACCOUNTS_RECEIVABLE)
        inv_prev = seed(LineItem.INVENTORY)
        ap_prev = seed(LineItem.ACCOUNTS_PAYABLE)
        ppe_prev = seed(LineItem.PPE_NET)
        re_prev = seed(LineItem.RETAINED_EARNINGS)
        std_base = seed(LineItem.SHORT_TERM_DEBT)
        ltd_base = seed(LineItem.LONG_TERM_DEBT)

        # Flat balance-sheet items (everything not actively driven). Held at seed.
        flat = {
            li: seed(li)
            for li in (
                LineItem.SHORT_TERM_INVESTMENTS,
                LineItem.OTHER_CURRENT_ASSETS,
                LineItem.GOODWILL,
                LineItem.INTANGIBLES,
                LineItem.OPERATING_LEASE_ROU,
                LineItem.OTHER_NONCURRENT_ASSETS,
                LineItem.ACCRUED_LIABILITIES,
                LineItem.CURRENT_OPERATING_LEASE,
                LineItem.OTHER_CURRENT_LIABILITIES,
                LineItem.NONCURRENT_OPERATING_LEASE,
                LineItem.DEFERRED_TAX_LIABILITIES,
                LineItem.OTHER_NONCURRENT_LIABILITIES,
                LineItem.COMMON_STOCK,
                LineItem.TREASURY_STOCK,
                LineItem.AOCI,
                LineItem.SHARES_OUTSTANDING,
            )
        }

        # Balance the internal seed: absorb any historical component gap into the
        # catch-all OTHER_NONCURRENT_LIABILITIES so the projection starts square.
        # (Historical output rows are untouched; this is a projection seed only.)
        assets_seed = (
            cash_prev
            + ar_prev
            + inv_prev
            + ppe_prev
            + sum(flat[li] for li in (_CURRENT_ASSETS + _NONCURRENT_ASSETS) if li in flat)
        )
        liab_seed = (
            ap_prev
            + std_base
            + ltd_base
            + sum(flat[li] for li in (_CURRENT_LIABILITIES + _NONCURRENT_LIABILITIES) if li in flat)
        )
        equity_seed = re_prev + sum(flat[li] for li in _EQUITY if li in flat)
        flat[LineItem.OTHER_NONCURRENT_LIABILITIES] += assets_seed - (liab_seed + equity_seed)

        # --- projected output rows ---
        proj: dict[LineItem, list[float | None]] = {li: [None] * n for li in LineItem}
        periods: list[Period] = []

        revolver_prev = 0.0
        debt_prev = std_base + ltd_base  # total debt entering year 0
        prev_end = hist.periods[-1].end
        base_fy = hist.periods[-1].fy or prev_end.year

        for t in range(n):
            rev = rev_prev * (1.0 + a.revenue_growth[t])
            cogs = rev * (1.0 - a.gross_margin[t])
            gross_profit = rev - cogs
            sga = a.sga_pct_revenue[t] * rev
            rnd = a.rnd_pct_revenue[t] * rev
            ebit = gross_profit - sga - rnd
            da = a.da_pct_revenue[t] * rev
            capex_abs = a.capex_pct_revenue[t] * rev

            ar = a.dso[t] / _DAYS * rev
            inv = a.dio[t] / _DAYS * cogs
            ap = a.dpo[t] / _DAYS * cogs
            d_wc = (ar - ar_prev) + (inv - inv_prev) - (ap - ap_prev)

            tax_rate = a.tax_rate[t]
            payout = a.dividend_payout[t]

            # Fixed-point solve for the financing circularity (interest <-> debt/cash).
            revolver = revolver_prev
            cash = cash_prev
            state: dict[str, float] = {}
            for _ in range(_MAX_ITERS):
                total_debt = std_base + ltd_base + revolver
                int_exp = a.interest_rate_on_debt * (debt_prev + total_debt) / 2.0
                int_inc = a.interest_rate_on_cash * (cash_prev + cash) / 2.0
                pretax = ebit - int_exp + int_inc
                tax = tax_rate * pretax
                ni = pretax - tax
                div_abs = payout * max(ni, 0.0)
                cfo = ni + da - d_wc
                cfi = -capex_abs
                cash_before = cash_prev + cfo + cfi - div_abs
                gap = a.min_cash - cash_before
                if gap > 0.0:
                    d_revolver = gap  # draw to hold min cash
                else:
                    d_revolver = -min(revolver_prev, cash_before - a.min_cash)  # repay excess
                new_revolver = revolver_prev + d_revolver
                new_cash = cash_before + d_revolver
                converged = abs(new_revolver - revolver) < _TOL and abs(new_cash - cash) < _TOL
                revolver, cash = new_revolver, new_cash
                state = {
                    "int_exp": int_exp,
                    "int_inc": int_inc,
                    "pretax": pretax,
                    "tax": tax,
                    "ni": ni,
                    "div_abs": div_abs,
                    "cfo": cfo,
                    "cfi": cfi,
                    "d_revolver": d_revolver,
                }
                if converged:
                    break

            ni = state["ni"]
            div_abs = state["div_abs"]
            d_revolver = state["d_revolver"]
            debt_issued = max(d_revolver, 0.0)
            debt_repaid = min(d_revolver, 0.0)
            cff = -div_abs + debt_issued + debt_repaid
            net_change = state["cfo"] + state["cfi"] + cff

            ppe = ppe_prev + capex_abs - da
            re = re_prev + ni - div_abs
            std = std_base + revolver

            # --- income statement ---
            proj[LineItem.REVENUE][t] = rev
            proj[LineItem.COST_OF_REVENUE][t] = cogs
            proj[LineItem.GROSS_PROFIT][t] = gross_profit
            proj[LineItem.SGA][t] = sga
            proj[LineItem.RND][t] = rnd
            proj[LineItem.OPERATING_INCOME][t] = ebit
            proj[LineItem.INTEREST_EXPENSE][t] = state["int_exp"]
            proj[LineItem.INTEREST_INCOME][t] = state["int_inc"]
            proj[LineItem.PRETAX_INCOME][t] = state["pretax"]
            proj[LineItem.INCOME_TAX_EXPENSE][t] = state["tax"]
            proj[LineItem.NET_INCOME][t] = ni
            proj[LineItem.DEP_AMORT][t] = da

            # --- cash flow ---
            proj[LineItem.DA_CF][t] = da
            proj[LineItem.CHANGE_IN_WC][t] = -d_wc
            proj[LineItem.CFO][t] = state["cfo"]
            proj[LineItem.CAPEX][t] = -capex_abs
            proj[LineItem.CFI][t] = state["cfi"]
            proj[LineItem.DIVIDENDS_PAID][t] = -div_abs
            proj[LineItem.DEBT_ISSUED][t] = debt_issued
            proj[LineItem.DEBT_REPAID][t] = debt_repaid
            proj[LineItem.CFF][t] = cff
            proj[LineItem.NET_CHANGE_IN_CASH][t] = net_change

            # --- balance sheet ---
            proj[LineItem.CASH][t] = cash
            proj[LineItem.ACCOUNTS_RECEIVABLE][t] = ar
            proj[LineItem.INVENTORY][t] = inv
            proj[LineItem.PPE_NET][t] = ppe
            proj[LineItem.ACCOUNTS_PAYABLE][t] = ap
            proj[LineItem.SHORT_TERM_DEBT][t] = std
            proj[LineItem.LONG_TERM_DEBT][t] = ltd_base
            proj[LineItem.RETAINED_EARNINGS][t] = re
            for li, v in flat.items():
                proj[li][t] = v

            tca = (
                cash
                + flat[LineItem.SHORT_TERM_INVESTMENTS]
                + ar
                + inv
                + flat[LineItem.OTHER_CURRENT_ASSETS]
            )
            total_assets = (
                tca
                + ppe
                + sum(
                    flat[li]
                    for li in (
                        LineItem.GOODWILL,
                        LineItem.INTANGIBLES,
                        LineItem.OPERATING_LEASE_ROU,
                        LineItem.OTHER_NONCURRENT_ASSETS,
                    )
                )
            )
            tcl = (
                ap
                + flat[LineItem.ACCRUED_LIABILITIES]
                + std
                + flat[LineItem.CURRENT_OPERATING_LEASE]
                + flat[LineItem.OTHER_CURRENT_LIABILITIES]
            )
            total_liabilities = (
                tcl
                + ltd_base
                + sum(
                    flat[li]
                    for li in (
                        LineItem.NONCURRENT_OPERATING_LEASE,
                        LineItem.DEFERRED_TAX_LIABILITIES,
                        LineItem.OTHER_NONCURRENT_LIABILITIES,
                    )
                )
            )
            total_equity = (
                flat[LineItem.COMMON_STOCK]
                + re
                + flat[LineItem.TREASURY_STOCK]
                + flat[LineItem.AOCI]
            )
            proj[LineItem.TOTAL_CURRENT_ASSETS][t] = tca
            proj[LineItem.TOTAL_ASSETS][t] = total_assets
            proj[LineItem.TOTAL_CURRENT_LIABILITIES][t] = tcl
            proj[LineItem.TOTAL_LIABILITIES][t] = total_liabilities
            proj[LineItem.TOTAL_EQUITY][t] = total_equity

            # --- period header ---
            end = prev_end + relativedelta(years=1)
            periods.append(
                Period(
                    PeriodType.DURATION,
                    end=end,
                    start=prev_end + timedelta(days=1),
                    fy=base_fy + t + 1,
                    fp="FY",
                )
            )

            # roll forward
            rev_prev, cash_prev = rev, cash
            ar_prev, inv_prev, ap_prev = ar, inv, ap
            ppe_prev, re_prev = ppe, re
            revolver_prev = revolver
            debt_prev = std_base + ltd_base + revolver
            prev_end = end

        combined = {li: hist.rows.get(li, [None] * hist.n_hist) + proj[li] for li in LineItem}
        return StatementSet(
            periods=list(hist.periods) + periods,
            rows=combined,
            n_hist=hist.n_hist,
        )


def balance_check(stmts: StatementSet) -> list[float]:
    """Return ``TOTAL_ASSETS - (TOTAL_LIABILITIES + TOTAL_EQUITY)`` per period.

    Every projected period must be ~0 (within $1) — the headline invariant gate.
    Honest unknowns are treated as 0 for the arithmetic.
    """
    ta = stmts.series(LineItem.TOTAL_ASSETS)
    tl = stmts.series(LineItem.TOTAL_LIABILITIES)
    te = stmts.series(LineItem.TOTAL_EQUITY)
    return [_num(ta[i]) - (_num(tl[i]) + _num(te[i])) for i in range(len(stmts.periods))]
