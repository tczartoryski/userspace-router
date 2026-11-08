'use strict';
// Controlled DOM and clock: no browser rendering or live-evidence claim.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const data=JSON.parse(execFileSync('python3',['-B','-c','import sys,json;sys.path.insert(0,"scripts");from test_nat_story import fixture;print(json.dumps(fixture()))'],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
const elements=new Map();
function element(){return {textContent:'',dataset:{},children:[],classList:{toggle(){}},setAttribute(){},append(x){this.children.push(x);}};}
const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
let pending,elapsed=0;
const context={document:{getElementById:get,querySelectorAll:()=>[element(),element(),element()],createElement:element,addEventListener(){}},AbortSignal:{timeout(){}},fetch:async()=>({ok:true,json:async()=>data}),setTimeout(fn,ms){assert.equal(ms,4000);pending=fn;return 1;},clearTimeout(){pending=undefined;}};
vm.runInNewContext(fs.readFileSync('story/app.js','utf8'),context);
setImmediate(()=>{
 assert.equal(get('chapter').dataset.sequenceState,'ready');
 get('play').onclick();
 const states=[];
 while(pending){states.push([get('chapter').dataset.chapter,get('chapter').dataset.phase]);const fn=pending;pending=undefined;elapsed+=4000;fn();assert.ok(elapsed<=52000);}
 assert.equal(states.length,13);assert.equal(new Set(states.map(String)).size,13);
 assert.equal(elapsed,52000);assert.equal(get('chapter').dataset.sequenceState,'complete');
 assert.match(get('phaseCaption').textContent,/FINISHED/);
 get('play').onclick();get('play').onclick();assert.equal(pending,undefined);assert.equal(get('chapter').dataset.sequenceState,'paused');
 get('next').onclick();assert.equal(get('chapter').dataset.chapter,'2');get('phaseNext').onclick();assert.equal(get('chapter').dataset.phase,'2');assert.equal(get('center').textContent,'198.51.100.1:40001');
 get('prev').onclick();get('phaseNext').onclick();get('phaseNext').onclick();assert.equal(get('chapter').dataset.direction,'reply');assert.equal(get('center').textContent,'198.51.100.1:40000');
 get('phaseNext').onclick();assert.equal(get('left').textContent,'10.0.0.2:12345');
 console.log('PASS: 13 unique substages, 52s finite cycle, completion, restart/pause and manual reply/port controls');
});
