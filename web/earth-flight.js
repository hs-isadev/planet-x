import * as THREE from 'three';
const AU_PER_PC=206264.806247;
const clamp=t=>Math.max(0,Math.min(1,t));
const ease=t=>t*t*(3-2*t);
const ENTRY_AU=60;
const MAX_BANK=.28;
function frame(v,outward){const e=23.439291111*Math.PI/180,x=v.x,y=-v.z,z=v.y;return outward?v.set(x,Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y-Math.sin(e)*z)):v.set(x,-Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y+Math.sin(e)*z));}
function dispose(group){group?.traverse(o=>{o.geometry?.dispose();for(const m of Array.isArray(o.material)?o.material:[o.material]){m?.map?.dispose();m?.dispose();}});}
// Follow an offset corridor and turn the view into it before the AU scale change.
export function solarEntry(from, earth, up, approach=1){
 const radial=from.clone().sub(earth).normalize();
 const side=up.clone().cross(radial);
 if(side.lengthSq()<1e-8)side.set(Math.abs(radial.x)<.9?1:0,0,Math.abs(radial.x)<.9?0:1).cross(radial);
 side.normalize();
 const high=radial.clone().cross(side).normalize();
 side.multiplyScalar(approach);
 const entry=radial.clone().addScaledVector(side,.38).addScaledVector(high,.23).normalize();
 return {radial,entry,side,rotation:new THREE.Quaternion().setFromUnitVectors(radial,entry)};
}

function bankedTarget(position,earth,side,angle){
 const offset=position.clone().sub(earth),distance=offset.length();
 const radial=offset.normalize();
 const lateral=side.clone().addScaledVector(radial,-side.dot(radial)).normalize();
 return earth.clone().addScaledVector(lateral, distance*Math.tan(angle));
}

