'use strict';
let latest;
const $ = id => document.getElementById(id);
function cards(id, values) { $(id).replaceChildren(...Object.entries(values).map(([label, value]) => { const el=document.createElement('div'); el.className='card'; const n=document.createElement('strong'); n.textContent=value; el.append(n,document.createTextNode(label)); return el; })); }
function rows(id, values) { $(id).replaceChildren(...values.map(row => { const tr=document.createElement('tr'); row.forEach(value => {const td=document.createElement('td');td.textContent=value;tr.append(td);});return tr;})); }
function render(data) {
 latest=data; $('status').textContent=data.state.toUpperCase();
 const s=data.snapshot;
 rows('workers',[]);rows('events',[]);cards('queues',{});$('queue-bars').replaceChildren();$('mode').textContent=s?'Reference snapshot':'Unavailable';$('sampling').textContent='';
 if(!s){$('age').textContent='Runtime unavailable. No current metrics.';cards('cards',{});cards('drops',{});rows('routes',[]);rows('mappings',[]);$('interfaces').textContent='Unavailable';$('mapping-note').textContent='';return;}
 $('age').textContent=`Snapshot age: ${data.age_seconds}s · uptime: ${s.uptime_seconds}s. ${data.state==='current'?'Live process snapshot.':'Last observed data; not current.'}`;
 if(s.schema===2){$('interfaces').textContent=`Inside: ${s.interfaces[0]} → Outside: ${s.interfaces[1]}`;parallel(data);return;}
 cards('cards',{'Received':s.core.received,'Forwarded':s.core.forwarded,'Active flows':s.core.active,'Expired':s.core.expired,'I/O drops':s.io_drops});
 $('interfaces').textContent=`Inside: ${s.interfaces[0]} → Outside: ${s.interfaces[1]}`;
 rows('routes',s.core.routes.map(r=>[r.network,r.side]));
 const hide=$('redact').checked;
 rows('mappings',s.core.mappings.map(m=>[hide?'Hidden':m.internal,hide?'Hidden':m.remote,hide?'Hidden':m.external,m.idle_seconds]));
 $('mapping-note').textContent=`Limit: ${s.core.max_flows} flows · ports ${s.core.ports.join('–')} · idle expiry ${s.core.idle_seconds}s${s.core.mappings_truncated?' · list truncated to 2048 mappings':''}`;
 cards('drops',s.core.drops);
}
async function refresh(){try{const response=await fetch('/api/snapshot',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error();render(await response.json());}catch{render({state:'offline'});}}
$('refresh').addEventListener('click',refresh);$('redact').addEventListener('change',()=>{if(latest)render(latest);});refresh();setInterval(refresh,2000);

function parallel(data) {
 const s=data.snapshot;
 $('mode').textContent=`${s.backend} · ${s.workers.length} workers · private aggregate schema 2. Reference mode remains default; multicore throughput and p99 regressed in measured comparisons.`;
 const received=s.dispatcher.received+s.workers.reduce((n,w)=>n+w.core.received,0);
 const forwarded=s.workers.reduce((n,w)=>n+w.core.forwarded,0);
 cards('cards',{'Core received':received,'Core forwarding decisions':forwarded,'Actual TUN writes':s.tx.packets,'I/O + queue drops':s.io_drops,'TX packets/s':data.state==='current'&&s.rates.tx_pps!==null?s.rates.tx_pps.toFixed(1):'Unavailable','Core decisions/s':data.state==='current'&&s.rates.core_forwarded_pps!==null?s.rates.core_forwarded_pps.toFixed(1):'Unavailable','TX IP Mbps':data.state==='current'&&s.rates.tx_ip_mbps!==null?s.rates.tx_ip_mbps.toFixed(3):'Unavailable'});
 rows('workers',s.workers.map(w=>[w.id,w.ports.join('–'),`${w.core.active}/${w.capacity}`,w.core.received,w.core.forwarded,`${w.input.occupancy}/${w.input.capacity}`,w.input.high_water,w.input.dropped,w.input.shutdown_drops,(w.observed_ns/1e9).toFixed(3)]));
 cards('queues',{'Output pending':s.output.occupancy,'Output high water':s.output.high_water,'Output drops':s.output.dropped,'Output shutdown drops':s.output.shutdown_drops,'TX WouldBlock':s.tx.would_block});
 const totals={...s.dispatcher.drops};s.workers.forEach(w=>Object.keys(totals).forEach(k=>totals[k]+=w.core.drops[k]));cards('drops',totals);
 rows('routes',[]);rows('mappings',[]);$('mapping-note').textContent='Schema 2 omits all tuples and payloads. Input pending includes the worker in-flight packet. Per-worker reports are periodic, not simultaneous.';
 rows('events',s.workers.flatMap(w=>w.events.map(e=>[w.id,(e.monotonic_ns/1e9).toFixed(3),e.direction,e.reason,e.bytes])));
 $('sampling').textContent=s.event_sample_every?`Every ${s.event_sample_every} worker decisions; newest 64 per worker. Not a packet trace.`:'Decision sampling disabled.';
 // Native meter charts display the same actual queue observations as the table.
 $('queue-bars').replaceChildren(...s.workers.map(w=>{const label=document.createElement('label');label.textContent=`Worker ${w.id} pending `;const meter=document.createElement('meter');meter.min=0;meter.max=w.input.capacity;meter.value=w.input.occupancy;label.append(meter);const drops=document.createElement('meter');drops.min=0;drops.max=Math.max(1,w.input.admitted+w.input.dropped);drops.value=w.input.dropped+w.input.shutdown_drops;label.append(document.createTextNode(' dropped attempts '),drops);return label;}));
}
