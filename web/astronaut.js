import * as THREE from 'three';
export function astronaut(){
 const root=new THREE.Group(),suit=new THREE.MeshStandardMaterial({color:'#d9e0e5',roughness:.7}),dark=new THREE.MeshStandardMaterial({color:'#283343',roughness:.65}),visor=new THREE.MeshStandardMaterial({color:'#c79d4e',metalness:.8,roughness:.18});
 const part=(g,m,x,y,z)=>{let mesh=new THREE.Mesh(g,m);mesh.position.set(x,y,z);root.add(mesh);return mesh;};
 part(new THREE.CapsuleGeometry(.24,.42,5,12),suit,0,1.02,0);
 part(new THREE.SphereGeometry(.29,24,16),suit,0,1.62,0);
 let glass=part(new THREE.SphereGeometry(.296,32,20,Math.PI*1.15,Math.PI*.7,.6,1.65),visor,0,1.62,0);glass.scale.set(1,1,1);
 part(new THREE.BoxGeometry(.44,.55,.22),suit,0,1.13,.28);for(let sign of [-1,1]){part(new THREE.CylinderGeometry(.07,.07,.42,12),dark,sign*.14,1.14,.44);part(new THREE.CylinderGeometry(.073,.073,.035,12),visor,sign*.14,1.34,.44);}part(new THREE.CylinderGeometry(.23,.23,.065,18),dark,0,1.4,0);part(new THREE.BoxGeometry(.08,.1,.03),new THREE.MeshStandardMaterial({color:'#a74332'}),-.18,1.15,-.23);
 part(new THREE.BoxGeometry(.26,.18,.04),dark,0,1.15,-.25);
 const limbs=[];for(let sign of [-1,1]){let leg=part(new THREE.CapsuleGeometry(.105,.47,4,8),suit,sign*.14,.4,0);let boot=part(new THREE.BoxGeometry(.23,.15,.35),dark,sign*.14,.08,-.06);let arm=part(new THREE.CapsuleGeometry(.09,.42,4,8),suit,sign*.36,1.03,0);limbs.push({leg,boot,arm,sign});}
 root.userData.update=(t,moving)=>{for(let l of limbs){let stride=moving?Math.sin(t*9+l.sign*Math.PI/2)*.36:0;l.leg.rotation.x=stride;l.arm.rotation.x=-stride;l.boot.position.z=-.06+stride*.25;}};
 return root;
}
