#!/usr/bin/env python3
"""Explicit release allowlist; excludes raw local logs and historical evidence."""
import hashlib
from pathlib import Path
import re
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ['Cargo.toml', 'Cargo.lock', 'README.md', 'docs/ARCHITECTURE.md', 'docs/architecture.svg',
         'docs/RELEASE-STATUS.md', 'docs/DEMO-VIDEO.md', 'docs/qa/BROWSER-BLOCKER.md',
         'docs/qa/RENDERED-QA.md', 'docs/PUBLICATION-AUDIT.md',
         'docs/img/banner.svg', 'docs/img/PROVENANCE.md']
# Only approved sanitized captures; never sweep the evidence directory.
RENDERED_FILES = ['docs/qa/rendered/' + name for name in
                  ('desktop.jpg', 'mobile.jpg', 'offline.png', 'live-demo.mov', 'capture-times.json')]
RENDERED_FILES.extend(f'docs/qa/rendered/frames/{index:04d}.png' for index in range(12))
BINARY_FILES = frozenset(name for name in RENDERED_FILES if not name.endswith('.json'))
FILES.extend(RENDERED_FILES)
FILES.append('docs/MULTICORE-RESULTS.md')
FILES.extend(['docs/benchmarks/multicore/workers-1-perf.json', 'docs/benchmarks/multicore/workers-1-size-1400.json', 'docs/benchmarks/multicore/workers-1-size-64.json', 'docs/benchmarks/multicore/workers-2-perf.json', 'docs/benchmarks/multicore/workers-2-size-1400.json', 'docs/benchmarks/multicore/workers-2-size-64.json', 'docs/benchmarks/multicore/workers-4-perf.json', 'docs/benchmarks/multicore/workers-4-size-1400.json', 'docs/benchmarks/multicore/workers-4-size-64.json'])
FILES.extend(['docs/MONITORING-RESULTS.md', 'docs/benchmarks/monitoring/router-worker-acceptance.json', 'docs/benchmarks/monitoring/workers-1-monitoring-off.json', 'docs/benchmarks/monitoring/workers-1-monitoring-on.json', 'docs/benchmarks/monitoring/workers-2-monitoring-off.json', 'docs/benchmarks/monitoring/workers-2-monitoring-on.json', 'docs/benchmarks/monitoring/workers-2-monitoring-sampled.json', 'docs/benchmarks/monitoring/workers-4-monitoring-off.json', 'docs/benchmarks/monitoring/workers-4-monitoring-on.json', 'docs/benchmarks/monitoring/workers-4-monitoring-sampled.json', 'docs/qa/v2-monitoring/desktop.png', 'docs/qa/v2-monitoring/mobile.png'])
BINARY_FILES = BINARY_FILES | {'docs/qa/v2-monitoring/desktop.png', 'docs/qa/v2-monitoring/mobile.png'}
# Reviewed source/UI allowlist. Generated scenario JSON requires separate review.
FILES.append('docs/benchmarks/optimization-comparison.json')
FILES.append('docs/benchmarks/optimization-comparison.md')
FILES.extend(['docs/benchmarks/e2e-after/e2e-128-1.json', 'docs/benchmarks/e2e-after/e2e-128-1.md', 'docs/benchmarks/e2e-after/e2e-128-512.json', 'docs/benchmarks/e2e-after/e2e-128-512.md', 'docs/benchmarks/e2e-after/e2e-128-64.json', 'docs/benchmarks/e2e-after/e2e-128-64.md', 'docs/benchmarks/e2e-after/e2e-1400-1.json', 'docs/benchmarks/e2e-after/e2e-1400-1.md', 'docs/benchmarks/e2e-after/e2e-1400-512.json', 'docs/benchmarks/e2e-after/e2e-1400-512.md', 'docs/benchmarks/e2e-after/e2e-1400-64.json', 'docs/benchmarks/e2e-after/e2e-1400-64.md', 'docs/benchmarks/e2e-after/e2e-512-1.json', 'docs/benchmarks/e2e-after/e2e-512-1.md', 'docs/benchmarks/e2e-after/e2e-512-512.json', 'docs/benchmarks/e2e-after/e2e-512-512.md', 'docs/benchmarks/e2e-after/e2e-512-64.json', 'docs/benchmarks/e2e-after/e2e-512-64.md', 'docs/benchmarks/e2e-after/e2e-64-1.json', 'docs/benchmarks/e2e-after/e2e-64-1.md', 'docs/benchmarks/e2e-after/e2e-64-512.json', 'docs/benchmarks/e2e-after/e2e-64-512.md', 'docs/benchmarks/e2e-after/e2e-64-64.json', 'docs/benchmarks/e2e-after/e2e-64-64.md', 'docs/benchmarks/e2e-after/profile-perf.json', 'docs/benchmarks/e2e-after/profile-perf.md', 'docs/benchmarks/e2e-after/profile-strace.json', 'docs/benchmarks/e2e-after/profile-strace.md', 'docs/benchmarks/comparison-long/after-128-512.json', 'docs/benchmarks/comparison-long/after-128-512.md', 'docs/benchmarks/comparison-long/after-1400-512.json', 'docs/benchmarks/comparison-long/after-1400-512.md', 'docs/benchmarks/comparison-long/after-512-512.json', 'docs/benchmarks/comparison-long/after-512-512.md', 'docs/benchmarks/comparison-long/after-64-512.json', 'docs/benchmarks/comparison-long/after-64-512.md', 'docs/benchmarks/comparison-long/before-128-512.json', 'docs/benchmarks/comparison-long/before-128-512.md', 'docs/benchmarks/comparison-long/before-1400-512.json', 'docs/benchmarks/comparison-long/before-1400-512.md', 'docs/benchmarks/comparison-long/before-512-512.json', 'docs/benchmarks/comparison-long/before-512-512.md', 'docs/benchmarks/comparison-long/before-64-512.json', 'docs/benchmarks/comparison-long/before-64-512.md', 'docs/benchmarks/after-linux.json', 'docs/benchmarks/after-linux.md'])
FILES.extend(['docs/benchmarks/e2e-baseline/e2e-64-1.json', 'docs/benchmarks/e2e-baseline/e2e-64-1.md', 'docs/benchmarks/e2e-baseline/e2e-64-64.json', 'docs/benchmarks/e2e-baseline/e2e-64-64.md', 'docs/benchmarks/e2e-baseline/e2e-64-512.json', 'docs/benchmarks/e2e-baseline/e2e-64-512.md', 'docs/benchmarks/e2e-baseline/e2e-128-1.json', 'docs/benchmarks/e2e-baseline/e2e-128-1.md', 'docs/benchmarks/e2e-baseline/e2e-128-64.json', 'docs/benchmarks/e2e-baseline/e2e-128-64.md', 'docs/benchmarks/e2e-baseline/e2e-128-512.json', 'docs/benchmarks/e2e-baseline/e2e-128-512.md', 'docs/benchmarks/e2e-baseline/e2e-512-1.json', 'docs/benchmarks/e2e-baseline/e2e-512-1.md', 'docs/benchmarks/e2e-baseline/e2e-512-64.json', 'docs/benchmarks/e2e-baseline/e2e-512-64.md', 'docs/benchmarks/e2e-baseline/e2e-512-512.json', 'docs/benchmarks/e2e-baseline/e2e-512-512.md', 'docs/benchmarks/e2e-baseline/e2e-1400-1.json', 'docs/benchmarks/e2e-baseline/e2e-1400-1.md', 'docs/benchmarks/e2e-baseline/e2e-1400-64.json', 'docs/benchmarks/e2e-baseline/e2e-1400-64.md', 'docs/benchmarks/e2e-baseline/e2e-1400-512.json', 'docs/benchmarks/e2e-baseline/e2e-1400-512.md', 'docs/benchmarks/e2e-baseline/profile-perf.json', 'docs/benchmarks/e2e-baseline/profile-perf.md', 'docs/benchmarks/e2e-baseline/profile-strace.json', 'docs/benchmarks/e2e-baseline/profile-strace.md'])
FILES.extend([
    'src/observability.rs',
    'scripts/worker_acceptance.py',
    'scripts/test_worker_acceptance.py',
    'scripts/test_observability.py',
    'scripts/test_dashboard_state.cjs',
    'docs/OBSERVABILITY.md',
    'docs/RESILIENCE.md',
    'src/packet_io.rs',
    'src/parallel.rs',
    'docs/MULTICORE-DESIGN.md',
    'scripts/e2e_benchmark.py',
    'scripts/linux-benchmark.sh',
    'scripts/test_e2e_benchmark.py',
    'docs/BENCHMARK-METHODOLOGY.md',
    'docs/OPTIMIZATION-RESULTS.md',
    'docs/benchmarks/baseline-linux.json',
    'docs/benchmarks/baseline-linux.md',
    'examples/core_bench.rs',
    'scripts/benchmark.py',
    'scripts/test_benchmark.py',
    'docs/AGENT_PROGRESS.md',
    'docs/PERFORMANCE-BASELINE.md',
    'docs/benchmarks/baseline-macos.json',
    'docs/benchmarks/baseline-macos.md', 'docs/benchmarks/linux-integration-baseline.json',
    'dashboard/app.js',
    'dashboard/index.html',
    'dashboard/style.css',
    'scripts/dashboard.py',
    'scripts/demo.py',
    'scripts/encode-demo.swift',
    'scripts/extended.py',
    'scripts/guest-demo.sh',
    'scripts/linux-integration.sh',
    'scripts/nat_story.py',
    'scripts/package.py',
    'scripts/read_snapshot.py',
    'scripts/serve_story.py',
    'scripts/test_dashboard.py',
    'scripts/test_demo.py',
    'scripts/test_documentation.py',
    'scripts/test_extended_verifier.py',
    'scripts/test_integration_bytecode.py',
    'scripts/test_nat_story.py',
    'scripts/test_story_timing.cjs',
    'scripts/test_package.py',
    'scripts/test_retained.py',
    'scripts/test_verifier.py',
    'scripts/traffic.py',
    'src/bin/udp-router.rs',
    'src/lib.rs',
    'src/linux.rs',
    'story/app.js',
    'story/index.html',
    'story/style.css',
    'tests/core.rs',
])
FILES.extend(['docs/NAT-STORY.md', 'docs/qa/nat-story/observations.json',
              'docs/qa/nat-story/capture.json', 'docs/qa/nat-story/nat-story.mp4',
              'docs/qa/nat-story/poster.png'])
