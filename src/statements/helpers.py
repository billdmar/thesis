"""Shared statement-series accessors used by the valuation and LBO engines.

These four helpers were duplicated character-for-character across
``src.valuation`` and ``src.lbo``; consolidating them keeps one definition of the
net-debt / share-count / D&A-add-back conventions (and their honest-unknown
handling) so the two engines can't drift apart. The comps engine reads from
``NormalizedFacts`` (a different source shape), so it keeps its own accessor.
"""

from __future__ import annotations

from src.interfaces import StatementSet
from src.schema import LineItem


def at(series: list[float | None], idx: int) -> float | None:
    """Value at ``idx`` in a period-aligned series, or None if out of range."""
    if idx < 0 or idx >= len(series):
        return None
    return series[idx]


def da_addback(statements: StatementSet, idx: int) -> float:
    """D&A at column ``idx``: prefer the income-statement tag (DEP_AMORT), fall
    back to the cash-flow tag (DA_CF); a line the filer did not report is treated
    as 0.0 (modeling default, not a fabricated figure)."""
    da = at(statements.series(LineItem.DEP_AMORT), idx)
    if da is None:
        da = at(statements.series(LineItem.DA_CF), idx)
    return 0.0 if da is None else da


def net_debt(statements: StatementSet, idx: int) -> float:
    """Net debt at balance-sheet column ``idx``:
    (SHORT_TERM_DEBT + LONG_TERM_DEBT) - (CASH + SHORT_TERM_INVESTMENTS).
    A line the filer did not report is treated as 0.0 (modeling default,
    not a fabricated figure)."""

    def v(li: LineItem) -> float:
        got = at(statements.series(li), idx)
        return 0.0 if got is None else got

    debt = v(LineItem.SHORT_TERM_DEBT) + v(LineItem.LONG_TERM_DEBT)
    cash = v(LineItem.CASH) + v(LineItem.SHORT_TERM_INVESTMENTS)
    return debt - cash


def shares(statements: StatementSet, idx: int) -> float:
    """Diluted share count at column ``idx``: SHARES_DILUTED, else
    SHARES_OUTSTANDING. Raises if neither is present or it is non-positive
    (cannot derive a per-share value without a real denominator)."""
    n = at(statements.series(LineItem.SHARES_DILUTED), idx)
    if n is None:
        n = at(statements.series(LineItem.SHARES_OUTSTANDING), idx)
    if n is None or n <= 0:
        raise ValueError(
            "no positive diluted share count (SHARES_DILUTED / SHARES_OUTSTANDING) "
            f"at historical column {idx}; cannot compute a per-share value."
        )
    return n
