"""FCFF DCF valuation engine.

Implements the ``ValuationEngine`` protocol from ``src/interfaces.py``:

* ``wacc`` — CAPM cost of equity + after-tax cost of debt, weighted by MARKET
  equity and BOOK debt (the WACC tab, WORKBOOK_SPEC.md §7).
* ``dcf`` — unlevered FCFF discounted at WACC, with BOTH terminal methods
  (Gordon growth and exit EV/EBITDA), the EV->equity bridge, and implied price
  per share (the DCF tab, WORKBOOK_SPEC.md §8).

Sign & unit conventions are inherited from ``src/interfaces.py``:

* Values are raw USD magnitudes; shares are counts. No pre-scaling.
* Cash-flow-statement outflows are stored **negative** (capex, and the cash
  effect of a working-capital build). Interest expense is stored positive.

FCFF formula (unlevered free cash flow to the firm), per projected year::

    FCFF = EBIT * (1 - tax) + D&A - |capex| + ΔWC_cf

  where
  * ``EBIT``      = OPERATING_INCOME for the year (required; missing -> error).
  * ``tax``       = ``wacc_inputs.tax_rate`` (single explicit rate; the flagship
                    per-year tax vector lives in ProjectionAssumptions and is
                    baked into the statements upstream — this engine uses one
                    documented marginal rate for the unlevered NOPAT term).
  * ``D&A``       = DEP_AMORT, falling back to DA_CF, else 0.0 (add-back).
  * ``|capex|``   = absolute magnitude of CAPEX. CAPEX is stored negative on the
                    cash-flow statement; we subtract its magnitude so the sign of
                    the source column cannot flip the result.
  * ``ΔWC_cf``    = CHANGE_IN_WC carried with its cash-flow-statement sign: a
                    working-capital build consumes cash and is stored negative,
                    so ADDING the signed value reduces FCFF. (Equivalently
                    FCFF = ... - ΔNWC where ΔNWC = -CHANGE_IN_WC_cf.)

Discounting uses the mid-year convention toggle: the year-``t`` discount factor
is ``1 / (1 + WACC) ** (t - 0.5)`` when ``mid_year_convention`` is True, else
``1 / (1 + WACC) ** t``. The terminal value is a lump sum at the end of the
explicit horizon and is discounted with the **final explicit year's** discount
factor (same factor applied to the last FCFF), so the mid-year toggle carries
through consistently.
"""

from __future__ import annotations

from src.interfaces import (
    DCFResult,
    StatementSet,
    TerminalAssumptions,
    WACCInputs,
)
from src.schema import LineItem
from src.statements.helpers import at as _at
from src.statements.helpers import da_addback
from src.statements.helpers import net_debt as _net_debt
from src.statements.helpers import shares as _shares


