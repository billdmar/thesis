"""Offline tests for the EDGAR client: CIK lookup + cache-only behavior.

These never touch the network. They exercise the cache path and the
offline-guard that turns a missing fixture into a loud error.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from config import settings
from src.edgar import EdgarClient


def test_lookup_cik_from_cached_tickers():
    client = EdgarClient(offline=True)
    assert client.lookup_cik("DECK") == "0000910521"
    # Case-insensitive.
    assert client.lookup_cik("deck") == "0000910521"
    # Zero-padded to 10 digits.
    assert len(client.lookup_cik("NKE")) == 10
    assert client.lookup_cik("NKE") == "0000320187"


def test_company_name_lookup():
    client = EdgarClient(offline=True)
    assert "DECKERS" in client.company_name("DECK").upper()


def test_unknown_ticker_raises():
    client = EdgarClient(offline=True)
    with pytest.raises(KeyError):
        client.lookup_cik("NOTATICKER")


def test_offline_loads_cached_companyfacts():
    client = EdgarClient(offline=True)
    facts = client.get_company_facts("DECK")
    assert facts["cik"] == 910521
    assert "us-gaap" in facts["facts"]


def test_offline_loads_cached_submissions():
    client = EdgarClient(offline=True)
    subs = client.get_submissions("DECK")
    # submissions payload carries filer metadata.
    assert isinstance(subs, dict)
    assert subs  # non-empty


def test_offline_missing_concept_raises_not_network(tmp_path):
    # A ticker whose companyfacts IS cached, but a concept file that is NOT:
    # offline mode must raise FileNotFoundError, never attempt a live call.
    client = EdgarClient(offline=True)
    with pytest.raises(FileNotFoundError):
        client.get_company_concept("DECK", "us-gaap", "Revenues")


def test_offline_missing_ticker_file_raises(tmp_path):
    # Point the client at an empty cache dir: even a known ticker's file is
    # absent, so lookup_cik itself fails (no company_tickers.json to read).
    client = EdgarClient(offline=True, cache_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        client.get_company_facts("DECK")


def test_rate_limit_spacing_is_configured():
    # Guard the fair-access contract constant the client relies on.
    assert settings.SEC_REQ_SPACING_SEC >= 0.1
    assert "thesis-research" in settings.SEC_USER_AGENT


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.headers_seen = None

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _install_fake_requests(monkeypatch, payload, calls):
    """Install a fake ``requests`` module so the live path never hits the net."""
    fake = types.ModuleType("requests")

    def _get(url, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _FakeResponse(payload)

    fake.get = _get
    monkeypatch.setitem(sys.modules, "requests", fake)


def test_live_fetch_writes_cache_and_sends_user_agent(monkeypatch, tmp_path):
    # Online mode, empty cache: the client fetches (mocked), sends the required
    # User-Agent, and writes the response into the cache for reuse.
    # Seed a minimal company_tickers.json so lookup_cik works.
    tickers = {"0": {"cik_str": 910521, "ticker": "DECK", "title": "DECKERS OUTDOOR CORP"}}
    (tmp_path / "company_tickers.json").write_text(json.dumps(tickers), encoding="utf-8")

    calls: list[dict] = []
    payload = {"cik": 910521, "facts": {}}
    _install_fake_requests(monkeypatch, payload, calls)

    client = EdgarClient(offline=False, cache_dir=tmp_path)
    got = client.get_company_facts("DECK")
    assert got == payload
    # User-Agent contract enforced on the live call.
    assert calls and calls[0]["headers"]["User-Agent"] == settings.SEC_USER_AGENT
    # Response cached to disk.
    cached = tmp_path / "companyfacts_DECK_0000910521.json"
    assert cached.exists()

    # Second call is served from cache — no additional live request.
    again = client.get_company_facts("DECK")
    assert again == payload
    assert len(calls) == 1


def test_respect_rate_limit_sleeps_between_requests(monkeypatch):
    # The spacing guard must sleep when two live requests happen back-to-back.
    client = EdgarClient(offline=False)
    slept: list[float] = []
    monkeypatch.setattr("src.edgar.client.time.sleep", lambda s: slept.append(s))
    # First call: no prior request, so wait computes <= 0 (no sleep).
    monkeypatch.setattr("src.edgar.client.time.monotonic", lambda: 100.0)
    client._respect_rate_limit()
    # Second call immediately after: elapsed ~0, so it must sleep ~spacing.
    client._respect_rate_limit()
    assert slept, "expected a sleep on the back-to-back request"
    assert slept[-1] <= settings.SEC_REQ_SPACING_SEC


def test_fetch_live_refuses_in_offline_mode():
    client = EdgarClient(offline=True)
    with pytest.raises(RuntimeError):
        client._fetch_live("https://data.sec.gov/whatever.json")
