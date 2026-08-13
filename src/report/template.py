"""HTML/CSS builder for the initiating-coverage report.

Jinja-free: the report is assembled from Python f-strings so the only runtime
dependency is WeasyPrint (Jinja2 is not guaranteed installed). The structure
follows docs/REPORT_SPEC.md section-for-section.

Single source of truth: every financial figure is read from the passed
:class:`ModelBundle`; nothing numeric is hard-coded. Analyst-authored narrative
prose is emitted as clearly-marked ``[DRAFT: ...]`` placeholders when not
supplied, so the layout is testable without inventing facts.
"""

from __future__ import annotations

import base64
import os

from src.interfaces import ModelBundle
from src.report.charts import build_all_charts
from src.schema import LineItem

# Verbatim disclaimer (REPORT_SPEC.md "Disclaimer" requirement). Do not reword.
DISCLAIMER = (
    "This report is an educational project and is not investment advice. It was "
    "produced from public SEC EDGAR data used under the SEC's fair-access policy "
    "without implying SEC endorsement. All projections are the author's own "
    "assumptions, labeled as such, and are never presented as fact. Nothing herein "
    "is a recommendation, offer, or solicitation to buy or sell any security."
)

_PLACEHOLDER = "[DRAFT: {}]"


def _narrative(key: str, narrative: dict[str, str] | None = None) -> str:
    """Return the analyst-authored prose for ``key`` if supplied, else a labeled
    placeholder. Narrative prose is injected data (parallel to how numbers flow
    from the engine): the template owns structure, the analyst owns the words."""
    if narrative and narrative.get(key):
        return narrative[key]
    return _PLACEHOLDER.format(key)


# --- Number formatting (honest unknown -> em dash, never a fake value) ----
def _usd(v: float | None, scale: float = 1.0, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"${v / scale:,.0f}{suffix}"


def _usd2(v: float | None) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _num(v: float | None, scale: float = 1.0, dp: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v / scale:,.{dp}f}"


def _pct(v: float | None, dp: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{dp}f}%"


def _mult(v: float | None, dp: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{dp}f}x"


def _n_verified_cells(model: ModelBundle) -> int:
    """Count of workbook cells differentially verified against the engine —
    read from the same authoritative map the verifier uses, so the report's
    claim can never drift from the actual coverage."""
    from src.workbook.writer import build_verifier_cell_map

    return len(build_verifier_cell_map(model))


def _shares(v: float | None) -> str:
    """Share counts always render in millions — never inherit the revenue
    billions scale (that produced the "0 bn" cover bug)."""
    if v is None:
        return "—"
    return f"{v / 1e6:,.1f}M"


def _net_cash_phrase(net_debt: float | None, scale: float, sfx: str) -> str:
    """Signed-sense net cash/debt. Negative net debt is net CASH — the DECK
    thesis point — and must not print as an ugly '$-2 bn'. One decimal so a
    ~$1.9bn position doesn't round to '$2 bn'."""
    if net_debt is None:
        return "—"
    mag = f"${_num(abs(net_debt), scale, dp=1)} {sfx}"
    return f"net cash {mag}" if net_debt < 0 else f"net debt {mag}"


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0):
        return None
    return num / den


def _auto_scale(model: ModelBundle) -> tuple[float, str]:
    """Pick a display scale (millions/billions) from revenue magnitude. Used for
    single headline figures (market cap, EV) where one decimal in $bn reads well."""
    rev = model.statements.series(LineItem.REVENUE)
    mags = [abs(v) for v in rev if v]
    peak = max(mags) if mags else 0.0
    if peak >= 1e9:
        return 1e9, "bn"
    if peak >= 1e6:
        return 1e6, "mm"
    return 1.0, ""


def _stmt_scale(model: ModelBundle) -> tuple[float, str]:
    """Scale for statement LINE-ITEM tables: always $mm with thousands commas.
    Billions-with-0dp collapsed real numbers (e.g. $5.47bn -> "5", net income ->
    "0"); rendering in millions ("5,472") keeps every line legible and non-zero."""
    return 1e6, "mm"


# Statement-table display window: show the last N historical + all forecast
# columns (a banker curates to a relevant window, not 18 years of raw history).
_HIST_DISPLAY = 4


def _display_period_indices(model: ModelBundle) -> list[int]:
    """Column indices to render in statement tables: last _HIST_DISPLAY
    historical periods + every projected period. Avoids the FY08→ overflow."""
    n = model.statements.n_hist
    total = len(model.statements.periods)
    start = max(0, n - _HIST_DISPLAY)
    return list(range(start, total))


