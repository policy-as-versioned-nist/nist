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
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
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


def grade(tag, declared):
    """RED-RUN SHIM (ticket 103): the old gate has one entry point, main(argv). A planted case
    writes the declaration it grades into the planted bump.yaml and calls it as the workflow
    does. Replaced by a real grade() in the green commit."""
    (CATALOG_DIR / "bump.yaml").write_text(f"bump: {declared}\n")
    return main(["declared-bump-gate.py", tag])


def tree(declared):
    (CATALOG_DIR / "bump.yaml").write_text(f"bump: {declared}\n")
    return main(["declared-bump-gate.py", "--tree"])


class _Planted:
    """A throwaway nist-shaped repository for --selfcheck: catalog/ with rule.yaml, bump.yaml,
    CATALOG_VERSION.json and one OSCAL catalogue file, committed and tagged under a hook-free
    git. The owner's global pre-commit hook is a rate-limited network call (estate note,
    2026-09-06), so every git call here pins core.hooksPath to an empty directory and signs
    nothing."""

    def __init__(self, root, name):
        self.repo = Path(root) / name
        self.hooks = Path(root) / "no-hooks"
        self.hooks.mkdir(exist_ok=True)
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.repo / "catalog").mkdir()
        (self.repo / "catalog" / "rule.yaml").write_text(
            'feed: sp-800-53\nchanged_when: "planted"\nentries: controls\n')

    def git(self, *args):
        return subprocess.run(["git", "-c", f"core.hooksPath={self.hooks}",
                               "-c", "user.name=selfcheck", "-c", "user.email=selfcheck@invalid",
                               "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
                               "-C", str(self.repo), *args],
                              capture_output=True, text=True, check=True).stdout

    def catalog(self, ids, version="1.0.0", file="planted_catalog.json", title="t"):
        body = {"catalog": {"groups": [{"id": "ac", "title": title, "controls": [
            {"id": i, "title": i.upper(), "controls": []} for i in ids]}]}}
        (self.repo / "catalog" / file).write_text(json.dumps(body, indent=1))
        (self.repo / "catalog" / "CATALOG_VERSION.json").write_text(
            json.dumps({"publishedVersion": version, "file": file}, indent=1))

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def tag(self, name):
        self.git("tag", name)

    def clone(self, name, *flags):
        dst = self.repo.parent / name
        subprocess.run(["git", "clone", "-q", *flags, str(self.repo), str(dst)],
                       capture_output=True, text=True, check=True)
        return dst


@contextlib.contextmanager
def _at(repo):
    """Point the gate at a planted repository for the duration of one case."""
    global REPO, CATALOG_DIR
    saved = REPO, CATALOG_DIR
    REPO, CATALOG_DIR = Path(repo), Path(repo) / "catalog"
    try:
        yield
    finally:
        REPO, CATALOG_DIR = saved


