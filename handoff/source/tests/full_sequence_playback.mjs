import fs from 'node:fs';
import assert from 'node:assert/strict';
import {ObservationDrawer} from '../web/observations.js';
import {installEpochCompare} from '../web/epoch-compare.js';
assert.match(fs.readFileSync('web/index.html','utf8'),/<option value="100" selected>10 frames\/s<\/option>/);
const elements=new Map();
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,hidden:false,textContent:'',setAttribute(){}});return elements.get(id);}};
const $=id=>document.getElementById(id),queue=[];
globalThis.setTimeout=(fn,delay)=>{queue.push({fn,delay});return queue.length;};
globalThis.clearTimeout=()=>{};
const frames=Array.from({length:50},(_,i)=>({id:'fixture-'+i,index:i,status:'ready',mjd:60000+i,detector:i%6+1,wavelength_um:1+i*.05}));
const shown=[],prefetched=[];
const view=Object.create(ObservationDrawer.prototype);
Object.assign(view,{jobId:'test-only',job:{frames},frames,position:0,imageRequests:new Map(),prefetchQueue:[],prefetchInFlight:0,playToken:0,playing:false,polling:true,icon:x=>x,api:async()=>({}),refreshFrames(){this.frames=this.job.frames;},async show(){shown.push(this.current().index);this.prefetchPlayback();},imageURL:index=>'frame-'+index,imageLoad:async function(url){prefetched.push(url);this.imageRequests.set(url,{});}});
installEpochCompare(view);
await $('compare-epochs').onclick();
assert.equal($('speed').value,'100');assert.equal($('group').value,'all');assert.equal($('red-changes').checked,true);
while(queue.length){const item=queue.shift();assert(item.delay<=100);await item.fn();}
assert.deepEqual(shown,frames.map(f=>f.index),'Every exposure is shown once, including all detectors, without endpoint-only jumps');
assert(prefetched.includes('frame-49'));assert.equal(view.playing,false);

const buffer=Object.create(ObservationDrawer.prototype);
const pending=new Map(),requested=[];
let active=0,peak=0;
Object.assign(buffer,{
 jobId:'test-only',job:{frames},frames,position:0,prefetchInFlight:0,imageRequests:new Map(),
 imageURL(index,updateLabels){assert.equal(updateLabels,false);return 'frame-'+index;},
 imageLoad(url,background){
  assert.equal(background,true);
  requested.push(url);
  peak=Math.max(peak,++active);
  const promise=new Promise(resolve=>pending.set(url,()=>{active--;resolve();}));
  this.imageRequests.set(url,{promise});
  return promise;
 }
});
async function finishBuffer(){
 while(pending.size){
  const batch=[...pending.values()];
  pending.clear();
  batch.forEach(finish=>finish());
  await new Promise(resolve=>setImmediate(resolve));
 }
}
buffer.prefetchPlayback();
assert.deepEqual(requested,['frame-1','frame-2','frame-3','frame-4']);
await finishBuffer();
assert.deepEqual(requested,frames.slice(1,25).map(f=>'frame-'+f.index));
assert.equal(peak,4);
buffer.position=48;
buffer.prefetchPlayback();
await finishBuffer();
assert.equal(requested.length,25);
assert.equal(requested.at(-1),'frame-49');
$('loop').checked=true;
buffer.prefetchPlayback();
await finishBuffer();
assert.equal(requested.at(-1),'frame-0');
buffer.position=25;
$('observations').hidden=true;
buffer.prefetchPlayback();
assert.equal(pending.size,0);
console.log('PASS: full 50-frame chronological playback at requested 10 fps; all bands retained, lookahead buffering, automatic residual overlay.');
