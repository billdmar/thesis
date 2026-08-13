"""G3 report-lint gate — every number in the RENDERED report is engine-sourced.

Unlike the earlier synthetic-set unit tests, this runs the lint against the
actual flagship report HTML: extract every financial figure the report renders
and assert each traces to an engine output (or a documented cited narrative
fact). This is the gate the project/README claim as "report-lint," now wired to
the real artifact. Offline (no live EDGAR).
"""

from __future__ import annotations

from src.flagship import build_flagship
from src.narrative import DECK_NARRATIVE
from src.report.template import build_html
from src.verify.report_lint import (
    collect_engine_numbers,
    extract_report_numbers,
    lint_report_numbers,
)


def test_rendered_report_numbers_are_all_engine_sourced(tmp_path):
    model = build_flagship()
    html = build_html(model, str(tmp_path / "assets"), narrative=DECK_NARRATIVE, as_of="2026-08-06")
    rendered = extract_report_numbers(html)
    engine = collect_engine_numbers(model)
    report = lint_report_numbers(rendered, engine)
    assert report.numbers_checked > 50, "expected the report to render many figures"
    assert report.passed, f"unsourced rendered numbers: {sorted(report.unsourced)}"


def test_lint_catches_a_fabricated_number(tmp_path):
    # Inject a fabricated number into a TABLE (an exhibit) → must be flagged.
    model = build_flagship()
    html = build_html(model, str(tmp_path / "assets"), narrative=DECK_NARRATIVE, as_of="2026-08-06")
    html_tampered = html.replace(
        "</table>", "<tr><td>Fabricated</td><td>$8,675.31</td></tr></table>", 1
    )
    rendered = extract_report_numbers(html_tampered)
    report = lint_report_numbers(rendered, collect_engine_numbers(model))
    assert not report.passed
    assert any(abs(x - 8675.31) < 0.01 for x in report.unsourced)


def test_extractor_scopes_to_tables_and_ignores_dates_fy_labels():
    html = (
        "<p>Prose 999.99 not in scope.</p>"
        "<table><tr><td>Revenue FY27E on 2024-12-17</td><td>5.5</td>"
        "<td>128.00</td></tr></table>"
    )
    nums = extract_report_numbers(html)
    assert 5.5 in nums and 128.0 in nums
    assert 999.99 not in nums  # prose is out of scope (tables_only)
    assert 2024 not in nums and 27 not in nums and 17 not in nums


def test_extractor_tolerates_malformed_numeric_tokens():
    # Bare/stray tokens (a lone dash, a trailing-dot fragment) and $-signs must not
    # crash the extractor or parse into spurious floats — it skips what it can't
    # cleanly read and still pulls the real figure.
    html = "<table><tr><td>-</td><td>$</td><td>.</td><td>4,321.00</td></tr></table>"
    nums = extract_report_numbers(html)
    assert 4321.0 in nums
    # No junk parsed from the stray '-', '$', or lone '.'.
    assert all(n == 4321.0 for n in nums)
