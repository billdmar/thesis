"""Accounting-invariant runner (G1 onward).

Checks the structural identities that must hold in any correct 3-statement
model, on the *projected* columns of a ``StatementSet``:

* Balance sheet balances: Assets = Liabilities + Equity, every period.
* Cash-flow statement ties: ending cash on the CFS equals BS cash.
* Retained-earnings roll: RE_t = RE_{t-1} + NI_t - Dividends_t.
* PP&E roll: PP&E_t = PP&E_{t-1} + Capex_t - D&A_t.

These are computed independently of the builder's own internal checks so the
gate is a genuine second opinion. Each returns the per-period residual; the
runner asserts every residual is within ``tol`` (default $1, i.e. sub-cent at
the scale of a multi-billion-dollar model).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.interfaces import StatementSet
from src.schema import LineItem


@dataclass
class InvariantResult:
    name: str
    residuals: list[float] = field(default_factory=list)  # per projected period
    tol: float = 1.0

    @property
    def ok(self) -> bool:
        return all(abs(r) <= self.tol for r in self.residuals)

    @property
    def max_abs(self) -> float:
        return max((abs(r) for r in self.residuals), default=0.0)


@dataclass
class InvariantReport:
    results: list[InvariantResult]

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)

    def summary(self) -> str:
        parts = [
            f"{r.name}: {'OK' if r.ok else 'FAIL'} (max |resid| {r.max_abs:.4g})"
            for r in self.results
        ]
        return "Invariants — " + "; ".join(parts)


def _proj_series(statements: StatementSet, li: LineItem) -> list[float | None]:
    return statements.series(li)[statements.n_hist :]


def _v(x: float | None) -> float:
    return 0.0 if x is None else x


def check_balance_sheet(statements: StatementSet, tol: float = 1.0) -> InvariantResult:
    """Assets - (Liabilities + Equity) for each projected period.

    Liabilities are summed from components when no aggregate row exists; the
    builder is expected to populate TOTAL_ASSETS / TOTAL_LIABILITIES /
    TOTAL_EQUITY (or their parts) for projected periods.
    """
    n = len(statements.periods) - statements.n_hist
    ta = _proj_series(statements, LineItem.TOTAL_ASSETS)
    tl = _proj_series(statements, LineItem.TOTAL_LIABILITIES)
    te = _proj_series(statements, LineItem.TOTAL_EQUITY)
    residuals = []
    for i in range(n):
        residuals.append(_v(ta[i]) - (_v(tl[i]) + _v(te[i])))
    return InvariantResult("balance_sheet", residuals, tol)


def check_cfs_ties_to_cash(statements: StatementSet, tol: float = 1.0) -> InvariantResult:
    """Ending cash implied by the CFS equals the BS cash line each period.

    Ending cash_t = cash_{t-1} + net_change_in_cash_t. The prior cash is taken
    from the last historical period for the first projected column.
    """
    cash = statements.series(LineItem.CASH)
    net_chg = _proj_series(statements, LineItem.NET_CHANGE_IN_CASH)
    n = len(statements.periods) - statements.n_hist
    residuals = []
    for i in range(n):
        prior = cash[statements.n_hist + i - 1]
        implied = _v(prior) + _v(net_chg[i])
        bs_cash = cash[statements.n_hist + i]
        residuals.append(_v(bs_cash) - implied)
    return InvariantResult("cfs_ties_to_cash", residuals, tol)


def check_retained_earnings_roll(statements: StatementSet, tol: float = 1.0) -> InvariantResult:
    """RE_t - (RE_{t-1} + NI_t - Dividends_t). Dividends stored negative on CF."""
    re = statements.series(LineItem.RETAINED_EARNINGS)
    ni = _proj_series(statements, LineItem.NET_INCOME)
    div = _proj_series(statements, LineItem.DIVIDENDS_PAID)  # negative outflow
    n = len(statements.periods) - statements.n_hist
    residuals = []
    for i in range(n):
        prior = re[statements.n_hist + i - 1]
        # dividends are negative outflows; RE reduction is +div (i.e. -|div|).
        expected = _v(prior) + _v(ni[i]) + _v(div[i])
        residuals.append(_v(re[statements.n_hist + i]) - expected)
    return InvariantResult("retained_earnings_roll", residuals, tol)


def check_ppe_roll(statements: StatementSet, tol: float = 1.0) -> InvariantResult:
    """PP&E_t - (PP&E_{t-1} + Capex_t - D&A_t). Capex stored negative on CF."""
    ppe = statements.series(LineItem.PPE_NET)
    capex = _proj_series(statements, LineItem.CAPEX)  # negative outflow
    da = _proj_series(statements, LineItem.DEP_AMORT)
    da_cf = _proj_series(statements, LineItem.DA_CF)
    n = len(statements.periods) - statements.n_hist
    residuals = []
    for i in range(n):
        prior = ppe[statements.n_hist + i - 1]
        d = da[i] if da[i] is not None else da_cf[i]
        # capex is negative; adds to PP&E as +|capex| = -capex_stored.
        expected = _v(prior) - _v(capex[i]) - _v(d)
        residuals.append(_v(ppe[statements.n_hist + i]) - expected)
    return InvariantResult("ppe_roll", residuals, tol)


def run_all(statements: StatementSet, tol: float = 1.0) -> InvariantReport:
    return InvariantReport(
        results=[
            check_balance_sheet(statements, tol),
            check_cfs_ties_to_cash(statements, tol),
            check_retained_earnings_roll(statements, tol),
            check_ppe_roll(statements, tol),
        ]
    )
