"""Whole monetary SDK seams; every nonempty population is explicitly synthetic."""
from pathlib import Path
import copy
import json
import sys
import unittest
import os
import tempfile
import subprocess
import shutil
import hashlib
from unittest.mock import patch
from test_publisher_reliability import fixture_git, verifier_fixture
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'publisher-reliability'))


def new_source(temp, party):
    repo = Path(temp) / 'sources' / party
    repo.mkdir(parents=True)
    fixture_git(repo, 'init', '-q', '-b', 'main')
    for key, value in [('user.name', 'explicit synthetic price fixture'),
                       ('user.email', 'fixture@example.invalid'), ('commit.gpgsign', 'false'),
                       ('tag.gpgSign', 'false'), ('core.hooksPath', os.devnull)]:
        fixture_git(repo, 'config', key, value)
    fixture_git(repo, 'remote', 'add', 'origin',
                f'https://github.com/policy-as-versioned-{party}/{party}.git')
    return repo


def publish(repo, documents, tag, at):
    for path, value in documents.items():
        dest = repo / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value if isinstance(value, str) else json.dumps(value))
    fixture_git(repo, 'add', '.', at=at)
    fixture_git(repo, 'commit', '-qm', 'explicit synthetic source, never world evidence', at=at)
    commit = fixture_git(repo, 'rev-parse', 'HEAD')
    fixture_git(repo, 'tag', '-a', tag, '-m', 'unsigned synthetic fixture', at=at)
    fixture_git(repo, 'update-ref', 'refs/remotes/origin/main', commit)
    def ref(path):
        return {'party': repo.name, 'tag': tag, 'commit': commit, 'path': path,
                'git_blob': fixture_git(repo, 'rev-parse', commit + ':' + path)}
    return ref


