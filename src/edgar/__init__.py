"""the EDGAR layer: SEC EDGAR client + XBRL normalization to canonical facts."""

from __future__ import annotations

from src.edgar.client import EdgarClient
from src.edgar.normalize import ALIAS_MAP, load_normalized_facts

__all__ = ["EdgarClient", "load_normalized_facts", "ALIAS_MAP"]
