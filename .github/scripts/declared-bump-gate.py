#!/usr/bin/env python3
"""declared-bump-gate.py -- ticket 43, ticket 18 Answer 5.

nist declares the bump for a release in one reviewed file,
`catalog/bump.yaml` (ticket 21 shipped it; nist has no versions.yaml array
to hang the field on). Nothing read it. This is the gate that does: before
cut-release.yml creates the tag, it computes the bump between the catalogue
on disk and the catalogue at the previous released tag, under the
catalogue's OWN rule (`catalog/rule.yaml`, ADR-0023 decision D2), and
REFUSES when the declaration and the computation disagree.

catalog/rule.yaml, verbatim: "a control id added (minor), removed or renamed
(major), or an existing control's text edited (patch)". A rename is a
removal plus an addition, so it falls out of the removal rule with no
special case. A baseline profile that stops resolving is the reason removal
is a major: another party's weights are keyed on those ids.

The predecessor is read from git, never from a second copy on disk: the
catalogue is one file per release, so "what did we publish last time" is the
previous tag and nothing else.

    declared-bump-gate.py v1.2.0     # the tag cut-release.yml is about to cut
    declared-bump-gate.py --tree     # ...the same question, without naming a tag
    declared-bump-gate.py --selfcheck
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "catalog"
LADDER = ("none", "patch", "minor", "major")


def read_flat(path, key):
    """Flat `key: value` YAML, standard library only -- the same shape and
    the same reason as every rule.yaml and bump.yaml in the estate."""
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith(f"{key}:"):
            return line.partition(":")[2].strip().strip('"').strip("'")
    return None


def control_ids(catalog):
    """Every control id in an OSCAL catalogue, groups and nested controls
    included -- the same recursive walk scripts/verify_catalog.py counts
    with, reading ids instead of counting."""
    out = set()

    def walk(controls):
        for control in controls:
            if "id" in control:
                out.add(control["id"])
            walk(control.get("controls", []))

    for group in catalog.get("catalog", {}).get("groups", []):
        walk(group.get("controls", []))
    return out


def compute(old, new):
    old_ids, new_ids = control_ids(old), control_ids(new)
    if old_ids - new_ids:
        return "major"
    if new_ids - old_ids:
        return "minor"
    return "none" if old == new else "patch"


def previous_tag(tag):
    """The highest released tag strictly below `tag`. Plain semver, no
    prereleases: nist publishes a catalogue, and a catalogue is never
    published degraded (nothing about it can be computed weaker than
    declared -- that is the policy publisher's problem, ticket 18 Answer 1)."""
    def key(t):
        return tuple(int(p) for p in t.lstrip("v").split("."))

    out = subprocess.run(["git", "-C", str(REPO), "tag", "-l", "v*.*.*"],
                         capture_output=True, text=True, check=True).stdout.split()
    below = [t for t in out if re.fullmatch(r"v\d+\.\d+\.\d+", t) and key(t) < key(tag)]
    return max(below, key=key) if below else None


def catalog_at(ref, rel_path):
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{rel_path}"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return json.loads(proc.stdout)


def main(argv):
    if len(argv) == 2 and argv[1] == "--selfcheck":
        return selfcheck()
    if len(argv) != 2:
        print("usage: declared-bump-gate.py <tag>|--selfcheck", file=sys.stderr)
        return 2
    tag = argv[1]
    if tag == "--tree":
        # What the tree currently claims, against the newest released tag.
        # The same question cut-release.yml asks, asked without naming a tag,
        # so a verify script can ask it forever.
        out = subprocess.run(["git", "-C", str(REPO), "tag", "-l", "v*.*.*"],
                             capture_output=True, text=True, check=True).stdout.split()
        released = [t for t in out if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
        if not released:
            print("SKIP: this repository has no released tag to compare the tree against")
            return 3
        newest = max(released, key=lambda t: tuple(int(p) for p in t.lstrip("v").split(".")))
        major, minor, patch = (int(p) for p in newest.lstrip("v").split("."))
        tag = f"v{major}.{minor}.{patch + 1}"
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        print(f"FAIL: {tag!r} is not a vX.Y.Z tag", file=sys.stderr)
        return 1

    declared = read_flat(CATALOG_DIR / "bump.yaml", "bump")
    if declared not in LADDER:
        print(f"FAIL: catalog/bump.yaml declares {declared!r}, not one of {LADDER}", file=sys.stderr)
        return 1

    meta = json.loads((CATALOG_DIR / "CATALOG_VERSION.json").read_text())
    rel_path = f"catalog/{meta['file']}"
    prev = previous_tag(tag)
    if prev is None:
        print(f"OK: {tag} is the first release -- no predecessor to compute a bump against, "
              f"so the declared bump {declared!r} stands unchallenged")
        return 0

    old = catalog_at(prev, rel_path)
    if old is None:
        print(f"FAIL: could not read {rel_path} at {prev} -- the gate cannot compute a bump "
              f"it cannot read the predecessor for", file=sys.stderr)
        return 1
    computed = compute(old, json.loads((CATALOG_DIR / meta["file"]).read_text()))
    if computed != declared:
        print(f"FAIL: catalog/bump.yaml declares {declared!r} but the computed bump from "
              f"{prev} is {computed!r} (rule: {read_flat(CATALOG_DIR / 'rule.yaml', 'changed_when')!r}). "
              f"The gate has two declarations of one fact and no rule for choosing between them.",
              file=sys.stderr)
        return 1
    print(f"OK: declared bump {declared!r} == computed bump {computed!r} ({prev} -> {tag})")
    return 0


def selfcheck():
    def catalog(ids, title="t"):
        return {"catalog": {"groups": [{"id": "ac", "title": title, "controls": [
            {"id": i, "title": i.upper(), "controls": []} for i in ids]}]}}

    base = catalog(["ac-1", "ac-2"])
    cases = [
        ("unchanged", catalog(["ac-1", "ac-2"]), "none"),
        ("control added", catalog(["ac-1", "ac-2", "ac-3"]), "minor"),
        ("control removed", catalog(["ac-1"]), "major"),
        ("control renamed", catalog(["ac-1", "ac-2a"]), "major"),
        ("prose edited", catalog(["ac-1", "ac-2"], title="edited"), "patch"),
    ]
    for name, candidate, expected in cases:
        got = compute(base, candidate)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    nested = {"catalog": {"groups": [{"controls": [
        {"id": "ac-2", "controls": [{"id": "ac-2.1"}]}]}]}}
    assert control_ids(nested) == {"ac-2", "ac-2.1"}, "an enhancement is a control id too"
    print("ok  nested control enhancements are counted as ids")
    assert read_flat(CATALOG_DIR / "bump.yaml", "bump") in LADDER, "the real bump.yaml must parse"
    assert read_flat(CATALOG_DIR / "rule.yaml", "entries") == "controls", "the real rule.yaml must parse"
    print("ok  the real catalog/bump.yaml and rule.yaml parse with the standard library")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
