"""Bounded JSONL parsing and deterministic route latency/error summaries."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re


MAX_LINE_BYTES = 16384
MAX_ROWS = 50000
MAX_FILE_BYTES = 8 * 1024 * 1024


def parse_line(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_LINE_BYTES:
        raise ValueError('Log row must be 1-16384 UTF-8 bytes')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate log field: ' + key)
            value[key] = item
        return value
    try:
        row = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('Invalid UTF-8 JSON log row') from error
    if not isinstance(row, dict) or set(row) != {'timestamp', 'route', 'status', 'duration_ms', 'trace_id'}:
        raise ValueError('Log row requires timestamp, route, status, duration_ms, trace_id')
    if not isinstance(row['timestamp'], str) or len(row['timestamp']) > 40:
        raise ValueError('Invalid timestamp')
    try:
        stamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Invalid ISO timestamp') from error
    if stamp.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    route = row['route']
    if not isinstance(route, str) or not 1 <= len(route) <= 120 or not route.startswith('/') or '?' in route or any(ord(c) < 32 for c in route):
        raise ValueError('Route must be a bounded path template')
    if type(row['status']) is not int or not 100 <= row['status'] <= 599:
        raise ValueError('Invalid HTTP status')
    if type(row['duration_ms']) is not int or not 0 <= row['duration_ms'] <= 600000:
        raise ValueError('Invalid duration')
    trace = row['trace_id']
    if not isinstance(trace, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', trace):
        raise ValueError('Invalid trace ID')
    return row


def read_rows(source):
    rows = []
    total_bytes = 0
    lines = iter(lambda: source.readline(MAX_LINE_BYTES + 3), b'') if hasattr(source, 'readline') else source
    for line_number, raw in enumerate(lines, 1):
        if line_number > MAX_ROWS:
            raise ValueError('Log file exceeds 50000 rows')
        total_bytes += len(raw)
        if total_bytes > MAX_FILE_BYTES:
            raise ValueError('Log file exceeds 8 MiB')
        record = raw.removesuffix(b'\n')
        if raw.endswith(b'\r\n'):
            record = record[:-1]
        if len(record) > MAX_LINE_BYTES:
            raise ValueError(f'Line {line_number}: Log row exceeds 16384 UTF-8 bytes')
        if not raw.strip():
            continue
        try:
            rows.append(parse_line(raw.strip()))
        except ValueError as error:
            raise ValueError(f'Line {line_number}: {error}') from error
    return rows


def summarize(rows, route=None, trace_id=None):
    if route is not None and (not isinstance(route, str) or not route.startswith('/')):
        raise ValueError('Route filter must be a path')
    if trace_id is not None and (not isinstance(trace_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', trace_id)):
        raise ValueError('Invalid trace ID filter')
    groups = defaultdict(list)
    for row in rows:
        if (route is None or row['route'] == route) and (trace_id is None or row['trace_id'] == trace_id):
            groups[row['route']].append(row)
    result = []
    for name in sorted(groups):
        group = groups[name]
        durations = sorted(row['duration_ms'] for row in group)
        errors = sum(row['status'] >= 500 for row in group)
        result.append({'route': name, 'requests': len(group), 'errors_5xx': errors,
                       'error_rate_pct': format(Decimal(errors * 100) / Decimal(len(group)), '.2f'),
                       'p50_ms': durations[(50 * len(durations) + 99) // 100 - 1],
                       'p95_ms': durations[(95 * len(durations) + 99) // 100 - 1]})
    return {'routes': result, 'total_requests': sum(row['requests'] for row in result),
            'basis': 'supplied log rows; nearest-rank percentiles'}


def evaluate_slo(summary, p95_limit_ms, error_rate_limit_pct):
    if type(p95_limit_ms) is not int or not 1 <= p95_limit_ms <= 600000:
        raise ValueError('p95 limit must be 1-600000 ms')
    try:
        error_limit = Decimal(str(error_rate_limit_pct))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError('Invalid 5xx rate limit') from error
    if not error_limit.is_finite() or not 0 <= error_limit <= 100:
        raise ValueError('5xx rate limit must be 0-100 percent')
    violations = []
    for row in summary['routes']:
        if row['p95_ms'] > p95_limit_ms:
            violations.append({'route': row['route'], 'check': 'p95_ms', 'actual': row['p95_ms'], 'limit': p95_limit_ms})
        if Decimal(row['errors_5xx'] * 100) / Decimal(row['requests']) > error_limit:
            violations.append({'route': row['route'], 'check': 'error_rate_pct',
                               'actual': row['error_rate_pct'], 'limit': format(error_limit, '.2f')})
    if not summary['total_requests']:
        violations.append({'route': None, 'check': 'sample_size', 'actual': 0, 'limit': 'at least one request'})
    return {'passed': not violations, 'violations': violations,
            'basis': 'supplied sample only; no production SLO claim'}
