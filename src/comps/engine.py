"""the comps engine: trading-comparables and precedent-transaction engine.

Concrete implementation of the ``CompsEngine`` protocol (src/interfaces.py).

Design notes (the judgment that matters):

* **Enterprise value.** For every peer, ``EV = equity_value + total_debt −
  (cash + short-term investments)``. ``total_debt`` sums SHORT_TERM_DEBT and
  LONG_TERM_DEBT (each missing component treated as 0 — a company that files no
  short-term-debt tag genuinely carries none). ``cash`` sums CASH and
  SHORT_TERM_INVESTMENTS.

* **Where market price enters.** XBRL contains no share price, so equity value
  cannot come from the filings. ``build_peer_multiples`` accepts an optional
  ``market_data`` mapping ``ticker -> {"price": float, "shares": float}``. When
  a peer (or the subject) appears there, its equity value is ``price × shares``
  — a true market capitalisation, and its P/E is a real market P/E. When it does
  NOT appear, we fall back to BOOK equity (TOTAL_EQUITY) purely so the EV/Revenue
  and EV/EBITDA bridges can still be built; P/E is left None in that case because
  a book "P/E" would be a plausible-but-wrong number (honest-unknown rule). A
  peer with neither market nor book equity is excluded from the peer set (it
  cannot be valued) rather than fabricated with a zero.

* **LTM basis.** "LTM" here is the latest reported fiscal year: income- and
  cash-flow items from the most recent annual DURATION period, balance-sheet
  items from the most recent INSTANT period. (Quarter-stitched true-LTM is out
  of scope for the fixture set; the annual basis is stated plainly rather than
  approximated.)

* **Honest unknowns.** Any multiple whose inputs are missing is None and is
  excluded from the summary statistics — never fabricated or interpolated.
"""

from __future__ import annotations

import csv
from statistics import mean, median

from src.interfaces import CompsResult, PeerMultiples, PrecedentTransaction
from src.schema import LineItem, NormalizedFacts

# The three LTM multiples we compute summary statistics for.
_MULTIPLE_KEYS = ("ev_revenue_ltm", "ev_ebitda_ltm", "pe_ltm")


def _latest_duration_value(facts: NormalizedFacts, li: LineItem) -> float | None:
    """Value of ``li`` in the most recent annual (FY) DURATION period, or None."""
    periods = facts.annual_periods()
    if not periods:
        return None
    return facts.value(li, periods[-1])


def _latest_instant_value(facts: NormalizedFacts, li: LineItem) -> float | None:
    """Value of ``li`` in the most recent balance-sheet INSTANT period, or None."""
    periods = facts.instant_periods()
    if not periods:
        return None
    return facts.value(li, periods[-1])


def _sum_present(*values: float | None) -> float:
    """Sum only the non-None values (missing balance-sheet lines count as 0)."""
    return sum(v for v in values if v is not None)


def _total_debt(facts: NormalizedFacts) -> float:
    return _sum_present(
        _latest_instant_value(facts, LineItem.SHORT_TERM_DEBT),
        _latest_instant_value(facts, LineItem.LONG_TERM_DEBT),
    )


def _cash_and_st(facts: NormalizedFacts) -> float:
    return _sum_present(
        _latest_instant_value(facts, LineItem.CASH),
        _latest_instant_value(facts, LineItem.SHORT_TERM_INVESTMENTS),
    )


def _ebitda(facts: NormalizedFacts) -> float | None:
    """EBITDA = OPERATING_INCOME + D&A. None if either input is unavailable.

    D&A is taken from DEP_AMORT, falling back to the cash-flow D&A line
    (DA_CF) — the same economic concept, commonly disclosed only on the CFS.
    """
    ebit = _latest_duration_value(facts, LineItem.OPERATING_INCOME)
    if ebit is None:
        return None
    da = _latest_duration_value(facts, LineItem.DEP_AMORT)
    if da is None:
        da = _latest_duration_value(facts, LineItem.DA_CF)
    if da is None:
        return None
    return ebit + da


def _equity_value(
    facts: NormalizedFacts,
    market: dict[str, float] | None,
) -> tuple[float | None, bool]:
    """Return (equity_value, is_market_based).

    Market cap (price × shares) when ``market`` is supplied; otherwise book
    equity (TOTAL_EQUITY) as a documented proxy. ``is_market_based`` gates P/E.
    """
    if market is not None and "price" in market and "shares" in market:
        return market["price"] * market["shares"], True
    return _latest_instant_value(facts, LineItem.TOTAL_EQUITY), False


def _safe_div(numer: float | None, denom: float | None) -> float | None:
    """Divide, returning None when either operand is missing or the ratio is
    not economically meaningful (denominator ≤ 0)."""
    if numer is None or denom is None or denom <= 0:
        return None
    return numer / denom


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]) over a sorted list."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _stats(values: list[float | None]) -> dict[str, float] | None:
    """median/mean/min/max + 25th/75th percentiles over the non-None values.

    The p25/p75 spread drives the comps valuation band (a defensible
    interquartile range) rather than the full min–max, which outliers distort.
    """
    present = sorted(v for v in values if v is not None)
    if not present:
        return None
    return {
        "median": median(present),
        "mean": mean(present),
        "min": present[0],
        "max": present[-1],
        "p25": _percentile(present, 0.25),
        "p75": _percentile(present, 0.75),
    }


