"""Report-lint gate — the flagship report renders with the analyst narrative, offline.

Confirms the report builds from the flagship bundle + the analyst-authored
narrative with (a) no ``[DRAFT: ...]`` placeholders leaking, (b) the verbatim
disclaimer present, (c) the thesis/rating/target and every required section
present, and (d) no ``None``/``nan`` leaking where a value belongs. The full
PDF render is exercised when weasyprint is importable (skipped otherwise, with
the HTML assertions still running unconditionally).
"""

from __future__ import annotations

import pytest
from src.flagship import build_flagship
from src.narrative import DECK_NARRATIVE
from src.report.template import DISCLAIMER, build_html


def _weasyprint_available() -> bool:
    import os

    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    assets = tmp_path_factory.mktemp("assets")
    return build_html(build_flagship(), str(assets), narrative=DECK_NARRATIVE)


def test_no_placeholders_leak(html):
    assert "[DRAFT:" not in html


def test_disclaimer_present(html):
    assert DISCLAIMER[:60] in html
    for phrase in ("not investment advice", "fair-access", "endorsement"):
        assert phrase.lower() in html.lower()


def test_required_sections_and_headline(html):
    for heading in (
        "Executive Summary",
        "Company Overview",
        "Industry",
        "Financial Analysis",
        "Valuation",
        "Risks",
        "Appendix",
    ):
        assert heading in html
    assert "Buy" in html
    assert "$128" in html  # 12-month target
    assert "HOKA" in html  # thesis prose injected


def test_no_none_or_nan_leaks(html):
    # Honest unknowns render as em dash; literal None/nan must never appear in
    # the VISIBLE text. Strip the inlined base64 chart data URIs first (their
    # random bytes coincidentally contain substrings like "nan").
    import re

    visible = re.sub(r"data:image/png;base64,[^\"']+", "", html)
    visible = re.sub(r"<[^>]+>", " ", visible)  # drop tags/attrs
    assert "None" not in visible
    assert "nan" not in visible.lower().replace("financial", "")


def test_thesis_and_risks_are_authored(html):
    # The thesis and all five risk bullets come from the narrative module.
    assert DECK_NARRATIVE["thesis"][:40] in html
    for risk in DECK_NARRATIVE["risks"].split("|"):
        assert risk[:30] in html


@pytest.mark.skipif(not _weasyprint_available(), reason="weasyprint native libs unavailable")
def test_full_pdf_renders(tmp_path):
    from src.report.render import render_report

    out = tmp_path / "DECK_initiating_coverage.pdf"
    render_report(build_flagship(), str(out), str(tmp_path / "assets"), narrative=DECK_NARRATIVE)
    assert out.exists()
    assert out.stat().st_size > 50_000  # a real multi-page PDF