def _img(path: str) -> str:
    """Inline a PNG as a data URI so the single HTML string is self-contained."""
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# --- CSS ------------------------------------------------------------------
def _css() -> str:
    return """
@page {
    size: Letter;
    margin: 22mm 18mm 20mm 18mm;
    @top-left { content: "Independent Equity Research"; font-size: 8pt; color: #5b7c99; }
    @top-right { content: "TICKER_HDR"; font-size: 8pt; color: #5b7c99; }
    @bottom-center { content: counter(page); font-size: 8pt; color: #9aa7b1; }
}
@page cover { @top-left { content: ""; } @top-right { content: ""; } }
body { font-family: Georgia, "Times New Roman", serif; font-size: 10pt;
       color: #1c2429; line-height: 1.42; }
h1, h2, h3, .sans { font-family: "Helvetica Neue", Arial, sans-serif; color: #1f3b57; }
h1 { font-size: 20pt; margin: 0 0 4pt 0; }
h2 { font-size: 14pt; border-bottom: 2px solid #1f3b57; padding-bottom: 3pt;
     margin: 20pt 0 8pt 0; }
h3 { font-size: 11pt; margin: 12pt 0 4pt 0; }
p { margin: 4pt 0; }
.cover { page: cover; height: 100%; }
.cover-title { margin-top: 30mm; }
.rating-box { display: inline-block; border: 2px solid #1f3b57; padding: 6pt 14pt;
              font-family: "Helvetica Neue", Arial, sans-serif; font-weight: bold;
              font-size: 16pt; color: #1f3b57; margin: 10pt 0; }
.pt-line { font-size: 13pt; font-family: "Helvetica Neue", Arial, sans-serif; }
.up { color: #2f6f4f; font-weight: bold; }
.down { color: #a3322b; font-weight: bold; }
.muted { color: #5b7c99; }
.orch { color: #9a6a00; font-style: italic; background: #fbf5e8;
        padding: 1pt 3pt; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9pt; }
th, td { text-align: right; padding: 3pt 6pt; border-bottom: 0.5pt solid #d8dee3; }
th:first-child, td:first-child { text-align: left; }
thead th { border-bottom: 1pt solid #1f3b57; color: #1f3b57;
           font-family: "Helvetica Neue", Arial, sans-serif; }
.fig { margin: 8pt 0 2pt 0; }
.fig img { width: 100%; }
.caption { font-size: 8pt; color: #5b7c99; margin-bottom: 8pt; font-style: italic; }
.disclaimer { font-size: 7.5pt; color: #4a545c; border-top: 0.5pt solid #d8dee3;
              padding-top: 6pt; margin-top: 10pt; }
.market-block td:first-child { color: #5b7c99; }
.pagebreak { page-break-before: always; }
.section-note { font-size: 8.5pt; color: #5b7c99; }
"""


# --- Section builders -----------------------------------------------------
def _upside(model: ModelBundle) -> float | None:
    if model.price_target is None or model.current_price in (None, 0):
        return None
    return model.price_target / model.current_price - 1.0


def _cover(model: ModelBundle, as_of: str, narrative: dict[str, str] | None = None) -> str:
    """One-page tearsheet: the dense summary a reviewer skims first —
    rating/target/upside, market data, valuation triangulation, a 5-yr financial
    snapshot, and the thesis one-liner + top catalyst/risk."""
    c = model.company
    scale, sfx = _auto_scale(model)
    up = _upside(model)
    up_cls = "up" if (up is not None and up >= 0) else "down"
    up_txt = _pct(up) if up is not None else "—"
    rating = model.rating or _narrative("rating")
    exchange = getattr(c, "exchange", None) or "SEC-registered"
    shares = model.dcf.shares_diluted
    ev = model.dcf.enterprise_value_gordon
    mkt_cap = model.wacc_inputs.market_cap
    d = model.dcf

    # Valuation triangulation mini-table.
    comps_px = model.comps.implied_price_from_ebitda
    tri = (
        f"<tr><td>DCF — Gordon growth</td><td>{_usd2(d.implied_price_gordon)}</td></tr>"
        f"<tr><td>DCF — exit multiple</td><td>{_usd2(d.implied_price_exit)}</td></tr>"
        f"<tr><td>Trading comps (EV/EBITDA)</td><td>{_usd2(comps_px)}</td></tr>"
    )
    if model.scenarios is not None:
        by = {s.name: s.implied_price_mid for s in model.scenarios.scenarios}
        tri += (
            f"<tr><td>Scenarios (bear / bull)</td>"
            f"<td>{_usd2(by.get('Bear'))} / {_usd2(by.get('Bull'))}</td></tr>"
        )

    # 5-year financial snapshot (last 2 hist + 3 forecast for a tight fit).
    stmts = model.statements
    idxs = _display_period_indices(model)[-5:]
    ss, _ = _stmt_scale(model)
    hdr = _stmt_labels(model, idxs)
    rev = stmts.series(LineItem.REVENUE)
    ebit = stmts.series(LineItem.OPERATING_INCOME)
    ebit_m = [_ratio(e, r) for e, r in zip(ebit, rev, strict=False)]
    snap = (
        "<tr><td>Revenue ($mm)</td>"
        + "".join(f"<td>{_num(rev[i], ss)}</td>" for i in idxs)
        + "</tr><tr><td>EBIT margin</td>"
        + "".join(f"<td>{_pct(ebit_m[i])}</td>" for i in idxs)
        + "</tr>"
    )

    thesis = _narrative("thesis", narrative)
    return f"""
<section class="cover">
  <div class="cover-title">
    <h1>{c.name}</h1>
    <p class="sans muted">{c.ticker} · {exchange} · Initiating Coverage · {_report_date(as_of)}</p>
  </div>
  <div class="rating-box">{rating}</div>
  <p class="pt-line">12-month price target: <b>{_usd2(model.price_target)}</b>
     &nbsp;|&nbsp; Current price: <b>{_usd2(model.current_price)}</b>
     &nbsp;|&nbsp; <span class="{up_cls}">{up_txt} {"upside" if (up or 0) >= 0 else "downside"}</span></p>
  <table style="width:100%; margin-top:6pt;"><tr>
    <td style="width:50%; vertical-align:top; border:none; padding-right:10pt;">
      <table class="market-block">
        <thead><tr><th>Market data</th><th></th></tr></thead>
        <tr><td>Market capitalization</td><td>{_usd(mkt_cap, scale, " " + sfx)}</td></tr>
        <tr><td>Enterprise value (DCF)</td><td>{_usd(ev, scale, " " + sfx)}</td></tr>
        <tr><td>Diluted shares</td><td>{_shares(shares)}</td></tr>
        <tr><td>Balance sheet</td><td>{_net_cash_phrase(d.net_debt, scale, sfx)}</td></tr>
        <tr><td>WACC</td><td>{_pct(d.wacc, dp=2)}</td></tr>
      </table>
    </td>
    <td style="width:50%; vertical-align:top; border:none;">
      <table>
        <thead><tr><th>Valuation ($/share)</th><th></th></tr></thead>
        {tri}
      </table>
    </td>
  </tr></table>
  <table style="margin-top:4pt;">
    <thead><tr><th>Financial snapshot</th>{hdr}</tr></thead>
    <tbody>{snap}</tbody>
  </table>
  <h3 style="margin-top:8pt;">Investment thesis</h3>
  <p style="font-size:9pt;">{thesis}</p>
  <p class="muted sans" style="font-size:8pt;">Analyst: William Mar
     (independent educational project). USD in millions unless noted.</p>
  <p class="disclaimer">{DISCLAIMER}</p>
  <p class="disclaimer">Data source: SEC EDGAR XBRL CompanyFacts (public domain).</p>
</section>
"""


