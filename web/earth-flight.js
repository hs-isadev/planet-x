import * as THREE from 'three';
const AU_PER_PC=206264.806247;
const clamp=t=>Math.max(0,Math.min(1,t));
const ease=t=>t*t*(3-2*t);
const ENTRY_AU=60;
const MAX_BANK=.20;
const routes=['head-on','twist','left','right'];
const randomRoute=()=>routes[Math.floor(Math.random()*routes.length)];
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
 const entry=radial.clone().addScaledVector(side,.38*Math.abs(approach)).addScaledVector(high,.23*Math.abs(approach)).normalize();
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
export function earthArcPose(start,earth,radius,progress,approach=1,route='right'){
 const t=clamp(progress),offset=start.clone().sub(earth),r0=offset.length();
 const lit=earth.clone().negate().normalize();if(!lit.lengthSq())lit.set(1,0,0);
 const endDirection=lit.clone().add(new THREE.Vector3(0,.18,0)).normalize();
 const from=offset.normalize(),rotation=new THREE.Quaternion().setFromUnitVectors(from,endDirection);
 const direction=from.clone().applyQuaternion(new THREE.Quaternion().slerp(rotation,route==='twist'?0:ease(t)));
 const lift=route==='twist'?0:Math.sin(Math.PI*t)**2;
 const lateral=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),endDirection).normalize();
 direction.y+=lift*.55;
 direction.addScaledVector(lateral,lift*.55*approach).normalize();
 const finalRadius=radius*6.5;
 const distance=finalRadius+(Math.max(r0,finalRadius)-finalRadius)*(1-t)**2;
 return {position:earth.clone().addScaledVector(direction,distance),target:earth.clone()};
}
// All steering geometry lives in AU, including the interstellar leg. Switching
// render scales can then sample the same line on both sides of the boundary.
export function inclinedEarthPath(start, earth, radius, up, departureTime, entryTime, totalTime){
 const radial=start.clone().sub(earth).normalize();
 const vertical=up.clone().addScaledVector(radial,-up.dot(radial));
 if(vertical.lengthSq()<1e-8){
  vertical.set(Math.abs(radial.x)<.9?1:0,Math.abs(radial.x)<.9?0:1,0);
  vertical.addScaledVector(radial,-vertical.dot(radial));
 }
 vertical.normalize();
 const lateral=vertical.clone().cross(radial);
 const sunward=earth.clone().negate().normalize();
 const arrivalAngle=Math.atan2(sunward.dot(lateral),sunward.dot(radial));
 const sweep=(Math.sign(arrivalAngle)||1)*Math.max(Math.PI/4,Math.abs(arrivalAngle));
 const finalRadius=radius*6.5;
 const finalElevation=THREE.MathUtils.clamp(Math.asin(THREE.MathUtils.clamp(sunward.dot(vertical),-1,1)),-.38,.38);
 const finalHeight=finalRadius*Math.sin(finalElevation);
 const finalRun=finalRadius*Math.cos(finalElevation);
 const joinRun=Math.max(finalRun*1.15,Math.min(2.2,start.distanceTo(earth)*.28));
 const joinHeight=joinRun*.32;
 const join=earth.clone().addScaledVector(radial,joinRun).addScaledVector(vertical,joinHeight);
 const backward=start.clone().sub(join).normalize();
 const length=start.distanceTo(join);
 const boundary=Math.min(length,ENTRY_AU);
 const turnTime=totalTime*.75;
 const curveTime=totalTime-turnTime;
 const inboundTime=turnTime-entryTime;
 const interstellar=entryTime>departureTime;
 const inboundLength=interstellar?boundary:length;
 const closingDistance=joinRun-finalRun;
 const projection=backward.dot(radial);
 const endSpeed=Math.min(3*closingDistance/(curveTime*projection),1.25*inboundLength/inboundTime);
 const slope=endSpeed*curveTime*projection/closingDistance;
 const verticalTangent=-endSpeed*curveTime*backward.dot(vertical);
 const inboundTail=endSpeed*inboundTime;
 const cruiseTail=(3*inboundLength-2*inboundTail)/inboundTime*(entryTime-departureTime);
 return elapsed=>{
  if(elapsed<entryTime){
   const t=clamp((elapsed-departureTime)/(entryTime-departureTime));
   const distance=boundary+(length-boundary-cruiseTail)*(1-t*t)**5+cruiseTail*(1-t);
   return join.clone().addScaledVector(backward,distance);
  }
  if(elapsed<turnTime){
   const t=clamp((elapsed-entryTime)/inboundTime);
   const distance=interstellar
    ? (inboundLength-inboundTail)*(1-t)**3+inboundTail*(1-t)
    : inboundLength*(1-ease(t))+inboundTail*t*t*(1-t);
   return join.clone().addScaledVector(backward,distance);
  }
  const t=clamp((elapsed-turnTime)/curveTime);
  const run=finalRun+closingDistance*(1-t)**2*(1+(2-slope)*t);
  const height=THREE.MathUtils.lerp(joinHeight,finalHeight,ease(t))+verticalTangent*t*(1-t)**2;
  return earth.clone().addScaledVector(radial.clone().applyAxisAngle(vertical,sweep*ease(t)),run)
   .addScaledVector(vertical,height);
 };
}

