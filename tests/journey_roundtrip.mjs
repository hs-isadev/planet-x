import assert from 'node:assert/strict';
import * as THREE from 'three';
import {ObservatoryScene} from '../web/scene.js';
import {cruisePose} from '../web/camera-path.js';

const solar={date:'2026-11-10',objects:[{id:'sun',name:'Sun',xyz_au:[0,0,0]},{id:'earth',name:'Earth',xyz_au:[1,0,0]}]};
const star={id:'barnard',name:"Barnard's Star",xyz_pc:[2,0,0],planets:[{star_radius_solar:.185}]};
const stars={objects:[star]};
function makeView(mode){
 const view=Object.create(ObservatoryScene.prototype);
 Object.assign(view,{camera:new THREE.PerspectiveCamera(),controls:{target:new THREE.Vector3(),enabled:true},renderer:{domElement:{style:{}}},reduced:false,mode,selected:mode==='solar'?'sun':'barnard',solarData:solar,starsData:stars,items:[],stopFlight(){},beaconLabel:null});
 view.solar=async data=>{view.mode='solar';view.solarData=data;view.local=null;view.items=data.objects.map(d=>({data:d,pos:view.vector(d.xyz_au),radius:d.id==='earth'?.01:.1}));};
 view.stars=data=>{view.mode='stars';view.starsData=data;view.local=null;view.items=data.objects.map(d=>({data:d,pos:view.vector(d.xyz_pc),radius:0}));};
 view.exitLocal=()=>{view.local=null;};
 view.scaleTransition=async fn=>fn();
 view.stellarCloseup=item=>{view.local={item,planets:item.data.planets};view.companionsReady=Promise.resolve();};
 view.fly=async(target,position)=>{view.camera.position.copy(position);view.controls.target.copy(target);return true;};
 view.turnLeftTo=async heading=>{view.controls.target.copy(view.camera.position).add(heading);return true;};
 view.flyForward=async(position,heading,clearance)=>{
  const from=view.camera.position.clone();
  for(const progress of [0,.1,.5,.9,1]){
   const pose=cruisePose(from,position,heading,clearance,progress);
   assert.ok(pose.target.clone().sub(pose.position).normalize().dot(heading)>.99999);
   view.camera.position.copy(pose.position);view.controls.target.copy(pose.target);
  }
  return true;
 };
 return view;
}

const context={direction_ecliptic:[1,0,0]};
for(const mode of ['solar','stars']){
 const view=makeView(mode);
 if(mode==='solar'){await view.solar(solar);view.camera.position.set(0,.2,.5);}
 else{view.stars(stars);view.stellarCloseup(view.items[0]);view.camera.position.set(0,.15,44);}
 const saved=view.camera.position.clone(),target=view.controls.target.clone();
 assert.equal(await view.trace(context,solar,()=>{}),true);
 assert.equal(view.mode,'solar');assert.equal(view.selected,'earth');
 assert.ok(view.controls.target.distanceTo(view.items.find(i=>i.data.id==='earth').pos)<1e-10);
 view.stayOnEarth();assert.equal(view.journey,false);assert.equal(view.controls.enabled,true);assert.ok(view.traceReturn);
 assert.equal(await view.returnFromTrace(),true);
 assert.equal(view.mode,mode);assert.equal(view.selected,mode==='solar'?'sun':'barnard');
 assert.ok(view.camera.position.distanceTo(saved)<1e-8,'The saved viewpoint is restored by the return path');
 assert.ok(view.controls.target.distanceTo(target)<1e-8);
 assert.equal(view.traceReturn,null);assert.equal(view.controls.enabled,true);
 if(mode==='stars')assert.equal(view.local.item.data.id,'barnard');
}

const cancelled=makeView('stars');cancelled.stars(stars);cancelled.stellarCloseup(cancelled.items[0]);cancelled.camera.position.set(0,0,30);
cancelled.flyForward=async()=>{cancelled.travelToken++;return false;};
assert.equal(await cancelled.trace(context,solar,()=>{}),false);
await cancelled.cancelTrace();assert.equal(cancelled.mode,'stars');assert.equal(cancelled.selected,'barnard');assert.equal(cancelled.journey,false);assert.equal(cancelled.controls.enabled,true);
console.log('PASS: solar and stellar journeys reach Earth, support staying, return to the saved viewpoint, and recover from cancellation.');
