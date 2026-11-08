#!/usr/bin/env python3
"""Opt-in actual live guest demo, ~40 seconds; not a benchmark or browser capture."""
import argparse
import os
from pathlib import Path
import selectors
import signal
import sys
import tempfile
import time
from e2e_benchmark import Lab, check, load, save, stop, udp, receive, wait_file
from worker_acceptance import gate
from traffic import launch
from dashboard import read_snapshot

SCRIPT=str(Path(__file__).resolve())
# Root-owned /tmp parent remains traversable after capability drop; no home chmod.
STATE=Path('/tmp/udp-router-v2-live')
REMOTE=('198.51.100.2',9000)


def payload(seq,flow):
    check(0<=seq<2000 and 0<=flow<4,'live payload bounds')
    return f'LIVEV2|{seq}|{flow}'.encode('ascii')


def decode(data):
    fields=data.decode('ascii').split('|');check(len(fields)==3 and fields[0]=='LIVEV2','unexpected live payload')
    seq,flow=map(int,fields[1:]);check(data==payload(seq,flow),'live payload mismatch');return seq,flow


def server(directory):
    root=Path(directory);done=False
    def end(*_):
        nonlocal done
        done=True
    signal.signal(signal.SIGTERM,end)
    count=0;deadline=time.monotonic()+46
    with udp(REMOTE) as sock,selectors.DefaultSelector() as poll:
        poll.register(sock,selectors.EVENT_READ);save(root/'server.ready',{'ready':True})
        while not done and time.monotonic()<deadline:
            for _,_ in poll.select(.05):
                for _ in range(128):
                    try:data,peer,_=receive(sock)
                    except BlockingIOError:break
                    decode(data);check(peer[0]=='198.51.100.1' and 40000<=peer[1]<=49999,'live SNAT tuple')
                    try:sock.sendto(data,peer)
                    except BlockingIOError:continue
                    count+=1
        check(done,'live server deadline');save(root/'server.json',{'actual_echoes':count})


def client(directory):
    root=Path(directory);sockets=[];sent={};seen=set();counts={k:0 for k in ('current','stale','resume','offline')};offered=counts.copy()
    try:
        with selectors.DefaultSelector() as poll:
            for flow in range(4):
                sock=udp(('10.0.0.2',12000+flow));sockets.append(sock);poll.register(sock,selectors.EVENT_READ,flow)
            end=time.monotonic()+40;seq=0
            while time.monotonic()<end and seq<2000:
                phase=(root/'phase').read_text().strip();check(phase in counts,'live phase label')
                flow=seq%4;data=payload(seq,flow)
                try:sockets[flow].sendto(data,REMOTE)
                except BlockingIOError:pass
                else:sent[seq]=(flow,phase);offered[phase]+=1
                seq+=1
                for key,_ in poll.select(.025):
                    for _ in range(128):
                        try:data,peer,_=receive(key.fileobj)
                        except BlockingIOError:break
                        received,flow=decode(data)
                        check(received in sent and sent[received][0]==flow==key.data and peer==REMOTE,'unverified live echo')
                        check(received not in seen,'duplicate live echo');seen.add(received);counts[sent[received][1]]+=1
                time.sleep(.025)
        check(counts['current']>=4 and counts['resume']>=4 and offered['offline']>=4 and counts['offline']==0,'live delivery/recovery/stopped controls')
        save(root/'client.json',dict(verified_echoes_by_send_phase=counts,offered_by_phase=offered))
    finally:
        for sock in sockets:sock.close()


def phase(root,label):
    check(label in ('current','stale','resume','offline'),'phase label')
    temporary=root/'phase.next';temporary.write_text(label);temporary.replace(root/'phase')


