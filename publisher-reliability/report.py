#!/usr/bin/env python3
"""Independent binary forecast report; no publisher-price quality score or price effect."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
CLAIM = {'binary_forecast_scores_only': True, 'publisher_price_accuracy': False, 'price_eligible': False}


class Rejected(ValueError):
    pass


class MissingInstrument(RuntimeError):
    pass


def parse_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise Rejected('duplicate JSON key: ' + key)
            value[key] = item
        return value
    def nonfinite(value):
        raise Rejected('nonfinite JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def load(path):
    try:
        return parse_json(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise Rejected(f'cannot read JSON {path}: {error}') from error


def stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise Rejected('as-of and record times must be fixed UTC YYYY-MM-DDTHH:MM:SSZ')
    try:
        dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError as error:
        raise Rejected(f'invalid UTC timestamp: {value}') from error
    return value


def validate(doc, schema, label):
    schema_document(doc, load(schema), label)


def tool(root):
    base = root / 'publisher-reliability'
    names = ['report.py', 'scoring.py', 'inputs.schema.json', 'payload.schema.json', 'trust.json', 'version.json', 'UPSTREAM.json', 'envelope.schema.json', 'forecast.schema.json', 'resolution.schema.json']
    if (base / 'report.py').read_bytes() != Path(__file__).read_bytes():
        raise Rejected('root tool source differs from the executing trusted report module')
    if (base / 'scoring.py').read_bytes() != Path(scoring.__file__).read_bytes():
        raise Rejected('root scoring source differs from the executing scoring module')
    upstream = load(base / 'UPSTREAM.json')
    if hashlib.sha256((base / 'scoring.py').read_bytes()).hexdigest() != upstream['sha256']:
        raise Rejected('binary scoring source differs from immutable UPSTREAM.json')
    return {'version': load(base / 'version.json')['tool_version'],
            'sources': {**{name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in names},
                        'party.yaml': hashlib.sha256((root / 'party.yaml').read_bytes()).hexdigest()},
            'upstream': upstream,
            'registration_basis': 'served first-parent Git committer dates; unchanged content and parent-clock checks, not independent wall-clock observation'}


def git(repo, *args, input=None):
    if shutil.which('git') is None:
        raise MissingInstrument('Git is required to authenticate pinned report inputs')
    environment = dict(os.environ, GIT_NO_REPLACE_OBJECTS='1')
    result = subprocess.run(['git', '-C', str(repo), *args], env=environment,
                            capture_output=True, timeout=60, input=input)
    if result.returncode:
        raise Rejected(f'cannot read required Git object or source metadata: {args[0]}')
    return result.stdout


def relative(path):
    if (not isinstance(path, str) or not path or path.startswith('/') or '\\' in path or
            any(part in ('', '.', '..', '.git') for part in path.split('/')) or
            any(ord(char) < 32 for char in path)):
        raise Rejected('input paths must be safe repository-relative file paths')
    return path


def blob(repo, commit, path):
    path = relative(path)
    oid = git(repo, 'rev-parse', '--verify', f'{commit}:{path}').decode().strip()
    if git(repo, 'cat-file', '-t', oid).strip() != b'blob':
        raise Rejected('a referenced input path must be a Git blob')
    return oid, git(repo, 'cat-file', 'blob', oid)


def schema_document(doc, schema, label):
    # Do not let a signed data file cause an implicit external-schema fetch.
    def local_refs(value):
        if isinstance(value, dict):
            if '$ref' in value and not str(value['$ref']).startswith('#'):
                raise Rejected(f'{label}: external schema references are not admitted offline')
            for item in value.values():
                local_refs(item)
        elif isinstance(value, list):
            for item in value:
                local_refs(item)
    local_refs(schema)
    try:
        jsonschema.Draft7Validator.check_schema(schema)
        errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(doc), key=lambda e: str(e.path))
    except jsonschema.SchemaError as error:
        raise Rejected(f'{label}: invalid payload schema') from error
    if errors:
        raise Rejected(f'{label}: {errors[0].message}')


def verify_input_tag(repo, party, tag, commit, identity, issuer):
    """Verify one frozen object in a private store; a mutable tag name is never the selector."""
    ref = 'refs/tags/' + tag
    oid = git(repo, 'rev-parse', '--verify', ref).decode().strip()
    if git(repo, 'cat-file', '-t', oid).strip() != b'tag':
        raise Rejected('input publication must be an annotated signed tag')
    header = git(repo, 'cat-file', 'tag', oid).split(b'\n\n', 1)[0].splitlines()
    required = [f'object {commit}'.encode(), b'type commit', f'tag {tag}'.encode()]
    if header[:3] != required:
        raise Rejected('signed input tag name/source does not match its exact pin')
    if shutil.which('gitsign') is None:
        raise MissingInstrument('gitsign is required to verify nonempty report inputs')
    objects = git(repo, 'pack-objects', '--stdout', '--revs', input=(oid + '\n').encode())
    with tempfile.TemporaryDirectory(prefix='publisher-input-') as temporary:
        frozen = Path(temporary) / party
        frozen.mkdir()
        git(frozen, 'init', '-q', '-b', 'main')
        git(frozen, 'unpack-objects', '-q', input=objects)
        git(frozen, 'update-ref', ref, oid)
        git(frozen, 'update-ref', 'refs/heads/main', commit)
        result = subprocess.run(['gitsign', 'verify-tag', tag,
                                 '--certificate-identity-regexp=^' + re.escape(identity) + '$',
                                 '--certificate-oidc-issuer=' + issuer], cwd=frozen,
                                env=dict(os.environ, GIT_NO_REPLACE_OBJECTS='1', GITSIGN_REKOR_MODE='offline'),
                                capture_output=True, timeout=60)
        if (git(frozen, 'rev-parse', ref).decode().strip() != oid or
                git(repo, 'rev-parse', ref).decode().strip() != oid):
            raise Rejected('input tag changed during pinned signature verification')
        output = result.stdout + result.stderr
        facts = (b'Good signature from', b'Validated Git signature: true',
                 b'Validated Rekor entry: true', b'Validated Certificate claims: true')
        if result.returncode or not all(fact in output for fact in facts):
            raise Rejected(f'{party} input signature verification refused its pinned identity/issuer')
    return oid


class AuthenticatedSources:
    """Read-only Git data and explicit verifier trust, shared by targets and pair records."""
    def __init__(self, root, sources):
        self.sources = sources
        self.trust = load(root / 'publisher-reliability/trust.json')
        self.checked = {}
        self.served = {}
        if (not isinstance(self.trust, dict) or self.trust.get('issuer') != 'https://token.actions.githubusercontent.com'
                or not isinstance(self.trust.get('publishers'), dict)
                or any(not isinstance(policy, dict) for policy in self.trust['publishers'].values())):
            raise Rejected('the scorer trust policy must pin the Actions issuer')

    def read(self, record):
        party, tag, commit = record['party'], record['tag'], record['commit']
        if (not re.fullmatch(r'[a-z0-9][a-z0-9-]*', party) or
                not re.fullmatch(r'[0-9a-f]{40}', commit) or
                not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', tag) or
                any(text in tag for text in ('..', '//', '@{')) or tag.endswith('.lock')):
            raise Rejected('invalid publisher, immutable source or tag name')
        if self.sources is None:
            raise MissingInstrument('canonical publisher source checkouts are required for nonempty inputs')
        repo = (self.sources / party).resolve()
        if not repo.is_dir():
            raise MissingInstrument(f'canonical source checkout for {party} is absent')
        if git(repo, 'rev-parse', '--show-toplevel').decode().strip() != str(repo):
            raise Rejected('source is not its own canonical Git checkout')
        origin = git(repo, 'config', '--get', 'remote.origin.url').decode().strip()
        expected = f'https://github.com/policy-as-versioned-{party}/{party}'
        if origin not in (expected, expected + '.git'):
            raise Rejected(f'{party} source origin is not canonical')
        if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
            raise MissingInstrument(f'{party} source history is shallow; registration cannot be read')
        key = (party, tag, commit)
        if key not in self.checked:
            identity = (self.trust.get('publishers', {}).get(party) or {}).get('identity')
            if not isinstance(identity, str) or not identity:
                raise Rejected(f'no pinned signature identity for {party}')
            verify_input_tag(repo, party, tag, commit, identity, self.trust['issuer'])
            if party not in self.served:
                self.served[party] = git(repo, 'rev-parse', 'refs/remotes/origin/main^{commit}').decode().strip()
            git(repo, 'merge-base', '--is-ancestor', commit, self.served[party])
            self.checked[key] = repo
        oid, raw = blob(repo, commit, record['path'])
        try:
            doc = parse_json(raw)
        except ValueError as error:
            raise Rejected('signed input record is not JSON') from error
        return {'party': party, 'tag': tag, 'commit': commit, 'path': record['path'],
                'git_blob': oid, 'repo': repo, 'served_main': self.served[party], 'document': doc}


def authenticate_targets(root, party, inputs, sources):
    reader = AuthenticatedSources(root, sources)
    targets, identities = {}, set()
    for target in inputs['targets']:
        if target['id'] in targets:
            raise Rejected('duplicate target identity')
        if target['publisher'] == party['party']:
            raise Rejected('the independent scorer cannot score a feed it publishes')
        if any(pub.get('kind') == 'feed' and pub.get('name') == target['name']
               for pub in party.get('publishes', [])):
            raise Rejected('the scorer publishes a declared target feed and is not independent')
        item = reader.read(dict(party=target['publisher'], tag=target['tag'],
                                commit=target['commit'], path=target['path']))
        doc = item['document']
        schema_document(doc, load(root / 'publisher-reliability/envelope.schema.json'), 'target envelope')
        if (doc['kind'] != 'feed' or doc['name'] != target['name'] or
                doc['published_by'] != target['publisher'] or
                target['tag'] not in (f'v{doc["version"]}', f'{target["name"]}/v{doc["version"]}')):
            raise Rejected('target envelope identity/version does not match its signed pin')
        try:
            declaration = yaml.safe_load(blob(item['repo'], item['commit'], 'party.yaml')[1])
        except yaml.YAMLError as error:
            raise Rejected('target discovery is invalid YAML') from error
        if (not isinstance(declaration, dict) or not isinstance(declaration.get('roles'), list)
                or 'publisher' not in declaration['roles']
                or not isinstance(declaration.get('publishes'), list)
                or any(not isinstance(p, dict) for p in declaration['publishes'])):
            raise Rejected('target discovery must be a publisher with readable publication records')
        publications = [p for p in declaration.get('publishes', []) if p.get('kind') == 'feed' and p.get('name') == target['name']]
        if declaration.get('party') != target['publisher'] or len(publications) != 1:
            raise Rejected('target has no unique matching publisher discovery record')
        publication = publications[0]
        if (not isinstance(publication.get('path'), str) or not publication['path'] or
                not isinstance(publication.get('payload_schema'), str) or not publication['payload_schema']):
            raise Rejected('target discovery must name its publication path and payload schema')
        relative(publication['path'])
        relative(publication['payload_schema'])
        expected_path = f'{publication["path"]}/v{doc["version"].split(".")[0]}/feed.json'
        if target['path'] != expected_path or publication.get('payload_schema') != doc['payload_schema']:
            raise Rejected('target bytes do not occupy the signed discovered feed path/schema')
        schema_raw = blob(item['repo'], item['commit'], doc['payload_schema'])[1]
        try:
            target_schema = parse_json(schema_raw)
        except ValueError as error:
            raise Rejected('target payload schema is not JSON') from error
        schema_document(doc['payload'], target_schema, 'target payload')
        identity = (doc['published_by'], doc['name'], item['commit'], item['path'])
        if identity in identities:
            raise Rejected('duplicate authenticated target under different manifest identities')
        identities.add(identity)
        targets[target['id']] = (target, item)
    return reader, targets


def record_document(item, root, name):
    document = item['document']
    schema_document(document, load(root / f'publisher-reliability/{name}.schema.json'), name)
    return document


def registration(item):
    """Exact served first-parent arrival, with no same-path rewrite accepted as immutable."""
    repo, path, served = item['repo'], item['path'], item['served_main']
    changes = git(repo, 'log', '--first-parent', '--reverse', '--format=%H',
                  served, '--', path).decode().splitlines()
    if len(changes) != 1:
        raise Rejected('registered record is missing, rewritten, deleted or re-added on served history')
    arrival = changes[0]
    current_oid, unused = blob(repo, served, path)
    if current_oid != item['git_blob']:
        raise Rejected('current served record differs from its immutable signed pin')
    git(repo, 'merge-base', '--is-ancestor', item['commit'], served)
    # The path arrival can precede its enclosing release commit. Its own unchanged blob is the
    # registration; a later release cannot create a false early registration for changed bytes.
    at_arrival, unused = blob(repo, arrival, path)
    if at_arrival != item['git_blob']:
        raise Rejected('served registration does not carry the pinned record bytes')
    epoch = int(git(repo, 'show', '-s', '--format=%ct', arrival))
    parents = git(repo, 'show', '-s', '--format=%P', arrival).decode().split()
    if parents:
        parent_epoch = int(git(repo, 'show', '-s', '--format=%ct', parents[0]))
        if epoch < parent_epoch:
            raise Rejected('registration commit predates its own parent')
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def score_pairs(root, inputs, as_of, reader, targets):
    scores, unscoreable, ids, forecasts, questions = [], [], set(), set(), set()
    for pair in sorted(inputs['pairs'], key=lambda p: p['id']):
        if pair['id'] in ids:
            raise Rejected('duplicate pair identity')
        ids.add(pair['id'])
        if pair['target'] not in targets:
            raise Rejected('pair names an undeclared target')
        target, target_record = targets[pair['target']]
        if pair['forecast']['party'] != target['publisher']:
            raise Rejected('forecast publisher differs from the exact target publisher')
        forecast = reader.read(pair['forecast'])
        forecast_key = tuple(forecast[k] for k in ('party', 'tag', 'commit', 'path'))
        if forecast_key in forecasts:
            raise Rejected('duplicate forecast input would double count its score')
        forecasts.add(forecast_key)
        fd = record_document(forecast, root, 'forecast')
        expected_target = {k: v for k, v in target.items() if k != 'id'}
        if fd['target'] != expected_target:
            raise Rejected('forecast target is not the exact declared signed feed pin')
        question = fd['question']
        question_key = (target['publisher'], target['name'], question['id'])
        if question_key in questions:
            raise Rejected('multiple forecasts for one target/question would stuff the population')
        questions.add(question_key)
        emitted = stamp(fd['emitted_at'])
        opens = stamp(question['resolution_window_opens_at'])
        registered = registration(forecast)
        probability = fd['probability']
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 < probability < 1:
            raise Rejected('binary probability must be strictly between zero and one')
        reason = None
        if emitted >= opens or registered >= opens:
            reason = 'forecast was not blindly registered before its resolution window opened'
        elif emitted > as_of or registered > as_of:
            reason = 'forecast was not served by the explicit report cutoff'
        resolution_ref = pair['resolution']
        if resolution_ref is None:
            reason = reason or 'no independent resolution is supplied'
        else:
            if resolution_ref['party'] == forecast['party']:
                raise Rejected('resolution must be independently sourced from a different publisher')
            resolution = reader.read(resolution_ref)
            rd = record_document(resolution, root, 'resolution')
            expected_forecast = {k: forecast[k] for k in ('party', 'tag', 'commit', 'path', 'git_blob')}
            if rd['forecast'] != expected_forecast or rd['question'] != question:
                raise Rejected('resolution substitutes a different forecast, target or co-registered question')
            resolved = stamp(rd['resolved_at'])
            arrived = registration(resolution)
            if resolved < opens or arrived < resolved or arrived <= registered:
                raise Rejected('resolution was published before its event or forecast registration')
            if resolved > as_of or arrived > as_of:
                reason = reason or 'independent resolution is not available at the explicit report cutoff'
        if reason:
            unscoreable.append({'id': pair['id'], 'reason': reason})
            continue
        losses = scoring.score(probability, rd['observed'])
        scores.append({'id': pair['id'], 'target': pair['target'], 'probability': float(probability),
                       'observed': rd['observed'], **losses,
                       'target_reference': {
                           'publisher': target_record['document']['published_by'],
                           'name': target_record['document']['name'],
                           **{k: target_record[k] for k in ('tag', 'commit', 'path', 'git_blob')}},
                       'forecast': {k: forecast[k] for k in ('party', 'tag', 'commit', 'path', 'git_blob')},
                       'resolution': {k: resolution[k] for k in ('party', 'tag', 'commit', 'path', 'git_blob')},
                       'question': question, 'registered_at': registered, 'resolved_at': resolved,
                       'resolution_registered_at': arrived, 'resolution_source': rd['source']})
    return scores, unscoreable


def build(root, inputs, as_of, sources):
    as_of = stamp(as_of)
    validate(inputs, root / 'publisher-reliability/inputs.schema.json', 'input manifest')
    try:
        party = yaml.safe_load((root / 'party.yaml').read_text())
    except yaml.YAMLError as error:
        raise Rejected(f'invalid scorer discovery YAML: {error}') from error
    if (not isinstance(party, dict) or party.get('party') != 'nist'
            or not isinstance(party.get('roles'), list) or 'publisher' not in party['roles']
            or not isinstance(party.get('publishes'), list)
            or any(not isinstance(pub, dict) for pub in party['publishes'])):
        raise Rejected('scorer must be the independent NIST publisher')
    reader, targets = authenticate_targets(root, party, inputs, sources)
    scores, unscoreable = score_pairs(root, inputs, as_of, reader, targets)
    count = len(scores)
    losses = {'lower_is_better': True, **{name: scoring.quantise(sum(row[name] for row in scores) / count) if count else None for name in scoring.RULES}}
    payload = {'schema': 'publisher-reliability/report-v1', 'scorer': 'nist', 'as_of': as_of,
               'status': 'measured' if count else 'unmeasured', 'claim_scope': CLAIM, 'tool': tool(root), 'inputs': inputs,
               'counts': {'submitted': len(inputs['pairs']), 'eligible': count, 'unscoreable': len(unscoreable)}, 'scores': scores,
               'losses': losses, 'diagram': scoring.reliability_diagram(scores, bins=10), 'unscoreable': unscoreable,
               'reason': None if count else 'no eligible independently resolved registered forecasts; no publisher-price quality measurement'}
    validate(payload, root / 'publisher-reliability/payload.schema.json', 'report payload')
    return {'kind': 'feed', 'name': 'publisher-reliability', 'version': load(root / 'publisher-reliability/version.json')['version'],
            'published_by': 'nist', 'published_at': as_of, 'payload_schema': 'publisher-reliability/payload.schema.json', 'payload': payload}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('build')
    command.add_argument('--root', type=Path, default=HERE.parent)
    command.add_argument('--as-of', required=True)
    command.add_argument('--inputs', type=Path)
    command.add_argument('--sources', type=Path)
    command.add_argument('--output', type=Path)
    command = sub.add_parser('check')
    command.add_argument('--root', type=Path, default=HERE.parent)
    command.add_argument('--report', type=Path, required=True)
    command.add_argument('--sources', type=Path)
    args = parser.parse_args()
    try:
        global yaml, jsonschema, scoring
        try:
            import yaml
            import jsonschema
            import scoring
        except ModuleNotFoundError as error:
            raise MissingInstrument(f'Python module {error.name} is required for publisher reliability reports') from error
        root = args.root.resolve()
        if args.command == 'build':
            result = build(root, load(args.inputs or root / 'publisher-reliability/inputs.json'), args.as_of, args.sources)
        else:
            report = load(args.report)
            validate(report, root / 'publisher-reliability/envelope.schema.json', 'feed envelope')
            validate(report['payload'], root / 'publisher-reliability/payload.schema.json', 'report payload')
            result = build(root, report['payload']['inputs'], report['payload']['as_of'], args.sources)
            if report != result:
                raise Rejected('report differs from deterministic reconstruction of its authenticated inputs and tool source')
        data = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
        if getattr(args, 'output', None):
            args.output.write_text(data)
        sys.stdout.write(data)
        return 0
    except MissingInstrument as error:
        print(f'SKIP: {error}', file=sys.stderr)
        return 3
    except (Rejected, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
