#!/usr/bin/env python3
"""Local-only Linux integration support. Python standard library, no proxy forwarding."""
import ctypes
import fcntl
import json
import os
import re
from pathlib import Path
import socket
import struct
import sys
import time


def launch(client, server, binary):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.setns.argtypes = (ctypes.c_int, ctypes.c_int)
    original = os.open('/proc/self/ns/net', os.O_RDONLY)
    devices = []
    try:
        for namespace, name in ((client, b'tun-in'), (server, b'tun-out')):
            ns = os.open('/run/netns/' + namespace, os.O_RDONLY)
            try:
                if libc.setns(ns, 0x40000000) != 0:
                    raise OSError(ctypes.get_errno(), 'setns endpoint')
            finally:
                os.close(ns)
            fd = os.open('/dev/net/tun', os.O_RDWR | os.O_NONBLOCK)
            devices.append(fd)
            fcntl.ioctl(fd, 0x400454CA, struct.pack('16sH22x', name, 0x1001))
            os.set_inheritable(fd, True)
        if libc.setns(original, 0x40000000) != 0:
            raise OSError(ctypes.get_errno(), 'setns router')
    finally:
        os.close(original)
    extra = json.loads(os.environ.get('UDP_ROUTER_EXTRA_ARGS', '[]'))
    os.execv(binary, [binary, '--inside-fd', str(devices[0]), '--outside-fd', str(devices[1]),
                     '--external', '198.51.100.1', '--ports', '40000-40002', '--max-flows', '3',
                     '--idle-seconds', '30', '--route', '10.0.0.0/24=inside',
                     '--route', '198.51.100.0/24=outside', '--report-seconds', '1'] + extra)


def ttl_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 64)
    sock.setsockopt(socket.IPPROTO_IP, 12, 1)  # Linux IP_RECVTTL
    sock.settimeout(3)
    return sock


def recv(sock):
    data, anc, flags, peer = sock.recvmsg(2048, 256)
    assert not flags, ('truncated packet or ancillary data', flags)
    ttls = [struct.unpack('i', value)[0] for level, kind, value in anc
            if level == socket.IPPROTO_IP and kind == socket.IP_TTL]
    assert ttls == [63], ('expected TTL decremented exactly once', ttls)
    return data, peer, ttls[0]


def serve(ready, evidence):
    with ttl_socket() as sock, open(evidence, 'a', buffering=1) as log:
        sock.bind(('198.51.100.2', 9000))
        Path(ready).touch()
        while True:
            try:
                data, peer, ttl = recv(sock)
            except socket.timeout:
                continue
            log.write(json.dumps(dict(peer=peer, ttl=ttl, payload=data.decode())) + '\n')
            assert peer == ('198.51.100.1', 40000), ('unexpected SNAT tuple', peer)
            assert data == b'controlled-real-udp-positive'
            # A packet from a different remote port must not reach the client.
            with ttl_socket() as wrong_remote:
                wrong_remote.bind(('198.51.100.2', 9001))
                wrong_remote.sendto(b'wrong-remote-must-be-filtered', peer)
            sock.sendto(data, peer)


def client(mode):
    with ttl_socket() as sock:
        sock.bind(('10.0.0.2', 12345))
        payload = ('controlled-real-udp-' + mode).encode()
        sock.sendto(payload, ('198.51.100.2', 9000))
        if mode == 'negative':
            try:
                sock.recvmsg(2048, 256)
            except socket.timeout:
                print(json.dumps(dict(mode=mode, timed_out=True)))
                return
            raise AssertionError('packet delivered after router stopped')
        data, peer, ttl = recv(sock)
        assert data == payload and peer == ('198.51.100.2', 9000), (data, peer)
        print(json.dumps(dict(mode=mode, peer=peer, ttl=ttl, payload=data.decode())))


def ready(marker, router_log, router_pid, server_pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for pid in (router_pid, server_pid):
            os.kill(int(pid), 0)
        if Path(marker).exists() and 'forwarding ready' in Path(router_log).read_text():
            return
        time.sleep(0.025)
    raise AssertionError('server/router startup deadline exceeded')


# Keep this schema aligned with src/linux.rs report() and core DROP_REASONS.
DROP_REASONS = ('Malformed', 'Options', 'Fragment', 'Protocol', 'Checksum',
                'Address', 'Ttl', 'Mtu', 'Route', 'Policy', 'Filter', 'Capacity', 'Clock')
COUNTER_KEYS = {'received', 'forwarded', 'active', 'expired', 'io_drops', *DROP_REASONS}


def final_counters(log):
    """Validate the final report, never a matching substring in an older report.

    Protocol counts unsupported packets (including incidental guest IPv6); it
    cannot identify IPv6 specifically. All other unexpected drops fail closed.
    """
    lines = log.splitlines()
    assert lines, 'missing final counters'
    fields = lines[-1].split()
    assert fields and all(re.fullmatch(r'[A-Za-z_]+=[0-9]+', field)
                          for field in fields), ('invalid final counters', lines[-1])
    counters = dict(field.split('=') for field in fields)
    assert len(fields) == len(counters), 'duplicate counter'
    assert counters.keys() == COUNTER_KEYS, ('unexpected counter schema', counters)
    counters = {key: int(value) for key, value in counters.items()}
    for key, expected in dict(forwarded=2, Filter=1, active=1, expired=0, io_drops=0).items():
        assert counters[key] == expected, (key, counters[key], expected)
    for reason in DROP_REASONS:
        if reason not in ('Protocol', 'Filter'):
            assert counters[reason] == 0, ('unexpected data-plane drop', reason, counters[reason])
    assert counters['received'] == counters['forwarded'] + sum(
        counters[reason] for reason in DROP_REASONS), ('unaccounted received packets', counters)
    return counters


def verify(directory):
    directory = Path(directory)
    observations = [json.loads(line) for line in (directory / 'server.jsonl').read_text().splitlines()]
    assert len(observations) == 1, observations
    assert observations[0]['peer'] == ['198.51.100.1', 40000]
    assert observations[0]['ttl'] == 63
    assert json.loads((directory / 'client-positive.json').read_text())['ttl'] == 63
    assert json.loads((directory / 'client-negative.json').read_text())['timed_out']
    log = (directory / 'router.log').read_text()
    counters = final_counters(log)
    (directory / 'PASS.json').write_text(json.dumps(dict(real_udp=True, snat=True, ttl=True, wrong_remote_filtered=True,
                                                       stopped_router_breaks_path=True, counters=counters), indent=2) + '\n')


if __name__ == '__main__':
    actions = dict(launch=launch, server=serve, client=client, ready=ready, verify=verify)
    actions[sys.argv[1]](*sys.argv[2:])
