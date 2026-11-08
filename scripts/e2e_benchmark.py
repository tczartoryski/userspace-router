#!/usr/bin/env python3
"""Opt-in disposable Linux E2E experiments; never configures host networking."""
import argparse
import errno
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import uuid

from traffic import launch, DROP_REASONS, COUNTER_KEYS

SIZES = (64, 128, 512, 1400)
MODES = ('cold', 'warm')
REMOTE = ('198.51.100.2', 9000)
SCRIPT = str(Path(__file__).resolve())


def check(value, message='experiment evidence rejected'):
    if not value:
        raise ValueError(message)


def save(path, data):
    Path(path).write_text(json.dumps(data, allow_nan=False, sort_keys=True)+'\n')


def load(path):
    raw = Path(path).read_bytes()
    check(len(raw) <= 2_000_000, 'artifact bound')
    return json.loads(raw)


def payload(size, stage, flow, seq):
    head = struct.pack('!4sBHI', b'URv2', stage, flow, seq)
    return head + bytes([(seq+flow+stage) % 251]) * (size-28-len(head))


def decode(data, size, flows):
    check(len(data) == size-28, 'payload size')
    magic, stage, flow, seq = struct.unpack('!4sBHI', data[:11])
    check(magic == b'URv2' and stage in (0, 1, 2) and flow < flows, 'payload header')
    check(data == payload(size, stage, flow, seq), 'payload corruption')
    return stage, flow, seq


def udp(address):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 64)
    sock.setsockopt(socket.IPPROTO_IP, 12, 1)  # Linux IP_RECVTTL
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    sock.bind(address)
    sock.setblocking(False)
    return sock


def receive(sock):
    data, anc, flags, peer = sock.recvmsg(2048, 256)
    after = time.monotonic_ns()
    check(not flags, 'truncated UDP/ancillary data')
    ttl = [struct.unpack('i', v)[0] for level, kind, v in anc
           if level == socket.IPPROTO_IP and kind == socket.IP_TTL]
    check(ttl == [63], 'TTL must be 63')
    return data, peer, after


def quantiles(samples):
    if not samples:
        return dict(p50_ns=None, p95_ns=None, p99_ns=None, samples=0)
    values = sorted(samples)
    return dict(zip(('p50_ns', 'p95_ns', 'p99_ns'),
                    (values[math.ceil(len(values)*p/100)-1] for p in (50,95,99))), samples=len(values))


def echo(directory, size, flows, count):
    root = Path(directory)
    stop = False
    def stopped(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, stopped)
    seen, duplicates, reordered, max_seq = set(), 0, 0, -1
    ports, port_owners, seed_seen = {}, {}, set()
    deadline = time.monotonic()+170
    with udp(REMOTE) as sock, selectors.DefaultSelector() as poll:
        poll.register(sock, selectors.EVENT_READ)
        save(root/'server.ready', {'ready': True})
        while not stop and time.monotonic() < deadline:
            for _, _ in poll.select(.02):
                for _ in range(128):
                    try:
                        data, peer, _ = receive(sock)
                    except BlockingIOError:
                        break
                    stage, flow, seq = decode(data, size, flows)
                    check(peer[0] == '198.51.100.1' and 40000 <= peer[1] <= 49999, 'SNAT endpoint')
                    check(flow not in ports or ports[flow] == peer[1], 'mapping changed')
                    check(peer[1] not in port_owners or port_owners[peer[1]] == flow, 'SNAT port collision')
                    port_owners[peer[1]] = flow
                    ports[flow] = peer[1]
                    if stage == 1:
                        check(seq < count and flow == seq % flows, 'unexpected sequence')
                        if seq in seen:
                            duplicates += 1
                        else:
                            reordered += int(seq < max_seq)
                            max_seq = max(seq, max_seq)
                            seen.add(seq)
                    elif stage == 0:
                        check(seq == flow, 'seed sequence')
                        seed_seen.add(flow)
                    # A bounded send failure is a loss, not a made-up delivery.
                    try:
                        sock.sendto(data, peer)
                    except BlockingIOError:
                        pass
    check(stop, 'server deadline')
    save(root/'server.json', dict(server_seen=len(seen), server_sequences=sorted(seen),
                                 server_duplicates=duplicates, server_out_of_order=reordered,
                                 distinct_nat_ports=len(set(ports.values())), seed_seen=len(seed_seen)))


