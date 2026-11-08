#!/usr/bin/env python3
"""Read-only loopback replay; validates evidence before listening. No VM access."""
import argparse
import json
import os
import stat
from http.server import HTTPServer
from pathlib import Path
from dashboard import Handler as BaseHandler
from nat_story import verify, LIMIT

ROOT = Path(__file__).resolve().parent.parent / 'story'
ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css')}


def evidence(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('regular evidence file required')
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('evidence exceeds bound')
    return json.dumps(verify(json.loads(raw))).encode()


class Handler(BaseHandler):
    def do_GET(self):
        expected = '127.0.0.1:' + str(self.server.server_port)
        if (self.headers.get_all('Host') != [expected] or
                self.headers.get_all('Origin', []) not in ([], ['http://' + expected]) or
                self.headers.get_all('Sec-Fetch-Site', []) not in ([], ['same-origin'], ['none'])):
            return self.respond(403, b'Forbidden', 'text/plain')
        if self.path == '/observations.json':
            return self.respond(200, self.server.evidence, 'application/json')
        if self.path not in ASSETS:
            return self.respond(404, b'Not found', 'text/plain')
        name, mime = ASSETS[self.path]
        self.respond(200, (ROOT / name).read_bytes(), mime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    data = evidence(args.evidence)
    with HTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.evidence = data
        server.timeout = 2
        print(f'http://127.0.0.1:{server.server_port} — recorded real Linux UDP observations', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
