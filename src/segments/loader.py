"""Segment (brand-level) data loader.

DECK's brand-level net sales (HOKA, UGG, and other) are disclosed in the 10-K
"Business Segments" / disaggregation-of-revenue footnote, but NOT in the core
us-gaap income-statement CompanyFacts tags the engine normalizes. So brand
figures are a **curated, hand-sourced input** — a documented, labeled exception
to the engine-only rule — loaded from a committed CSV where every row carries
its 10-K citation. This module validates and structures that CSV; it never
fabricates a figure.
"""

from __future__ import annotations

import csv

from src.interfaces import Segment, SegmentSet, SegmentYear


def load_segments(csv_path: str) -> SegmentSet:
    """Load brand-level segment revenue/op-income from a sourced CSV.

    Columns: ``segment,fiscal_year,revenue,operating_income,source``. Revenue is
    required; operating_income may be blank (honest-unknown → None). Values are
    in raw USD. Rows are grouped by segment and ordered by fiscal year.
    """
    by_segment: dict[str, list[SegmentYear]] = {}
    sources: dict[str, str] = {}
    required = {"segment", "fiscal_year", "revenue"}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing_cols = required - set(reader.fieldnames or [])
        if missing_cols:
            raise ValueError(
                f"segment CSV {csv_path} missing required column(s): {sorted(missing_cols)}"
            )
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            name = row["segment"].strip()
            rev_raw = (row.get("revenue") or "").strip()
            if not rev_raw:
                raise ValueError(f"segment CSV {csv_path} row {i} ({name}): revenue is required")
            try:
                rev = float(rev_raw)
                fy = int(row["fiscal_year"])
            except ValueError as e:
                raise ValueError(f"segment CSV {csv_path} row {i} ({name}): {e}") from e
            oi_raw = (row.get("operating_income") or "").strip()
            oi = float(oi_raw) if oi_raw else None
            by_segment.setdefault(name, []).append(
                SegmentYear(fiscal_year=fy, revenue=rev, operating_income=oi)
            )
            if row.get("source"):
                sources[name] = row["source"].strip()

    segments = [
        Segment(
            name=name,
            years=sorted(years, key=lambda y: y.fiscal_year),
            source=sources.get(name, ""),
        )
        for name, years in by_segment.items()
    ]
    return SegmentSet(
        segments=segments,
        source_note=(
            "Brand-level net sales are sourced from Deckers' Form 10-K "
            "disaggregation-of-revenue / segment footnotes; brand splits are a "
            "curated input (not carried in the core XBRL income-statement tags), "
            "and the brand total reconciles to the SEC-reported total revenue "
            "each year (the residual is shown as Other)."
        ),
    )