// Descend from above the arrival plane and wrap toward Earth's lit hemisphere.
// Positions are presentation geometry in AU, using the displayed Earth radius.
export function earthArcPose(start,earth,radius,progress,approach=1){
 const t=clamp(progress),offset=start.clone().sub(earth),r0=offset.length();
 const lit=earth.clone().negate().normalize();if(!lit.lengthSq())lit.set(1,0,0);
 const endDirection=lit.clone().add(new THREE.Vector3(0,.18,0)).normalize();
 const from=offset.normalize(),rotation=new THREE.Quaternion().setFromUnitVectors(from,endDirection);
 const direction=from.clone().applyQuaternion(new THREE.Quaternion().slerp(rotation,ease(t)));
 const horizontal=new THREE.Vector3(0,1,0).cross(endDirection);
 direction.y+=Math.sin(Math.PI*t)**2*.65;
 direction.addScaledVector(horizontal, approach*.8*Math.sin(Math.PI*t)**2).normalize();
 const finalRadius=radius*6.5;
 const distance=finalRadius+(r0-finalRadius)*Math.pow(1-t,3);
 return {position:earth.clone().addScaledVector(direction,distance),target:earth.clone()};
}
export function surfacePose(from,center,radius,earth,progress){
 const t=clamp(progress),heading=earth.clone().sub(center).normalize();
 if(!heading.lengthSq())heading.set(0,0,1);
 const outward=from.clone().sub(center);if(!outward.lengthSq())outward.copy(heading);
 const r0=Math.max(radius*1.22,from.distanceTo(center)),r1=radius*1.45;
 const u=ease(t),rotation=new THREE.Quaternion().setFromUnitVectors(outward.normalize(),heading);
 const direction=outward.clone().applyQuaternion(new THREE.Quaternion().slerp(rotation,u));
 // Interpolate apparent size: the surface becomes visible during the approach,
 // rather than compressing all the close-up into its final animation frame.
 const distance=1/((1-u)/r0+u/r1);
 const position=center.clone().addScaledVector(direction,distance);
 return {position,target:earth.clone()};
}
export function installEarthFlight(C){
 const clear=C.prototype.clear,solar=C.prototype.solar;
 C.prototype.solar=async function(data){
  const ready=solar.call(this,data),version=this.version;
  this.solarFlightReady=false;
  await ready;
  if(this.version!==version||this.mode!=='solar'||!this.items.some(i=>i.data.id==='earth'))return;
  await this.renderer.compileAsync?.(this.scene,this.camera).catch(()=>{});
  if(this.version===version)this.solarFlightReady=true;
 };
 C.prototype.clear=function(){
  if(this.mode==='solar'&&this.solarFlightReady&&!this.solarData?.size_layout&&this.items.some(i=>i.data.id==='earth')){
   if(this.cachedFlightSolar){dispose(this.cachedFlightSolar.content);this.cachedFlightSolar.items.forEach(i=>i.label.remove());}
   this.cachedFlightSolar={content:this.content,items:this.items,orbits:this.orbits,data:this.solarData,orbitDays:this.orbitDays,orbitEpoch:this.orbitEpoch};
   this.scene.remove(this.content);this.items.forEach(i=>i.label.remove());
   this.content=new THREE.Group();this.scene.add(this.content);this.items=[];this.solarFlightReady=false;
  }
  clear.call(this);
 };
 C.prototype.activateFlightSolar=function(retired){
  const cached=this.cachedFlightSolar;if(!cached)throw Error('Earth assets are not ready.');
  // Swap scene groups on the render frame. Dispose the outgoing group after arrival.
  this.version=(this.version||0)+1;
  retired.push(this.content);
  this.scene.remove(this.content);
  this.content=cached.content;this.items=cached.items;this.orbits=cached.orbits;
  this.scene.add(this.content);this.content.visible=true;
  document.getElementById('labels').replaceChildren(...this.items.map(item=>item.label));
  this.solarData=cached.data;this.physicalSolar=cached.data;this.orbitDays=cached.orbitDays;this.orbitEpoch=cached.orbitEpoch;
  this.mode='solar';this.ambient.intensity=.16;this.light.visible=true;this.controls.minDistance=.000001;this.controls.maxDistance=1000;
  this.camera.near=.000001;this.camera.far=100000;this.camera.updateProjectionMatrix();
  this.cachedFlightSolar=null;this.solarFlightReady=true;
 };
 C.prototype.trace=async function(context,solarData,progress,approach=1){
  const item=this.items.find(i=>i.data.id===this.selected);if(!item||item.data.id==='earth')return false;
  const stellar=this.mode==='stars';
  if(stellar&&!this.cachedFlightSolar)throw Error('Earth scene is still preparing. Try again when Trace back to Earth is enabled.');
  const token=this.travelToken=(this.travelToken||0)+1;
  const original={mode:this.mode,data:stellar?this.starsData:this.solarData,selected:this.selected,camera:this.camera.position.clone(),target:this.controls.target.clone(),up:this.camera.up.clone(),wasLocal:!!this.local,context};
  this.stopFlight();this.traceReturn=original;this.journey=true;this.controls.enabled=false;this.zoomImpulse=0;this.navKeys?.clear();
  const solarEarth=stellar?this.cachedFlightSolar.items.find(i=>i.data.id==='earth'):this.items.find(i=>i.data.id==='earth');
  const earthAu=solarEarth.pos.clone(),earthPc=frame(earthAu.clone(),true).multiplyScalar(1/AU_PER_PC);
  const physicalRadius=(item.data.planets?.[0]?.star_radius_solar||1)*.00465047/AU_PER_PC;
  let sourceCenter=item.pos.clone(),sourceRadius=item.radius,earth=earthAu.clone();
  if(stellar){
   if(!this.local){
    const position=this.camera.position.clone().sub(item.pos).multiplyScalar(1/physicalRadius);
    const target=this.controls.target.clone().sub(item.pos).multiplyScalar(1/physicalRadius),up=this.camera.up.clone();
    this.stellarCloseup(item,position.length());this.camera.position.copy(position);this.controls.target.copy(target);this.camera.up.copy(up);
   }
   sourceCenter=new THREE.Vector3();sourceRadius=1;earth=earthPc.clone().sub(item.pos).multiplyScalar(1/physicalRadius);
   this.camera.far=Math.max(100000,this.camera.position.length()*3);this.camera.updateProjectionMatrix();
  }
  this.controls.enabled=false;
  const start=this.camera.position.clone(),q0=this.camera.quaternion.clone();
  const surface=surfacePose(start,sourceCenter,sourceRadius,earth,1).position;
  const departurePc=stellar?surface.clone().multiplyScalar(physicalRadius).add(item.pos):null;
  const corridor=stellar?solarEntry(departurePc,earthPc,original.up,approach):null;
  const boundaryPc=stellar?earthPc.clone().addScaledVector(corridor.entry,ENTRY_AU/AU_PER_PC):null;
  const arrivalStart=stellar?frame(boundaryPc.clone(),false).multiplyScalar(AU_PER_PC):surface.clone();
  const arrivalSide=stellar?frame(corridor.side.clone(),false):null;
  const retired=[];
  let phase='surface',lastStage='';
  const departMs=this.reduced?150:1800,cruiseMs=stellar?(this.reduced?150:3000):0,arcMs=this.reduced?350:4600,total=departMs+cruiseMs+arcMs;
  const sample=progressValue=>{
   const ms=progressValue*total;
   let pose;
   if(ms<departMs){
    pose=surfacePose(start,sourceCenter,sourceRadius,earth,ms/departMs);
    const look=new THREE.Matrix4().lookAt(pose.position,pose.target,this.camera.up),q1=new THREE.Quaternion().setFromRotationMatrix(look);
    const q=q0.clone().slerp(q1,ease(clamp((ms/departMs-.45)/.55)));
    pose.target=pose.position.clone().addScaledVector(new THREE.Vector3(0,0,-1).applyQuaternion(q),Math.max(sourceRadius*2,pose.position.distanceTo(earth)));
   }else if(stellar&&ms<departMs+cruiseMs){
    if(phase==='surface'){
     // Rebase once in the same animation frame; no awaited assets or overlays.
     if(this.localGroup){
     this.scene.remove(this.localGroup);
     retired.push(this.localGroup);
     this.localGroup=null;this.local=null;
     document.body.classList.remove('stellar-closeup');
    }else this.exitLocal();
    this.content.visible=true;this.controls.enabled=false;
     this.camera.near=1e-12;this.camera.far=100000;this.camera.updateProjectionMatrix();phase='cruise';
    }
    const t=clamp((ms-departMs)/cruiseMs),u=t*t*(2-t);
    const end=ENTRY_AU/AU_PER_PC,r0=departurePc.distanceTo(earthPc);
    const tail=3*(ENTRY_AU-solarEarth.radius*6.5)*cruiseMs/arcMs/AU_PER_PC;
    const radius=end+(r0-end)*Math.pow(1-u,6)+tail*u*(1-u);
    const bearing=corridor.radial.clone().applyQuaternion(new THREE.Quaternion().slerp(corridor.rotation,ease(t)));
    const position=earthPc.clone().addScaledVector(bearing,radius);
    pose={position,target:bankedTarget(position,earthPc,corridor.side,MAX_BANK*ease(Math.min(1,t*3)))};
   }else{
    if(phase!=='arrival'){
     if(stellar){this.activateFlightSolar(retired);this.camera.up.copy(frame(original.up.clone(),false));}
     phase='arrival';
    }
    const t=clamp((ms-departMs-cruiseMs)/arcMs);
    pose=earthArcPose(arrivalStart,earthAu,solarEarth.radius,t,approach);
    if(stellar)pose.target=bankedTarget(pose.position,earthAu,arrivalSide,MAX_BANK*(1-ease(Math.min(1,t*1.6))));
   }
   const stage=ms<departMs?'surface':ms<departMs+cruiseMs?'cruise':'arrival';
   if(stage!==lastStage){lastStage=stage;progress(stage==='surface'?'Facing Earth from '+item.data.name:stage==='cruise'?'Crossing toward the Solar System':'Arcing toward sunlit Earth','Continuous illustrative flight · catalog distances and enlarged body radii · not a physical trajectory.');}
   return pose;
  };
  const reached=await new Promise(done=>{this.flight={start:performance.now(),duration:total,baseFov:this.camera.fov,continuousEarth:true,sample,done};});
  if(retired.length)setTimeout(()=>retired.forEach(dispose),250);
  if(!reached||token!==this.travelToken)return false;
  this.selected='earth';this.controls.target.copy(earthAu);this.camera.lookAt(earthAu);
  this.camera.near=.000001;this.camera.updateProjectionMatrix();
  progress('Sunlit Earth','Stay in orbit or return to your object. The globe remains at a comfortable viewing distance.');return true;
 };
}
