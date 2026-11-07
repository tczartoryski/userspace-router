#!/usr/bin/env python3
"""Guest bridge: one fixed task-owned snapshot, bounded output, no shell."""
import os
import stat
import sys
fd = os.open('/tmp/udp-router-demo/snapshot.json', os.O_RDONLY | os.O_NOFOLLOW)
with os.fdopen(fd, 'rb') as source:
    meta = os.fstat(source.fileno())
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
        raise SystemExit('unsafe snapshot permissions')
    data = source.read(1048577)
    if len(data) > 1048576:
        raise SystemExit('snapshot too large')
    sys.stdout.buffer.write(data)
