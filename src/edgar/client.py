"""SEC EDGAR HTTP client with an offline-first, cache-backed design.

Fair-access is law here (see config.settings):
* every request carries the ``thesis-research`` User-Agent,
* live requests are spaced >= ``SEC_REQ_SPACING_SEC`` apart,
* responses are cached to disk under ``data/fixtures/raw/`` and
* in OFFLINE mode the client reads ONLY from that cache and never touches the
  network — a missing cache file is a loud error, not a silent live fetch.

Tests run fully offline against committed fixtures; the live path is real but
unexercised by CI.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import settings


class EdgarClient:
    """Fetches SEC company facts / concepts / submissions, cache-first.

    Parameters
    ----------
    offline:
        When True (or ``config.settings.OFFLINE`` is set), never hit the
        network; serve from cache or raise. When False, missing cache entries
        are fetched live (rate-limited) and written to the cache.
    cache_dir:
        Where cached JSON lives. Defaults to ``FIXTURES_DIR/"raw"``.
    user_agent:
        Sent on every live request. Defaults to ``SEC_USER_AGENT``.
    """

    def __init__(
        self,
        *,
        offline: bool | None = None,
        cache_dir: Path | None = None,
        user_agent: str = settings.SEC_USER_AGENT,
    ) -> None:
        self.offline = settings.OFFLINE if offline is None else offline
        self.cache_dir = Path(cache_dir) if cache_dir is not None else settings.FIXTURES_DIR / "raw"
        self.user_agent = user_agent
        self._last_request_at: float = 0.0
        self._ticker_index: dict[str, dict[str, str]] | None = None

    # -- CIK lookup ---------------------------------------------------------
    def _load_ticker_index(self) -> dict[str, dict[str, str]]:
        """Map upper-case ticker -> {cik (10-digit), name} from the cached file."""
        if self._ticker_index is not None:
            return self._ticker_index
        raw = self._read_json("company_tickers.json")
        index: dict[str, dict[str, str]] = {}
        # company_tickers.json is a dict keyed by row index -> {cik_str, ticker, title}.
        for row in raw.values():
            ticker = str(row["ticker"]).upper()
            index[ticker] = {
                "cik": str(row["cik_str"]).zfill(10),
                "name": str(row.get("title", "")),
            }
        self._ticker_index = index
        return index

    def lookup_cik(self, ticker: str) -> str:
        """Return the zero-padded 10-digit CIK for ``ticker``.

        Raises ``KeyError`` for an unknown ticker (honest-unknown: we do not
        guess a CIK).
        """
        index = self._load_ticker_index()
        key = ticker.upper()
        if key not in index:
            raise KeyError(f"ticker not found in company_tickers.json: {ticker!r}")
        return index[key]["cik"]

    def company_name(self, ticker: str) -> str:
        """Registrant name for ``ticker`` from the ticker index."""
        return self._load_ticker_index()[ticker.upper()]["name"]

    # -- Public fetch methods ----------------------------------------------
    def get_company_facts(self, ticker: str) -> dict[str, Any]:
        """companyfacts JSON for ``ticker`` (all XBRL facts)."""
        cik = self.lookup_cik(ticker)
        filename = f"companyfacts_{ticker.upper()}_{cik}.json"
        url = f"{settings.SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"
        return self._get(filename, url)

    def get_company_concept(self, ticker: str, taxonomy: str, tag: str) -> dict[str, Any]:
        """companyconcept JSON for a single (taxonomy, tag) of ``ticker``."""
        cik = self.lookup_cik(ticker)
        filename = f"companyconcept_{ticker.upper()}_{cik}_{taxonomy}_{tag}.json"
        url = f"{settings.SEC_BASE_URL}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
        return self._get(filename, url)

    def get_submissions(self, ticker: str) -> dict[str, Any]:
        """submissions JSON for ``ticker`` (filing history / metadata)."""
        cik = self.lookup_cik(ticker)
        filename = f"submissions_{ticker.upper()}_{cik}.json"
        url = f"{settings.SEC_BASE_URL}/submissions/CIK{cik}.json"
        return self._get(filename, url)

    # -- Cache / network plumbing ------------------------------------------
    def _get(self, filename: str, url: str) -> dict[str, Any]:
        """Return cached JSON if present; otherwise fetch live (unless offline)."""
        path = self.cache_dir / filename
        if path.exists():
            return self._read_json(filename)
        if self.offline:
            raise FileNotFoundError(
                f"offline mode: required cache file is missing: {path} (would have fetched {url})"
            )
        payload = self._fetch_live(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self.cache_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"cache file not found: {path}")
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _fetch_live(self, url: str) -> dict[str, Any]:
        """Perform a rate-limited live GET. Never reached in offline mode/CI."""
        if self.offline:  # defensive: callers gate on this, but never trust it blindly
            raise RuntimeError(f"refusing live fetch in offline mode: {url}")
        self._respect_rate_limit()
        import requests  # local import so offline runs never require the dep at import time

        resp = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _respect_rate_limit(self) -> None:
        """Sleep so consecutive live requests are >= SEC_REQ_SPACING_SEC apart."""
        elapsed = time.monotonic() - self._last_request_at
        wait = settings.SEC_REQ_SPACING_SEC - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()
