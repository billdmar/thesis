"""Excel<->Python cell-level differential (the moat) — the verification gate machinery.

Loads a live-formula workbook with the ``formulas`` library, recalculates it,
and for every ``(sheet, cell)`` in :func:`~src.workbook.build_verifier_cell_map`
asserts the recalculated value matches the engine value to the cent. This is the
reusable :class:`~src.interfaces.Verifier` behind the differential; the standing
test in ``tests/test_differential_dcf.py`` exercises the same recalc pattern.

The ``formulas`` solution keys are addressed as ``'[<filename>]<SHEET>'!<COORD>``
with the sheet name uppercased and the filename taken from the workbook's on-disk
basename (original case). A missing node or an out-of-tolerance value is a
mismatch and fails :attr:`DifferentialReport.passed`.
"""

from __future__ import annotations

import os

import formulas

from src.interfaces import CellDiff, DifferentialReport, ModelBundle
from src.workbook import build_verifier_cell_map


class WorkbookVerifier:
    """Concrete :class:`~src.interfaces.Verifier`. See module docstring."""

    def recalc_and_diff(
        self, workbook_path: str, model: ModelBundle, tol: float = 0.01
    ) -> DifferentialReport:
        """Recalculate ``workbook_path`` and diff every mapped cell vs the engine.

        Returns a :class:`DifferentialReport` whose ``mismatches`` holds only the
        cells that failed (``passed`` is true when that list is empty).
        """
        xl = formulas.ExcelModel().loads(str(workbook_path)).finish()
        sol = xl.calculate()
        fname = os.path.basename(str(workbook_path))

        cell_map = build_verifier_cell_map(model)
        mismatches: list[CellDiff] = []
        for (sheet, coord), engine_value in cell_map.items():
            wb_value = self._recalc_cell(sol, fname, sheet, coord)
            ok = wb_value is not None and abs(wb_value - engine_value) <= tol
            if not ok:
                mismatches.append(
                    CellDiff(
                        sheet=sheet,
                        cell=coord,
                        engine_value=engine_value,
                        workbook_value=wb_value,
                        ok=False,
                    )
                )
        return DifferentialReport(cells_checked=len(cell_map), mismatches=mismatches)

    @staticmethod
    def _recalc_cell(sol, fname: str, sheet: str, coord: str) -> float | None:
        """Look up one recalculated cell value in the ``formulas`` solution."""
        node = sol.get(f"'[{fname}]{sheet.upper()}'!{coord}")
        return None if node is None else float(node.value[0, 0])
