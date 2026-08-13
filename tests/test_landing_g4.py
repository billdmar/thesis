"""G4 landing-page gate — the reviewer-facing front door is trustworthy.

Mirrors the G3 report-lint gate (tests/test_report_lint_g3.py) for the screen
landing page: every financial exhibit number is engine-sourced, the headline
matches the flagship constants, no placeholder leaks, the required outward links
are present, and the page is deterministic. PDF-free — no native libs needed.
"""

from __future__ import annotations

from src.flagship import CURRENT_PRICE, PRICE_TARGET, RATING, build_flagship
from src.narrative import DECK_NARRATIVE
from src.report.landing import (
    LINKEDIN_URL,
    PDF_URL,
    REPO_URL,
    XLSX_URL,
    build_landing_html,
    write_landing_page,
)
from src.verify.report_lint import (
    collect_engine_numbers,
    extract_report_numbers,
    lint_report_numbers,
)


def _html(tmp_path) -> str:
    model = build_flagship()
    return build_landing_html(
        model, str(tmp_path / "assets"), narrative=DECK_NARRATIVE, as_of="2026-08-06"
    )


def test_landing_numbers_are_all_engine_sourced(tmp_path):
    model = build_flagship()
    html = build_landing_html(
        model, str(tmp_path / "assets"), narrative=DECK_NARRATIVE, as_of="2026-08-06"
    )
    rendered = extract_report_numbers(html)
    report = lint_report_numbers(rendered, collect_engine_numbers(model))
    assert report.numbers_checked > 0, "expected the landing table to render figures"
    assert report.passed, f"unsourced rendered numbers: {sorted(report.unsourced)}"


def test_landing_headline_matches_flagship_constants(tmp_path):
    html = _html(tmp_path)
    assert RATING in html
    assert f"${PRICE_TARGET:,.2f}" in html  # 12-month target
    assert f"${CURRENT_PRICE:,.2f}" in html  # current price
    upside = f"{(PRICE_TARGET / CURRENT_PRICE - 1.0) * 100:.1f}%"
    assert upside in html  # implied upside


def test_landing_has_no_draft_placeholder_leak(tmp_path):
    assert "[DRAFT:" not in _html(tmp_path)


def test_landing_has_required_links(tmp_path):
    html = _html(tmp_path)
    for url in (PDF_URL, XLSX_URL, LINKEDIN_URL, REPO_URL):
        assert url in html, f"missing required link: {url}"
    # Both deliverables link to Release assets (native-viewer download), not the
    # in-repo blob viewer.
    assert "releases/latest/download/DECK_initiating_coverage.pdf" in html
    assert "releases/latest/download/DECK_model.xlsx" in html


def test_landing_is_deterministic(tmp_path):
    model = build_flagship()
    h1 = build_landing_html(
        model, str(tmp_path / "a"), narrative=DECK_NARRATIVE, as_of="2026-08-06"
    )
    h2 = build_landing_html(
        model, str(tmp_path / "b"), narrative=DECK_NARRATIVE, as_of="2026-08-06"
    )
    assert h1 == h2, "landing HTML differs across rebuilds (nondeterministic content?)"


def test_write_landing_page_writes_self_contained_file(tmp_path):
    model = build_flagship()
    out = tmp_path / "index.html"
    write_landing_page(model, str(out), narrative=DECK_NARRATIVE, as_of="2026-08-06")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    # Self-contained: charts inlined as data URIs, no external asset references.
    assert "data:image/png;base64," in html
    assert 'src="assets/' not in html


def test_landing_has_social_unfurl_meta(tmp_path):
    # The Pages URL is shared in outreach messages; the og:/twitter: tags make
    # it unfurl as a rich card with a preview image.
    html = _html(tmp_path)
    for tag in (
        'property="og:title"',
        'property="og:description"',
        'property="og:image"',
        'property="og:url"',
        'name="twitter:card" content="summary_large_image"',
        'rel="canonical"',
    ):
        assert tag in html, f"missing social/unfurl meta: {tag}"
    # og:image is an absolute URL (relative images don't unfurl).
    assert "https://billdmar.github.io/thesis/img/football_field.png" in html


def test_thesis_slice_states_the_call_not_just_the_bear_setup(tmp_path):
    # Guard against the truncation defect: the elevator thesis must include the
    # analyst's actual view ("we think that fear is overpriced"), not stop on the
    # bear setup — otherwise the landing page reads as if it contradicts the Buy.
    html = _html(tmp_path)
    assert "<h2>The thesis</h2>" in html
    assert "overpriced" in html.lower()


def test_thesis_section_omitted_without_narrative(tmp_path):
    # No narrative → the thesis slice is empty and its section is dropped, not
    # rendered as an empty/placeholder block.
    model = build_flagship()
    html = build_landing_html(model, str(tmp_path / "assets"), narrative=None)
    assert "<h2>The thesis</h2>" not in html
    assert "[DRAFT:" not in html
