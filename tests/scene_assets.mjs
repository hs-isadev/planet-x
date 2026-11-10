import assert from 'node:assert/strict';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {ObservatoryScene} from '../web/scene.js';

const elements=new Map();
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{hidden:false,replaceChildren(){}});return elements.get(id);}};
globalThis.window=new EventTarget();
globalThis.fetch=async()=>({ok:true,json:async()=>({rows:[]})});
const view=Object.create(ObservatoryScene.prototype);
Object.assign(view,{
 version:0,scene:new THREE.Scene(),content:new THREE.Group(),camera:new THREE.PerspectiveCamera(),
 ambient:{},light:{},controls:{},renderer:{capabilities:{getMaxAnisotropy:()=>8}},items:[],showPaths:true,
 clear(){this.version++;this.content.clear();this.items=[];this.orbits=new THREE.Group();this.content.add(this.orbits);},
 label(data,pos,radius,mesh){this.items.push({data,pos,radius,mesh});},
 installTravelDust(){},loadContextSky(){}
});
let textureReady,modelReady;
THREE.TextureLoader.prototype.loadAsync=()=>new Promise(resolve=>{textureReady=resolve;});
GLTFLoader.prototype.loadAsync=()=>new Promise(resolve=>{modelReady=resolve;});
const data={objects:[
 {id:'earth',xyz_au:[1,0,0],radius_km:6371,texture:'/assets/earth.png'},
 {id:'saturn',xyz_au:[9,0,0],radius_km:58232,model:'/assets/saturn.glb'}
]};
let done=false;
const loading=view.solar(data).then(()=>{done=true;});
await Promise.resolve();assert.equal(done,false);
textureReady(new THREE.Texture());await Promise.resolve();await Promise.resolve();assert.equal(done,false,'A loaded texture must not reveal an unfinished model');
const model=new THREE.Group();model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial()));
modelReady({scene:model});await loading;
assert.equal(done,true);assert.ok(view.items.find(i=>i.data.id==='saturn').model);assert.equal(view.items.find(i=>i.data.id==='saturn').mesh.visible,false);

THREE.TextureLoader.prototype.loadAsync=async()=>{throw Error('Unavailable texture');};
await view.solar({objects:[{id:'earth',xyz_au:[1,0,0],radius_km:6371,texture:'/missing.png'}]});
assert.match(view.items[0].data.asset_error,/unavailable/);assert.equal(view.items[0].mesh.visible,true,'Failed maps leave the explicit neutral geometry fallback');
console.log('PASS: scene readiness waits for both textures and models and handles unavailable assets explicitly.');
