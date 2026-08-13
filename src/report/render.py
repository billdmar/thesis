"""PDF rendering of the initiating-coverage report via WeasyPrint.

macOS ARM note: WeasyPrint's native deps (pango/cairo/gobject) live under the
Homebrew prefix; ``import weasyprint`` fails unless that path is on the dyld
fallback path. We set it here before importing WeasyPrint. On CI/Linux this
environment variable is inert.
"""

from __future__ import annotations

import os

# Must be set BEFORE weasyprint is imported (module import triggers native load).
os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

from src.interfaces import ModelBundle  # noqa: E402
from src.report.template import build_html  # noqa: E402


def render_report(
    model: ModelBundle,
    out_path: str,
    assets_dir: str,
    narrative: dict[str, str] | None = None,
    as_of: str = "2026-08-06",
) -> str:
    """Render the full report to a PDF at ``out_path``; returns ``out_path``.

    Charts are written into ``assets_dir`` and inlined into the HTML, so the
    resulting PDF is fully self-contained. Every figure originates from
    ``model`` (single source of truth); ``narrative`` supplies analyst-authored
    prose for the thesis/catalysts/risks/etc. sections (see ``build_html``).
    """
    # Re-assert in case the module was imported before this env var mattered.
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    from weasyprint import HTML  # local import so charts/HTML paths work without native libs

    html = build_html(model, assets_dir, narrative, as_of)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    HTML(string=html).write_pdf(out_path)
    return out_path
