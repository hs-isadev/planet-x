import assert from 'node:assert/strict';
import * as THREE from 'three';
import {orbitPose,cruisePose,cruiseDuration,orbitDuration} from '../web/camera-path.js';
import {chronological,sequenceSummary} from '../web/exposure-sequence.js';

const origin=new THREE.Vector3(),from=new THREE.Vector3(0,0,300),to=new THREE.Vector3(0,0,4.4);
let previous=Infinity;
for(let n=0;n<=1000;n++){
 const pose=orbitPose(from,origin,to,origin,n/1000),distance=pose.position.length();
 assert.ok(distance<=previous+1e-10);assert.ok(Number.isFinite(distance));previous=distance;
}
assert.ok(orbitPose(from,origin,to,origin,.8).position.length()<6,'The star becomes close well before the final frame');
assert.ok(orbitPose(from,origin,to,origin,.95).position.distanceTo(to)<.03,'The final approach decelerates');
assert.ok(orbitDuration(new THREE.Vector3(0,0,1e8),origin,to,origin)>10000,'Large scale changes receive more time');
const opposite=orbitPose(new THREE.Vector3(0,0,10),origin,new THREE.Vector3(0,0,-10),origin,.5);
assert.ok(opposite.position.length()>9.9,'Changing viewing sides follows an arc outside the body');

const start=new THREE.Vector3(1,2,3),end=new THREE.Vector3(1,2,-1e8),heading=end.clone().sub(start).normalize();
previous=start.clone();let maxStep=0;
for(let n=0;n<=1000;n++){
 const pose=cruisePose(start,end,heading,1,n/1000);
 assert.ok(pose.target.clone().sub(pose.position).normalize().dot(heading)>.999999,'Departure never turns back toward Earth');
 assert.ok(pose.position.distanceTo(end)<=previous.distanceTo(end)+1e-7);
 maxStep=Math.max(maxStep,pose.position.distanceTo(previous));previous=pose.position;
}
assert.ok(previous.distanceTo(end)<1e-7);assert.ok(maxStep<start.distanceTo(end)*.04,'No single sampled frame jumps across the journey');
assert.ok(cruisePose(start,end,heading,1,1).target.distanceTo(end)<3,'The focus distance shrinks on arrival so near clipping cannot hide the destination');
assert.ok(cruisePose(start,end,heading,1,.99).position.distanceTo(end)<.001,'Arrival slows over the final few radii');
assert.ok(cruiseDuration(1e8,1)>=20000);

// The UI must not silently reduce 364 observations to one detector's 36 frames.
const frames=Array.from({length:364},(_,i)=>({id:'real-fixture-'+i,index:i,mjd:60000+(363-i)/10,date:'2026-01-01',detector:i%6+1,status:i===7?'error':i===8?'pending':'ready'}));
const ordered=chronological(frames);assert.equal(ordered.length,364);
assert.ok(ordered.every((f,i)=>!i||f.mjd>=ordered[i-1].mjd));
assert.equal(new Set(ordered.map(f=>f.detector)).size,6);
const summary=sequenceSummary({frames},362);
assert.match(summary,/Full chronological/);assert.match(summary,/362 playable \/ 364/);assert.match(summary,/1 still loading/);assert.match(summary,/1 unavailable/);
assert.match(sequenceSummary({frames},36,'D1'),/Filtered chronological/);
console.log('PASS: forward-facing travel, gradual close approaches, safe orbit-camera arcs, and complete chronological exposure ordering.');
