# Monetary empirical forecast accuracy

The v2 software supports one closed profile, `money-empirical-crps/v1`: the
annual aggregate monetary loss distribution produced by the publisher's actual
served FAIR model. It does not reinterpret PERT triples as quantiles, compare a
mode with an outcome, or relabel the binary v1 Brier/log-loss report.

The current committed `price-inputs.json` declares **no monetary cohorts**. Its
report set contains `reports: []`, no pooled score, unit or target, and an explicit
unmeasured reason. Releasing this software does not enroll a publisher, resolve an
outcome, supply an adopter bar, or alter any price.

## Source-bound producer and independent resolver

`price_records.py` owns these public functions:

- `build_forecast(root, *, profile, target, case_id, emitted_at, generator, source_roots)`
- `build_resolution(root, *, forecast, profile, source, resolved_at, published_at, evidence_uri, source_roots)`
- `check_record(root, kind, record, source_roots)`
- `score_empirical(atoms, observed)` returns an exact `Fraction` loss.

References bind canonical publisher, annotated signed tag, immutable commit,
path and exact Git blob. Same-tree references inherit the enclosing signed tree.
The implementation verifies pinned Actions identities, complete canonical source
history and captured served main, preserves registration and parent-clock guards,
and rejects rewritten records. Git committer dates remain publisher assertions;
they are not independent cryptographic proof of pre-outcome wall-clock existence.

An annual profile precommits its complete case inventory, nominal currency/basis,
nonoverlapping Gregorian annual horizons, independent resolver and final/complete
ledger rules. A forecast must reproduce the exact signed publisher converter's
`forecast-base payload.json context.json` scenario from the supported ICO penalty-schema or feeds threat-register served
converter path, and the fixed released FAIR
engine's actual empirical draws. The context is its authenticated complete party
document; arbitrary supplied turnover/institution arguments are not accepted.
The selected signed `inherits` edge supplies the existing converter version-key
normalization. Native converter currency must equal the declared unit; this
profile does not infer FX. Resolver amounts come from the declared independent
signed source and its exact finality/completeness pointers, not a supplied scalar.

`PRICE-UPSTREAM.json` binds the unchanged platform v5.4.0 FAIR and severity source
blobs. Their intrinsic Git blob identities are checked independently of manifest
hashes. There is no replacement risk engine. Technical limits bound parsing,
exact rational intermediates, cases, atoms, work and allocations. Work is reserved
for the complete report before any engine runs; excessive LEF or cumulative work
refuses instead of truncating financial values.

## Exact criterion and consumer boundary

For independent draws X and X' from the declared empirical CDF, loss is
`E|X-y| - E|X-X'|/2`. It has the outcome's monetary unit. Cohorts aggregate losses
by an exact equal-case mean, and expose its negative as a higher-is-better score.
See [Gneiting, Balabdaoui and Raftery (2007), equations 12–14](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf).
Late/unresolved cases remain visible and unscoreable. No eligible observations
means null loss/score; it cannot earn calibration or a pricing credit.

`price_accuracy.build_price_report(root, manifest, cutoff, source_roots=None)` and
`check_price_report(root, payload, source_roots=None)` reconstruct the entire
report set through the authenticated producer/resolver path. There is no public
admitted dictionary, trusted cache or skip-verification argument. A consumer must
capture complete source/ref/history/signature evidence for portable rechecking;
copying payloads or trusting an earlier score is insufficient.

Adopter bars/minimum populations and publisher widening targets are separately
signed inputs. The platform consumer owns the actual pre-cage pricing effect,
report-independent financial date, ordinary publisher-version comparison and
switching calculations. An independently authenticated degraded release can
select its target even when the score population is insufficient. This NIST
module never supplies an adopter appetite or prices anything itself.

## CLI, checks and releases

`price_report.py build --root . --as-of <actual-UTC> --output report.json` produces
an envelope; `price_report.py check --root . --report report.json --sources <roots>`
reconstructs it. `build-forecast`, `build-resolution` and `check-record` expose the
same SDK through closed JSON requests. Exit 0 means the declared artifact checks;
3 names a missing instrument, and 1 refuses invalid authority/data. It does not
turn an empty cohort into a failed or measured forecast population.

`scripts/verify-publisher-price-accuracy.sh` checks the committed empty report and
runs labelled synthetic real-Git/real-converter/real-FAIR controls. Only the
signature boundary is synthetic in these source tests. The binary wrapper also
checks the protected v1 files against its original fd93 source tree and replays
that immutable artifact with its original discovery, rather than changing it to
fit v2 discovery. Neither wrapper's fixtures are world observations.

The report retains the existing `publisher-reliability/vX.Y.Z` signed release
family; v2 selects its own version, schema, CLI and native check. Schema changes
are major, cohort/results changes minor, and cutoff/tool-only changes patch.
The controls catalogue, its release route, binary source and historical report
remain separate. Actual enrollment and priced activation require genuine signed
profile/target/forecast/resolution/bar inputs and ordinary release/adoption.

## Supplying nonempty source collections

The native wrapper is offline. Pass `--sources /path/to/full/party-clones`, set
`PUBLISHER_PRICE_SOURCE_ROOTS`, or use an existing flat sibling estate directory.
`--report` selects another envelope; `--check-only` performs the same complete
authenticated reconstruction without additionally running the source fixture
suites. It never skips signature, immutable-history or generation checks.
Missing source instruments remain exit 3; no network fallback is attempted.

Ordinary v2 cut/release workflows call `price_sources.py` before checking a
nonempty report. This bounded acquisition helper clones the eight canonical
public origins in the pinned trust registry into a new private source root,
with full independent history and no depth, filter, alternate object store or
credential-helper requirement. An empty collection performs no cloning and
introduces no fictional source refs. Acquisition does not admit a report: the
SDK subsequently verifies the exact tags, identities, trees, blobs, immutable
registration and model coupling. Existing source directories are never refreshed
or overwritten by the helper.

Resolver construction and record checking both require the forecast's signed
publisher to be its target publisher. They retain the same immutable served
registration checks for forecast and independent outcome source that the full
report already required; copied, rewritten, deleted or re-added records refuse.

## Shadow recovery-expense family

The closed supported target set also includes `feeds/recovery-expense`, served only by its same-tree `recovery-expense/to_fair_scenario.py`. This is a separate institution-year direct-expense pilot, not a relabelled threat or fine forecast. Its explicit signed context edge can coexist with existing monetary targets. The unchanged admission path still checks exact discovery/schema, publisher tree, context, cutoff history, fixed FAIR descriptor and actual converter reproduction. No arbitrary family or caller-provided scenario gains authority from this addition. Platform keeps this family out of ordinary institutional prices and financial dates. No actual model, registration, observation or score is provided by the SDK extension.
