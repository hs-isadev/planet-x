import * as THREE from 'three';
import {corona} from './plasma.js';
import {addMoons,addPlanets} from './companions.js';
import {travelDust} from './travel-dust.js';
const $=id=>document.getElementById(id);
export function installContext(C){
 const solar=C.prototype.solar,close=C.prototype.stellarCloseup,exit=C.prototype.exitLocal,stars=C.prototype.stars;
 C.prototype.solar=async function(data){
  data.objects=data.objects.filter(d=>!d.parent);
  const expectedVersion=(this.version||0)+1;await solar.call(this,data);if(this.version!==expectedVersion)return;const version=this.version;
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
    sprite.scale.setScalar(3000*2*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))*px*(this.starSize||1)/this.h);
   }
  };
 };
 C.prototype.stellarCloseup=function(item,...args){
  close.call(this,item,...args);
  if((item.data.teff_gspphot||0)>=2300)this.localGroup.add(corona(1));
  const reliable=Number.isFinite(item.data.teff_gspphot)&&item.data.teff_gspphot>0;
  $('stellar-provenance').textContent=reliable?'COMPUTED appearance using catalog temperature. Faint visible-light glow; any surface activity is illustrative and accelerated.':'TEMPERATURE UNKNOWN: close-up color and appearance are illustrative and may be inaccurate. No measured stellar activity is claimed.';
  if(reliable&&item.data.teff_gspphot<2300)$('stellar-provenance').textContent+=' Cool brown-dwarf appearance is illustrative; this is not a visible-light photograph.';
  $('stellar-system').hidden=false;$('stellar-system').disabled=true;$('stellar-system').textContent='Loading planet catalog…';
  $('planet-list')?.replaceChildren();
  $('stellar-system').onclick=()=>this.systemOverview();
  const context=this.local;
  const show=planets=>{if(this.local!==context)return;item.data.planets=planets;addPlanets(this,item,planets);};
  this.companionsReady=item.data.planets?Promise.resolve(show(item.data.planets)):
   item.data.ra!=null?fetch('/api/companions?'+new URLSearchParams({ra:item.data.ra,dec:item.data.dec,name:item.data.name})).then(r=>{if(!r.ok)throw Error('Planet catalog unavailable');return r.json();}).then(data=>show(data.planets||[])).catch(()=>{if(this.local===context){$('stellar-system').textContent='Planet catalog unavailable';$('stellar-provenance').textContent+=' Planet catalog could not load; no orbit has been invented.';}}):Promise.resolve(show([]));
 };
 C.prototype.systemOverview=function(){
  if(!this.local)return;this.local.followPlanet=null;const distance=Math.max(6,(this.local.systemExtent||2)*3.4);
  this.controls.maxDistance=Math.max(1800,distance*4);this.camera.far=Math.max(100000,distance*10);this.camera.updateProjectionMatrix();
  return this.fly(new THREE.Vector3(),new THREE.Vector3(0,distance*.5,distance),5500);
 };
 C.prototype.planetCloseup=async function(planet){
  if(!this.local||!planet)return;
  this.local.followPlanet=planet;const radius=planet.userData.displayRadius||.1,target=planet.position.clone();
  return this.fly(target,target.clone().add(new THREE.Vector3(0,radius*3,radius*8)),4500);
 };
 C.prototype.exitLocal=function(){exit.call(this);if(this.mode==='solar')for(const i of this.items){i.mesh.visible=!i.model;if(i.model)i.model.visible=true;}if($('stellar-system'))$('stellar-system').hidden=true;$('planet-list')?.replaceChildren();};
 C.prototype.focus=async function(){
  this.exitLocal();const i=this.items.find(i=>i.data.id===this.selected);if(!i)return;
  const selected=this.selected,d=Math.max(i.radius*4.4,this.camera.position.distanceTo(this.controls.target));
  const direction=this.camera.position.clone().sub(i.pos).normalize();if(!direction.length())direction.set(0,.25,1).normalize();
  await this.turnLeftTo(i.pos.clone().sub(this.camera.position),550,'');
  if(this.selected!==selected)return;
  return this.fly(i.pos,i.pos.clone().addScaledVector(direction,d),1050);
 };
 // Every orbit-camera zoom uses the same gradual geometric-distance path.
 const fly=C.prototype.fly;
 C.prototype.fly=function(target,pos,duration=1800){this.zoomImpulse=0;return fly.call(this,target,pos,duration);};
 const orbit=C.prototype.planetOrbit;
 C.prototype.planetOrbit=function(id=this.selected){if(this.mode==='solar'&&id==='sun'){this.showPaths=true;this.orbits.visible=true;this.orbits.children.forEach(o=>o.visible=true);return this.overview();}return orbit.call(this,id);};
}
