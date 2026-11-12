import io
import json
import unittest

from inspector import MAX_LINE_BYTES, evaluate_slo, parse_line, read_rows, summarize


def line(route='/tours', status=200, duration=20, trace='abc'):
    return json.dumps({'timestamp': '2026-11-06T12:00:00Z', 'route': route, 'status': status,
                       'duration_ms': duration, 'trace_id': trace}).encode() + b'\n'


class InspectorTests(unittest.TestCase):
    def test_oversized_record_is_rejected_before_consuming_the_whole_stream(self):
        for character in (b'x', b' ', b'\r'):
            with self.subTest(character=character):
                source = io.BytesIO(character * (MAX_LINE_BYTES * 64))
                with self.assertRaises(ValueError):
                    read_rows(source)
                self.assertLessEqual(source.tell(), MAX_LINE_BYTES * 2)

    def test_boundary_sized_records_preserve_line_ending_and_iterable_support(self):
        record = line().rstrip(b'\n').ljust(MAX_LINE_BYTES, b' ')
        for ending in (b'\n', b'\r\n', b''):
            with self.subTest(ending=ending):
                self.assertEqual(read_rows(io.BytesIO(record + ending))[0]['route'], '/tours')
        self.assertEqual(read_rows(iter([line()]))[0]['route'], '/tours')

    def test_nearest_rank_latency_and_error_rate(self):
        rows = read_rows(io.BytesIO(b''.join(line(status=503 if index == 19 else 200,
                                             duration=index + 1) for index in range(20))))
        summary = summarize(rows)
        self.assertEqual(summary['routes'][0]['p50_ms'], 10)
        self.assertEqual(summary['routes'][0]['p95_ms'], 19)
        self.assertEqual(summary['routes'][0]['error_rate_pct'], '5.00')

    def test_trace_filter_and_invalid_rows(self):
        rows = read_rows(io.BytesIO(line(trace='one') + line('/health', trace='two')))
        self.assertEqual(summarize(rows, trace_id='one')['total_requests'], 1)
        for raw in (b'{"status":200,"status":500}\n', b'[]\n', line(duration=-1), line(route='/a?secret=1')):
            with self.assertRaises(ValueError):
                read_rows(io.BytesIO(raw))
        self.assertEqual(parse_line(line().strip())['route'], '/tours')

    def test_slo_failures_and_empty_samples_are_explicit(self):
        summary = summarize(read_rows(io.BytesIO(line(status=503, duration=800))))
        gate = evaluate_slo(summary, 500, '1.00')
        self.assertFalse(gate['passed'])
        self.assertEqual({row['check'] for row in gate['violations']}, {'p95_ms', 'error_rate_pct'})
        self.assertFalse(evaluate_slo(summarize([]), 500, '1.00')['passed'])
