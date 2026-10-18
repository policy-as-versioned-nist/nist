"""Authenticated annual monetary empirical-CDF diagnostics; no adopter appetite or price."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import jsonschema
from fractions import Fraction
from price_records import (PriceError, _Session, _arrival, _schema, _stamp, _plain,
                           _sum, _multiply, _yaml, _engine_ref, _verify_engine, score_empirical)

HERE = Path(__file__).resolve().parent


def _load(path):
    return json.loads(Path(path).read_text())


def _tool(root):
    base = root / 'publisher-reliability'
    _verify_engine(root)
    if (base / 'price_accuracy.py').read_bytes() != Path(__file__).read_bytes():
        raise PriceError('source-binding', 'executing price checker differs from selected source')
    names = ['price_accuracy.py', 'price_records.py', 'price_report.py', 'price_generator.py',
             'price-schemas.json', 'price-payload.schema.json', 'PRICE-UPSTREAM.json', 'price-trust.json',
             'price-version.json', 'requirements.txt', 'report.py', 'scoring.py', 'envelope.schema.json']
    for name in names:
        if (base / name).read_bytes() != (HERE / name).read_bytes():
            raise PriceError('source-binding', 'executing monetary source closure differs: ' + name)
    sources = []
    for name in names:
        raw = (base / name).read_bytes()
        oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        sources.append({'path': 'publisher-reliability/' + name, 'git_blob': oid})
    raw = (root / 'party.yaml').read_bytes()
    sources.append({'path': 'party.yaml', 'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})
    return {'source_files': sources, 'generator_engine': _engine_ref(root)}


def _ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def build_price_report(root, manifest, cutoff, source_roots=None):
    root = Path(root).resolve()
    cutoff = _stamp(cutoff)
    _schema(root, 'input_set', manifest)
    if len(manifest['cohorts']) > 10000:
        raise PriceError('resource-limit', 'whole report cohort budget exceeded')
    session = _Session(root, source_roots)
    scorer = _yaml((root / 'party.yaml').read_bytes())
    if (scorer.get('party') != 'nist' or 'publisher' not in scorer.get('roles', []) or
            not isinstance(scorer.get('publishes'), list)):
        raise PriceError('source-authentication', 'scorer must be the independent NIST publisher')
    preparations, cohorts, identities, forecast_ids = [], [], set(), set()
    total_cases = 0
    for cohort in manifest['cohorts']:
        profile, target, inventory = session.profile(cohort['profile'], cohort['target'])
        if (target['party'] == 'nist' or any(pub.get('kind') == 'feed' and
                pub.get('name') == target['document']['name'] for pub in scorer['publishes'])):
            raise PriceError('source-authentication', 'scorer publishes a target feed and is not independent')
        identity = tuple(cohort['profile'][key] for key in ('party', 'commit', 'path', 'git_blob'))
        if identity in identities:
            raise PriceError('population-binding', 'duplicate declared cohort/profile')
        identities.add(identity)
        total_cases += len(inventory['document']['cases'])
        if total_cases > 10000:
            raise PriceError('resource-limit', 'whole report registered-case budget exceeded')
        declared = {case['case_id']: case for case in inventory['document']['cases']}
        supplied = {case['case_id']: case for case in cohort['cases']}
        if len(supplied) != len(cohort['cases']) or set(supplied) != set(declared):
            raise PriceError('population-binding', 'manifest must retain every precommitted case exactly once')
        rows = []
        for case_id in sorted(declared):
            case = supplied[case_id]
            if case['forecast'] is None:
                if case['resolution'] is not None:
                    raise PriceError('population-binding', 'resolution cannot substitute for an absent forecast')
                rows.append({'case': case, 'prepared': None})
                continue
            reference = case['forecast']
            key = tuple(reference[k] for k in ('party', 'commit', 'path', 'git_blob'))
            if key in forecast_ids:
                raise PriceError('population-binding', 'reused forecast would stuff the population')
            forecast_ids.add(key)
            item = session.sources.read(reference)
            forecast = item['document']
            _schema(root, 'forecast', forecast)
            if (reference['party'] != target['party'] or forecast['target'] != cohort['target'] or
                    forecast['profile'] != cohort['profile'] or forecast['case_id'] != case_id):
                raise PriceError('source-binding', 'forecast substitutes exact target/profile/case or publisher')
            prepared = session.prepare(forecast['profile'], forecast['target'], case_id,
                                       forecast['emitted_at'], forecast['generator'])
            # Every actual generator execution is reserved together across the whole operation.
            preparations.append(prepared)
            rows.append({'case': case, 'prepared': prepared, 'item': item})
        cohorts.append((cohort, profile, target, inventory, rows))
    if len(preparations) > 10000 or sum(p['forecast']['generator']['iterations'] for p in preparations) > 1000000:
        raise PriceError('resource-limit', 'whole report forecast/output population exceeds the budget')
    session.reserve(preparations)
    reports = []
    for cohort, profile, target, inventory, pending in cohorts:
        rows, losses = [], []
        for pending_row in pending:
            case, prepared = pending_row['case'], pending_row['prepared']
            row = {'case_id': case['case_id'], 'forecast': case['forecast'], 'resolution': case['resolution'],
                   'state': 'unscoreable', 'reason': None, 'loss': None}
            if prepared is None:
                row['reason'] = 'no registered forecast is supplied for this precommitted case'
                rows.append(row)
                continue
            forecast = session.generate(prepared)
            item = pending_row['item']
            if forecast != _plain(item['document']):
                raise PriceError('generator-mismatch', 'signed empirical atoms differ from actual pinned generation')
            arrived = _arrival(item)
            opens = forecast['horizon']['starts_at']
            reason = None
            if max(arrived, forecast['emitted_at']) >= opens:
                reason = 'forecast was not blindly registered before its annual horizon'
            elif max(arrived, forecast['emitted_at']) > cutoff:
                reason = 'forecast was not available at the explicit report cutoff'
            if case['resolution'] is None:
                reason = reason or 'no independent complete annual resolution is supplied'
            else:
                resolution_item = session.sources.read(case['resolution'])
                resolution = resolution_item['document']
                _schema(root, 'resolution', resolution)
                if case['resolution']['party'] != profile['document']['resolver_rule']['party']:
                    raise PriceError('resolution-binding', 'resolution signer is not the declared independent publisher')
                expected = session.resolution(case['forecast'], cohort['profile'], resolution['source'],
                    resolution['resolved_at'], resolution['published_at'], resolution['evidence_uri'], forecast)
                if expected != _plain(resolution):
                    raise PriceError('resolution-binding', 'resolution differs from its actual independent source')
                resolution_arrived = _arrival(resolution_item)
                source = session.sources.read(resolution['source'])
                source_arrived = _arrival(source)
                if (resolution_arrived < resolution['published_at'] or source_arrived > resolution_arrived or
                        resolution_arrived <= arrived):
                    raise PriceError('registration-history', 'resolution/source publication order is inconsistent')
                if max(resolution_arrived, source_arrived, resolution['published_at'], resolution['resolved_at']) > cutoff:
                    reason = reason or 'independent annual resolution was not available at the explicit cutoff'
                if reason is None:
                    loss = score_empirical(forecast['distribution']['atoms'], resolution['observed'])
                    losses.append(loss)
                    row.update(state='eligible', loss=_ratio(loss))
            row['reason'] = reason
            rows.append(row)
        total = Fraction()
        for loss in losses:
            total = _sum(total, loss)
        mean = _multiply(total, Fraction(1, len(losses))) if losses else None
        inventory_ref = {**{k: profile[k] for k in ('party', 'tag', 'commit')},
                         **profile['document']['population']['case_inventory']}
        report = {'schema': 'publisher-reliability/price-report-v1', 'scorer': 'nist', 'cutoff': cutoff,
                  'profile': cohort['profile'], 'target': cohort['target'], 'unit': profile['document']['unit'],
                  'criterion': 'money-empirical-crps/v1', 'score_direction': 'higher-is-better',
                  'cohort': inventory_ref, 'status': 'measured' if losses else 'unmeasured',
                  'counts': {'registered_cases': len(rows), 'eligible': len(losses), 'unscoreable': len(rows) - len(losses)},
                  'loss': _ratio(mean) if mean is not None else None,
                  'score': _ratio(-mean) if mean is not None else None, 'cases': rows,
                  'tool': _tool(root), 'inputs': cohort,
                  'claim_scope': {'measure': 'declared-annual-monetary-empirical-CDF-error',
                                  'population': 'exact-registered-cohort-only',
                                  'calibration_guarantee': False, 'binary_report_relabelled': False}}
        _schema(root, 'report', report)
        reports.append(report)
    result = {'schema': 'publisher-reliability/price-report-set-v1', 'scorer': 'nist', 'cutoff': cutoff,
              'tool': _tool(root), 'inputs': manifest, 'reports': reports,
              'reason': None if reports else 'no declared monetary cohorts; no publisher-price accuracy measurement'}
    _schema(root, 'report_set', result)
    return _plain(result)


def check_price_report(root, report, source_roots=None):
    root = Path(root).resolve()
    _schema(root, 'report_set', report)
    expected = build_price_report(root, report['inputs'], report['cutoff'], source_roots)
    if report != expected:
        raise PriceError('source-binding', 'monetary report differs from complete authenticated reconstruction')
    return expected
