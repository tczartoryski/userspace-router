#!/usr/bin/env python3
"""Approved router-lab only. SIGINT/SIGTERM stop children and VM."""
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from package import build

LIMA = os.path.expanduser('~/.local/opt/lima-2.3.0/bin/limactl')
ROOT = Path(__file__).resolve().parent.parent


def run(*args, **kwargs):
    return subprocess.run([LIMA, *args], check=True, timeout=180, **kwargs)


def main():
    children, stage = [], None
    previous = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, interrupted)
    try:
        run('start', 'router-lab')
        result = run('shell', 'router-lab', 'mktemp', '-d', '/tmp/udp-router-demo-stage.XXXXXXXXXXXX',
                     capture_output=True, text=True)
        candidate = result.stdout.strip()
        if not re.fullmatch(r'/tmp/udp-router-demo-stage\.[A-Za-z0-9]{12}', candidate):
            raise ValueError('unexpected guest staging path')
        stage = candidate
        with tempfile.TemporaryDirectory(prefix='udp-router-package-') as tmp:
            archive = str(Path(tmp)/'source.tar.gz')
            build(archive)
            run('copy', archive, 'router-lab:' + stage + '/source.tar.gz')
            run('shell', 'router-lab', 'tar', '-xzf', stage + '/source.tar.gz', '-C', stage)
        guest_root = stage + '/udp-router'
        children.append(subprocess.Popen([LIMA, 'shell', 'router-lab', 'bash', guest_root + '/scripts/guest-demo.sh', '--retain'], start_new_session=True))
        children.append(subprocess.Popen(['python3', str(ROOT/'scripts/dashboard.py'), '--guest', '--guest-root', guest_root], start_new_session=True))
        print('Dashboard http://127.0.0.1:8765; Ctrl-C or SIGTERM stops processes and VM.', flush=True)
        while True:
            for child in children:
                code = child.poll()
                if code is not None:
                    raise RuntimeError(f'demo child exited unexpectedly (status {code})')
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        # Repeated stop requests must not interrupt cleanup.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        try:
            for child in children:
                if child.poll() is None:
                    try:
                        child.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
            for child in children:
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
        finally:
            try:
                if stage:
                    run('shell', 'router-lab', 'rm', '-rf', '--', stage)
            finally:
                try:
                    run('stop', 'router-lab')
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)


if __name__ == '__main__':
    main()