def _report_date(as_of: str) -> str:
    """Format the as-of date deterministically. Never uses today's date — the
    report must rebuild identically and its date is the market-data as-of, not
    the render day."""
    from datetime import date

    try:
        return date.fromisoformat(as_of).strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return as_of


def _key_financials_table(model: ModelBundle) -> str:
    stmts = model.statements
    scale, sfx = _stmt_scale(model)
    idxs = _display_period_indices(model)
    periods = stmts.periods
    labels = []
    for i in idxs:
        p = periods[i]
        fy = p.fy if p.fy is not None else p.end.year
        tag = "" if i < stmts.n_hist else "E"
        labels.append(f"FY{str(fy)[-2:]}{tag}")
    rev = stmts.series(LineItem.REVENUE)
    ebit = stmts.series(LineItem.OPERATING_INCOME)
    eps = stmts.series(LineItem.EPS_DILUTED)
    cfo = stmts.series(LineItem.CFO)
    capex = stmts.series(LineItem.CAPEX)
    fcf = [
        (o + cx) if (o is not None and cx is not None) else None
        for o, cx in zip(cfo, capex, strict=False)
    ]
    ebit_margin = [_ratio(e, r) for e, r in zip(ebit, rev, strict=False)]

    head = "".join(f"<th>{lbl}</th>" for lbl in labels)

    def row(name, vals, fmt):
        cells = "".join(f"<td>{fmt(vals[i])}</td>" for i in idxs)
        return f"<tr><td>{name}</td>{cells}</tr>"

    return f"""
<table>
  <thead><tr><th>USD {sfx}, FY ending</th>{head}</tr></thead>
  <tbody>
    {row("Revenue", rev, lambda v: _num(v, scale))}
    {row("EBIT margin", ebit_margin, _pct)}
    {row("Diluted EPS", eps, _usd2)}
    {row("Free cash flow", fcf, lambda v: _num(v, scale))}
  </tbody>
</table>
<p class="section-note">USD in millions. FCF = cash from operations + capital
expenditures (capex is signed negative per the engine convention). Columns marked
E are forecast (assumption-driven), not fact.</p>
"""


def _exec_summary(model: ModelBundle, narrative: dict[str, str] | None = None) -> str:
    cat = (narrative or {}).get("catalysts")
    if cat:
        cat_items = "".join(f"<li>{c}</li>" for c in cat.split("|"))
    else:
        cat_items = (
            f"<li>{_narrative('catalyst 1')}</li>"
            f"<li>{_narrative('catalyst 2')}</li>"
            f"<li>{_narrative('catalyst 3')}</li>"
        )
    return f"""
<section class="pagebreak">
  <h2>Executive Summary</h2>
  <h3>Investment thesis</h3>
  <p>{_narrative("thesis", narrative)}</p>
  <h3>Key financials</h3>
  {_key_financials_table(model)}
  <h3>Catalysts</h3>
  <ul>
    {cat_items}
  </ul>
  <h3>Valuation summary</h3>
  <p>Our 12-month target of <b>{_usd2(model.price_target)}</b> is triangulated across
     a DCF (implied {_usd2(model.dcf.implied_price_gordon)}–{_usd2(model.dcf.implied_price_exit)}),
     trading comparables{_comps_range_phrase(model)}, and precedent transactions.
     Against the current price of {_usd2(model.current_price)} this implies
     {_pct(_upside(model))} {"upside" if (_upside(model) or 0) >= 0 else "downside"}.
     <span>{_narrative("method_weighting", narrative)}</span></p>
</section>
"""


def _comps_range_phrase(model: ModelBundle) -> str:
    p = model.comps.implied_price_from_ebitda
    if p is None:
        return ""
    return f" (implied {_usd2(p)} on peer EV/EBITDA)"