export function rolledUpVector(position,target,up,progress,direction){
 const forward=target.clone().sub(position).normalize();
 const axisUp=up.clone().addScaledVector(forward,-up.dot(forward));
 if(axisUp.lengthSq()<1e-8){
  axisUp.set(Math.abs(forward.x)<.9?1:0,Math.abs(forward.x)<.9?0:1,0);
  axisUp.addScaledVector(forward,-axisUp.dot(forward));
 }
 return axisUp.normalize().applyAxisAngle(forward,direction*Math.PI*2*ease(clamp(progress)));
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
 C.prototype.solar=async function(data,options){
  const ready=solar.call(this,data,options),version=this.version;
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
 C.prototype.trace=async function(context,solarData,progress,route=randomRoute()){
  if(typeof route==='number')route=route<0?'left':'right';
  const roll=route==='roll-left'?-1:route==='roll-right'?1:route==='twist'?(Math.random()<.5?-1:1):0;
  const spiral=route==='head-on';
  const approach=route==='left'?-1:1;
  const straight=roll||spiral;
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
  const launchDirection=earth.clone().sub(start).normalize();
  const nearSourceAt=Math.max(0,sourceCenter.clone().sub(start).dot(launchDirection));
  const clearLaunch=start.clone().addScaledVector(launchDirection,nearSourceAt).distanceTo(sourceCenter)>sourceRadius*1.2;
  const rollInPlace=roll && clearLaunch;
  const surface=rollInPlace?start:surfacePose(start,sourceCenter,sourceRadius,earth,1).position;
  const departurePc=stellar?surface.clone().multiplyScalar(physicalRadius).add(item.pos):null;
  const corridor=stellar&&!spiral?solarEntry(departurePc,earthPc,original.up,roll?0:approach):null;
  const boundaryPc=corridor?earthPc.clone().addScaledVector(corridor.entry,ENTRY_AU/AU_PER_PC):null;
  const arrivalStart=boundaryPc?frame(boundaryPc.clone(),false).multiplyScalar(AU_PER_PC):surface.clone();
  const arrivalSide=corridor?frame(corridor.side.clone(),false):null;
  const retired=[];
  let phase='surface',lastStage='';
  const departMs=this.reduced?120:stellar?1050:530;
  const cruiseMs=stellar?(this.reduced?240:spiral?4200:roll?4300:3700):0;
  const arcMs=this.reduced?(spiral?400:270):spiral?(stellar?6400:8200):roll?(stellar?5000:6800):4100;
  const total=departMs+cruiseMs+arcMs;
  const bank=straight?0:MAX_BANK;
  const arrivalUp=stellar?frame(original.up.clone(),false):original.up;
  const spiralPosition=spiral?inclinedEarthPath(
   stellar?frame(departurePc.clone(),false).multiplyScalar(AU_PER_PC):surface,
   earthAu,solarEarth.radius,arrivalUp,departMs,departMs+cruiseMs,total
  ):null;
  const sample=progressValue=>{
   const ms=progressValue*total;
   let pose;
   if(ms<departMs){
    pose=rollInPlace?{position:start,target:earth}:surfacePose(start,sourceCenter,sourceRadius,earth,ms/departMs);
    const look=new THREE.Matrix4().lookAt(pose.position,pose.target,original.up),q1=new THREE.Quaternion().setFromRotationMatrix(look);
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
    if(spiralPosition){
     const position=frame(spiralPosition(ms),true).multiplyScalar(1/AU_PER_PC);
     pose={position,target:earthPc};
    }else{
     const t=clamp((ms-departMs)/cruiseMs);
     const end=ENTRY_AU/AU_PER_PC,r0=departurePc.distanceTo(earthPc);
     const tail=2*(ENTRY_AU-solarEarth.radius*6.5)*cruiseMs/arcMs/AU_PER_PC;
     // Match the arrival leg's closing speed at the scale change.
     const radius=end+(r0-end-tail)*(1-t*t)**5+tail*(1-t);
     const bearing=corridor.radial.clone().applyQuaternion(new THREE.Quaternion().slerp(corridor.rotation,ease(t)));
     const position=earthPc.clone().addScaledVector(bearing,radius);
     pose={position,target:bankedTarget(position,earthPc,corridor.side,bank*ease(Math.min(1,t*3)))};
    }
   }else{
    if(phase!=='arrival'){
     if(stellar){this.activateFlightSolar(retired);this.camera.up.copy(frame(original.up.clone(),false));}
     phase='arrival';
    }
    const t=clamp((ms-departMs-cruiseMs)/arcMs);
    pose=spiralPosition?{position:spiralPosition(ms),target:earthAu}
     :earthArcPose(arrivalStart,earthAu,solarEarth.radius,t,approach,roll?'twist':route);
    if(stellar && bank)pose.target=bankedTarget(pose.position,earthAu,arrivalSide,bank*(1-ease(Math.min(1,t*1.6))));
   }
   if(roll && !this.reduced){
    const rollProgress=(ms-departMs)/(total-departMs);
    pose.up=rolledUpVector(pose.position,pose.target,phase==='arrival'?arrivalUp:original.up,rollProgress,roll);
   }
   let stage='Closing in on Earth';
   if(ms<departMs)stage='Facing Earth from '+item.data.name;
   else if(ms<departMs+cruiseMs)stage='Crossing toward the Solar System';
   else if(spiral && progressValue>=.75)stage='Spiraling down toward Earth';
   else if(roll)stage='Direct approach to Earth';
   else if(!spiral)stage='Arcing toward sunlit Earth';
   if(stage!==lastStage){lastStage=stage;progress(stage,'Continuous illustrative flight · catalog distances and enlarged body radii · not a physical trajectory.');}
   return pose;
  };
  const reached=await new Promise(done=>{this.flight={start:performance.now(),duration:total,baseFov:this.camera.fov,continuousEarth:true,sample,done};});
  if(retired.length)setTimeout(()=>retired.forEach(dispose),250);
  if(!reached||token!==this.travelToken)return false;
  this.selected='earth';this.camera.up.copy(arrivalUp);this.controls.target.copy(earthAu);this.camera.lookAt(earthAu);
  this.camera.near=.000001;this.camera.updateProjectionMatrix();
  progress(roll||spiral?'Earth':'Sunlit Earth','Stay in orbit or return to your object. The globe remains at a comfortable viewing distance.');return true;
 };
}
