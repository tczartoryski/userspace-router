"""Portable tests with explicit test fixtures. No real Linux acceptance claim."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import nat_story as story
import serve_story


def fixture():
    d = dict(schema=1, kind='recorded-real-linux-udp', clients=[], server=[], inside=[], outside=[], runs=[])
    for i, payload in enumerate(story.PAYLOADS):
        local = ['10.0.0.3' if i == 1 else '10.0.0.2', 12345]
        remote = ['198.51.100.3' if i == 2 else '198.51.100.2', 9000]
        c = dict(local=local, remote=remote, payload=payload, timed_out=i in (2,3))
        d['clients'].append(c)
        d['inside'].append(dict(src=local, dst=remote, payload=payload, ttl=64, direction='outgoing'))
        if i in (2,3):
            continue
        external = ['198.51.100.1', 40001 if i == 1 else 40000]
        c.update(peer=remote, reply=payload, ttl=63)
        d['server'].append(dict(local=remote, peer=external, payload=payload, ttl=63))
        d['inside'].append(dict(src=remote, dst=local, payload=payload, ttl=63, direction='incoming'))
        d['outside'].extend([dict(src=external, dst=remote, payload=payload, ttl=63, direction='incoming'),
                             dict(src=remote, dst=external, payload=payload, ttl=64, direction='outgoing')])
    for forwarded, policy, active in ((4,1,2),(2,0,1)):
        run = dict.fromkeys(story.COUNTER_KEYS, 0)
        run.update(forwarded=forwarded, Policy=policy, received=forwarded+policy, active=active)
        d['runs'].append(run)
    return d


class StoryTests(unittest.TestCase):
    def test_verifier_rejects_altered_evidence(self):
        story.verify(fixture())
        changes = [lambda d:d['server'][1]['peer'].__setitem__(1,40000),
                   lambda d:d['clients'][4].update(timed_out=True),
                   lambda d:d['runs'][0].update(Policy=0),
                   lambda d:d['inside'][1]['dst'].__setitem__(0,'198.51.100.1'),
                   lambda d:d['outside'].pop(),
                   lambda d:d['clients'][3].update(timed_out=False),
                   lambda d:d.update(private_path='/private/fixture'),
                   lambda d:d['server'][0].update(payload='unknown'),
                   lambda d:d['inside'][0].update(ttl=63),
                   lambda d:d['runs'][1].update(io_drops=1)]
        for change in changes:
            d=copy.deepcopy(fixture()); change(d)
            with self.assertRaises(ValueError): story.verify(d)

    def test_bounded_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.json'
            path.write_text(json.dumps(fixture()))
            self.assertTrue(serve_story.evidence(path))
            link=Path(tmp)/'link'; link.symlink_to(path)
            with self.assertRaises(OSError): serve_story.evidence(link)
            path.write_bytes(b'x'*(story.LIMIT+1))
            with self.assertRaises(ValueError): serve_story.evidence(path)

    def test_stop_has_bounded_escalation(self):
        child=Mock(); child.poll.return_value=None
        child.wait.side_effect=[subprocess.TimeoutExpired('test',2),0]
        story.stop(child)
        child.terminate.assert_called_once(); child.kill.assert_called_once()
        self.assertEqual([x.kwargs for x in child.wait.call_args_list],[{'timeout':2},{'timeout':2}])

    def test_setup_failure_cleans_owned_namespace_with_deadlines(self):
        operations = []
        def run(argv, **kwargs):
            operations.append(argv)
            self.assertEqual(kwargs['timeout'], 4)
            if argv[0:2] == ['ip', '-n']:
                raise subprocess.TimeoutExpired(argv, 4)
            return SimpleNamespace(stdout=b'')
        with patch('nat_story.sys.platform', 'linux'), patch('nat_story.os.geteuid', return_value=0), \
                patch.dict('os.environ', {'UDP_ROUTER_ISOLATED_LINUX':'YES'}), \
                patch('nat_story.subprocess.run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                story.collect(__file__, '/tmp/unused-nat-story-test.json')
        created = operations[0][-1]
        self.assertEqual(operations[-1], ['ip', 'netns', 'del', created])
        self.assertEqual(len(operations), 3)

    def request(self, path='/', headers=(), method='GET'):
        request=('\r\n'.join([f'{method} {path} HTTP/1.0','Host: 127.0.0.1:8766',*headers])+'\r\n\r\n').encode()
        output=io.BytesIO()
        class Socket:
            def makefile(self,mode,*args): return io.BytesIO(request) if 'r' in mode else output
            def sendall(self,data): output.write(data)
            def settimeout(self,value): pass
        serve_story.Handler(Socket(),('127.0.0.1',1),SimpleNamespace(server_port=8766,evidence=b'{}'))
        return output.getvalue()

    def test_http_boundaries(self):
        for path in ('/','/app.js','/style.css','/observations.json'):
            response=self.request(path)
            self.assertIn(b'200',response.splitlines()[0])
            self.assertIn(b'Content-Security-Policy',response)
        for path in ('/../Cargo.toml','/%2e%2e/Cargo.toml','/observations.json?path=x','//evil','/api/snapshot'):
            self.assertIn(b'404',self.request(path).splitlines()[0])
        for headers in (['Host: evil'],['Origin: https://evil'],['Sec-Fetch-Site: cross-site'],
                        ['Origin: http://127.0.0.1:8766']*2):
            self.assertIn(b'403',self.request(headers=headers).splitlines()[0])
        for method in ('POST','PUT','DELETE','PATCH','OPTIONS','HEAD'):
            self.assertIn(b'405',self.request(method=method).splitlines()[0])

    def test_ui_replay_and_no_sample(self):
        html=(serve_story.ROOT/'index.html').read_text()
        js=(serve_story.ROOT/'app.js').read_text()
        self.assertIn('RECORDED REAL LINUX UDP OBSERVATIONS',html)
        self.assertIn('SCHEMATIC PATH',html)
        self.assertNotIn('innerHTML',js)
        self.assertIn("fetch('/observations.json'",js)
        self.assertNotIn('nat-story-one',js)


if __name__ == '__main__': unittest.main()
