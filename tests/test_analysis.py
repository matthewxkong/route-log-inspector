import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analysis import compare_samples, trace_timeline, window_rows


def row(stamp='2026-01-02T12:00:00Z', duration=20, status=200, route='/tours', trace='one'):
    return {'timestamp': stamp, 'route': route, 'status': status, 'duration_ms': duration, 'trace_id': trace}


class AnalysisTests(unittest.TestCase):
    def test_baseline_window(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.jsonl'
            path.write_text('\n'.join(json.dumps(row(stamp)) for stamp in
                                      ('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')), encoding='utf-8')
            cli = Path(__file__).resolve().parents[1] / 'cli.py'
            result = subprocess.run([sys.executable, str(cli), str(path), '--baseline', str(path),
                                     '--baseline-until', '2026-01-02T00:00:00Z'],
                                    capture_output=True, check=True)
        item = json.loads(result.stdout)['routes'][0]
        self.assertEqual((item['baseline_requests'], item['current_requests']), (1, 2))

    def test_windows_compare_absolute_instants_and_exclude_upper_boundary(self):
        rows = [row('2026-01-02T04:00:00-08:00'), row('2026-01-02T12:01:00Z')]
        self.assertEqual(window_rows(rows, '2026-01-02T12:00:00Z', '2026-01-02T12:01:00Z'), rows[:1])
        for lower, upper in [('2026-01-02', None), ('2026-01-02T12:01:00Z', '2026-01-02T12:01:00Z')]:
            with self.assertRaises(ValueError):
                window_rows(rows, lower, upper)

    def test_timeline_is_stable_across_offsets_and_does_not_mutate_input(self):
        rows = [row('2026-01-02T12:01:00Z'), row('2026-01-02T04:00:00-08:00'), row(trace='other')]
        result = trace_timeline(rows, 'one')
        self.assertEqual(result['total_requests'], 2)
        self.assertEqual(result['events'][0]['timestamp'], '2026-01-02T04:00:00-08:00')
        result['events'][0]['duration_ms'] = 999
        self.assertEqual(rows[1]['duration_ms'], 20)

    def test_comparison_explains_missing_new_and_undersized_routes(self):
        before = [row()] * 20 + [row(route='/gone')] * 20
        after = [row(duration=40, status=503)] * 20 + [row(route='/new')]
        result = {item['route']: item for item in compare_samples(before, after)['routes']}
        self.assertEqual(result['/tours']['p95_delta_ms'], 20)
        self.assertEqual(result['/tours']['error_rate_delta_pct'], '100.00')
        self.assertEqual(result['/gone']['status'], 'missing_route')
        self.assertEqual(result['/new']['status'], 'new_route')
        self.assertEqual(compare_samples([row()], [row()])['routes'][0]['status'], 'insufficient_sample')

    def test_cli_modes_fail_cleanly_and_baseline_is_independent_of_current_window(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rows.jsonl'
            path.write_text(json.dumps(row()) + '\n', encoding='utf-8')
            root = Path(__file__).resolve().parents[1]
            args = [sys.executable, str(root / 'cli.py'), str(path)]
            result = subprocess.run(args + ['--timeline'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            result = subprocess.run(args + ['--baseline', str(path), '--minimum-requests', '1'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['routes'][0]['p95_delta_ms'], 0)
