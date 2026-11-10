import * as THREE from 'three';
import {flares} from './activity.js';
const $=id=>document.getElementById(id);
export function installNavigation(C){
 const originalClose=C.prototype.stellarCloseup,originalExit=C.prototype.exitLocal;
 C.prototype.stellarCloseup=function(item,startDistance=300){this.stopFlight();originalClose.call(this,item);this.camera.far=100000;this.camera.position.set(0,.05,startDistance);this.controls.minDistance=1.003;this.controls.maxDistance=1800;this.camera.updateProjectionMatrix();this.controls.update();this.localGroup.add(flares(1));this.local.entryDistance=startDistance;this.local.item=item;};
 C.prototype.approach=async function(lit=false){let i=this.items.find(i=>i.data.id===this.selected);if(!i)return;
  if(this.mode==='stars'){if(i.data.id==='origin'){window.dispatchEvent(new Event('cosmic-enter'));return;}if(!this.local)this.stellarCloseup(i);return this.fly(new THREE.Vector3(),new THREE.Vector3(0,.15,4.4),2800,true);}
  let v=lit&&i.data.id!=='sun'?i.pos.clone().negate().normalize():this.camera.position.clone().sub(this.controls.target).normalize();if(!v.length())v.set(0,.3,1).normalize();let distance=i.radius*(i.data.id==='saturn'?8.5:4.4)*(innerWidth<=650?1.35:1);return this.fly(i.pos,i.pos.clone().addScaledVector(v,distance),1900,true);
 };
 C.prototype.smoothExit=async function(){if(!this.local||this.surface){this.exitLocal();return;}await this.fly(new THREE.Vector3(),this.camera.position.clone().normalize().multiplyScalar(this.local.entryDistance||300),1800,true);this.exitLocal();};
 C.prototype.zoomBy=function(factor){if(this.journey||this.surface)return;this.stopFlight();this.zoomImpulse=(this.zoomImpulse||0)+Math.log(factor);};
 C.prototype.navigationTick=function(dt){
  if(this.journey||this.surface||this.flight)return;let body=this.items.find(i=>i.data.id===this.selected);if(this.mode==='solar'&&body?.data.id==='earth'&&this.camera.position.distanceTo(body.pos)<body.radius*2.4&&performance.now()-(this.terrainPrefetchTime||0)>2500){this.terrainPrefetchTime=performance.now();this.prefetchTerrain(this.landingPoint()).catch(()=>{});}let k=this.navKeys||new Set(),active=!document.body.classList.contains('observing')&&!document.body.classList.contains('searching');
  let impulse=this.zoomImpulse||0;if(active){impulse+=((k.has('KeyS')?1:0)-(k.has('KeyW')?1:0))*dt*1.8;let orbit=((k.has('KeyD')?1:0)-(k.has('KeyA')?1:0))*dt*.8;if(orbit){let v=this.camera.position.clone().sub(this.controls.target);v.applyAxisAngle(this.camera.up,orbit);this.camera.position.copy(this.controls.target).add(v);}}
  let factor=Math.exp(impulse*Math.min(1,dt*13));this.zoomImpulse=impulse*Math.exp(-dt*13);let offset=this.camera.position.clone().sub(this.controls.target),d=offset.length();if(Math.abs(impulse)>.00001){d=THREE.MathUtils.clamp(d*factor,this.controls.minDistance,this.controls.maxDistance);offset.setLength(d);this.camera.position.copy(this.controls.target).add(offset);}
  let i=this.items.find(i=>i.data.id===this.selected);
  if(this.mode==='stars'&&!this.local&&this.selected==='origin'&&d<.0004&&impulse<-.001){window.dispatchEvent(new Event('cosmic-enter'));return;}if(this.mode==='solar'&&!this.local&&d>70&&impulse>.001){window.dispatchEvent(new Event('cosmic-exit'));return;}if(this.mode==='stars'&&!this.local&&impulse<-.001&&i&&d<.18&&this.controls.target.distanceTo(i.pos)<.01&&i.data.id!=='origin'){let direction=offset.clone().normalize();this.stellarCloseup(i,300);this.camera.position.copy(direction).multiplyScalar(300);this.controls.target.set(0,0,0);}
  else if(this.local&&!this.surface){this.camera.near=Math.max(.0002,Math.min(.02,(d-1)*.015));this.camera.updateProjectionMatrix();if(d>900&&!this.journey){let direction=offset.clone().normalize(),saved=this.local;originalExit.call(this);this.controls.target.copy(saved.item.pos);this.camera.position.copy(saved.item.pos).addScaledVector(direction,.2);}}
 };
 C.prototype.scaleTransition=async function(fn){let token=this.travelToken;let cover=document.createElement('img');cover.src=this.renderer.domElement.toDataURL();cover.className='travel-rebase';this.renderer.domElement.parentElement.append(cover);let animation=cover.animate([{transform:'scale(1)',opacity:1,filter:'blur(0)'},{transform:'scale(2.8)',opacity:1,filter:'blur(1px)'},{transform:'scale(6)',opacity:0,filter:'blur(3px)'}],{duration:this.reduced?250:650,easing:'cubic-bezier(.5,0,.8,.5)',fill:'forwards'});await new Promise(r=>setTimeout(r,this.reduced?120:350));if(token===this.travelToken)await fn();await animation.finished.catch(()=>{});cover.remove();};
 C.prototype.trace=async function(context,solar,progress){
  let item=this.items.find(i=>i.data.id===this.selected);if(!item)return false;let token=this.travelToken=(this.travelToken||0)+1,valid=()=>this.travelToken===token;
  this.traceReturn={mode:this.mode,data:this.mode==='solar'?this.solarData:this.starsData,selected:this.selected,camera:this.camera.position.clone(),target:this.controls.target.clone(),wasLocal:!!this.local,context};
  this.journey=true;this.controls.enabled=false;this.zoomImpulse=0;this.stopFlight();let direction,earth;
  progress('Departing '+item.data.name,'Accelerated illustrative journey · epoch frozen');
  if(this.mode==='stars'){
   let toward=item.pos.clone().negate().normalize();if(!toward.length()){let ra=context.ra*Math.PI/180,dec=context.dec*Math.PI/180;toward=this.vector([-Math.cos(dec)*Math.cos(ra),-Math.cos(dec)*Math.sin(ra),-Math.sin(dec)]);}
   let approachDirection=toward.clone().applyAxisAngle(this.camera.up.clone().normalize(),-Math.PI/2);
   if(item.data.id!=='origin'){if(!this.local)this.stellarCloseup(item);this.controls.enabled=false;if(!await this.fly(new THREE.Vector3(),approachDirection.clone().multiplyScalar(-1.14),1600,true)||!valid())return false;}
   progress('Turning left toward Earth','Camera rotates at the approached surface before departure');if(!await this.turnLeftTo(toward,1900)||!valid())return false;direction=item.pos.clone().normalize();if(!direction.length())direction.set(0,0,1);
   await this.scaleTransition(()=>{this.exitLocal();this.controls.enabled=false;this.camera.position.copy(item.pos).addScaledVector(direction,-.00001);this.controls.target.set(0,0,0);this.controls.update();});if(!valid())return false;earth=new THREE.Vector3();
  }else{earth=this.items.find(i=>i.data.id==='earth').pos.clone();direction=item.pos.clone().sub(earth).normalize();let toward=earth.clone().sub(item.pos).normalize(),initial=toward.clone().applyAxisAngle(this.camera.up.clone().normalize(),-Math.PI/2),departure=item.pos.clone().addScaledVector(initial,-item.radius*1.14);if(!await this.fly(item.pos,departure,1600,true)||!valid())return false;progress('Turning left toward Earth','Surface approach complete · rotating before acceleration');if(!await this.turnLeftTo(earth.clone().sub(this.camera.position),1900)||!valid())return false;}
  progress('Trace back to Earth',this.mode==='stars'?'Smooth accelerated travel · catalog parsec scale':'Smooth accelerated travel · Solar System AU scale');
  if(!await this.fly(earth,this.camera.position.clone(),1100)||!valid())return false;
  let end=earth.clone().addScaledVector(direction,this.mode==='solar'?this.items.find(i=>i.data.id==='earth').radius*2.8:.003);
  if(!await this.fly(earth,end,6500,true)||!valid())return false;
  if(this.mode==='stars'){
   progress('Entering the Solar System','Parsec → AU scale transition');direction=this.vector(context.direction_ecliptic).normalize();
   await this.scaleTransition(async()=>{await this.solar(solar);this.controls.enabled=false;let e=this.items.find(i=>i.data.id==='earth');earth=e.pos.clone();this.camera.position.copy(earth).addScaledVector(direction,.25);this.controls.target.copy(earth);this.controls.update();});if(!valid())return false;
   let e=this.items.find(i=>i.data.id==='earth');if(!await this.fly(earth,earth.clone().addScaledVector(direction,e.radius*2.8),1100,true)||!valid())return false;
  }
  progress('Looking back from Earth',context.constellation+' · source direction in our sky');return valid();
 };
 C.prototype.returnFromTrace=async function(progress=()=>{}){
  let token=this.travelToken=(this.travelToken||0)+1,r=this.traceReturn;this.stopFlight();if(!r){this.journey=false;this.controls.enabled=true;return;}this.traceReturn=null;this.renderer.domElement.style.opacity='1';this.journey=true;this.controls.enabled=false;
  progress('Returning to object','Turning toward the source before accelerating');let heading=r.mode==='stars'?this.vector(r.context.direction_ecliptic).normalize():this.items.find(i=>i.data.id===r.selected)?.pos.clone().sub(this.camera.position);if(heading)await this.turnLeftTo(heading,1800,'RETURN - '+r.selected);if(this.travelToken!==token)return;
  if(this.local)await this.scaleTransition(()=>this.exitLocal());if(this.travelToken!==token)return;
  if(r.mode==='stars'){
   let earth=this.items.find(i=>i.data.id==='earth');if(earth&&this.mode==='solar'){let dir=this.vector(r.context.direction_ecliptic).normalize();await this.fly(earth.pos,this.camera.position.clone(),700);await this.fly(earth.pos,earth.pos.clone().addScaledVector(dir,.25),2000,true);}
   await this.scaleTransition(()=>{this.stars(r.data,false);this.selected=r.selected;let i=this.items.find(i=>i.data.id===r.selected);let dir=i.pos.clone().normalize();if(!dir.length())dir.set(0,0,1);this.camera.position.copy(dir).multiplyScalar(.003);this.controls.target.copy(i.pos);this.controls.enabled=false;this.controls.update();});
   if(this.travelToken!==token)return;let i=this.items.find(i=>i.data.id===r.selected),dir=i.pos.clone().normalize();if(!dir.length())dir.set(0,0,1);
   await this.fly(i.pos,i.pos.clone().addScaledVector(dir,-.17),6500,true);
   if(i.data.id!=='origin'){await this.scaleTransition(()=>this.stellarCloseup(i,300));this.controls.enabled=false;await this.fly(new THREE.Vector3(),new THREE.Vector3(0,.15,4.4),2600,true);}
  }else{
   if(this.mode!=='solar')await this.scaleTransition(()=>this.solar(r.data));let i=this.items.find(i=>i.data.id===r.selected);this.selected=r.selected;
   await this.fly(i.pos,this.camera.position.clone(),1000);await this.fly(i.pos,r.camera,6500,true);await this.fly(r.target,r.camera,800);
  }
  this.journey=false;this.controls.enabled=true;this.selectLabelOnly?.();this.selected=r.selected;
 };

 C.prototype.sizeComparison=async function(){
  let data=this.physicalSolar||this.solarData;if(!data)return;this.physicalSolar=data;let cursor=-2;let objects=data.objects.map(d=>{let radius=d.radius_km/695700;cursor+=radius;let x=cursor;cursor+=radius+.22;return {...d,xyz_au:[x,0,0],display_radius_factor:149597870.7/695700,orbit_au:null};});await this.solar({...data,size_layout:true,objects});this.mode='sizes';this.selected='sun';let extent=cursor+2;await this.fly(new THREE.Vector3((cursor-2)/2,0,0),new THREE.Vector3((cursor-2)/2,.5,extent*1.4),1300);$('size-note').textContent='True radius ratios · arranged centers · units R☉';$('scene-subtitle').textContent='Physical size comparison. Centers are arranged for comparison, not catalog positions.';
 };
 C.prototype.planetOrbit=async function(id=this.selected){
  if(this.mode==='sizes')await this.solar(this.physicalSolar);let i=this.items.find(i=>i.data.id===id);if(!i)return;this.selected=id;this.orbits.children.forEach(o=>o.visible=o.userData.body===id);this.orbits.visible=true;
  let extent=Math.max(.1,...(i.data.orbit_au||[]).map(p=>Math.hypot(...p)));if(!i.data.orbit_au){await this.overview();return;}
  let direction=new THREE.Vector3(.1,.65,1).normalize();await this.fly(new THREE.Vector3(),direction.multiplyScalar(extent*3.1),1600,true);$('scene-subtitle').textContent=i.data.name+' orbit around the Sun · calculated geometry, presentation radii';
 };


 C.prototype.landingPoint=function(){let i=this.items.find(i=>i.data.id===this.selected);if(!i||i.data.id!=='earth')return null;if(i.data.landingUV)return {lat:(i.data.landingUV.y-.5)*180,lon:i.data.landingUV.x*360-180};
 let p=this.camera.position.clone().sub(i.pos).normalize().multiplyScalar(i.radius).add(i.pos);this.scene.updateMatrixWorld();let local=i.mesh.worldToLocal(p).normalize();return {lat:THREE.MathUtils.radToDeg(Math.asin(local.y)),lon:((THREE.MathUtils.radToDeg(Math.atan2(local.z,-local.x))+360)%360)-180};};
 C.prototype.prefetchTerrain=function(point){this.terrainRequests??=new Map();let key=point.lat.toFixed(4)+','+point.lon.toFixed(4);if(!this.terrainRequests.has(key)){if(this.terrainRequests.size>=8)this.terrainRequests.delete(this.terrainRequests.keys().next().value);let task=fetch('/api/terrain/earth?'+new URLSearchParams(point)).then(async r=>{if(!r.ok){let e=await r.json();throw Error(e.detail);}return r.json();});task.catch(()=>{});this.terrainRequests.set(key,task);}return this.terrainRequests.get(key);};
 C.prototype.enterSurface=async function(){this.stopFlight();let point=this.landingPoint();if(!point)throw Error('Choose Earth to land on mapped terrain.');if(this.surface)return true;window.dispatchEvent(new CustomEvent('scene-error',{detail:'Loading the exact landing region '+point.lat.toFixed(3)+'°, '+point.lon.toFixed(3)+'°…'}));let data=await this.prefetchTerrain(point);if(this.selected!=='earth')return false;this.exitLocal();this.local={camera:this.camera.position.clone(),target:this.controls.target.clone(),min:this.controls.minDistance,max:this.controls.maxDistance,near:this.camera.near,far:this.camera.far};this.content.visible=false;this.controls.enabled=false;this.surface=new this.SurfaceExplorerType(data,this.renderer);document.body.classList.add('surface-active');$('surface-hud').hidden=false;$('surface-name').textContent=data.name;$('surface-note').textContent=data.source+' · '+data.resolution_m+' m sampling. '+data.note+' '+data.temperature_note;return true;};


 C.prototype.turnLeftTo=function(direction,duration=1800,label='EARTH - computed direction'){this.stopFlight();this.earthBeacon=direction.clone().normalize();if(!this.beaconLabel){this.beaconLabel=document.createElement('span');this.beaconLabel.className='earth-beacon';this.beaconLabel.textContent='EARTH · computed direction';document.getElementById('stage').append(this.beaconLabel);}if(this.beaconLabel){this.beaconLabel.textContent=label;this.beaconLabel.style.display=label?'':'none';}let from=this.controls.target.clone().sub(this.camera.position).normalize(),to=direction.clone().normalize(),up=this.camera.up.clone().normalize(),horizontal=from.clone().addScaledVector(up,-from.dot(up)).normalize(),end=to.clone().addScaledVector(up,-to.dot(up)).normalize(),delta=Math.atan2(up.dot(horizontal.clone().cross(end)),horizontal.dot(end));return new Promise(done=>this.pan={start:performance.now(),duration:this.reduced?500:duration,up,horizontal,delta,pitch:Math.asin(from.dot(up)),endPitch:Math.asin(to.dot(up)),distance:Math.max(.001,this.camera.position.distanceTo(this.controls.target)),done});};


 C.prototype.addCatalogSky=function(data){if(this.sky)return;this.sky=new THREE.Group();this.sky.userData.catalog=true;let eps=23.439291111*Math.PI/180;for(let d of data.objects){if(d.phot_g_mean_mag!=null&&d.phot_g_mean_mag>12)continue;let p=d.xyz_pc,e=[p[0],Math.cos(eps)*p[1]+Math.sin(eps)*p[2],-Math.sin(eps)*p[1]+Math.cos(eps)*p[2]],sprite=this.makeHalo(d);sprite.userData.catalogObject=d;sprite.userData.direction=this.vector(e).normalize();this.sky.add(sprite);}this.scene.add(this.sky);};

}