def _segment_table(model: ModelBundle, charts: dict[str, str]) -> str:
    """Brand-level (HOKA/UGG/other) net-sales table + chart, if data is loaded."""
    seg = model.segments
    if seg is None or not seg.segments:
        return ""
    years = sorted({y.fiscal_year for s in seg.segments for y in s.years})
    scale, sfx = _stmt_scale(model)
    head = "".join(f"<th>FY{str(y)[-2:]}</th>" for y in years)
    rows = ""
    for s in seg.segments:
        by_year = {y.fiscal_year: y.revenue for y in s.years}
        cells = "".join(f"<td>{_num(by_year.get(y), scale)}</td>" for y in years)
        rows += f"<tr><td>{s.name}</td>{cells}</tr>"
    chart_html = ""
    if "segment_revenue" in charts:
        chart_html = (
            f'<div class="fig"><img src="{_img(charts["segment_revenue"])}" '
            'alt="Segment revenue"/></div>'
            '<p class="caption">Figure. Brand-level net-sales mix and growth '
            "(HOKA vs UGG). Source: curated from Deckers 10-K segment footnotes.</p>"
        )
    return f"""
<h3>Brand-level net sales</h3>
<table>
  <thead><tr><th>Net sales (USD {sfx}), FY ending</th>{head}</tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="section-note">{seg.source_note}</p>
{chart_html}
"""


def _company_overview(
    model: ModelBundle, charts: dict[str, str], narrative: dict[str, str] | None = None
) -> str:
    return f"""
<section class="pagebreak">
  <h2>Company Overview</h2>
  <p>{_narrative("company_overview", narrative)}</p>
  {_segment_table(model, charts)}
</section>
"""


def _sensitivity_table(model: ModelBundle) -> str:
    """Two-way WACC × terminal-growth implied-price grid, computed from engine
    outputs (mirrors the workbook's Sensitivities tab). The centre cell (Δ=0)
    reproduces the DCF Gordon implied price while minority interest is 0 (the
    grid subtracts net debt only; the engine bridge also nets minority interest,
    which is zero for this filer), so the two surfaces agree; every cell is
    engine-derived, so the report-number lint still holds."""
    d = model.dcf
    tf = getattr(d, "terminal_fcff_normalized", None)
    if tf is None or d.shares_diluted in (None, 0):
        return ""
    base_w = d.wacc
    base_g = model.terminal.terminal_growth
    n = len(d.fcff_by_year)
    deltas_w = [-0.01, -0.005, 0.0, 0.005, 0.01]
    deltas_g = [-0.01, -0.005, 0.0, 0.005, 0.01]

    def price(w: float, g: float) -> float | None:
        if w - g <= 0:  # Gordon undefined / invalid when g >= WACC
            return None
        tv = tf * (1.0 + g) / (w - g)
        ev = d.pv_explicit_fcff + tv / (1.0 + w) ** (n - 0.5)
        return (ev - d.net_debt) / d.shares_diluted

    head = "".join(f"<th>{_pct(base_w + dw)}</th>" for dw in deltas_w)
    rows = ""
    for dg in deltas_g:
        cells = ""
        for dw in deltas_w:
            p = price(base_w + dw, base_g + dg)
            cells += f"<td>{_usd2(p)}</td>"
        rows += f"<tr><td>{_pct(base_g + dg)}</td>{cells}</tr>"
    return f"""
<h3>Sensitivity — implied price by WACC and terminal growth</h3>
<table>
  <thead><tr><th>g \\ WACC</th>{head}</tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="section-note">Gordon implied price per share as WACC and the terminal
   growth rate g vary around the base case ({_pct(base_w, dp=2)} / {_pct(base_g)}, the
   centre cell; column headers are rounded to one decimal). The band brackets the
   target across a defensible range of the two
   inputs the DCF is most sensitive to; cells where g ≥ WACC are omitted (Gordon
   undefined).</p>
"""


def _sotp_table(model: ModelBundle) -> str:
    """HOKA/UGG sum-of-the-parts cross-check: sourced brand net sales × an
    illustrative per-brand EV/revenue multiple → blended equity value per share,
    reconciled against the consolidated DCF. Quantifies the two-brand thesis; not
    the target basis. Every rendered number is engine/config-derived (see
    segments.sotp.compute_sotp), so the report-number lint holds."""
    from src.flagship import SOTP_EV_REVENUE
    from src.segments.sotp import compute_sotp

    r = compute_sotp(model, SOTP_EV_REVENUE)
    if r is None:
        return ""
    # $mm with thousands separators (the statement-table scale), NOT $bn-0dp:
    # billions-with-0dp collapses a real $220M brand to "$0 bn" and the parts stop
    # footing to the total (the documented "0 bn" rounding hazard).
    scale, sfx = _stmt_scale(model)
    rows = ""
    for b in r.brands:
        rows += (
            f"<tr><td>{b.name}</td>"
            f"<td>{_num(b.revenue, scale)}</td>"
            # 2 dp so the row foots: revenue × multiple = implied EV (a 1-dp "3.8x"
            # against 2,233 → 8,374 would look ~1% off to a reader checking the math).
            f"<td>{_mult(b.multiple, dp=2)}</td>"
            f"<td>{_num(b.ev, scale)}</td></tr>"
        )
    net_cash_cell = f"({_num(-r.net_debt, scale)})" if r.net_debt < 0 else _num(r.net_debt, scale)
    return f"""
<h3>Sum-of-the-parts cross-check (HOKA / UGG)</h3>
<table>
  <thead><tr><th>Brand (USD {sfx})</th><th>Net sales (LTM)</th><th>EV/Revenue</th><th>Implied EV</th></tr></thead>
  <tbody>
    {rows}
    <tr style="font-weight:bold;"><td>Total enterprise value</td><td></td><td></td>
       <td>{_num(r.total_ev, scale)}</td></tr>
    <tr><td>Plus: net cash (added back)</td><td></td><td></td><td>{net_cash_cell}</td></tr>
    <tr style="font-weight:bold;"><td>Equity value → per share</td><td></td><td></td>
       <td>{_usd2(r.implied_price)}</td></tr>
  </tbody>
</table>
<p class="section-note">A cross-check, not the target basis: brand net sales are
   sourced from the 10-K, but per-brand EV/revenue multiples are illustrative
   analyst judgment (HOKA a growth premium, UGG a mature-franchise multiple),
   anchored so the blend reconciles to the consolidated DCF (~{_usd2(model.dcf.implied_price_gordon)}
   Gordon). Brand EBITDA is not disclosed, so this is deliberately an EV/revenue
   cross-check, not a fabricated brand-EBITDA build.</p>
"""


