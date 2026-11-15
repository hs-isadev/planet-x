import * as THREE from 'three';

const tilt=THREE.MathUtils.degToRad(23.439291111);
const sin=Math.sin(tilt), cos=Math.cos(tilt);
const $=id=>document.getElementById(id);

export function icrsDirection(ra,dec){
 const a=THREE.MathUtils.degToRad(ra),d=THREE.MathUtils.degToRad(dec);
 const x=Math.cos(d)*Math.cos(a),y=Math.cos(d)*Math.sin(a),z=Math.sin(d);
 return new THREE.Vector3(x,-sin*y+cos*z,-(cos*y+sin*z));
}
export function skyCoordinates(direction){
 const {x,y:ez,z:minusEy}=direction.clone().normalize(), ey=-minusEy;
 const y=cos*ey-sin*ez,z=sin*ey+cos*ez;
 return {ra:(THREE.MathUtils.radToDeg(Math.atan2(y,x))+360)%360,
         dec:THREE.MathUtils.radToDeg(Math.asin(THREE.MathUtils.clamp(z,-1,1)))};
}
export function installSunSky(C){
 C.prototype.sunSkyDirection=function(x=0,y=0){
  this.camera.updateMatrixWorld();
  const ray=new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(x,y),this.camera);
  return skyCoordinates(ray.ray.direction);
 };
 C.prototype.aimSunSky=function(){
  const state=this.sunSky;
  if(!state)return;
  const direction=new THREE.Vector3().setFromSphericalCoords(1,state.phi,state.theta);
  this.camera.position.copy(state.origin).add(direction);
  this.camera.lookAt(this.camera.position.clone().add(direction));
  const point=this.sunSkyDirection();
  $('sun-sky-readout').textContent='RA '+point.ra.toFixed(4)+'° · Dec '+point.dec.toFixed(4)+'°';
 };
 C.prototype.enterSunSky=function(position){
  if(this.sunSky)return;
  this.stopFlight();
  const direction=position?icrsDirection(position.ra,position.dec):this.camera.getWorldDirection(new THREE.Vector3());
  const spherical=new THREE.Spherical().setFromVector3(direction);
  this.sunSky={
   phi:THREE.MathUtils.clamp(spherical.phi,.003,Math.PI-.003),theta:spherical.theta,
   origin:this.items.find(item=>item.data.id==='sun')?.pos.clone()||new THREE.Vector3(),
   saved:{mode:this.mode,position:this.camera.position.clone(),quaternion:this.camera.quaternion.clone(),
          up:this.camera.up.clone(),near:this.camera.near,far:this.camera.far,
          content:this.content.visible,controls:this.controls.enabled}
  };
  this.mode='solar';
  this.controls.enabled=false;
  this.content.visible=false;
  if(this.localGroup)this.localGroup.visible=false;
  this.camera.up.set(0,1,0);
  this.camera.near=.001;this.camera.far=12000;
  document.body.dataset.sunSky='true';
  $('sun-sky-panel').hidden=false;
  $('sun-sky-tab').setAttribute('aria-pressed','true');
  $('stage').setAttribute('aria-label','Sun sky view. Drag to look around, then right-click a direction to load SPHEREx images.');
  this.installSunSkyInput();
  this.resize();
  this.aimSunSky();
  this.loadContextSky();
 };
 C.prototype.leaveSunSky=function(){
  if(!this.sunSky)return;
  const saved=this.sunSky.saved;
  this.sunSky=null;
  this.mode=saved.mode;
  this.camera.position.copy(saved.position);
  this.camera.quaternion.copy(saved.quaternion);
  this.camera.up.copy(saved.up);
  this.camera.near=saved.near;this.camera.far=saved.far;
  this.content.visible=saved.content;
  if(this.localGroup)this.localGroup.visible=true;
  this.controls.enabled=saved.controls;
  delete document.body.dataset.sunSky;
  $('sun-sky-panel').hidden=true;
  $('sun-sky-tab').setAttribute('aria-pressed','false');
  $('stage').setAttribute('aria-label','Interactive 3D Solar System. Drag to orbit, scroll to zoom. Click bodies to select.');
  this.resize();
 };
 C.prototype.renderSunSky=function(dt){
  const k=this.navKeys;
  if(!document.body.classList.contains('observing')&&(k?.size||0)){
   const state=this.sunSky;
   state.theta+=((k.has('KeyA')?1:0)-(k.has('KeyD')?1:0))*dt;
   state.phi=THREE.MathUtils.clamp(state.phi+((k.has('KeyS')?1:0)-(k.has('KeyW')?1:0))*dt,.003,Math.PI-.003);
   this.aimSunSky();
  }
  if(this.sky){
   this.sky.visible=true;
   this.sky.userData.update?.();
  }
  this.renderer.render(this.scene,this.camera);
 };
 C.prototype.installSunSkyInput=function(){
  if(this.sunSkyInput)return;
  this.sunSkyInput=true;
  const canvas=this.renderer.domElement;
  let drag=null;
  canvas.addEventListener('pointerdown',event=>{
   if(!this.sunSky||event.button!==0)return;
   drag={id:event.pointerId,x:event.clientX,y:event.clientY,state:this.sunSky};
   canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove',event=>{
   if(!drag||drag.state!==this.sunSky||drag.id!==event.pointerId)return;
   const {clientX:x,clientY:y}=event;
   const sensitivity=1.7/Math.max(200,canvas.getBoundingClientRect().height);
   this.sunSky.theta+=(x-drag.x)*sensitivity;
   this.sunSky.phi=THREE.MathUtils.clamp(this.sunSky.phi-(y-drag.y)*sensitivity,.003,Math.PI-.003);
   drag.x=x;drag.y=y;
   this.aimSunSky();
  });
  const end=event=>{if(drag?.id===event.pointerId)drag=null;};
  for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,end);
  canvas.addEventListener('contextmenu',event=>{
   if(!this.sunSky)return;
   event.preventDefault();
   const r=canvas.getBoundingClientRect();
   if(!r.width||!r.height)return;
   const x=2*(event.clientX-r.left)/r.width-1,y=1-2*(event.clientY-r.top)/r.height;
   window.dispatchEvent(new CustomEvent('sun-sky-observe',{detail:this.sunSkyDirection(x,y)}));
  });
 };
}
