"""Pure evidence and mocked lifecycle checks; no root/network/VM operations."""
import copy
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import e2e_benchmark as bench


def fixture():
    c = dict(attempted=3,sent=3,received=2,dropped=1,send_failed=0,duplicates=0,
             out_of_order=1,wall_ns=1000,generator_cpu_ns=10,
             sent_sequences=[0,1,2],received_sequences=[0,2],
             rtt=dict(p50_ns=10,p95_ns=20,p99_ns=20,samples=2))
    s = dict(server_seen=3,server_sequences=[0,1,2],server_duplicates=0,
             server_out_of_order=0,distinct_nat_ports=1,seed_seen=1)
    return c,s


class E2ETests(unittest.TestCase):
    def test_payload_sizes_and_corruption(self):
        for size in bench.SIZES:
            data = bench.payload(size,1,511,1999)
            self.assertEqual(len(data),size-28)
            self.assertEqual(bench.decode(data,size,512),(1,511,1999))
            for bad in (data[:-1],data[:-1]+bytes([data[-1]^1])):
                with self.assertRaises(ValueError): bench.decode(bad,size,512)
        with self.assertRaises(ValueError): bench.decode(bench.payload(64,1,512,0),64,512)

    def test_quantiles_aggregation_and_invalid_metrics(self):
        self.assertEqual(bench.quantiles([30,10,20]),dict(p50_ns=20,p95_ns=30,p99_ns=30,samples=3))
        self.assertEqual(bench.aggregate([1,2,3]),dict(median=2,minimum=1,maximum=3,cv=.5))
        for values in ([],[1,2],[1,2,True],[1,2,float('nan')],[1,2,-1]):
            with self.assertRaises(ValueError): bench.aggregate(values)
        c,s = fixture()
        self.assertEqual(bench.validate_exchange(c,s,3,1,'warm')['dropped'],1)
        for change in (lambda c,s:c.update(received=True),lambda c,s:c.update(dropped=0),
                       lambda c,s:s.update(server_seen=2),lambda c,s:s.update(server_sequences=[0,1]),
                       lambda c,s:c.update(received_sequences=[0,0]),lambda c,s:c.update(sent_sequences=[0,1,3]),
                       lambda c,s:c['rtt'].update(p99_ns=1),lambda c,s:c.update(duplicates=1),
                       lambda c,s:s.update(seed_seen=0),lambda c,s:s.update(distinct_nat_ports=2)):
            c,s = copy.deepcopy(fixture()); change(c,s)
            with self.assertRaises(ValueError): bench.validate_exchange(c,s,3,1,'warm')

    def test_mutating_topology_commands_are_scoped(self):
        for backend in ('user','kernel'):
            with tempfile.TemporaryDirectory() as tmp:
                lab = bench.Lab(tmp,99999999999)
                commands = []
                lab.command = lambda *args,**kwargs: commands.append(args)
                lab.setup(backend)
                self.assertEqual(set(lab.owned),set(lab.names))
                for cmd in commands:
                    self.assertEqual(cmd[0:2],('ip','netns'))
                    if cmd[2] == 'add':
                        self.assertIn(cmd[3],lab.names)
                    else:
                        self.assertEqual(cmd[2],'exec')
                        self.assertIn(cmd[3],lab.owned)
                if backend == 'kernel':
                    self.assertTrue(any('SNAT' in cmd for cmd in commands))
                    self.assertTrue(any('veth' in cmd for cmd in commands))
                with self.assertRaises(ValueError): lab.ns('unowned','sysctl','-w','x=1')

    def test_cleanup_reaps_escalates_and_only_deletes_created(self):
        p = Mock(); p.poll.return_value = None
        p.wait.side_effect = [subprocess.TimeoutExpired('child',2),0]
        bench.stop(p)
        p.terminate.assert_called_once(); p.kill.assert_called_once()
        self.assertEqual([c.kwargs['timeout'] for c in p.wait.call_args_list],[2,2])
        with tempfile.TemporaryDirectory() as tmp:
            lab = bench.Lab(tmp,0)
            lab.owned = lab.names[:2]
            lab.children = [Mock(),Mock()]
            calls = []
            lab.command = lambda *args,**kwargs:calls.append((args,kwargs))
            with patch.object(bench,'stop',side_effect=[OSError('test'),None]) as stopped:
                with self.assertRaises(ValueError): lab.cleanup()
            self.assertEqual(stopped.call_count,2)
            self.assertEqual([c[0] for c in calls],[('ip','netns','del',n) for n in reversed(lab.owned)])
            self.assertTrue(all(c[1] == {'cleanup':True} for c in calls))

    def test_partial_setup_failure_keeps_only_successful_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = bench.Lab(tmp,99999999999)
            def command(*args,**kwargs):
                if args[:3] == ('ip','netns','add') and args[3] == lab.names[1]:
                    raise subprocess.CalledProcessError(1,args)
            lab.command = command
            with self.assertRaises(subprocess.CalledProcessError): lab.setup('user')
            self.assertEqual(lab.owned,lab.names[:1])

    def test_root_gate_and_bytecode_prologue(self):
        with patch.dict('os.environ',{'UDP_ROUTER_ISOLATED_LINUX':'NO'}):
            with self.assertRaises(ValueError): bench.main()
        shell = Path(__file__).with_name('linux-benchmark.sh').read_text()
        self.assertIn('export PYTHONDONTWRITEBYTECODE=1',shell)
        self.assertIn('exec python3 -B',shell)
        self.assertNotIn('sudo',shell)

    def test_final_counters_and_proc_parser(self):
        values = dict.fromkeys(bench.COUNTER_KEYS,0)
        values.update(received=5,forwarded=4,Protocol=1,active=1)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'router.log'
            line = ' '.join(f'{k}={v}' for k,v in values.items())
            p.write_text(line+'\n')
            self.assertEqual(bench.counters(p),values)
            for bad in (line+' forwarded=4',line.replace('forwarded=4','forwarded=3'),
                        line.replace('Filter=0','Filter=1'),'fatal'):
                p.write_text(bad+'\n')
                with self.assertRaises(ValueError): bench.counters(p)
        with patch.object(Path,'read_text',return_value='1 (router name) '+' '.join(str(i) for i in range(22))):
            with patch.object(bench.os,'sysconf',return_value=4096):
                self.assertEqual(bench.proc(1),dict(ticks=23,rss_bytes=21*4096))


