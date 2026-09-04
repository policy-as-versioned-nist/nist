#!/usr/bin/env bash
# cs-14: proves EXPECTED_IDENTITY_REGEXP (release.yml) matches exactly what
# it should -- main and the release/<major>.<minor>.x maintenance branch
# shape, pinned to this org/repo/workflow path -- and nothing else. Pulled
# straight out of release.yml so this can never drift from what CI enforces.
#
# bash's [[ =~ ]] is POSIX ERE, not RE2 (what gitsign/cosign actually use),
# but this pattern only uses anchors, alternation, an escaped literal dot and
# a character class -- all identical between the two engines -- so ERE is a
# faithful stand-in here without needing gitsign installed to run this check.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REGEXP=$(grep -oE '^  EXPECTED_IDENTITY_REGEXP: .*' "${HERE}/.github/workflows/release.yml" | sed 's/^  EXPECTED_IDENTITY_REGEXP: //')

if [ -z "${REGEXP}" ]; then
  echo "FAIL: could not find EXPECTED_IDENTITY_REGEXP in release.yml" >&2
  exit 1
fi

fail=0

must_match() {
  if [[ "$1" =~ ${REGEXP} ]]; then
    echo "OK (matches):     $1"
  else
    echo "FAIL (should match): $1" >&2
    fail=1
  fi
}

must_not_match() {
  if [[ "$1" =~ ${REGEXP} ]]; then
    echo "FAIL (should NOT match): $1" >&2
    fail=1
  else
    echo "OK (rejects):     $1"
  fi
}

# main and every backport still verify
must_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/main"
must_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/release/1.0.x"
must_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/release/12.34.x"

# a foreign org, repo, workflow path, or branch shape must not sneak through
must_not_match "https://github.com/evil-org/nist/.github/workflows/cut-release.yml@refs/heads/main"
must_not_match "https://github.com/policy-as-versioned-nist/other-repo/.github/workflows/cut-release.yml@refs/heads/main"
must_not_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/other.yml@refs/heads/main"
must_not_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/maint/1.0"
must_not_match "evil.com/https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/main"
must_not_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/cut-release.yml@refs/heads/main.evil.com"
# a proposer identity (the adopters' propose-tier.yml signs cage-tier proposal
# commits, ticket 78) is never a publisher's tag identity; this repo has no
# proposer and its tags must not verify under one
must_not_match "https://github.com/policy-as-versioned-nist/nist/.github/workflows/propose-tier.yml@refs/heads/main"

if [ "${fail}" -ne 0 ]; then
  echo "FAIL: EXPECTED_IDENTITY_REGEXP did not behave as required" >&2
  exit 1
fi
echo "OK: EXPECTED_IDENTITY_REGEXP anchors org/repo/workflow and allows only main + release/<major>.<minor>.x"
