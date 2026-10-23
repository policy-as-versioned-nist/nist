"""Pure SDK admission/converter seam; source authentication is an explicit fixture.

No Git signatures, engine draws, reports, registrations or observed expenses are produced.
The converter fixture is synthetic; private cross-repository integration additionally
runs the actual recovery publisher converter through this same prepare() boundary.
"""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'publisher-reliability'))
import price_records as sdk


def ref(party, path):
    return {'party': party, 'tag': 'recovery-expense/v1.0.0' if party == 'feeds' else 'TEST-ONLY-UNSIGNED/v1.0.0',
            'commit': 'a' * 40, 'path': path, 'git_blob': 'b' * 40}


class FixtureSources:
    """Explicit stand-in for authenticated source reads; never an SDK public flag."""
    def __init__(self, docs, raw):
        self.docs, self.bytes = docs, raw

    def read(self, reference):
        return {**reference, 'document': copy.deepcopy(self.docs[(reference['party'], reference['path'])])}

    def path_ref(self, enclosing, path):
        return {k: v for k, v in {**enclosing, 'path': path}.items() if k != 'document'}

    def at(self, enclosing, relative):
        return self.read(self.path_ref(enclosing, relative['path']))

    def raw(self, reference):
        return {**reference, 'raw': self.bytes[(reference['party'], reference['path'])]}


def fixture():
    engine = sdk._engine_ref(ROOT)  # Hash checks only; no engine execution.
    context = ref('driftwood', 'party.yaml')
    case = {'case_id': 'driftwood/2027', 'subject': 'driftwood', 'perspective': 'driftwood',
        'horizon': {'starts_at': '2027-01-01T00:00:00Z', 'ends_at': '2028-01-01T00:00:00Z', 'boundary': '[start,end)'},
        'context_ref': context}
    inventory = {'schema': 'publisher-reliability/price-cases-v1', 'profile_id': 'TEST-ONLY-recovery', 'cases': [case]}
    profile = {'schema': 'publisher-reliability/price-profile-v1', 'id': inventory['profile_id'],
        'criterion': 'money-empirical-crps/v1', 'outcome_kind': 'annual-aggregate-loss/v1',
        'target_feed': {'publisher': 'feeds', 'name': 'recovery-expense'},
        'unit': {'currency': 'GBP', 'basis': 'TEST ONLY nominal direct recovery expense'},
        'definition': {'loss_categories': ['TEST ONLY'], 'accounting_rule': 'TEST ONLY',
            'completeness_rule': 'TEST ONLY', 'finality_rule': 'TEST ONLY'},
        'horizon_rule': {'duration': 'P1Y', 'boundary': '[start,end)', 'calendar': 'UTC-Gregorian'},
        'resolver_rule': {'party': 'platform', 'source_schema': 'recovery-expense/resolution-source-v1',
            'amount_pointer': '/amount', 'finality_pointer': '/final', 'completeness_pointer': '/complete',
            'evidence_uri_prefix': 'https://fixture.invalid/'},
        'population': {'case_inventory': {'path': 'cases.json', 'git_blob': 'c' * 40},
            'registration_deadline': 'strictly-before-horizon-start', 'aggregation': 'equal-case-mean',
            'overlap_rule': 'distinct-case-subject-horizon-no-overlap'},
        'generator': {'kind': 'pinned-fair-annual-empirical/v1', 'engine': engine, 'state': 'warn',
            'parameter_policy': 'explicit-per-registration-recorded-not-inferred'}}
    scenario = {'version': 'v1', 'name': 'TEST ONLY recovery converter',
        'warn': {'lef': [0, 1, 2], 'lm': [10, 20, 30]}, 'deny': {'lef': [0, 1, 2], 'lm': [10, 20, 30]}}
    converter = b'''import json,sys
assert sys.argv[1:]==['forecast-base','payload.json','context.json']
p=json.load(open('payload.json')); c=json.load(open('context.json'))
assert c['schema']=='publisher-reliability/generator-context-v1'
assert c['document']['party']=='driftwood'
print(json.dumps(p['TEST_ONLY_scenario']))
'''
    payload = {'currency': 'GBP', 'feed_version': 'v1', 'TEST_ONLY_scenario': scenario}
    target = {'kind': 'feed', 'name': 'recovery-expense', 'version': '1.0.0', 'published_by': 'feeds',
        'published_at': '2026-10-23T00:00:00Z', 'payload_schema': 'recovery-expense/payload.schema.json', 'payload': payload}
    docs = {('feeds', 'profile.json'): profile, ('feeds', 'cases.json'): inventory,
        ('feeds', 'recovery-expense/v1/feed.json'): target,
        ('feeds', 'recovery-expense/payload.schema.json'): {'type': 'object'},
        ('feeds', 'party.yaml'): {'party': 'feeds', 'publishes': [{'kind': 'feed', 'name': 'recovery-expense',
            'path': 'recovery-expense', 'payload_schema': 'recovery-expense/payload.schema.json'}]},
        ('driftwood', 'party.yaml'): {'party': 'driftwood', 'reporting_currency': 'GBP', 'inherits': [
            {'party': 'feeds', 'kind': 'feed', 'name': 'threat-register', 'version': 'v4'},
            {'party': 'ico', 'kind': 'feed', 'name': 'penalty-schema', 'version': 'v3'},
            {'party': 'feeds', 'kind': 'feed', 'name': 'recovery-expense', 'version': 'v1'}]}}
    session = object.__new__(sdk._Session)
    session.root, session.work = ROOT, [0, 0, 0]
    session.sources = FixtureSources(docs, {('feeds', 'recovery-expense/to_fair_scenario.py'): converter})
    generator = {'kind': 'pinned-fair-annual-empirical/v1', 'engine': engine,
        'converter': ref('feeds', 'recovery-expense/to_fair_scenario.py'),
        'invocation': ['forecast-base', 'payload.json', 'context.json'], 'context_ref': context,
        'scenario': scenario, 'state': 'warn', 'seed': 42, 'iterations': 2}
    return session, {'profile_ref': ref('feeds', 'profile.json'), 'target_ref': ref('feeds', 'recovery-expense/v1/feed.json'),
        'case_id': case['case_id'], 'emitted_at': '2026-10-24T00:00:00Z', 'generator': generator}


