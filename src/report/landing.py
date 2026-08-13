"""Screen-styled landing page — the reviewer-facing front door on GitHub Pages.

This is the one-click surface for a reviewer who will NOT clone or run the repo:
the headline call, the two deliverables (report PDF, Excel model), the valuation
triangulation, and the verification moat — all on one self-contained HTML page.

Distinct from :mod:`src.report.template` (the print ``@page`` PDF): this uses a
screen stylesheet and inlines its charts as data URIs, so the emitted file needs
no external assets. It is intentionally PDF-free — it imports no WeasyPrint — so
its tests run without the native pango/cairo libraries.

Single source of truth, same rule as the PDF: every financial figure is read
from the passed :class:`ModelBundle` or a ``src.flagship`` constant; nothing
numeric is hand-typed. Verification counts (XBRL tie-out lines, differentially
verified workbook cells) are recomputed from the engine so the page's claims can
never drift from the actual coverage.
"""

from __future__ import annotations

import os

from src.interfaces import ModelBundle
from src.report.charts import build_all_charts
from src.report.template import (
    DISCLAIMER,
    _img,
    _mult,
    _n_verified_cells,
    _pct,
    _report_date,
    _upside,
    _usd2,
)

# --- Canonical outward-facing links (blob = inline render; release = latest asset) ---
REPO_URL = "https://github.com/billdmar/thesis"
# The GitHub Pages URL is the link shared in outreach messages; og:/twitter:
# tags below make it unfurl as a rich card, not a bare link.
PAGES_URL = "https://billdmar.github.io/thesis/"
OG_IMAGE_URL = f"{PAGES_URL}img/football_field.png"
# Both deliverables link to the Release assets: a direct download that opens in
# the reader's native PDF/Excel viewer, not GitHub's in-repo blob viewer (which
# is slow and alien to a non-engineer — the report is the key proof of the work).
PDF_URL = f"{REPO_URL}/releases/latest/download/DECK_initiating_coverage.pdf"
XLSX_URL = f"{REPO_URL}/releases/latest/download/DECK_model.xlsx"
LINKEDIN_URL = "https://www.linkedin.com/in/williamdmar/"
ASSUMPTIONS_URL = f"{REPO_URL}/blob/main/docs/ASSUMPTIONS.md"

BYLINE = "William Mar"


def _tieout_count(model: ModelBundle) -> int:
    """Number of historical statement lines that reconcile to SEC facts, read
    from the same tie-out gate the verifier runs — so the page's "N/N tie-out"
    claim is sourced, never hand-typed."""
    from src.edgar import load_normalized_facts
    from src.verify.tieout import tie_out_historical

    nf = load_normalized_facts(model.company.ticker)
    return tie_out_historical(model.statements, nf).checked


def _thesis_slice(narrative: dict[str, str] | None) -> str:
    """The elevator version of the thesis: the setup PLUS the analyst's actual
    view. Takes the first three sentences so the slice ends on the call ("we
    think that fear is overpriced…"), not the bear setup — a two-sentence cut
    stops mid-argument and reads as if it contradicts the Buy. Prose, so it lives
    outside the number-lint's table scope (like the PDF narrative)."""
    thesis = (narrative or {}).get("thesis", "")
    parts = thesis.split(". ")
    return ". ".join(parts[:3]).rstrip(".") + "." if parts and parts[0] else ""


