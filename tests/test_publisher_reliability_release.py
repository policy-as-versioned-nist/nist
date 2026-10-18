"""Namespaced release routing using unsigned synthetic Git, never real publication."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / '.github/scripts/report-bump-gate.py'
TAG = 'publisher-reliability/v1.0.0'


def git(repo, *args):
    call = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'commit.gpgsign=false',
                           '-c', 'tag.gpgsign=false', '-c', 'user.name=synthetic release fixture',
                           '-c', 'user.email=fixture@example.invalid', '-C', str(repo), *args],
                          text=True, capture_output=True)
    if call.returncode:
        raise AssertionError(call.stderr)
    return call.stdout.strip()


class ReportRelease(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='synthetic-report-release-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.upstream = self.base / 'upstream'
        self.upstream.mkdir()
        shutil.copytree(ROOT / 'publisher-reliability', self.upstream / 'publisher-reliability',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(ROOT / 'party.yaml', self.upstream / 'party.yaml')
        tools = self.upstream / '.github/scripts'
        tools.mkdir(parents=True)
        shutil.copyfile(GATE, tools / GATE.name)
        git(self.upstream, 'init', '-q', '-b', 'main')
        git(self.upstream, 'add', '.')
        git(self.upstream, 'commit', '-qm', 'synthetic first report source')
        git(self.upstream, 'tag', 'v99.0.0')  # Catalogue family must not select a report predecessor.
        self.repo = self.base / 'clone'
        subprocess.run(['git', 'clone', '-q', str(self.upstream), str(self.repo)], check=True)

    def invoke(self, tag=TAG):
        return subprocess.run([sys.executable, str(GATE), '--root', str(self.repo), tag],
                              text=True, capture_output=True)

    def change(self, path, value):
        destination = self.repo / path
        destination.write_text(json.dumps(value, sort_keys=True) + '\n')

    def report(self):
        return json.loads((self.repo / 'publisher-reliability/v1/feed.json').read_text())

    def previous(self):
        git(self.repo, 'tag', '-a', TAG, '-m', 'explicit unsigned predecessor fixture')
        git(self.repo, 'push', '-q', 'origin', 'refs/tags/' + TAG)

    def next_version(self, version, bump):
        self.change('publisher-reliability/version.json', {'version': version, 'tool_version': '1.0.0'})
        report = self.report()
        report['version'] = version
        destination = self.repo / ('publisher-reliability/v' + version.split('.')[0] + '/feed.json')
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(report, sort_keys=True) + '\n')
        (self.repo / 'publisher-reliability/bump.yaml').write_text('bump: ' + bump + '\n')

    def test_bootstrap_namespaced_route_ignores_catalogue_tags(self):
        call = self.invoke()
        self.assertEqual(call.returncode, 0, call.stderr + call.stdout)
        self.assertIn('bootstrap', call.stdout)
        self.assertIn('no predecessor', call.stdout)
        wrong = self.invoke('publisher-reliability/v2.0.0')
        self.assertEqual(wrong.returncode, 1, wrong.stdout)

    def test_declared_patch_matches_exact_next_report_increment(self):
        self.previous()
        self.next_version('1.0.1', 'patch')
        report = self.report()
        report['published_at'] = report['payload']['as_of'] = '2026-10-17T08:00:00Z'
        self.change('publisher-reliability/v1/feed.json', report)
        call = self.invoke('publisher-reliability/v1.0.1')
        self.assertEqual(call.returncode, 0, call.stderr + call.stdout)
        self.assertIn('computed patch', call.stdout)
        wrong = self.invoke('publisher-reliability/v1.1.0')
        self.assertEqual(wrong.returncode, 1, wrong.stdout)

    def test_none_and_schema_change_cannot_hide_as_a_patch(self):
        self.previous()
        self.next_version('1.0.1', 'patch')
        self.assertEqual(self.invoke('publisher-reliability/v1.0.1').returncode, 1)
        schema = json.loads((self.repo / 'publisher-reliability/payload.schema.json').read_text())
        schema['description'] = 'Explicit synthetic schema change; not a real release.'
        self.change('publisher-reliability/payload.schema.json', schema)
        refused = self.invoke('publisher-reliability/v1.0.1')
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn('computed major', refused.stdout)
        self.next_version('2.0.0', 'major')
        self.assertEqual(self.invoke('publisher-reliability/v2.0.0').returncode, 0)

    def test_missing_local_predecessor_and_occupied_ref_refuse(self):
        self.previous()
        occupied = self.invoke()
        self.assertEqual(occupied.returncode, 1)
        self.assertIn('already exists', occupied.stdout)
        git(self.repo, 'tag', '-d', TAG)
        self.next_version('1.0.1', 'patch')
        missing = self.invoke('publisher-reliability/v1.0.1')
        self.assertEqual(missing.returncode, 1, missing.stdout)
        self.assertIn('missing local', missing.stdout)


    def workflow(self, name):
        return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)

    def step(self, workflow, name):
        steps = self.workflow(workflow)['jobs']['cut' if workflow == 'cut-release.yml' else 'release']['steps']
        matches = [step for step in steps if step.get('name') == name]
        self.assertEqual(len(matches), 1, 'actual workflow is missing ' + name)
        return matches[0]

    def run_step(self, step, **environment):
        return subprocess.run(['/bin/bash', '-euo', 'pipefail', '-c', step['run']], cwd=self.repo,
                              env=dict(os.environ, **environment), capture_output=True, text=True)

    def test_actual_cut_report_gate_shell_uses_the_namespaced_computation(self):
        step = self.step('cut-release.yml', 'report declared bump and exact version')
        self.assertEqual(step['env']['VERSION_INPUT'], '${{ inputs.version }}')
        call = self.run_step(step, VERSION_INPUT=TAG)
        self.assertEqual(call.returncode, 0, call.stderr + call.stdout)
        self.assertIn('bootstrap', call.stdout)
        wrong = self.run_step(step, VERSION_INPUT='publisher-reliability/v2.0.0')
        self.assertEqual(wrong.returncode, 1, wrong.stdout)

    def test_actual_cut_family_route_requires_main_only_for_reports(self):
        step = self.step('cut-release.yml', 'select the bounded publication family')
        output = self.base / 'cut-env'
        accepted = self.run_step(step, VERSION_INPUT=TAG, GITHUB_REF='refs/heads/main', GITHUB_ENV=str(output))
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertIn('PUBLICATION_KIND=report', output.read_text())
        refused = self.run_step(step, VERSION_INPUT=TAG, GITHUB_REF='refs/heads/release/1.0.x', GITHUB_ENV=str(output))
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        catalogue = self.run_step(step, VERSION_INPUT='v1.1.0', GITHUB_REF='refs/heads/release/1.1.x', GITHUB_ENV=str(output))
        self.assertEqual(catalogue.returncode, 0, catalogue.stdout + catalogue.stderr)
        self.assertIn('PUBLICATION_KIND=catalogue', output.read_text())

    def test_actual_release_routes_main_only_report_identity_and_signed_source_check(self):
        step = self.step('release.yml', 'select publication family and verification identity')
        output = self.base / 'release-env'
        call = self.run_step(step, TAG=TAG, GITHUB_ENV=str(output))
        self.assertEqual(call.returncode, 0, call.stderr + call.stdout)
        assigned = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(assigned['EXPECTED_IDENTITY_REGEXP'], r'^https://github\.com/policy-as-versioned-nist/nist/\.github/workflows/cut-release\.yml@refs/heads/main$')
        self.assertIn('publisher-reliability/v*.*.*', self.workflow('release.yml')['on']['push']['tags'])
        checked = self.step('release.yml', 'verify report from the exact authenticated source')
        self.assertIn('VERIFIED_TAG_OBJECT', checked['run'])
        self.assertIn('report.py', checked['run'])
        self.assertIn('check', checked['run'])

    def test_existing_catalogue_gate_and_structured_offline_tag_signing_remain(self):
        cut = self.workflow('cut-release.yml')
        steps = cut['jobs']['cut']['steps']
        old_gate = [step for step in steps if 'declared bump must agree' in step.get('name', '')][0]
        self.assertIn('.github/scripts/declared-bump-gate.py', old_gate['run'])
        self.assertEqual(old_gate['if'], "env.PUBLICATION_KIND == 'catalogue'")
        signing = [step for step in steps if step.get('name', '').startswith('create the signed annotated tag')][0]
        self.assertIn('gitsign.rekorMode=offline', signing['run'])
        self.assertEqual(signing['env']['VERSION_INPUT'], '${{ inputs.version }}')
        self.assertEqual(signing['env']['MESSAGE_INPUT'], '${{ inputs.message }}')
        self.assertNotIn('${{', signing['run'])


    def test_local_predecessor_object_must_equal_the_actual_origin_tag(self):
        self.previous()
        report = self.report()
        report['published_at'] = report['payload']['as_of'] = '2026-10-17T06:00:00Z'
        self.change('publisher-reliability/v1/feed.json', report)
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'explicit unpublished predecessor substitution fixture')
        git(self.repo, 'tag', '-f', '-a', TAG, '-m', 'different unsigned fixture object')
        self.next_version('1.0.1', 'patch')
        report = self.report()
        report['published_at'] = report['payload']['as_of'] = '2026-10-17T08:00:00Z'
        self.change('publisher-reliability/v1/feed.json', report)
        refused = self.invoke('publisher-reliability/v1.0.1')
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn('differs from origin', refused.stdout)


if __name__ == '__main__':
    unittest.main()