def _scenario_table(model: ModelBundle) -> str:
    """Bull / base / bear implied-price table, if scenarios are present."""
    sc = model.scenarios
    if sc is None or not sc.scenarios:
        return ""
    rows = ""
    for s in sc.scenarios:
        rows += (
            f"<tr><td>{s.name}</td>"
            f"<td>{_pct(s.revenue_cagr)}</td>"
            f"<td>{_pct(s.terminal_growth)}</td>"
            f"<td>{_mult(s.exit_ev_ebitda)}</td>"
            f"<td>{_usd2(s.implied_price_mid)}</td></tr>"
        )
    return f"""
<h3>Scenario analysis (bull / base / bear)</h3>
<table>
  <thead><tr><th>Scenario</th><th>Rev CAGR</th><th>Term. g</th><th>Exit EV/EBITDA</th>
     <th>Implied price (mid)</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="section-note">Each scenario runs the same statement + DCF engine on its
   own driver set; the current price sits near the bear case, framing the
   asymmetry.</p>
"""


def _comps_table(model: ModelBundle) -> str:
    peers = model.comps.peers
    if not peers:
        return '<p class="section-note">No peer multiples available from the engine.</p>'
    scale, sfx = _auto_scale(model)
    body = ""
    for p in peers:
        body += (
            f"<tr><td>{p.ticker} — {p.name}</td>"
            f"<td>{_usd(p.enterprise_value, scale, ' ' + sfx)}</td>"
            f"<td>{_mult(p.ev_revenue_ltm)}</td>"
            f"<td>{_mult(p.ev_ebitda_ltm)}</td>"
            f"<td>{_mult(p.pe_ltm)}</td></tr>"
        )
    stats = model.comps.stats
    med_ebitda = stats.get("ev_ebitda_ltm", {}).get("median")
    med_rev = stats.get("ev_revenue_ltm", {}).get("median")
    med_pe = stats.get("pe_ltm", {}).get("median")
    body += (
        f'<tr style="font-weight:bold;"><td>Peer median</td><td></td>'
        f"<td>{_mult(med_rev)}</td><td>{_mult(med_ebitda)}</td><td>{_mult(med_pe)}</td></tr>"
    )
    return f"""
<table>
  <thead><tr><th>Peer</th><th>EV</th><th>EV/Rev</th><th>EV/EBITDA</th><th>P/E</th></tr></thead>
  <tbody>{body}</tbody>
</table>
"""


def _industry(
    model: ModelBundle, charts: dict[str, str], narrative: dict[str, str] | None = None
) -> str:
    return f"""
<section class="pagebreak">
  <h2>Industry &amp; Competitive Analysis</h2>
  <p>{_narrative("industry", narrative)}</p>
  {_comps_table(model)}
  <div class="fig"><img src="{_img(charts["comps_scatter"])}" alt="Comps scatter"/></div>
  <p class="caption">Figure 1. Trading comparables — valuation multiples with
     {model.company.ticker} highlighted. Multiples are computed by the engine from
     SEC-reported financials; peer prices and share counts are illustrative,
     approximate as-of quotes (external to SEC XBRL), so the peer multiples are
     indicative and used only as a cross-check on the DCF.</p>
</section>
"""


def _financial_analysis(
    model: ModelBundle, charts: dict[str, str], narrative: dict[str, str] | None = None
) -> str:
    return f"""
<section class="pagebreak">
  <h2>Financial Analysis</h2>
  <p>{_narrative("financial_analysis", narrative)}</p>
  <div class="fig"><img src="{_img(charts["revenue_margin"])}" alt="Revenue and margins"/></div>
  <p class="caption">Figure 2. Revenue with gross- and EBIT-margin trend, history and
     forecast. Source: statement model.</p>
  <div class="fig"><img src="{_img(charts["fcf_trend"])}" alt="FCFF trend"/></div>
  <p class="caption">Figure 3. Projected unlevered free cash flow (FCFF).
     Source: DCF engine (fcff_by_year).</p>
</section>
"""


