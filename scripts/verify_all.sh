#!/usr/bin/env bash
#
# verify_all.sh — run the full verification gate suite and print PASS/FAIL.
#
# Runs ruff lint + format-check, then the test suite (excluding live-EDGAR
# tests) with branch coverage on src/. CI-safe: no live network, fixtures only.
#
# Usage:  bash scripts/verify_all.sh
set -euo pipefail

# Resolve repo root from this script's location so it runs from anywhere.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY=.venv/bin/python
RUFF=.venv/bin/ruff
PYTEST=.venv/bin/pytest

fail=0
run_step() {
  local name="$1"
  shift
  echo ""
  echo "=== ${name} ==="
  if "$@"; then
    echo "--- ${name}: PASS"
  else
    echo "--- ${name}: FAIL"
    fail=1
  fi
}

run_step "ruff check" "$RUFF" check src tests
run_step "ruff format --check" "$RUFF" format --check src tests
run_step "pytest (not live) + coverage (gate >=90%)" \
  "$PYTEST" -m "not live" --cov=src --cov-report=term-missing --cov-fail-under=90

echo ""
echo "==================================================="
if [ "$fail" -eq 0 ]; then
  echo "VERIFY ALL: PASS"
else
  echo "VERIFY ALL: FAIL"
fi
echo "==================================================="
exit "$fail"
