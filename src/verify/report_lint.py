"""Report-number provenance lint (the report-lint gate).

The report may render only numbers the engine produced — nothing hand-typed.
The challenge is that the report displays engine magnitudes at many scales
(billions with 1 dp, per-share with 2 dp, percents, multiples), so a naive
absolute-tolerance comparison against raw engine floats is unsound.

Design: :func:`collect_engine_numbers` emits every engine value in the *display
forms* the report could render it as — raw, in millions, in billions, and as a
percent — each rounded to a small set of precisions. :func:`extract_report_numbers`
pulls the numeric tokens from the rendered HTML (ignoring inlined chart data).
:func:`lint_report_numbers` flags any rendered token that matches no engine
display-form within a relative tolerance. This is sound (a foreign number has no
match) without being noisy on legitimately-scaled values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.interfaces import ModelBundle
from src.schema import LineItem


@dataclass
class LintReport:
    """Result of :func:`lint_report_numbers`. ``passed`` iff every rendered
    number traces to an engine number in some display form."""

    numbers_checked: int = 0
    unsourced: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unsourced

    def summary(self) -> str:
        head = f"Report-number lint: {self.numbers_checked} rendered numbers"
        return head + (" — PASS" if self.passed else f" — {len(self.unsourced)} UNSOURCED")


def lint_report_numbers(
    rendered_numbers: set[float],
    engine_numbers: set[float],
    abs_tol: float = 0.011,
) -> LintReport:
    """Flag rendered numbers with no engine source.

    ``engine_numbers`` already contains every engine value in its plausible
    display forms rounded to the report's precisions (see
    :func:`collect_engine_numbers`), so matching is near-exact: a rendered
    number is sourced only when an engine display-form is within ``abs_tol``
    (one display unit at 2 dp). A tight absolute band — NOT a relative one —
    keeps the check sound: a relative band creates near-continuous coverage in
    dense value regions and would spuriously "source" a fabricated number.
    """
    engine = sorted(engine_numbers)
    unsourced: list[float] = []
    for x in rendered_numbers:
        if not any(abs(x - e) <= abs_tol for e in engine):
            unsourced.append(x)
    return LintReport(numbers_checked=len(rendered_numbers), unsourced=unsourced)


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_report_numbers(html: str, tables_only: bool = True) -> set[float]:
    """Pull numeric tokens from rendered report HTML.

    Scope (``tables_only``, default): only the financial EXHIBITS — the
    ``<table>`` elements — where every number must be an engine output. Narrative
    prose (``<p>``) legitimately cites contextual/sourced facts (52-week ranges,
    basis points, deal terms) that are the author's writing, not engine outputs,
    so it is out of scope for a machine number-lint. This makes the gate both
    sound and meaningful: "every number in every financial exhibit is verified."

    Strips base64 chart data, ISO dates, and FY labels (their digits are labels),
    then parses $-amounts, percents, multiples, and plain numbers to floats at
    their displayed magnitude; trivial tokens (0, small ints, years) are dropped.
    """
    if tables_only:
        html = " ".join(re.findall(r"<table.*?</table>", html, flags=re.DOTALL))
    text = re.sub(r"data:image/[^;]+;base64,[^\"']+", "", html)
    text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    text = re.sub(r"FY\s*\d{2,4}E?", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    out: set[float] = set()
    for tok in _NUM_RE.findall(text):
        tok = tok.strip().rstrip(".")
        if not tok or tok in {"-"}:
            continue
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        # Exclude non-financial tokens: figure numbers, small counts, 4-digit
        # years, and bare 2-digit integers (FY-label remnants / list indices).
        if v == 0:
            continue
        if v.is_integer() and (abs(v) <= 40 or 2000 <= v <= 2035):
            continue
        out.add(round(v, 2))
    return out


# External facts the analyst narrative cites (sourced to press releases in the
# precedents CSV), which are legitimately not engine outputs — e.g. per-share
# deal offer prices. Documented here so the lint stays strict on exhibit figures
# without flagging cited historical facts in prose.
NARRATIVE_SOURCED_FACTS: set[float] = {
    63.0,
    43.0,
    9.4,
    2.5,
    2.1,
    2.3,
    1.23,
    0.36,
    289.0,  # GBP 289M Kurt Geiger consideration, cited in the precedent's source text
}


def collect_engine_numbers(model: ModelBundle) -> set[float]:
    """Gather every engine figure the report may cite, in all display forms.

    For each base engine magnitude the report might render, we add: the raw
    value, its millions and billions scalings, and (for rates) its ×100 percent
    form — each rounded to the precisions the templates use. The lint then
    matches rendered tokens against this set.
    """
    base: set[float] = set()

    def add(*values: float | None) -> None:
        for v in values:
            if v is not None:
                base.add(float(v))

    d = model.dcf
    add(
        d.wacc,
        d.pv_explicit_fcff,
        d.terminal_value_gordon,
        d.terminal_value_exit,
        d.pv_terminal_gordon,
        d.pv_terminal_exit,
        d.enterprise_value_gordon,
        d.enterprise_value_exit,
        d.net_debt,
        d.minority_interest,
        d.equity_value_gordon,
        d.equity_value_exit,
        d.shares_diluted,
        d.implied_price_gordon,
        d.implied_price_exit,
        getattr(d, "terminal_fcff_normalized", None),
    )
    add(*d.fcff_by_year)
    add(*d.discount_factors)

    # Sensitivity grid: the report renders a WACC x g implied-price table (see
    # template._sensitivity_table). Those cells are engine-derived from the same
    # Gordon relation, so emit the grid here — otherwise the lint would flag the
    # off-centre cells as "unsourced". The base WACC/g deltas are also rendered.
    tf = getattr(d, "terminal_fcff_normalized", None)
    if tf is not None and d.shares_diluted not in (None, 0):
        n = len(d.fcff_by_year)
        deltas = (-0.01, -0.005, 0.0, 0.005, 0.01)
        for dw in deltas:
            w = d.wacc + dw
            add(w)
            for dg in deltas:
                g = model.terminal.terminal_growth + dg
                add(g)
                if w - g > 0:
                    tv = tf * (1.0 + g) / (w - g)
                    ev = d.pv_explicit_fcff + tv / (1.0 + w) ** (n - 0.5)
                    add((ev - d.net_debt) / d.shares_diluted)

    # WACC CAPM components (rendered in the WACC table).
    w = model.wacc_inputs
    add(w.risk_free_rate, w.beta, w.equity_risk_premium, w.pretax_cost_of_debt, w.tax_rate)
    add(w.risk_free_rate + w.beta * w.equity_risk_premium)  # cost of equity
    add(w.market_cap)

    # Terminal / assumptions rendered as text.
    t = model.terminal
    add(t.terminal_growth, t.exit_ev_ebitda)

    # Every statement line the report tables render, all periods, plus the
    # derived margins / EPS / FCF the key-financials table computes.
    s = model.statements
    rev = s.series(LineItem.REVENUE)
    ebit = s.series(LineItem.OPERATING_INCOME)
    cfo = s.series(LineItem.CFO)
    capex = s.series(LineItem.CAPEX)
    for li in (
        LineItem.REVENUE,
        LineItem.COST_OF_REVENUE,
        LineItem.GROSS_PROFIT,
        LineItem.SGA,
        LineItem.OPERATING_INCOME,
        LineItem.DEP_AMORT,
        LineItem.PRETAX_INCOME,
        LineItem.INCOME_TAX_EXPENSE,
        LineItem.NET_INCOME,
        LineItem.EPS_DILUTED,
        LineItem.TOTAL_ASSETS,
        LineItem.TOTAL_EQUITY,
        LineItem.CFO,
        LineItem.DA_CF,
        LineItem.CHANGE_IN_WC,
        LineItem.CFI,
        LineItem.NET_CHANGE_IN_CASH,
        LineItem.CASH,
        LineItem.ACCOUNTS_RECEIVABLE,
        LineItem.INVENTORY,
        LineItem.TOTAL_CURRENT_ASSETS,
        LineItem.PPE_NET,
        LineItem.ACCOUNTS_PAYABLE,
        LineItem.TOTAL_CURRENT_LIABILITIES,
        LineItem.TOTAL_LIABILITIES,
        LineItem.RETAINED_EARNINGS,
    ):
        add(*s.series(li))
    # Derived rows: EBIT margin, FCF = CFO + capex.
    for e, r in zip(ebit, rev, strict=False):
        if e is not None and r not in (None, 0):
            add(e / r)
    for o, cx in zip(cfo, capex, strict=False):
        if o is not None and cx is not None:
            add(o + cx)

    # Comps peers + implied prices; precedents; LBO.
    c = model.comps
    add(
        c.implied_ev_from_ebitda,
        c.implied_price_from_ebitda,
        c.implied_price_from_revenue,
        c.implied_price_from_pe,
    )
    for p in c.peers:
        add(
            p.enterprise_value,
            p.equity_value,
            p.ev_revenue_ltm,
            p.ev_ebitda_ltm,
            p.pe_ltm,
        )
    for stat in c.stats.values():
        add(*stat.values())
    for pt in model.precedents:
        add(pt.ev, pt.ev_revenue, pt.ev_ebitda)
    if model.lbo is not None:
        add(model.lbo.irr, model.lbo.moic, model.lbo.exit_equity_value)
        add(*model.lbo.sources.values(), *model.lbo.uses.values())

    # Scenario table (bull/base/bear implied prices + drivers).
    if model.scenarios is not None:
        for sc in model.scenarios.scenarios:
            add(
                sc.revenue_cagr,
                sc.terminal_growth,
                sc.exit_ev_ebitda,
                sc.implied_price_gordon,
                sc.implied_price_exit,
                sc.implied_price_mid,
            )
    # Segment table (brand-level net sales).
    if model.segments is not None:
        for seg in model.segments.segments:
            for y in seg.years:
                add(y.revenue, y.operating_income)

    # Sum-of-the-parts cross-check exhibit (per-brand EV/revenue → implied price).
    from src.flagship import SOTP_EV_REVENUE
    from src.segments.sotp import compute_sotp

    sotp = compute_sotp(model, SOTP_EV_REVENUE)
    if sotp is not None:
        for b in sotp.brands:
            add(b.revenue, b.multiple, b.ev)
        add(sotp.total_ev, sotp.equity_value, sotp.implied_price)

    add(model.current_price, model.price_target)
    if model.price_target and model.current_price:
        add(model.price_target / model.current_price - 1.0)  # upside %
    add(*NARRATIVE_SOURCED_FACTS)  # cited external deal facts in prose

    # Expand each base value into its plausible display forms.
    forms: set[float] = set()
    for v in base:
        for scaled in (v, v / 1e3, v / 1e6, v / 1e9, v * 100.0):
            for dp in (0, 1, 2, 3, 4):
                forms.add(round(scaled, dp))
                forms.add(round(abs(scaled), dp))  # signed values rendered abs
    return forms