def wait_file(path, seconds, children=()):
    end = time.monotonic()+seconds
    while not Path(path).exists():
        check(all(p.poll() is None for p in children), 'child exited before readiness')
        check(time.monotonic() < end, 'readiness deadline')
        time.sleep(.01)


def client(directory, size, flows, count, window, mode):
    root = Path(directory)
    sockets = []
    try:
        with selectors.DefaultSelector() as poll:
            for flow in range(flows):
                sock = udp(('10.0.0.2', 12000+flow))
                sockets.append(sock)
                poll.register(sock, selectors.EVENT_READ, flow)
            def exchange(stage, total):
                pending, sent, received, latency = {}, set(), set(), []
                attempted = duplicates = reordered = 0
                maximum = -1
                start = time.monotonic_ns()
                cpu = time.process_time_ns()
                end = time.monotonic()+8
                while attempted < total or pending:
                    check(time.monotonic() < end, 'generator 8 second deadline')
                    while attempted < total and len(pending) < window:
                        seq = attempted
                        flow = seq % flows
                        data = payload(size, stage, flow, seq)
                        t = time.monotonic_ns()  # RTT starts immediately before sendto.
                        try:
                            n = sockets[flow].sendto(data, REMOTE)
                            check(n == len(data), 'short UDP send')
                        except BlockingIOError:
                            pass
                        else:
                            sent.add(seq)
                            pending[seq] = t
                            timestamps[seq] = t
                        attempted += 1
                    for key, _ in poll.select(.005):
                        for _ in range(128):
                            try:
                                data, peer, after = receive(key.fileobj)
                            except BlockingIOError:
                                break
                            got_stage, flow, seq = decode(data, size, flows)
                            check(peer == REMOTE and flow == key.data, 'reply endpoint/flow')
                            check(got_stage == stage and seq in sent and flow == seq % flows, 'reply sequence/stage')
                            if seq in received:
                                duplicates += 1
                            else:
                                # Late replies after the per-packet deadline still count as delivered.
                                check(seq in timestamps, 'missing send timestamp')
                                latency.append(after-timestamps[seq])
                                received.add(seq)
                                reordered += int(seq < maximum)
                                maximum = max(maximum, seq)
                            pending.pop(seq, None)
                    now = time.monotonic_ns()
                    # Preserve timestamps after timeout for validation and late RTTs.
                    for seq in list(pending):
                        if now-pending[seq] >= 500_000_000:
                            del pending[seq]
                # Include a bounded final drain to observe late/duplicate responses.
                drain = time.monotonic()+(.05 if len(received) < len(sent) else 0)
                while time.monotonic() < drain:
                    for key, _ in poll.select(.005):
                        for _ in range(128):
                            try:
                                data, peer, after = receive(key.fileobj)
                            except BlockingIOError:
                                break
                            st, flow, seq = decode(data,size,flows)
                            check(peer == REMOTE and st == stage and flow == key.data and seq in sent and flow == seq % flows, 'drain evidence')
                            if seq in received:
                                duplicates += 1
                            else:
                                received.add(seq); latency.append(after-timestamps[seq])
                                reordered += int(seq < maximum); maximum = max(maximum,seq)
                wall = time.monotonic_ns()-start
                return dict(attempted=attempted, sent=len(sent), received=len(received),
                            dropped=len(sent)-len(received), send_failed=attempted-len(sent),
                            duplicates=duplicates, out_of_order=reordered, wall_ns=wall,
                            generator_cpu_ns=time.process_time_ns()-cpu,
                            received_sequences=sorted(received), sent_sequences=sorted(sent),
                            rtt=quantiles(latency))
            # Sent timestamps are recorded before the receiver can consume each reply.
            timestamps = {}
            if mode == 'warm':
                seeded = exchange(0, flows)
                check(seeded['received'] == flows and not seeded['duplicates'], 'warm seed loss')
            save(root/'client.ready', {'ready': True})
            wait_file(root/'go', 5)
            timestamps.clear()
            result = exchange(1, count)
            calibration = []
            for _ in range(512):
                t = time.monotonic_ns(); calibration.append(time.monotonic_ns()-t)
            result['clock_calibration'] = quantiles(calibration)
            save(root/'client.json', result)
    finally:
        for sock in sockets:
            sock.close()


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(timeout=2)
    else:
        child.wait(timeout=2)