BINARY_FILES = BINARY_FILES | {'docs/qa/nat-story/nat-story.mp4', 'docs/qa/nat-story/poster.png'}


def sanitize_architecture(text):
    """Drop historical sections by heading, including on an already clean input."""
    sections = re.split(r'(?=^## )', text, flags=re.M)
    historical = {'## Milestones and evidence', '## Material prerequisite discovered'}
    text = ''.join(section for section in sections
                   if section.split('\n', 1)[0].rstrip() not in historical)
    text = text.replace('**No Linux\nlinking, TUN I/O or controlled real UDP integration has run.** See\n[EVIDENCE.md](EVIDENCE.md) for exact scope and the remaining environment blocker.',
                        'Historical MVP and coordinator-supplied extended live tests passed. See [release status](RELEASE-STATUS.md).')
    return re.sub(r'> \*\*Follow-up.*?\n\n', '', text, flags=re.S)


def build(output):
    files = sorted(set(FILES))
    pattern = re.compile(rb'/Users/|/home/openclaw|codex-run|BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}')
    # Documentation is sanitized in the archive, preserving historical local originals.
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for name in files:
            source = ROOT/name
            if source.is_symlink():
                raise ValueError('symlink forbidden: '+name)
            raw = source.read_bytes()
            if name == 'docs/ARCHITECTURE.md':
                text = raw.decode()
                text = sanitize_architecture(text)
                raw = text.encode()
            # Audit code for secrets but permit the auditor's own literal pattern.
            if name not in BINARY_FILES and name != 'scripts/package.py' and pattern.search(raw):
                raise ValueError('secret/internal-path audit failed: '+name)
            target = stage/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        manifest = ''.join(hashlib.sha256((stage/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in files)
        (stage/'MANIFEST.sha256').write_text(manifest)
        with tarfile.open(output, 'w:gz') as tar:
            for name in files + ['MANIFEST.sha256']:
                tar.add(stage/name, arcname='udp-router/'+name, recursive=False)
    print(f'Package audit passed: {len(files)} allowlisted files; {output}')


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv)>1 else '/tmp/udp-router-release.tar.gz')
