"""Nonempty release/native seams; local transport and signature fixtures only."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import shutil
import yaml
import unittest
from unittest.mock import patch
from test_price_accuracy import ROOT,annual_fixture,new_source,publish
from test_publisher_reliability import verifier_fixture,fixture_git
sys.path.insert(0,str(ROOT/'publisher-reliability'))


def envelope(payload):
    declared = json.loads((ROOT/'publisher-reliability/price-version.json').read_text())
    return {'kind':'feed','name':'publisher-reliability','version':declared['version'],
            'published_by':'nist','published_at':payload['cutoff'],
            'payload_schema':'publisher-reliability/price-payload.schema.json','payload':payload}


class PriceDelivery(unittest.TestCase):
    def test_empty_collection_preparation_performs_no_clone_or_admission(self):
        from price_sources import prepare_sources
        from price_accuracy import build_price_report
        with tempfile.TemporaryDirectory() as temporary:
            report=Path(temporary)/'explicit-empty-fixture.json'
            report.write_text(json.dumps(envelope(build_price_report(ROOT,
                {'schema':'publisher-reliability/price-input-set-v1','cohorts':[]},'2026-10-18T17:00:00Z'))))
            destination=Path(temporary)/'absent-source-root'
            with patch('subprocess.run',side_effect=AssertionError('empty collection must not invoke transport')):
                receipt=prepare_sources(ROOT,report,destination)
            self.assertEqual(receipt,{'source_roots':None,'parties':[],'admission':False})
            self.assertFalse(destination.exists())

    def test_actual_native_wrapper_requires_and_forwards_nonempty_source_roots(self):
        from price_accuracy import build_price_report
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,verifier_fixture(temp)):
            forecast,resolution,manifest,sources=annual_fixture(temp)
            report=Path(temp)/'synthetic-report.json'
            report.write_text(json.dumps(envelope(build_price_report(ROOT,manifest,'2021-02-01T00:00:00Z',sources))))
            command=['bash',str(ROOT/'scripts/verify-publisher-price-accuracy.sh'),'--check-only','--report',str(report)]
            env=dict(os.environ,PYTHON=sys.executable)
            refused=subprocess.run(command+['--sources',str(Path(temp)/'missing')],env=env,capture_output=True,text=True)
            self.assertEqual(refused.returncode,3,refused.stdout+refused.stderr)
            accepted=subprocess.run(command+['--sources',str(sources)],env=env,capture_output=True,text=True)
            self.assertEqual(accepted.returncode,0,accepted.stdout+accepted.stderr)
            self.assertIn('fully reconstructed',accepted.stdout)

    def test_release_cli_provisions_full_canonical_clones_then_real_checker_admits(self):
        from price_accuracy import build_price_report,check_price_report
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,verifier_fixture(temp)):
            forecast,resolution,manifest,sources=annual_fixture(temp)
            payload=build_price_report(ROOT,manifest,'2021-02-01T00:00:00Z',sources)
            report=Path(temp)/'synthetic-report.json';report.write_text(json.dumps(envelope(payload)))
            parties=sorted(json.loads((ROOT/'publisher-reliability/price-trust.json').read_text())['publishers'])
            transport=dict(os.environ,GIT_CONFIG_COUNT=str(len(parties)))
            for index,party in enumerate(parties):
                if not (sources/party).exists():
                    repo=new_source(temp,party)
                    publish(repo,{'party.yaml':'party: '+party+'\n'},'fixture/v1.0.0','2019-01-01T00:00:00Z')
                transport['GIT_CONFIG_KEY_'+str(index)]='url.'+(sources/party).as_uri()+'.insteadOf'
                transport['GIT_CONFIG_VALUE_'+str(index)]=f'https://github.com/policy-as-versioned-{party}/{party}.git'
            destination=Path(temp)/'prepared'
            call=subprocess.run([sys.executable,str(ROOT/'publisher-reliability/price_sources.py'),
                '--root',str(ROOT),'--report',str(report),'--destination',str(destination)],
                env=transport,capture_output=True,text=True)
            self.assertEqual(call.returncode,0,call.stdout+call.stderr)
            receipt=json.loads(call.stdout)
            self.assertEqual(receipt['parties'],parties);self.assertFalse(receipt['admission'])
            for party in parties:
                repo=destination/party
                self.assertTrue((repo/'.git').is_dir())
                self.assertEqual(fixture_git(repo,'rev-parse','--is-shallow-repository'),'false')
                self.assertFalse((repo/'.git/objects/info/alternates').exists())
                self.assertEqual(fixture_git(repo,'config','--get','remote.origin.url'),
                    f'https://github.com/policy-as-versioned-{party}/{party}.git')
                self.assertEqual(fixture_git(repo,'show-ref','--tags'),fixture_git(sources/party,'show-ref','--tags'))
            self.assertEqual(check_price_report(ROOT,payload,destination),payload)
            # Execute the actual authenticated-source release step. Only package
            # transport and the already verified outer tag are explicit fixtures;
            # source cloning, CLI reconstruction and all record checks are real.
            release_root=Path(temp)/'release-source'
            shutil.copytree(ROOT,release_root,ignore=shutil.ignore_patterns('.git','__pycache__'))
            (release_root/'publisher-reliability/v2/feed.json').write_text(report.read_text())
            fixture_git(release_root,'init','-q','-b','main')
            for key,value in [('user.name','synthetic release source'),('user.email','fixture@example.invalid'),
                              ('commit.gpgsign','false'),('tag.gpgSign','false'),('core.hooksPath',os.devnull)]:
                fixture_git(release_root,'config',key,value)
            fixture_git(release_root,'add','.')
            fixture_git(release_root,'commit','-qm','unsigned synthetic source-release fixture')
            declared=json.loads((release_root/'publisher-reliability/price-version.json').read_text())
            tag='publisher-reliability/v'+declared['version']
            fixture_git(release_root,'tag','-a',tag,'-m','unsigned synthetic outer verification fixture')
            binary=Path(temp)/'release-bin';binary.mkdir()
            python=binary/'python3'
            python.write_text('#!'+sys.executable+'\nimport os,sys\n'
                'if sys.argv[1:4]==["-m","pip","install"]:\n'
                ' print("synthetic package transport: pinned dependencies already installed");sys.exit(0)\n'
                'os.execv(sys.executable,[sys.executable,*sys.argv[1:]])\n')
            python.chmod(0o755)
            temporary=Path(temp)/'workflow-temporary';temporary.mkdir()
            workflow=yaml.load((ROOT/'.github/workflows/release.yml').read_text(),Loader=yaml.BaseLoader)
            step=next(s for s in workflow['jobs']['release']['steps']
                if s.get('name')=='verify report from the exact authenticated source')
            hosted_env=dict(transport,TAG=tag,VERIFIED_TAG_OBJECT=fixture_git(release_root,'rev-parse','refs/tags/'+tag),
                PATH=str(binary)+os.pathsep+transport['PATH'],TMPDIR=str(temporary))
            hosted=subprocess.run(['/bin/bash','-euo','pipefail','-c',step['run']],
                cwd=release_root,env=hosted_env,capture_output=True,text=True)
            self.assertEqual(hosted.returncode,0,hosted.stdout+hosted.stderr)
            self.assertIn('authenticated report recomputes',hosted.stdout)



if __name__=='__main__':unittest.main()
