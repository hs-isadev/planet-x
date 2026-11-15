import assert from 'node:assert/strict';
import * as THREE from 'three';
import {ObservatoryScene} from '../web/scene.js';

// Exercise a real animation frame, including the asynchronously loaded backdrop.
// A render failure here used to leave the WebGL image frozen while labels moved.
const elements=new Map();
globalThis.document={
  activeElement:{id:''},
  getElementById(id){
    if(!elements.has(id))elements.set(id,{textContent:'',style:{}});
    return elements.get(id);
  }
};
let scheduled=0;
globalThis.requestAnimationFrame=()=>{scheduled++;};
const view=Object.create(ObservatoryScene.prototype);
let renders=0;
Object.assign(view,{
  scene:new THREE.Scene(),camera:new THREE.PerspectiveCamera(38,1,.001,100000),
  controls:{target:new THREE.Vector3(),update(){view.camera.updateMatrixWorld();}},
  renderer:{render(){renders++;},domElement:{style:{}}},
  mode:'solar',w:800,h:800,items:[],activityEnabled:true,activityTime:0,
  navigationTick(){},makeHalo:()=>new THREE.Sprite(new THREE.SpriteMaterial())
});
view.camera.position.set(0,2,3);
view.camera.lookAt(0,0,0);
const mesh=new THREE.Mesh(new THREE.SphereGeometry(.1),new THREE.MeshBasicMaterial());
view.scene.add(mesh);
const label={hidden:false,style:{},offsetWidth:100};
view.items.push({data:{id:'sun'},pos:new THREE.Vector3(),radius:.1,mesh,label});
view.selected='sun';view.showLabels=true;

view.animate();
assert.equal(renders,1,'Frame renders before the catalog arrives');
view.addCatalogSky({objects:Array.from({length:8},(_,i)=>({id:'host:'+i,name:'Catalog star '+i,xyz_pc:[1+i,2+i,3+i],ra:60,dec:53,distance_pc:4+i,phot_g_mean_mag:6}))});
const points=view.sky.children[0];
assert.equal(view.sky.children.length,1,'Backdrop uses a single point batch');
assert.equal(points.userData.catalogEntries.length,2,'Crowded angular cells retain at most two actual catalog rows');
const firstPoint=()=>new THREE.Vector3().fromArray(points.geometry.attributes.position.array,0);
view.animate();
assert.equal(renders,2,'Frame renders after the catalog arrives');
assert.ok(Math.abs(firstPoint().length()-3000)<1e-3);
assert.ok(view.sky.position.equals(view.camera.position));
const previousLabel=label.style.transform;
view.camera.position.set(1,3,4);
view.camera.lookAt(0,0,0);
view.controls.target.set(.1,0,0);
view.camera.lookAt(view.controls.target);
view.animate();
assert.equal(renders,3,'Camera changes still reach the renderer');
assert.notEqual(label.style.transform,previousLabel);
assert.ok(Math.abs(firstPoint().length()-3000)<1e-3);
assert.ok(view.sky.position.equals(view.camera.position));

view.mode='stars';view.local={item:{data:{id:'host:0',name:'Catalog star 0'},pos:new THREE.Vector3(1,3,-2)}};
view.animate();
assert.equal(renders,4,'Stellar closeups still render');
assert.equal(firstPoint().length(),0,'The selected star is omitted from its own backdrop');
assert.equal(label.hidden,true);
view.surface={update(){}};view.sky.userData.update();
assert.equal(view.sky.visible,false,'The catalog is hidden during terrain exploration');
assert.equal(scheduled,4);
view.surface=null;view.local=null;view.beaconLabel={style:{},remove(){}};
view.camera.position.set(0,3,0);view.controls.target.set(0,0,0);view.camera.lookAt(view.controls.target);
const turn=view.turnLeftTo(new THREE.Vector3(1,0,0),1000,'');
view.pan.start=performance.now()-1100;view.animate();await turn;
assert.ok(new THREE.Vector3(0,0,-1).applyQuaternion(view.camera.quaternion).dot(new THREE.Vector3(1,0,0))>.999999,'A turn starting at the camera pole reaches its destination without a horizontal-vector singularity');
console.log('PASS: catalog arrival, camera motion, and stellar closeups continue rendering with synchronized labels.');