def _css() -> str:
    """Screen stylesheet — a restrained navy/steel research aesthetic that reads
    on a phone or a reviewer's laptop. Not the print @page template."""
    return """
:root {
  --accent: #1f3b57; --steel: #5b7c99; --muted: #6b7680; --line: #d8dee3;
  --up: #2f6f4f; --paper: #ffffff; --wash: #f5f7f9; --ink: #1c2429;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--wash); color: var(--ink);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5; }
.wrap { max-width: 960px; margin: 0 auto; padding: 0 20px 56px; }
a { color: var(--accent); }
h1 { font-family: Georgia, "Times New Roman", serif; font-size: 2.1rem;
  margin: 0 0 2px; color: var(--accent); }
h2 { font-size: 1.15rem; color: var(--accent); border-bottom: 2px solid var(--accent);
  padding-bottom: 5px; margin: 40px 0 14px; }
.sub { color: var(--steel); font-size: .95rem; margin: 0 0 6px; }
.byline { color: var(--muted); font-size: .9rem; margin: 2px 0 0; }
header { background: var(--paper); border-bottom: 1px solid var(--line);
  padding: 34px 0 26px; }
.badge { display: inline-block; background: var(--accent); color: #fff;
  font-weight: 700; letter-spacing: .04em; padding: 5px 14px; border-radius: 3px;
  font-size: 1rem; vertical-align: middle; }
.stats { display: flex; flex-wrap: wrap; gap: 14px; margin: 20px 0 4px; }
.stat { background: var(--wash); border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 18px; min-width: 150px; flex: 1; }
.stat .k { color: var(--steel); font-size: .78rem; text-transform: uppercase;
  letter-spacing: .05em; }
.stat .v { font-size: 1.5rem; font-weight: 700; color: var(--accent); margin-top: 3px; }
.stat .v.up { color: var(--up); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 4px; }
.cta a { display: inline-block; text-decoration: none; font-weight: 600;
  padding: 12px 22px; border-radius: 6px; font-size: 1rem; }
.cta a.primary { background: var(--accent); color: #fff; }
.cta a.secondary { background: #fff; color: var(--accent); border: 1.5px solid var(--accent); }
.figs { display: flex; flex-wrap: wrap; gap: 18px; }
.figs figure { flex: 1; min-width: 300px; margin: 0; }
.figs img { width: 100%; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
figcaption { color: var(--steel); font-size: .8rem; font-style: italic; margin-top: 6px; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: .95rem;
  border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
th, td { text-align: right; padding: 9px 14px; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child { text-align: left; }
thead th { background: var(--accent); color: #fff; font-weight: 600; }
tbody tr:last-child td { border-bottom: none; }
.moat { background: #fff; border: 1px solid var(--line); border-left: 4px solid var(--accent);
  border-radius: 6px; padding: 6px 22px; }
.moat li { margin: 8px 0; }
.moat b { color: var(--accent); }
.thesis { background: #fff; border: 1px solid var(--line); border-radius: 6px;
  padding: 16px 22px; font-size: 1.02rem; }
.links { display: flex; flex-wrap: wrap; gap: 10px 26px; margin: 8px 0; padding: 0; list-style: none; }
.note { color: var(--steel); font-size: .82rem; }
.disclaimer { color: var(--muted); font-size: .78rem; border-top: 1px solid var(--line);
  margin-top: 40px; padding-top: 14px; }
"""


def _hero(model: ModelBundle, as_of: str) -> str:
    """Name, rating badge, and the three headline stat cards (target / price /
    upside). Cards are styled divs (not a lint-scanned table); each renders an
    engine or ``src.flagship``-constant value through the shared formatters."""
    c = model.company
    up = _upside(model)
    up_txt = _pct(up) if up is not None else "—"
    up_word = "upside" if (up or 0) >= 0 else "downside"
    rating = model.rating or "—"
    return f"""
<header>
  <div class="wrap">
    <h1>{c.name} <span class="note">({c.ticker})</span></h1>
    <p class="sub">Initiating Coverage · Independent equity research · as of {_report_date(as_of)}</p>
    <p style="margin:14px 0 0;"><span class="badge">{rating}</span></p>
    <div class="stats">
      <div class="stat"><div class="k">12-month price target</div>
        <div class="v">{_usd2(model.price_target)}</div></div>
      <div class="stat"><div class="k">Current price</div>
        <div class="v">{_usd2(model.current_price)}</div></div>
      <div class="stat"><div class="k">Implied {up_word}</div>
        <div class="v up">{up_txt}</div></div>
    </div>
    <p class="byline">{BYLINE} · <a href="{LINKEDIN_URL}">LinkedIn</a> ·
      educational project, not investment advice</p>
  </div>
</header>
"""