def collect(binary,output):
    # Refuse every pre-existing directory, even apparently private: no overwrite
    # or cleanup of another run/user's artifacts. Only this creation is owned.
    STATE.mkdir(mode=0o700)
    previous={};router=None;frozen=False
    def interrupt(*_):raise KeyboardInterrupt
    for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,interrupt)
    try:
        with tempfile.TemporaryDirectory(prefix='router-v2-live-private-') as tmp:
            root=Path(tmp);lab=Lab(tmp,time.monotonic()+52)
            try:
                lab.setup('user')
                srv=lab.spawn(lab.s,[sys.executable,'-B',SCRIPT,'server',tmp],'server');wait_file(root/'server.ready',3,[srv])
                extra=['--workers','4','--queue-depth','64','--ports','40000-49999','--max-flows','128','--idle-seconds','120',
                       '--snapshot',str(STATE/'snapshot.json'),'--event-sample-every','100']
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',UDP_ROUTER_EXTRA_ARGS=__import__('json').dumps(extra))
                router=lab.spawn(lab.r,[sys.executable,'-B',SCRIPT,'launch',lab.c,lab.s,str(Path(binary).resolve())],'router',env)
                end=time.monotonic()+3
                while 'userspace forwarding ready' not in (root/'router.log').read_text():
                    check(router.poll() is None and time.monotonic()<end,'fresh live readiness: '+(root/'router.log').read_text()[-1600:]);time.sleep(.02)
                phase(root,'current')
                generator=lab.spawn(lab.c,[sys.executable,'-B',SCRIPT,'client',tmp],'client')
                started=time.monotonic();stage='current';observations={}
                print('LIVE: actual traffic; current12s → SIGSTOP/stale7s → resume12s → stopped/offline9s',flush=True)
                while generator.poll() is None:
                    elapsed=time.monotonic()-started
                    check(elapsed<43 and srv.poll() is None,'live process deadline')
                    if elapsed>=12 and stage=='current':
                        view=read_snapshot(STATE/'snapshot.json')
                        check(view['state']=='current' and view['snapshot']['schema']==2 and len(view['snapshot']['workers'])==4 and view['snapshot']['tx']['packets']>0,'actual current live snapshot missing')
                        observations['current']=view['snapshot']
                        check(router.poll() is None,'router exited before pause');router.send_signal(signal.SIGSTOP);frozen=True
                        phase(root,'stale');stage='stale';print('STALE PHASE: task-owned router SIGSTOP; snapshot timestamp unchanged',flush=True)
                    if elapsed>=19 and stage=='stale':
                        view=read_snapshot(STATE/'snapshot.json');check(view['state']=='stale','actual snapshot did not become stale');observations['stale']=view['snapshot']
                        router.send_signal(signal.SIGCONT);frozen=False;phase(root,'resume');stage='resume';print('RESUME: SIGCONT; verifying real echoes again',flush=True)
                    if elapsed>=31 and stage=='resume':
                        view=read_snapshot(STATE/'snapshot.json');check(view['state']=='current' and view['snapshot']['tx']['packets']>observations['current']['tx']['packets'],'actual current recovery missing');observations['resumed']=view['snapshot']
                        stop(router);check(router.returncode==0,'live router did not join cleanly')
                        view=read_snapshot(STATE/'snapshot.json');check(view['state']=='offline' and not view['snapshot']['running'],'actual stopped snapshot missing');observations['offline']=view['snapshot']
                        phase(root,'offline');stage='offline';print('OFFLINE: router reaped; real stopped snapshot retained until demo ends',flush=True)
                    if stage!='offline':check(router.poll() is None,'live router failure')
                    time.sleep(.05)
                check(generator.returncode==0 and stage=='offline','live echo/status verification failed')
                client_data=load(root/'client.json');stop(srv);check(srv.returncode==0,'live server failure')
                result=dict(kind='REAL-LINUX-LIVE-DEMO',snapshots=observations,client=client_data,server=load(root/'server.json'),disclosure='actual phase observations; browser capture performed separately')
            finally:
                for sig in previous:signal.signal(sig,signal.SIG_IGN)
                if router is not None and frozen and router.poll() is None:router.send_signal(signal.SIGCONT)
                lab.cleanup()
        save(output,result);print('PASS actual echo recovery/current/stale/offline controls; cleanup complete',flush=True)
    finally:
        # Delete only the exact snapshot created in our exclusively created dir.
        try:
            (STATE/'snapshot.json').unlink(missing_ok=True)
            STATE.rmdir()
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)


def main():
    gate();args=sys.argv[1:]
    if args and args[0] in ('server','client','launch'):
        action,*rest=args;{'server':server,'client':client,'launch':launch}[action](*rest);return
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('binary',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(args)
    check(a.binary.is_file() and os.access(a.binary,os.X_OK),'existing executable required');collect(a.binary,a.output)


if __name__=='__main__':main()
