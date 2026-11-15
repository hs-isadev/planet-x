import assert from 'node:assert/strict';
import fs from 'node:fs';
import {ObservationDrawer} from '../web/observations.js';

// An isolated DOM fixture checks the real entry module without requiring WebGL
// or a live catalog. No fixture response is part of the served application.
class Element {
 constructor(){this.style={};this.dataset={};this.hidden=false;this.checked=false;this.value='';this.children=[];this.options=[];this.selectedOptions=[];this.attributes={};this.classList={add(){},remove(){},contains(){return false;},toggle(){}};}
 addEventListener(){}
 getContext(){return {clearRect(){},fillRect(){}};}
 setAttribute(name,value){this.attributes[name]=value;}
 append(...children){this.children.push(...children);}
 after(...children){this.siblings=children;}
 set innerHTML(html){for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element());}
 replaceChildren(...children){this.children=children;}
 closest(){return new Element();}
 querySelector(){return new Element();}
 querySelectorAll(){return [];}
}
const html=fs.readFileSync('web/index.html','utf8'),elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
const classes=new Set(['observing']);
const body=new Element();body.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c){classes.has(c)?classes.delete(c):classes.add(c);}};
globalThis.document={body,documentElement:{dataset:{}},activeElement:{tagName:'BODY'},getElementById:id=>elements.get(id),createElement:()=>new Element(),querySelectorAll:()=>[],querySelector:()=>new Element(),addEventListener(){}};
globalThis.window=new EventTarget();
globalThis.Option=class extends Element{constructor(text,value){super();this.textContent=text;this.value=value;}};
globalThis.MutationObserver=class{observe(){}};
globalThis.localStorage={getItem:()=>null};
globalThis.location={search:'',href:'http://127.0.0.1:8000/'};
globalThis.matchMedia=()=>{throw Error('WebGL deliberately unavailable in the startup test');};
let releaseCatalog;
globalThis.fetch=async url=>{
 if(url==='/api/examples/vesta')return {ok:false,status:503,json:async()=>({detail:'Starter archive temporarily unavailable'})};
 assert.equal(url,'/api/presets');
 return new Promise(resolve=>{releaseCatalog=()=>resolve({ok:true,json:async()=>[]});});
};
let timeout;
await Promise.race([
 import('../web/app.js'),
 new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Startup is blocked by an unresolved catalog request')),2000);})
]);
clearTimeout(timeout);
assert.ok(window.parallax,'The app finishes startup while the catalog is pending');
assert.equal(typeof elements.get('universe-home').onclick,'function');
assert.equal(typeof elements.get('observation-close').onclick,'function');
assert.equal(typeof releaseCatalog,'function');
await elements.get('universe-home').onclick();
assert.equal(classes.has('observing'),false,'The 3D control leaves the image workspace immediately');
assert.equal(elements.get('observations').hidden,true);
assert.match(elements.get('scene-message').textContent,/3D is unavailable/,'WebGL failures are presented explicitly');
releaseCatalog();await new Promise(resolve=>setTimeout(resolve,0));

// Exercise the actual image-display method as well as parsing its module.
const frame={id:'exposure',index:0,mjd:61000,date:'2026-01-01',band:'D1',release:'test-fixture',status:'ready'};
const view=Object.create(ObservationDrawer.prototype);let draws=0;
Object.assign(view,{frames:[frame],position:0,job:{frames:[frame],fov:8},loadToken:0,imageURL:()=>'/test-frame',imageLoad:async()=>({width:80,height:80}),draw(){draws++;},colorbar(){},overlays(){}});
elements.get('group').value='all';elements.get('compare-mode').value='single';elements.get('observations').hidden=false;
await view.show();
assert.equal(view.loadedURL,'/test-frame');assert.equal(elements.get('image-empty').hidden,true);assert.ok(draws>0);
assert.match(elements.get('sequence-note').textContent,/Full chronological/);
console.log('PASS: real entry-module startup, navigation during pending catalog requests, visible initialization errors, and observed-frame display.');
