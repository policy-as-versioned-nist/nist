"""Source-bound annual monetary forecast/resolution SDK; no admission or appetite flags."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re


class PriceError(ValueError):
    """Named refusal; never converted into an unmeasured or favourable result."""
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason
        super().__init__(f'{code}: {reason}')

    def as_record(self):
        return {'schema': 'publisher-reliability/error-v1', 'kind': 'instrument-refusal',
                'code': self.code, 'reason': self.reason}


def _fraction(value):
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > 8192:
        raise PriceError('resource-limit', 'exact fraction exceeds 8192 bits')
    return value


def _decimal(value, *, negative=False):
    if (not isinstance(value, str) or len(value) > 260 or
            not re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', value)):
        raise PriceError('invalid-money', 'money must be an exact canonical decimal string')
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise PriceError('invalid-money', 'invalid decimal') from error
    if (not number.is_finite() or len(number.as_tuple().digits) > 128 or
            abs(number.as_tuple().exponent) > 128):
        raise PriceError('resource-limit', 'decimal exceeds the versioned representability bound')
    if (number.is_signed() and number.is_zero()) or (number < 0 and not negative):
        raise PriceError('invalid-money', 'negative monetary loss or negative zero')
    return _fraction(Fraction(number))


def _sum(left, right):
    # Bounded operands imply at most16384-bit products; include the carry bit.
    if max(left.numerator.bit_length() + right.denominator.bit_length(),
           right.numerator.bit_length() + left.denominator.bit_length()) + 1 > 16384:
        raise PriceError('resource-limit', 'exact addition exceeds the intermediate budget')
    return _fraction(left + right)


def _multiply(left, right):
    if max(left.numerator.bit_length() + right.numerator.bit_length(),
           left.denominator.bit_length() + right.denominator.bit_length()) > 16384:
        raise PriceError('resource-limit', 'exact product exceeds the intermediate budget')
    return _fraction(left * right)


def score_empirical(atoms, observed):
    """Exact CRPS of the declared empirical CDF, in the observation's unit.

    Gneiting/Balabdaoui/Raftery2007 eq13: E|X-y| - E|X-X'|/2.
    Sorted prefix weights evaluate the second term without quadratic allocation.
    """
    if not isinstance(atoms, list) or not 1 <= len(atoms) <= 100000:
        raise PriceError('resource-limit', 'empirical atoms must have bounded nonempty population')
    y = _decimal(observed)
    parsed, total, previous = [], 0, None
    for atom in atoms:
        if not isinstance(atom, dict) or set(atom) != {'value', 'count'}:
            raise PriceError('invalid-record', 'empirical atom fields are closed')
        count = atom['count']
        if type(count) is not int or not 1 <= count <= 1000000:
            raise PriceError('invalid-record', 'atom multiplicity must be a positive bounded integer')
        x = _decimal(atom['value'])
        if previous is not None and x <= previous:
            raise PriceError('invalid-record', 'empirical atoms must be strictly increasing and unique')
        previous = x
        total += count
        if total > 1000000:
            raise PriceError('resource-limit', 'empirical total multiplicity exceeds one million')
        parsed.append((x, count))
    distance, half_pair_distance = Fraction(), Fraction()
    prefix_count, prefix_value = 0, Fraction()
    for x, count in parsed:
        distance = _sum(distance, _multiply(Fraction(count), abs(x - y)))
        before = _sum(_multiply(x, Fraction(prefix_count)), -prefix_value)
        half_pair_distance = _sum(half_pair_distance, _multiply(Fraction(count), before))
        prefix_count += count
        prefix_value = _sum(prefix_value, _multiply(x, Fraction(count)))
    return _sum(_multiply(distance, Fraction(1, total)),
                -_multiply(half_pair_distance, Fraction(1, total * total)))


# These helpers own authority. No public function accepts a verified/admitted/cache flag.
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collections import Counter

import jsonschema
from referencing.exceptions import Unresolvable
import yaml

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('_nist_binary_registration', HERE / 'report.py')
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)


def _bounded(value, depth=0):
    if depth > 32:
        raise PriceError('resource-limit', 'JSON/YAML nesting exceeds32')
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PriceError('invalid-record', 'object keys must be strings')
            _bounded(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _bounded(item, depth + 1)
    elif type(value) is int:
        if value.bit_length() > 426 or len(str(abs(value))) > 128:
            raise PriceError('resource-limit', 'numeric token exceeds128decimal digits')
    elif isinstance(value, (Decimal, float)):
        number = Decimal(str(value))
        if (not number.is_finite() or len(number.as_tuple().digits) > 128 or
                abs(number.as_tuple().exponent) > 128):
            raise PriceError('resource-limit', 'nonfinite or excessive numeric token')


def _parse(raw):
    if len(raw) > 33554432:
        raise PriceError('resource-limit', 'record exceeds32MiB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PriceError('invalid-record', 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def bad(value):
        raise PriceError('invalid-money', 'nonfinite JSON literal: ' + value)
    try:
        def numeric(token):
            mantissa, _, exponent = token.lower().partition('e')
            digits = mantissa.replace('.', '').lstrip('-').lstrip('0') or '0'
            if len(digits) > 128 or (exponent and (len(exponent.lstrip('+-').lstrip('0') or '0') > 3 or abs(int(exponent)) > 128)):
                raise PriceError('resource-limit', 'numeric token exceeds the decimal representation budget')
            return Decimal(token) if '.' in token or exponent else int(token)
        result = json.loads(raw, object_pairs_hook=unique, parse_float=numeric, parse_int=numeric, parse_constant=bad)
        _bounded(result)
        return result
    except (ValueError, InvalidOperation, RecursionError) as error:
        if isinstance(error, PriceError):
            raise
        raise PriceError('invalid-record', 'invalid bounded JSON') from error


def _plain(value):
    if isinstance(value, Decimal):
        converted = float(value)
        if not math.isfinite(converted) or Decimal(str(converted)) != value:
            raise PriceError('invalid-money', 'numeric value cannot be represented by the pinned FAIR engine')
        return converted
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def canonical_json(value):
    _bounded(value)
    try:
        return json.dumps(_plain(value), sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    except (ValueError, OverflowError) as error:
        raise PriceError('invalid-money', 'unrepresentable JSON value') from error


def _schema(root, kind, document):
    _bounded(document)
    definitions = json.loads((Path(root) / 'publisher-reliability/price-schemas.json').read_text())['$defs']
    if kind not in definitions:
        raise PriceError('unsupported-profile', 'unknown monetary record kind')
    errors = sorted(jsonschema.Draft7Validator({'$ref': '#/$defs/' + kind, '$defs': definitions}).iter_errors(document),
                    key=lambda error: str(error.path))
    if errors:
        raise PriceError('invalid-record', f'{kind}: {errors[0].message}')


def _stamp(value):
    try:
        return _legacy.stamp(value)
    except ValueError as error:
        raise PriceError('invalid-record', str(error)) from error


def _yaml(raw):
    class Unique(yaml.SafeLoader):
        pass
    Unique.yaml_implicit_resolvers = {key: [(tag, pattern) for tag, pattern in values
        if tag != 'tag:yaml.org,2002:timestamp'] for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if not isinstance(key, str) or key in result:
                raise PriceError('invalid-record', 'YAML keys must be unique strings')
            result[key] = loader.construct_object(value_node, deep=True)
        return result
    Unique.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    Unique.add_constructor('tag:yaml.org,2002:float', lambda loader, node: Decimal(loader.construct_scalar(node)))
    try:
        if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(raw)):
            raise PriceError('invalid-record', 'YAML aliases/anchors are not admitted for immutable context')
        result = yaml.load(raw, Loader=Unique)
        _bounded(result)
        return result
    except (yaml.YAMLError, InvalidOperation, ValueError, RecursionError) as error:
        if isinstance(error, PriceError):
            raise
        raise PriceError('invalid-record', 'invalid bounded unique YAML context') from error


class _Sources:
    def __init__(self, root, roots):
        self.root = Path(root)
        self.roots = Path(roots).resolve() if roots is not None else None
        self.trust = json.loads((self.root / 'publisher-reliability/price-trust.json').read_text())
        self.checked, self.served, self.bytes = {}, {}, 0
        if self.trust.get('issuer') != 'https://token.actions.githubusercontent.com':
            raise PriceError('source-authentication', 'trust policy must pin the Actions issuer')

    def raw(self, ref):
        _schema(self.root, 'source_ref', ref)
        party, tag, commit, path = (ref[key] for key in ('party', 'tag', 'commit', 'path'))
        if (not re.fullmatch(r'[a-z0-9][a-z0-9-]*', party) or
                not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', tag) or
                any(x in tag for x in ('..', '//', '@{')) or tag.endswith('.lock')):
            raise PriceError('source-binding', 'invalid canonical party or tag')
        try:
            _legacy.relative(path)
            if self.roots is None:
                raise _legacy.MissingInstrument('canonical publisher sources are absent')
            repo = (self.roots / party).resolve()
            if not (repo / '.git').is_dir():
                raise _legacy.MissingInstrument('a canonical full regular source clone is required: ' + party)
            git = lambda *args: _legacy.git(repo, *args).decode().strip()
            expected = f'https://github.com/policy-as-versioned-{party}/{party}'
            if git('config', '--get', 'remote.origin.url') not in (expected, expected + '.git'):
                raise PriceError('source-authentication', 'source origin is not canonical')
            if git('rev-parse', '--show-toplevel') != str(repo):
                raise PriceError('source-authentication', 'source is not its own Git root')
            if (git('rev-parse', '--is-shallow-repository') != 'false' or
                    (repo / '.git/objects/info/alternates').exists() or
                    list((repo / '.git/objects/pack').glob('*.promisor'))):
                raise _legacy.MissingInstrument('source needs full unshared history')
            common = git('rev-parse', '--path-format=absolute', '--git-common-dir')
            if common != str((repo / '.git').resolve()):
                raise PriceError('source-authentication', 'linked worktrees are not immutable canonical stores')
            oid = git('rev-parse', '--verify', 'refs/tags/' + tag)
            key = (party, tag, commit)
            if key not in self.checked:
                identity = (self.trust.get('publishers', {}).get(party) or {}).get('identity')
                if not identity:
                    raise PriceError('source-authentication', 'no pinned signer for ' + party)
                verified = _legacy.verify_input_tag(repo, party, tag, commit, identity, self.trust['issuer'])
                self.checked[key] = verified
            if self.checked[key] != oid:
                raise PriceError('source-authentication', 'captured tag changed during this operation')
            if party not in self.served:
                self.served[party] = git('rev-parse', 'refs/remotes/origin/main^{commit}')
            served = self.served[party]
            _legacy.git(repo, 'merge-base', '--is-ancestor', commit, served)
            actual = git('rev-parse', '--verify', commit + ':' + path)
            if actual != ref['git_blob'] or git('cat-file', '-t', actual) != 'blob':
                raise PriceError('source-binding', 'source does not match its exact tree blob')
            size = int(git('cat-file', '-s', actual))
            self.bytes += size
            if size > 33554432 or self.bytes > 268435456:
                raise PriceError('resource-limit', 'source record/operation byte limit exceeded')
            raw = _legacy.git(repo, 'cat-file', 'blob', actual)
            return {'party': party, 'tag': tag, 'commit': commit, 'path': path,
                    'git_blob': actual, 'repo': repo, 'served_main': served, 'raw': raw}
        except _legacy.MissingInstrument as error:
            raise PriceError('missing-instrument', str(error)) from error
        except _legacy.Rejected as error:
            raise PriceError('source-authentication', str(error)) from error

    def read(self, ref):
        item = self.raw(ref)
        item['document'] = _yaml(item['raw']) if ref['path'].endswith(('.yaml', '.yml')) else _parse(item['raw'])
        return item

    def at(self, enclosing, file):
        _schema(self.root, 'tree_file_ref', file)
        return self.read({**{key: enclosing[key] for key in ('party', 'tag', 'commit')}, **file})

    def path_ref(self, enclosing, path):
        try:
            _legacy.relative(path)
            oid = _legacy.git(enclosing['repo'], 'rev-parse', enclosing['commit'] + ':' + path).decode().strip()
        except _legacy.Rejected as error:
            raise PriceError('source-binding', 'signed discovered path is absent') from error
        return {**{key: enclosing[key] for key in ('party', 'tag', 'commit')}, 'path': path, 'git_blob': oid}


def _arrival(item):
    try:
        return _legacy.registration(item)
    except (_legacy.Rejected, ValueError, OverflowError, OSError) as error:
        raise PriceError('registration-history', str(error)) from error


def _verify_engine(root):
    upstream = json.loads((Path(root) / 'publisher-reliability/PRICE-UPSTREAM.json').read_text())
    expected = {'fair/fair.py': '1e73bd8f6603ff1798268206cd1bcc6f0842975b',
                'fair/severity.py': '5bbd7c698498dc7930ed5c1b7ed36abc663cd919'}
    if (upstream.get('repository') != 'https://github.com/policy-as-versioned-platform/platform' or
            upstream.get('tag') != 'v5.4.0' or
            upstream.get('commit') != '5d45baa5923191dfd0e9cfb2cfaeae6906a41fce' or
            upstream.get('tag_object') != '3d7670f7e9fd5414caf62dca55a3056369abe6bc' or
            upstream.get('tree') != 'ce8c4c53159cfbf273ceff5236113dc2f0cf0036' or
            {item.get('path') for item in upstream.get('files', [])} != set(expected) or
            len(upstream.get('files', [])) != len(expected)):
        raise PriceError('source-binding', 'FAIR provenance differs from the fixed released source')
    for record in upstream['files']:
        path = record['path']
        if record.get('vendored_path') != 'publisher-reliability/vendor/' + path:
            raise PriceError('source-binding', 'FAIR dependency path differs')
        raw = (Path(root) / record['vendored_path']).read_bytes()
        oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if (oid != expected[path] or record.get('git_blob') != expected[path] or
                hashlib.sha256(raw).hexdigest() != record.get('sha256')):
            raise PriceError('source-binding', 'FAIR bytes do not equal the exact released tree blob')
    return upstream


def _content_time(item):
    """Available source content under the same explicit Git-clock limitation as registration."""
    try:
        arrival = _legacy.git(item['repo'], 'log', '-1', '--format=%H', item['commit'], '--', item['path']).decode().strip()
        if not arrival:
            raise PriceError('source-binding', 'referenced content has no source history')
        oid, unused = _legacy.blob(item['repo'], arrival, item['path'])
        if oid != item['git_blob']:
            raise PriceError('source-binding', 'source content differs at its last recorded write')
        epoch = int(_legacy.git(item['repo'], 'show', '-s', '--format=%ct', arrival))
        parents = _legacy.git(item['repo'], 'show', '-s', '--format=%P', arrival).decode().split()
        if parents and epoch < int(_legacy.git(item['repo'], 'show', '-s', '--format=%ct', parents[0])):
            raise PriceError('source-binding', 'input content clock predates its parent')
        return dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    except (_legacy.Rejected, ValueError, OverflowError, OSError) as error:
        if isinstance(error, PriceError):
            raise
        raise PriceError('source-binding', 'input content history/time is invalid') from error


def _engine_ref(root):
    upstream = _verify_engine(root)
    return {'party': 'platform', 'tag': upstream['tag'], 'commit': upstream['commit'],
            'path': 'fair/fair.py', 'git_blob': '1e73bd8f6603ff1798268206cd1bcc6f0842975b'}


def _horizon(value):
    start, end = (_stamp(value[key]) for key in ('starts_at', 'ends_at'))
    a, b = (dt.datetime.strptime(x, '%Y-%m-%dT%H:%M:%SZ') for x in (start, end))
    if b <= a or b.year != a.year + 1 or b.strftime('%m-%dT%H:%M:%S') != a.strftime('%m-%dT%H:%M:%S'):
        raise PriceError('invalid-record', 'profile requires one exact UTC Gregorian anniversary year')
    return start, end


def _generator_plan(generator):
    n = generator['iterations']
    scenario = generator['scenario']['warn']
    lef = scenario['lef']
    sources = scenario['lm'] if isinstance(scenario['lm'][0], list) else [scenario['lm']]
    for triple in [lef, *sources]:
        if any(isinstance(x, bool) or not isinstance(x, (int, float, Decimal)) for x in triple):
            raise PriceError('invalid-money', 'FAIR triples must be numeric')
        if not 0 <= triple[0] <= triple[1] <= triple[2]:
            raise PriceError('invalid-money', 'FAIR triples must be ordered and nonnegative')
        for number in triple:
            if not math.isfinite(float(number)):
                raise PriceError('invalid-money', 'unrepresentable FAIR triple')
    f = math.ceil(Decimal(str(lef[2])))
    event_draws = n * f * len(sources)
    temporary = 6 * n + f + 3 * len(sources)
    if f > 10000 or event_draws > 1000000 or temporary > 1000000:
        raise PriceError('resource-limit', 'pinned FAIR pre-execution event/allocation budget exceeded')
    return (event_draws, n, event_draws + 2 * n)


def _process(*args, **kwargs):
    try:
        return subprocess.run(*args, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PriceError('missing-instrument', 'pinned converter/engine process unavailable or exceeded its bounded runtime') from error


class _Session:
    def __init__(self, root, roots):
        self.root = Path(root).resolve()
        for name in ('price_records.py', 'price_generator.py', 'report.py', 'scoring.py',
                     'price-schemas.json', 'price-trust.json'):
            if (self.root / 'publisher-reliability' / name).read_bytes() != (HERE / name).read_bytes():
                raise PriceError('source-binding', 'executed SDK closure differs from selected source: ' + name)
        _verify_engine(self.root)
        self.sources = _Sources(self.root, roots)
        self.work = [0, 0, 0]

    def profile(self, profile_ref, target_ref):
        profile = self.sources.read(profile_ref)
        doc = profile['document']
        _schema(self.root, 'profile', doc)
        target = self.sources.read(target_ref)
        envelope = target['document']
        if (profile_ref['party'] != target_ref['party'] or
                doc['target_feed'] != {'publisher': target_ref['party'], 'name': envelope.get('name')}):
            raise PriceError('source-binding', 'profile and exact target publisher/feed disagree')
        _legacy_schema = json.loads((self.root / 'publisher-reliability/envelope.schema.json').read_text())
        try:
            jsonschema.Draft7Validator(_legacy_schema).validate(envelope)
        except (jsonschema.ValidationError, jsonschema.SchemaError) as error:
            raise PriceError('source-binding', 'target is not a valid feed envelope') from error
        if (envelope['published_by'] != target_ref['party'] or envelope['kind'] != 'feed' or
                target_ref['tag'] not in ('v' + envelope['version'], envelope['name'] + '/v' + envelope['version'])):
            raise PriceError('source-binding', 'target feed envelope differs from exact tag/publisher')
        if (target_ref['party'], envelope['name']) not in {('ico', 'penalty-schema'), ('feeds', 'threat-register')}:
            raise PriceError('unsupported-profile', 'target has no supported served annual-model converter')
        discovery = self.sources.read(self.sources.path_ref(target, 'party.yaml'))['document']
        publications = [p for p in discovery.get('publishes', [])
                        if p.get('kind') == 'feed' and p.get('name') == envelope['name']]
        if (discovery.get('party') != target_ref['party'] or len(publications) != 1 or
                publications[0].get('payload_schema') != envelope['payload_schema'] or
                target_ref['path'] != publications[0]['path'] + '/v' + envelope['version'].split('.')[0] + '/feed.json'):
            raise PriceError('source-binding', 'target publication discovery/path/schema mismatch')
        payload_schema = self.sources.read(self.sources.path_ref(target, envelope['payload_schema']))['document']
        def safe(value):
            if isinstance(value, dict):
                if '$ref' in value and not str(value['$ref']).startswith('#'):
                    raise PriceError('source-binding', 'external target schema references refuse')
                for item in value.values():
                    safe(item)
            elif isinstance(value, list):
                for item in value:
                    safe(item)
        safe(payload_schema)
        try:
            jsonschema.Draft7Validator(payload_schema).validate(envelope['payload'])
        except (jsonschema.ValidationError, jsonschema.SchemaError, Unresolvable) as error:
            raise PriceError('source-binding', 'target payload violates its signed schema') from error
        if doc['resolver_rule']['party'] == target_ref['party']:
            raise PriceError('source-binding', 'profile must declare a different independent resolution publisher')
        if doc['generator']['engine'] != _engine_ref(self.root):
            raise PriceError('unsupported-profile', 'profile does not select the fixed released FAIR source')
        inventory = self.sources.at(profile, doc['population']['case_inventory'])
        _schema(self.root, 'case_inventory', inventory['document'])
        if inventory['document']['profile_id'] != doc['id']:
            raise PriceError('population-binding', 'case inventory profile identity differs')
        cases = inventory['document']['cases']
        if len(cases) > 10000:
            raise PriceError('resource-limit', 'too many registered cases')
        ids, periods = set(), {}
        profile_arrival, inventory_arrival = _arrival(profile), _arrival(inventory)
        for case in cases:
            start, end = _horizon(case['horizon'])
            if case['case_id'] in ids:
                raise PriceError('population-binding', 'duplicate precommitted case identity')
            ids.add(case['case_id'])
            if max(profile_arrival, inventory_arrival) >= start:
                raise PriceError('registration-history', 'profile/case inventory was not committed before its horizon')
            key = (case['subject'], case['perspective'])
            for old_start, old_end in periods.setdefault(key, []):
                if start < old_end and old_start < end:
                    raise PriceError('population-binding', 'overlapping case subject/horizon population')
            periods[key].append((start, end))
        return profile, target, inventory

    def prepare(self, profile_ref, target_ref, case_id, emitted_at, generator):
        profile, target, inventory = self.profile(profile_ref, target_ref)
        _schema(self.root, 'generator', generator)
        _stamp(emitted_at)
        cases = [c for c in inventory['document']['cases'] if c['case_id'] == case_id]
        if len(cases) != 1:
            raise PriceError('population-binding', 'forecast is not in the complete declared case inventory')
        case = cases[0]
        if (generator['engine'] != _engine_ref(self.root) or
                generator['context_ref'] != case['context_ref'] or
                generator['invocation'] != ['forecast-base', 'payload.json', 'context.json']):
            raise PriceError('generator-mismatch', 'generator engine/context/normalized invocation differs')
        served_path = {('ico', 'penalty-schema'): 'schema/to_fair_scenario.py',
                       ('feeds', 'threat-register'): 'threat-register/to_fair_scenario.py'}.get(
                           (target_ref['party'], target['document']['name']))
        if served_path is None or generator['converter']['path'] != served_path:
            raise PriceError('unsupported-profile', 'forecast requires the actual supported served converter path')
        if any(generator['converter'][key] != target_ref[key] for key in ('party', 'tag', 'commit')):
            raise PriceError('generator-mismatch', 'converter is outside the exact target signed tree')
        context = self.sources.read(generator['context_ref'])
        document = context['document']
        if (context['path'] != 'party.yaml' or not isinstance(document, dict) or
                document.get('party') != context['party'] or
                case['perspective'] != context['party'] or case['subject'] != context['party'] or
                document.get('reporting_currency') != profile['document']['unit']['currency']):
            raise PriceError('source-binding', 'case/perspective/unit is not the actual signed adopter context')
        name = target['document']['name']
        edges = [edge for edge in document.get('inherits', []) if isinstance(edge, dict) and
                 edge.get('party') == target_ref['party'] and edge.get('kind') == 'feed' and
                 edge.get('name') == name]
        if len(edges) != 1 or not isinstance(edges[0].get('version'), str):
            raise PriceError('source-binding', 'context must select one exact target-party/feed edge')
        selected_version = edges[0]['version']
        version = target['document']['version']
        if selected_version not in (version, 'v' + version, version.split('.')[0], 'v' + version.split('.')[0]):
            raise PriceError('source-binding', 'target envelope is outside the signed selected feed version')
        payload = dict(target['document']['payload'])
        native_currency = (payload.get('regimes', {}).get('uk-gdpr', {}).get('currency')
                           if name == 'penalty-schema' else payload.get('currency'))
        if native_currency != profile['document']['unit']['currency']:
            raise PriceError('source-binding', 'native converter currency differs from the declared monetary unit; FX is unsupported')
        # Same bridge as platform load_feed_payload, not a new per-regime formula.
        payload.setdefault('schema_version' if name == 'penalty-schema' else 'feed_version', selected_version)
        # Check the declared support BEFORE executing any engine. Converter reproduction then
        # verifies that the declaration is the actual publisher scenario, not a cheap stand-in.
        plan = _generator_plan(generator)
        converter = self.sources.raw(generator['converter'])
        emitted = dt.datetime.strptime(emitted_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        if any(_content_time(item) > emitted for item in (context, target, converter, profile, inventory)):
            raise PriceError('source-binding', 'forecast uses source content unavailable at its emitted information cutoff')
        try:
            published = dt.datetime.fromisoformat(target['document']['published_at'].replace('Z', '+00:00'))
            if published.tzinfo is None or published > emitted:
                raise PriceError('source-binding', 'target publication is unavailable at the forecast cutoff')
        except ValueError as error:
            if isinstance(error, PriceError):
                raise
            raise PriceError('source-binding', 'invalid target publication timestamp') from error
        with tempfile.TemporaryDirectory(prefix='price-converter-') as temporary:
            stage = Path(temporary)
            (stage / 'converter.py').write_bytes(converter['raw'])
            (stage / 'payload.json').write_text(canonical_json(payload))
            wrapper = {'schema': 'publisher-reliability/generator-context-v1',
                       'source': generator['context_ref'], 'document': document}
            (stage / 'context.json').write_text(canonical_json(wrapper))
            call = _process([sys.executable, '-I', 'converter.py', *generator['invocation']],
                                  cwd=stage, capture_output=True, timeout=60,
                                  env={'PATH': os.environ.get('PATH', ''), 'LC_ALL': 'C'})
            if call.returncode:
                raise PriceError('generator-mismatch', 'signed publisher forecast-base refused its actual context')
            actual = _plain(_parse(call.stdout))
        if actual != _plain(generator['scenario']):
            raise PriceError('generator-mismatch', 'registered scenario differs from actual signed publisher converter')
        forecast = {'schema': 'publisher-reliability/price-forecast-v1', 'target': target_ref,
                    'profile': profile_ref, 'case_id': case_id, 'subject': case['subject'],
                    'perspective': case['perspective'], 'horizon': case['horizon'],
                    'unit': profile['document']['unit'], 'emitted_at': emitted_at,
                    'generator': _plain(generator)}
        return {'forecast': forecast, 'profile': profile, 'target': target,
                'inventory': inventory, 'plan': plan}

    def reserve(self, preparations):
        sums = [self.work[i] + sum(p['plan'][i] for p in preparations) for i in range(3)]
        if sums[0] > 5000000 or sums[1] > 1000000 or sums[2] > 5000000:
            raise PriceError('resource-limit', 'whole report/cohort/replay generator budget exceeded')
        self.work = sums

    def generate(self, prepared):
        generator = prepared['forecast']['generator']
        _verify_engine(self.root)
        program = self.root / 'publisher-reliability/price_generator.py'
        call = _process([sys.executable, '-I', str(program)],
                              input=canonical_json(generator).encode(), capture_output=True, timeout=60,
                              env={'PATH': os.environ.get('PATH', ''), 'LC_ALL': 'C'})
        if call.returncode:
            raise PriceError('invalid-money', 'fixed FAIR generator refused or produced an unrepresentable amount')
        values = _parse(call.stdout)
        if not isinstance(values, list) or len(values) != generator['iterations']:
            raise PriceError('generator-mismatch', 'fixed FAIR output count differs from requested iterations')
        counts = Counter()
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
                raise PriceError('invalid-money', 'fixed FAIR produced a nonnumeric observation')
            number = format(Decimal(str(value)), 'f')
            # Canonical exact decimal wire strings carry no redundant fractional zeroes.
            if '.' in number:
                number = number.rstrip('0').rstrip('.')
            _decimal(number)
            counts[number] += 1
        atoms = [{'value': value, 'count': count} for value, count in
                 sorted(counts.items(), key=lambda pair: Decimal(pair[0]))]
        distribution = {'kind': 'weighted-empirical/v1', 'total_count': len(values), 'atoms': atoms}
        _schema(self.root, 'distribution', distribution)
        result = {**prepared['forecast'], 'distribution': distribution}
        _schema(self.root, 'forecast', result)
        return result

    def resolution(self, forecast_ref, profile_ref, source_ref, resolved_at, published_at, evidence_uri, forecast):
        if forecast_ref['party'] != forecast['target']['party']:
            raise PriceError('resolution-binding', 'forecast signer differs from its exact target publisher')
        if forecast['profile'] != profile_ref:
            raise PriceError('resolution-binding', 'resolution profile differs from the exact registered forecast')
        profile, target, inventory = self.profile(profile_ref, forecast['target'])
        rule = profile['document']['resolver_rule']
        source = self.sources.read(source_ref)
        _arrival(source)
        document = source['document']
        if source_ref['party'] != rule['party'] or source_ref['party'] == forecast_ref['party']:
            raise PriceError('resolution-binding', 'resolution requires the declared different independent publisher')
        if not isinstance(document, dict) or document.get('schema') != rule['source_schema']:
            raise PriceError('resolution-binding', 'resolution source schema differs from the declared rule')
        def pointer(path):
            if not path.startswith('/'):
                raise PriceError('resolution-binding', 'resolution pointer must be a JSON pointer')
            value = document
            try:
                for part in path[1:].split('/'):
                    key = part.replace('~1', '/').replace('~0', '~')
                    value = value[int(key)] if isinstance(value, list) else value[key]
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise PriceError('resolution-binding', 'resolution pointer is missing') from error
            return value
        observed = pointer(rule['amount_pointer'])
        _decimal(observed)
        if pointer(rule['finality_pointer']) is not True or pointer(rule['completeness_pointer']) is not True:
            raise PriceError('resolution-binding', 'annual outcome is not explicitly final and complete')
        for key in ('case_id', 'subject', 'perspective', 'horizon', 'unit'):
            if document.get(key) != forecast[key]:
                raise PriceError('resolution-binding', 'independent source substitutes case/horizon/unit: ' + key)
        if (not isinstance(evidence_uri, str) or not evidence_uri.startswith(rule['evidence_uri_prefix']) or
                not evidence_uri.startswith('https://')):
            raise PriceError('resolution-binding', 'resolution evidence URI differs from signed rule')
        resolved_at, published_at = _stamp(resolved_at), _stamp(published_at)
        if resolved_at < forecast['horizon']['ends_at'] or published_at < resolved_at:
            raise PriceError('resolution-binding', 'resolution precedes annual horizon/finality')
        result = {'schema': 'publisher-reliability/price-resolution-v1', 'forecast': forecast_ref,
                  'profile': profile_ref, **{key: forecast[key] for key in
                  ('case_id', 'subject', 'perspective', 'horizon', 'unit')},
                  'observed': observed, 'resolved_at': resolved_at, 'published_at': published_at,
                  'source': source_ref, 'evidence_uri': evidence_uri}
        _schema(self.root, 'resolution', result)
        return result


def build_forecast(root, *, profile, target, case_id, emitted_at, generator, source_roots):
    """Build from authenticated actual publisher context/model, never supplied atoms."""
    session = _Session(root, source_roots)
    prepared = session.prepare(profile, target, case_id, emitted_at, generator)
    session.reserve([prepared])
    return session.generate(prepared)


def build_resolution(root, *, forecast, profile, source, resolved_at, published_at, evidence_uri, source_roots):
    """Read a declared independent complete annual outcome; no caller observed amount."""
    session = _Session(root, source_roots)
    item = session.sources.read(forecast)
    doc = item['document']
    _schema(root, 'forecast', doc)
    _arrival(item)
    prepared = session.prepare(doc['profile'], doc['target'], doc['case_id'], doc['emitted_at'], doc['generator'])
    session.reserve([prepared])
    reproduced = session.generate(prepared)
    if reproduced != _plain(doc):
        raise PriceError('generator-mismatch', 'signed forecast differs from actual generation')
    return session.resolution(forecast, profile, source, resolved_at, published_at, evidence_uri, reproduced)


def check_record(root, kind, record, source_roots):
    """Check/reproduce a closed record, with all source authority checked privately."""
    _schema(root, kind, record)
    if kind == 'forecast':
        result = build_forecast(root, **{key: record[key] for key in
                                ('profile', 'target', 'case_id', 'emitted_at', 'generator')},
                                source_roots=source_roots)
    elif kind == 'resolution':
        result = build_resolution(root, **{key: record[key] for key in
                                  ('forecast', 'profile', 'source', 'resolved_at', 'published_at', 'evidence_uri')},
                                  source_roots=source_roots)
    else:
        raise PriceError('unsupported-profile', 'only monetary forecast/resolution records are admitted')
    if result != _plain(record):
        raise PriceError('source-binding', 'record differs from complete authenticated reconstruction')
    return result
