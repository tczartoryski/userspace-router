#!/usr/bin/env python3
"""Guest-only bounded four-worker socket adversarial/export acceptance. Not a benchmark."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import sys
import tempfile
import time
from e2e_benchmark import Lab, check, load, save, stop, udp, receive, wait_file
from traffic import launch
from dashboard import read_snapshot, validate_snapshot

SCRIPT=str(Path(__file__).resolve())
REMOTE=('198.51.100.2',9000)
STAGES={'local','denied','owner','arm','reallocate','policy','overload','paced','stopped'}


def gate():
    check(sys.platform=='linux' and os.geteuid()==0 and os.environ.get('UDP_ROUTER_ISOLATED_LINUX')=='YES','explicit isolated Linux root opt-in required')


def owner(address,port=12345):
    value=0xcbf29ce484222325
    for byte in socket.inet_aton(address)+port.to_bytes(2,'big'):
        value=((value^byte)*0x100000001b3)&(2**64-1)
    return value%4


def clients():
    chosen={}
    for n in range(2,255):
        address=f'10.0.0.{n}';chosen.setdefault(owner(address),address)
    check(len(chosen)==4,'fixture cannot address all shards')
    extra=next(f'10.0.0.{n}' for n in range(2,255) if owner(f'10.0.0.{n}')==0 and f'10.0.0.{n}' not in chosen.values())
    return [chosen[i] for i in range(4)],extra


def payload(stage,token):
    check(stage in STAGES and type(token) is int and 0<=token<32768,'fixture payload bounds')
    return f'URV2A|{stage}|{token}'.encode('ascii')


def decode(data):
    check(len(data)<=64,'unexpected payload length')
    fields=data.decode('ascii').split('|')
    check(len(fields)==3 and fields[0]=='URV2A' and fields[2].isascii() and fields[2].isdecimal(),'unexpected payload')
    stage=fields[1];token=int(fields[2]);check(data==payload(stage,token),'payload mismatch')
    return stage,token


def server(directory):
    root=Path(directory);stopped=False
    def end(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,end)
    records=[];overload=set();wrong_addr=wrong_port=late=0;armed=None;last_wrong=0
    sockets=[]
    try:
        for address,port in (REMOTE,('198.51.100.2',9001),('198.51.100.4',9000),('198.51.100.3',9000)):
            sockets.append(udp((address,port)))
        with selectors.DefaultSelector() as poll:
            poll.register(sockets[0],selectors.EVENT_READ);poll.register(sockets[3],selectors.EVENT_READ)
            save(root/'server.ready',{'ready':True});deadline=time.monotonic()+18
            while not stopped and time.monotonic()<deadline:
                for key,_ in poll.select(.01):
                    for _ in range(128):
                        try:data,peer,_=receive(key.fileobj)
                        except BlockingIOError:break
                        stage,token=decode(data)
                        check(peer[0]=='198.51.100.1' and 40000<=peer[1]<=40007,'actual SNAT endpoint')
                        if stage=='overload':overload.add(token)
                        else:
                            check(len(records)<128,'server observation bound')
                            records.append(dict(stage=stage,token=token,peer=list(peer)))
                        if stage=='arm':armed=(time.monotonic(),peer)
                        try:key.fileobj.sendto(data,peer)
                        except BlockingIOError:pass
                if armed:
                    started,peer=armed;now=time.monotonic()
                    if .25<=now-started<=3.0 and now-last_wrong>=.125:
                        if wrong_port<=wrong_addr:
                            sockets[1].sendto(b'WRONG-PORT',peer);wrong_port+=1
                        else:
                            sockets[2].sendto(b'WRONG-ADDRESS',peer);wrong_addr+=1
                        last_wrong=now
                    if now-started>=3.4 and not late:
                        sockets[0].sendto(b'LATE',peer);late+=1
            check(stopped,'server lifetime deadline')
            save(root/'server.json',dict(records=records,overload_seen=len(overload),wrong_address_sent=wrong_addr,wrong_port_sent=wrong_port,late_sent=late))
    finally:
        for sock in sockets:sock.close()


def exchange(sock,stage,token,destination=REMOTE,delivery=True):
    data=payload(stage,token);sock.sendto(data,destination)
    with selectors.DefaultSelector() as poll:
        poll.register(sock,selectors.EVENT_READ)
        events=poll.select(.6 if delivery else .35)
        if not delivery:
            check(not events,'negative case delivered');return
        check(events,'required echo missing')
        answer,peer,_=receive(sock);check(answer==data and peer==destination,'incorrect echo/tuple')


def client(directory):
    root=Path(directory);addresses,extra=clients();sockets=[]
    try:
        for address in addresses+[extra]:sockets.append(udp((address,12345)))
        exchange(sockets[0],'local',0)
        exchange(sockets[4],'denied',0,delivery=False) # shard zero full, three shards still free
        for i in range(1,4):exchange(sockets[i],'owner',i)
        exchange(sockets[0],'policy',0,('198.51.100.3',9000),False)
        exchange(sockets[0],'arm',0)
        # Wrong tuples continue near expiry; valid original-remote late packet is
        # sent after 3.4s, beyond a two-integer-second idle limit. No boundary claim.
        with selectors.DefaultSelector() as poll:
            poll.register(sockets[0],selectors.EVENT_READ)
            end=time.monotonic()+4.0
            while time.monotonic()<end:
                check(not poll.select(max(0,min(.05,end-time.monotonic()))),'wrong remote refreshed/delivered or expired late packet delivered')
        exchange(sockets[4],'reallocate',0)
        offered=set();received=set();send_failed=duplicates=0;start=time.monotonic();end=start+1.2;seq=0
        with selectors.DefaultSelector() as poll:
            poll.register(sockets[4],selectors.EVENT_READ)
            while time.monotonic()<end and seq<32768:
                for _ in range(min(64,32768-seq)):
                    try:sockets[4].sendto(payload('overload',seq),REMOTE)
                    except BlockingIOError:send_failed+=1
                    else:offered.add(seq)
                    seq+=1
                for key,_ in poll.select(.001):
                    for _ in range(1024):
                        try:data,peer,_=receive(key.fileobj)
                        except BlockingIOError:break
                        stage,token=decode(data);check(stage=='overload' and token in offered and peer==REMOTE,'incorrect overload reply')
                        if token in received:duplicates+=1
                        received.add(token)
                time.sleep(.002)
            drain=time.monotonic()+.3
            while time.monotonic()<drain:
                for key,_ in poll.select(.01):
                    for _ in range(1024):
                        try:data,peer,_=receive(key.fileobj)
                        except BlockingIOError:break
                        stage,token=decode(data);check(stage=='overload' and token in offered and peer==REMOTE,'incorrect overload drain')
                        if token in received:duplicates+=1
                        received.add(token)
        check(not duplicates and len(received)>0,'overload echo validation')
        overload_ns=int((time.monotonic()-start)*1e9)
        check(overload_ns>=1_000_000_000,'sustained burst interval missing')
        save(root/'paced.ready',{'ready':True})
        began=time.monotonic_ns();paced=0
        while time.monotonic_ns()-began<3_200_000_000:
            exchange(sockets[4],'paced',paced);paced+=1;time.sleep(.12)
        save(root/'client.json',dict(bindings=[list(s.getsockname()) for s in sockets],partition_timeout=True,policy_timeout=True,wrong_remote_and_late_timeout=True,
             reallocated=True,paced_echoes=paced,paced_ns=time.monotonic_ns()-began,
             offered=len(offered),received=len(received),send_failed=send_failed,overload_wall_ns=overload_ns,duplicates=duplicates))
    finally:
        for sock in sockets:sock.close()


def negative(directory):
    _,address=clients()
    with udp((address,12345)) as sock:exchange(sock,'stopped',0,delivery=False)
    save(Path(directory)/'control.json',{'no_delivery':True})


def verify_receipts(server_data):
    records=server_data['records']
    check(not any(r['stage'] in ('denied','policy','stopped') for r in records),'negative server delivery')
    expected=[next((r for r in records if r['stage']=='local' and r['token']==0),None)]
    expected += [next((r for r in records if r['stage']=='owner' and r['token']==i),None) for i in range(1,4)]
    check(all(expected),'all four worker observations required')
    ports=[]
    for i,r in enumerate(expected):
        check(r['peer'][0]=='198.51.100.1' and 40000+2*i<=r['peer'][1]<=40001+2*i,'observed external port not owned by expected worker')
        ports.append(r['peer'][1])
    check(len(set(ports))==4,'cross-worker external collision')
    check(server_data['wrong_address_sent']>=2 and server_data['wrong_port_sent']>=2 and server_data['late_sent']==1,'actual adversarial sends missing')
    check(any(r['stage']=='reallocate' and 40000<=r['peer'][1]<=40001 for r in records),'reallocation owner receipt missing')


def collect(binary,output):
    previous={}
    def interrupted(*_):raise KeyboardInterrupt
    for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,interrupted)
    try:
        with tempfile.TemporaryDirectory(prefix='router-worker-accept-') as tmp:
            root=Path(tmp);lab=Lab(tmp,time.monotonic()+25);snapshots=[];paced_baseline=None
            check(root.stat().st_mode&0o077==0,'private acceptance parent permissions')
            try:
                lab.setup('user');addresses,extra=clients()
                for address in addresses+[extra]:
                    if address!='10.0.0.2':lab.ns(lab.c,'ip','addr','add',address+'/32','dev','tun-in')
                for address in ('198.51.100.3','198.51.100.4'):lab.ns(lab.s,'ip','addr','add',address+'/32','dev','tun-out')
                srv=lab.spawn(lab.s,[sys.executable,'-B',SCRIPT,'server',tmp],'server');wait_file(root/'server.ready',3,[srv])
                args=['--workers','4','--queue-depth','1','--ports','40000-40007','--max-flows','4','--idle-seconds','2',
                      '--route','198.51.100.3/32=inside','--snapshot',str(root/'snapshot.json'),'--event-sample-every','1']
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',UDP_ROUTER_EXTRA_ARGS=json.dumps(args))
                router=lab.spawn(lab.r,[sys.executable,'-B',SCRIPT,'launch',lab.c,lab.s,str(Path(binary).resolve())],'router',env)
                end=time.monotonic()+3
                while 'userspace forwarding ready' not in (root/'router.log').read_text():
                    check(router.poll() is None and time.monotonic()<end,'fresh ready deadline');time.sleep(.01)
                generator=lab.spawn(lab.c,[sys.executable,'-B',SCRIPT,'client',tmp],'client')
                end=time.monotonic()+15
                while generator.poll() is None:
                    check(time.monotonic()<end and srv.poll() is None and router.poll() is None,'acceptance process deadline/failure')
                    path=root/'snapshot.json'
                    if path.exists():
                        meta=path.lstat();check(stat.S_ISREG(meta.st_mode) and meta.st_mode&0o777==0o600 and meta.st_uid==os.geteuid(),'snapshot private file permissions')
                        d=read_snapshot(path)['snapshot'];check(d['schema']==2 and d['running'],'live snapshot schema')
                        if (root/'paced.ready').exists():
                            if paced_baseline is None:paced_baseline=d['monotonic_ns']
                            elif d['monotonic_ns']>paced_baseline and (not snapshots or d['monotonic_ns']!=snapshots[-1]['monotonic_ns']):snapshots.append(d)
                    time.sleep(.03)
                check(generator.returncode==0,'client acceptance failed; private logs not published')
                c=load(root/'client.json');check(c['paced_ns']>=3_000_000_000 and len(snapshots)>=2,'steady export observations missing')
                check(snapshots[-1]['monotonic_ns']-snapshots[0]['monotonic_ns']>=1_000_000_000,'steady snapshot intervals missing')
                stop(router);check(router.returncode==0,'router failed to join cleanly')
                final=read_snapshot(root/'snapshot.json')['snapshot'];validate_snapshot(final);check(not final['running'] and len(final['workers'])==4 and final['event_sample_every']==1,'clean final snapshot/settings missing')
                check(all(w['capacity']==1 and w['ports']==[40000+2*i,40001+2*i] and w['input']['channel_capacity']==1 for i,w in enumerate(final['workers'])),'actual partition/queue configuration')
                totals={k:sum(w['core']['drops'][k] for w in final['workers']) for k in final['workers'][0]['core']['drops']}
                check(totals['Capacity']>=1 and totals['Policy']>=1 and totals['Filter']>=2,'adversarial core counters missing')
                check(sum(w['core']['expired'] for w in final['workers'])>=4,'idle expiry evidence missing')
                queue_drops=final['output']['dropped']+sum(w['input']['dropped'] for w in final['workers'])
                check(queue_drops>0,'offered burst did not establish router queue overload; no overload claim')
                lab.ns(lab.c,sys.executable,'-B',SCRIPT,'negative',tmp);check(load(root/'control.json')=={'no_delivery':True},'stopped path control')
                stop(srv);check(srv.returncode==0,'server failed')
                s=load(root/'server.json');verify_receipts(s)
                check(c['bindings']==[[a,12345] for a in addresses+[extra]],'actual source socket bindings')
                check(totals['Filter']>=s['wrong_address_sent']+s['wrong_port_sent']+s['late_sent'],'adversarial packets not accounted by actual filter counter')
                check(c['received']<=s['overload_seen']<=c['offered'],'overload endpoint conservation')
                result=dict(schema=1,kind='REAL-LINUX-WORKER-ACCEPTANCE',workers=4,guest_note='4 workers oversubscribe approved 2vCPU guest',
                            client=c,server=s,steady_snapshots=snapshots,final_snapshot=final,stopped_no_delivery=True)
            finally:
                for sig in previous:signal.signal(sig,signal.SIG_IGN)
                lab.cleanup()
        save(output,result);print('PASS: actual four-worker adversarial, overload, steady private export and stopped path gates')
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


def main():
    gate();args=sys.argv[1:]
    if args and args[0] in ('server','client','negative','launch'):
        action,*rest=args
        {'server':server,'client':client,'negative':negative,'launch':launch}[action](*rest);return
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('binary',type=Path);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args(args);check(a.binary.is_file() and os.access(a.binary,os.X_OK),'existing executable required')
    collect(a.binary,a.output)


if __name__=='__main__':main()
