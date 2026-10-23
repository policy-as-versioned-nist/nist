"""Replay the actual empty served report without executing a source or engine."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'publisher-reliability'))
from price_accuracy import build_price_report, check_price_report
from price_records import PriceError


class ServedPriceReportClosure(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / 'publisher-reliability/v2/feed.json').read_text())['payload']

    def test_current_empty_served_report_replays_at_its_original_cutoff(self):
        self.assertEqual(self.payload['cutoff'], '2026-10-18T18:36:00Z')
        self.assertEqual(self.payload['inputs']['cohorts'], [])
        self.assertEqual(self.payload['reports'], [])
        self.assertEqual(self.payload['reason'],
                         'no declared monetary cohorts; no publisher-price accuracy measurement')
        with patch('subprocess.run', side_effect=AssertionError('no source or engine execution')):
            self.assertEqual(check_price_report(ROOT, self.payload), self.payload)

    def test_reconstructed_empty_report_still_rejects_a_changed_tool_blob(self):
        with patch('subprocess.run', side_effect=AssertionError('no source or engine execution')):
            payload = build_price_report(ROOT, self.payload['inputs'], self.payload['cutoff'])
            tampered = copy.deepcopy(payload)
            tampered['tool']['source_files'][1]['git_blob'] = '0' * 40
            with self.assertRaisesRegex(PriceError, 'complete authenticated reconstruction'):
                check_price_report(ROOT, tampered)


if __name__ == '__main__':
    unittest.main()
