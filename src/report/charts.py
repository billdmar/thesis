"""Matplotlib chart suite for the initiating-coverage report.

Every chart is driven exclusively from a :class:`ModelBundle`; no financial
figure is hand-typed here (single-source-of-truth rule). Each
function saves a PNG into a caller-supplied directory and returns its path.

House style: restrained navy/steel palette, serif titles, sans tick labels,
no chart junk. Uses the non-interactive Agg backend so it renders headless in
CI and inside the WeasyPrint pipeline.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (must follow use("Agg"))

from src.interfaces import ModelBundle  # noqa: E402
from src.schema import LineItem, Period  # noqa: E402

# --- House style ---------------------------------------------------------
ACCENT = "#1f3b57"  # deep navy — subject / primary
STEEL = "#5b7c99"  # secondary series
MUTED = "#9aa7b1"  # peers / neutral
GRID = "#d8dee3"
POSITIVE = "#2f6f4f"  # target marker
FIGSIZE = (7.2, 3.9)
DPI = 150

_STYLE = {
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
    "axes.edgecolor": "#6b7680",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlecolor": ACCENT,
    "font.family": "sans-serif",
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
}


def _period_label(p: Period) -> str:
    """Column label preferring fiscal year, falling back to the end year."""
    if p.fy is not None:
        return f"FY{str(p.fy)[-2:]}"
    return f"FY{str(p.end.year)[-2:]}"


def _forecast_labels(model: ModelBundle) -> list[str]:
    """Labels for the projection years, based on the last historical period."""
    stmts = model.statements
    n = len(model.dcf.fcff_by_year)
    base_fy: int | None = None
    if stmts.periods:
        last = stmts.periods[min(stmts.n_hist, len(stmts.periods)) - 1]
        base_fy = last.fy if last.fy is not None else last.end.year
    if base_fy is None:
        return [f"Y{i + 1}" for i in range(n)]
    return [f"FY{str(base_fy + i + 1)[-2:]}" for i in range(n)]


def _save(fig: plt.Figure, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _ratio(num: list[float | None], den: list[float | None]) -> list[float | None]:
    out: list[float | None] = []
    for a, b in zip(num, den, strict=False):
        out.append(a / b if (a is not None and b not in (None, 0)) else None)
    return out


# --- Charts --------------------------------------------------------------
def revenue_margin_chart(model: ModelBundle, out_dir: str) -> str:
    """Revenue bars with gross- and EBIT-margin lines over all periods.

    Historical periods use the accent fill; projected periods (index >=
    ``n_hist``) are drawn lighter to signal they are assumption-driven.
    """
    stmts = model.statements
    # Trim to a readable window (last ~4 historical + all forecast) so the
    # x-axis isn't a jammed run of 18 fiscal-year ticks.
    total = len(stmts.periods)
    start = max(0, stmts.n_hist - 4)
    idxs = list(range(start, total))
    periods = [stmts.periods[i] for i in idxs]
    labels = [_period_label(p) for p in periods]
    revenue = [stmts.series(LineItem.REVENUE)[i] for i in idxs]
    gross = [stmts.series(LineItem.GROSS_PROFIT)[i] for i in idxs]
    ebit = [stmts.series(LineItem.OPERATING_INCOME)[i] for i in idxs]
    gm = _ratio(gross, revenue)
    om = _ratio(ebit, revenue)

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        x = range(len(periods))
        colors = [ACCENT if idxs[i] < stmts.n_hist else STEEL for i in x]
        bar_vals = [(v / 1e9) if v is not None else 0.0 for v in revenue]  # $bn
        ax.bar(x, bar_vals, color=colors, width=0.62, zorder=2)
        ax.set_ylabel("Revenue ($ bn)")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.margins(y=0.18)

        ax2 = ax.twinx()
        ax2.grid(False)
        ax2.plot(
            x,
            [None if v is None else v * 100 for v in gm],
            color="#b5651d",
            marker="o",
            markersize=4,
            linewidth=1.6,
            label="Gross margin",
        )
        ax2.plot(
            x,
            [None if v is None else v * 100 for v in om],
            color=POSITIVE,
            marker="s",
            markersize=4,
            linewidth=1.6,
            label="EBIT margin",
        )
        ax2.set_ylabel("Margin (%)")
        ax2.legend(loc="upper left", fontsize=7, frameon=False)
        # Hist/forecast boundary, in trimmed-window coordinates.
        boundary = stmts.n_hist - start
        if 0 < boundary < len(periods):
            ax.axvline(boundary - 0.5, color=MUTED, linestyle="--", linewidth=0.9)
        ax.set_title("Revenue & Margins — History and Forecast")
    return _save(fig, out_dir, "revenue_margin.png")


def fcf_trend_chart(model: ModelBundle, out_dir: str) -> str:
    """Unlevered free cash flow (FCFF) trend across the forecast horizon."""
    fcff = model.dcf.fcff_by_year
    labels = _forecast_labels(model)
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        x = range(len(fcff))
        ax.bar(x, fcff, color=STEEL, width=0.6, zorder=2)
        ax.plot(x, fcff, color=ACCENT, marker="o", markersize=4, linewidth=1.6, zorder=3)
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_ylabel("FCFF (USD)")
        ax.margins(y=0.18)
        ax.set_title("Projected Unlevered Free Cash Flow (FCFF)")
    return _save(fig, out_dir, "fcf_trend.png")


def comps_scatter_chart(model: ModelBundle, out_dir: str) -> str:
    """EV/EBITDA vs EV/Revenue scatter of the peer set, subject highlighted.

    The subject is placed using engine outputs: EV from the DCF and LTM
    revenue/EBITDA from the last historical statement column. Guards an empty
    peer list by rendering an explanatory placeholder frame.
    """
    peers = [
        p for p in model.comps.peers if p.ev_ebitda_ltm is not None and p.ev_revenue_ltm is not None
    ]
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.set_title("Trading Comparables — EV/EBITDA vs EV/Revenue")
        ax.set_xlabel("EV / Revenue (LTM, x)")
        ax.set_ylabel("EV / EBITDA (LTM, x)")
        if not peers:
            ax.text(
                0.5,
                0.5,
                "No peer multiples available",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color=MUTED,
                fontsize=10,
            )
            ax.set_xticks([])
            ax.set_yticks([])
            return _save(fig, out_dir, "comps_scatter.png")

        xs = [p.ev_revenue_ltm for p in peers]
        ys = [p.ev_ebitda_ltm for p in peers]
        ax.scatter(xs, ys, color=MUTED, s=55, zorder=2, label="Peers")
        for p in peers:
            ax.annotate(
                p.ticker,
                (p.ev_revenue_ltm, p.ev_ebitda_ltm),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=7,
                color="#4a545c",
            )

        subj = _subject_point(model)
        if subj is not None:
            sx, sy = subj
            ax.scatter(
                [sx], [sy], color=ACCENT, s=110, marker="*", zorder=4, label=model.company.ticker
            )
            ax.annotate(
                model.company.ticker,
                (sx, sy),
                textcoords="offset points",
                xytext=(6, 5),
                fontsize=8,
                fontweight="bold",
                color=ACCENT,
            )
        ax.legend(loc="best", fontsize=7, frameon=False)
    return _save(fig, out_dir, "comps_scatter.png")


def _subject_point(model: ModelBundle) -> tuple[float, float] | None:
    """(EV/Revenue, EV/EBITDA) for the subject from engine outputs, or None."""
    stmts = model.statements
    if not stmts.periods:
        return None
    idx = min(stmts.n_hist, len(stmts.periods)) - 1
    rev = stmts.series(LineItem.REVENUE)[idx]
    ebit = stmts.series(LineItem.OPERATING_INCOME)[idx]
    da_row = stmts.series(LineItem.DA_CF)
    da = da_row[idx] if idx < len(da_row) else None
    ev = model.dcf.enterprise_value_gordon
    if rev in (None, 0) or ebit is None:
        return None
    ebitda = ebit + (da or 0.0)
    if ebitda <= 0:
        return None
    return (ev / rev, ev / ebitda)


def football_field_chart(model: ModelBundle, out_dir: str) -> str:
    """Horizontal valuation ranges (DCF, comps) with price & target markers."""
    dcf = model.dcf
    rows: list[tuple[str, float, float]] = []

    lo_dcf = min(dcf.implied_price_gordon, dcf.implied_price_exit)
    hi_dcf = max(dcf.implied_price_gordon, dcf.implied_price_exit)
    rows.append(("DCF (Gordon / Exit)", lo_dcf, hi_dcf))

    # Comps band: EV/EBITDA only (capital-structure-neutral, the metric the
    # narrative anchors on). EV/Revenue and P/E implied prices are not
    # comparable across this peer set's margin/leverage differences and would
    # produce an indefensible $38–$163 span, so they are excluded from the band.
    # Bracket the EV/EBITDA implied price with the peer 25th–75th percentile
    # multiple spread when available, else a modest ±10% band.
    comps = model.comps
    ebitda_price = comps.implied_price_from_ebitda
    if ebitda_price is not None:
        stats = comps.stats.get("ev_ebitda_ltm", {})
        med = stats.get("median")
        p25, p75 = stats.get("p25"), stats.get("p75")
        if med and p25 and p75 and med > 0:
            lo_c = ebitda_price * (p25 / med)
            hi_c = ebitda_price * (p75 / med)
        else:
            lo_c, hi_c = ebitda_price * 0.90, ebitda_price * 1.10
        rows.append(("Trading comps (EV/EBITDA)", lo_c, hi_c))

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(7.2, 2.6 + 0.35 * len(rows)))
        ax.grid(False)
        ax.xaxis.grid(True)
        labels = [r[0] for r in rows]
        for i, (_, lo, hi) in enumerate(rows):
            ax.barh(i, hi - lo, left=lo, height=0.45, color=STEEL, zorder=2)
            ax.text(lo, i, f"${lo:,.0f}", va="center", ha="right", fontsize=7, color="#4a545c")
            ax.text(hi, i, f"${hi:,.0f}", va="center", ha="left", fontsize=7, color="#4a545c")
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(labels)
        ax.set_xlabel("Implied share price (USD)")

        ax.axvline(model.current_price, color=MUTED, linestyle="--", linewidth=1.2)
        ax.text(
            model.current_price,
            len(rows) - 0.35,
            f"  Price ${model.current_price:,.0f}",
            color="#4a545c",
            fontsize=7,
            va="bottom",
        )
        if model.price_target is not None:
            ax.axvline(model.price_target, color=POSITIVE, linewidth=1.6)
            ax.text(
                model.price_target,
                -0.6,
                f"Target ${model.price_target:,.0f}",
                color=POSITIVE,
                fontsize=7.5,
                fontweight="bold",
                ha="center",
            )
        ax.set_ylim(-0.9, len(rows) - 0.2)
        ax.invert_yaxis()
        ax.set_title("Football Field — Valuation Range")
    return _save(fig, out_dir, "football_field.png")


def segment_chart(model: ModelBundle, out_dir: str) -> str | None:
    """Stacked bar of brand-level net sales by fiscal year (HOKA/UGG/other)."""
    seg = model.segments
    if seg is None or not seg.segments:
        return None
    years = sorted({y.fiscal_year for s in seg.segments for y in s.years})
    scale = 1e9
    colors = [ACCENT, STEEL, MUTED, "#c2cbd3"]
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.grid(False)
        ax.yaxis.grid(True)
        bottoms = [0.0] * len(years)
        for i, s in enumerate(seg.segments):
            by_year = {y.fiscal_year: y.revenue / scale for y in s.years}
            vals = [by_year.get(y, 0.0) for y in years]
            ax.bar(
                [str(y) for y in years],
                vals,
                bottom=bottoms,
                label=s.name,
                color=colors[i % len(colors)],
                zorder=2,
            )
            bottoms = [b + v for b, v in zip(bottoms, vals, strict=True)]
        ax.set_ylabel("Net sales ($ bn)")
        ax.set_title("Brand-level net sales (HOKA / UGG / other)")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
    return _save(fig, out_dir, "segment_revenue.png")


def valuation_bridge_chart(model: ModelBundle, out_dir: str) -> str:
    """Waterfall: enterprise value → (less net debt / plus net cash) → equity
    value. The net-cash step is the DECK 'EV < equity' teaching moment."""
    d = model.dcf
    scale = 1e9
    ev = d.enterprise_value_gordon / scale
    net_debt = d.net_debt / scale  # negative = net cash
    equity = d.equity_value_gordon / scale
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.grid(False)
        ax.yaxis.grid(True)
        # Bar 1: EV (from 0). Bar 2: the net-debt/cash step (floats to equity).
        # Bar 3: equity value (from 0).
        ax.bar(0, ev, color=ACCENT, width=0.6, zorder=2)
        step_bottom = min(ev, equity)
        ax.bar(1, abs(net_debt), bottom=step_bottom, color=POSITIVE, width=0.6, zorder=2)
        ax.bar(2, equity, color=STEEL, width=0.6, zorder=2)
        ax.set_xticks([0, 1, 2])
        step_label = "less: net debt" if net_debt > 0 else "plus: net cash"
        ax.set_xticklabels(["Enterprise\nvalue", step_label, "Equity\nvalue"])
        ax.set_ylabel("$ bn")
        for xi, val in [(0, ev), (2, equity)]:
            ax.text(xi, val, f"${val:,.1f}B", ha="center", va="bottom", fontsize=8)
        ax.text(
            1,
            step_bottom + abs(net_debt),
            f"${abs(net_debt):,.1f}B",
            ha="center",
            va="bottom",
            fontsize=8,
            color=POSITIVE,
        )
        ax.set_title("Valuation Bridge — EV to Equity (Gordon)")
        ax.margins(y=0.18)
    return _save(fig, out_dir, "valuation_bridge.png")


def build_all_charts(model: ModelBundle, out_dir: str) -> dict[str, str]:
    """Render the full suite; returns a name -> path map for the template."""
    charts = {
        "revenue_margin": revenue_margin_chart(model, out_dir),
        "fcf_trend": fcf_trend_chart(model, out_dir),
        "comps_scatter": comps_scatter_chart(model, out_dir),
        "football_field": football_field_chart(model, out_dir),
        "valuation_bridge": valuation_bridge_chart(model, out_dir),
    }
    seg = segment_chart(model, out_dir)
    if seg is not None:
        charts["segment_revenue"] = seg
    return charts
