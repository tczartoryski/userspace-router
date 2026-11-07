'use strict';
let latest;
const $ = id => document.getElementById(id);
function cards(id, values) { $(id).replaceChildren(...Object.entries(values).map(([label, value]) => { const el=document.createElement('div'); el.className='card'; const n=document.createElement('strong'); n.textContent=value; el.append(n,document.createTextNode(label)); return el; })); }
function rows(id, values) { $(id).replaceChildren(...values.map(row => { const tr=document.createElement('tr'); row.forEach(value => {const td=document.createElement('td');td.textContent=value;tr.append(td);});return tr;})); }
function render(data) {
 latest=data; $('status').textContent=data.state.toUpperCase();
 const s=data.snapshot;
 if(!s){$('age').textContent='Runtime unavailable. No current metrics.';cards('cards',{});cards('drops',{});rows('routes',[]);rows('mappings',[]);$('interfaces').textContent='Unavailable';$('mapping-note').textContent='';return;}
 $('age').textContent=`Snapshot age: ${data.age_seconds}s · uptime: ${s.uptime_seconds}s. ${data.state==='current'?'Live process snapshot.':'Last observed data; not current.'}`;
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
