#!/usr/bin/env bash
# Native report/provenance self-proof. Synthetic pairs are not world measurements.
set -eu
finish() {
  result=$?
  if [ "$result" != 0 ] && [ "$result" != 3 ]; then
    echo "FAIL: publisher reliability native check observed false (exit $result)"
  fi
  return "$result"
}
trap finish EXIT
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo 'SKIP: publisher reliability needs Python 3'; exit 3; }
command -v git >/dev/null 2>&1 || { echo 'SKIP: publisher reliability needs Git'; exit 3; }
"$PY" "$ROOT/publisher-reliability/report.py" check --root "$ROOT" \
  --report "$ROOT/publisher-reliability/v1/feed.json" >/dev/null
"$PY" "$ROOT/tests/test_publisher_reliability.py"
"$PY" "$ROOT/tests/test_publisher_reliability_release.py"
echo 'PASS: publisher reliability report recomputes and labelled synthetic provenance/scoring controls hold; no publisher-price accuracy was measured'
