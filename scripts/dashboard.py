#!/usr/bin/env python3
"""Read-only loopback telemetry viewer; no dependencies or HTTP-controlled commands."""
import argparse
import json
import math
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
    if type(data) is dict and type(data.get("schema")) is int and data["schema"] == 2:
        return validate_parallel(data)
    if type(data) is not dict or type(data.get('schema')) is not int or data['schema'] != 1 or type(data.get('running')) is not bool:
        raise ValueError('unsupported snapshot')
    exact(data,'schema unix_seconds uptime_seconds running io_drops interfaces core')
    # The producer emits integer seconds; floats (including NaN/Inf) are invalid.
    for key in ('unix_seconds', 'uptime_seconds', 'io_drops'):
        integer(data[key])
    interfaces = data['interfaces']
    if type(interfaces) is not list or len(interfaces) != 2 or len(set(interfaces)) != 2:
        raise ValueError('invalid interfaces')
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', v) for v in interfaces):
        raise ValueError('invalid interface')
    core = data['core']
    exact(core,'received forwarded expired active idle_seconds max_flows ports routes drops mappings mappings_truncated')
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
        exact(route,'network side')
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
        exact(mapping,'internal remote external idle_seconds')
        internal, remote, external = (endpoint(mapping[k]) for k in ('internal', 'remote', 'external'))
        integer(mapping['idle_seconds'])
        if not ports[0] <= external[1] <= ports[1] or external[1] in used or (internal, remote) in tuples:
            raise ValueError('mapping mismatch')
        if external_host is not None and external_host != external[0]:
            raise ValueError('external address mismatch')
        external_host = external[0]
        used.add(external[1])
        tuples.add((internal, remote))


def exact(data, keys):
    if type(data) is not dict or set(data) != set(keys.split()):
        raise ValueError('unexpected/private snapshot fields')


def validate_core_counts(c):
    exact(c, 'received forwarded expired active drops')
    for k in ('received','forwarded','expired','active'): integer(c[k])
    exact(c['drops'], ' '.join(DROP_NAMES))
    for v in c['drops'].values(): integer(v)
    if c['received'] != min(U64,c['forwarded']+sum(c['drops'].values())):
        raise ValueError('core conservation')


def validate_queue(q, processing):
    exact(q, 'capacity channel_capacity admitted completed occupancy high_water dropped shutdown_drops')
    for v in q.values(): integer(v)
    integer(q['channel_capacity'],1,1024)
    if (q['capacity'] != q['channel_capacity']+int(processing) or
        not q['occupancy'] <= q['high_water'] <= q['capacity'] or
        q['admitted'] != min(U64,q['completed']+q['occupancy']+q['shutdown_drops'])):
        raise ValueError('queue conservation/bounds')


def validate_parallel(d):
    exact(d, 'schema unix_seconds uptime_seconds monotonic_ns running interfaces backend mode monitoring event_sample_every io_drops tx dispatcher output workers rates')
    if type(d['running']) is not bool or d['monitoring'] is not True or d['backend'] != 'tun-poll' or d['mode'] != 'workers':
        raise ValueError('invalid backend/state')
    for k in ('unix_seconds','uptime_seconds','monotonic_ns','event_sample_every','io_drops'): integer(d[k])
    if d['uptime_seconds'] != d['monotonic_ns']//1_000_000_000:
        raise ValueError('monotonic units')
    names=d['interfaces']
    if type(names) is not list or len(names) != 2 or any(type(n) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,15}',n) for n in names) or len(set(names)) != 2:
        raise ValueError('interface identities')
    validate_core_counts(d['dispatcher'])
    if any(d['dispatcher'][k] for k in ('forwarded','expired','active')): raise ValueError('dispatcher core state')
    validate_queue(d['output'],False)
    exact(d['tx'],'packets ip_bytes would_block')
    for v in d['tx'].values(): integer(v)
    tx=d['tx']
    if not 28*tx['packets'] <= tx['ip_bytes'] <= 65535*tx['packets'] or d['output']['completed'] != tx['packets']+tx['would_block']:
        raise ValueError('actual transmit accounting')
    workers=d['workers']
    if type(workers) is not list or not 2 <= len(workers) <= 32: raise ValueError('worker bounds')
    last=None; capacity=0; forwarded=0; drops=tx['would_block']+d['output']['dropped']+d['output']['shutdown_drops']; slots=d['output']['channel_capacity']
    for i,w in enumerate(workers):
        exact(w,'id ports capacity observed_ns core input events')
        if type(w['id']) is not int or w['id'] != i: raise ValueError('worker identity')
        ports=w['ports']
        if type(ports) is not list or len(ports) != 2: raise ValueError('ports')
        integer(ports[0],1,65535); integer(ports[1],ports[0],65535)
        if last is not None and ports[0] != last+1: raise ValueError('overlapping/missing port ownership')
        last=ports[1]; integer(w['capacity'],1,ports[1]-ports[0]+1); capacity+=w['capacity']
        integer(w['observed_ns'],0,d['monotonic_ns'])
        validate_core_counts(w['core']); validate_queue(w['input'],True)
        q=w['input']; c=w['core']; slots+=q['channel_capacity']
        if q['channel_capacity'] != d['output']['channel_capacity'] or c['active'] > w['capacity'] or c['received'] > q['completed']:
            raise ValueError('worker/report skew')
        if not d['running'] and c['received'] != q['completed']: raise ValueError('final report incomplete')
        forwarded+=c['forwarded']; drops+=q['dropped']+q['shutdown_drops']
        events=w['events']
        if type(events) is not list or len(events)>64 or (d['event_sample_every']==0 and events): raise ValueError('event bounds/disabled')
        before=0; counts={}
        for e in events:
            exact(e,'monotonic_ns direction reason bytes')
            integer(e['monotonic_ns'],before,w['observed_ns']); before=e['monotonic_ns']; integer(e['bytes'],28,65535)
            if e['direction'] not in ('Inside','Outside') or e['reason'] not in ['Forward']+DROP_NAMES: raise ValueError('event fields')
            counts[e['reason']]=counts.get(e['reason'],0)+1
        if any(count>(c['forwarded'] if reason=='Forward' else c['drops'][reason]) for reason,count in counts.items()): raise ValueError('invented events')
    if capacity>65535 or slots>4096 or d['io_drops'] != min(U64,drops): raise ValueError('aggregate limits/drops')
    if not d['running'] and forwarded != d['output']['admitted']+d['output']['dropped']: raise ValueError('final output conservation')
    exact(d['rates'],'interval_ns tx_pps tx_ip_mbps core_forwarded_pps')
    r=d['rates']
    if r['interval_ns'] is None:
        if any(r[k] is not None for k in ('tx_pps','tx_ip_mbps','core_forwarded_pps')): raise ValueError('rate without interval')
    else:
        integer(r['interval_ns'],1,d['monotonic_ns'])
        for k in ('tx_pps','tx_ip_mbps','core_forwarded_pps'):
            if type(r[k]) not in (int,float) or not math.isfinite(r[k]) or r[k]<0: raise ValueError('invalid rate')


def read_snapshot(path, guest=False, guest_root="router"):
    if guest:
        # Fixed command and fixed task-owned path. Neither is derived from HTTP.
        result = subprocess.run([os.path.expanduser('~/.local/opt/lima-2.3.0/bin/limactl'),
                                 'shell', 'router-lab', 'sudo', '-n', 'python3', '-B', guest_root + '/scripts/read_snapshot.py'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=True)
        raw = result.stdout
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
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