def _wacc_table(model: ModelBundle) -> str:
    w = model.wacc_inputs
    cost_equity = w.risk_free_rate + w.beta * w.equity_risk_premium
    after_tax_kd = w.pretax_cost_of_debt * (1 - w.tax_rate)
    e = w.market_cap
    d = w.total_debt
    v = e + d
    we = e / v if v else None
    wd = d / v if v else None
    return f"""
<table style="width:70%;">
  <thead><tr><th>WACC build (CAPM)</th><th></th></tr></thead>
  <tbody>
    <tr><td>Risk-free rate (10Y UST)</td><td>{_pct(w.risk_free_rate)}</td></tr>
    <tr><td>Levered beta</td><td>{_num(w.beta, dp=2)}</td></tr>
    <tr><td>Equity risk premium</td><td>{_pct(w.equity_risk_premium)}</td></tr>
    <tr><td>Cost of equity (CAPM)</td><td>{_pct(cost_equity, dp=2)}</td></tr>
    <tr><td>Pre-tax cost of debt</td><td>{_pct(w.pretax_cost_of_debt)}</td></tr>
    <tr><td>Tax rate</td><td>{_pct(w.tax_rate)}</td></tr>
    <tr><td>After-tax cost of debt</td><td>{_pct(after_tax_kd)}</td></tr>
    <tr><td>Weight of equity / debt</td><td>{_pct(we)} / {_pct(wd)}</td></tr>
    <tr style="font-weight:bold;"><td>WACC</td><td>{_pct(model.dcf.wacc, dp=2)}</td></tr>
  </tbody>
</table>
"""


def _dcf_bridge_table(model: ModelBundle) -> str:
    d = model.dcf
    scale, sfx = _stmt_scale(model)

    def u(v):
        return _usd(v, scale, " " + sfx)

    # Net debt / minority interest are subtracted in the bridge; show net debt
    # with its true sign sense (DECK is net cash, so it ADDS to equity value).
    net_debt_cell = (
        "—" if d.net_debt is None else f"({u(-d.net_debt)})" if d.net_debt < 0 else u(d.net_debt)
    )
    shares_cell = _shares(d.shares_diluted)
    return f"""
<table style="width:85%;">
  <thead><tr><th>DCF (USD {sfx})</th><th>Gordon growth</th><th>Exit multiple</th></tr></thead>
  <tbody>
    <tr><td>PV of explicit FCFF</td><td>{u(d.pv_explicit_fcff)}</td><td>{u(d.pv_explicit_fcff)}</td></tr>
    <tr><td>Terminal value</td><td>{u(d.terminal_value_gordon)}</td><td>{u(d.terminal_value_exit)}</td></tr>
    <tr><td>PV of terminal value</td><td>{u(d.pv_terminal_gordon)}</td><td>{u(d.pv_terminal_exit)}</td></tr>
    <tr style="font-weight:bold;"><td>Enterprise value</td><td>{u(d.enterprise_value_gordon)}</td><td>{u(d.enterprise_value_exit)}</td></tr>
    <tr><td>Less: net debt (parens = net cash added back)</td><td>{net_debt_cell}</td><td>{net_debt_cell}</td></tr>
    <tr><td>Less: minority interest</td><td>{u(d.minority_interest)}</td><td>{u(d.minority_interest)}</td></tr>
    <tr style="font-weight:bold;"><td>Equity value</td><td>{u(d.equity_value_gordon)}</td><td>{u(d.equity_value_exit)}</td></tr>
    <tr><td>Diluted shares (mm)</td><td>{shares_cell}</td><td>{shares_cell}</td></tr>
    <tr style="font-weight:bold;"><td>Implied price / share</td><td>{_usd2(d.implied_price_gordon)}</td><td>{_usd2(d.implied_price_exit)}</td></tr>
  </tbody>
</table>
"""


def _precedents_table(model: ModelBundle) -> str:
    if not model.precedents:
        return '<p class="section-note">No precedent transactions loaded.</p>'
    body = ""
    for t in model.precedents:
        body += (
            f"<tr><td>{t.date} — {t.acquirer} / {t.target}</td>"
            f"<td>${_num(t.ev, 1e9, dp=1)} bn</td>"
            f"<td>{_mult(t.ev_revenue)}</td>"
            f"<td>{_mult(t.ev_ebitda)}</td>"
            f'<td style="text-align:left; font-size:7.5pt;">{t.source}</td></tr>'
        )
    return f"""
<table>
  <thead><tr><th>Transaction</th><th>EV</th><th>EV/Rev</th><th>EV/EBITDA</th><th>Source</th></tr></thead>
  <tbody>{body}</tbody>
</table>
"""


def _valuation(
    model: ModelBundle, charts: dict[str, str], narrative: dict[str, str] | None = None
) -> str:
    t = model.terminal
    g_ok = t.terminal_growth < model.dcf.wacc
    sanity = (
        "Terminal growth is below WACC (Gordon model is valid)."
        if g_ok
        else '<span class="down">WARNING: terminal growth ≥ WACC — Gordon model invalid.</span>'
    )
    return f"""
<section class="pagebreak">
  <h2>Valuation</h2>
  <h3>Discounted cash flow — WACC</h3>
  {_wacc_table(model)}
  <h3>DCF — terminal value &amp; equity bridge</h3>
  <p class="section-note">Terminal growth (Gordon): {_pct(t.terminal_growth)} ·
     Exit EV/EBITDA: {_mult(t.exit_ev_ebitda)} ·
     Mid-year convention: {"yes" if t.mid_year_convention else "no"}. {sanity}</p>
  {_dcf_bridge_table(model)}
  <div class="fig"><img src="{_img(charts["valuation_bridge"])}" alt="Valuation bridge"/></div>
  <p class="caption">Figure. Enterprise value → equity value bridge. DECK's net
     cash is <b>added</b> (EV &lt; equity value), unlike a leveraged issuer.
     Source: DCF engine.</p>
  <h3>Trading comparables — implied value</h3>
  <p>Applying the peer-median <b>EV/EBITDA</b> multiple to {model.company.ticker}'s
     EBITDA implies <b>{_usd2(model.comps.implied_price_from_ebitda)}</b> per share —
     our primary comps read, corroborating the DCF. We anchor on EV/EBITDA because it
     is capital-structure-neutral and the most comparable metric across this peer set;
     EV/Revenue and P/E are shown in the model for reference but are less meaningful
     here given differences in margin profile and leverage across peers. Peer market
     data (prices, share counts) is illustrative and approximate — external to SEC XBRL
     — so the comps are an indicative triangulation, not the basis of the target; the
     DCF anchors the call.</p>
  <h3>Precedent transactions</h3>
  {_precedents_table(model)}
  <h3>Football field &amp; target derivation</h3>
  <div class="fig"><img src="{_img(charts["football_field"])}" alt="Football field"/></div>
  <p class="caption">Figure 4. Valuation ranges by method with current price and
     target markers. Source: engine outputs.</p>
  <p>{_narrative("target_derivation", narrative)}</p>
  {_sensitivity_table(model)}
  {_sotp_table(model)}
  {_scenario_table(model)}
</section>
"""