class CompsEngine:
    """Concrete ``CompsEngine`` (see src/interfaces.py Protocol)."""

    def build_peer_multiples(
        self,
        subject: NormalizedFacts,
        peers: list[NormalizedFacts],
        market_data: dict[str, dict[str, float]] | None = None,
    ) -> CompsResult:
        """Build peer multiples, summary stats, and the subject's implied value.

        ``market_data`` maps ticker -> {"price", "shares"}. It is the ONLY place
        a share price enters the engine (XBRL has none). See module docstring for
        the EV construction and the market-vs-book equity fallback.
        """
        market_data = market_data or {}

        peer_rows: list[PeerMultiples] = []
        for pf in peers:
            row = self._peer_row(pf, market_data.get(pf.company.ticker))
            if row is not None:
                peer_rows.append(row)

        stats = {
            key: s
            for key in _MULTIPLE_KEYS
            if (s := _stats([getattr(r, key) for r in peer_rows])) is not None
        }

        result = CompsResult(peers=peer_rows, stats=stats)
        self._apply_implied(result, subject, market_data.get(subject.company.ticker))
        return result

    def _peer_row(
        self,
        facts: NormalizedFacts,
        market: dict[str, float] | None,
    ) -> PeerMultiples | None:
        """One peer's EV build and LTM multiples, or None if it cannot be valued."""
        equity_value, is_market = _equity_value(facts, market)
        if equity_value is None:
            # No market cap and no book equity — cannot construct EV. Excluded
            # rather than fabricated (honest-unknown rule).
            return None

        ev = equity_value + _total_debt(facts) - _cash_and_st(facts)

        revenue = _latest_duration_value(facts, LineItem.REVENUE)
        ebitda = _ebitda(facts)
        net_income = _latest_duration_value(facts, LineItem.NET_INCOME)

        # P/E only when equity is a real market cap; a book "P/E" would mislead.
        pe = _safe_div(equity_value, net_income) if is_market else None

        return PeerMultiples(
            ticker=facts.company.ticker,
            name=facts.company.name,
            enterprise_value=ev,
            equity_value=equity_value,
            ev_revenue_ltm=_safe_div(ev, revenue),
            ev_ebitda_ltm=_safe_div(ev, ebitda),
            pe_ltm=pe,
        )

    def _apply_implied(
        self,
        result: CompsResult,
        subject: NormalizedFacts,
        market: dict[str, float] | None,
    ) -> None:
        """Apply peer MEDIAN multiples to the subject's own metrics."""
        net_debt = _total_debt(subject) - _cash_and_st(subject)

        # Subject shares for the per-share bridge: market share count if given,
        # else period-end shares outstanding, else diluted weighted-average.
        shares: float | None = None
        if market is not None and "shares" in market:
            shares = market["shares"]
        if shares is None:
            shares = _latest_instant_value(subject, LineItem.SHARES_OUTSTANDING)
        if shares is None:
            shares = _latest_duration_value(subject, LineItem.SHARES_DILUTED)

        ebitda = _ebitda(subject)
        revenue = _latest_duration_value(subject, LineItem.REVENUE)
        net_income = _latest_duration_value(subject, LineItem.NET_INCOME)

        med_ebitda = result.stats.get("ev_ebitda_ltm", {}).get("median")
        med_revenue = result.stats.get("ev_revenue_ltm", {}).get("median")
        med_pe = result.stats.get("pe_ltm", {}).get("median")

        # EV/EBITDA -> implied EV -> implied equity -> implied price.
        if med_ebitda is not None and ebitda is not None:
            implied_ev = med_ebitda * ebitda
            result.implied_ev_from_ebitda = implied_ev
            result.implied_price_from_ebitda = _safe_div(implied_ev - net_debt, shares)

        # EV/Revenue -> implied EV -> implied equity -> implied price.
        if med_revenue is not None and revenue is not None:
            implied_ev_rev = med_revenue * revenue
            result.implied_price_from_revenue = _safe_div(implied_ev_rev - net_debt, shares)

        # P/E -> implied equity -> implied price.
        if med_pe is not None and net_income is not None:
            result.implied_price_from_pe = _safe_div(med_pe * net_income, shares)

    def load_precedents(self, csv_path: str) -> list[PrecedentTransaction]:
        """Parse the curated precedent-transactions CSV.

        Columns: date,acquirer,target,ev,ev_revenue,ev_ebitda,source. Empty
        numeric cells parse to None (honest unknown); ``ev`` is required.
        """
        out: list[PrecedentTransaction] = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out.append(
                    PrecedentTransaction(
                        date=row["date"].strip(),
                        acquirer=row["acquirer"].strip(),
                        target=row["target"].strip(),
                        ev=float(row["ev"]),
                        ev_revenue=_parse_optional_float(row.get("ev_revenue")),
                        ev_ebitda=_parse_optional_float(row.get("ev_ebitda")),
                        source=row["source"].strip(),
                    )
                )
        return out


def _parse_optional_float(raw: str | None) -> float | None:
    """A blank cell is an honest unknown (None); otherwise parse the float."""
    if raw is None or raw.strip() == "":
        return None
    return float(raw)
