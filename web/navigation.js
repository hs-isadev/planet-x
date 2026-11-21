import {cruiseDuration} from './camera-path.js';
import * as THREE from 'three';
import {flares} from './activity.js';
const $=id=>document.getElementById(id);
export function installNavigation(C){
 const originalClose=C.prototype.stellarCloseup,originalExit=C.prototype.exitLocal;
 C.prototype.stellarCloseup=function(item,startDistance=300){this.stopFlight();originalClose.call(this,item);this.camera.far=100000;this.camera.position.set(0,.05,startDistance);this.controls.minDistance=1.003;this.controls.maxDistance=1800;this.camera.updateProjectionMatrix();this.controls.update();if((item.data.teff_gspphot||0)>=2300)this.localGroup.add(flares(1));this.local.entryDistance=startDistance;this.local.item=item;};
 C.prototype.approach=async function(lit=false){
  const item=this.items.find(i=>i.data.id===this.selected);if(!item)return;
  if(this.mode==='stars'){
   if(item.data.id==='origin'){window.dispatchEvent(new Event('cosmic-enter'));return;}
   if(!this.local)this.stellarCloseup(item);
   await this.companionsReady;
   if(this.local?.item!==item||this.selected!==item.data.id)return false;
   if(this.local.planets?.length)return this.systemOverview();
   return this.fly(new THREE.Vector3(),new THREE.Vector3(0,.15,4.4),6500);
  }
  let direction=lit&&item.data.id!=='sun'?item.pos.clone().negate().normalize():this.camera.position.clone().sub(this.controls.target).normalize();
  if(!direction.length())direction.set(0,.3,1).normalize();
  const distance=item.radius*(item.data.id==='saturn'?8.5:4.4)*(innerWidth<=650?1.35:1);
  return this.fly(item.pos,item.pos.clone().addScaledVector(direction,distance),5000);
 };
 C.prototype.smoothExit=async function(){if(!this.local||this.surface){this.exitLocal();return;}this.local.followPlanet=null;await this.fly(new THREE.Vector3(),this.camera.position.clone().normalize().multiplyScalar(Math.max(this.local.entryDistance||300,(this.local.systemExtent||0)*6)),5500);await this.scaleTransition(()=>this.exitLocal());};
 // zoomImpulse is the zoom still to be applied, in natural-log units of distance. Each wheel notch adds the same
 // ratio, and the remainder is eased in at a fixed rate, so zooming is steady at every scale: no slow start, no runaway.
 C.prototype.zoomBy=function(factor){if(this.journey||this.surface)return;this.stopFlight();this.zoomImpulse=THREE.MathUtils.clamp((this.zoomImpulse||0)+Math.log(factor),-3,3);};
 C.prototype.navigationTick=function(dt){
  if(!this.loading&&!this.journey&&!this.surface)this.smallBodyTick?.(dt);
  // Focused on an object (camera target on a body, a followed asteroid, or a stellar close-up): keep the view upright.
  // Free-roaming the Solar System with nothing focused: free tilt.
  {const focus=this.items.find(i=>i.data.id===this.selected);
   this.controls.upright=Boolean(this.smallFocus||(this.local&&focus)||(focus&&this.controls.target.distanceTo(focus.pos)<Math.max(focus.radius*2,1e-9)));}
  if(this.loading||this.journey||this.surface||this.flight)return;if(this.smallFocus?.anim){this.zoomImpulse=0;return;}let body=this.items.find(i=>i.data.id===this.selected);let k=this.navKeys||new Set(),active=!document.body.classList.contains('observing')&&!document.body.classList.contains('searching');
  let pending=this.zoomImpulse||0;if(active){pending+=((k.has('KeyS')?1:0)-(k.has('KeyW')?1:0))*dt*1.6;let orbit=((k.has('KeyD')?1:0)-(k.has('KeyA')?1:0))*dt*.8;if(orbit){let v=this.camera.position.clone().sub(this.controls.target);v.applyAxisAngle(this.camera.up,orbit);this.camera.position.copy(this.controls.target).add(v);}}
  const step=pending*(1-Math.exp(-dt*(this.reduced?30:7.5)));
  this.zoomImpulse=Math.abs(pending-step)<1e-5?0:pending-step;
  const impulse=step/Math.max(dt,1e-4);
  let offset=this.camera.position.clone().sub(this.controls.target),d=offset.length();if(step){const next=THREE.MathUtils.clamp(d*Math.exp(step),this.controls.minDistance,this.controls.maxDistance);if(next===this.controls.minDistance||next===this.controls.maxDistance)this.zoomImpulse=0;d=next;offset.setLength(d);this.camera.position.copy(this.controls.target).add(offset);}
  let i=this.items.find(i=>i.data.id===this.selected);
  if(this.mode==='stars'&&!this.local&&this.selected==='origin'&&d<.0003&&impulse<-.001){window.dispatchEvent(new Event('cosmic-enter'));return;}if(this.mode==='solar'&&!this.local&&d>70&&impulse>.001){window.dispatchEvent(new Event('cosmic-exit'));return;}if(this.mode==='stars'&&!this.local&&impulse<-.001&&i&&d<.18&&this.controls.target.distanceTo(i.pos)<.01&&i.data.id!=='origin'){let direction=offset.clone().normalize();this.stellarCloseup(i,300);this.camera.position.copy(direction).multiplyScalar(300);this.controls.target.set(0,0,0);const local=this.local;this.companionsReady?.then(()=>{if(this.local===local&&local.planets?.length)this.systemOverview();});}
  else if(this.local&&!this.surface){this.camera.near=Math.max(.0002,Math.min(.02,(d-1)*.015));this.camera.updateProjectionMatrix();if(d>Math.max(900,(this.local.systemExtent||0)*6)&&!this.journey){let direction=offset.clone().normalize(),saved=this.local;originalExit.call(this);this.controls.target.copy(saved.item.pos);this.camera.position.copy(saved.item.pos).addScaledVector(direction,.2);}}
 };
 C.prototype.scaleTransition=async function(fn){
  const token=this.travelToken,cover=document.createElement('img');
  cover.src=this.renderer.domElement.toDataURL();cover.className='travel-rebase';
  this.renderer.domElement.parentElement.append(cover);
  try{
   if(token===this.travelToken)await fn();
   this.camera.lookAt(this.controls.target);this.renderer.render(this.scene,this.camera);
   const animation=cover.animate([{opacity:1},{opacity:0}],{duration:this.reduced?120:1000,easing:'ease-in-out',fill:'forwards'});
   await animation.finished.catch(()=>{});
  }finally{cover.remove();}
 };
 const AU_PER_PC=206264.806247;
 function frame(v,outward){const e=23.439291111*Math.PI/180,x=v.x,y=-v.z,z=v.y;
  return outward?v.set(x,Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y-Math.sin(e)*z)):v.set(x,-Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y+Math.sin(e)*z));
 }
 function hostRadius(item){return (item.data.planets?.[0]?.star_radius_solar||1)*.00465047/AU_PER_PC;}
 C.prototype.flyForward=function(pos,heading,clearance,minimum=2200){
  this.stopFlight();const from=this.camera.position.clone(),duration=Math.max(minimum,Math.min(5600,cruiseDuration(from.distanceTo(pos),clearance)*.30));
  return new Promise(done=>{this.flight={start:performance.now(),duration:this.reduced?900:duration,baseFov:this.camera.fov,from,pos:pos.clone(),heading:heading.clone().normalize(),clearance,done};});
 };
 C.prototype.trace=async function(context,solar,progress){
  const item=this.items.find(i=>i.data.id===this.selected);if(!item)return false;
  const token=this.travelToken=(this.travelToken||0)+1,valid=()=>this.travelToken===token;
  this.traceReturn={mode:this.mode,data:this.mode==='solar'?this.solarData:this.starsData,selected:this.selected,camera:this.camera.position.clone(),target:this.controls.target.clone(),up:this.camera.up.clone(),wasLocal:!!this.local,context};
  this.journey=true;this.controls.enabled=false;this.zoomImpulse=0;this.stopFlight();
  progress('Departing '+item.data.name,'Accelerated illustrative travel; orbits paused. Passing stars and dust are illustrative effects.');
  if(this.mode==='solar'&&this.camera.position.distanceTo(item.pos)>item.radius*12){const offset=this.camera.position.clone().sub(item.pos).normalize().multiplyScalar(item.radius*5);if(!await this.fly(item.pos,item.pos.clone().add(offset),1600)||!valid())return false;}
  if(this.mode==='stars'){
   const earthData=solar.objects.find(d=>d.id==='earth'),earthPc=frame(this.vector(earthData.xyz_au),true).multiplyScalar(1/AU_PER_PC);
   if(!this.local){
    const offset=this.camera.position.clone().sub(item.pos).normalize().multiplyScalar(hostRadius(item)*300);
    if(!await this.fly(item.pos,item.pos.clone().add(offset),1800)||!valid())return false;
   }
   let direction=earthPc.clone().sub(this.local?item.pos:this.camera.position).normalize();
   if(!await this.turnLeftTo(direction,1050,'EARTH - computed direction')||!valid())return false;
   if(this.local){
    const position=this.camera.position.clone().multiplyScalar(hostRadius(item)).add(item.pos),up=this.camera.up.clone();
    await this.scaleTransition(()=>{this.exitLocal();this.camera.position.copy(position);this.camera.up.copy(up);this.controls.target.copy(position).addScaledVector(direction,.001);this.controls.enabled=false;});
    if(!valid())return false;
   }
   const boundary=earthPc.clone().addScaledVector(direction,-60/AU_PER_PC);
   progress('Travelling toward the Solar System','Catalog parsec distances; gradual departure and deceleration.');
   if(!await this.flyForward(boundary,direction,hostRadius(item)*5,4600)||!valid())return false;
   const position=frame(this.camera.position.clone(),false).multiplyScalar(AU_PER_PC),up=frame(this.camera.up.clone(),false);
   direction=frame(direction,false);
   progress('Entering the Solar System','Catalog parsec scale to computed AU scale.');
   await this.scaleTransition(async()=>{await this.solar(solar);this.camera.position.copy(position);this.camera.up.copy(up);this.controls.target.copy(position).addScaledVector(direction,10);this.controls.enabled=false;this.controls.maxDistance=1000;});
   if(!valid())return false;
  }
  const earth=this.items.find(i=>i.data.id==='earth');if(!earth)return false;
  const direction=earth.pos.clone().sub(this.camera.position).normalize();
  progress('Approaching Earth','Slowing continuously into Earth orbit.');
  if(!await this.turnLeftTo(direction,850,'EARTH - computed direction')||!valid())return false;
  if(!await this.flyForward(earth.pos.clone().addScaledVector(direction,-earth.radius*2.8),direction,earth.radius*2,2800)||!valid())return false;
  this.selected='earth';this.controls.target.copy(earth.pos);this.camera.lookAt(earth.pos);
  progress('Arrived at Earth','Stay and explore Earth, or retrace the journey to your object.');
  return valid();
 };
 C.prototype.returnFromTrace=async function(progress=()=>{}){
  const r=this.traceReturn;if(!r){this.journey=false;this.controls.enabled=true;return false;}
  const token=this.travelToken=(this.travelToken||0)+1,valid=()=>this.travelToken===token;
  this.stopFlight();this.journey=true;this.controls.enabled=false;this.zoomImpulse=0;
  if(this.surface)this.exitLocal();
  progress('Returning to '+(r.data.objects.find(i=>i.id===r.selected)?.name||'object'),'Turning toward the destination before departure.');
  if(r.mode==='stars'){
   let heading=this.vector(r.context.direction_ecliptic).normalize();
   if(!await this.turnLeftTo(heading,1050,'RETURN - source direction')||!valid())return false;
   if(this.mode==='solar'){
    const earth=this.items.find(i=>i.data.id==='earth'),boundary=earth.pos.clone().addScaledVector(heading,60);
    if(!await this.flyForward(boundary,heading,earth.radius*2,3500)||!valid())return false;
    const position=frame(this.camera.position.clone(),true).multiplyScalar(1/AU_PER_PC),up=frame(this.camera.up.clone(),true);
    heading=frame(heading,true);
    await this.scaleTransition(()=>{this.stars(r.data,false);this.camera.position.copy(position);this.camera.up.copy(up);this.controls.target.copy(position).addScaledVector(heading,.001);this.controls.enabled=false;});
    if(!valid())return false;
   }else if(this.local){
    // A return requested while still near the departure star needs no Earth leg.
    if(this.local.item?.data.id===r.selected&&r.wasLocal){await this.fly(r.target,r.camera,1700);this.finishTrace(r);return valid();}
    this.exitLocal();
   }
   const item=this.items.find(i=>i.data.id===r.selected);if(!item)return false;
   heading=item.pos.clone().sub(this.camera.position).normalize();
   if(!await this.turnLeftTo(heading,1200,'RETURN - source direction')||!valid())return false;
   const end=item.pos.clone().addScaledVector(heading,-(r.wasLocal?hostRadius(item)*300:Math.max(hostRadius(item)*300,r.camera.distanceTo(item.pos))));
   progress('Approaching '+item.data.name,'Decelerating toward the destination; the camera keeps facing forward.');
   if(!await this.flyForward(end,heading,hostRadius(item)*4,4600)||!valid())return false;
   if(r.wasLocal){
    const offset=this.camera.position.clone().sub(item.pos).multiplyScalar(1/hostRadius(item)),up=this.camera.up.clone();
    await this.scaleTransition(()=>{this.stellarCloseup(item,offset.length());this.camera.position.copy(offset);this.camera.up.copy(up);this.controls.target.set(0,0,0);this.controls.enabled=false;});
    if(!valid())return false;
    await this.companionsReady;
    if(!await this.fly(r.target,r.camera,1800)||!valid())return false;
   }else{this.controls.target.copy(item.pos);if(!await this.fly(r.target,r.camera,1700)||!valid())return false;}
  }else{
   if(this.mode!=='solar')await this.scaleTransition(()=>this.solar(r.data));if(!valid())return false;
   const item=this.items.find(i=>i.data.id===r.selected);if(!item)return false;
   const heading=item.pos.clone().sub(this.camera.position).normalize();
   if(!await this.turnLeftTo(heading,1600,'RETURN - '+item.data.name)||!valid())return false;
   const end=item.pos.clone().addScaledVector(heading,-Math.max(item.radius*6,r.camera.distanceTo(item.pos)));if(!await this.flyForward(end,heading,item.radius*2,3500)||!valid())return false;this.controls.target.copy(item.pos);
   if(!await this.fly(r.target,r.camera,2200)||!valid())return false;
  }
  this.finishTrace(r);return valid();
 };
 C.prototype.finishTrace=function(r){this.traceReturn=null;this.journey=false;this.controls.enabled=true;this.selected=r.selected;this.beaconLabel?.remove();this.beaconLabel=null;this.earthBeacon=null;};
 C.prototype.stayOnEarth=function(){this.travelToken=(this.travelToken||0)+1;this.stopFlight();this.journey=false;this.controls.enabled=true;this.selected='earth';this.beaconLabel?.remove();this.beaconLabel=null;this.earthBeacon=null;};
 C.prototype.cancelTrace=async function(){
  const r=this.traceReturn;if(!r)return;
  this.travelToken=(this.travelToken||0)+1;this.stopFlight();this.exitLocal();
  await this.scaleTransition(async()=>{if(r.mode==='solar')await this.solar(r.data);else this.stars(r.data,false);if(r.wasLocal){const item=this.items.find(i=>i.data.id===r.selected);this.stellarCloseup(item);}this.camera.position.copy(r.camera);this.controls.target.copy(r.target);if(r.up)this.camera.up.copy(r.up);});
  this.finishTrace(r);
 };

 C.prototype.sizeComparison=async function(){
  let data=this.physicalSolar||this.solarData;if(!data)return;this.physicalSolar=data;let cursor=-2;let objects=data.objects.map(d=>{let radius=d.radius_km/695700;cursor+=radius;let x=cursor;cursor+=radius+.22;return {...d,xyz_au:[x,0,0],display_radius_factor:149597870.7/695700,orbit_au:null};});await this.solar({...data,size_layout:true,objects});this.mode='sizes';this.selected='sun';let extent=cursor+2;await this.fly(new THREE.Vector3((cursor-2)/2,0,0),new THREE.Vector3((cursor-2)/2,.5,extent*1.4),1300);$('size-note').textContent='True radius ratios · arranged centers · units R☉';$('scene-subtitle').textContent='Physical size comparison. Centers are arranged for comparison, not catalog positions.';
 };
 C.prototype.planetOrbit=async function(id=this.selected){
  if(this.mode==='sizes')await this.solar(this.physicalSolar);let i=this.items.find(i=>i.data.id===id);if(!i)return;this.selected=id;this.orbits.children.forEach(o=>o.visible=o.userData.body===id);this.orbits.visible=true;
  let extent=Math.max(.1,...(i.data.orbit_au||[]).map(p=>Math.hypot(...p)));if(!i.data.orbit_au){await this.overview();return;}
  let direction=new THREE.Vector3(.1,.65,1).normalize();await this.fly(new THREE.Vector3(),direction.multiplyScalar(extent*3.1),1600,true);$('scene-subtitle').textContent=i.data.name+' orbit around the Sun · calculated geometry, presentation radii';
 };


 C.prototype.turnLeftTo=function(direction,duration=1800,label='EARTH - computed direction'){
  this.stopFlight();if(direction.lengthSq()<1e-20)return Promise.resolve(true);
  this.earthBeacon=direction.clone().normalize();
  if(!this.beaconLabel){this.beaconLabel=document.createElement('span');this.beaconLabel.className='earth-beacon';document.getElementById('stage').append(this.beaconLabel);}
  this.beaconLabel.textContent=label;this.beaconLabel.style.display=label?'':'none';
  const target=this.camera.position.clone().add(this.earthBeacon),matrix=new THREE.Matrix4().lookAt(this.camera.position,target,this.camera.up);
  return new Promise(done=>{this.pan={start:performance.now(),duration:this.reduced?500:duration,fromQuaternion:this.camera.quaternion.clone(),toQuaternion:new THREE.Quaternion().setFromRotationMatrix(matrix),distance:Math.max(.001,this.camera.position.distanceTo(this.controls.target)),done};});
 };


 C.prototype.addCatalogSky=function(data){if(this.sky)return;this.sky=new THREE.Group();this.sky.userData.catalog=true;let eps=23.439291111*Math.PI/180;for(let d of data.objects){if(d.phot_g_mean_mag!=null&&d.phot_g_mean_mag>12)continue;let p=d.xyz_pc,e=[p[0],Math.cos(eps)*p[1]+Math.sin(eps)*p[2],-Math.sin(eps)*p[1]+Math.cos(eps)*p[2]],sprite=this.makeHalo(d);sprite.userData.catalogObject=d;sprite.userData.direction=this.vector(e).normalize();this.sky.add(sprite);}this.scene.add(this.sky);};

}