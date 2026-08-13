"""HOKA/UGG sum-of-the-parts cross-check (report exhibit, not the target basis).

Brand EBITDA is not disclosed by the filer (honest unknown), so this is an
EV/revenue SOTP on SOURCED brand net sales (latest fiscal year) with illustrative,
analyst-set per-brand multiples (``flagship.SOTP_EV_REVENUE``), anchored so the
blended value reconciles to the consolidated DCF. It quantifies the "two ways to
compound" thesis; it does NOT set the price target — the DCF anchors that.

Kept as one function so the report template and the report-number lint compute
identical values (the lint must know these numbers are engine/config-derived).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.interfaces import ModelBundle


@dataclass
class SotpBrand:
    name: str
    revenue: float  # latest-FY sourced net sales
    multiple: float  # illustrative EV/revenue (analyst judgment)
    ev: float  # revenue * multiple


@dataclass
class SotpResult:
    brands: list[SotpBrand]
    total_ev: float
    net_debt: float  # negative = net cash (added back)
    equity_value: float
    implied_price: float | None


def compute_sotp(model: ModelBundle, multiples: dict[str, float]) -> SotpResult | None:
    """Blend per-brand EV/revenue into an equity value per share, or None if the
    segment data / share count needed isn't available."""
    seg = model.segments
    d = model.dcf
    if seg is None or not seg.segments or d.shares_diluted in (None, 0):
        return None
    brands: list[SotpBrand] = []
    for s in seg.segments:
        if not s.years:
            continue
        rev = s.years[-1].revenue  # latest sourced FY
        mult = multiples.get(s.name, multiples.get("Other", 1.0))
        brands.append(SotpBrand(name=s.name, revenue=rev, multiple=mult, ev=rev * mult))
    if not brands:
        return None
    total_ev = sum(b.ev for b in brands)
    equity = total_ev - d.net_debt  # net_debt < 0 (net cash) → adds back
    return SotpResult(
        brands=brands,
        total_ev=total_ev,
        net_debt=d.net_debt,
        equity_value=equity,
        implied_price=equity / d.shares_diluted,
    )