class GeneratorTests(unittest.TestCase):
    def run_generator(self, late=False):
        # Deterministic socket/selector doubles exercise actual generator control flow.
        sockets = []
        clock = [0.0]
        class Sock:
            def __init__(self,flow): self.flow,self.queue = flow,[]
            def sendto(self,data,peer):
                self.queue.append(data)
                return len(data)
            def close(self): pass
        class Poll:
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def register(self,sock,events,data): pass
            def select(self,timeout):
                clock[0] += .006
                return [(Mock(fileobj=s,data=s.flow),1) for s in sockets
                        if s.queue and (not late or s.queue[0][4] == 0 or clock[0] >= .515)]
        def udp(address):
            sock = Sock(len(sockets)); sockets.append(sock); return sock
        def receive(sock):
            if not sock.queue: raise BlockingIOError()
            return sock.queue.pop(0),bench.REMOTE,int(clock[0]*1e9)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'go').write_text('{}')
            with patch.object(bench,'udp',side_effect=udp), patch.object(bench,'receive',side_effect=receive), \
                    patch.object(bench.selectors,'DefaultSelector',Poll), \
                    patch.object(bench.time,'monotonic',side_effect=lambda:clock[0]), \
                    patch.object(bench.time,'monotonic_ns',side_effect=lambda:int(clock[0]*1e9)):
                bench.client(tmp,64,2,8,64,'warm')
            result = bench.load(Path(tmp)/'client.json')
            self.assertEqual(result['received'],8)
            self.assertEqual(result['dropped'],0)
            self.assertEqual(len(sockets),2)
            self.assertEqual(result['rtt']['samples'],8)
            return result, clock[0]

    def test_warm_generator_reuses_sockets_and_validates_immediate_replies(self):
        result, clock = self.run_generator()
        # One selector pass per exchange, with no forced 50-ms idle tail.
        self.assertEqual(result['wall_ns'],6_000_000)
        self.assertAlmostEqual(clock,.012)

    def test_late_collection_counts_replies_and_stops_when_complete(self):
        result, clock = self.run_generator(late=True)
        # Replies arrive after the 500-ms timeout, during conditional collection.
        self.assertGreaterEqual(result['wall_ns'],500_000_000)
        self.assertLess(result['wall_ns'],520_000_000)
        self.assertLess(clock,.53)
        self.assertEqual(result['rtt']['p99_ns'],result['wall_ns'])

    def test_helper_client_dispatch_arguments(self):
        argv = ['e2e_benchmark.py','client','/tmp/fixture','64','2','8','64','warm']
        with patch.object(bench.sys,'argv',argv),patch.object(bench.sys,'platform','linux'), \
                patch.object(bench.os,'geteuid',return_value=0), \
                patch.dict('os.environ',{'UDP_ROUTER_ISOLATED_LINUX':'YES'}), \
                patch.object(bench,'client') as client:
            bench.main()
        client.assert_called_once_with('/tmp/fixture',64,2,8,64,'warm')


