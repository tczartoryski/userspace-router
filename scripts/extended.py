#!/usr/bin/env python3
"""Real Linux kernel UDP endpoints: never generates raw/synthetic IP packets."""
import json
from pathlib import Path
import socket
import re
import sys
import time
from traffic import ttl_socket, recv, DROP_REASONS


def server(ready, log):
    with ttl_socket() as sock, open(log, 'a', buffering=1) as out:
        sock.bind(('198.51.100.2', 9000))
        Path(ready).touch()
        while True:
            try:
                data, peer, ttl = recv(sock)
            except socket.timeout:
                continue
            out.write(json.dumps(dict(payload=data.decode(), peer=peer, ttl=ttl)) + '\n')
            if data == b'expire':
                time.sleep(4)  # same exact remote tuple, but mapping must have expired
                sock.sendto(b'late', peer)
            else:
                with ttl_socket() as wrong:
                    wrong.bind(('198.51.100.2', 9001))
                    wrong.sendto(b'wrong', peer)
                sock.sendto(data, peer)


def exchange(sock, payload):
    sock.sendto(payload, ('198.51.100.2', 9000))
    data, peer, _ = recv(sock)
    assert data == payload and peer == ('198.51.100.2', 9000), (data, peer)


def client(directory):
    sockets = []
    try:
        for n in (2, 3, 4):
            sock = ttl_socket(); sock.settimeout(.6)
            sock.bind((f'10.0.0.{n}', 12345)); sockets.append(sock)
        exchange(sockets[0], b'client-a')
        exchange(sockets[1], b'client-b')
        sockets[2].sendto(b'exhausted', ('198.51.100.2', 9000))
        try:
            sockets[2].recv(2048)
            raise AssertionError('exhaustion delivered')
        except socket.timeout:
            pass
        # A /32 inside route overrides the outside /24; packet must be rejected.
        sockets[0].sendto(b'route-blocked', ('198.51.100.3', 9000))
        time.sleep(4)
        sockets[0].sendto(b'expire', ('198.51.100.2', 9000))
        sockets[0].settimeout(5)
        try:
            sockets[0].recv(2048)
            raise AssertionError('late reply delivered after expiry')
        except socket.timeout:
            pass
        exchange(sockets[2], b'reallocated')
        Path(directory, 'extended-client.json').write_text(json.dumps(dict(real_kernel_udp=True, same_source_port=True, exhausted_timeout=True, expired_reply_timeout=True, reallocated=True)))
    finally:
        for sock in sockets:
            sock.close()


def verify(directory):
    root = Path(directory)
    observations = [json.loads(line) for line in (root/'server.jsonl').read_text().splitlines()]
    assert [o['payload'] for o in observations] == ['client-a', 'client-b', 'expire', 'reallocated'], observations
    assert observations[0]['peer'][1] != observations[1]['peer'][1]
    assert all(o['peer'][0] == '198.51.100.1' and o['ttl'] == 63 for o in observations)
    tokens = (root/'router.log').read_text().splitlines()[-1].split()
    assert tokens and all(re.fullmatch(r'[A-Za-z_]+=[0-9]+', f) for f in tokens), tokens
    fields = dict(f.split('=') for f in tokens)
    assert len(fields) == len(tokens) and fields.keys() == {'received','forwarded','active','expired','io_drops',*DROP_REASONS}, fields
    c = {k:int(v) for k,v in fields.items()}
    assert c['Capacity'] == 1 and c['Policy'] == 1 and c['Filter'] == 4, c
    assert c['expired'] == 3 and c['active'] == 1 and c['forwarded'] == 7 and c['io_drops'] == 0, c
    assert all(c[r] == 0 for r in DROP_REASONS if r not in ('Capacity','Policy','Filter','Protocol')), c
    assert c['received'] == c['forwarded'] + sum(c[r] for r in DROP_REASONS)
    assert json.loads((root/'client-negative.json').read_text())['timed_out']
    (root/'PASS.json').write_text(json.dumps(dict(real_kernel_udp=True, same_port_distinct_clients=True, longest_prefix=True, expiry=True, exhaustion=True, stopped_router_breaks_path=True, counters=c), indent=2)+'\n')
    print('PASS extended real UDP: distinct clients, exhaustion, idle expiry, longest-prefix policy, stopped-router control')


def pulse_exchange(sock, budget=5.0, attempt_timeout=0.5):
    """Bounded real exchange retries on one tuple; validation errors fail at once."""
    deadline = time.monotonic() + budget
    attempts = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f'retained UDP exchange deadline exceeded after {attempts} attempts')
        sock.settimeout(min(attempt_timeout, remaining))
        attempts += 1
        try:
            exchange(sock, b'live-demo')
        except socket.timeout:
            print(f'retained UDP attempt {attempts} timed out', file=sys.stderr, flush=True)
            continue
        return


def pulse():
    with ttl_socket() as sock:
        sock.bind(('10.0.0.2', 12345))
        pulse_exchange(sock)


if __name__ == '__main__':
    dict(server=server, client=client, verify=verify, pulse=pulse)[sys.argv[1]](*sys.argv[2:])
