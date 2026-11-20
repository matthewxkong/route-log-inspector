"""Inspect bounded JSONL request logs without installing dependencies."""
import argparse
import csv
import io
import json
import sys

from inspector import evaluate_slo, read_rows, summarize
from analysis import compare_samples, trace_timeline, window_rows


def csv_report(summary):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['route', 'requests', 'errors_5xx', 'error_rate_pct', 'p50_ms', 'p95_ms'])
    for row in summary['routes']:
        writer.writerow([row[key] for key in ('route', 'requests', 'errors_5xx', 'error_rate_pct', 'p50_ms', 'p95_ms')])
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', default='-', help='UTF-8 JSONL file or - for stdin')
    parser.add_argument('--route', help='exact route template filter')
    parser.add_argument('--trace-id', help='exact trace ID filter')
    parser.add_argument('--since', help='inclusive timezone-aware ISO lower bound')
    parser.add_argument('--until', help='exclusive timezone-aware ISO upper bound')
    parser.add_argument('--timeline', action='store_true', help='JSON event timeline; requires --trace-id')
    parser.add_argument('--baseline', help='compare selected rows with a separate JSONL baseline')
    parser.add_argument('--minimum-requests', type=int, help='per-sample route count needed for comparison (default: 20)')
    parser.add_argument('--format', choices=('json', 'csv'), default='json')
    parser.add_argument('--slo-p95-ms', type=int, help='optional p95 threshold for every selected route')
    parser.add_argument('--slo-5xx-pct', help='optional maximum 5xx percent for every selected route')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.minimum_requests is not None and not args.baseline:
            raise ValueError('--minimum-requests requires --baseline')
        if args.path == '-':
            rows = read_rows(sys.stdin.buffer)
        else:
            with open(args.path, 'rb') as source:
                rows = read_rows(source)
        rows = window_rows(rows, args.since, args.until)
        if args.timeline or args.baseline:
            if args.format != 'json' or args.slo_p95_ms is not None or args.slo_5xx_pct is not None:
                raise ValueError('Timeline and baseline modes require JSON and cannot combine with SLO gates')
            if args.timeline and args.baseline:
                raise ValueError('Choose either timeline or baseline mode')
            if args.route is not None or args.trace_id is not None:
                summarize(rows, args.route, args.trace_id)  # validate filters before applying them
                rows = [row for row in rows if (args.route is None or row['route'] == args.route)
                        and (args.trace_id is None or row['trace_id'] == args.trace_id)]
            if args.timeline:
                result = trace_timeline(rows, args.trace_id)
            else:
                with open(args.baseline, 'rb') as source:
                    baseline = read_rows(source)
                if args.route is not None or args.trace_id is not None:
                    baseline = [row for row in baseline if (args.route is None or row['route'] == args.route)
                                and (args.trace_id is None or row['trace_id'] == args.trace_id)]
                result = compare_samples(baseline, rows, 20 if args.minimum_requests is None else args.minimum_requests)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        result = summarize(rows, args.route, args.trace_id)
        if (args.slo_p95_ms is None) != (args.slo_5xx_pct is None):
            raise ValueError('Both SLO thresholds are required together')
        if args.slo_p95_ms is not None:
            if args.format == 'csv':
                raise ValueError('SLO evaluation is available in JSON output')
            result['slo'] = evaluate_slo(result, args.slo_p95_ms, args.slo_5xx_pct)
        print(json.dumps(result, indent=2, ensure_ascii=False) if args.format == 'json' else csv_report(result),
              end='\n' if args.format == 'json' else '')
        return 0 if 'slo' not in result or result['slo']['passed'] else 3
    except (ValueError, RecursionError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 2
    except OSError as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
