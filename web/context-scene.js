import * as THREE from 'three';
import {corona} from './plasma.js';
import {addMoons,addPlanets} from './companions.js?v=gaia-host';
import {travelDust} from './travel-dust.js';
const $=id=>document.getElementById(id);
function starProfile() {
 const width=64,pixels=new Uint8Array(width*width*4);
 for(let y=0;y<width;y++)for(let x=0;x<width;x++){
  const r=Math.hypot(2*(x+.5)/width-1,2*(y+.5)/width-1);
  const edge=THREE.MathUtils.clamp((1-r)/.22,0,1);
  const alpha=edge*(.82*Math.exp(-14*r*r)+.22*Math.exp(-4.4*r*r));
  const i=4*(y*width+x);
  pixels[i]=pixels[i+1]=pixels[i+2]=255;
  pixels[i+3]=Math.round(255*Math.min(1,alpha));
 }
 const texture=new THREE.DataTexture(pixels,width,width,THREE.RGBAFormat);
 texture.minFilter=texture.magFilter=THREE.LinearFilter;
 texture.needsUpdate=true;
 return texture;
}

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
 C.prototype.loadContextSky=function(){
  if(!this.contextCatalogReady)this.contextCatalogReady=fetch('/api/context-sky').then(response=>{
   if(!response.ok)throw Error('Catalog backdrop unavailable');
   return response.json();
  }).then(data=>{this.addCatalogSky(data);return data;}).catch(()=>{
   this.contextCatalogReady=null;
   return null;
  });
  return this.contextCatalogReady;
 };
 C.prototype.addCatalogSky=function(data){
  if(this.sky)return;
  // Limit angular density across the catalog. Keep real rows with valid distances.
  const counts=new Map(), entries=[];
  const sorted=data.objects.filter(source=>!source.expanded_catalog).sort((a,b)=>a.distance_pc-b.distance_pc||a.id.localeCompare(b.id));
  for(const source of sorted){
   if(!source.xyz_pc?.every(Number.isFinite)||!Number.isFinite(source.ra)||!Number.isFinite(source.dec))continue;
   const cell=Math.floor(source.ra/12)+':'+Math.floor((source.dec+90)/12);
   const count=counts.get(cell)||0;
   if(count>=2)continue;
   counts.set(cell,count+1);
   entries.push(source);
   if(entries.length>=512)break;
  }
  entries.push(...data.objects.filter(source=>source.expanded_catalog&&source.xyz_pc?.every(Number.isFinite)));
  this.sky=new THREE.Group();
  this.sky.userData.catalog=true;
  this.sky.userData.sourceCount=data.objects.length;
  this.scene.add(this.sky);
  const directions=entries.map(source=>this.vector(source.xyz_pc));
  const positions=new Float32Array(entries.length*3), colors=new Float32Array(entries.length*3);
  entries.forEach((source,index)=>{
   const color=new THREE.Color((source.teff_gspphot||0)>6500?'#b1c7eb':source.teff_gspphot<4700?'#d4b297':'#ccd2db');
   color.toArray(colors,index*3);
  });
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  geometry.boundingSphere=new THREE.Sphere(new THREE.Vector3(),3001);
  const material=new THREE.PointsMaterial({size:5.6,map:starProfile(),sizeAttenuation:false,vertexColors:true,transparent:true,opacity:.86,alphaTest:.012,depthWrite:false});
  const points=new THREE.Points(geometry,material);
  points.userData.catalogEntries=entries;
  this.sky.add(points);
  const raw=new THREE.Vector3(), lastOrigin=new THREE.Vector3(Infinity,Infinity,Infinity);
  let lastMode,lastLocal,lastCatalogStars;
  const epsilon=THREE.MathUtils.degToRad(23.439291111);
  const sin=Math.sin(epsilon),cos=Math.cos(epsilon);
  this.sky.userData.update=()=>{
   this.sky.visible=!this.surface;
   this.sky.position.copy(this.camera.position);
   material.size=THREE.MathUtils.clamp(5.6*(this.starSize||1),2.4,12);
   const origin=this.local?.item?.pos||this.camera.position;
   const local=this.local?.item?.data.id;
   const catalogStars=this.mode==='stars'?this.visibleCatalogStars:null;
   if(this.mode===lastMode&&local===lastLocal&&lastCatalogStars===catalogStars&&(this.mode!=='stars'||origin.equals(lastOrigin)))return;
   lastMode=this.mode;lastLocal=local;lastCatalogStars=catalogStars;lastOrigin.copy(origin);
   for(let i=0;i<entries.length;i++){
    raw.copy(directions[i]);
    if(this.mode==='stars')raw.sub(origin);
    else {const y=-raw.z,z=raw.y;raw.set(raw.x,-sin*y+cos*z,-(cos*y+sin*z));}
    if(entries[i].id===local||(!local&&catalogStars?.has(entries[i].id))||raw.lengthSq()<1e-12)raw.set(0,0,0);
    else raw.setLength(3000);
    raw.toArray(positions,i*3);
   }
   geometry.attributes.position.needsUpdate=true;
  };
  this.sky.userData.update();
 };
 C.prototype.catalogAtPointer=function(pointer){
  const points=this.sky?.children[0];
  const entries=points?.userData.catalogEntries;
  if(!this.sky?.visible||!entries)return null;
  const positions=points.geometry.attributes.position.array;
  const projected=new THREE.Vector3();
  let best=null, radius=6;
  for(let i=0;i<entries.length;i++){
   projected.fromArray(positions,i*3).applyMatrix4(points.matrixWorld).project(this.camera);
   if(projected.z<0||projected.z>=1)continue;
   const distance=Math.hypot((projected.x-pointer.x)*this.w/2,(projected.y-pointer.y)*this.h/2);
   if(distance<radius){radius=distance;best=entries[i];}
  }
  return best;
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
    this.journey?Promise.resolve(show([])):
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
  const finished=await this.turnLeftTo(i.pos.clone().sub(this.camera.position),550,'');
  if(!finished||this.journey||this.selected!==selected)return;
  return this.fly(i.pos,i.pos.clone().addScaledVector(direction,d),1050);
 };
 // Every orbit-camera zoom uses the same gradual geometric-distance path.
 const fly=C.prototype.fly;
 C.prototype.fly=function(target,pos,duration=1800){this.zoomImpulse=0;return fly.call(this,target,pos,duration);};
 const orbit=C.prototype.planetOrbit;
 C.prototype.planetOrbit=function(id=this.selected){if(this.mode==='solar'&&id==='sun'){this.showPaths=true;this.orbits.visible=true;this.orbits.children.forEach(o=>o.visible=true);return this.overview();}return orbit.call(this,id);};
}
