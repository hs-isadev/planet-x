import * as THREE from 'three';

export function addPlanets(view,item,planets){
 if(!view.localGroup||view.local?.item!==item)return;
 view.local.planets=planets;
 const old=view.localGroup.getObjectByName('companions');
 if(old){view.localGroup.remove(old);old.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});}
 const group=new THREE.Group();group.name='companions';view.localGroup.add(group);
 const list=document.getElementById('planet-list');list?.replaceChildren();
 let extent=1;
 planets.forEach((p,index)=>{
  const starRadius=p.star_radius_solar||1,a=p.semimajor_au/(starRadius*.00465047);extent=Math.max(extent,a);
  const curve=Array.from({length:129},(_,j)=>new THREE.Vector3(a*Math.cos(j/128*Math.PI*2),0,a*Math.sin(j/128*Math.PI*2)));
  const orbit=new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve),new THREE.LineBasicMaterial({color:0xaab5c3,transparent:true,opacity:.48}));group.add(orbit);
  const radius=THREE.MathUtils.clamp((p.radius_earth||1)*.0091577/starRadius,.045,.3);
  const planet=new THREE.Mesh(new THREE.SphereGeometry(radius,32,20),new THREE.MeshStandardMaterial({color:0xb5aba1,roughness:1,emissive:0x181a20}));
  planet.name=p.name;planet.userData.displayRadius=radius;group.add(planet);
  planet.userData.update=time=>{
   const phase=index*2.399+time/Math.max(p.period_days,.1)*Math.PI*2;
   const previous=planet.position.clone();planet.position.set(a*Math.cos(phase),0,a*Math.sin(phase));if(view.local?.followPlanet===planet&&!view.journey){const delta=planet.position.clone().sub(previous);view.camera.position.add(delta);view.controls.target.add(delta);const flight=view.flight;if(flight&&!flight.heading){flight.from.add(delta);flight.fromTarget.add(delta);flight.pos.add(delta);flight.target.add(delta);}}
   // Keep the intentionally enlarged planet at least four pixels across in a
   // system overview, without changing its orbital distance or period.
   const distance=view.camera.position.distanceTo(planet.position),minRadius=distance*2*Math.tan(THREE.MathUtils.degToRad(view.camera.fov/2))*2/Math.max(view.h||800,1);
   planet.scale.setScalar(Math.max(1,minRadius/radius));
   planet.rotation.y=time*.1;
  };
  planet.userData.update(view.activityTime||0);
  if(list){const button=document.createElement('button');button.className='quiet';button.textContent=p.name;button.title='Catalog orbit: '+p.semimajor_au+' AU · '+p.period_days+' days. Planet size enlarged.';button.onclick=()=>view.planetCloseup(planet);list.append(button);}
 });
 group.add(new THREE.PointLight(0xfff4e8,3,0,0));
 view.local.systemExtent=extent;
 view.controls.maxDistance=Math.max(view.controls.maxDistance,extent*14);
 view.camera.far=Math.max(view.camera.far,extent*40);view.camera.updateProjectionMatrix();
 const button=document.getElementById('stellar-system');button.hidden=false;button.disabled=!planets.length;button.textContent=planets.length?'View all '+planets.length+' planet orbits':'No catalogued planet orbits';
 const label=document.getElementById('stellar-provenance');
 label.textContent+=planets.length?' '+planets.length+' catalogued planets. Circular orbit planes, phases and appearances are illustrative; planet sizes are enlarged for visibility. '+(planets.some(p=>!p.star_radius_solar)?'Host radius is unavailable; stellar size normalization is approximate.':''):' No measured planetary orbits for this target are installed in this catalog. This does not establish that it has no planets.';
}

export async function addMoons(view,data,version){
 const response=await fetch('/assets/moons.json');if(!response.ok)return;
 const catalog=await response.json();if(view.version!==version||view.mode!=='solar'||data.size_layout)return;
 for(const [index,d] of catalog.rows.entries()){
  const parent=view.items.find(i=>i.data.id===d.parent);if(!parent)continue;
  const a=parent.radius*(2.9+d.semimajor_km/parent.data.radius_km*.12);
  const radius=parent.radius*THREE.MathUtils.clamp(d.radius_km/parent.data.radius_km,.045,.28);
  const mesh=new THREE.Mesh(new THREE.SphereGeometry(radius,24,16),new THREE.MeshStandardMaterial({color:d.id==='titan'?0xc9aa7c:0xb3b0a9,roughness:1,emissive:0x080808}));
  const row={...d,kind:'Moon of '+parent.data.name,orbital_period_days:d.period_days,
   distance_sun_au:parent.data.distance_sun_au,description:catalog.note,texture_note:catalog.note,
   display_factor:radius*149597870.7/d.radius_km,provenance:'catalog / computed',ra:parent.data.ra,dec:parent.data.dec};
  const pos=parent.pos.clone().add(new THREE.Vector3(a,0,0));mesh.position.copy(pos);mesh.userData.id=d.id;
  view.content.add(mesh);view.label(row,pos,radius,mesh);const item=view.items.at(-1);
  // Keep selectors and the inspector on the same object set as the rendered scene.
  if(!data.objects.some(o=>o.id===d.id))data.objects.push(row);
  const orbit=new THREE.Line(new THREE.BufferGeometry().setFromPoints(Array.from({length:97},(_,j)=>new THREE.Vector3(a*Math.cos(j/96*Math.PI*2),0,a*Math.sin(j/96*Math.PI*2)))),new THREE.LineBasicMaterial({color:0x8a8f99,transparent:true,opacity:.3}));
  orbit.userData.body=d.parent;view.orbits.add(orbit);
  mesh.userData.update=time=>{
   const angle=index*2.399+(d.retrograde?-1:1)*time/Math.max(d.period_days,.1)*Math.PI*2;
   const next=parent.pos.clone().add(new THREE.Vector3(a*Math.cos(angle),0,a*Math.sin(angle)));
   const delta=next.clone().sub(item.pos),follow=view.selected===d.id&&view.controls.target.distanceTo(item.pos)<radius*.5;
   item.pos.copy(next);mesh.position.copy(next);orbit.position.copy(parent.pos);
   if(follow&&!view.flight&&!view.journey){view.controls.target.add(delta);view.camera.position.add(delta);}
   const distance=view.camera.position.distanceTo(parent.pos),visible=view.selected===d.id||distance<parent.radius*90;
   mesh.visible=visible;orbit.visible=view.showPaths&&visible;
  };
 }
}
