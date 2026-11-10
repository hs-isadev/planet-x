import * as THREE from 'three';
import {corona} from './plasma.js';
import {addMoons,addPlanets} from './companions.js';
import {travelDust} from './travel-dust.js';
const $=id=>document.getElementById(id);
export function installContext(C){
 const solar=C.prototype.solar,close=C.prototype.stellarCloseup,exit=C.prototype.exitLocal,stars=C.prototype.stars;
 C.prototype.solar=async function(data){
  data.objects=data.objects.filter(d=>!d.parent);
  await solar.call(this,data);const version=this.version;
  this.camera.far=100000;this.camera.updateProjectionMatrix();
  this.items.find(i=>i.data.id==='sun')?.mesh.add(corona(this.items[0].radius));
  for(const i of this.items){i.mesh.visible=!i.model;if(i.model)i.model.visible=true;}
  try{await addMoons(this,data,version);}catch(e){window.dispatchEvent(new CustomEvent('scene-error',{detail:'Moon catalog unavailable: '+e.message}));}
  this.installTravelDust();this.loadContextSky();
 };
 C.prototype.stars=function(...args){stars.apply(this,args);this.installTravelDust();this.loadContextSky();};
 C.prototype.installTravelDust=function(){if(this.dustUpdate)return;this.dustUpdate=travelDust(this);const tick=new THREE.Group();tick.userData.update=()=>this.dustUpdate();this.scene.add(tick);};
 C.prototype.loadContextSky=function(){if(this.contextSkyLoading)return;this.contextSkyLoading=true;fetch('/api/context-sky').then(r=>{if(!r.ok)throw Error('Catalog backdrop unavailable');return r.json();}).then(data=>{this.addCatalogSky(data);}).catch(()=>{this.contextSkyLoading=false;});};
 C.prototype.addCatalogSky=function(data){
  if(!this.sky){this.sky=new THREE.Group();this.sky.userData.catalog=true;this.scene.add(this.sky);this.skyIds=new Set();}
  for(const d of data.objects){if(this.skyIds.has(d.id))continue;this.skyIds.add(d.id);let sprite=this.makeHalo(d);
   sprite.userData.catalogObject=d;sprite.userData.passive=d.id.startsWith('host:');sprite.userData.icrs=this.vector(d.xyz_pc);this.sky.add(sprite);
  }
  this.sky.userData.update=()=>{
   this.sky.visible=!this.surface;
   const eps=THREE.MathUtils.degToRad(23.439291111);
   for(const sprite of this.sky.children){const raw=sprite.userData.icrs.clone();
    if(this.local?.item?.data.name?.toLowerCase()===sprite.userData.catalogObject.name.toLowerCase()){sprite.visible=false;continue;}
    if(this.mode==='stars')raw.sub(this.local?.item?.pos||this.camera.position);
    else {const y=-raw.z,z=raw.y;raw.set(raw.x,-Math.sin(eps)*y+Math.cos(eps)*z,-(Math.cos(eps)*y+Math.sin(eps)*z));}
    if(raw.lengthSq()<1e-12){sprite.visible=false;continue;}sprite.visible=true;raw.normalize();
    sprite.position.copy(this.camera.position).addScaledVector(raw,3000);
    const mag=sprite.userData.catalogObject.phot_g_mean_mag,px=mag==null?1.2:THREE.MathUtils.clamp(4-mag*.22,1.3,4);
    sprite.scale.setScalar(3000*2*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))*px/this.h);
   }
  };
 };
 C.prototype.stellarCloseup=function(item,...args){
  close.call(this,item,...args);this.localGroup.add(corona(1));
  const reliable=Number.isFinite(item.data.teff_gspphot)&&item.data.teff_gspphot>0;
  $('stellar-provenance').textContent=reliable?'COMPUTED appearance using catalog temperature; accelerated activity is illustrative, not an observed surface.':'TEMPERATURE UNKNOWN: close-up appearance, color and activity are illustrative and may be inaccurate.';
  $('stellar-system').hidden=true;
  $('stellar-system').onclick=()=>this.systemOverview();
  const context=this.local;
  if(item.data.planets)addPlanets(this,item,item.data.planets);
  else if(item.data.ra!=null)fetch('/api/companions?'+new URLSearchParams({ra:item.data.ra,dec:item.data.dec,name:item.data.name})).then(r=>r.json()).then(data=>{item.data.planets=data.planets||[];if(this.local===context)addPlanets(this,item,item.data.planets);}).catch(()=>{});
 };
 C.prototype.systemOverview=function(){if(!this.local)return;const distance=Math.max(6,(this.local.systemExtent||2)*3);return this.fly(new THREE.Vector3(),new THREE.Vector3(0,distance*.42,distance),1800);};
 C.prototype.exitLocal=function(){exit.call(this);if(this.mode==='solar')for(const i of this.items){i.mesh.visible=!i.model;if(i.model)i.model.visible=true;}if($('stellar-system'))$('stellar-system').hidden=true;};
 C.prototype.focus=async function(){
  this.exitLocal();const i=this.items.find(i=>i.data.id===this.selected);if(!i)return;
  const selected=this.selected,d=Math.max(i.radius*4.4,this.camera.position.distanceTo(this.controls.target));
  const direction=this.camera.position.clone().sub(i.pos).normalize();if(!direction.length())direction.set(0,.25,1).normalize();
  await this.turnLeftTo(i.pos.clone().sub(this.camera.position),550,'');
  if(this.selected!==selected)return;
  return this.fly(i.pos,i.pos.clone().addScaledVector(direction,d),1050);
 };
 // A single interpolation law for every flight: quintic ease, linear world distance.
 const fly=C.prototype.fly;
 C.prototype.fly=function(target,pos,duration=1400){this.zoomImpulse=0;return fly.call(this,target,pos,duration,false);};
 const orbit=C.prototype.planetOrbit;
 C.prototype.planetOrbit=function(id=this.selected){if(this.mode==='solar'&&id==='sun'){this.showPaths=true;this.orbits.visible=true;this.orbits.children.forEach(o=>o.visible=true);return this.overview();}return orbit.call(this,id);};
}
