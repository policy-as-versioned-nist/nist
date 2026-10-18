# Independent binary forecast diagnostic

Ticket46's first slice uses the existing NIST publisher as an independent scorer.
This report validates authenticated input references and reuses the hub's existing
binary Brier/log-loss functions and reliability bins. It does **not** measure
publisher-price accuracy, supply an adopter threshold or widening target, change
an evidence grade, grant transfer credit or affect a price. Ticket46 remains open.

`v1/feed.json` is a deterministic source artifact for declared version1.0.0. It is
unpublished until an ordinary reviewed namespaced signed release is actually cut.
Its genuine manifest is `inputs.json`: no target feeds or forecast/resolution
pairs. It therefore reports eligible count0, `unmeasured`, null losses, all ten
empty bins with null rates, and a named reason. Zero is a population count, never
a favourable score. Nonempty populations in the tests are labelled synthetic
fixtures; they are not newly observed forecasts, outcomes or calibration data.

## Native interface and evidence

```sh
python3 publisher-reliability/report.py build --root . --as-of 2026-10-17T07:00:00Z \
  --output publisher-reliability/v1/feed.json
python3 publisher-reliability/report.py check --root . \
  --report publisher-reliability/v1/feed.json
bash scripts/verify-publisher-reliability.sh
```

`build` accepts optional `--inputs` and `--sources` paths. `--sources` contains a
canonical regular publisher clone named for each party. `check` accepts the same
source directory, authenticates the embedded manifest, reconstructs the complete
report and compares every field. Both return the same canonical JSON envelope on
success. Neither fetches, signs, mutates a source repository or consults a clock.
`--help` is available without Python report dependencies. The supplied as-of is a
fixed UTC cutoff, not an observation manufactured by this tool.

Exit0 means a valid/reproducible report, including an unmeasured one. Rejected
input, a wrong identity, an ambiguous/revised record or a changed report exits1
with `FAIL:`. An actually absent Python dependency, Git, gitsign or source history
instrument exits3 with a named `SKIP:`; invalid authenticated facts are never
converted into a wait. The wrapper's PASS establishes local self-proof only. The
hub's separate estate reader waits before a signed report exists and still waits
for an authenticated n=0 report.

A target identifies a publisher/feed and exact tag, commit and repository-relative
feed path. The reader checks canonical origin, a nonshallow source, the signed
tag's internal name/direct commit, pinned identity/Actions issuer, discovered feed
path/schema, envelope and payload. It captures the annotated object before reading
history, copies its exact reachable objects into a fresh private regular Git store
and verifies that private ref. A mutable source tag cannot select different bytes
for verification. The private repository has no alternate or public remote; its
unsigned ref is only a local selector for verifying the copied signed object.
The genuine implementation uses checksum-installed gitsign0.17.1 with offline
Rekor proof verification. Native fixtures use an explicit signature adapter and
prove neither a genuine certificate nor a world outcome.

The scorer's own discovery is read from the supplied source snapshot, whose exact
party.yaml SHA256 is included in tool provenance. The scorer must publish none of
the declared target feeds. Forecasts must name that exact target and a registered
binary question, with strictly0<p<1. Resolutions must come from a different
publisher, bind the same forecast blob/question and carry a Boolean outcome and
source citation. A date or an annualised monetary triple cannot become a
probability or an outcome.

Registration is inferred from the record's single unchanged appearance on served
first-parent Git history, with its exact blob and source commit. Rewrites,
deletions/re-additions and parent-clock reversal refuse. Served-history object IDs
are frozen for the invocation. The explicit limitation remains: Git committer
dates are publisher assertions checked against their parents, not independent
wall-clock witnesses or a claim that an adversarial history rewrite is impossible.
Late, unresolved or unavailable-at-cutoff otherwise-authentic pairs are explicitly
unscoreable, never scored as false or silently included. Duplicate pairs,
forecasts or target/questions cannot stuff the population.

`UPSTREAM.json` pins the unmodified hub scoring source and the platform envelope
schema by repository/commit/blob/SHA256. The executed scoring module must equal the
reported copy. The report binds tool version and source/schema/trust/discovery
hashes, complete manifest, cutoff, included/excluded pairs and resolution evidence.
Only eligible binary pairs receive the unchanged lower-is-better Brier/log-loss
calculations; all ten bins, including empty ones, are retained. No transformed
`1-loss` publisher-quality score is defined.

## Bounded release family

Discovery adds this feed beside the unchanged controls catalogue. The report uses
`publisher-reliability/v<SEMVER>` tags and the existing cut-release workflow's exact
main-only Actions identity and issuer. Bare catalogue tags do not publish a
report. Catalogue gates and their existing maintenance-branch identity remain on
the catalogue route.

Before any cut, `.github/scripts/report-bump-gate.py` reads complete local/origin
report refs, rejects occupied, missing, moved or malformed refs, and compares the
reviewed declaration with the report's own rule. First1.0.0 is an explicit
bootstrap with a declared initial major and no predecessor; it is not a computed
major, price movement or measurement. Later schema bytes/path changes are major;
target/pair/population/results changes minor; tool/provenance/cutoff/metadata
changes patch; identical content apart from envelope version is none and carries
no release. The exact next semver increment must agree. A future major also needs
its own `v<MAJOR>/feed.json` and ordinary consumer compatibility review.

The ordinary cut workflow validates the committed report/native controls, signs
an immutable annotated tag with embedded offline Rekor proof and pushes it. The
release workflow verifies the expected signer/issuer and exact source, then runs
the native checker from that authenticated source before publication. Dispatch
inputs enter shell through structured environment variables. No actual release,
tag, public write or genuine scoring population is supplied by this source change.
