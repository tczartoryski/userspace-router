#!/usr/bin/env python3
"""Guest bridge: fixed private snapshot choices, bounded regular-file reads."""
import argparse
import os
from pathlib import Path
import stat
import sys


LIVE_SNAPSHOT=Path('/tmp/udp-router-v2-live/snapshot.json')

def read(path):
    path=Path(path)
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_mode&0o077 or parent.st_uid!=os.geteuid():
        raise ValueError('unsafe snapshot parent')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        meta=os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_mode&0o077 or meta.st_uid!=os.geteuid():
            raise ValueError('unsafe snapshot permissions/ownership')
        data=source.read(1048577)
        if len(data)>1048576:raise ValueError('snapshot too large')
        return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v2-live',action='store_true',help='fixed /tmp/udp-router-v2-live/snapshot.json; no arbitrary path API')
    a=parser.parse_args()
    path=LIVE_SNAPSHOT if a.v2_live else Path('/tmp/udp-router-demo/snapshot.json')
    sys.stdout.buffer.write(read(path))


if __name__=='__main__':main()
