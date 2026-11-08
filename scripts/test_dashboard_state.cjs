'use strict';
// Controlled DOM fixtures: contract checks only, not browser/live-data evidence.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function el(){return {textContent:'',children:[],checked:true,replaceChildren(...v){this.children=v;},append(...v){this.children.push(...v);},addEventListener(){}};}
const get=id=>{if(!elements.has(id))elements.set(id,el());return elements.get(id);};
const context=vm.createContext({document:{getElementById:get,createElement:el,createTextNode:v=>({textContent:v})},fetch:()=>new Promise(()=>{}),setInterval(){},AbortSignal:{timeout(){}}});
vm.runInContext(fs.readFileSync('dashboard/app.js','utf8'),context);
const q={occupancy:0,capacity:3,high_water:1,dropped:0,shutdown_drops:0};
const snapshot={schema:2,backend:'tun-poll',unix_seconds:100,uptime_seconds:1,interfaces:['tun-in','tun-out'],
 io_drops:0,event_sample_every:0,dispatcher:{received:0,drops:{Filter:0}},output:q,tx:{packets:2,would_block:0},
 rates:{tx_pps:2,tx_ip_mbps:.001,core_forwarded_pps:2},workers:[0,1].map(id=>({id,ports:[40000+id*2,40001+id*2],capacity:2,observed_ns:100,core:{active:1,received:1,forwarded:1,drops:{Filter:0}},input:q,events:[]}))};
context.data={state:'current',age_seconds:0,snapshot};vm.runInContext('render(data)',context);
assert.equal(get('workers').children.length,2);assert.equal(get('queue-bars').children.length,2);assert.match(get('mode').textContent,/regressed/);
context.data.state='stale';vm.runInContext('render(data)',context);assert.ok(get('cards').children.some(c=>c.children[0].textContent==='Unavailable'));
vm.runInContext("render({state:'offline'})",context);assert.equal(get('workers').children.length,0);assert.equal(get('queue-bars').children.length,0);assert.equal(get('mode').textContent,'Unavailable');
context.data={state:'current',age_seconds:0,snapshot:{schema:1,uptime_seconds:1,io_drops:0,interfaces:['tun-in','tun-out'],core:{received:1,forwarded:1,active:1,expired:0,routes:[],mappings:[],max_flows:1,ports:[40000,40000],idle_seconds:10,drops:{Filter:0}}}};
vm.runInContext('render(data)',context);assert.equal(get('mode').textContent,'Reference snapshot');assert.equal(get('workers').children.length,0);
console.log('PASS: schema 1/2 rendering, actual queue meters, stale rates and offline clearing');
