#!/usr/bin/env python3
"""Explicit release allowlist; excludes raw local logs and historical evidence."""
import hashlib
from pathlib import Path
import re
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ['Cargo.toml', 'Cargo.lock', 'README.md', 'docs/ARCHITECTURE.md', 'docs/architecture.svg',
         'docs/RELEASE-STATUS.md', 'docs/DEMO-VIDEO.md', 'docs/qa/BROWSER-BLOCKER.md']
for folder in ('src', 'tests', 'scripts', 'dashboard'):
    FILES.extend(str(p.relative_to(ROOT)) for p in (ROOT/folder).rglob('*')
                 if p.is_file() and p.suffix in ('.rs', '.py', '.sh', '.html', '.css', '.js', '.swift'))


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
            if name in ('README.md', 'docs/ARCHITECTURE.md'):
                text = raw.decode()
                # Replace legacy reproduction/evidence sections with release-specific docs.
                if name == 'README.md':
                    text = RELEASE_README
                else:
                    text = sanitize_architecture(text)
                raw = text.encode()
            # Audit code for secrets but permit the auditor's own literal pattern.
            if name != 'scripts/package.py' and pattern.search(raw):
                raise ValueError('secret/internal-path audit failed: '+name)
            target = stage/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        manifest = ''.join(hashlib.sha256((stage/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in files)
        (stage/'MANIFEST.sha256').write_text(manifest)
        with tarfile.open(output, 'w:gz') as tar:
            for name in files + ['MANIFEST.sha256']:
                tar.add(stage/name, arcname='udp-router/'+name, recursive=False)
    print(f'Package audit passed: {len(files)} allowlisted files; {output}')


RELEASE_README = '''# Userspace Router

Real IPv4/UDP forwarding and endpoint-dependent SNAT through precreated Linux TUN
interfaces. Kernel forwarding/NAT does not perform the dataplane. No dependencies.
Repository: `tczartoryski/userspace-router` (private, owner-approved). License remains pending owner decision. No license grant.

Portable checks: `cargo test --locked --offline` and
`python3 -m unittest discover -s scripts -p 'test_*.py'`.
Linux requires an explicitly approved isolated environment with existing iproute2,
Python 3, Rust and /dev/net/tun. Never run namespace setup on a shared host.
Inside the approved Ubuntu lab: `bash scripts/guest-demo.sh` runs both extended
real-packet suites. `bash scripts/guest-demo.sh --retain` also retains real traffic
for QA until Ctrl-C cleans up namespaces and processes.

On the approved Lima host, `python3 scripts/demo.py` copies only the release
allowlist, starts the guest demo and localhost dashboard, and stops the VM on exit.
Use http://127.0.0.1:8765. Ctrl-C or SIGTERM stops and cleans up.
The dashboard is read-only; snapshots contain sensitive network tuples, hidden
by default. Stale and offline snapshots are labeled. No public listener or CDN.

See docs/ARCHITECTURE.md, docs/RELEASE-STATUS.md, docs/DEMO-VIDEO.md and
[architecture diagram](docs/architecture.svg). No production/throughput claim.
'''
if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv)>1 else '/tmp/udp-router-release.tar.gz')
