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
# The immutable binary artifact binds its original discovery bytes. Replay that
# complete historical tree rather than rewriting the old report for v2 discovery.
"$PY" -c 'import sys
try:
 import yaml, jsonschema
except ModuleNotFoundError as error:
 print("SKIP: Python module " + error.name, file=sys.stderr); sys.exit(3)'
command -v tar >/dev/null 2>&1 || { echo 'SKIP: binary artifact replay needs tar'; exit 3; }
LEGACY=$(mktemp -d)
trap 'result=$?; rm -rf "$LEGACY"; if [ "$result" != 0 ] && [ "$result" != 3 ]; then echo "FAIL: publisher reliability native check observed false (exit $result)"; fi; exit "$result"' EXIT
git -C "$ROOT" archive fd93b1612a3495c45bde9191ff2b67478ad46877 | tar -x -C "$LEGACY"
"$PY" - "$ROOT" "$LEGACY" <<'PYTHON'
from pathlib import Path
import sys
current, legacy = map(Path, sys.argv[1:])
protected = ('report.py', 'scoring.py', 'inputs.schema.json', 'payload.schema.json',
             'trust.json', 'version.json', 'UPSTREAM.json', 'envelope.schema.json',
             'forecast.schema.json', 'resolution.schema.json', 'inputs.json',
             'requirements.txt', 'v1/feed.json')
for name in protected:
    path = 'publisher-reliability/' + name
    if (current / path).read_bytes() != (legacy / path).read_bytes():
        raise SystemExit('FAIL: protected binary source/artifact changed: ' + path)
PYTHON
"$PY" "$LEGACY/publisher-reliability/report.py" check --root "$LEGACY" \
  --report "$LEGACY/publisher-reliability/v1/feed.json" >/dev/null
"$PY" "$ROOT/tests/test_publisher_reliability.py"
"$PY" "$ROOT/tests/test_publisher_reliability_release.py"
echo 'PASS: publisher reliability report recomputes and labelled synthetic provenance/scoring controls hold; no publisher-price accuracy was measured'
