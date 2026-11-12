> **Illustrative Git calendar:** January-November 2026, assigned November 6, 2026.
> Actual implementation occurred in November 2026 with AI assistance. Generated
> scenarios are committed individually for this presentation calendar; commit
> counts are not evidence of earlier work or an equivalent number of features.
> See [HISTORY.md](HISTORY.md) and [SCENARIOS.md](SCENARIOS.md).

> The original 2024-2025 illustrative commits are preserved.

# Route Log Inspector

A dependency-free CLI for inspecting supplied JSONL request logs. It calculates deterministic nearest-rank p50/p95 latency, 5xx rate by route, optional trace filtering, and explicit sample-based SLO checks. Created in November 2026 with an illustrative Git calendar as a practical utility inspired by the blueprint's 2024–2026 operations theme.

## Run

Python 3.10+ and its standard library are sufficient. No package installation or live service is needed.

```powershell
python cli.py sample.jsonl
python cli.py sample.jsonl --route /tours/bookings --format csv
python cli.py sample.jsonl --slo-p95-ms 500 --slo-5xx-pct 1
python -m unittest discover -s tests -v
```

The SLO command returns exit code 0 when every selected route passes, 3 when a threshold fails or no rows match, 2 for invalid input, and 1 for file errors. It reports only on **supplied sample rows**, not production service health. A timestamp must have a timezone; each row must contain `timestamp`, a route template, HTTP `status`, `duration_ms`, and `trace_id`. Inputs are bounded to 50,000 rows, 8 MiB total, and 16 KiB per row. Duplicate JSON keys, malformed UTF-8, query-bearing routes, and invalid numeric types are rejected.

File and stdin reads are capped before parsing each record. The 16 KiB physical-row limit includes surrounding whitespace and excludes LF/CRLF terminators; oversized records are rejected without reading the entire line into memory. A final record without a newline is supported.

No requests are made to a log service, and no third-party packages are installed. The sample is synthetic. See [HISTORY.md](HISTORY.md) for provenance.

## Time windows, timelines, and baselines

Use `--since 2026-11-06T12:00:00Z --until 2026-11-06T12:01:00Z` to select a half-open time window. Offsets are compared as absolute instants. `python cli.py sample.jsonl --timeline --trace-id tour-a` returns ordered observations; their order is not a causal trace. `--baseline other.jsonl --minimum-requests 20` compares route p95 and error rates. New, missing, and undersized routes have explicit statuses instead of invented deltas. Time bounds apply to the current sample; the baseline file is independently selected. Exact route/trace filters apply to both. Timeline and baseline modes use JSON and cannot be combined with SLO gates.

Run `python scenarios.py` to replay every disclosed synthetic scenario offline.
