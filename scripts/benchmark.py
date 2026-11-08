#!/usr/bin/env python3
"""Bounded portable MICRO runner. No privileged setup or environment discovery."""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

CASES = {'timestamp', 'cold_allocation', 'warm_outbound', 'reverse_lookup', 'expiry'}


def parse(raw, n):
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        if set(row) != {'schema', 'kind', 'case', 'size', 'flows', 'n', 'p50_ns', 'p95_ns', 'p99_ns', 'sum_ns', 'wall_ns', 'cpu_ns', 'rss_bytes'}:
            raise ValueError('invalid fields')
        if type(row['schema']) is not int or row['schema'] != 1 or row['kind'] != 'MICRO' or row['case'] not in CASES:
            raise ValueError('invalid schema')
        for key in ('size', 'flows', 'n', 'p50_ns', 'p95_ns', 'p99_ns', 'sum_ns', 'wall_ns'):
            if type(row[key]) is not int or not 0 <= row[key] <= 2**63-1:
                raise ValueError('invalid metric')
        if row['n'] != n or not row['p50_ns'] <= row['p95_ns'] <= row['p99_ns'] <= row['sum_ns'] <= row['wall_ns']:
            raise ValueError('inconsistent metrics')
        if row['cpu_ns'] is not None or row['rss_bytes'] is not None:
            raise ValueError('unsupported metric')
        rows.append(row)
    expected = {('timestamp', 0, 0)} | {(c, s, f) for c in CASES-{'timestamp'} for s in (64,128,512,1400) for f in (1,64,512)}
    if len(rows) != len(expected) or {(r['case'],r['size'],r['flows']) for r in rows} != expected:
        raise ValueError('missing/duplicate cases')
    return sorted(rows, key=lambda r: (r["case"], r["size"], r["flows"]))


def aggregate(values):
    if len(values) < 3 or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('require at least three finite nonnegative samples')
    mean = statistics.mean(values)
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values),
                cv=statistics.stdev(values)/mean if mean else 0.0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('executable', type=Path)
    p.add_argument('--count', type=int, default=128)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--metadata', required=True, help='generic hardware/OS/compiler label, no paths or identifiers')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.count <= 2000 or not 3 <= a.repeats <= 10:
        p.error('count 1..2000; repeats 3..10')
    if not re.fullmatch(r'[A-Za-z0-9 .,+()=_-]{1,240}', a.metadata):
        p.error('generic metadata only')
    runs = []
    start = time.monotonic()
    for _ in range(a.repeats):
        remaining = 90 - (time.monotonic()-start)
        if remaining <= 0:
            raise TimeoutError('90 second run budget')
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            subprocess.run([str(a.executable.resolve()), str(a.count)], stdout=out, stderr=err,
                           timeout=remaining, check=True)
            if out.tell() > 65536 or err.tell() > 4096:
                raise ValueError('output bound exceeded')
            out.seek(0)
            runs.append(parse(out.read().decode('ascii'), a.count))
    summary = []
    for i, row in enumerate(runs[0]):
        summary.append(dict(case=row['case'], size=row['size'], flows=row['flows'],
                            p50_ns=aggregate([run[i]['p50_ns'] for run in runs])))
    result = dict(schema=1, kind='MICRO', metadata=a.metadata, count=a.count,
                  repeats=a.repeats, cpu='not measured', rss='coordinator sampled; not collected here',
                  runs=runs, summary=summary)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    lines = ['# Actual portable MICRO baseline', '', a.metadata, '',
             f'{a.repeats} repeats; {a.count} operations per case per repeat. Median of repeat p50s; CV uses repeat p50s.',
             'CPU unmeasured. RSS reserved for coordinator sampling. No Linux/TUN/E2E measurement.', '',
             '| Case | IPv4 bytes | Flows | Median p50 ns | Min–max p50 ns | CV |',
             '|---|---:|---:|---:|---:|---:|']
    for r in summary:
        v = r['p50_ns']
        lines.append(f"| {r['case']} | {r['size']} | {r['flows']} | {v['median']} | {v['minimum']}–{v['maximum']} | {v['cv']:.3f} |")
    a.output.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    print(f'Validated {len(summary)} cases x {a.repeats} repeats')


if __name__ == '__main__':
    main()