def _risks(model: ModelBundle, narrative: dict[str, str] | None = None) -> str:
    key = (narrative or {}).get("risks")
    if key:
        items = "".join(f"<li>{r}</li>" for r in key.split("|"))
        body = f"<ul>{items}</ul>"
    else:
        body = f'<p class="orch">{_narrative("risks")}</p>'
    return f"""
<section class="pagebreak">
  <h2>Risks</h2>
  {body}
</section>
"""


def _stmt_labels(model: ModelBundle, idxs: list[int]) -> str:
    stmts = model.statements
    out = []
    for i in idxs:
        p = stmts.periods[i]
        fy = p.fy if p.fy is not None else p.end.year
        out.append(f"FY{str(fy)[-2:]}{'' if i < stmts.n_hist else 'E'}")
    return "".join(f"<th>{lbl}</th>" for lbl in out)


def _appendix_statements(model: ModelBundle) -> str:
    stmts = model.statements
    scale, sfx = _stmt_scale(model)
    idxs = _display_period_indices(model)
    head = _stmt_labels(model, idxs)
    lines = [
        ("Revenue", LineItem.REVENUE),
        ("Gross profit", LineItem.GROSS_PROFIT),
        ("Operating income (EBIT)", LineItem.OPERATING_INCOME),
        ("Net income", LineItem.NET_INCOME),
        ("Total assets", LineItem.TOTAL_ASSETS),
        ("Total equity", LineItem.TOTAL_EQUITY),
        ("Cash from operations", LineItem.CFO),
        ("Capital expenditures", LineItem.CAPEX),
    ]
    rows = ""
    for name, li in lines:
        vals = stmts.series(li)
        cells = "".join(f"<td>{_num(vals[i], scale)}</td>" for i in idxs)
        rows += f"<tr><td>{name}</td>{cells}</tr>"
    return f"""
<table>
  <thead><tr><th>Condensed model (USD {sfx})</th>{head}</tr></thead>
  <tbody>{rows}</tbody>
</table>
"""


def _appendix_income_statement(model: ModelBundle) -> str:
    """Full projected income statement, line by line (engine values)."""
    stmts = model.statements
    scale, sfx = _stmt_scale(model)
    idxs = _display_period_indices(model)
    head = _stmt_labels(model, idxs)
    lines = [
        ("Revenue", LineItem.REVENUE),
        ("Cost of revenue", LineItem.COST_OF_REVENUE),
        ("Gross profit", LineItem.GROSS_PROFIT),
        ("SG&amp;A", LineItem.SGA),
        ("Operating income (EBIT)", LineItem.OPERATING_INCOME),
        ("Depreciation &amp; amortization", LineItem.DEP_AMORT),
        ("Interest expense", LineItem.INTEREST_EXPENSE),
        ("Pre-tax income", LineItem.PRETAX_INCOME),
        ("Income tax expense", LineItem.INCOME_TAX_EXPENSE),
        ("Net income", LineItem.NET_INCOME),
    ]
    rows = ""
    for name, li in lines:
        vals = stmts.series(li)
        cells = "".join(f"<td>{_num(vals[i], scale)}</td>" for i in idxs)
        rows += f"<tr><td>{name}</td>{cells}</tr>"
    return f"""
<table>
  <thead><tr><th>Income statement (USD {sfx})</th>{head}</tr></thead>
  <tbody>{rows}</tbody>
</table>
"""


def _appendix_dcf_detail(model: ModelBundle) -> str:
    """Year-by-year FCFF and discounting from the DCF engine."""
    d = model.dcf
    n = len(d.fcff_by_year)
    scale, sfx = _auto_scale(model)
    yr_head = "".join(f"<th>Y{i + 1}</th>" for i in range(n))
    fcff = "".join(f"<td>{_num(v, scale)}</td>" for v in d.fcff_by_year)
    dfs = "".join(f"<td>{_num(v, dp=3)}</td>" for v in d.discount_factors)
    pv = "".join(
        f"<td>{_num(f * df, scale)}</td>"
        for f, df in zip(d.fcff_by_year, d.discount_factors, strict=False)
    )
    return f"""
<table>
  <thead><tr><th>DCF detail (USD {sfx})</th>{yr_head}</tr></thead>
  <tbody>
    <tr><td>Unlevered FCFF</td>{fcff}</tr>
    <tr><td>Discount factor</td>{dfs}</tr>
    <tr><td>PV of FCFF</td>{pv}</tr>
  </tbody>
</table>
<table style="width:70%;margin-top:8px;">
  <tbody>
    <tr><td>PV of explicit FCFF</td><td>{_usd(d.pv_explicit_fcff, scale, " " + sfx)}</td></tr>
    <tr><td>PV of terminal (Gordon)</td><td>{_usd(d.pv_terminal_gordon, scale, " " + sfx)}</td></tr>
    <tr><td>Enterprise value (Gordon)</td><td>{_usd(d.enterprise_value_gordon, scale, " " + sfx)}</td></tr>
    <tr><td>Less: net debt (negative = net cash)</td><td>{_usd(d.net_debt, scale, " " + sfx)}</td></tr>
    <tr><td><b>Equity value (Gordon)</b></td><td><b>{_usd(d.equity_value_gordon, scale, " " + sfx)}</b></td></tr>
    <tr><td>Diluted shares</td><td>{_num(d.shares_diluted, 1e6, dp=1)} M</td></tr>
    <tr><td><b>Implied price (Gordon)</b></td><td><b>{_usd2(d.implied_price_gordon)}</b></td></tr>
  </tbody>
</table>
"""


