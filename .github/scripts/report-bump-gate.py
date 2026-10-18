#!/usr/bin/env python3
"""Compute only the report family's own bump; never classify catalogue or price quality."""
from pathlib import Path
import argparse
import copy
import json
import re
import subprocess
import sys

PREFIX = 'publisher-reliability/v'
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
ROOT = Path(__file__).resolve().parents[2]


class Refused(ValueError):
    pass


def git(root, *args, strip=True):
    call = subprocess.run(['git', '--no-replace-objects', '-C', str(root), *args],
                          capture_output=True, text=True, timeout=30)
    if call.returncode:
        raise Refused('cannot read complete report release history: ' + args[0])
    return call.stdout.strip() if strip else call.stdout


def version(tag):
    if not tag.startswith(PREFIX) or not SEMVER.fullmatch(tag[len(PREFIX):]):
        raise Refused('report releases require exactly publisher-reliability/vX.Y.Z')
    return tuple(int(part) for part in tag[len(PREFIX):].split('.'))


def read(root, path, old=None):
    return git(root, 'show', old + ':' + path, strip=False) if old else (root / path).read_text()


def report(root, release_version, old=None):
    path = f'publisher-reliability/v{release_version[0]}/feed.json'
    return json.loads(read(root, path, old))


def compute(root, old, new, old_object):
    if (old['payload_schema'] != new['payload_schema'] or
            read(root, old['payload_schema'], old_object) != read(root, new['payload_schema'])):
        return 'major'
    if new['payload_schema'] == 'publisher-reliability/price-payload.schema.json':
        def monetary_population(document):
            payload = copy.deepcopy(document['payload'])
            payload.pop('cutoff', None); payload.pop('tool', None)
            for cohort in payload['reports']:
                cohort.pop('cutoff', None); cohort.pop('tool', None)
            return payload
        changed = monetary_population(old) != monetary_population(new)
    else:
        population = ('inputs', 'counts', 'scores', 'unscoreable')
        changed = any(old['payload'][key] != new['payload'][key] for key in population)
    if changed:
        return 'minor'
    before, after = copy.deepcopy(old), copy.deepcopy(new)
    before.pop('version'); after.pop('version')
    return 'none' if before == after else 'patch'


def declared(root):
    for line in (root / 'publisher-reliability/bump.yaml').read_text().splitlines():
        key, _, value = line.split('#', 1)[0].partition(':')
        if key.strip() == 'bump':
            bump = value.strip().strip('"\'')
            if bump in ('none', 'patch', 'minor', 'major'):
                return bump
    raise Refused('publisher-reliability/bump.yaml must declare major, minor, patch or none')


def check(root, tag):
    wanted = version(tag)
    if git(root, 'rev-parse', '--is-shallow-repository') != 'false':
        raise Refused('shallow history cannot identify a report predecessor')
    local = set(git(root, 'tag', '--list', PREFIX + '*').splitlines())
    remote = set()
    remote_objects = {}
    for line in git(root, 'ls-remote', '--tags', 'origin', 'refs/tags/' + PREFIX + '*').splitlines():
        oid, name = line.split('\t', 1)
        if not name.endswith('^{}'):
            name = name.removeprefix('refs/tags/')
            remote.add(name)
            remote_objects[name] = oid
    for name in local | remote:
        version(name)
    if tag in local | remote:
        raise Refused('report tag already exists; immutable refs cannot be reused')
    if remote - local:
        raise Refused('missing local report tags; fetch complete release history before cutting')
    if local - remote:
        raise Refused('local report tags absent from origin cannot supply published predecessors')
    for name in remote:
        if git(root, 'rev-parse', 'refs/tags/' + name) != remote_objects[name]:
            raise Refused('local report tag object differs from origin: ' + name)
    current = report(root, wanted)
    version_file = ('price-version.json' if current['payload_schema'] == 'publisher-reliability/price-payload.schema.json' else 'version.json')
    declared_version = json.loads((root / 'publisher-reliability' / version_file).read_text())['version']
    if current['version'] != tag[len(PREFIX):] or declared_version != current['version']:
        raise Refused('tag, committed report and declared version do not agree')
    bump = declared(root)
    if not local:
        if wanted != (1, 0, 0) or bump != 'major':
            raise Refused('first report is explicit bootstrap1.0.0 with declared major, not a computed bump')
        return 'bootstrap1.0.0: no predecessor; initial major declaration is not a computed-major or price claim'
    previous = max(local, key=version)
    old_version = version(previous)
    old_object = git(root, 'rev-parse', '--verify', 'refs/tags/' + previous)
    if git(root, 'cat-file', '-t', old_object) != 'tag':
        raise Refused('report predecessor must be an annotated publication tag')
    if wanted <= old_version:
        raise Refused('new report tag must follow the newest published report')
    actual = compute(root, report(root, old_version, old_object), current, old_object)
    expected = {'patch': (old_version[0], old_version[1], old_version[2] + 1),
                'minor': (old_version[0], old_version[1] + 1, 0),
                'major': (old_version[0] + 1, 0, 0)}
    if bump != actual:
        raise Refused(f'declared {bump}, computed {actual} under the report rule')
    if actual == 'none':
        raise Refused('computed none: no report release is queued')
    if wanted != expected[actual]:
        raise Refused('tag is not the exact next ' + actual + ' increment of ' + previous)
    return f'{previous} -> {tag}: declared {bump} == computed {actual}; no price-quality claim'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('tag')
    args = parser.parse_args()
    try:
        print('PASS: ' + check(args.root.resolve(), args.tag))
        return 0
    except FileNotFoundError as error:
        if error.filename == 'git':
            print('SKIP: report release gate needs Git')
            return 3
        print('FAIL: report release input missing: ' + str(error))
    except (Refused, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print('FAIL: ' + str(error))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