def annual_fixture(temp, *, lef=1, iterations=2, defer_forecast=False, context_at='2019-11-01T00:00:00Z', native_currency='GBP'):
    """Real Git/source readers/converter/FAIR; only signature boundary is synthetic."""
    from price_records import build_forecast, build_resolution
    adopter = new_source(temp, 'driftwood')
    context = publish(adopter, {'party.yaml':
        'party: driftwood\nroles: [adopter, risk-bearer]\nreporting_currency: GBP\ninherits:\n  - {party: ico, kind: feed, name: penalty-schema, version: v1}\nsize:\n  turnover: {amount: 100, currency: GBP}\n'},
        'context/v1.0.0', context_at)('party.yaml')
    publisher = new_source(temp, 'ico')
    converter = """import json,sys
assert sys.argv[1:] == ['forecast-base','payload.json','context.json']
p=json.load(open('payload.json')); c=json.load(open('context.json'))
assert c['schema']=='publisher-reliability/generator-context-v1'
assert c['document']['party']=='driftwood'
m=p['money']; f=p['frequency']
print(json.dumps({'version':'synthetic1','name':'explicit synthetic constant model',
 'warn':{'lef':[f,f,f],'lm':[m,m,m]},'deny':{'lef':[0,0,0],'lm':[m,m,m]}}))
"""
    target = {'kind':'feed','name':'penalty-schema','version':'1.0.0','published_by':'ico',
              'published_at':'2019-11-01T00:00:00Z','payload_schema':'annual/payload.schema.json',
              'payload':{'money':10,'frequency':lef,'regimes':{'uk-gdpr':{'currency':native_currency}}}}
    initial = publish(publisher, {'penalty-schema/v1/feed.json':target,'annual/payload.schema.json':{'type':'object'},
        'schema/to_fair_scenario.py':converter,'schema/alternate.py':converter,'party.yaml':
        'party: ico\nroles: [publisher]\npublishes:\n  - {kind: feed, name: penalty-schema, path: penalty-schema, payload_schema: annual/payload.schema.json}\n'},
        'penalty-schema/v1.0.0','2019-11-01T00:00:00Z')
    horizon={'starts_at':'2020-01-01T00:00:00Z','ends_at':'2021-01-01T00:00:00Z','boundary':'[start,end)'}
    unit={'currency':'GBP','basis':'explicit synthetic nominal GBP'}
    inventory={'schema':'publisher-reliability/price-cases-v1','profile_id':'synthetic-annual',
        'cases':[{'case_id':'case-one','subject':'driftwood','perspective':'driftwood',
                  'horizon':horizon,'context_ref':context}]}
    invraw=json.dumps(inventory).encode()
    invblob=__import__('hashlib').sha1(b'blob '+str(len(invraw)).encode()+b'\0'+invraw).hexdigest()
    engine=json.loads((ROOT/'publisher-reliability/PRICE-UPSTREAM.json').read_text())
    engine_ref={'party':'platform','tag':engine['tag'],'commit':engine['commit'],
                'path':'fair/fair.py','git_blob':engine['files'][0]['git_blob']}
    profile={'schema':'publisher-reliability/price-profile-v1','id':'synthetic-annual',
      'criterion':'money-empirical-crps/v1','outcome_kind':'annual-aggregate-loss/v1',
      'target_feed':{'publisher':'ico','name':'penalty-schema'},'unit':unit,
      'definition':{'loss_categories':['synthetic-only'],'accounting_rule':'synthetic gross loss',
                    'completeness_rule':'complete synthetic annual ledger','finality_rule':'settled'},
      'horizon_rule':{'duration':'P1Y','boundary':'[start,end)','calendar':'UTC-Gregorian'},
      'resolver_rule':{'party':'feeds','source_schema':'synthetic-ledger/v1','amount_pointer':'/amount',
          'finality_pointer':'/final','completeness_pointer':'/complete','evidence_uri_prefix':'https://fixture.invalid/'},
      'population':{'case_inventory':{'path':'cases.json','git_blob':invblob},
          'registration_deadline':'strictly-before-horizon-start','aggregation':'equal-case-mean',
          'overlap_rule':'distinct-case-subject-horizon-no-overlap'},
      'generator':{'kind':'pinned-fair-annual-empirical/v1','engine':engine_ref,'state':'warn',
                   'parameter_policy':'explicit-per-registration-recorded-not-inferred'}}
    declared = publish(publisher, {'profile.json':profile,'cases.json':inventory},
                       'profile/v1.0.0','2019-12-01T00:00:00Z')
    generator={'kind':'pinned-fair-annual-empirical/v1','engine':engine_ref,
      'converter':initial('schema/to_fair_scenario.py'),'invocation':['forecast-base','payload.json','context.json'],
      'context_ref':context,'scenario':{'version':'synthetic1','name':'explicit synthetic constant model',
           'warn':{'lef':[lef,lef,lef],'lm':[10,10,10]},'deny':{'lef':[0,0,0],'lm':[10,10,10]}},
      'state':'warn','seed':42,'iterations':iterations}
    request=dict(profile=declared('profile.json'),target=initial('penalty-schema/v1/feed.json'),
        case_id='case-one',emitted_at='2019-12-02T00:00:00Z',generator=generator,source_roots=publisher.parent)
    if defer_forecast:
        return request
    forecast=build_forecast(ROOT,**request)
    forecast_ref=publish(publisher,{'forecast.json':forecast},'forecast/v1.0.0',
                         '2019-12-03T00:00:00Z')('forecast.json')
    resolver=new_source(temp,'feeds')
    observed=publish(resolver,{'ledger.json':{'schema':'synthetic-ledger/v1','amount':'30',
        'final':True,'complete':True,'case_id':'case-one','subject':'driftwood','perspective':'driftwood',
        'horizon':horizon,'unit':unit}},'ledger/v1.0.0','2021-01-02T00:00:00Z')('ledger.json')
    resolution=build_resolution(ROOT,forecast=forecast_ref,profile=declared('profile.json'),source=observed,
        resolved_at='2021-01-02T00:00:00Z',published_at='2021-01-03T00:00:00Z',
        evidence_uri='https://fixture.invalid/explicit-synthetic-ledger',source_roots=publisher.parent)
    resolution_ref=publish(resolver,{'resolution.json':resolution},'resolution/v1.0.0',
                           '2021-01-03T00:00:00Z')('resolution.json')
    manifest={'schema':'publisher-reliability/price-input-set-v1','cohorts':[
      {'schema':'publisher-reliability/price-inputs-v1','profile':declared('profile.json'),
       'target':initial('penalty-schema/v1/feed.json'),'cases':[{'case_id':'case-one',
          'forecast':forecast_ref,'resolution':resolution_ref}]}]}
    return forecast,resolution,manifest,publisher.parent


