"""Portable documentation checks; --audit-history inventories all reachable Git blobs.

History scanning is a heuristic review aid, not a proof of absence of secrets.
Media needs separate visual/metadata review. No network, VM or installs.
"""
from html.parser import HTMLParser
from pathlib import Path
import ipaddress
import re
import subprocess
import sys
import unittest
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

import package


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        self.targets.extend(value for key, value in attrs
                            if key in ('src', 'href') and value)


def check_documents(root, names):
    errors = []
    allowed = set(names)
    for name in names:
        path = root / name
        if path.suffix == '.md':
            text = path.read_text()
            parser = Links()
            parser.feed(text)
            targets = parser.targets + re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)', text)
            for target in targets:
                link = urlsplit(target)
                if link.scheme or link.netloc or not link.path:
                    continue
                resolved = (path.parent / unquote(link.path)).resolve()
                try:
                    relative = str(resolved.relative_to(root.resolve()))
                except ValueError:
                    errors.append(f'{name}: escaping link {target}')
                    continue
                if relative not in allowed or not resolved.is_file():
                    errors.append(f'{name}: missing/unpackaged link {target}')
        if path.suffix == '.svg':
            raw = path.read_text()
            if re.search(r'<!DOCTYPE|<!ENTITY', raw, re.I):
                errors.append(f'{name}: SVG declarations forbidden')
            tree = ET.fromstring(raw)
            safe = {'svg', 'title', 'desc', 'defs', 'marker', 'rect', 'g', 'path', 'text', 'circle', 'line', 'polyline', 'polygon'}
            for node in tree.iter():
                if node.tag.split('}')[-1] not in safe:
                    errors.append(f'{name}: unsafe SVG element')
                for key, value in node.attrib.items():
                    key = key.split('}')[-1].lower()
                    if key.startswith('on') or key in ('href', 'src', 'style') or re.search(r'url\((?!#[\w-]+\))', value):
                        errors.append(f'{name}: unsafe SVG attribute')
    return errors


def git(*args):
    return subprocess.check_output(['git', *args], cwd=package.ROOT)


def audit_history():
    commits = git('rev-list', '--all').decode().splitlines()
    entries, blobs = set(), set()
    for commit in commits:
        for item in git('ls-tree', '-rz', '-r', commit).split(b'\0'):
            if not item:
                continue
            meta, name = item.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            entries.add((mode, kind, oid, name.decode()))
            if kind == 'blob':
                blobs.add(oid)
    print(f'History: {len(commits)} commits, {len(blobs)} unique blobs, {len(entries)} tree entries')
    print(git('log', '--all', '--format=%h %an <%ae> | %cn <%ce> | %s').decode(), end='')
    findings = []
    credentials = re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9]{20,}')
    private_paths = re.compile(rb'/(?:Users/[^/\s]+|home/(?:openclaw|ubuntu|[^/\s]+))/|codex-' + rb'run')
    addresses, binary = set(), []
    for oid in sorted(blobs):
        raw = git('cat-file', 'blob', oid)
        names = sorted({entry[3] for entry in entries if entry[2] == oid})
        if credentials.search(raw):
            findings.append(('credential candidate', oid, names))
        # package.py contains its own literal audit expressions, not a private path.
        if private_paths.search(raw):
            findings.append(('private path candidate', oid, names))
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            binary.append((oid, names, len(raw)))
            continue
        for value in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', text):
            try:
                addresses.add(str(ipaddress.IPv4Address(value)))
            except ValueError:
                pass
    for entry in sorted(entries):
        mode, kind, oid, name = entry
        if mode != '100644' and mode != '100755':
            findings.append(('special tree mode', mode, name))
        if name.startswith(('.github/', '.gitmodules')) or name.endswith(('.zip', '.tar', '.gz', '.env', '.pem', '.key')):
            findings.append(('configuration/archive review', name))
    print('IPv4 literals:', ', '.join(sorted(addresses)))
    print('Binary inventory:')
    for item in binary:
        print(item)
    print('Candidates requiring contextual review:')
    for finding in findings:
        print(finding)
    return findings


class DocumentationTests(unittest.TestCase):
    def test_packaged_document_links_and_svg_safety(self):
        self.assertEqual(check_documents(package.ROOT, package.FILES), [])

    def test_banner_and_provenance_are_explicitly_allowlisted(self):
        self.assertIn('docs/img/banner.svg', package.FILES)
        self.assertIn('docs/img/PROVENANCE.md', package.FILES)
        self.assertIn('docs/PUBLICATION-AUDIT.md', package.FILES)


if __name__ == '__main__':
    if sys.argv[1:] == ['--audit-history']:
        audit_history()
    else:
        unittest.main()
