import io
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import dashboard


def snapshot(running=True, unix_seconds=None):
    return dict(schema=1, running=running, unix_seconds=int(time.time()) if unix_seconds is None else int(unix_seconds),
                uptime_seconds=0, io_drops=0, interfaces=['tun-in', 'tun-out'],
                core=dict(received=0, forwarded=0, expired=0, active=0, max_flows=2, ports=[40000,40002],
                          idle_seconds=3, routes=[dict(network='10.0.0.0/24', side='Inside')],
                          drops=dict.fromkeys(dashboard.DROP_NAMES,0), mappings=[], mappings_truncated=False))


original = dashboard.read_snapshot


class DashboardTests(unittest.TestCase):
    def test_snapshot_current_stale_stopped_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'snapshot.json'
            for running, age, expected in ((True,0,'current'),(True,60,'stale'),(False,0,'offline'),(True,-60,'stale')):
                path.write_text(json.dumps(snapshot(running, time.time()-age)))
                path.chmod(0o600)
                self.assertEqual(dashboard.read_snapshot(path)['state'],expected)
            path.chmod(0o644)
            with self.assertRaises(ValueError): dashboard.read_snapshot(path)
            path.chmod(0o600); path.write_bytes(b'x'*(dashboard.LIMIT+1))
            with self.assertRaises(ValueError): dashboard.read_snapshot(path)
            path.unlink(); path.symlink_to('/dev/null')
            with self.assertRaises(OSError): dashboard.read_snapshot(path)

    def request(self, path='/', host='127.0.0.1:8765', origin=None, method='GET', fetch=None, extra=()):
        headers = [f'{method} {path} HTTP/1.0', f'Host: {host}']
        if origin: headers.append('Origin: '+origin)
        if fetch: headers.append('Sec-Fetch-Site: '+fetch)
        headers.extend(extra)
        request = ('\r\n'.join(headers)+'\r\n\r\n').encode()
        output = io.BytesIO()
        class Socket:
            def makefile(self, mode, *args): return io.BytesIO(request) if 'r' in mode else output
            def sendall(self, data): output.write(data)
            def settimeout(self, timeout): pass
        server = SimpleNamespace(server_port=8765, snapshot='/nonexistent', guest=False)
        dashboard.Handler(Socket(), ('127.0.0.1',1), server)
        return output.getvalue()

    def test_http_guards_and_allowlist(self):
        for host in ('evil.example:8765','localhost:8765','127.0.0.1:8765.evil','127.0.0.2:8765'):
            self.assertIn(b'403',self.request(host=host).splitlines()[0])
        self.assertIn(b'403',self.request(origin='https://evil.example').splitlines()[0])
        self.assertIn(b'403',self.request(fetch='cross-site').splitlines()[0])
        for path in ('/../Cargo.toml','/api/snapshot?command=bad','/favicon.ico','//evil'):
            self.assertIn(b'404',self.request(path).splitlines()[0])
        for method in ('POST','PUT','DELETE','PATCH','OPTIONS','HEAD'):
            self.assertIn(b'405',self.request(method=method).splitlines()[0])
        for path in ('/','/app.js','/style.css','/api/snapshot'):
            response=self.request(path)
            self.assertIn(b'200',response.splitlines()[0]);self.assertIn(b'Content-Security-Policy:',response)
            self.assertNotIn(b'Access-Control-Allow-Origin',response)
        self.assertIn(b'"state": "offline"',self.request('/api/snapshot'))

    def test_bridge_fixed_argv_timeout(self):
        result=SimpleNamespace(stdout=json.dumps(snapshot(False,0)).encode())
        with patch('dashboard.subprocess.run',return_value=result) as run:
            dashboard.read_snapshot('ignored; shell-command',True)
            args, kwargs=run.call_args
            self.assertNotIn('shell',kwargs)
            self.assertEqual(args[0][-5:],['sudo','-n','python3','-B','router/scripts/read_snapshot.py'])
            self.assertEqual(kwargs['timeout'],4)

    def test_actual_mapping_schema_and_consistency(self):
        data=snapshot()
        core=data['core']
        core.update(received=1, forwarded=1, active=1,
                    mappings=[dict(internal='10.0.0.2:1234', remote='198.51.100.2:9000',
                                   external='198.51.100.1:40000', idle_seconds=0)])
        dashboard.validate_snapshot(data)
        for key, value in [('external','198.51.100.1:39999'), ('remote','bad:9000'),
                           ('internal','10.0.0.2:0'), ('idle_seconds',float('nan'))]:
            bad=copy.deepcopy(data); bad['core']['mappings'][0][key]=value
            with self.assertRaises(ValueError): dashboard.validate_snapshot(bad)
        bad=copy.deepcopy(data); bad['core']['active']=2
        bad['core']['mappings'] *= 2
        with self.assertRaises(ValueError): dashboard.validate_snapshot(bad)

    def test_duplicate_security_headers_rejected(self):
        for key, value in [('Origin','http://127.0.0.1:8765'), ('Sec-Fetch-Site','same-origin')]:
            for other in (value, 'evil'):
                response = self.request(extra=[key+': '+value,key+': '+other])
                self.assertIn(b'403', response.splitlines()[0])

    def test_invalid_schema_fails_offline(self):
        mutations = [
            lambda d: d.update(unix_seconds=float('nan')),
            lambda d: d.update(unix_seconds=float('inf')),
            lambda d: d.update(unix_seconds='yesterday'),
            lambda d: d.update(unix_seconds=True),
            lambda d: d.update(unix_seconds=-1),
            lambda d: d.update(unix_seconds=2**64),
            lambda d: d['core'].update(active=3),
            lambda d: d['core'].update(received=1),
            lambda d: d['core'].update(mappings_truncated=True),
            lambda d: d['core'].update(routes=[dict(network='bad',side='Inside')]),
            lambda d: d['core'].update(routes=[]),
            lambda d: d['core'].update(ports=[0,65536]),
            lambda d: d['core']['drops'].update(Filter=-1),
            lambda d: d['core'].update(mappings=[{}]),
            lambda d: d.update(core=[]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json'
            for mutate in mutations:
                data=copy.deepcopy(snapshot()); mutate(data)
                path.write_text(json.dumps(data)); path.chmod(0o600)
                with patch('dashboard.read_snapshot', side_effect=lambda *args: original(path)):
                    self.assertIn(b'"state": "offline"', self.request('/api/snapshot'))

    def test_ui_has_accessibility_and_no_external_assets(self):
        html=(dashboard.ROOT/'index.html').read_text()
        for marker in ('lang="en"','name="viewport"','aria-live="polite"','scope="col"','id="redact"','class="skip"'):
            self.assertIn(marker,html)
        js=(dashboard.ROOT/'app.js').read_text()
        self.assertNotIn('innerHTML',js)
        self.assertNotIn('https://',html)
        self.assertIn('AbortSignal.timeout',js)

if __name__ == '__main__': unittest.main()
