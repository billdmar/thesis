"""the verifier — the verification gates (the moat).

Exports the differential verifier, the Excel banker-convention audit, the
report-number lint, and the tie-out / invariant runners.
"""

from __future__ import annotations

from src.verify.audit import AuditReport, audit_workbook
from src.verify.invariants import InvariantReport, InvariantResult, run_all
from src.verify.recalc import WorkbookVerifier
from src.verify.report_lint import LintReport, collect_engine_numbers, lint_report_numbers
from src.verify.tieout import TieOutLine, TieOutReport, balance_sheet_ties, tie_out_historical

__all__ = [
    "WorkbookVerifier",
    "AuditReport",
    "audit_workbook",
    "LintReport",
    "lint_report_numbers",
    "collect_engine_numbers",
    "InvariantReport",
    "InvariantResult",
    "run_all",
    "TieOutLine",
    "TieOutReport",
    "tie_out_historical",
    "balance_sheet_ties",
]