class DCFValuationEngine:
    """Concrete ``ValuationEngine``: WACC + FCFF DCF (both terminal methods)."""

    # Spread of the terminal return on new invested capital (RONIC) over WACC,
    # used to normalize the Gordon terminal FCFF via reinvestment = g / RONIC.
    # A modest positive spread reflects a mature-but-still-value-creating firm.
    RONIC_SPREAD = 0.03

    # -- WACC -------------------------------------------------------------
    def wacc(self, inputs: WACCInputs) -> float:
        """WACC = we*Ke + wd*Kd_at.

        Ke (CAPM) = rf + beta * ERP. Kd_at = pretax_cost_of_debt * (1 - tax).
        Weights use MARKET value of equity (``market_cap``) and BOOK value of
        debt (``total_debt``). A net-cash company (``total_debt == 0``) has no
        debt weight, so WACC collapses cleanly to Ke.
        """
        cost_of_equity = inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium

        if inputs.total_debt == 0:
            # Net-cash / all-equity capital structure: WACC == cost of equity.
            return cost_of_equity

        after_tax_cost_of_debt = inputs.pretax_cost_of_debt * (1.0 - inputs.tax_rate)
        capital = inputs.market_cap + inputs.total_debt
        if capital <= 0:
            raise ValueError(
                "WACC weights undefined: market_cap + total_debt must be > 0 "
                f"(got market_cap={inputs.market_cap}, total_debt={inputs.total_debt})"
            )
        weight_equity = inputs.market_cap / capital
        weight_debt = inputs.total_debt / capital
        return weight_equity * cost_of_equity + weight_debt * after_tax_cost_of_debt

    # -- DCF --------------------------------------------------------------
    def dcf(
        self,
        statements: StatementSet,
        wacc_inputs: WACCInputs,
        terminal: TerminalAssumptions,
    ) -> DCFResult:
        wacc = self.wacc(wacc_inputs)
        g = terminal.terminal_growth

        # Hard sanity contract: Gordon growth must be below the discount rate,
        # otherwise the perpetuity is undefined / negative.
        if g >= wacc:
            raise ValueError(
                f"terminal_growth ({g}) must be < WACC ({wacc}); Gordon perpetuity is "
                "undefined when g >= WACC (valuation sanity gate)."
            )

        n_hist = statements.n_hist
        n_periods = len(statements.periods)
        proj_idx = list(range(n_hist, n_periods))
        if not proj_idx:
            raise ValueError("no projected periods: statements.n_hist == len(periods)")

        tax = wacc_inputs.tax_rate

        ebit_series = statements.series(LineItem.OPERATING_INCOME)
        capex_series = statements.series(LineItem.CAPEX)
        wc_series = statements.series(LineItem.CHANGE_IN_WC)

        fcff_by_year: list[float] = []
        da_by_year: list[float] = []
        for idx in proj_idx:
            ebit = _at(ebit_series, idx)
            if ebit is None:
                raise ValueError(
                    f"OPERATING_INCOME (EBIT) missing for projected period index {idx}; "
                    "cannot compute FCFF (honest-unknown: not fabricated)."
                )
            # D&A add-back: prefer the income-statement tag, fall back to the CF tag.
            da = da_addback(statements, idx)
            capex = _at(capex_series, idx)
            capex_outflow = 0.0 if capex is None else abs(capex)
            wc_cf = _at(wc_series, idx)
            wc_cf = 0.0 if wc_cf is None else wc_cf

            fcff = ebit * (1.0 - tax) + da - capex_outflow + wc_cf
            fcff_by_year.append(fcff)
            da_by_year.append(da)

        # Discount factors, mid-year toggle. t is 1-indexed over projected years.
        discount_factors: list[float] = []
        for t in range(1, len(proj_idx) + 1):
            exponent = (t - 0.5) if terminal.mid_year_convention else float(t)
            discount_factors.append(1.0 / (1.0 + wacc) ** exponent)

        pv_explicit = sum(f * df for f, df in zip(fcff_by_year, discount_factors, strict=True))

        ebit_terminal = ebit_series[proj_idx[-1]]
        assert ebit_terminal is not None  # guaranteed non-None from FCFF loop
        da_terminal = da_by_year[-1]

        # --- Gordon perpetuity on a NORMALIZED terminal FCFF ---
        # The raw last-year FCFF is not a steady state: the base case runs capex
        # below D&A (so PP&E would shrink forever) and carries a lumpy year-T
        # working-capital build, both of which overstate a perpetual cash flow.
        # Normalized terminal FCFF via the textbook reinvestment-rate identity:
        #   terminal FCFF = NOPAT_T x (1 - reinvestment rate),
        #   reinvestment rate = g / RONIC
        # where RONIC (return on new invested capital) = WACC + a modest positive
        # spread. This is the standard steady-state normalization: a perpetuity
        # growing at g MUST reinvest g/RONIC of NOPAT, so terminal FCFF is a
        # disciplined fraction of NOPAT rather than the raw (over-stated) last
        # explicit-year FCFF. It is self-guarding: with 0 < g < RONIC the factor
        # is in (0,1), so the terminal value is always positive and finite.
        nopat_terminal = ebit_terminal * (1.0 - tax)
        ronic = wacc + self.RONIC_SPREAD
        reinvestment_rate = g / ronic if ronic > 0 else 0.0
        fcff_terminal_normalized = nopat_terminal * (1.0 - reinvestment_rate)
        df_terminal = discount_factors[-1]  # mid-year, matches the perpetuity stream

        terminal_value_gordon = fcff_terminal_normalized * (1.0 + g) / (wacc - g)
        pv_terminal_gordon = terminal_value_gordon * df_terminal

        # --- Exit multiple: a year-end SALE at year N, discounted FULL-year ---
        # An exit at N×EBITDA is a lump sum received at the end of year N, so it
        # must be discounted with the full-year factor (1+WACC)^-N, NOT the
        # mid-year factor used for the going-concern cash-flow stream.
        n_years = len(proj_idx)
        discount_factor_exit = 1.0 / (1.0 + wacc) ** n_years
        ebitda_terminal = ebit_terminal + da_terminal
        terminal_value_exit = ebitda_terminal * terminal.exit_ev_ebitda
        pv_terminal_exit = terminal_value_exit * discount_factor_exit

        enterprise_value_gordon = pv_explicit + pv_terminal_gordon
        enterprise_value_exit = pv_explicit + pv_terminal_exit

        # --- EV -> equity bridge, off the last HISTORICAL balance-sheet column. ---
        last_hist = n_hist - 1
        net_debt = _net_debt(statements, last_hist)
        # Minority interest is not a member of the frozen LineItem vocabulary
        # (src/schema.py), so there is nothing to subtract. Honest-unknown: 0.0,
        # not a fabricated figure. If the contract later adds the line, wire here.
        minority_interest = 0.0

        equity_value_gordon = enterprise_value_gordon - net_debt - minority_interest
        equity_value_exit = enterprise_value_exit - net_debt - minority_interest

        shares_diluted = _shares(statements, last_hist)
        implied_price_gordon = equity_value_gordon / shares_diluted
        implied_price_exit = equity_value_exit / shares_diluted

        return DCFResult(
            wacc=wacc,
            pv_explicit_fcff=pv_explicit,
            terminal_value_gordon=terminal_value_gordon,
            terminal_value_exit=terminal_value_exit,
            pv_terminal_gordon=pv_terminal_gordon,
            pv_terminal_exit=pv_terminal_exit,
            enterprise_value_gordon=enterprise_value_gordon,
            enterprise_value_exit=enterprise_value_exit,
            net_debt=net_debt,
            minority_interest=minority_interest,
            equity_value_gordon=equity_value_gordon,
            equity_value_exit=equity_value_exit,
            shares_diluted=shares_diluted,
            implied_price_gordon=implied_price_gordon,
            implied_price_exit=implied_price_exit,
            fcff_by_year=fcff_by_year,
            discount_factors=discount_factors,
            terminal_fcff_normalized=fcff_terminal_normalized,
            discount_factor_exit=discount_factor_exit,
        )
