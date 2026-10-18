#!/usr/bin/env python3
"""Provision public full-history sources for a nonempty monetary report, never admit it."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PARTIES = frozenset(('feeds','ico','insurer','nist','platform','driftwood','tuppence','ludlow'))


def prepare_sources(root, report, destination):
    """Clone only the pinned trust registry's canonical public origins; empty means no transport."""
    from price_records import PriceError,_parse,_schema
    root=Path(root).resolve()
    document=_parse(Path(report).read_bytes())
    if not isinstance(document,dict) or not isinstance(document.get('payload'),dict):
        raise PriceError('invalid-record','source preparation requires a monetary report envelope')
    payload=document['payload']
    _schema(root,'report_set',payload)
    if not payload['inputs']['cohorts']:
        return {'source_roots':None,'parties':[],'admission':False}
    trust=json.loads((root/'publisher-reliability/price-trust.json').read_text())
    if (not isinstance(trust,dict) or not isinstance(trust.get('publishers'),dict) or
            trust.get('issuer')!='https://token.actions.githubusercontent.com' or set(trust.get('publishers',{}))!=PARTIES):
        raise PriceError('source-binding','source acquisition requires the closed publisher trust registry')
    for party,policy in trust['publishers'].items():
        expected=f'https://github.com/policy-as-versioned-{party}/{party}/.github/workflows/cut-release.yml@refs/heads/main'
        if not isinstance(policy,dict) or policy.get('identity')!=expected:
            raise PriceError('source-binding','publisher trust identity differs from its canonical Actions origin')
    destination=Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise PriceError('source-binding','source preparation needs a new or empty private directory')
    destination.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_NO_REPLACE_OBJECTS='1')
    for party in sorted(PARTIES):
        origin=f'https://github.com/policy-as-versioned-{party}/{party}.git'
        repo=destination/party
        try:
            call=subprocess.run(['git','-c','credential.helper=','-c','core.hooksPath='+os.devnull,
                'clone','--no-local','--no-hardlinks','--',origin,str(repo)],env=env,
                capture_output=True,timeout=180)
            if call.returncode:
                raise PriceError('missing-instrument','canonical public source clone unavailable: '+party)
            def git(*args):
                result=subprocess.run(['git','--no-replace-objects','-C',str(repo),*args],
                    env=env,capture_output=True,timeout=30)
                if result.returncode:
                    raise PriceError('missing-instrument','incomplete canonical clone: '+party)
                return result.stdout.decode().strip()
            if (not (repo/'.git').is_dir() or git('rev-parse','--is-shallow-repository')!='false' or
                    git('config','--get','remote.origin.url')!=origin or
                    git('rev-parse','--path-format=absolute','--git-common-dir')!=str((repo/'.git').resolve()) or
                    (repo/'.git/objects/info/alternates').exists() or
                    list((repo/'.git/objects/pack').glob('*.promisor'))):
                raise PriceError('source-binding','source acquisition did not produce full independent canonical history')
            git('rev-parse','--verify','refs/remotes/origin/main^{commit}')
        except (OSError,subprocess.TimeoutExpired) as error:
            raise PriceError('missing-instrument','bounded public source transport unavailable: '+party) from error
    return {'source_roots':str(destination),'parties':sorted(PARTIES),'admission':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    try:
        from price_records import PriceError
    except ModuleNotFoundError as error:
        print('SKIP: missing-instrument: Python dependency '+error.name,file=sys.stderr);return 3
    try:
        print(json.dumps(prepare_sources(args.root,args.report,args.destination),sort_keys=True))
        return 0
    except PriceError as error:
        code=3 if error.code=='missing-instrument' else 1
        print(('SKIP: ' if code==3 else 'FAIL: ')+str(error),file=sys.stderr);return code
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('FAIL: invalid-record: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
