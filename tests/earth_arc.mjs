import assert from 'node:assert/strict';
import * as THREE from 'three';
import {earthArcPose,surfacePose} from '../web/earth-flight.js';
for(const start of [new THREE.Vector3(60,4,-2),new THREE.Vector3(-60,3,4),new THREE.Vector3(1,60,0),new THREE.Vector3(1,-60,0)]){
 const earth=new THREE.Vector3(1,0,0),radius=.01;let previous=Infinity;
 for(let i=0;i<=1000;i++){const p=earthArcPose(start,earth,radius,i/1000),r=p.position.distanceTo(earth);assert.ok(p.position.toArray().every(Number.isFinite));assert.ok(r>=6.5*radius-1e-9);assert.ok(r<=previous+1e-8);previous=r;}
 const first=earthArcPose(start,earth,radius,0),end=earthArcPose(start,earth,radius,1);assert.ok(first.position.distanceTo(start)<1e-9);assert.ok(Math.abs(end.position.distanceTo(earth)/radius-6.5)<1e-8);assert.ok(end.position.clone().sub(earth).normalize().dot(earth.clone().negate().normalize())>.98);
}
for(const start of [new THREE.Vector3(0,0,20),new THREE.Vector3(-10,0,0),new THREE.Vector3(1.3,0,0)])for(let i=0;i<=100;i++){
 const p=surfacePose(start,new THREE.Vector3(),1,new THREE.Vector3(40,0,0),i/100);assert.ok(p.position.length()>=1.22-1e-9);
}
console.log('PASS: continuous arc starts exactly at entry, descends outside Earth, ends at 6.5 radii on the lit side, and surface paths stay outside the source.');
