#!/usr/bin/env bash
# Offline authenticated report replay; full mode also runs labelled source fixtures.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
SOURCES="${PUBLISHER_PRICE_SOURCE_ROOTS:-$(dirname "$ROOT")}"
REPORT="$ROOT/publisher-reliability/v2/feed.json"
CHECK_ONLY=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sources|--report)
      [ "$#" -ge 2 ] || { echo "FAIL: $1 requires a path"; exit 1; }
      if [ "$1" = --sources ]; then SOURCES="$2"; else REPORT="$2"; fi
      shift 2 ;;
    --check-only) CHECK_ONLY=true; shift ;;
    *) echo "FAIL: unknown native check option: $1"; exit 1 ;;
  esac
done
command -v "$PY" >/dev/null 2>&1 || { echo 'SKIP: price accuracy needs Python 3'; exit 3; }
command -v git >/dev/null 2>&1 || { echo 'SKIP: price accuracy needs Git'; exit 3; }
"$PY" "$ROOT/publisher-reliability/price_report.py" check --root "$ROOT" \
  --report "$REPORT" --sources "$SOURCES" >/dev/null
echo 'PASS: monetary report fully reconstructed from its declared source population'
if [ "$CHECK_ONLY" = false ]; then
  "$PY" "$ROOT/tests/test_price_accuracy.py"
  "$PY" "$ROOT/tests/test_publisher_reliability_release.py"
  "$PY" "$ROOT/tests/test_publisher_price_delivery.py"
  echo 'PASS: monetary SDK, release and bounded-generation controls hold; labelled fixtures are not world measurements'
fi
