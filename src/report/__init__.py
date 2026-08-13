"""Initiating-coverage report package: charts, HTML template, PDF render.

Public API: :func:`build_html` (testable HTML string) and
:func:`render_report` (full PDF). Both bind every figure to a ``ModelBundle``.
"""

from src.report.render import render_report
from src.report.template import build_html

__all__ = ["build_html", "render_report"]
