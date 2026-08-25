#!/usr/bin/env bash
# Fast offline check: the catalog is well-formed OSCAL, its recorded sha256
# matches the file on disk, and the publish script produces a real pinnable
# tag+commit. No network, no cluster.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "${HERE}/scripts/verify_catalog.py"

echo "==> baselines: LOW/MODERATE/HIGH resolve against the catalogue, bare ids only"
python3 "${HERE}/scripts/verify_baselines.py"

echo "==> cs-14: EXPECTED_IDENTITY_REGEXP anchors org/repo/workflow, allows main + release/x.y.x"
bash "${HERE}/scripts/verify-cert-identity-regexp.sh"

echo "==> dry-run: publish.sh seeds + tags cleanly"
bash "${HERE}/scripts/publish.sh" >/dev/null
echo "OK: nist catalog verified + publishable"
