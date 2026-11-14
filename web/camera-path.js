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


// A single AU path crosses the catalog/planet renderer boundary unchanged.
const SWEEP_START = .75;
const SWEEP_ANGLE = 3 * Math.PI / 2;

function hermite(start,end,startSlope,endSlope,t){
 const square=t*t,cube=square*t;
 return (2*cube-3*square+1)*start+(cube-2*square+t)*startSlope+
  (-2*cube+3*square)*end+(cube-square)*endSlope;
}

export function earthApproach(from,earth,daylight,up,radius,fromLook,reduced=false){
 const offset=from.clone().sub(earth),distance=offset.length();
 const start=distance>1e-12?offset.normalize():daylight.clone();
 const end=daylight.clone().addScaledVector(up,.22).normalize();
 const entry=start.clone().addScaledVector(end,-start.dot(end));
 if(entry.lengthSq()<1e-12)entry.copy(up).addScaledVector(end,-up.dot(end));
 if(entry.lengthSq()<1e-12)entry.set(1,0,0).addScaledVector(end,-end.x);
 entry.normalize();
 const normal=entry.clone().cross(end).negate().normalize();
 const arcUp=normal.clone().multiplyScalar(normal.dot(up)<0?-1:1);

 const initial=Math.max(distance,radius*1.05);
 const arrival=radius*(Math.abs(initial/radius-4.5)<.15?4.8:4.5);
 const farRing=Math.max(arrival*1.08,Math.min(radius*11,initial*.76));
 const ring=initial>farRing?farRing:Math.sqrt(initial*arrival);
 const approachEnd=earth.clone().addScaledVector(entry,ring);
 const incoming=from.clone().sub(approachEnd), approachLength=incoming.length();
 incoming.normalize();
 const b=Math.log(ring),c=Math.log(arrival);
 const reach=Math.log1p(approachLength/ring);
 const departureSlope=Math.min(reach*.035,.13);
 // The incoming line meets the sweep with the same radial velocity. A short
 // blend near the limb aligns that velocity without stopping at the entry.
 const joinSlope=Math.sign(c-b)*Math.min(reach/SWEEP_START,Math.abs(c-b)/(1-SWEEP_START))*1.35;
 const joinDirection=entry.clone().multiplyScalar(joinSlope>0?-1:1);
 const viewTurn=new THREE.Quaternion(),turnTo=new THREE.Quaternion();

 return progress=>{
  const t=THREE.MathUtils.clamp(progress,0,1), sweeping=t>=SWEEP_START;
  let position;
  if(sweeping){
   const q=(t-SWEEP_START)/(1-SWEEP_START);
   const radiusNow=Math.exp(hermite(b,c,joinSlope*(1-SWEEP_START),0,q));
   const angle=(reduced?-Math.PI/2:SWEEP_ANGLE)*smooth(q);
   const radial=entry.clone().applyAxisAngle(normal,angle);
   position=earth.clone().addScaledVector(t===1?end:radial,radiusNow);
  }else{
   const remaining=ring*Math.expm1(hermite(reach,0,-departureSlope,-Math.abs(joinSlope)*SWEEP_START,t/SWEEP_START));
   const mix=smooth(Math.max(0,1-remaining/(ring*.45)));
   position=t===0?from.clone():approachEnd.clone().addScaledVector(incoming,remaining*(1-mix))
    .addScaledVector(joinDirection,remaining*mix);
  }
  const separation=position.clone().sub(earth);
  const minimum=Math.min(initial,radius*1.025);
  if(t>0&&separation.length()<minimum)position.copy(earth).addScaledVector(separation.normalize(),minimum);
  const heading=earth.clone().sub(position).normalize();
  if(heading.lengthSq()<1e-16)heading.copy(fromLook);
  const turn=smooth(Math.min(1,t/.3));
  turnTo.setFromUnitVectors(fromLook,heading);
  const forward=fromLook.clone().applyQuaternion(viewTurn.identity().slerp(turnTo,turn));
  return {position,forward,distance:Math.max(radius*2,position.distanceTo(earth)),arcUp};
 };
}