def _run(entry, *args):
    """(exit code, everything printed) of one gate entry point."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = entry(*args)
    return code, out.getvalue().strip()


def _expect(label, got, code, *phrases):
    """One selfcheck verdict: the exit code and every phrase the output must carry."""
    have, text = got
    missing = [p for p in phrases if p not in text]
    if have != code or missing:
        raise AssertionError(f"{label}: expected exit {code} naming {list(phrases)}, got exit "
                             f"{have} (missing {missing}): {text.splitlines()[-1] if text else '<nothing>'}")
    print(f"ok  {label}")


def _case_1_predecessor_at_the_tag(tmp):
    """Ticket 103 (1), nist's shape: the predecessor was read at its tag already, but its file
    NAME came from the working tree's CATALOG_VERSION.json, so a catalogue file renamed since the
    tag could not be read at all. Both the name and the bytes now come from the tag."""
    p = _Planted(tmp, "one")
    p.catalog(["ac-1", "ac-2"], file="rev5_catalog.json")
    p.commit("v1")
    p.tag("v1.0.0")
    (p.repo / "catalog" / "rev5_catalog.json").unlink()
    p.catalog(["ac-1", "ac-2"], version="1.0.1", file="rev6_catalog.json")   # renamed, same content
    p.commit("the catalogue file renamed, nothing else")
    with _at(p.repo):
        _expect("(1) the predecessor's file name is read at v1.0.0, not from the tree: a rename computes none",
                _run(tree, "none"), 0, "v1.0.0 -> tree", "'none'")
    (p.repo / "catalog" / "rev6_catalog.json").unlink()
    p.catalog(["ac-1"], version="2.0.0", file="rev7_catalog.json")           # renamed, control removed
    p.commit("renamed again, ac-2 removed")
    with _at(p.repo):
        _expect("(1) ...and a rename carrying a removed control computes major against the tag's bytes",
                _run(grade, "v2.0.0", "major"), 0, "v1.0.0 -> v2.0.0", "'major'")


def _case_2_the_tag_is_the_declared_bump(tmp):
    """Ticket 103 (2): the tag must equal bump(previous released tag, declared)."""
    p = _Planted(tmp, "two")
    p.catalog(["ac-1", "ac-2"])
    p.commit("v1")
    p.tag("v1.0.0")
    p.catalog(["ac-1", "ac-2", "ac-3"], version="1.1.0")                     # a control added
    p.commit("a control added")
    with _at(p.repo):
        _expect("(2) v1.1.0 declared minor over v1.0.0 is admitted",
                _run(grade, "v1.1.0", "minor"), 0, "v1.0.0 -> v1.1.0")
        _expect("(2) v1.0.1 declared minor is refused: the tag is a patch increment",
                _run(grade, "v1.0.1", "minor"), 1, "v1.0.1", "'patch'", "'minor'")
        _expect("(2) v2.0.0 declared minor is refused: the tag is a major increment",
                _run(grade, "v2.0.0", "minor"), 1, "v2.0.0", "'major'", "'minor'")
        _expect("(2) --tree derives v1.1.0 from the declared minor and admits it",
                _run(tree, "minor"), 0, "v1.0.0 -> v1.1.0")
        _expect("(2) --tree refuses a declared none while the tree carries a minor",
                _run(tree, "none"), 1, "'none'", "'minor'")
    p.catalog(["ac-1", "ac-2"])                                              # nothing queued
    p.commit("unchanged again")
    with _at(p.repo):
        _expect("(2) v1.0.1 declared none is refused: no tag carries none",
                _run(grade, "v1.0.1", "none"), 1, "'none'", "no release is queued")
        _expect("(2) --tree under a declared none admits an unchanged tree: no release is queued",
                _run(tree, "none"), 0, "v1.0.0 -> tree", "no release is queued")


def _case_3_no_tags_in_this_clone(tmp):
    """Ticket 103 (3): an empty tag list is told apart from a repository that never released."""
    p = _Planted(tmp, "three")
    p.catalog(["ac-1", "ac-2"])
    p.commit("v1")
    p.tag("v1.0.0")
    with _at(p.clone("three-no-tags", "--no-tags")):
        _expect("(3) a --no-tags clone of a released repository is refused, not graded as a first release",
                _run(grade, "v1.0.1", "patch"), 1, "no tags in this clone")
        _expect("(3) ...and --tree refuses the same way, not exit 3",
                _run(tree, "none"), 1, "no tags in this clone")
    q = _Planted(tmp, "four")
    q.catalog(["ac-1", "ac-2"])
    q.commit("v1, never released")
    with _at(q.clone("four-clone")):
        _expect("(3) a clone of a repository that never released takes the first-release path",
                _run(grade, "v1.0.0", "major"), 0, "first")
        _expect("(3) ...and --tree names the tree's own publishedVersion as that first release",
                _run(tree, "major"), 0, "v1.0.0", "first")


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

    # ticket 103: three ways the gate could agree about a number a release would not carry. Each
    # case plants a repository and runs the real entry points; every case is reported, not the
    # first to fail, so a red run names everything that is red.
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in (_case_1_predecessor_at_the_tag, _case_2_the_tag_is_the_declared_bump,
                     _case_3_no_tags_in_this_clone):
            try:
                case(tmp)
            except AssertionError as exc:
                failed.append(str(exc))
                print(f"FAIL {exc}")
    if failed:
        print(f"FAIL: {len(failed)} ticket-103 selfcheck case(s) red", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