class ShadowRecoveryAdapter(unittest.TestCase):
    def setUp(self):
        self.session, self.request = fixture()
        before = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
        for name, value in (('_arrival', '2026-10-23T00:00:00Z'), ('_content_time', before)):
            p = patch.object(sdk, name, return_value=value)
            p.start(); self.addCleanup(p.stop)

    def test_real_prepare_admits_additive_shadow_edge_and_reproduces_converter(self):
        current = copy.deepcopy(self.session.sources.docs[('driftwood', 'party.yaml')])
        result = self.session.prepare(**self.request)
        self.assertEqual(result['forecast']['generator'], self.request['generator'])
        self.assertEqual(result['forecast']['target']['path'], 'recovery-expense/v1/feed.json')
        self.assertNotIn('distribution', result['forecast'])  # prepare never draws or registers.
        self.assertEqual(self.session.sources.docs[('driftwood', 'party.yaml')], current)

    def test_wrong_served_path_or_forecast_values_refuse(self):
        self.request['generator']['converter']['path'] = 'threat-register/to_fair_scenario.py'
        with self.assertRaisesRegex(sdk.PriceError, 'supported served converter path'):
            self.session.prepare(**self.request)
        self.request['generator']['converter']['path'] = 'recovery-expense/to_fair_scenario.py'
        self.request['generator']['scenario'] = copy.deepcopy(self.request['generator']['scenario'])
        self.request['generator']['scenario']['warn']['lm'] = [1, 1, 1]
        with self.assertRaisesRegex(sdk.PriceError, 'differs from actual signed publisher converter'):
            self.session.prepare(**self.request)

    def test_no_implicit_target_from_existing_threat_edge(self):
        self.session.sources.docs[('driftwood', 'party.yaml')]['inherits'].pop()
        with self.assertRaisesRegex(sdk.PriceError, 'one exact target-party/feed edge'):
            self.session.prepare(**self.request)

    def test_discovery_schema_and_resolver_authority_still_refuse(self):
        doc = self.session.sources.docs[('feeds', 'party.yaml')]['publishes'][0]
        doc['payload_schema'] = 'threat-register/payload.schema.v4.json'
        with self.assertRaisesRegex(sdk.PriceError, 'discovery/path/schema mismatch'):
            self.session.prepare(**self.request)
        doc['payload_schema'] = 'recovery-expense/payload.schema.json'
        self.session.sources.docs[('feeds', 'profile.json')]['resolver_rule']['party'] = 'feeds'
        with self.assertRaisesRegex(sdk.PriceError, 'different independent resolution publisher'):
            self.session.prepare(**self.request)

    def test_supported_set_is_closed_and_original_converter_paths_unchanged(self):
        self.assertEqual(sdk._SERVED_CONVERTERS, {('ico', 'penalty-schema'): 'schema/to_fair_scenario.py',
            ('feeds', 'threat-register'): 'threat-register/to_fair_scenario.py',
            ('feeds', 'recovery-expense'): 'recovery-expense/to_fair_scenario.py'})
        self.session.sources.docs[('feeds', 'recovery-expense/v1/feed.json')]['name'] = 'caller-new-family'
        self.session.sources.docs[('feeds', 'profile.json')]['target_feed']['name'] = 'caller-new-family'
        self.request['target_ref']['tag'] = 'caller-new-family/v1.0.0'
        with self.assertRaisesRegex(sdk.PriceError, 'unsupported-profile'):
            self.session.prepare(**self.request)


if __name__ == '__main__':
    unittest.main()
