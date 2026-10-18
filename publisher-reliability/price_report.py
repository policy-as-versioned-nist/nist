#!/usr/bin/env python3
"""Build/check annual monetary report sets or source-bound producer/resolver records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--inputs', '--manifest', dest='inputs', type=Path)
    build.add_argument('--as-of', '--cutoff', dest='cutoff', required=True)
    check = commands.add_parser('check')
    check.add_argument('--report', type=Path, required=True)
    for name in ('build-forecast', 'build-resolution'):
        command = commands.add_parser(name)
        command.add_argument('--request', type=Path, required=True)
    record = commands.add_parser('check-record')
    record.add_argument('--kind', choices=['forecast', 'resolution'], required=True)
    record.add_argument('--record', type=Path, required=True)
    for command in commands.choices.values():
        command.add_argument('--root', type=Path, default=HERE.parent)
        command.add_argument('--sources', type=Path)
        command.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        from price_records import PriceError, _parse, _plain, canonical_json, build_forecast, build_resolution, check_record
        from price_accuracy import build_price_report, check_price_report
    except ModuleNotFoundError as error:
        print(f'SKIP: missing-instrument: Python dependency {error.name}', file=sys.stderr)
        return 3
    try:
        root = args.root.resolve()
        if args.command == 'build':
            manifest = _parse((args.inputs or root / 'publisher-reliability/price-inputs.json').read_bytes())
            payload = build_price_report(root, manifest, args.cutoff, args.sources)
            version = json.loads((root / 'publisher-reliability/price-version.json').read_text())['version']
            result = {'kind': 'feed', 'name': 'publisher-reliability', 'version': version,
                      'published_by': 'nist', 'published_at': args.cutoff,
                      'payload_schema': 'publisher-reliability/price-payload.schema.json', 'payload': payload}
        elif args.command == 'check':
            result = _plain(_parse(args.report.read_bytes()))
            if not isinstance(result, dict) or not isinstance(result.get('payload'), dict):
                raise PriceError('invalid-record', 'monetary envelope and payload must be objects')
            version = json.loads((root / 'publisher-reliability/price-version.json').read_text())['version']
            identity = {key: result.get(key) for key in
                        ('kind', 'name', 'version', 'published_by', 'payload_schema')}
            if identity != {'kind': 'feed', 'name': 'publisher-reliability', 'version': version,
                            'published_by': 'nist', 'payload_schema': 'publisher-reliability/price-payload.schema.json'}:
                raise PriceError('source-binding', 'monetary envelope identity/schema/version differs from selected source')
            if set(result) != {'kind','name','version','published_by','published_at','payload_schema','payload'}:
                raise PriceError('invalid-record', 'monetary envelope has unknown or missing fields')
            if result['published_at'] != result['payload'].get('cutoff'):
                raise PriceError('source-binding', 'envelope timestamp differs from report cutoff')
            check_price_report(root, result['payload'], args.sources)
        elif args.command.startswith('build-'):
            request = _parse(args.request.read_bytes())
            required = ({'profile','target','case_id','emitted_at','generator'} if args.command == 'build-forecast'
                        else {'forecast','profile','source','resolved_at','published_at','evidence_uri'})
            if not isinstance(request, dict) or set(request) != required:
                raise PriceError('invalid-record', 'producer/resolver request has unknown or missing fields')
            function = build_forecast if args.command == 'build-forecast' else build_resolution
            result = function(root, **request, source_roots=args.sources)
        else:
            result = check_record(root, args.kind, _parse(args.record.read_bytes()), args.sources)
        data = canonical_json(result)
        if args.output:
            args.output.write_text(data)
        sys.stdout.write(data)
        return 0
    except PriceError as error:
        code = 3 if error.code == 'missing-instrument' else 1
        print(('SKIP: ' if code == 3 else 'FAIL: ') + str(error), file=sys.stderr)
        return code
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'FAIL: invalid-record: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
