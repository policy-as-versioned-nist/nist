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

echo "==> party.yaml: parses, every publishes[] path exists, catalog/{rule,bump}.yaml beside it (ticket 21, ADR-0019)"
python3 - "${HERE}" <<'EOF' || exit 1
import sys, os, yaml
here = sys.argv[1]
with open(os.path.join(here, "party.yaml")) as f:
    party = yaml.safe_load(f)
for i, pub in enumerate(party.get("publishes") or []):
    path = os.path.join(here, pub.get("path", ""))
    if not os.path.exists(path):
        print(f"FAIL: publishes[{i}].path does not exist: {path}"); sys.exit(1)
    for side in ("rule.yaml", "bump.yaml"):
        if not os.path.isfile(os.path.join(path, side)):
            print(f"FAIL: {pub['path']}/{side} missing beside the published catalogue"); sys.exit(1)
    with open(os.path.join(path, "bump.yaml")) as f:
        bump = yaml.safe_load(f).get("bump")
    if bump not in ("major", "minor", "patch", "none"):
        print(f"FAIL: {pub['path']}/bump.yaml declares {bump!r}, not major|minor|patch|none"); sys.exit(1)
    print(f"OK: publishes[{i}] {pub['kind']}/{pub['name']} at {pub['path']}, next bump declared {bump}")
EOF

echo "PASS: nist catalog verified + publishable"
