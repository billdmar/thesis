"""Illustrative LBO engine.

Implements the ``LBOEngine`` protocol from ``src/interfaces.py``:

    run(statements, assumptions: LBOAssumptions, current_price) -> LBOResult

The flagship subject (Deckers, DECK) carries a **net-cash, zero-debt,
asset-light** balance sheet, so this is framed as an ILLUSTRATIVE exercise —
"what leverage *could* do to a clean-balance-sheet target." The full standard
LBO mechanics are built out; the entry simply introduces leverage that does not
exist on the real balance sheet today.

Sign & unit conventions are inherited from ``src/interfaces.py``:

* Values are raw USD magnitudes; shares are counts. No pre-scaling.
* Cash-flow-statement outflows are stored **negative** (capex). Interest
  expense is stored positive; we compute it explicitly here.

Mechanics
---------
**Entry.** Offer price per share = ``current_price * (1 + entry_premium)``.
Entry equity value = offer price * diluted shares (last historical
SHARES_DILUTED, falling back to SHARES_OUTSTANDING). Entry EBITDA = last
historical OPERATING_INCOME + D&A (DEP_AMORT, falling back to DA_CF). Entry
enterprise value:

* if ``entry_ev_ebitda`` is given:  EV = entry_ev_ebitda * entry EBITDA;
* else:                             EV = entry equity value + net debt.

Net debt = (SHORT_TERM_DEBT + LONG_TERM_DEBT) - (CASH + SHORT_TERM_INVESTMENTS)
off the last historical balance-sheet column (~0 for DECK).

**Sources & Uses.** Uses = the purchase enterprise value (which funds the
equity purchase plus refinancing of any existing net debt) + transaction fees.
``LBOAssumptions`` carries no fee field, so fees are an honest 0.0 (not
fabricated). Sources = new debt (``debt_pct_of_ev * EV``) + sponsor equity
(the plug). Sources equal Uses by construction; a test asserts it via
``LBOResult.sources_equal_uses()``.

**Debt schedule** (one row per hold year). For each year:

* ``begin``    = prior year's ending balance (year 1 = new debt raised).
* ``interest`` = ``debt_rate * begin`` (cash interest on the opening balance —
  the simplest hand-checkable convention). This is a REAL use of cash: it is
  subtracted from the sweep base below, not merely disclosed.
* ``fcf``      = the LEVERED free cash flow for the year (see below).
* ``sweep``    = ``cash_sweep_pct * fcf`` when levered FCF is positive, floored
  so debt never goes negative (``min(cash_sweep_pct * fcf, begin)``); a negative
  levered FCF sweeps nothing. No mandatory amortization (not in the contract).
* ``end``      = ``begin - sweep`` (>= 0).
* ``cash_balance`` = running balance of un-swept levered FCF (see Exit).

**FCF available for the sweep is LEVERED** — operating free cash flow after cash
interest::

    tax_t         = INCOME_TAX_EXPENSE_t / PRETAX_INCOME_t   (if both present and
                    PRETAX_INCOME_t > 0, else 0.0 — honest unknown, no fabrication)
    operating_fcf = OPERATING_INCOME_t * (1 - tax_t) + D&A_t - |CAPEX_t|
    levered_fcf   = operating_fcf - interest_t

Interest genuinely reduces the cash available to pay down debt. Levered FCF that
is not swept ACCUMULATES on the balance sheet (``cash_balance``); if levered FCF
is negative the balance falls, representing a real funding shortfall.

**Exit.** Exit EV = ``exit_ev_ebitda`` * final-projected-year EBITDA
(OPERATING_INCOME + D&A). Exit equity value = exit EV - remaining net debt,
where **remaining net debt = ending debt balance - accumulated cash_balance**
(a positive cash balance reduces net debt; a negative balance increases it — it
is not floored away). Cash accrues to exit rather than being distributed, so the
sponsor cash-flow vector stays single-in/single-out and IRR = MOIC^(1/n) - 1
holds exactly. Simplification (disclosed): accumulated cash earns no interest
while debt accrues it — a one-sided, downside-conservative treatment.

**Returns.** MOIC = exit equity value / sponsor equity. IRR is solved from the
sponsor cash-flow vector ``[-sponsor_equity, 0, ..., 0, +exit_equity_value]``
by bisection on NPV (a proper cash-flow IRR, extensible to interim dividends).
For this single-in / single-out case the solver's root equals the closed form
``MOIC**(1/hold_years) - 1`` to solver tolerance; a test asserts that invariant.
"""

from __future__ import annotations

