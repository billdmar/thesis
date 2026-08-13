"""One-shot rate-limited EDGAR fixture puller (W0 background job).

Fetches CompanyFacts + submissions for the subject and peer set into
data/fixtures/raw/, respecting SEC fair-access (User-Agent, 150ms spacing).
This is a bootstrap convenience so the parallel W1 fleet has data to build on;
SA-edgar owns the production client. Idempotent: skips files already cached.

Run: .venv/bin/python scripts/pull_edgar_fixtures.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

UA = "thesis-research billdmar@gmail.com"
SPACING = 0.15  # 150ms between requests (well under 10 req/s)
RAW = Path("data/fixtures/raw")

# Subject + footwear/apparel peer set (CIKs resolved from company_tickers.json).
COMPANIES = {
    "DECK": "0000910521",  # subject — Deckers Outdoor
    "NKE": "0000320187",   # Nike
    "CROX": "0001334036",  # Crocs
    "WWW": "0000110471",   # Wolverine World Wide
    "SHOO": "0000913241",  # Steven Madden
    "COLM": "0001050797",  # Columbia Sportswear
    "VFC": "0000103379",   # VF Corp
    "BOOT": "0001610250",  # Boot Barn
    "CAL": "0000014707",   # Caleres
}


def fetch(url: str, dest: Path) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return f"cached  {dest.name}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (SEC https only)
            data = resp.read()
            import gzip

            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
    except Exception as e:  # noqa: BLE001 — bootstrap script, log and continue
        return f"ERROR   {dest.name}: {e}"
    dest.write_bytes(data)
    time.sleep(SPACING)
    return f"pulled  {dest.name} ({len(data):,} bytes)"


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    log = []
    for ticker, cik in COMPANIES.items():
        # CompanyFacts: all XBRL facts for the filer.
        log.append(
            fetch(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                RAW / f"companyfacts_{ticker}_{cik}.json",
            )
        )
        # Submissions: filing index (forms, accessions, dates) for the subject + peers.
        log.append(
            fetch(
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                RAW / f"submissions_{ticker}_{cik}.json",
            )
        )
    print("\n".join(log))
    errors = [line for line in log if line.startswith("ERROR")]
    manifest = {
        "companies": COMPANIES,
        "user_agent": UA,
        "files": sorted(p.name for p in RAW.glob("*.json")),
    }
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nDONE: {len(log)} fetches, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
