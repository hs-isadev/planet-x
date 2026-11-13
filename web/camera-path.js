import * as THREE from 'three';

export const smooth=t=>t*t*t*(t*(t*6-15)+10);

// Geometric distance gives the final few radii time on screen even after a
// journey spanning many orders of magnitude. These are presentation paths.
export function orbitPose(from,fromTarget,to,toTarget,progress){
 const t=smooth(progress),a=from.clone().sub(fromTarget),b=to.clone().sub(toTarget);
 const da=a.length(),db=b.length(),target=fromTarget.clone().lerp(toTarget,t);
 if(da<1e-12||db<1e-12)return {position:from.clone().lerp(to,t),target};
 const rotation=new THREE.Quaternion().setFromUnitVectors(a.normalize(),b.normalize());
 const direction=a.applyQuaternion(new THREE.Quaternion().slerp(rotation,t));
 const distance=Math.exp(Math.log(da)+(Math.log(db)-Math.log(da))*t);
 return {position:target.clone().addScaledVector(direction,distance),target};
}

export function cruisePose(from,to,heading,clearance,progress){
 const length=from.distanceTo(to),t=smooth(progress),c=Math.max(clearance,1e-12);
 const half=Math.log1p(length/(2*c));
 const travelled=t<=.5?c*Math.expm1(half*t*2):length-c*Math.expm1(half*(1-t)*2);
 const position=from.clone().lerp(to,length?travelled/length:1);
 return {position,target:position.clone().addScaledVector(heading,Math.max(c*2,position.distanceTo(to)+c))};
}

export function cruiseDuration(length,clearance){
 return THREE.MathUtils.clamp(4500+Math.log10(1+length/Math.max(clearance,1e-12))*2000,6500,22000);
}

export function orbitDuration(from,fromTarget,to,toTarget,minimum=1800){
 const a=from.distanceTo(fromTarget),b=to.distanceTo(toTarget);
 return Math.max(minimum,Math.min(14000,Math.abs(Math.log10(Math.max(a,1e-12)/Math.max(b,1e-12)))*2400));
}


// One path in AU, even when the renderer changes from catalog parsecs to AU.
export function earthApproach(from, earth, daylight, up, radius, fromLook, reduced=false){
 const arrival=radius*3.3, offset=from.clone().sub(earth);
 const distance=offset.length(), start=distance>1e-12?offset.normalize():daylight.clone();
 const end=daylight.clone().addScaledVector(up,.24).normalize();
 const alignment=THREE.MathUtils.clamp(start.dot(end),-1,1), angle=Math.acos(alignment);
 const side=end.clone().addScaledVector(start,-alignment);
 if(side.lengthSq()<1e-12){
  side.copy(up).addScaledVector(start,-up.dot(start));
  if(side.lengthSq()<1e-12)side.set(1,0,0).addScaledVector(start,-start.x);
 }
 side.normalize();
 const lift=start.clone().cross(side).normalize();
 const span=Math.max(1, distance/arrival), logSpan=Math.log(span);
 return progress=>{
  const t=smooth(progress);
  const radiusNow=distance>arrival?arrival*Math.exp(logSpan*(1-t)):THREE.MathUtils.lerp(distance,arrival,t);
  // Let the limb sweep into view as the flight curves onto the sunlit side.
  const sweep=smooth(t);
  const angleNow=angle*sweep;
  const arc=reduced?0:.34*Math.sin(Math.PI*t)**2;
  const radial=start.clone().multiplyScalar(Math.cos(angleNow))
    .addScaledVector(side,Math.sin(angleNow)).addScaledVector(lift,arc).normalize();
  const position=t===0?from.clone():earth.clone().addScaledVector(t===1?end:radial,radiusNow);
  const heading=earth.clone().sub(position).normalize();
  const glance=reduced?0:.19*Math.sin(4*Math.PI*progress)*Math.sin(Math.PI*progress)**2;
  const glanceAxis=heading.clone().cross(up).normalize();
  heading.addScaledVector(glanceAxis,glance).normalize();
  const turn=smooth(Math.min(1,progress/.32));
  const rotation=new THREE.Quaternion().setFromUnitVectors(fromLook,heading);
  const forward=fromLook.clone().applyQuaternion(new THREE.Quaternion().slerp(rotation,turn));
  return {position,forward,distance:Math.max(radius*2,position.distanceTo(earth))};
 };
}