class PriceReport(unittest.TestCase):
    def test_empty_report_set_recomputes_without_inventing_a_cohort_or_money(self):
        from price_accuracy import build_price_report, check_price_report
        inputs = {'schema': 'publisher-reliability/price-input-set-v1', 'cohorts': []}
        result = build_price_report(ROOT, inputs, '2026-10-18T17:00:00Z')
        self.assertEqual(result['reports'], [])
        self.assertEqual(result['inputs'], inputs)
        self.assertEqual(result['reason'], 'no declared monetary cohorts; no publisher-price accuracy measurement')
        self.assertNotIn('score', result)
        self.assertNotIn('unit', result)
        self.assertEqual(check_price_report(ROOT, result), result)
        changed = copy.deepcopy(result)
        changed['reason'] = 'calibrated'
        with self.assertRaises(ValueError):
            check_price_report(ROOT, changed)

    def test_real_source_producer_resolver_and_report_reproduce_the_same_distribution(self):
        from price_accuracy import build_price_report, check_price_report
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, verifier_fixture(temp)):
                forecast,resolution,manifest,sources=annual_fixture(temp)
                self.assertEqual(forecast['distribution'], {'kind':'weighted-empirical/v1',
                    'total_count':2,'atoms':[{'value':'10','count':2}]})
                self.assertEqual(resolution['observed'],'30')
                report=build_price_report(ROOT,manifest,'2021-02-01T00:00:00Z',sources)
                cohort=report['reports'][0]
                self.assertEqual(cohort['score'],{'numerator':'-20','denominator':'1'})
                self.assertEqual(cohort['counts'],{'registered_cases':1,'eligible':1,'unscoreable':0})
                self.assertEqual(check_price_report(ROOT,report,sources),report)

    def test_empty_report_refuses_a_rehashed_substitution_for_the_fixed_released_engine(self):
        from price_accuracy import build_price_report
        from price_records import PriceError
        with tempfile.TemporaryDirectory() as temp:
            altered = Path(temp) / 'altered-source'
            shutil.copytree(ROOT, altered, ignore=shutil.ignore_patterns('.git','__pycache__'))
            engine = altered / 'publisher-reliability/vendor/fair/fair.py'
            engine.write_bytes(engine.read_bytes() + b'\n# synthetic tampered source\n')
            provenance = altered / 'publisher-reliability/PRICE-UPSTREAM.json'
            doc = json.loads(provenance.read_text())
            doc['files'][0]['sha256'] = hashlib.sha256(engine.read_bytes()).hexdigest()
            provenance.write_text(json.dumps(doc))
            with self.assertRaises(PriceError) as refused:
                build_price_report(altered, {'schema':'publisher-reliability/price-input-set-v1','cohorts':[]},
                                   '2026-10-18T17:00:00Z')
            self.assertEqual(refused.exception.code,'source-binding')

    def test_actual_cli_build_check_has_an_empty_versioned_envelope(self):
        cli = ROOT / 'publisher-reliability/price_report.py'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            built = subprocess.run([sys.executable,str(cli),'build','--root',str(ROOT),
                '--as-of','2026-10-18T17:00:00Z','--output',str(path)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            envelope = json.loads(built.stdout)
            self.assertEqual(envelope['version'],'2.0.0')
            self.assertEqual(envelope['payload']['reports'],[])
            checked = subprocess.run([sys.executable,str(cli),'check','--root',str(ROOT),
                '--report',str(path)],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertEqual(checked.stdout,built.stdout)

    def test_missing_or_early_outcomes_remain_null_and_population_cannot_be_omitted(self):
        from price_accuracy import build_price_report
        from price_records import PriceError
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,verifier_fixture(temp)):
            forecast,resolution,manifest,sources=annual_fixture(temp)
            missing=copy.deepcopy(manifest)
            missing['cohorts'][0]['cases'][0]['resolution']=None
            for inputs,cutoff in [(missing,'2021-02-01T00:00:00Z'),(manifest,'2020-06-01T00:00:00Z')]:
                cohort=build_price_report(ROOT,inputs,cutoff,sources)['reports'][0]
                self.assertEqual(cohort['status'],'unmeasured')
                self.assertEqual(cohort['counts'],{'registered_cases':1,'eligible':0,'unscoreable':1})
                self.assertIsNone(cohort['score']);self.assertIsNone(cohort['loss'])
                self.assertTrue(cohort['cases'][0]['reason'])
            omitted=copy.deepcopy(manifest);omitted['cohorts'][0]['cases']=[]
            with self.assertRaises(PriceError) as refused:
                build_price_report(ROOT,omitted,'2021-02-01T00:00:00Z',sources)
            self.assertEqual(refused.exception.code,'population-binding')
            wrong=copy.deepcopy(manifest);wrong['cohorts'][0]['cases'][0]['forecast']['git_blob']='0'*40
            with self.assertRaises(PriceError) as refused:
                build_price_report(ROOT,wrong,'2021-02-01T00:00:00Z',sources)
            self.assertEqual(refused.exception.code,'source-binding')

    def test_signed_alternate_converter_cannot_replace_the_served_model(self):
        from price_records import build_forecast, PriceError
        with tempfile.TemporaryDirectory() as temp:
            request=annual_fixture(temp,defer_forecast=True)
            request['generator']['converter']['path']='schema/alternate.py'
            with patch.dict(os.environ,verifier_fixture(temp)):
                with self.assertRaises(PriceError) as refused:
                    build_forecast(ROOT,**request)
            self.assertEqual(refused.exception.code,'unsupported-profile')

    def test_native_currency_cannot_be_relabelled_as_reporting_currency(self):
        from price_records import build_forecast, PriceError
        with tempfile.TemporaryDirectory() as temp:
            request=annual_fixture(temp,native_currency='EUR',defer_forecast=True)
            with patch.dict(os.environ,verifier_fixture(temp)):
                with self.assertRaises(PriceError) as refused:
                    build_forecast(ROOT,**request)
            self.assertEqual(refused.exception.code,'source-binding')

    def test_future_profile_cannot_be_used_at_a_claimed_earlier_emission_cutoff(self):
        from price_records import build_forecast,PriceError
        with tempfile.TemporaryDirectory() as temp:
            request=annual_fixture(temp,defer_forecast=True)
            request['emitted_at']='2019-11-15T00:00:00Z'
            with patch.dict(os.environ,verifier_fixture(temp)):
                with self.assertRaises(PriceError) as refused:
                    build_forecast(ROOT,**request)
            self.assertEqual(refused.exception.code,'source-binding')

    def test_future_adopter_input_cannot_be_presented_as_a_preoutcome_forecast(self):
        from price_records import build_forecast, PriceError
        with tempfile.TemporaryDirectory() as temp:
            request=annual_fixture(temp,context_at='2020-02-01T00:00:00Z',defer_forecast=True)
            with patch.dict(os.environ,verifier_fixture(temp)):
                with self.assertRaises(PriceError) as refused:
                    build_forecast(ROOT,**request)
            self.assertEqual(refused.exception.code,'source-binding')


class EmpiricalScore(unittest.TestCase):
    def test_declared_full_cdf_has_exact_monetary_crps_not_mode_error(self):
        from price_records import score_empirical
        atoms = [{'value': '0', 'count': 1}, {'value': '10', 'count': 1}]
        self.assertEqual(score_empirical(atoms, '20'), Fraction(25, 2))
        self.assertEqual(score_empirical(atoms, '5'), Fraction(5, 2))
        self.assertEqual(score_empirical([{'value': '5', 'count': 2}], '5'), 0)


class NumericRefusals(unittest.TestCase):
    def test_exact_parser_and_loss_reject_ambiguous_or_excessive_numbers(self):
        from price_records import _parse,_yaml,canonical_json,score_empirical,PriceError
        self.assertEqual(json.loads(canonical_json(_yaml(b'since: 2026-10-18\n'))),{'since':'2026-10-18'})
        for raw in (b'{"x":NaN}',b'{"x":1e99999999}',b'{"x":'+b'1'*129+b'}',b'{"x":1,"x":2}'):
            with self.subTest(raw=raw[:30]),self.assertRaises(PriceError):
                _parse(raw)
        for atoms in ([{'value':'1','count':True}],[{'value':'1','count':0}],
                      [{'value':'1','count':1},{'value':'1','count':1}],
                      [{'value':'NaN','count':1}],[{'value':'-1','count':1}]):
            with self.subTest(atoms=atoms),self.assertRaises(PriceError):
                score_empirical(atoms,'0')


class GeneratorBudget(unittest.TestCase):
    def test_aggregate_report_reserves_all_case_work_before_any_engine_execution(self):
        from price_accuracy import build_price_report
        from price_records import PriceError
        with tempfile.TemporaryDirectory() as temp:
            request=annual_fixture(temp,lef=9,iterations=100000,defer_forecast=True)
            publisher=request['source_roots']/'ico'
            profile=json.loads((publisher/'profile.json').read_text())
            inventory=json.loads((publisher/'cases.json').read_text())
            original=inventory['cases'][0]
            inventory['cases']=[]
            for index in range(6):
                case=copy.deepcopy(original)
                case['case_id']='case-'+str(index)
                case['horizon']['starts_at']=str(2020+index)+'-01-01T00:00:00Z'
                case['horizon']['ends_at']=str(2021+index)+'-01-01T00:00:00Z'
                inventory['cases'].append(case)
            raw=json.dumps(inventory).encode()
            profile['population']['case_inventory']['path']='batch-cases.json'
            profile['population']['case_inventory']['git_blob']=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            declared=publish(publisher,{'batch-profile.json':profile,'batch-cases.json':inventory},
                             'profile/v1.0.1','2019-12-01T12:00:00Z')
            documents={}
            for case in inventory['cases']:
                documents[case['case_id']+'.json']={
                    'schema':'publisher-reliability/price-forecast-v1','profile':declared('batch-profile.json'),
                    'target':request['target'],'case_id':case['case_id'],
                    'subject':case['subject'],'perspective':case['perspective'],'horizon':case['horizon'],
                    'unit':profile['unit'],'emitted_at':request['emitted_at'],'generator':request['generator'],
                    'distribution':{'kind':'weighted-empirical/v1','total_count':100000,
                                    'atoms':[{'value':'90','count':100000}]}}
            forecasts=publish(publisher,documents,'forecast/v1.0.0','2019-12-03T00:00:00Z')
            manifest={'schema':'publisher-reliability/price-input-set-v1','cohorts':[{
                'schema':'publisher-reliability/price-inputs-v1','profile':declared('batch-profile.json'),
                'target':request['target'],'cases':[{'case_id':case['case_id'],
                    'forecast':forecasts(case['case_id']+'.json'),'resolution':None} for case in inventory['cases']]}]}
            real_run,launches=subprocess.run,[]
            def external_process(argv,*args,**kwargs):
                if any(str(item).endswith('price_generator.py') for item in argv):
                    launches.append(list(argv))
                    raise AssertionError('aggregate engine boundary stopped; no large simulation executed')
                return real_run(argv,*args,**kwargs)
            with patch.dict(os.environ,verifier_fixture(temp)),patch('subprocess.run',side_effect=external_process):
                with self.assertRaises(PriceError) as refused:
                    build_price_report(ROOT,manifest,'2027-01-01T00:00:00Z',request['source_roots'])
            self.assertEqual(refused.exception.code,'resource-limit')
            self.assertEqual(launches,[])

    def test_resource_refusal_precedes_any_billion_event_engine_execution(self):
        from price_records import build_forecast, PriceError
        with tempfile.TemporaryDirectory() as temp:
            env = verifier_fixture(temp)
            request = annual_fixture(temp, lef=1000000000, iterations=1, defer_forecast=True)
            real_run, engine_launches = subprocess.run, []
            def external_process(argv, *args, **kwargs):
                if any(str(item).endswith('price_generator.py') for item in argv):
                    engine_launches.append(list(argv))
                    raise AssertionError('boundary refused billion-event generator; no engine executed')
                return real_run(argv, *args, **kwargs)
            with patch.dict(os.environ, env), patch('subprocess.run', side_effect=external_process):
                with self.assertRaises(PriceError) as refused:
                    build_forecast(ROOT, **request)
            self.assertEqual(refused.exception.code, 'resource-limit')
            self.assertEqual(engine_launches, [])


if __name__ == '__main__':
    unittest.main()