class Lab:
    """Every mutation is scoped to a namespace created successfully by this object."""
    def __init__(self, directory, budget):
        self.root = Path(directory)
        self.owned, self.children, self.handles = [], [], []
        self.deadline = budget
        self.names = ['urb-'+uuid.uuid4().hex[:10]+'-'+s for s in ('c','r','s')]
        self.c, self.r, self.s = self.names

    def command(self, *args, cleanup=False):
        remaining = self.deadline-time.monotonic()
        check(cleanup or remaining > 0, '180 second job budget')
        return subprocess.run(list(args), timeout=4 if cleanup else min(4,remaining),
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def ns(self, ns, *args):
        check(ns in self.owned, 'namespace not owned')
        return self.command('ip','netns','exec',ns,*args)

    def spawn(self, ns, args, name, env=None):
        check(ns in self.owned, 'namespace not owned')
        handle = open(self.root/(name+'.log'),'wb'); self.handles.append(handle)
        p = subprocess.Popen(['ip','netns','exec',ns,*args], stdout=handle, stderr=handle, env=env)
        self.children.append(p)
        return p

    def setup(self, backend):
        for ns in self.names:
            self.command('ip','netns','add',ns)
            self.owned.append(ns)
            self.ns(ns,'ip','link','set','lo','up')
            self.ns(ns,'sysctl','-q','-w','net.ipv4.conf.all.rp_filter=0',
                    'net.ipv4.conf.default.rp_filter=0','net.ipv4.ip_forward=0')
        if backend == 'user':
            for ns,dev,addr in ((self.c,'tun-in','10.0.0.2'),(self.s,'tun-out','198.51.100.2')):
                self.ns(ns,'ip','tuntap','add','dev',dev,'mode','tun')
                self.ns(ns,'ip','addr','add',addr+'/32','dev',dev)
                self.ns(ns,'ip','link','set',dev,'mtu','1500','up')
            self.ns(self.c,'ip','route','add','198.51.100.0/24','dev','tun-in','src','10.0.0.2')
            self.ns(self.s,'ip','route','add','198.51.100.1/32','dev','tun-out','src','198.51.100.2')
        else:
            # Create both ends inside owned namespaces; no transient host veth.
            for ns,dev,other in ((self.c,'cin','rin'),(self.s,'sout','rout')):
                self.ns(ns,'ip','link','add',dev,'type','veth','peer','name',other)
                self.ns(ns,'ip','link','set',other,'netns',self.r)
            for ns,dev,addr in ((self.c,'cin','10.0.0.2/24'),(self.r,'rin','10.0.0.1/24'),
                                (self.r,'rout','198.51.100.1/24'),(self.s,'sout','198.51.100.2/24')):
                self.ns(ns,'ip','addr','add',addr,'dev',dev)
                self.ns(ns,'ip','link','set',dev,'mtu','1500','up')
            self.ns(self.c,'ip','route','add','198.51.100.0/24','via','10.0.0.1')
            self.ns(self.s,'ip','route','add','10.0.0.0/24','via','198.51.100.1')
            self.ns(self.r,'iptables','-t','nat','-A','POSTROUTING','-p','udp','-s','10.0.0.0/24',
                    '-d','198.51.100.2','-j','SNAT','--to-source','198.51.100.1:40000-49999')
            self.ns(self.r,'sysctl','-q','-w','net.ipv4.ip_forward=1')

    def cleanup(self):
        errors = []
        for p in reversed(self.children):
            try:
                stop(p)
            except (OSError, subprocess.SubprocessError) as error:
                errors.append(type(error).__name__)
        for h in self.handles:
            h.close()
        for ns in reversed(self.owned):
            try:
                self.command('ip','netns','del',ns,cleanup=True)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                errors.append(type(error).__name__)
        check(not errors, 'owned cleanup failed: '+','.join(errors))


def proc(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return dict(ticks=int(fields[11])+int(fields[12]), rss_bytes=int(fields[21])*os.sysconf('SC_PAGE_SIZE'))


def guest_cpu():
    values = list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return dict(total=sum(values), idle=values[3]+values[4])


def counters(path):
    fields = Path(path).read_text().splitlines()[-1].split()
    check(fields and all(re.fullmatch(r'[A-Za-z_]+=[0-9]+',s) for s in fields), 'final router counters')
    result = dict(s.split('=') for s in fields)
    check(len(result) == len(fields) and set(result) == COUNTER_KEYS, 'counter schema')
    result = {k:int(v) for k,v in result.items()}
    check(result['received'] == result['forwarded']+sum(result[k] for k in DROP_REASONS), 'counter conservation')
    check(all(result[k] == 0 for k in DROP_REASONS if k != 'Protocol'), 'unexpected core drops')
    return result


def profile_start(lab, pid, mode):
    if mode == 'none':
        return []
    commands = ([['perf','record','-e','cpu-clock','-F','999','-g','-p',str(pid),'-o',str(lab.root/'perf.data')],
                 ['perf','stat','-x,','-e','task-clock,context-switches,page-faults','-p',str(pid),'-o',str(lab.root/'perf-stat.txt')]]
                if mode == 'perf' else [['strace','-c','-p',str(pid),'-o',str(lab.root/'strace.txt')]])
    children = [lab.spawn(lab.r,args,'profiler-'+str(i)) for i,args in enumerate(commands)]
    time.sleep(.15)
    check(all(p.poll() is None for p in children), 'profiler attach failed')
    return children


def profile_finish(lab, children, mode):
    for p in children:
        p.send_signal(signal.SIGINT)
        p.wait(timeout=3)
    if mode == 'none':
        return None
    if mode == 'strace':
        raw = (lab.root/'strace.txt').read_text()
        rows = [line.split() for line in raw.splitlines()
                if re.fullmatch(r'\s*[0-9.]+\s+[0-9.]+\s+\d+\s+\d+(?:\s+\d+)?\s+[a-zA-Z0-9_]+\s*',line)]
        check(rows, 'empty strace summary')
        return dict(tool='strace-c', rows=rows)
    report = lab.ns(lab.r,'perf','report','--stdio','--no-children','--sort','symbol',
                    '--percent-limit','1','-i',str(lab.root/'perf.data')).stdout.decode(errors='replace')
    symbols = []
    for line in report.splitlines():
        match = re.search(r'([0-9.]+)%\s+\[.\]\s+(.+)',line)
        if match and re.fullmatch(r'[A-Za-z0-9_:<>~{}()+,*& .\[\]-]{1,200}',match[2]):
            symbols.append(dict(percent=float(match[1]),symbol=match[2]))
    stats = []
    for line in (lab.root/'perf-stat.txt').read_text().splitlines():
        fields = line.split(',')
        if len(fields) >= 3 and fields[2] in ('task-clock','context-switches','page-faults'):
            check(re.fullmatch(r'[0-9.]+',fields[0]), 'unsupported software perf event')
            stats.append(dict(event=fields[2],value=float(fields[0]),unit=fields[1]))
    check(symbols and len(stats) == 3, 'empty software perf summary')
    return dict(tool='perf-software', frequency_hz=999, symbols=symbols[:40], stats=stats)


def validate_exchange(client_data, server_data, count, flows, mode):
    """Cross-check independent endpoint receipts before discarding private sequences."""
    c, s = client_data, server_data
    for source, keys in ((c, ('attempted','sent','received','dropped','send_failed','duplicates','out_of_order',
                              'wall_ns','generator_cpu_ns')),
                         (s, ('server_seen','server_duplicates','server_out_of_order','distinct_nat_ports','seed_seen'))):
        check(all(type(source[k]) is int and 0 <= source[k] <= 2**63-1 for k in keys), 'invalid metric')
    sets = []
    for source,key in ((c,'sent_sequences'),(c,'received_sequences'),(s,'server_sequences')):
        values = source[key]
        check(type(values) is list and all(type(v) is int and 0 <= v < count for v in values), 'sequence range')
        check(len(values) == len(set(values)), 'duplicate receipt evidence')
        sets.append(set(values))
    sent, received, seen = sets
    check(received <= seen <= sent, 'independent endpoint mismatch')
    check(c['attempted'] == count and c['sent'] == len(sent) and c['received'] == len(received), 'client counts')
    check(c['dropped'] == len(sent)-len(received) and c['send_failed'] == count-len(sent), 'loss accounting')
    check(s['server_seen'] == len(seen) and 0 < s['distinct_nat_ports'] <= flows, 'server counts')
    check(s['seed_seen'] == (flows if mode == 'warm' else 0), 'seed accounting')
    if mode == 'warm':
        check(s['distinct_nat_ports'] == flows, 'warm mapping coverage')
    check(c['received'] > 0 and c['wall_ns'] > 0, 'no deliveries')
    q = c['rtt']
    check(q['samples'] == len(received), 'RTT sample count')
    check(all(type(q[k]) is int and 0 <= q[k] <= c['wall_ns'] for k in ('p50_ns','p95_ns','p99_ns')), 'RTT bounds')
    check(q['p50_ns'] <= q['p95_ns'] <= q['p99_ns'], 'RTT ordering')
    check(c['out_of_order'] <= max(0,c['received']-1) and
          s['server_out_of_order'] <= max(0,s['server_seen']-1), 'reorder bounds')
    check(c['duplicates'] == 0 and s['server_duplicates'] == 0, 'duplicate traffic')
    c = dict(c, client_to_server_loss=len(sent)-len(seen),
             echo_or_reply_loss=len(seen)-len(received))
    return {k:v for k,v in c.items() if not k.endswith('_sequences')} | {
        k:v for k,v in s.items() if not k.endswith('_sequences')}


def probe(directory, size, flows):
    outcome = 'timeout'
    with udp(('10.0.0.2',12000)) as sock, selectors.DefaultSelector() as poll:
        poll.register(sock,selectors.EVENT_READ)
        sock.sendto(payload(size,2,0,0),REMOTE)
        end = time.monotonic()+.3
        while time.monotonic() < end:
            if not poll.select(min(.02,max(0,end-time.monotonic()))):
                continue
            try:
                receive(sock)
            except BlockingIOError:
                continue
            except OSError as error:
                check(error.errno in (errno.ECONNREFUSED,errno.EHOSTUNREACH,errno.ENETUNREACH), 'unexpected control error')
                outcome = 'kernel_rejection'
                break
            raise ValueError('negative control delivered')
    save(Path(directory)/'control.json', {'no_delivery': True, 'outcome':outcome})


def experiment(binary, backend, mode, size, flows, count, window, profile, deadline):
    with tempfile.TemporaryDirectory(prefix='router-v2-private-') as tmp:
        lab = Lab(tmp, deadline)
        router = None
        try:
            lab.setup(backend)
            server = lab.spawn(lab.s,[sys.executable,'-B',SCRIPT,'echo',tmp,str(size),str(flows),str(count)],'server')
            wait_file(lab.root/'server.ready',4,[server])
            check(load(lab.root/'server.ready') == {'ready':True}, 'server readiness schema')
            if backend == 'user':
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                           UDP_ROUTER_EXTRA_ARGS=json.dumps(['--ports','40000-49999','--max-flows',str(flows),
                                                           '--idle-seconds','120']))
                router = lab.spawn(lab.r,[sys.executable,'-B',SCRIPT,'launch',lab.c,lab.s,binary],'router',env)
                end = time.monotonic()+4
                while 'userspace forwarding ready' not in (lab.root/'router.log').read_text():
                    check(router.poll() is None and time.monotonic() < end, 'fresh router readiness')
                    time.sleep(.01)
            generator = lab.spawn(lab.c,[sys.executable,'-B',SCRIPT,'client',tmp,str(size),str(flows),str(count),str(window),mode],'client')
            wait_file(lab.root/'client.ready',5,[server,generator]+([router] if router else []))
            check(load(lab.root/'client.ready') == {'ready':True}, 'client readiness schema')
            profilers = profile_start(lab,router.pid,profile) if router else []
            hz = os.sysconf('SC_CLK_TCK')
            before_server = proc(server.pid)
            before_router = proc(router.pid) if router else None
            rss = before_router['rss_bytes'] if router else None
            guest_before = guest_cpu()
            monitor_start = time.monotonic_ns()
            save(lab.root/'go',{'go':True})
            while generator.poll() is None:
                check(time.monotonic() < min(deadline, monitor_start/1e9+10), 'measurement deadline')
                check(server.poll() is None and (not router or router.poll() is None), 'forwarding process exited')
                if router:
                    rss = max(rss,proc(router.pid)['rss_bytes'])
                time.sleep(.02)
            check(generator.returncode == 0, 'generator failed; private logs removed')
            monitor_wall = time.monotonic_ns()-monitor_start
            guest_after = guest_cpu()
            after_server = proc(server.pid)
            after_router = proc(router.pid) if router else None
            diagnostic = profile_finish(lab,profilers,profile) if router else None
            # Stop the actual path, keeping the same endpoint/server/topology alive.
            if router:
                stop(router)
                check(router.returncode == 0, 'router failed')
                router_counters = counters(lab.root/'router.log')
            else:
                lab.ns(lab.r,'sysctl','-q','-w','net.ipv4.ip_forward=0')
                router_counters = None
            lab.ns(lab.c,sys.executable,'-B',SCRIPT,'probe',tmp,str(size),str(flows))
            control = load(lab.root/'control.json')
            check(control in ({'no_delivery':True,'outcome':'timeout'},
                              {'no_delivery':True,'outcome':'kernel_rejection'}), 'negative control evidence')
            stop(server)
            check(server.returncode == 0, 'server failed; private logs removed')
            c,s = load(lab.root/'client.json'),load(lab.root/'server.json')
            result = validate_exchange(c,s,count,flows,mode)
            if router_counters:
                seed = flows if mode == 'warm' else 0
                check(result['distinct_nat_ports'] <= router_counters['active'] <= flows and router_counters['expired'] == 0, 'mapping/expiry bound')
                check(router_counters['forwarded'] <= 2*(count+seed), 'unexpected forwarded traffic')
                check(router_counters['forwarded'] >= 2*(result['received']+seed), 'forwarded delivery mismatch')
            wall_seconds = result['wall_ns']/1e9
            total_ticks = guest_after['total']-guest_before['total']
            busy_ticks = total_ticks-(guest_after['idle']-guest_before['idle'])
            result.update(backend=backend, mode=mode, size=size, flows=flows, window=window,
                          profile=profile, diagnostic=diagnostic, negative_control=control,
                          delivered_pps=result['received']/wall_seconds,
                          delivered_ip_mbps=result['received']*size*8/wall_seconds/1e6,
                          delivered_udp_goodput_mbps=result['received']*(size-28)*8/wall_seconds/1e6,
                          monitor_wall_ns=monitor_wall,
                          receiver_cpu_seconds=(after_server['ticks']-before_server['ticks'])/hz,
                          router_cpu_seconds=(after_router['ticks']-before_router['ticks'])/hz if router else None,
                          router_sampled_peak_rss_bytes=rss,
                          proc_clock_ticks_per_second=hz,
                          guest_cpu_busy_seconds=busy_ticks/hz, guest_cpu_total_seconds=total_ticks/hz,
                          router_counters=router_counters)
            result['router_cpu_one_core_fraction'] = result['router_cpu_seconds']/(monitor_wall/1e9) if router else None
            result['receiver_cpu_one_core_fraction'] = result['receiver_cpu_seconds']/(monitor_wall/1e9)
            result['generator_cpu_one_core_fraction'] = result['generator_cpu_ns']/result['wall_ns']
            result['guest_cpu_busy_fraction'] = busy_ticks/total_ticks if total_ticks else None
            return result
        finally:
            # Repeated stop requests cannot interrupt reaping/deleting owned resources.
            previous = {sig:signal.signal(sig,signal.SIG_IGN) for sig in (signal.SIGINT,signal.SIGTERM)}
            try:
                lab.cleanup()
            finally:
                for sig,handler in previous.items():
                    signal.signal(sig,handler)


def aggregate(values):
    check(len(values) >= 3 and all(type(v) in (int,float) and math.isfinite(v) and v >= 0 for v in values), 'invalid repeats')
    mean = statistics.mean(values)
    return dict(median=statistics.median(values),minimum=min(values),maximum=max(values),
                cv=statistics.stdev(values)/mean if mean else 0)


def summarize(rows):
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in ('backend','mode','size','flows','profile'))
        groups.setdefault(key,[]).append(row)
    result = []
    for key,group in sorted(groups.items()):
        result.append(dict(zip(('backend','mode','size','flows','profile'),key),
                           repeats=len(group), delivered_pps=aggregate([r['delivered_pps'] for r in group]),
                           rtt_p50_ns=aggregate([r['rtt']['p50_ns'] for r in group]),
                           rtt_p95_ns=aggregate([r['rtt']['p95_ns'] for r in group]),
                           rtt_p99_ns=aggregate([r['rtt']['p99_ns'] for r in group]),
                           dropped=[r['dropped'] for r in group]))
    return result