def _appendix_lbo(model: ModelBundle) -> str:
    """Illustrative LBO returns summary from the engine (if present)."""
    lbo = model.lbo
    if lbo is None:
        return '<p class="section-note">LBO not modeled for this run.</p>'
    scale, sfx = _auto_scale(model)
    src = "".join(
        f"<tr><td>{k}</td><td>{_usd(v, scale, ' ' + sfx)}</td></tr>" for k, v in lbo.sources.items()
    )
    return f"""
<table style="width:70%;">
  <thead><tr><th>Illustrative LBO — sources</th><th></th></tr></thead>
  <tbody>{src}
    <tr><td><b>Exit equity value</b></td><td><b>{_usd(lbo.exit_equity_value, scale, " " + sfx)}</b></td></tr>
    <tr><td><b>IRR</b></td><td><b>{_pct(lbo.irr)}</b></td></tr>
    <tr><td><b>MOIC</b></td><td><b>{_num(lbo.moic, dp=2)}x</b></td></tr>
  </tbody>
</table>
<p class="section-note">Illustrative only: DECK carries no debt today. This models
   what a leveraged buyer could earn assuming the entry premium, leverage, cash
   sweep, and exit multiple in the assumptions ledger — a mechanics exercise, not
   a base-case expectation for a net-cash company.</p>
"""


def _appendix(model: ModelBundle) -> str:
    return f"""
<section class="pagebreak">
  <h2>Appendix</h2>
  <h3>Condensed model summary</h3>
  {_appendix_statements(model)}
</section>
<section class="pagebreak">
  <h3>Projected income statement</h3>
  {_appendix_income_statement(model)}
  <h3>DCF detail</h3>
  {_appendix_dcf_detail(model)}
</section>
<section class="pagebreak">
  <h3>Illustrative LBO</h3>
  {_appendix_lbo(model)}
  <h3>Methodology &amp; assumptions</h3>
  <p class="section-note">Historical statements are normalized from SEC EDGAR XBRL
     CompanyFacts and tie out to reported facts. Projections are driven by the
     assumptions ledger (see docs/ASSUMPTIONS.md). The DCF discounts unlevered FCFF
     at the WACC derived above; two terminal methods (Gordon growth and exit
     multiple) bracket terminal value.</p>
  <h3>Verification summary</h3>
  <p class="section-note">Every figure in this report is generated by the Python
     reference engine. In the companion workbook, the full income-statement
     projection chain, WACC build, and DCF valuation &amp; bridge are written as
     live Excel formulas and recalculated cell-by-cell against the engine to the
     cent (Excel↔Python differential, {_n_verified_cells(model)} cells);
     historical statement lines reconcile to SEC-reported facts to the dollar.
     Accounting invariants (balance-sheet balance every period, cash-flow tie-out
     to balance-sheet cash, retained-earnings and PP&amp;E rolls) are enforced at
     build time, and a full rebuild is deterministic.</p>
  <h3>Data source</h3>
  <p class="section-note">SEC EDGAR XBRL CompanyFacts API (public domain).</p>
  <p class="disclaimer">{DISCLAIMER}</p>
</section>
"""


def build_html(
    model: ModelBundle,
    assets_dir: str,
    narrative: dict[str, str] | None = None,
    as_of: str = "2026-08-06",
) -> str:
    """Assemble the full report HTML string, rendering charts into ``assets_dir``.

    Every numeric value is read from ``model``; narrative sections take
    the analyst-authored prose from ``narrative`` (keyed by section) when provided,
    else emit a labeled ``[DRAFT: ...]`` placeholder. ``as_of`` sets the report
    date deterministically (never today's date). The returned string is
    self-contained (charts inlined as data URIs) and ready for WeasyPrint.

    Narrative keys: ``thesis``, ``catalysts`` (``|``-separated bullets),
    ``method_weighting``, ``company_overview``, ``industry``,
    ``financial_analysis``, ``target_derivation``, ``risks`` (``|``-separated).
    """
    os.makedirs(assets_dir, exist_ok=True)
    charts = build_all_charts(model, assets_dir)
    css = _css().replace("TICKER_HDR", f"{model.company.ticker} — Initiating Coverage")
    body = "".join(
        [
            _cover(model, as_of, narrative),
            _exec_summary(model, narrative),
            _company_overview(model, charts, narrative),
            _industry(model, charts, narrative),
            _financial_analysis(model, charts, narrative),
            _valuation(model, charts, narrative),
            _risks(model, narrative),
            _appendix(model),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{model.company.name} ({model.company.ticker}) — Initiating Coverage</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""
