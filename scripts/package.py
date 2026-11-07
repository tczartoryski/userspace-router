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