def main():
    # Helpers are private subprocess modes. All of them enforce the same gate.
    check(os.environ.get('UDP_ROUTER_ISOLATED_LINUX') == 'YES' and sys.platform == 'linux'
          and os.geteuid() == 0, 'requires explicit isolated Linux root opt-in')
    args = sys.argv[1:]
    if args and args[0] in ('echo','client','probe','launch'):
        action,*a = args
        if action == 'launch':
            launch(*a)
        elif action == 'echo':
            echo(a[0],*map(int,a[1:]))
        elif action == 'client':
            client(a[0],*map(int,a[1:5]),a[5])
        else:
            probe(a[0],*map(int,a[1:]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path)
    parser.add_argument('--size',type=int,choices=SIZES,default=64)
    parser.add_argument('--flows',type=int,default=64)
    parser.add_argument('--count',type=int,default=1500)
    parser.add_argument('--window',type=int,choices=(64,128),default=64)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--backend',choices=('both','user','kernel'),default='both')
    parser.add_argument('--mode',choices=('both',*MODES),default='both')
    parser.add_argument('--profile',choices=('none','perf','strace'),default='none')
    parser.add_argument('--metadata',required=True,help='generic OS/CPU/compiler label; no paths or identifiers')
    parser.add_argument('--output',type=Path,required=True)
    a = parser.parse_args(args)
    check(1 <= a.flows <= 512 and a.flows <= a.count <= (20000 if a.profile != 'none' else 2000), 'flow/count bounds')
    check(3 <= a.repeats <= 5, 'repeats 3..5')
    check(re.fullmatch(r'[A-Za-z0-9 .,+()=_-]{1,240}',a.metadata), 'generic metadata only')
    check(a.profile == 'none' or a.backend == 'user', 'profiling is a separate userspace diagnostic job')
    check(a.binary.is_file() and os.access(a.binary,os.X_OK), 'existing release router executable required')
    previous = {}
    def interrupted(*_):
        raise KeyboardInterrupt
    for sig in (signal.SIGINT,signal.SIGTERM):
        previous[sig] = signal.signal(sig,interrupted)
    rows = []
    deadline = time.monotonic()+120
    try:
        backends = ('user','kernel') if a.backend == 'both' else (a.backend,)
        modes = MODES if a.mode == 'both' else (a.mode,)
        for repeat in range(a.repeats):
            # Alternate backend order to expose ordering/thermal effects.
            for backend in backends[::1 if repeat % 2 == 0 else -1]:
                for mode in modes:
                    row = experiment(str(a.binary.resolve()),backend,mode,a.size,a.flows,a.count,
                                     a.window,a.profile,deadline)
                    row['repeat'] = repeat+1
                    rows.append(row)
        summary = summarize(rows)
        result = dict(schema=1,kind='REAL-LINUX-E2E' if a.profile == 'none' else 'PROFILE-DIAGNOSTIC',
                      metadata=a.metadata, count=a.count, repeats=a.repeats, rows=rows, summary=summary,
                      boundary='socket RTT; batch delivery rate includes up to 50ms receive grace only if replies are missing',
                      cpu='process ticks / CLK_TCK; generator process_time_ns; guest aggregate proc-stat ticks',
                      rss='router sampled at start and every 20ms; not lifetime high-water mark')
        save(a.output,result)
        lines = ['# Actual Linux E2E run', '',a.metadata,'',result['kind'], '',
                 'Contextual TUN userspace versus veth kernel comparison. No isolated algorithm speedup claim.', '',
                 '| Backend | Mode | Size | Flows | PPS median (min..max) | PPS CV | Loss per repeat |',
                 '|---|---|---:|---:|---:|---:|---|']
        for r in summary:
            v = r['delivered_pps']
            lines.append(f"| {r['backend']} | {r['mode']} | {r['size']} | {r['flows']} | {v['median']:.1f} ({v['minimum']:.1f}..{v['maximum']:.1f}) | {v['cv']:.3f} | {r['dropped']} |")
        a.output.with_suffix('.md').write_text('\n'.join(lines)+'\n')
        print(f'Validated {len(rows)} real experiments; no generated data is release-allowlisted')
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)


if __name__ == '__main__':
    main()