def _cta() -> str:
    return f"""
<div class="cta">
  <a class="primary" href="{PDF_URL}">Read the report (PDF)</a>
  <a class="secondary" href="{XLSX_URL}">Download the model (Excel)</a>
</div>
"""


def _charts(charts: dict[str, str]) -> str:
    return f"""
<h2>Valuation at a glance</h2>
<div class="figs">
  <figure>
    <img src="{_img(charts["football_field"])}" alt="Football field — valuation range by method"/>
    <figcaption>Valuation range by method, with current price and target markers.</figcaption>
  </figure>
  <figure>
    <img src="{_img(charts["valuation_bridge"])}" alt="Enterprise value to equity bridge"/>
    <figcaption>EV → equity bridge — net cash is added back (EV &lt; equity value).</figcaption>
  </figure>
</div>
"""


def _triangulation_table(model: ModelBundle) -> str:
    """Method-by-method implied value + the derived-from-engine cross-checks.
    Every cell is an engine output, so the number-lint verifies this exhibit
    end-to-end (the same guarantee the PDF's tables carry)."""
    d = model.dcf
    comps_px = model.comps.implied_price_from_ebitda
    rows = (
        f"<tr><td>DCF — Gordon growth</td><td>{_usd2(d.implied_price_gordon)}</td></tr>"
        f"<tr><td>DCF — exit multiple ({_mult(model.terminal.exit_ev_ebitda)})</td>"
        f"<td>{_usd2(d.implied_price_exit)}</td></tr>"
        f"<tr><td>Trading comps — peer EV/EBITDA</td><td>{_usd2(comps_px)}</td></tr>"
    )
    if model.scenarios is not None:
        by = {s.name: s.implied_price_mid for s in model.scenarios.scenarios}
        rows += (
            f"<tr><td>Scenario — bear (mid)</td><td>{_usd2(by.get('Bear'))}</td></tr>"
            f"<tr><td>Scenario — bull (mid)</td><td>{_usd2(by.get('Bull'))}</td></tr>"
        )
    lbo = ""
    if model.lbo is not None:
        lbo = (
            f"<tr><td>Illustrative LBO — IRR / MOIC</td>"
            f"<td>{_pct(model.lbo.irr)} · {_mult(model.lbo.moic, dp=1)}</td></tr>"
        )
    return f"""
<h2>How the target triangulates</h2>
<table>
  <thead><tr><th>Method</th><th>Implied value / return</th></tr></thead>
  <tbody>
    {rows}
    <tr><td>WACC (net-cash ⇒ = cost of equity)</td><td>{_pct(model.dcf.wacc, dp=2)}</td></tr>
    {lbo}
  </tbody>
</table>
<p class="note">Each row runs the same reference engine; the DCF anchors the call
   and comps corroborate. Scenario rows are the bull/base/bear midpoints. The comps
   use illustrative, approximate peer market data (external to SEC XBRL), so they are
   an indicative cross-check. The LBO is illustrative too — DECK is net-cash, so it
   models what leverage <em>could</em> do.</p>
"""


def _moat(model: ModelBundle) -> str:
    """The verification moat, in finance terms. Prose (not a lint-scanned
    exhibit); the two counts are recomputed from the engine, never hand-typed."""
    tie = _tieout_count(model)
    cells = _n_verified_cells(model)
    return f"""
<h2>Why the numbers are trustworthy</h2>
<ul class="moat">
  <li><b>{tie}/{tie} XBRL tie-out</b> — every historical statement line reconciles
    to SEC-reported facts to the dollar.</li>
  <li><b>{cells}-cell Excel↔Python differential</b> — the workbook's live formulas
    (income-statement projection chain, WACC build, DCF valuation &amp; EV→equity
    bridge) are recalculated and matched to an independent Python engine to the cent.</li>
  <li><b>Report-number lint</b> — every figure in every financial exhibit traces
    back to an engine output; a fabricated number fails the build.</li>
  <li><b>Accounting invariants</b> — balance sheet balances every period, cash-flow
    ties to balance-sheet cash, retained-earnings and PP&amp;E rolls hold.</li>
  <li><b>Deterministic rebuild</b> — a full rebuild from cached data reproduces
    identical numbers.</li>
</ul>
"""


