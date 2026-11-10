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
view.addCatalogSky({objects:[{id:'host:1',name:'Catalog star',xyz_pc:[1,2,3],phot_g_mean_mag:6}]});
const star=view.sky.children[0];
assert.ok(star.userData.icrs);
view.animate();
assert.equal(renders,2,'Frame renders after the catalog arrives');
assert.ok(Math.abs(star.position.distanceTo(view.camera.position)-3000)<1e-8);
const previousLabel=label.style.transform;
view.camera.position.set(1,3,4);
view.camera.lookAt(0,0,0);
view.controls.target.set(.1,0,0);
view.camera.lookAt(view.controls.target);
view.animate();
assert.equal(renders,3,'Camera changes still reach the renderer');
assert.notEqual(label.style.transform,previousLabel);
assert.ok(Math.abs(star.position.distanceTo(view.camera.position)-3000)<1e-8);

view.mode='stars';view.local={item:{data:{name:'Catalog star'},pos:new THREE.Vector3(1,3,-2)}};
view.animate();
assert.equal(renders,4,'Stellar closeups still render');
assert.equal(star.visible,false,'The selected star is omitted from its own backdrop');
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
