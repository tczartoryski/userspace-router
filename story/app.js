'use strict';
const $=id=>document.getElementById(id);
let data, index=0, phase=0, timer;
const phaseCounts=[4,2,4,3];
const phaseDuration=4000; // 13 editorial substages, one bounded 52-second cycle.
const names=['Translation','Shared address','Policy','Recovery'];
const tuple=x=>x.join(':');
function render(){
 const c=data.clients, s=data.server;
 const chapters=[
 {title:'One request. Two identities.',claim:'The server sees the external tuple. The reply returns to the original kernel socket.',left:tuple(c[0].local),center:tuple(s[0].peer),right:tuple(s[0].local),ld:'Bound kernel UDP socket',cd:'Source observed by the server',rd:'Echo endpoint · TTL '+s[0].ttl,fact:'Reverse translation is captured.',detail:'The inside TUN packet has the original destination again. The client also receives the same fixture payload from the server.',receipt:data.inside.filter(p=>p.payload===c[0].payload).map(p=>`${p.direction.toUpperCase()}  ${tuple(p.src)} → ${tuple(p.dst)}\nTTL ${p.ttl} · ${p.payload}`).join('\n\n'),label:'OBSERVED / INSIDE TUN IP PACKETS'},
 {title:'Same port. Separate conversations.',claim:'Two internal addresses bind UDP port 12345. One external address carries both flows without collision.',left:c.slice(0,2).map(x=>tuple(x.local)).join('\n'),center:s.slice(0,2).map(x=>tuple(x.peer)).join('\n'),right:tuple(s[0].local),ld:'Two kernel sockets · same source port',cd:'Distinct ports observed at the server',rd:'Both requests delivered',fact:'A shared address preserves identity.',detail:'Both clients received their own fixture payload. The two external source ports differ; the internal source port is unchanged.',receipt:s.slice(0,2).map(x=>`${x.payload}\nobserved peer ${tuple(x.peer)}\nreply received by ${tuple(c[s.indexOf(x)].local)}`).join('\n\n'),label:'OBSERVED / ENDPOINT RECEIPTS'},
 {title:'A route can refuse the packet.',claim:'The /32 route to 198.51.100.3 selects inside egress. The router rejects inside-to-inside forwarding as Policy.',left:tuple(c[2].local),center:'Policy +'+data.runs[0].Policy,right:tuple(c[2].remote),ld:'Actual blocked UDP send',cd:'Final counter · first router process',rd:'Bound server socket · no delivery',fact:'Allowed traffic passes. Blocked traffic drops.',detail:'The allowed endpoint received two requests. The blocked fixture appears only at the inside TUN, the client times out, and the final Policy counter is exactly one.',receipt:`blocked fixture: ${c[2].payload}\nclient timed out: ${c[2].timed_out}\nserver deliveries: ${s.filter(x=>x.payload===c[2].payload).length}\noutside packets: ${data.outside.filter(x=>x.payload===c[2].payload).length}\nPolicy: ${data.runs[0].Policy}`,label:'OBSERVED / NEGATIVE CONTROL'},
 {title:'Stop the router. Break the path.',claim:'The same topology fails with the forwarding process stopped. A fresh process restores the real UDP exchange.',left:tuple(c[3].local),center:'STOP → RESTART',right:tuple(c[4].remote),ld:'Same source and destination tuples',cd:'Fresh ready log checked before retry',rd:'Kernel endpoint remains running',fact:'Failure, then recovery.',detail:'The stopped request times out with no server delivery. After restart, the server sees SNAT again and the client receives its reply; inside TUN capture verifies its destination.',receipt:`STOPPED · ${c[3].payload}\ntimeout: ${c[3].timed_out}\n\nRECOVERED · ${s[2].payload}\nserver peer: ${tuple(s[2].peer)}\nreply to: ${tuple(c[4].local)}\nreply TTL: ${c[4].ttl}`,label:'OBSERVED / PROCESS CONTROL'}];
 const x=chapters[index];
 const replyOutside=data.outside.find(p=>p.payload===c[0].payload&&p.direction==='outgoing');
 const replyInside=data.inside.find(p=>p.payload===c[0].payload&&p.direction==='incoming');
 const captions=[
 ['REQUEST · Before translation: the original bound socket.', 'REQUEST · After SNAT: the server observes the external source.', 'REPLY ← Outside destination: '+tuple(replyOutside.dst), 'REPLY ← Reverse translation: inside destination '+tuple(replyInside.dst)],
 ['CLIENT A · '+tuple(c[0].local)+' → '+tuple(s[0].peer), 'CLIENT B · '+tuple(c[1].local)+' → '+tuple(s[1].peer)+' · same source port, distinct external port'],
 ['ALLOWED → Request to '+tuple(c[0].remote), 'DELIVERED · Server receipt and client echo verified.', 'POLICY → Route selects inside egress; forwarding rejected.', 'DROPPED · Client timeout; no server delivery or outside packet.'],
 ['RUNNING → Initial request and reply verified.', 'STOPPED · Same tuple times out; no server delivery.', 'RESTARTED → Fresh process; server receipt and client reply verified.']
 ];
 $('phaseCaption').textContent=captions[index][phase];
 $('chapter').dataset.chapter=String(index+1);$('chapter').dataset.phase=String(phase+1);
 $('chapter').dataset.direction=index===0&&phase>=2?'reply':'request';
 $('chapter').dataset.outcome=index===2&&phase>=2?'dropped':index===3&&phase===1?'stopped':'delivered';
 document.querySelectorAll('.node').forEach((node,i)=>node.classList.toggle('active',i===(index===0?[0,1,1,0][phase]:index===1?phase:phase%3)));
 document.querySelectorAll('.arrow span').forEach(el=>el.textContent=index===0&&phase>=2?'←':index===2&&phase===3||index===3&&phase===1?'×':'→');
 if(index===0&&phase>=2){x.left=tuple(replyInside.dst);x.center=tuple(replyOutside.dst);x.right=tuple(replyOutside.src);x.ld='REPLY · inside destination';x.cd='REPLY · outside destination';x.rd='Reply source · kernel server';}
 if(index===1){x.left=tuple(c[phase].local);x.center=tuple(s[phase].peer);x.ld='Client '+(phase===0?'A':'B')+' · bound source port 12345';x.cd='Observed external source · distinct port';}
 if(index===2){x.center=['ALLOWED','DELIVERED','POLICY','DROPPED'][phase];if(phase<2){x.left=tuple(c[0].local);x.right=tuple(s[0].local);x.ld='Observed allowed request';x.cd='Server receipt and client echo';x.rd='Delivered endpoint';}}
 if(index===3){x.center=['RUNNING','STOPPED','RESTARTED'][phase];x.cd=phase===1?'Client timeout · no delivery':'Verified endpoint reply';}
 $('phasePrev').disabled=phase===0;$('phaseNext').disabled=phase===phaseCounts[index]-1;
 for(const [id,value] of Object.entries({number:`0${index+1} / 04 · ${names[index].toUpperCase()}`,title:x.title,claim:x.claim,left:x.left,center:x.center,right:x.right,leftDetail:x.ld,centerDetail:x.cd,rightDetail:x.rd,fact:x.fact,detail:x.detail,receipt:x.receipt,receiptLabel:x.label,progress:`${index+1} / 4 · ${timer?'Autoplay replay':'Manual replay'}`}))$(id).textContent=value;
 [...$('dots').children].forEach((el,i)=>el.setAttribute('aria-current',String(i===index)));
}
function stop(){clearTimeout(timer);timer=undefined;}
function move(n){if(data){stop();index=(n+4)%4;phase=0;setState('manual');render();}}
function setState(state){$('chapter').dataset.sequenceState=state;$('play').textContent=state==='running'?'Pause':'Start 52s replay';}
function advance(){
 timer=undefined;
 if(phase+1<phaseCounts[index])phase++;
 else if(index<3){index++;phase=0;}
 else {setState('complete');render();$('phaseCaption').textContent='FINISHED · Translation, distinct ports, policy and recovery verified.';$('progress').textContent='Complete · 52-second editorial replay';return;}
 timer=setTimeout(advance,phaseDuration);render();
}
$('prev').onclick=()=>move(index-1);$('next').onclick=()=>move(index+1);
$('phasePrev').onclick=()=>{stop();phase=Math.max(0,phase-1);setState('manual');render();};
$('phaseNext').onclick=()=>{stop();phase=Math.min(phaseCounts[index]-1,phase+1);setState('manual');render();};
$('play').onclick=()=>{if(!data)return;if(timer){stop();setState('paused');render();return;}index=0;phase=0;setState('running');timer=setTimeout(advance,phaseDuration);render();};
names.forEach((name,i)=>{const b=document.createElement('button');b.textContent=`0${i+1}`;b.setAttribute('aria-label',name);b.onclick=()=>move(i);$('dots').append(b);});
document.addEventListener('keydown',e=>{if(e.target.tagName==='BUTTON')return;if(e.key==='ArrowRight')$('phaseNext').click();if(e.key==='ArrowLeft')$('phasePrev').click();});
fetch('/observations.json',{cache:'no-store',signal:AbortSignal.timeout(4000)}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{data=d;setState('ready');render();}).catch(()=>{$('claim').textContent='Verified evidence unavailable. Run the isolated Linux collector first.';$('chapter').dataset.sequenceState='unavailable';$('progress').textContent='Unavailable';});
