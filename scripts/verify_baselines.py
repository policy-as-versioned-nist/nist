#!/usr/bin/env python3
"""Verify beat for the published baselines (ticket policy-composition/09).

Resolves every control id named by every OSCAL baseline profile against the
catalogue, exact-string: no case-folding, no prefix-stripping. Walks nested
`controls` so an enhancement (a child control, e.g. ac-6.10) is found by a
group-level scan. An id the catalogue does not carry is a hard failure.

Run directly or via verify-catalog.sh.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CATALOG_DIR = HERE / "catalog"
FIXTURES_DIR = HERE / "scripts" / "fixtures"


def catalog_control_ids(catalog_doc):
    """Every control id in the catalogue, walking nested (enhancement) controls."""
    ids = set()

    def walk(controls):
        for c in controls:
            ids.add(c["id"])
            walk(c.get("controls", []))

    for group in catalog_doc["catalog"].get("groups", []):
        walk(group.get("controls", []))
    return ids


def resolve_profile_ids(profile_doc, catalog_ids):
    """Return the with-ids list and the subset absent from catalog_ids.

    Exact-string resolution only: no .lower(), no prefix split. That is the
    point of the check, not an implementation shortcut around it.
    """
    ids = profile_doc["profile"]["imports"][0]["include-controls"][0]["with-ids"]
    missing = [i for i in ids if i not in catalog_ids]
    return ids, missing


def assert_bare(ids, label):
    bad = [i for i in ids if i != i.lower() or ":" in i]
    assert not bad, f"{label}: non-bare control id(s) (upper case or prefix): {bad}"


def load_catalog():
    meta = json.loads((CATALOG_DIR / "CATALOG_VERSION.json").read_text())
    catalog_doc = json.loads((CATALOG_DIR / meta["file"]).read_bytes())
    return catalog_doc, catalog_control_ids(catalog_doc)


def main():
    catalog_doc, catalog_ids = load_catalog()
    baseline_meta = json.loads((CATALOG_DIR / "BASELINE_VERSIONS.json").read_text())

    counts = {}
    for name, entry in baseline_meta["baselines"].items():
        path = CATALOG_DIR / entry["file"]
        raw = path.read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        assert actual_sha == entry["sha256"], (
            f"{name}: baseline file has drifted from its recorded checksum: "
            f"{actual_sha} != {entry['sha256']}"
        )

        profile_doc = json.loads(raw)
        href = profile_doc["profile"]["imports"][0]["href"]
        assert href == baseline_meta["catalogFile"], (
            f"{name}: href {href!r} does not name the catalogue once, "
            f"expected {baseline_meta['catalogFile']!r}"
        )

        ids, missing = resolve_profile_ids(profile_doc, catalog_ids)
        assert_bare(ids, name)
        assert not missing, f"{name}: id(s) absent from the catalogue: {missing}"
        assert len(ids) == entry["controlCount"], (
            f"{name}: expected {entry['controlCount']} controls, resolved {len(ids)}"
        )
        counts[name] = set(ids)
        print(f"OK: {name} resolves {len(ids)} controls, all bare, all in the catalogue")

    # The facts the estate's selection rests on (ADR-0013, ticket 09 acceptance).
    assert {"ac-6", "cm-6", "ac-6.10"} <= counts["MODERATE"], (
        "MODERATE must hold ac-6, cm-6 and ac-6.10"
    )
    assert "ac-6" not in counts["LOW"], "LOW must not hold ac-6"
    assert len(counts["MODERATE"]) == 287, "MODERATE must resolve exactly 287 controls"

    # Negative case: a profile carrying an id absent from the catalogue fails
    # the beat. A fixture proves it (acceptance criterion, ticket 09).
    fixture = json.loads((FIXTURES_DIR / "profile-with-unknown-id.json").read_text())
    _, fixture_missing = resolve_profile_ids(fixture, catalog_ids)
    assert fixture_missing == ["zz-999"], (
        f"fixture must fail resolution against the catalogue with the "
        f"unknown id 'zz-999', got missing={fixture_missing}"
    )
    print("OK: fixture profile carrying an unknown id ('zz-999') fails resolution, as required")

    print(
        f"OK: {len(baseline_meta['baselines'])} baselines verified "
        f"({', '.join(f'{k}={len(v)}' for k, v in counts.items())})"
    )


if __name__ == "__main__":
    main()