from src.interfaces import LBOAssumptions, LBOResult, StatementSet
from src.schema import LineItem
from src.statements.helpers import at as _at
from src.statements.helpers import da_addback
from src.statements.helpers import net_debt as _net_debt
from src.statements.helpers import shares as _shares


def _irr(
    cashflows: list[float], lo: float = -0.999999, hi: float = 100.0, iters: int = 200
) -> float:
    """Internal rate of return of a dated cash-flow vector via bisection.

    ``cashflows[t]`` occurs at the end of period ``t`` (t = 0 is the initial
    outflow). Solves NPV(r) = sum_t cf_t / (1 + r)**t == 0. Requires a sign
    change across ``[lo, hi]`` (a conventional LBO — one outflow at t=0, an
    inflow at exit — brackets cleanly). Raises if the root cannot be bracketed.
    """

    def npv(rate: float) -> float:
        return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cashflows))

    f_lo = npv(lo)
    f_hi = npv(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if (f_lo > 0.0) == (f_hi > 0.0):
        raise ValueError(
            "IRR is not bracketed on the search interval; the sponsor cash-flow "
            "vector has no sign change (cannot solve for a real return)."
        )
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if f_mid == 0.0:
            return mid
        if (f_mid > 0.0) == (f_lo > 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return 0.5 * (lo + hi)


class LBOModelEngine:
    """Concrete ``LBOEngine``: entry, sources & uses, debt sweep, exit, returns."""

    def run(
        self, statements: StatementSet, assumptions: LBOAssumptions, current_price: float
    ) -> LBOResult:
        if current_price <= 0:
            raise ValueError(f"current_price must be > 0 (got {current_price}).")
        if assumptions.hold_years <= 0:
            raise ValueError(f"hold_years must be > 0 (got {assumptions.hold_years}).")
        if not 0.0 <= assumptions.debt_pct_of_ev <= 1.0:
            raise ValueError(
                f"debt_pct_of_ev must be in [0, 1] (got {assumptions.debt_pct_of_ev})."
            )
        if not 0.0 <= assumptions.cash_sweep_pct <= 1.0:
            raise ValueError(
                f"cash_sweep_pct must be in [0, 1] (got {assumptions.cash_sweep_pct})."
            )

        n_hist = statements.n_hist
        n_periods = len(statements.periods)
        last_hist = n_hist - 1
        if last_hist < 0:
            raise ValueError("statements has no historical period (n_hist == 0).")
        proj_idx = list(range(n_hist, n_periods))
        if len(proj_idx) < assumptions.hold_years:
            raise ValueError(
                f"need at least hold_years ({assumptions.hold_years}) projected periods; "
                f"only {len(proj_idx)} present."
            )

        # -- Entry --------------------------------------------------------
        shares = _shares(statements, last_hist)
        offer_price = current_price * (1.0 + assumptions.entry_premium)
        entry_equity_value = offer_price * shares

        entry_ebitda = self._ebitda(statements, last_hist)
        net_debt_entry = _net_debt(statements, last_hist)

        if assumptions.entry_ev_ebitda is not None:
            if entry_ebitda <= 0:
                raise ValueError(
                    "entry EBITDA is non-positive; cannot size EV from entry_ev_ebitda "
                    "(honest-unknown: not fabricated)."
                )
            entry_ev = assumptions.entry_ev_ebitda * entry_ebitda
        else:
            entry_ev = entry_equity_value + net_debt_entry
        if entry_ev <= 0:
            raise ValueError(f"entry enterprise value must be > 0 (got {entry_ev}).")

        # -- Sources & Uses ----------------------------------------------
        # No transaction-fee field in the frozen LBOAssumptions -> honest 0.0.
        transaction_fees = 0.0
        uses = {
            "purchase_enterprise_value": entry_ev,
            "transaction_fees": transaction_fees,
        }
        total_uses = sum(uses.values())

        new_debt = assumptions.debt_pct_of_ev * entry_ev
        sponsor_equity = total_uses - new_debt  # plug
        if sponsor_equity <= 0:
            raise ValueError(
                f"sponsor equity plug is non-positive (got {sponsor_equity}); leverage "
                "exceeds total uses."
            )
        sources = {"new_debt": new_debt, "sponsor_equity": sponsor_equity}

        # -- Debt schedule with a LEVERED cash sweep --------------------
        # The cash available to sweep is levered FCF — operating FCF AFTER cash
        # interest on the debt. Interest is a real use of cash, not decorative.
        # FCF not swept (the un-swept remainder) accumulates on the balance sheet
        # and is netted against debt at exit. Cash accrues to exit (no interim
        # distributions), so the single-in/single-out IRR == MOIC^(1/n)-1 holds.
        debt_schedule: list[dict[str, float]] = []
        begin = new_debt
        cash_balance = 0.0
        for year in range(1, assumptions.hold_years + 1):
            idx = n_hist + (year - 1)  # projected period for this hold year
            interest = assumptions.debt_rate * begin
            operating_fcf = self._unlevered_fcf(statements, idx)
            levered_fcf = operating_fcf - interest  # cash after debt service
            desired_sweep = assumptions.cash_sweep_pct * levered_fcf if levered_fcf > 0 else 0.0
            sweep = min(desired_sweep, begin)  # floor the debt balance at 0
            end = begin - sweep
            # Cash not used for the sweep builds on the balance sheet.
            cash_balance += levered_fcf - sweep
            debt_schedule.append(
                {
                    "begin": begin,
                    "interest": interest,
                    "fcf": levered_fcf,
                    "sweep": sweep,
                    "end": end,
                    "cash_balance": cash_balance,
                }
            )
            begin = end

        ending_debt = debt_schedule[-1]["end"]
        # Net debt at exit = ending LBO debt minus accumulated cash. We do NOT
        # floor accumulated cash at zero: if cash interest exceeds operating FCF
        # the balance goes negative (a real funding shortfall), and that deficit
        # correctly INCREASES net debt rather than being silently discarded.
        # (Simplification, disclosed: accumulated positive cash earns no interest
        # while the debt accrues it — a one-sided, conservative-on-the-downside
        # treatment for this illustrative model.)
        remaining_net_debt = ending_debt - cash_balance

        # -- Exit ---------------------------------------------------------
        exit_idx = n_hist + (assumptions.hold_years - 1)  # final held projected year
        exit_ebitda = self._ebitda(statements, exit_idx)
        exit_ev = assumptions.exit_ev_ebitda * exit_ebitda
        exit_equity_value = exit_ev - remaining_net_debt

        # -- Returns ------------------------------------------------------
        moic = exit_equity_value / sponsor_equity
        if exit_equity_value <= 0:
            raise ValueError(
                f"exit equity value is non-positive (got {exit_equity_value}); IRR is "
                "undefined for a total wipe-out in this illustrative model."
            )
        # Single-in / single-out sponsor cash-flow vector; no interim dividends.
        cashflows = [-sponsor_equity] + [0.0] * (assumptions.hold_years - 1) + [exit_equity_value]
        irr = _irr(cashflows)

        return LBOResult(
            sources=sources,
            uses=uses,
            debt_schedule=debt_schedule,
            exit_equity_value=exit_equity_value,
            irr=irr,
            moic=moic,
        )

    # -- statement helpers -----------------------------------------------
    @staticmethod
    def _ebitda(statements: StatementSet, idx: int) -> float:
        """EBITDA at column ``idx`` = OPERATING_INCOME + D&A.

        EBIT (OPERATING_INCOME) is required. D&A prefers DEP_AMORT, falls back
        to DA_CF, else 0.0 (a firm reporting no D&A add-back has none).
        """
        ebit = _at(statements.series(LineItem.OPERATING_INCOME), idx)
        if ebit is None:
            raise ValueError(
                f"OPERATING_INCOME (EBIT) missing at period index {idx}; cannot compute "
                "EBITDA (honest-unknown: not fabricated)."
            )
        return ebit + da_addback(statements, idx)

    @staticmethod
    def _unlevered_fcf(statements: StatementSet, idx: int) -> float:
        """Unlevered FCF for the sweep base: EBIT*(1-tax) + D&A - |capex|.

        Effective tax is derived per year from the projected statement
        (INCOME_TAX_EXPENSE / PRETAX_INCOME) when both are present and pretax is
        positive; otherwise 0.0 (honest unknown — no fabricated rate). D&A and
        capex follow the ``_ebitda`` / cash-flow-sign conventions.
        """
        ebit = _at(statements.series(LineItem.OPERATING_INCOME), idx)
        if ebit is None:
            raise ValueError(
                f"OPERATING_INCOME (EBIT) missing at projected index {idx}; cannot "
                "compute sweep FCF (honest-unknown: not fabricated)."
            )
        pretax = _at(statements.series(LineItem.PRETAX_INCOME), idx)
        tax_exp = _at(statements.series(LineItem.INCOME_TAX_EXPENSE), idx)
        if pretax is not None and pretax > 0 and tax_exp is not None:
            tax_rate = tax_exp / pretax
        else:
            tax_rate = 0.0

        da = da_addback(statements, idx)

        capex = _at(statements.series(LineItem.CAPEX), idx)
        capex_outflow = 0.0 if capex is None else abs(capex)

        return ebit * (1.0 - tax_rate) + da - capex_outflow
