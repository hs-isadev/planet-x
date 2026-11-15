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