class ProfilingTests(unittest.TestCase):
    def test_software_events_attach_actual_pid_and_sanitize_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = bench.Lab(tmp,99999999999)
            child = Mock(); child.poll.return_value = None
            lab.spawn = Mock(return_value=child)
            with patch.object(bench.time,'sleep'):
                children = bench.profile_start(lab,314159,'perf')
            commands = [call.args[1] for call in lab.spawn.call_args_list]
            self.assertEqual(len(commands),2)
            for cmd in commands:
                self.assertEqual(cmd[cmd.index('-p')+1],'314159')
                self.assertNotIn('cycles',','.join(cmd))
                self.assertNotIn('instructions',','.join(cmd))
            (lab.root/'perf-stat.txt').write_text('1.25,msec,task-clock,1,100.00\n2,,context-switches,1,100.00\n0,,page-faults,1,100.00\n')
            lab.ns = Mock(return_value=Mock(stdout=b' 80.00% [.] userspace_udp_router::Router::process\n 20.00% [.] /private/fixture/forbidden\n'))
            result = bench.profile_finish(lab,children,'perf')
            self.assertEqual(result['symbols'],[dict(percent=80.0,symbol='userspace_udp_router::Router::process')])
            self.assertEqual(len(result['stats']),3)
            child.send_signal.assert_called_with(signal.SIGINT)


class WorkerHarnessTests(unittest.TestCase):
    def test_worker_overrides_keep_positive_shards_and_bounded_queues(self):
        for workers in (1,2,4):
            args = bench.router_arguments(1,workers,64)
            self.assertEqual(args[args.index('--workers')+1],str(workers))
            self.assertEqual(args[args.index('--max-flows')+1],str(workers))
            self.assertEqual(args[args.index('--ports')+1],'40000-49999')
        for workers,queue in ((0,64),(3,64),(4,0),(4,1024)):
            with self.assertRaises(ValueError): bench.router_arguments(64,workers,queue)

    def test_worker_counts_remain_separate_in_repeat_aggregation(self):
        rows = []
        for workers in (1,2,4):
            for repeat in range(3):
                rows.append(dict(backend='user',mode='warm',size=64,flows=64,profile='none',
                                 workers=workers,queue_depth=None if workers == 1 else 64,
                                 delivered_pps=100+repeat,dropped=0,
                                 rtt=dict(p50_ns=1,p95_ns=2,p99_ns=3)))
        summary = bench.summarize(rows)
        self.assertEqual([r['workers'] for r in summary],[1,2,4])
        self.assertTrue(all(r['repeats'] == 3 for r in summary))


if __name__ == '__main__':
    unittest.main()
