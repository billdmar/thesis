"""XBRL tie-out gate (G1).

Reconciles every historical statement line in a built ``StatementSet`` back to
the SEC-reported fact it came from. This is the first integration gate: if the
statement builder or the normalization layer drifts, a historical value stops
matching the raw XBRL fact and this fails loudly.

The check is deliberately strict — historical values are *reported facts*, not
estimates, so they must match to the dollar (``tol=0.0`` by default, with a $1
allowance available for rounding-unit edge cases). Derived subtotals that the
filer did not itself report (e.g. a gross-profit line computed from revenue
minus cost of revenue) are reconciled against their components rather than a
raw tag, and are reported separately so they never mask a real mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.schema import STATEMENT_OF, LineItem, NormalizedFacts, Statement


@dataclass
class TieOutLine:
    line_item: LineItem
    fy: int | None
    statement_value: float
    fact_value: float | None
    xbrl_tag: str | None
    accession: str | None
    ok: bool
    note: str = ""


@dataclass
class TieOutReport:
    lines: list[TieOutLine]

    @property
    def checked(self) -> int:
        return len(self.lines)

    @property
    def mismatches(self) -> list[TieOutLine]:
        return [line for line in self.lines if not line.ok]

    @property
    def passed(self) -> bool:
        return not self.mismatches

    def summary(self) -> str:
        return (
            f"XBRL tie-out: {self.checked - len(self.mismatches)}/{self.checked} "
            f"historical lines reconcile to SEC facts"
            + ("" if self.passed else f" — {len(self.mismatches)} MISMATCH")
        )


def tie_out_historical(
    statements,
    facts: NormalizedFacts,
    *,
    tol: float = 0.0,
) -> TieOutReport:
    """Reconcile the historical columns of ``statements`` to ``facts``.

    For each (LineItem, historical period) with a non-None statement value,
    look up the matching normalized fact and assert equality within ``tol``.
    A statement value that has no corresponding fact is only a mismatch when it
    is NOT a legitimately-derived subtotal; derived subtotals are re-checked
    against their components.
    """
    lines: list[TieOutLine] = []
    hist_periods = statements.periods[: statements.n_hist]

    # Balance-sheet facts live under INSTANT periods, but statement columns are
    # the DURATION (annual) periods. Index instants by end date so a balance
    # line in a fiscal-year column resolves to the period-end instant fact.
    instant_by_end = {p.end: p for p in facts.instant_periods()}

    for li, series in statements.rows.items():
        is_balance = STATEMENT_OF.get(li) is Statement.BALANCE
        for idx, period in enumerate(hist_periods):
            sval = series[idx]
            if sval is None:
                continue
            if is_balance:
                inst = instant_by_end.get(period.end)
                fact = facts.get(li, inst) if inst is not None else None
            else:
                fact = facts.get(li, period)
            if fact is not None:
                ok = abs(sval - fact.value) <= tol
                lines.append(
                    TieOutLine(
                        line_item=li,
                        fy=period.fy,
                        statement_value=sval,
                        fact_value=fact.value,
                        xbrl_tag=fact.provenance.xbrl_tag,
                        accession=fact.provenance.accession,
                        ok=ok,
                        note="" if ok else "value != SEC fact",
                    )
                )
            else:
                # No raw fact. Accept only if it is a derived subtotal that
                # reconciles to its components; otherwise flag it.
                derived_ok, note = _reconcile_derived(li, statements, idx, tol)
                lines.append(
                    TieOutLine(
                        line_item=li,
                        fy=period.fy,
                        statement_value=sval,
                        fact_value=None,
                        xbrl_tag=None,
                        accession=None,
                        ok=derived_ok,
                        note=note,
                    )
                )
    return TieOutReport(lines=lines)


# Subtotals the builder may synthesize from components when the filer did not
# tag an aggregate. Maps the subtotal -> (positive components, negative components).
_DERIVED: dict[LineItem, tuple[list[LineItem], list[LineItem]]] = {
    LineItem.GROSS_PROFIT: ([LineItem.REVENUE], [LineItem.COST_OF_REVENUE]),
}


def _reconcile_derived(li: LineItem, statements, idx: int, tol: float) -> tuple[bool, str]:
    spec = _DERIVED.get(li)
    if spec is None:
        return False, "no SEC fact and not a recognized derived subtotal"
    pos, neg = spec
    total = statements.rows[li][idx]
    acc = 0.0
    for c in pos:
        v = statements.series(c)[idx]
        if v is None:
            return False, f"derived {li.value} missing component {c.value}"
        acc += v
    for c in neg:
        v = statements.series(c)[idx]
        if v is None:
            return False, f"derived {li.value} missing component {c.value}"
        acc -= v
    ok = abs(total - acc) <= max(tol, 1.0)
    return ok, "" if ok else f"derived {li.value} != components"


def balance_sheet_ties(facts: NormalizedFacts, *, tol: float = 1.0) -> list[tuple[int, float]]:
    """Independent BS identity check straight from normalized facts.

    For each instant period where the pieces exist, returns (year, residual)
    where residual = TotalAssets - (TotalLiabilities + TotalEquity). When the
    filer did not tag TotalLiabilities (common — e.g. DECK), it is inferred as
    TotalAssets - TotalEquity, so this degenerates to an equity/asset presence
    check for those filers rather than a false failure.
    """
    out: list[tuple[int, float]] = []
    for p in facts.instant_periods():
        ta = facts.value(LineItem.TOTAL_ASSETS, p)
        te = facts.value(LineItem.TOTAL_EQUITY, p)
        tl = facts.value(LineItem.TOTAL_LIABILITIES, p)
        if ta is None or te is None:
            continue
        if tl is None:
            tl = ta - te  # inferred; residual is 0 by construction
        out.append((p.end.year, ta - (tl + te)))
    return out
