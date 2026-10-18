"""Report CLI contracts. Any nonempty populations below are explicit synthetic fixtures."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'publisher-reliability/report.py'


def fixture_git(repo, *args, at='2026-01-01T00:00:00Z'):
    env = dict(os.environ, GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    call = subprocess.run(['git', '-C', str(repo), *args], env=env, capture_output=True, text=True)
    if call.returncode:
        raise AssertionError(call.stderr)
    return call.stdout.strip()


def source_fixture(temp, party='feeds'):
    """Real Git and canonical origin; signatures are explicitly synthetic at the tool seam."""
    repo = Path(temp) / 'sources' / party
    repo.mkdir(parents=True)
    fixture_git(repo, 'init', '-q', '-b', 'main')
    for key, value in [('user.name', 'explicit synthetic scorer fixture'), ('user.email', 'fixture@example.invalid'),
                       ('commit.gpgsign', 'false'), ('tag.gpgSign', 'false'), ('core.hooksPath', os.devnull)]:
        fixture_git(repo, 'config', key, value)
    fixture_git(repo, 'remote', 'add', 'origin', f'https://github.com/policy-as-versioned-{party}/{party}.git')
    payload = repo / 'fixture/v1/feed.json'
    payload.parent.mkdir(parents=True)
    payload.write_text(json.dumps({'kind': 'feed', 'name': 'fixture-binary-source', 'version': '1.0.0',
                                  'published_by': party, 'published_at': '2026-01-01T00:00:00Z',
                                  'payload_schema': 'fixture/payload.schema.json', 'payload': {}}))
    (repo / 'fixture/payload.schema.json').write_text('{"type":"object"}')
    (repo / 'party.yaml').write_text(f'party: {party}\nroles: [publisher]\ninherits: []\npublishes:\n  - {{kind: feed, name: fixture-binary-source, path: fixture, payload_schema: fixture/payload.schema.json}}\noverlay: {{add: [], restate: []}}\n')
    fixture_git(repo, 'add', '.')
    fixture_git(repo, 'commit', '-qm', 'explicit synthetic target')
    sha = fixture_git(repo, 'rev-parse', 'HEAD')
    fixture_git(repo, 'tag', '-a', 'fixture-binary-source/v1.0.0', '-m', 'unsigned synthetic fixture tag')
    fixture_git(repo, 'update-ref', 'refs/remotes/origin/main', sha)
    target = {'id': 'fixture-target', 'publisher': party, 'name': 'fixture-binary-source',
              'tag': 'fixture-binary-source/v1.0.0', 'commit': sha, 'path': 'fixture/v1/feed.json'}
    return repo, target


def verifier_fixture(temp):
    directory = Path(temp) / 'bin'
    directory.mkdir(exist_ok=True)
    script = directory / 'gitsign'
    script.write_text('#!' + sys.executable + '\n' + """import os,re,subprocess,sys
from pathlib import Path
assert sys.argv[1] == 'verify-tag'
party = Path.cwd().name
identity = f'https://github.com/policy-as-versioned-{party}/{party}/.github/workflows/cut-release.yml@refs/heads/main'
assert '--certificate-identity-regexp=^' + re.escape(identity) + '$' in sys.argv
assert '--certificate-oidc-issuer=https://token.actions.githubusercontent.com' in sys.argv
if os.environ.get('FIXTURE_MOVE_TAG') == sys.argv[2]:
    subprocess.run(['git','update-ref','refs/tags/' + sys.argv[2],'HEAD'], check=True)
print('synthetic signature adapter; not production verification')
if not os.environ.get('FIXTURE_OMIT_SIGNATURE_FACTS'):
    print('Good signature from synthetic fixture')
    print('Validated Git signature: true')
    print('Validated Rekor entry: true')
    print('Validated Certificate claims: true')
