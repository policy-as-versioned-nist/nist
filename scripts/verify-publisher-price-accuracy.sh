#!/usr/bin/env bash
# Actual source/empty-collection replay plus explicitly synthetic producer/resolver controls.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo 'SKIP: price accuracy needs Python 3'; exit 3; }
command -v git >/dev/null 2>&1 || { echo 'SKIP: price accuracy needs Git'; exit 3; }
"$PY" "$ROOT/publisher-reliability/price_report.py" check --root "$ROOT" \
  --report "$ROOT/publisher-reliability/v2/feed.json" >/dev/null
"$PY" "$ROOT/tests/test_price_accuracy.py"
"$PY" "$ROOT/tests/test_publisher_reliability_release.py"
echo 'PASS: monetary SDK, authenticated reconstruction and bounded-generation controls hold; genuine declared cohorts remain empty'