def _thesis(narrative: dict[str, str] | None) -> str:
    slice_ = _thesis_slice(narrative)
    if not slice_:
        return ""
    return f"""
<h2>The thesis</h2>
<p class="thesis">{slice_}</p>
"""


def _links() -> str:
    return f"""
<h2>Go deeper</h2>
<ul class="links">
  <li><a href="{ASSUMPTIONS_URL}">Assumptions ledger</a></li>
  <li><a href="{REPO_URL}">Source &amp; verifier (GitHub)</a></li>
  <li><a href="{LINKEDIN_URL}">{BYLINE} on LinkedIn</a></li>
</ul>
"""


def build_landing_html(
    model: ModelBundle,
    assets_dir: str,
    narrative: dict[str, str] | None = None,
    as_of: str = "2026-08-06",
) -> str:
    """Assemble the self-contained landing-page HTML string.

    Renders the chart suite into ``assets_dir`` (scratch) and inlines the two
    hero charts as data URIs, so the returned string references no external
    files. Every numeric value comes from ``model`` or a ``src.flagship``
    constant; ``narrative`` supplies the analyst thesis slice; ``as_of`` sets the
    header date deterministically (never today's date).
    """
    os.makedirs(assets_dir, exist_ok=True)
    charts = build_all_charts(model, assets_dir)
    body = "".join(
        [
            _hero(model, as_of),
            '<div class="wrap">',
            _cta(),
            _thesis(narrative),
            _charts(charts),
            _triangulation_table(model),
            _moat(model),
            _links(),
            f'<p class="disclaimer">{DISCLAIMER}</p>',
            '<p class="disclaimer">Data source: SEC EDGAR XBRL CompanyFacts (public domain).</p>',
            "</div>",
        ]
    )
    page_title = (
        f"{model.company.name} ({model.company.ticker}) — Initiating Coverage · "
        f"{model.rating} {_usd2(model.price_target)}"
    )
    page_desc = (
        f"Independent initiating-coverage research on {model.company.name} "
        f"({model.company.ticker}): {model.rating}, {_usd2(model.price_target)} target. "
        "SEC-EDGAR-driven, machine-verified DCF / comps / LBO model."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{page_title}</title>
<meta name="description" content="{page_desc}"/>
<link rel="canonical" href="{PAGES_URL}"/>
<meta property="og:type" content="website"/>
<meta property="og:title" content="{page_title}"/>
<meta property="og:description" content="{page_desc}"/>
<meta property="og:url" content="{PAGES_URL}"/>
<meta property="og:image" content="{OG_IMAGE_URL}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{page_title}"/>
<meta name="twitter:description" content="{page_desc}"/>
<meta name="twitter:image" content="{OG_IMAGE_URL}"/>
<style>{_css()}</style>
</head>
<body>
{body}
</body>
</html>
"""


def write_landing_page(
    model: ModelBundle,
    out_path: str,
    assets_dir: str | None = None,
    narrative: dict[str, str] | None = None,
    as_of: str = "2026-08-06",
) -> str:
    """Write the landing page to ``out_path``; returns ``out_path``. Charts are
    rendered into ``assets_dir`` (defaults to a sibling ``assets/`` scratch dir)
    and inlined, so the written HTML file is fully self-contained."""
    if assets_dir is None:
        assets_dir = os.path.join(os.path.dirname(out_path) or ".", "assets")
    html = build_landing_html(model, assets_dir, narrative=narrative, as_of=as_of)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path
