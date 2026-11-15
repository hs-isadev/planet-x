import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const $ = id => document.getElementById(id);
const WORLD_LIMIT = {stars:200, galaxies:3500};
const toward = (ra, dec) => {
 const a=THREE.MathUtils.degToRad(ra), d=THREE.MathUtils.degToRad(dec);
 return new THREE.Vector3(Math.cos(a)*Math.cos(d),Math.sin(d),-Math.sin(a)*Math.cos(d));
};

export function installCatalogAtlas(openObservation) {
 const dialog=$('catalog-atlas'), host=$('atlas-stage'), control=$('atlas-kind'), epoch=$('atlas-year');
 const status=$('physical-atlas-status'), pickNote=$('atlas-pick');
 const datasets=new Map(), scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(46,1,.02,20000);
 scene.background=new THREE.Color('#090f19');
 let renderer, controls, points, line, marker, dataset, selected=-1, loadVersion=0, down;
 const ray=new THREE.Raycaster(), pointer=new THREE.Vector2();

 const draw=()=>{if(dialog.open&&renderer)renderer.render(scene,camera);};
 function size() {
  if(!renderer||!host.clientWidth||!host.clientHeight)return;
  renderer.setSize(host.clientWidth,host.clientHeight,false);
  camera.aspect=host.clientWidth/host.clientHeight;
  camera.updateProjectionMatrix();
  draw();
 }
 function overview() {
  const limit=WORLD_LIMIT[control.value];
  camera.position.set(limit*.95,limit*.82,limit*1.3);
  controls.target.set(0,0,0);
  controls.update();
  draw();
 }
 function position(record, year) {
  const p=toward(record.ra,record.dec).multiplyScalar(record.distance);
  if(record.velocity&&record.epoch!=null) {
   const [x,y,z]=record.velocity;
   p.addScaledVector(new THREE.Vector3(x,z,-y),year-record.epoch);
  }
  return p;
 }
 function skyOf(record,year) {
  if(!record.velocity)return {ra:record.ra,dec:record.dec};
  const p=position(record,year), r=p.length();
  return {ra:THREE.MathUtils.euclideanModulo(THREE.MathUtils.radToDeg(Math.atan2(-p.z,p.x)),360),
          dec:THREE.MathUtils.radToDeg(Math.asin(THREE.MathUtils.clamp(p.y/r,-1,1)))};
 }
 function updateSelection() {
  const record=dataset?.records[selected], has=Boolean(record);
  $('atlas-focus').disabled=$('atlas-observe').disabled=$('atlas-export').disabled=!has;
  $('atlas-interval').disabled=!has||record.distanceError==null;
  marker.visible=line.visible=false;
  if(!has){pickNote.textContent='Select a point in the atlas to inspect its catalog record.';return;}
  const year=+epoch.value, p=position(record,year);
  const label=record.name||dataset.release+' '+record.id;
  const error=record.distanceError==null?'':' ± '+record.distanceError.toPrecision(3);
  const details=[label, p.length().toFixed(2)+error+' '+dataset.unit];
  if(dataset.kind==='galaxies')details.push('z '+record.redshift.toFixed(5), record.lookbackGyr.toFixed(2)+' Gyr lookback');
  else details.push(record.velocity?'3D velocity projected to '+year:'Fixed at catalog epoch; no complete 3D velocity');
  pickNote.textContent=details.join(' · ');
  marker.position.copy(p);
  marker.visible=true;
  if($('atlas-interval').checked && record.distanceError!=null){
   const direction=p.clone().normalize().multiplyScalar(record.distanceError);
   line.geometry.setFromPoints([p.clone().sub(direction),p.clone().add(direction)]);
   line.geometry.computeBoundingSphere();
   line.visible=true;
  }
 }
 function positions() {
  if(!points)return;
  const attr=points.geometry.getAttribute('position');
  const year=+epoch.value;
  dataset.records.forEach((record,i)=>{
   const p=position(record,year);
   attr.setXYZ(i,p.x,p.y,p.z);
  });
  attr.needsUpdate=true;
  points.geometry.computeBoundingSphere();
  updateSelection();
  draw();
 }
 async function load() {
  const kind=control.value, version=++loadVersion;
  $('atlas-year-control').hidden=kind!=='stars';
  status.textContent='Loading the '+(kind==='stars'?'Gaia':'DESI')+' catalog sample…';
  try {
   if(!datasets.has(kind)){
    const response=await fetch('/assets/atlas-'+kind+'.json');
    if(!response.ok)throw Error('The catalog sample could not be loaded.');
    const payload=await response.json();
    payload.records=payload.rows.map(row=>Object.fromEntries(payload.columns.map((key,i)=>[key,row[i]])));
    datasets.set(kind,payload);
   }
   if(version!==loadVersion||!dialog.open)return;
   dataset=datasets.get(kind);
   if(points){scene.remove(points);points.geometry.dispose();points.material.dispose();}
   const geom=new THREE.BufferGeometry(), color=new Float32Array(dataset.records.length*3);
   for(const [i,record] of dataset.records.entries()){
    const shade=new THREE.Color().setHSL(kind==='stars'?.62-.21*THREE.MathUtils.clamp(((record.color??1)+.4)/3.8,0,1):.76-.50*record.redshift,.70,.67);
    shade.toArray(color,i*3);
   }
   geom.setAttribute('position',new THREE.BufferAttribute(new Float32Array(color.length),3));
   geom.setAttribute('color',new THREE.BufferAttribute(color,3));
   points=new THREE.Points(geom,new THREE.PointsMaterial({size:4,sizeAttenuation:false,vertexColors:true,transparent:true,opacity:.86}));
   scene.add(points);
   selected=-1;
   positions();
   overview();
   status.textContent=dataset.records.length.toLocaleString()+' '+dataset.release+' catalog entries · '+dataset.distanceKind+' ('+dataset.unit+'). '
    +(kind==='stars'?'The slider projects only stars with Gaia radial velocities.':'The map shows the DESI survey footprint and uses Planck18 cosmology.');
  }catch(error){if(version===loadVersion)status.textContent=error.message;}
 }
 function setup() {
  renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,1.6));
  const canvas=renderer.domElement;
  host.append(canvas);
  controls=new OrbitControls(camera,canvas);
  controls.addEventListener('change',draw);
  controls.minDistance=1;
  controls.maxDistance=12000;
  marker=new THREE.Points(
   new THREE.BufferGeometry().setFromPoints([new THREE.Vector3()]),
   new THREE.PointsMaterial({color:0x7af7e1,size:9,sizeAttenuation:false})
  );
  line=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x7af7e1}));
  scene.add(marker,line);
  marker.visible=line.visible=false;
  new ResizeObserver(size).observe(host);
  canvas.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];});
  canvas.addEventListener('pointerup',e=>{
   if(!points||!down||e.button!==0||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
   const r=canvas.getBoundingClientRect();
   pointer.set((e.clientX-r.left)/r.width*2-1,1-(e.clientY-r.top)/r.height*2);
   ray.setFromCamera(pointer,camera);
   ray.params.Points.threshold=camera.position.distanceTo(controls.target)*.008;
   const hits=ray.intersectObject(points);
   if(hits.length){
    hits.sort((a,b)=>a.distanceToRay-b.distanceToRay);
    selected=hits[0].index;
    updateSelection();
    draw();
   }
  });
 }
 $('physical-atlas-open').onclick=()=>{
  dialog.showModal();
  try{if(!renderer)setup();size();load();}
  catch(error){status.textContent='3D atlas unavailable: '+error.message;}
 };
 $('atlas-close').onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>loadVersion++);
 control.onchange=load;
 epoch.oninput=()=>{$('atlas-year-display').textContent=epoch.value;positions();};
 $('atlas-reset').onclick=()=>{if(controls)overview();};
 $('atlas-interval').onchange=()=>{updateSelection();draw();};
 $('atlas-focus').onclick=()=>{
  if(!dataset?.records[selected])return;
  const p=marker.position;
  const offset=camera.position.clone().sub(controls.target).setLength(WORLD_LIMIT[control.value]*.16);
  controls.target.copy(p);
  camera.position.copy(p).add(offset);
  controls.update();
 };
 $('atlas-observe').onclick=()=>{
  const record=dataset?.records[selected];
  if(!record)return;
  // Use the current observation epoch for an archive search, independent of the historical preview slider.
  const year=2016+(Date.now()-Date.UTC(2016,0,1))/(365.25*86400000);
  const point=skyOf(record,year);
  dialog.close();
  openObservation(point,record.name||dataset.release+' '+record.id,record.redshift);
 };
 $('atlas-export').onclick=()=>{
  const record=dataset?.records[selected];
  if(!record)return;
  const body={source:dataset.source,source_url:dataset.sourceUrl,distance_unit:dataset.unit,query:dataset.query,record};
  if(dataset.kind==='stars')body.projected={year:+epoch.value,...skyOf(record,+epoch.value)};
  const url=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='catalog-'+record.id+'.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
}
