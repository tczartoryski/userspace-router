"""Portable release round-trip checks; no VM or live packet integration."""
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

import package


class PackageTests(unittest.TestCase):
    def test_architecture_sanitization_is_idempotent(self):
        original = (package.ROOT / 'docs/ARCHITECTURE.md').read_text()
        clean = package.sanitize_architecture(original)
        self.assertEqual(package.sanitize_architecture(clean), clean)
        self.assertNotIn('## Milestones and evidence', clean)
        self.assertNotIn('## Material prerequisite discovered', clean)
        self.assertIn('## Namespace attachment refinement', clean)
        # Sections may be missing or reordered; unrelated content must survive.
        for text in ('# Architecture\n\n## Dataplane\nKeep\n',
                     '## Material prerequisite discovered\nRemove\n## Dataplane\nKeep\n',
                     '## Milestones and evidence\nRemove\n## Dataplane\nKeep\n'):
            sanitized = package.sanitize_architecture(text)
            self.assertIn('Keep\n', sanitized)
            self.assertNotIn('Remove\n', sanitized)
            self.assertEqual(package.sanitize_architecture(sanitized), sanitized)

    def read_archive(self, path, expected):
        with tarfile.open(path, 'r:gz') as archive:
            members = archive.getmembers()
            self.assertEqual(len(members), len(expected))
            self.assertEqual({m.name for m in members}, expected)
            self.assertTrue(all(m.isfile() for m in members))
            contents = {m.name.removeprefix('udp-router/'): archive.extractfile(m).read()
                        for m in members}
        manifest = ''.join(hashlib.sha256(contents[name]).hexdigest() + '  ' + name + '\n'
                           for name in sorted(contents) if name != 'MANIFEST.sha256')
        self.assertEqual(contents['MANIFEST.sha256'].decode(), manifest)
        # Same internal-path/credential audit applies after each packaging pass.
        forbidden = re.compile(b'/Users' + b'/|/home/' + b'openclaw|codex-' +
                               b'run|BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}')
        for name, raw in contents.items():
            if name != 'scripts/package.py':
                self.assertIsNone(forbidden.search(raw), name)
            if name.endswith('.md'):
                for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)', raw.decode()):
                    link = urlsplit(target)
                    if link.scheme or link.netloc or not link.path:
                        continue
                    resolved = PurePosixPath(name).parent / unquote(link.path)
                    self.assertIn(str(resolved), contents, (name, target))
        return contents

    def test_extracted_release_repackages_with_same_allowlist_and_manifest(self):
        expected = {'udp-router/' + name for name in package.FILES}
        expected.add('udp-router/MANIFEST.sha256')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / 'first.tar.gz'
            package.build(first)
            original = self.read_archive(first, expected)
            fresh = root / 'fresh'
            fresh.mkdir()
            # Extract only after validating all members against the allowlist.
            with tarfile.open(first, 'r:gz') as archive:
                archive.extractall(fresh, filter='data')
            second = root / 'second.tar.gz'
            result = subprocess.run([sys.executable, 'scripts/package.py', str(second)],
                                    cwd=fresh / 'udp-router', capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            repacked = self.read_archive(second, expected)
            self.assertEqual(repacked, original)


if __name__ == '__main__':
    unittest.main()
