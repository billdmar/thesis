#!/usr/bin/env python
"""Build every DECK deliverable from cached data, in one command.

    python scripts/build_deliverables.py

Deterministic: the model is built once via :func:`build_flagship` and every
artifact is derived from that single bundle, so a rebuild reproduces identical
bytes (the determinism requirement). No number is hand-typed here — the script
only orchestrates the writers.

Outputs
    out/DECK_model.xlsx                 live-formula workbook (scratch)
    out/DECK_initiating_coverage.pdf    initiating-coverage report (scratch)
    out/assets/*.png                    rendered charts (scratch)
    releases/DECK_model.xlsx            committed deliverable (release asset)
    releases/DECK_initiating_coverage.pdf   committed deliverable (PDF blob)
    docs/index.html                     GitHub Pages landing page
    docs/img/football_field.png         hero chart (README + Pages)
    docs/img/valuation_bridge.png       hero chart (README + Pages)

macOS: WeasyPrint's native libs live under the Homebrew prefix — set here before
any import triggers the native load. Inert on CI/Linux.
"""

from __future__ import annotations

# Must precede any import that transitively loads WeasyPrint's native deps.
import os

os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

import shutil  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# Make ``src`` importable no matter the invocation directory (a bare
# ``python scripts/build_deliverables.py`` puts scripts/ on the path, not root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.flagship import AS_OF, build_flagship  # noqa: E402
from src.narrative import DECK_NARRATIVE  # noqa: E402
from src.report.landing import write_landing_page  # noqa: E402
from src.report.render import render_report  # noqa: E402
from src.workbook import ExcelWorkbookWriter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
ASSETS = OUT / "assets"
RELEASES = ROOT / "releases"
DOCS = ROOT / "docs"
DOCS_IMG = DOCS / "img"

XLSX_NAME = "DECK_model.xlsx"
PDF_NAME = "DECK_initiating_coverage.pdf"
# Hero charts surfaced on the README + Pages (rendered into out/assets by the
# report pipeline; copied to docs/img so they render on GitHub without a build).
HERO_CHARTS = ("football_field.png", "valuation_bridge.png")


def _manifest_line(path: Path) -> str:
    kb = path.stat().st_size / 1024
    return f"  {path.relative_to(ROOT)}  ({kb:,.1f} KB)"


def main() -> None:
    for d in (OUT, ASSETS, RELEASES, DOCS, DOCS_IMG):
        d.mkdir(parents=True, exist_ok=True)

    # Single source of truth: build the bundle once, derive everything from it.
    model = build_flagship()

    written: list[Path] = []

    # 1. Live-formula workbook.
    xlsx_out = OUT / XLSX_NAME
    ExcelWorkbookWriter().write(str(xlsx_out), model)
    written.append(xlsx_out)

    # 2. Initiating-coverage PDF (charts rendered into out/assets, inlined).
    pdf_out = OUT / PDF_NAME
    render_report(model, str(pdf_out), str(ASSETS), narrative=DECK_NARRATIVE, as_of=AS_OF)
    written.append(pdf_out)

    # 3. GitHub Pages landing page (self-contained; charts inlined). Reuses the
    #    charts already rendered into out/assets.
    index_out = DOCS / "index.html"
    write_landing_page(
        model, str(index_out), assets_dir=str(ASSETS), narrative=DECK_NARRATIVE, as_of=AS_OF
    )
    written.append(index_out)

    # 4. Publish committed deliverables into releases/ (release assets + PDF blob).
    for name in (XLSX_NAME, PDF_NAME):
        dst = RELEASES / name
        shutil.copyfile(OUT / name, dst)
        written.append(dst)

    # 5. Copy the two hero charts into docs/img for the README + Pages.
    for chart in HERO_CHARTS:
        dst = DOCS_IMG / chart
        shutil.copyfile(ASSETS / chart, dst)
        written.append(dst)

    print("Built DECK deliverables (deterministic):")
    for p in written:
        print(_manifest_line(p))


if __name__ == "__main__":
    main()
