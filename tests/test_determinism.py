"""Determinism gate — a full rebuild reproduces identical deliverables.

the project claims a rebuild is deterministic. This enforces it: the engine
numbers, the workbook BYTES, and the report HTML string must be identical across
two independent builds from the committed fixtures. (The PDF itself is
deterministic modulo WeasyPrint font-subset metadata, so we assert on the HTML
string — the deterministic surface — not raw PDF bytes.)
"""

from __future__ import annotations

import hashlib
import zipfile

from src.flagship import build_flagship
from src.narrative import DECK_NARRATIVE
from src.report.template import build_html
from src.workbook import ExcelWorkbookWriter


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_engine_numbers_are_deterministic():
    a, b = build_flagship(), build_flagship()
    assert a.dcf.wacc == b.dcf.wacc
    assert a.dcf.implied_price_gordon == b.dcf.implied_price_gordon
    assert a.dcf.enterprise_value_gordon == b.dcf.enterprise_value_gordon
    assert a.lbo.irr == b.lbo.irr and a.lbo.moic == b.lbo.moic


def test_workbook_is_byte_identical_across_rebuilds(tmp_path):
    m = build_flagship()
    pa, pb = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    ExcelWorkbookWriter().write(str(pa), m)
    ExcelWorkbookWriter().write(str(pb), m)
    assert _sha(pa) == _sha(pb), "workbook bytes differ across rebuilds (timestamp leak?)"


def test_workbook_zip_timestamps_are_pinned(tmp_path):
    """Cross-process determinism guard: openpyxl otherwise stamps each ZIP entry
    (and docProps/core.xml `modified`) with the current wall-clock time, so two
    builds in different processes/seconds diverge even with identical content.
    The writer pins them; assert every entry carries the fixed epoch."""
    p = tmp_path / "m.xlsx"
    ExcelWorkbookWriter().write(str(p), build_flagship())
    zf = zipfile.ZipFile(p)
    stamps = {info.date_time for info in zf.infolist()}
    assert stamps == {(2026, 1, 1, 0, 0, 0)}, f"unpinned ZIP entry timestamps: {stamps}"
    assert b"2026-01-01T00:00:00Z</dcterms:modified>" in zf.read("docProps/core.xml")


def test_report_html_is_identical_across_rebuilds(tmp_path):
    m = build_flagship()
    h1 = build_html(m, str(tmp_path / "a"), narrative=DECK_NARRATIVE, as_of="2026-08-06")
    h2 = build_html(m, str(tmp_path / "b"), narrative=DECK_NARRATIVE, as_of="2026-08-06")
    assert h1 == h2, "report HTML differs across rebuilds (nondeterministic content?)"
