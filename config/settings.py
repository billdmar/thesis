"""Project-wide configuration constants. ORCH-owned."""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
OUT_DIR = ROOT / "out"
RELEASES_DIR = ROOT / "releases"

# --- SEC EDGAR fair-access (this is law here) ---
SEC_USER_AGENT = "thesis-research billdmar@gmail.com"
SEC_MAX_REQ_PER_SEC = 10
SEC_REQ_SPACING_SEC = 0.15  # 150ms spacing
SEC_BASE_URL = "https://data.sec.gov"
SEC_WWW_URL = "https://www.sec.gov"

# CI and offline runs must never hit live EDGAR — fixtures only.
OFFLINE = os.environ.get("THESIS_OFFLINE") == "1"

# --- Flagship subject ---
SUBJECT_TICKER = "DECK"
SUBJECT_CIK = "0000910521"
SUBJECT_NAME = "Deckers Outdoor Corporation"
SUBJECT_FYE = "03-31"  # fiscal year end (March 31)
