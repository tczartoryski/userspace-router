#!/usr/bin/env python3
"""Bounded isolated Linux evidence collection; no host network configuration."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

from traffic import launch, ready, ttl_socket, recv, DROP_REASONS, COUNTER_KEYS

LIMIT = 65536
ROOT = Path(__file__).resolve().parent.parent
PAYLOADS = ('nat-story-one', 'nat-story-two', 'nat-story-blocked',
            'nat-story-stopped', 'nat-story-recovered')


def load(path):
    with open(path, 'rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('evidence exceeds bound')
    return json.loads(raw)


def save(path, data):
    raw = json.dumps(data, sort_keys=True, indent=2) + '\n'
    if len(raw.encode()) > LIMIT:
        raise ValueError('evidence exceeds bound')
    temporary = Path(str(path) + '.partial')
    temporary.write_text(raw)
    temporary.replace(path)


def endpoint(directory):
    directory = Path(directory)
    sockets = []
    try:
        for address in ('198.51.100.2', '198.51.100.3'):
            sock = ttl_socket()
            sock.bind((address, 9000))
            sock.setblocking(False)
            sockets.append(sock)
        (directory / 'server.ready').touch()
        observations = []
        deadline = time.monotonic() + 35
        import select
        while time.monotonic() < deadline:
            for sock in select.select(sockets, [], [], .1)[0]:
                data, peer, ttl = recv(sock)
                if data.decode('ascii') not in PAYLOADS or len(observations) >= 8:
                    raise ValueError('unexpected endpoint traffic')
                observations.append(dict(local=list(sock.getsockname()), peer=list(peer),
                                         payload=data.decode('ascii'), ttl=ttl))
                save(directory / 'server.json', observations)
                sock.sendto(data, peer)
    finally:
        for sock in sockets:
            sock.close()


def capture(interface, directory):
    """AF_PACKET/SOCK_DGRAM receives actual IP datagrams, never injects packets."""
    directory = Path(directory)
    with socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(0x0003)) as sock:
        sock.bind((interface, 0))
        sock.settimeout(.1)
        (directory / (interface + '.ready')).touch()
        packets = []
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                packet, address = sock.recvfrom(2048)
            except socket.timeout:
                continue
            if len(packet) < 28 or packet[0] != 0x45 or packet[9] != 17:
                continue
            length = struct.unpack('!H', packet[2:4])[0]
            udp_length = struct.unpack('!H', packet[24:26])[0]
            if length != len(packet) or udp_length != length - 20:
                raise ValueError('truncated capture')
            payload = packet[28:].decode('ascii', errors='replace')
            if payload not in PAYLOADS:
                continue
            if len(packets) >= 24:
                raise ValueError('capture bound exceeded')
            src, dst = struct.unpack('!HH', packet[20:24])
            packets.append(dict(src=[socket.inet_ntoa(packet[12:16]), src],
                                dst=[socket.inet_ntoa(packet[16:20]), dst],
                                ttl=packet[8], payload=payload,
                                direction='outgoing' if address[2] == 4 else 'incoming'))
            save(directory / (interface + '.json'), packets)


def exchange(address, payload, destination='198.51.100.2', timeout=False):
    with ttl_socket() as sock:
        sock.settimeout(.7)
        sock.bind((address, 12345))
        sock.sendto(payload.encode(), (destination, 9000))
        result = dict(local=list(sock.getsockname()), remote=[destination, 9000], payload=payload)
        try:
            data, peer, ttl = recv(sock)
        except socket.timeout:
            if not timeout:
                raise
            result['timed_out'] = True
        else:
            if timeout or data != payload.encode():
                raise ValueError('unexpected delivery')
            result.update(peer=list(peer), reply=data.decode(), ttl=ttl, timed_out=False)
        return result


def check(condition):
    if not condition:
        raise ValueError('scenario evidence rejected')


def verify(d):
    """Strict sanitized schema plus cross-observation consistency; not authentication."""
    check(set(d) == {'schema', 'kind', 'clients', 'server', 'inside', 'outside', 'runs'})
    check(d['schema'] == 1 and d['kind'] == 'recorded-real-linux-udp')
    clients = d['clients']
    check(len(clients) == 5)
    for i, c in enumerate(clients):
        failed = i in (2, 3)
        keys = {'local', 'remote', 'payload', 'timed_out'}
        if not failed:
            keys |= {'peer', 'reply', 'ttl'}
        check(set(c) == keys)
        check(c['local'] == ['10.0.0.3' if i == 1 else '10.0.0.2', 12345])
        check(c['remote'] == ['198.51.100.3' if i == 2 else '198.51.100.2', 9000])
        check(c['payload'] == PAYLOADS[i] and c['timed_out'] is failed)
        if not failed:
            check(c['peer'] == c['remote'] and c['reply'] == c['payload'] and c['ttl'] == 63)
    check(len(d['server']) == 3)
    ports = []
    for s, i in zip(d['server'], (0, 1, 4)):
        check(set(s) == {'local', 'peer', 'payload', 'ttl'})
        check(s['local'] == ['198.51.100.2', 9000] and s['ttl'] == 63)
        check(s['payload'] == PAYLOADS[i] and s['peer'][0] == '198.51.100.1')
        check(type(s['peer'][1]) is int and 40000 <= s['peer'][1] <= 40002)
        ports.append(s['peer'][1])
    check(ports[0] != ports[1] and ports[2] == ports[0])
    for side in ('inside', 'outside'):
        packets = d[side]
        expected = []
        for j, i in enumerate((0, 1, 4)):
            local = clients[i]['local'] if side == 'inside' else ['198.51.100.1', ports[j]]
            remote = ['198.51.100.2', 9000]
            expected.extend([dict(src=local, dst=remote, payload=PAYLOADS[i],
                                  ttl=64 if side == 'inside' else 63, direction='outgoing' if side == 'inside' else 'incoming'),
                             dict(src=remote, dst=local, payload=PAYLOADS[i],
                                  ttl=63 if side == 'inside' else 64, direction='incoming' if side == 'inside' else 'outgoing')])
        if side == 'inside':
            for i in (2, 3):
                expected.append(dict(src=clients[i]['local'], dst=clients[i]['remote'],
                                     payload=PAYLOADS[i], ttl=64, direction='outgoing'))
        check(len(packets) == len(expected))
        check(sorted(map(lambda x: json.dumps(x, sort_keys=True), packets)) ==
              sorted(map(lambda x: json.dumps(x, sort_keys=True), expected)))
    check(len(d['runs']) == 2)
    for run, forwarded, policy, active in zip(d['runs'], (4, 2), (1, 0), (2, 1)):
        check(set(run) == COUNTER_KEYS)
        check(all(type(v) is int and 0 <= v <= 1000 for v in run.values()))
        check(run['forwarded'] == forwarded and run['Policy'] == policy and run['active'] == active)
        check(run['expired'] == 0 and run['io_drops'] == 0)
        check(all(run[r] == 0 for r in DROP_REASONS if r not in ('Policy', 'Protocol')))
        check(run['received'] == forwarded + sum(run[r] for r in DROP_REASONS))
    return d


def counters(path):
    fields = Path(path).read_text().splitlines()[-1].split()
    result = dict(item.split('=') for item in fields)
    check(len(fields) == len(result) and set(result) == COUNTER_KEYS)
    return {k: int(v) for k, v in result.items()}


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
    else:
        child.wait(timeout=2)


def collect(binary, output):
    check(sys.platform == 'linux' and os.geteuid() == 0 and
          os.environ.get('UDP_ROUTER_ISOLATED_LINUX') == 'YES')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    binary = str(Path(binary).resolve(strict=True))
    children, namespaces = [], []
    handles = []
    def command(*args):
        return subprocess.run(list(args), check=True, timeout=4, capture_output=True)
    def spawn(ns, *args, log=None, env=None):
        if log:
            handle = open(log, 'w'); handles.append(handle)
        else:
            handle = subprocess.DEVNULL
        child = subprocess.Popen(['ip', 'netns', 'exec', ns, *args], stdout=subprocess.DEVNULL,
                                 stderr=handle, env=env)
        children.append(child)
        return child
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    with tempfile.TemporaryDirectory(prefix='nat-story-') as tmp:
        directory = Path(tmp)
        try:
            tag = 'ns-story-' + str(os.getpid())
            client, server, router = [tag + '-' + suffix for suffix in ('c', 's', 'r')]
            for ns in (client, server, router):
                command('ip', 'netns', 'add', ns); namespaces.append(ns)
                command('ip', '-n', ns, 'link', 'set', 'lo', 'up')
                command('ip', 'netns', 'exec', ns, 'sysctl', '-q', '-w', 'net.ipv4.ip_forward=0',
                        'net.ipv4.conf.all.rp_filter=0', 'net.ipv4.conf.default.rp_filter=0')
            for ns, dev, addresses in ((client, 'tun-in', ('10.0.0.2', '10.0.0.3')),
                                       (server, 'tun-out', ('198.51.100.2', '198.51.100.3'))):
                command('ip', '-n', ns, 'tuntap', 'add', 'dev', dev, 'mode', 'tun')
                for address in addresses:
                    command('ip', '-n', ns, 'addr', 'add', address + '/32', 'dev', dev)
                command('ip', '-n', ns, 'link', 'set', dev, 'mtu', '1500', 'up')
            command('ip', '-n', client, 'route', 'add', '198.51.100.0/24', 'dev', 'tun-in', 'src', '10.0.0.2')
            command('ip', '-n', server, 'route', 'add', '198.51.100.1/32', 'dev', 'tun-out', 'src', '198.51.100.2')
            script = str(Path(__file__).resolve())
            endpoint_process = spawn(server, sys.executable, '-B', script, 'endpoint', tmp)
            captures = [spawn(ns, sys.executable, '-B', script, 'capture', dev, tmp)
                        for ns, dev in ((client, 'tun-in'), (server, 'tun-out'))]
            deadline = time.monotonic() + 4
            while not all((directory / name).exists() for name in ('server.ready', 'tun-in.ready', 'tun-out.ready')):
                check(time.monotonic() < deadline and all(p.poll() is None for p in children))
                time.sleep(.02)
            env = dict(os.environ, UDP_ROUTER_EXTRA_ARGS='["--route","198.51.100.3/32=inside"]')
            def start(index):
                log = directory / ('router-' + str(index) + '.log')
                process = spawn(router, sys.executable, '-B', script, 'launch', client, server, binary, log=log, env=env)
                ready(str(directory / 'server.ready'), str(log), process.pid, endpoint_process.pid)
                return process, log
            def send(index, address='10.0.0.2', destination='198.51.100.2', failed=False):
                result = command('ip', 'netns', 'exec', client, sys.executable, '-B', script,
                                 'exchange', address, PAYLOADS[index], destination, str(int(failed)))
                return json.loads(result.stdout)
            first, log1 = start(1)
            observations = [send(0), send(1, '10.0.0.3'), send(2, destination='198.51.100.3', failed=True)]
            stop(first); check(first.returncode == 0)
            observations.append(send(3, failed=True))
            second, log2 = start(2)  # distinct empty ready log, fresh process
            observations.append(send(4))
            stop(second); check(second.returncode == 0)
            time.sleep(.15)
            check(all(p.poll() is None for p in [endpoint_process, *captures]))
            for p in [endpoint_process, *captures]:
                stop(p)
            data = dict(schema=1, kind='recorded-real-linux-udp', clients=observations,
                        server=load(directory / 'server.json'), inside=load(directory / 'tun-in.json'),
                        outside=load(directory / 'tun-out.json'), runs=[counters(log1), counters(log2)])
            verify(data)
            save(output, data)
        finally:
            for sig in previous:
                signal.signal(sig, signal.SIG_IGN)
            try:
                errors = []
                for child in reversed(children):
                    try:
                        stop(child)
                    except (OSError, subprocess.SubprocessError) as error:
                        errors.append(error)
                for handle in handles:
                    handle.close()
                for ns in reversed(namespaces):
                    try:
                        command('ip', 'netns', 'del', ns)
                    except (OSError, subprocess.SubprocessError) as error:
                        errors.append(error)
                if errors:
                    raise RuntimeError('owned resource cleanup failed') from errors[0]
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)


def main():
    args = sys.argv[1:]
    if args[0] == 'launch':
        launch(*args[1:])
    elif args[0] == 'endpoint':
        endpoint(args[1])
    elif args[0] == 'capture':
        capture(*args[1:])
    elif args[0] == 'exchange':
        print(json.dumps(exchange(*args[1:4], timeout=bool(int(args[4])))))
    elif args[0] == 'verify':
        verify(load(args[1])); print('PASS: four real UDP scenario checks')
    elif args[0] == 'collect':
        collect(*args[1:])
    else:
        raise ValueError('unknown command')


if __name__ == '__main__':
    main()
