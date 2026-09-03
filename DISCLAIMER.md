# Disclaimer

A demonstration party, not affiliated with, endorsed by or speaking for any real authority it names.

`policy-as-versioned-nist` is a party in the *Policy as Versioned Code* demonstration estate. It
is **not** the National Institute of Standards and Technology (NIST), the US Department of
Commerce or any other agency of the United States Government. Nobody at NIST has reviewed,
approved or contributed to this repository, and no endorsement by NIST is claimed or implied.

## What is NIST's and what is not

`catalog/` holds the genuine NIST SP 800-53 Rev 5.2.0 OSCAL catalogue and its LOW, MODERATE and
HIGH baseline profiles, redistributed **verbatim** from
[usnistgov/oscal-content](https://github.com/usnistgov/oscal-content). Those files are works of
the United States Government, in the public domain under 17 U.S.C. section 105, and are attributed
in [NOTICE](NOTICE), which cites the upstream URL and the sha256 of each file exactly as
`catalog/CATALOG_VERSION.json` and `catalog/BASELINE_VERSIONS.json` record them. The hub's
`verify/disclaimer` check refuses a NOTICE that disagrees with either manifest.

Everything else — `party.yaml`, the scripts, the version and provenance manifests, this file and
the README — is this party's own wrapper, licensed under [Apache-2.0](LICENSE). The Apache
licence does not, and could not, apply to the catalogue or the baselines.

## What the signature and the version mean

Releases are signed under this repository's own gitsign tags, and `publishedVersion` in
`CATALOG_VERSION.json` is this party's wrapper version, not a NIST version number. A signed tag
here attests that *this demonstration party* published these bytes at that version. It attests
nothing about NIST; NIST publishes its own catalogue at its own address and under its own
release process, and that upstream is the authority on what SP 800-53 says.

## What this is for

The estate shows how a controls catalogue that a regulator already publishes as machine-readable
data can travel as a signed, versioned dependency that institutions pin, select a baseline from
and receive bumps to. The catalogue is real to keep the demonstration honest; the party
publishing it is a stand-in. Do not rely on this repository as an authoritative copy of
SP 800-53 — go to NIST for that.