raise SystemExit(1 if os.environ.get('FIXTURE_REFUSE_SIGNATURE') or os.environ.get('FIXTURE_REFUSE_TAG') == sys.argv[2] else 0)
""")
    script.chmod(0o755)
    return dict(os.environ, PATH=str(directory) + os.pathsep + os.environ.get('PATH', ''))


def publish_record(repo, path, document, tag, at):
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(document))
    fixture_git(repo, 'add', path, at=at)
    fixture_git(repo, 'commit', '-qm', 'explicit synthetic registered record', at=at)
    commit = fixture_git(repo, 'rev-parse', 'HEAD')
    fixture_git(repo, 'tag', '-a', tag, '-m', 'unsigned synthetic fixture record', at=at)
    fixture_git(repo, 'update-ref', 'refs/remotes/origin/main', commit)
    return {'party': repo.name, 'tag': tag, 'commit': commit, 'path': path}


def binary_pair_fixture(temp, forecast_at='2026-01-02T00:00:00Z'):
    feeds, target = source_fixture(temp)
    resolver, unused = source_fixture(temp, 'ico')
    question = {'id': 'explicit-fixture-question', 'proposition': 'An explicitly synthetic fixture event',
                'resolution_window_opens_at': '2026-02-01T00:00:00Z'}
    forecast_doc = {'schema': 'publisher-reliability/forecast-v1',
                    'target': {k: v for k, v in target.items() if k != 'id'}, 'question': question,
                    'probability': 0.8, 'emitted_at': '2026-01-02T00:00:00Z'}
    forecast = publish_record(feeds, 'forecasts/fixture.json', forecast_doc, 'forecast/v1.0.0', forecast_at)
    reference = dict(forecast, git_blob=fixture_git(feeds, 'rev-parse', forecast['commit'] + ':' + forecast['path']))
    outcome_doc = {'schema': 'publisher-reliability/resolution-v1', 'forecast': reference,
                   'question': question, 'observed': True, 'resolved_at': '2026-02-02T00:00:00Z',
                   'source': 'https://explicit-fixture.invalid/resolution-not-a-real-observation'}
    resolution = publish_record(resolver, 'resolutions/fixture.json', outcome_doc, 'resolution/v1.0.0', '2026-02-02T00:00:00Z')
    manifest = {'schema': 'publisher-reliability/inputs-v1', 'targets': [target],
                'pairs': [{'id': 'explicit-fixture-pair', 'target': target['id'], 'forecast': forecast, 'resolution': resolution}]}
    return feeds, resolver, manifest


class ReportCLI(unittest.TestCase):
    def test_empty_actual_cli_reports_no_measured_price_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs = Path(temp) / 'inputs.json'
            inputs.write_text(json.dumps({'schema': 'publisher-reliability/inputs-v1', 'targets': [], 'pairs': []}))
            call = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(ROOT),
                                   '--inputs', str(inputs), '--as-of', '2026-10-17T00:00:00Z'],
                                  capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            report = json.loads(call.stdout)['payload']
            self.assertEqual(report['status'], 'unmeasured')
            self.assertEqual(report['counts'], {'submitted': 0, 'eligible': 0, 'unscoreable': 0})
            self.assertEqual(report['claim_scope'], {'binary_forecast_scores_only': True,
                                                   'publisher_price_accuracy': False, 'price_eligible': False})
            self.assertIsNone(report['losses']['brier'])
            self.assertIsNone(report['losses']['log_loss'])
            self.assertEqual(report['diagram']['total'], 0)
            self.assertEqual(len(report['diagram']['bins']), 10)
            self.assertTrue(all(b['count'] == 0 and b['mean_forecast'] is None and
                                b['empirical_frequency'] is None for b in report['diagram']['bins']))
            self.assertTrue(report['reason'])

    def test_check_reproduces_the_actual_cli_and_rejects_changed_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'feed.json'
            built = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(ROOT),
                                    '--as-of', '2026-10-17T00:00:00Z', '--output', str(report)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            checked = subprocess.run([sys.executable, str(CLI), 'check', '--root', str(ROOT),
                                      '--report', str(report)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(checked.stdout, built.stdout)
            changed = json.loads(report.read_text())
            changed['payload']['losses']['lower_is_better'] = False
            report.write_text(json.dumps(changed))
            refused = subprocess.run([sys.executable, str(CLI), 'check', '--root', str(ROOT),
                                      '--report', str(report)], capture_output=True, text=True)
            self.assertEqual(refused.returncode, 1, refused.stderr)
            self.assertTrue(refused.stderr.rstrip().splitlines()[-1].startswith('FAIL:'))

    def test_actual_target_reader_checks_identity_and_canonical_source(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, target = source_fixture(temp)
            inputs = Path(temp) / 'inputs.json'
            inputs.write_text(json.dumps({'schema': 'publisher-reliability/inputs-v1', 'targets': [target], 'pairs': []}))
            env = verifier_fixture(temp)
            argv = [sys.executable, str(CLI), 'build', '--root', str(ROOT), '--inputs', str(inputs),
                    '--sources', str(repo.parent), '--as-of', '2026-10-17T00:00:00Z']
            accepted = subprocess.run(argv, env=env, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(json.loads(accepted.stdout)['payload']['status'], 'unmeasured')
            refused = subprocess.run(argv, env=dict(env, FIXTURE_REFUSE_SIGNATURE='1'), capture_output=True, text=True)
            self.assertEqual(refused.returncode, 1, refused.stderr)
            self.assertIn('signature', refused.stderr)
            fixture_git(repo, 'remote', 'set-url', 'origin', 'https://github.com/other/forged.git')
            wrong = subprocess.run(argv, env=env, capture_output=True, text=True)
            self.assertEqual(wrong.returncode, 1, wrong.stderr)
            self.assertIn('canonical', wrong.stderr)

    def test_registered_independent_fixture_pair_uses_existing_binary_losses_only(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            inputs = Path(temp) / 'inputs.json'
            inputs.write_text(json.dumps(manifest))
            output = Path(temp) / 'feed.json'
            env = verifier_fixture(temp)
            argv = [sys.executable, str(CLI), 'build', '--root', str(ROOT), '--inputs', str(inputs),
                    '--sources', str(feeds.parent), '--as-of', '2026-03-01T00:00:00Z', '--output', str(output)]
            call = subprocess.run(argv, env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            payload = json.loads(call.stdout)['payload']
            self.assertEqual(payload['counts'], {'submitted': 1, 'eligible': 1, 'unscoreable': 0})
            self.assertEqual(payload['status'], 'measured')
            self.assertEqual(payload['losses'], {'lower_is_better': True, 'brier': 0.04, 'log_loss': 0.223143551314})
            self.assertEqual(payload['diagram']['bins'][8]['count'], 1)
            self.assertEqual(payload['diagram']['bins'][8]['empirical_frequency'], 1.0)
            self.assertFalse(payload['claim_scope']['publisher_price_accuracy'])
            check = subprocess.run([sys.executable, str(CLI), 'check', '--root', str(ROOT), '--report', str(output),
                                    '--sources', str(feeds.parent)], env=env, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(check.stdout, call.stdout)


    def invoke_fixture(self, temp, manifest, env=None):
        inputs = Path(temp) / 'inputs.json'
        inputs.write_text(json.dumps(manifest))
        argv = [sys.executable, str(CLI), 'build', '--root', str(ROOT), '--inputs', str(inputs),
                '--sources', str(Path(temp) / 'sources'), '--as-of', '2026-03-01T00:00:00Z']
        return subprocess.run(argv, env=env or verifier_fixture(temp), capture_output=True, text=True)

    def test_late_authentic_fixture_is_unscoreable_not_a_false_or_measured_score(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp, '2026-02-01T00:00:00Z')
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 0, call.stderr)
            report = json.loads(call.stdout)['payload']
            self.assertEqual(report['status'], 'unmeasured')
            self.assertEqual(report['counts'], {'submitted': 1, 'eligible': 0, 'unscoreable': 1})
            self.assertIsNone(report['losses']['brier'])
            self.assertIn('blindly registered', report['unscoreable'][0]['reason'])

    def test_rewritten_served_forecast_cannot_reuse_an_old_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            record = json.loads((feeds / 'forecasts/fixture.json').read_text())
            record['probability'] = 0.7
            publish_record(feeds, 'forecasts/fixture.json', record, 'forecast/v1.0.1', '2026-02-03T00:00:00Z')
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('rewritten', call.stderr)

    def test_independent_resolver_cannot_be_replaced_by_the_forecaster(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            manifest['pairs'][0]['resolution']['party'] = 'feeds'
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('independently sourced', call.stderr)

    def test_signed_fixture_question_substitution_is_rejected_at_the_actual_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            record = json.loads((resolver / 'resolutions/fixture.json').read_text())
            record['question']['proposition'] = 'A different explicit fixture event'
            reference = publish_record(resolver, 'resolutions/substitute.json', record, 'resolution/v1.0.1', '2026-02-03T00:00:00Z')
            manifest['pairs'][0]['resolution'] = reference
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('substitutes', call.stderr)

    def test_independence_and_population_duplicates_fail_before_any_score(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            manifest['targets'][0]['publisher'] = 'nist'
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('independent scorer', call.stderr)
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            manifest['pairs'].append(dict(manifest['pairs'][0]))
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('duplicate pair', call.stderr)

    def test_required_native_instruments_have_named_skip_and_help_is_independent(self):
        call = subprocess.run([sys.executable, '-S', str(CLI), '--help'], capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        call = subprocess.run([sys.executable, '-S', str(CLI), 'build', '--root', str(ROOT), '--as-of', '2026-03-01T00:00:00Z'], capture_output=True, text=True)
        self.assertEqual(call.returncode, 3, call.stderr)
        self.assertIn('SKIP: Python module yaml', call.stderr)
        with tempfile.TemporaryDirectory() as temp:
            feeds, target = source_fixture(temp)
            manifest = {'schema': 'publisher-reliability/inputs-v1', 'targets': [target], 'pairs': []}
            hidden = Path(temp) / 'hidden'
            hidden.mkdir()
            call = self.invoke_fixture(temp, manifest, dict(os.environ, PATH=str(hidden)))
            self.assertEqual(call.returncode, 3, call.stderr)
            self.assertIn('SKIP: Git', call.stderr)
            (hidden / 'git').symlink_to(shutil.which('git'))
            call = self.invoke_fixture(temp, manifest, dict(os.environ, PATH=str(hidden)))
            self.assertEqual(call.returncode, 3, call.stderr)
            self.assertIn('SKIP: gitsign', call.stderr)

    def test_public_payload_schema_rejects_numeric_loss_on_an_unmeasured_population(self):
        from jsonschema import Draft7Validator
        call = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(ROOT),
                               '--as-of', '2026-03-01T00:00:00Z'], capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        report = json.loads(call.stdout)['payload']
        schema = json.loads((ROOT / 'publisher-reliability/payload.schema.json').read_text())
        validator = Draft7Validator(schema)
        self.assertTrue(validator.is_valid(report))
        report['losses']['brier'] = 0.5  # Explicit invalid fixture, not a measured score.
        self.assertFalse(validator.is_valid(report))


    def test_scorer_discovery_cannot_publish_a_declared_target_feed(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, target = source_fixture(temp)
            copied = Path(temp) / 'scorer'
            shutil.copytree(ROOT / 'publisher-reliability', copied / 'publisher-reliability')
            (copied / 'party.yaml').write_text((ROOT / 'party.yaml').read_text() +
                '\n# Explicitly invalid discovery fixture.\n')
            import yaml
            declaration = yaml.safe_load((copied / 'party.yaml').read_text())
            declaration['publishes'].append({'kind': 'feed', 'name': target['name'], 'path': 'fixture', 'revoked': []})
            (copied / 'party.yaml').write_text(yaml.safe_dump(declaration))
            inputs = Path(temp) / 'inputs.json'
            inputs.write_text(json.dumps({'schema': 'publisher-reliability/inputs-v1', 'targets': [target], 'pairs': []}))
            call = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(copied),
                                   '--inputs', str(inputs), '--sources', str(feeds.parent),
                                   '--as-of', '2026-03-01T00:00:00Z'], env=verifier_fixture(temp), capture_output=True, text=True)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('publishes a declared target', call.stderr)

    def test_moved_input_tag_cannot_authenticate_a_different_pinned_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            env = dict(verifier_fixture(temp), FIXTURE_MOVE_TAG=manifest['targets'][0]['tag'])
            call = self.invoke_fixture(temp, manifest, env)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('changed', call.stderr)

    def test_report_cannot_claim_a_different_scoring_source_than_the_executing_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / 'scorer'
            shutil.copytree(ROOT / 'publisher-reliability', copied / 'publisher-reliability')
            shutil.copyfile(ROOT / 'party.yaml', copied / 'party.yaml')
            source = copied / 'publisher-reliability/scoring.py'
            source.write_text(source.read_text() + '\n# Explicit altered provenance fixture.\n')
            upstream = copied / 'publisher-reliability/UPSTREAM.json'
            provenance = json.loads(upstream.read_text())
            provenance['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            upstream.write_text(json.dumps(provenance))
            schema_path = copied / 'publisher-reliability/payload.schema.json'
            schema = json.loads(schema_path.read_text())
            schema['properties']['tool']['properties']['upstream']['const'] = provenance
            schema_path.write_text(json.dumps(schema))
            call = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(copied),
                                   '--as-of', '2026-03-01T00:00:00Z'], capture_output=True, text=True)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('executing scoring', call.stderr)


    def test_actual_native_wrapper_names_missing_instruments_before_any_selfcheck(self):
        with tempfile.TemporaryDirectory() as temp:
            hidden = Path(temp) / 'bin'
            hidden.mkdir()
            (hidden / 'dirname').symlink_to(shutil.which('dirname'))
            wrapper = ROOT / 'scripts/verify-publisher-reliability.sh'
            env = dict(os.environ, PATH=str(hidden), PYTHON='python3')
            call = subprocess.run(['/bin/bash', str(wrapper)], env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 3, call.stdout + call.stderr)
            self.assertIn('SKIP: publisher reliability needs Python 3', call.stdout)
            env['PYTHON'] = sys.executable
            call = subprocess.run(['/bin/bash', str(wrapper)], env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 3, call.stdout + call.stderr)
            self.assertIn('SKIP: publisher reliability needs Git', call.stdout)
            (hidden / 'git').symlink_to(shutil.which('git'))
            module_absent = hidden / 'module-absent-python'
            module_absent.write_text('#!/bin/bash\nexec ' + sys.executable + ' -S "$@"\n')
            module_absent.chmod(0o755)
            env['PYTHON'] = str(module_absent)
            call = subprocess.run(['/bin/bash', str(wrapper)], env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 3, call.stdout + call.stderr)
            self.assertIn('SKIP: Python module yaml', call.stderr)


    def test_duplicate_json_cannot_supply_ambiguous_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs = Path(temp) / 'inputs.json'
            inputs.write_text('{"schema":"publisher-reliability/inputs-v1","targets":[],"pairs":[],"pairs":[]}')
            call = subprocess.run([sys.executable, str(CLI), 'build', '--root', str(ROOT),
                                   '--inputs', str(inputs), '--as-of', '2026-03-01T00:00:00Z'], capture_output=True, text=True)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('duplicate JSON key', call.stderr)

    def test_signed_fixture_forecast_target_substitution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            record = json.loads((feeds / 'forecasts/fixture.json').read_text())
            record['target']['name'] = 'different-explicit-fixture-feed'
            manifest['pairs'][0]['forecast'] = publish_record(feeds, 'forecasts/substitute.json', record,
                                                             'forecast/v1.0.1', '2026-01-03T00:00:00Z')
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('exact declared signed feed pin', call.stderr)

    def test_numeric_outcome_cannot_be_coerced_into_a_true_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            record = json.loads((resolver / 'resolutions/fixture.json').read_text())
            record['observed'] = 1
            manifest['pairs'][0]['resolution'] = publish_record(resolver, 'resolutions/nonboolean.json', record,
                                                               'resolution/v1.0.1', '2026-02-03T00:00:00Z')
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('not of type', call.stderr)

    def test_zero_verifier_exit_without_real_verification_facts_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            env = dict(verifier_fixture(temp), FIXTURE_OMIT_SIGNATURE_FACTS='1')
            call = self.invoke_fixture(temp, manifest, env)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('signature verification refused', call.stderr)

    def test_missing_jsonschema_is_an_exercised_native_instrument_wait(self):
        import yaml
        with tempfile.TemporaryDirectory() as temp:
            # Only the actual PyYAML package is available under -S; jsonschema is physically absent.
            (Path(temp) / 'yaml').symlink_to(Path(yaml.__file__).parent, target_is_directory=True)
            env = dict(os.environ, PYTHONPATH=temp)
            call = subprocess.run([sys.executable, '-S', str(CLI), 'build', '--root', str(ROOT),
                                   '--as-of', '2026-03-01T00:00:00Z'], env=env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 3, call.stderr)
            self.assertIn('SKIP: Python module jsonschema', call.stderr)


    def test_score_carries_target_blob_from_the_authenticated_source(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 0, call.stderr)
            target = manifest['targets'][0]
            expected = {key: value for key, value in target.items() if key != 'id'}
            expected['git_blob'] = fixture_git(feeds, 'rev-parse', target['commit'] + ':' + target['path'])
            self.assertEqual(json.loads(call.stdout)['payload']['scores'][0]['target_reference'], expected)


    def test_target_alias_cannot_duplicate_the_same_authenticated_feed(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, target = source_fixture(temp)
            alias = dict(target, id='another-id-for-the-identical-feed')
            manifest = {'schema': 'publisher-reliability/inputs-v1', 'targets': [target, alias], 'pairs': []}
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('duplicate authenticated target', call.stderr)

    def test_signed_target_discovery_without_a_path_has_a_named_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, target = source_fixture(temp)
            import yaml
            declaration = yaml.safe_load((feeds / 'party.yaml').read_text())
            del declaration['publishes'][0]['path']
            (feeds / 'party.yaml').write_text(yaml.safe_dump(declaration))
            document = json.loads((feeds / target['path']).read_text())
            document['version'] = '1.0.1'
            (feeds / target['path']).write_text(json.dumps(document))
            fixture_git(feeds, 'add', 'party.yaml', target['path'])
            fixture_git(feeds, 'commit', '-qm', 'explicit malformed target discovery fixture')
            fixture_git(feeds, 'tag', '-a', 'fixture-binary-source/v1.0.1', '-m', 'unsigned fixture')
            target.update(tag='fixture-binary-source/v1.0.1', commit=fixture_git(feeds, 'rev-parse', 'HEAD'))
            fixture_git(feeds, 'update-ref', 'refs/remotes/origin/main', target['commit'])
            call = self.invoke_fixture(temp, {'schema': 'publisher-reliability/inputs-v1', 'targets': [target], 'pairs': []})
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertTrue(call.stderr.rstrip().splitlines()[-1].startswith('FAIL:'), call.stderr)
            self.assertIn('discovery', call.stderr)

    def test_same_question_id_cannot_be_rescored_with_substitute_text(self):
        with tempfile.TemporaryDirectory() as temp:
            feeds, resolver, manifest = binary_pair_fixture(temp)
            forecast = json.loads((feeds / 'forecasts/fixture.json').read_text())
            forecast['question']['proposition'] = 'Substitute text for the same explicit fixture identity'
            reference = publish_record(feeds, 'forecasts/duplicate-question.json', forecast,
                                       'forecast/v1.0.1', '2026-01-03T00:00:00Z')
            manifest['pairs'].append({'id': 'another-explicit-fixture-pair', 'target': manifest['targets'][0]['id'],
                                      'forecast': reference, 'resolution': None})
            call = self.invoke_fixture(temp, manifest)
            self.assertEqual(call.returncode, 1, call.stderr)
            self.assertIn('target/question', call.stderr)


if __name__ == '__main__':
    unittest.main()
