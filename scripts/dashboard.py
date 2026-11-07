#!/usr/bin/env python3
"""Read-only loopback telemetry viewer; no dependencies or HTTP-controlled commands."""
import argparse
import json
import ipaddress
import re
import os
from pathlib import Path
import stat
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

LIMIT = 1048576
ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
ROOT = Path(__file__).resolve().parent.parent / 'dashboard'


DROP_NAMES = 'Malformed Options Fragment Protocol Checksum Address Ttl Mtu Route Policy Filter Capacity Clock'.split()
U64 = 2**64 - 1


def integer(value, low=0, high=U64):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid bounded integer')
    return value


def endpoint(value):
    if not isinstance(value, str) or len(value) > 21:
        raise ValueError('invalid endpoint')
    host, port = value.split(':')
    ipaddress.IPv4Address(host)
    if not port.isascii() or not port.isdecimal():
        raise ValueError('invalid port')
    return host, integer(int(port), 1, 65535)


def validate_snapshot(data):
    if type(data) is not dict or type(data.get('schema')) is not int or data['schema'] != 1 or type(data.get('running')) is not bool:
        raise ValueError('unsupported snapshot')
    # The producer emits integer seconds; floats (including NaN/Inf) are invalid.
    for key in ('unix_seconds', 'uptime_seconds', 'io_drops'):
        integer(data[key])
    interfaces = data['interfaces']
    if type(interfaces) is not list or len(interfaces) != 2 or len(set(interfaces)) != 2:
        raise ValueError('invalid interfaces')
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', v) for v in interfaces):
        raise ValueError('invalid interface')
    core = data['core']
    for key in ('received', 'forwarded', 'expired', 'active', 'idle_seconds'):
        integer(core[key], 1 if key == 'idle_seconds' else 0)
    integer(core['max_flows'], 1, 65535)
    ports = core['ports']
    if type(ports) is not list or len(ports) != 2:
        raise ValueError('invalid ports')
    integer(ports[0], 1, 65535)
    integer(ports[1], ports[0], 65535)
    if core['active'] > min(core['max_flows'], ports[1] - ports[0] + 1):
        raise ValueError('active exceeds capacity')
    routes = core['routes']
    if type(routes) is not list or not 1 <= len(routes) <= 128:
        raise ValueError('invalid routes')
    networks = set()
    for route in routes:
        network = str(ipaddress.IPv4Network(route['network'], strict=True))
        if network in networks or route['side'] not in ('Inside', 'Outside'):
            raise ValueError('invalid route')
        networks.add(network)
    drops = core['drops']
    if type(drops) is not dict or set(drops) != set(DROP_NAMES):
        raise ValueError('invalid drops')
    for count in drops.values():
        integer(count)
    if core['received'] != min(U64, core['forwarded'] + sum(drops.values())):
        raise ValueError('counter mismatch')
    mappings = core['mappings']
    if type(mappings) is not list or len(mappings) != min(core['active'], 2048):
        raise ValueError('mapping count mismatch')
    if type(core['mappings_truncated']) is not bool or core['mappings_truncated'] != (core['active'] > 2048):
        raise ValueError('truncation mismatch')
    used = set()
    external_host = None
    tuples = set()
    for mapping in mappings:
        internal, remote, external = (endpoint(mapping[k]) for k in ('internal', 'remote', 'external'))
        integer(mapping['idle_seconds'])
        if not ports[0] <= external[1] <= ports[1] or external[1] in used or (internal, remote) in tuples:
            raise ValueError('mapping mismatch')
        if external_host is not None and external_host != external[0]:
            raise ValueError('external address mismatch')
        external_host = external[0]
        used.add(external[1])
        tuples.add((internal, remote))


def read_snapshot(path, guest=False, guest_root="router"):
    if guest:
        # Fixed command and fixed task-owned path. Neither is derived from HTTP.
        result = subprocess.run([os.path.expanduser('~/.local/opt/lima-2.3.0/bin/limactl'),
                                 'shell', 'router-lab', 'sudo', '-n', 'python3', '-B', guest_root + '/scripts/read_snapshot.py'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=True)
        raw = result.stdout
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as file:
            meta = os.fstat(file.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
                raise ValueError('snapshot must be a private regular file')
            raw = file.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('snapshot too large')
    data = json.loads(raw)
    validate_snapshot(data)
    age = time.time() - data['unix_seconds']
    state = 'offline' if not data['running'] else ('current' if -2 <= age <= 5 else 'stale')
    return dict(state=state, age_seconds=max(0, round(age, 1)), snapshot=data)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def do_GET(self):
        expected = '127.0.0.1:' + str(self.server.server_port)
        if self.headers.get_all('Host') != [expected] or self.headers.get_all('Origin', []) not in ([], ['http://' + expected]):
            return self.respond(403, b'Forbidden', 'text/plain')
        if self.headers.get_all('Sec-Fetch-Site', []) not in ([], ['same-origin'], ['none']):
            return self.respond(403, b'Forbidden', 'text/plain')
        if self.path == '/api/snapshot':
            try:
                data = read_snapshot(self.server.snapshot, self.server.guest, getattr(self.server, 'guest_root', 'router'))
            except (OSError, ValueError, KeyError, TypeError, OverflowError, AttributeError, RecursionError, subprocess.SubprocessError):
                data = dict(state='offline', error='Runtime snapshot unavailable')
            return self.respond(200, json.dumps(data).encode(), 'application/json')
        if self.path not in ASSETS:
            return self.respond(404, b'Not found', 'text/plain')
        name, mime = ASSETS[self.path]
        self.respond(200, (ROOT / name).read_bytes(), mime)

    def respond(self, code, body, mime):
        self.send_response(code)
        for key, value in {'Content-Type': mime + '; charset=utf-8', 'Content-Length': str(len(body)),
                           'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                           'Content-Security-Policy': "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                           'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def reject(self):
        self.respond(405, b'Read only', 'text/plain')

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = reject


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', default='/tmp/udp-router-demo/snapshot.json')
    parser.add_argument('--guest', action='store_true')
    parser.add_argument('--guest-root', default='router')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    server.snapshot, server.guest, server.guest_root = args.snapshot, args.guest, args.guest_root
    print(f'http://127.0.0.1:{server.server_port} — sensitive tuples, localhost read-only', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
