import csv
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def test_comparison_threshold(self):
        result = self.run_cli('sample.jsonl', '--minimum-requests', '5')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--baseline', result.stderr)
        self.assertEqual(result.stdout, '')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, 'cli.py', *args], cwd=ROOT, capture_output=True, text=True)

    def test_json_and_csv_filter_the_same_rows(self):
        json_result = self.run_cli('sample.jsonl', '--route', '/tours/bookings')
        self.assertEqual(json_result.returncode, 0)
        self.assertEqual(json.loads(json_result.stdout)['total_requests'], 2)
        csv_result = self.run_cli('sample.jsonl', '--route', '/tours/bookings', '--format', 'csv')
        self.assertEqual(csv_result.returncode, 0)
        rows = list(csv.DictReader(io.StringIO(csv_result.stdout)))
        self.assertEqual(rows[0]['errors_5xx'], '1')
        self.assertEqual(rows[0]['error_rate_pct'], '50.00')

    def test_missing_file_is_a_file_error(self):
        result = self.run_cli('missing.jsonl')
        self.assertEqual(result.returncode, 1)

    def test_slo_gate_returns_distinct_failure_exit(self):
        failed = self.run_cli('sample.jsonl', '--slo-p95-ms', '500', '--slo-5xx-pct', '1')
        self.assertEqual(failed.returncode, 3)
        self.assertFalse(json.loads(failed.stdout)['slo']['passed'])
        self.assertEqual(self.run_cli('sample.jsonl', '--slo-p95-ms', '500').returncode, 2)
