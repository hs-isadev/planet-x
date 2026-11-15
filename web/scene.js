import {icrsDirection,installSunSky} from './sun-sky.js';
import {orbitPose,cruisePose,orbitDuration} from './camera-path.js';
import {installEarthFlight} from './earth-flight.js';
import {installContext} from './context-scene.js';
import {installNavigation} from './navigation.js';
import {flares,dust} from './activity.js';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {photosphere,halo} from './stellar.js';
const $=id=>document.getElementById(id);
export class ObservatoryScene {
 constructor(onSelect){
  this.starSize=2.5;this.makeHalo=halo;this.onSelect=onSelect;this.items=[];this.mode='solar';this.selected=null;this.showLabels=true;this.showPaths=true;this.filterRadius=5;this.filterMagnitude=12;this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  this.renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.1;$('scene').append(this.renderer.domElement);
  this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#080b10');this.camera=new THREE.PerspectiveCamera(38,1,.000001,30000);this.camera.position.set(0,2,3);this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=!this.reduced;this.controls.dampingFactor=.09;this.controls.minDistance=.000001;this.controls.maxDistance=10000;this.controls.zoomSpeed=.65;
  this.ambient=new THREE.AmbientLight(0xffffff,.13);this.scene.add(this.ambient);this.light=new THREE.PointLight(0xffffff,3,0,0);this.scene.add(this.light);
  this.content=new THREE.Group();this.scene.add(this.content);this.orbits=new THREE.Group();this.content.add(this.orbits);this.ray=new THREE.Raycaster();this.pointer=new THREE.Vector2();
  this.renderer.domElement.addEventListener('pointerdown',e=>this.down=[e.clientX,e.clientY]);this.renderer.domElement.addEventListener('pointerup',e=>{if(this.sunSky||this.surface||this.journey||this.local||!this.down||Math.hypot(e.clientX-this.down[0],e.clientY-this.down[1])>5)return;let r=this.renderer.domElement.getBoundingClientRect();this.pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);this.ray.setFromCamera(this.pointer,this.camera);let hits=this.ray.intersectObjects(this.items.filter(x=>x.model?.visible||x.mesh.visible).map(x=>x.hit),true);if(hits.length){let o=hits[0].object;while(o&&!o.userData.id)o=o.parent;if(o){this.onSelect(o.userData.id,true);return;}}const picked=this.catalogAtPointer(this.pointer);if(picked)window.dispatchEvent(new CustomEvent('catalog-context-select',{detail:picked}));});
  this.navKeys=new Set();this.activityEnabled=!this.reduced;this.activityTime=0;
  document.addEventListener('keydown',e=>{if(!e.ctrlKey&&!e.metaKey&&!/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)&&['KeyW','KeyA','KeyS','KeyD'].includes(e.code)&&!document.body.classList.contains('observing')){this.navKeys.add(e.code);if(!this.surface)e.preventDefault();}});document.addEventListener('keyup',e=>this.navKeys.delete(e.code));window.addEventListener('blur',()=>this.navKeys.clear());
  this.renderer.domElement.addEventListener('wheel',e=>{if(this.surface||this.journey)return;e.preventDefault();e.stopImmediatePropagation();if(this.sunSky)return;this.zoomBy(Math.exp(THREE.MathUtils.clamp(e.deltaY,-220,220)*.003));},{passive:false,capture:true});
  this.controls.addEventListener('start',()=>{this.stopFlight();});new ResizeObserver(()=>this.resize()).observe($('stage'));this.resize();this.animate();
 }
 resize(){let r=$('stage').getBoundingClientRect();if(!r.width||!r.height)return;this.w=r.width;this.h=r.height;this.renderer.setSize(r.width,r.height);this.camera.aspect=r.width/r.height;this.camera.fov=THREE.MathUtils.radToDeg(2*Math.atan(Math.tan(THREE.MathUtils.degToRad(19))/Math.min(1,this.camera.aspect)));if(this.camera.aspect<1&&!this.sunSky)this.camera.setViewOffset(r.width,r.height,0,r.height*.17,r.width,r.height);else this.camera.clearViewOffset();this.camera.fov/=(this.viewFill||1);this.camera.updateProjectionMatrix();}
 stopFlight(){if(this.pan){this.pan.done(false);this.pan=null;}if(this.flight?.baseFov){this.camera.fov=this.flight.baseFov;this.camera.updateProjectionMatrix();}this.renderer.domElement.style.transform='';this.renderer.domElement.style.filter='';if(this.flight?.done)this.flight.done(false);this.flight=null;}
 clear(){this.leaveSunSky();this.beaconLabel?.remove();this.beaconLabel=null;this.earthBeacon=null;this.stopFlight();this.exitLocal();this.version=(this.version||0)+1;this.items.forEach(x=>x.label.remove());this.content.traverse(o=>{o.geometry?.dispose();if(o.material)for(let m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}});this.content.clear();this.content.visible=true;this.orbits=new THREE.Group();this.content.add(this.orbits);this.items=[];}
 label(data,pos,radius,mesh){let label=document.createElement('span');label.className='object-label';label.textContent=data.name;label.setAttribute('aria-hidden','true');$('labels').append(label);this.items.push({data,pos,radius,mesh,hit:mesh,label});}
 async solar(data){
  this.clear();this.solarData=data;
  if(!data.size_layout){this.physicalSolar=data;this.orbitDays=0;this.orbitEpoch=data.date;}
  this.mode='solar';this.ambient.intensity=.16;this.light.visible=true;
  this.controls.maxDistance=200;this.controls.minDistance=.000001;
  const version=this.version,tex=new THREE.TextureLoader(),gltf=new GLTFLoader(),assets=[];
  for(const d of data.objects){
   const p=this.vector(d.xyz_au),factor=d.display_radius_factor??(d.id==='sun'?16:250),r=d.radius_km/149597870.7*factor;
   d.display_factor=factor;
   const material=d.id==='sun'?photosphere(d):new THREE.MeshStandardMaterial({color:0xdad9d4,roughness:1,metalness:0});
   const mesh=new THREE.Mesh(new THREE.SphereGeometry(r,128,80),material);
   mesh.position.copy(p);mesh.userData.id=d.id;this.content.add(mesh);this.label(d,p,r,mesh);
   if(d.id==='sun')mesh.add(flares(r));if(d.id==='mars')mesh.add(dust(r));
   if(d.id==='sun'){const glow=halo(d);glow.material.opacity=.15;glow.position.copy(p);glow.scale.setScalar(r*2.8);this.content.add(glow);}
   if(d.texture)assets.push(tex.loadAsync(d.texture).then(t=>{
    if(version!==this.version){t.dispose();return;}
    t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(8,this.renderer.capabilities.getMaxAnisotropy());
    material.map=t;material.color.set(0xffffff);material.needsUpdate=true;
   }).catch(()=>{d.asset_error='Published appearance map unavailable. No replacement detail invented.';}));
   if(d.model)assets.push(gltf.loadAsync(d.model).then(result=>{
    if(version!==this.version){result.scene.traverse(o=>{o.geometry?.dispose();for(const m of (Array.isArray(o.material)?o.material:[o.material])){m?.map?.dispose();m?.dispose();}});return;}
    const model=result.scene,box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3()),group=new THREE.Group();
    model.position.sub(center);group.add(model);group.scale.setScalar((d.id==='saturn'?r*4.7:r*2)/Math.max(size.x,size.y,size.z));
    group.position.copy(p);group.userData.id=d.id;group.rotation.y=mesh.rotation.y;this.content.add(group);mesh.visible=false;
    const item=this.items.find(i=>i.data===d);if(item){item.hit=group;item.model=group;}
   }).catch(()=>{d.asset_error='NASA model unavailable. Neutral geometry shown.';}));
   if(d.orbit_au){const geometry=new THREE.BufferGeometry().setFromPoints(d.orbit_au.map(a=>this.vector(a))),orbit=new THREE.Line(geometry,new THREE.LineBasicMaterial({color:0x6b7988,transparent:true,opacity:.4}));orbit.userData.body=d.id;this.orbits.add(orbit);}
  }
  this.orbits.visible=this.showPaths;
  this.assetsReady=Promise.allSettled(assets);await this.assetsReady;
 }
 stars(data,fit=true){this.clear();this.starsData=data;this.mode='stars';this.ambient.intensity=0;this.light.visible=false;this.controls.maxDistance=10000;this.controls.minDistance=.0000001;let sun={id:'origin',name:'Sun',kind:'G-type star',distance_pc:0,teff_gspphot:5772};for(const star of [sun,...data.objects])this.addStar(star);if(data.scope==='field')this.filterRadius=Math.max(...data.objects.map(d=>d.distance_pc),5);else this.filterRadius=5;this.applyFilter();if(fit)this.overview();}
 addStar(star){
  const position=this.vector(star.xyz_pc||[0,0,0]);
  const mesh=halo(star);mesh.position.copy(position);mesh.userData.id=star.id;
  this.content.add(mesh);this.label(star,position,0,mesh);
  return this.items.at(-1);
 }
 vector(a){return new THREE.Vector3(a[0],a[2],-a[1]);}
 passes(d){return d.id==='origin'||(d.distance_pc<=this.filterRadius&&(d.phot_g_mean_mag==null||d.phot_g_mean_mag<=this.filterMagnitude));}
 applyFilter(){
  const visibleStars=new Set();
  for(const item of this.items){
   const visible=this.mode!=='stars'||this.passes(item.data)||item.data.id===this.selected;
   item.mesh.visible=visible&&!item.model;if(item.model)item.model.visible=visible;
   if(visible&&this.mode==='stars')visibleStars.add(item.data.id);
  }
  this.visibleCatalogStars=visibleStars;
  return this.items.filter(item=>visibleStars.has(item.data.id)&&item.data.id!=='origin').map(item=>item.data);
 }
 select(id,focus=false){if(this.local&&this.local.item?.data.id!==id)this.exitLocal();let item=this.items.find(x=>x.data.id===id);if(!item)return;this.selected=id;this.items.forEach(x=>x.label.classList.toggle('selected',x===item));this.applyFilter();if(focus)this.focus();}
 focus(){this.exitLocal();let i=this.items.find(x=>x.data.id===this.selected);if(!i)return;let offset=this.camera.position.clone().sub(this.controls.target);this.fly(i.pos,i.pos.clone().add(offset),250);}
 approach(lit=false){let i=this.items.find(x=>x.data.id===this.selected);if(!i)return;if(this.mode==='stars'){if(i.data.teff_gspphot>=2300||i.data.id==='origin')this.stellarCloseup(i);else window.dispatchEvent(new CustomEvent('scene-error',{detail:'No usable stellar temperature is available. A detailed surface would be invented; explore the catalog position and SPHEREx observations instead.'}));return;}let v=lit&&true?i.pos.clone().negate().normalize():this.camera.position.clone().sub(this.controls.target).normalize();if(!v.length())v.set(0,.3,1).normalize();let distance=i.radius*(i.data.id==='saturn'?8.5:4.4);if(innerWidth<=650)distance*=1.35;this.fly(i.pos,i.pos.clone().addScaledVector(v,distance));}
 stellarCloseup(i){this.stopFlight();this.exitLocal();this.local={camera:this.camera.position.clone(),target:this.controls.target.clone(),min:this.controls.minDistance,max:this.controls.maxDistance,near:this.camera.near,far:this.camera.far};this.content.visible=false;this.localGroup=new THREE.Group();let star=new THREE.Mesh(new THREE.SphereGeometry(1,96,64),photosphere(i.data));this.localGroup.add(star);let glow=halo(i.data);glow.material.opacity=i.data.teff_gspphot>0&&i.data.teff_gspphot<2300?0:.15;glow.scale.setScalar(2.8);this.localGroup.add(glow);this.scene.add(this.localGroup);this.camera.near=.02;this.camera.far=100;this.camera.updateProjectionMatrix();this.camera.position.set(0,.15,4.4);this.controls.target.set(0,0,0);this.controls.minDistance=1.03;this.controls.maxDistance=25;this.controls.update();$('scale').textContent='Modeled photosphere · normalized size';document.body.classList.add('stellar-closeup');}
 exitLocal(){if(this.local){this.scene.remove(this.localGroup);this.localGroup?.traverse(o=>{o.geometry?.dispose();o.material?.map?.dispose();o.material?.dispose();});this.localGroup=null;this.camera.position.copy(this.local.camera);this.controls.target.copy(this.local.target);this.controls.minDistance=this.local.min;this.controls.maxDistance=this.local.max;this.camera.near=this.local.near;this.camera.far=this.local.far;this.camera.updateProjectionMatrix();this.local=null;this.content.visible=true;this.controls.enabled=true;this.controls.update();document.body.classList.remove('stellar-closeup');}this.entryPending=false;}
 overview(){this.exitLocal();let extent=this.mode==='solar'?33:Math.max(2,...this.items.filter(i=>i.mesh.visible).map(x=>x.pos.length()));return this.fly(new THREE.Vector3(),new THREE.Vector3(extent*.65,extent*.8,extent*1.35));}
 fly(target,pos,duration=1800){
  this.stopFlight();
  const travelTime=this.journey?duration:orbitDuration(this.camera.position,this.controls.target,pos,target,duration);
  return new Promise(done=>{this.flight={start:performance.now(),duration:this.reduced?Math.min(travelTime,1200):travelTime,baseFov:this.camera.fov,from:this.camera.position.clone(),fromTarget:this.controls.target.clone(),pos:pos.clone(),target:target.clone(),done};});
 }
 async trace(context,solar,progress){let item=this.items.find(i=>i.data.id===this.selected);if(!item)return;this.journey=true;this.controls.enabled=false;this.traceReturn={mode:this.mode,data:this.mode==='solar'?this.solarData:this.starsData,selected:this.selected};this.exitLocal();this.controls.enabled=false;
  if(this.mode==='stars'&&(item.data.teff_gspphot>=2300||item.data.id==='origin')){this.stellarCloseup(item);this.controls.enabled=false;progress('Above the modeled photosphere','Individual stellar features are unresolved. Starting the accelerated journey.');await new Promise(r=>setTimeout(r,this.reduced?1:1600));if(!this.journey)return;this.exitLocal();this.controls.enabled=false;}
  let earth=this.mode==='solar'?this.items.find(i=>i.data.id==='earth').pos.clone():new THREE.Vector3();let direction=item.pos.clone().sub(earth).normalize();let start=item.pos.clone().addScaledVector(direction.clone().negate(),Math.max(item.radius*1.03,.00000001));this.camera.position.copy(start);this.controls.target.copy(earth);this.controls.update();progress('Trace back to Earth',this.mode==='stars'?'Catalog distances in parsecs · accelerated, frozen epoch':'Computed ephemeris in AU · body radii enlarged, frozen epoch');
  let end=earth.clone().addScaledVector(direction,this.mode==='solar'?this.items.find(i=>i.data.id==='earth').radius*1.05:.003);
  if(!await this.fly(earth,end,6500,true)||!this.journey)return;
  if(this.mode==='stars'){direction=this.vector(context.direction_ecliptic).normalize();progress('Entering the Solar System','Changing from parsecs to AU. This is a separate spatial scale.');await this.solar(solar);this.controls.enabled=false;let e=this.items.find(i=>i.data.id==='earth');earth=e.pos.clone();this.camera.position.copy(earth).addScaledVector(direction,.2);this.controls.target.copy(earth);await this.fly(earth,earth.clone().addScaledVector(direction,e.radius*1.05),2200,true);}
  if(this.journey)progress('Looking back from Earth',context.constellation+' · the source direction in our sky');return !!this.journey;
 }
 async returnFromTrace(){this.journey=false;this.stopFlight();let r=this.traceReturn;this.traceReturn=null;if(r){if(r.mode==='solar')await this.solar(r.data);else this.stars(r.data);this.selected=r.selected;this.select(r.selected);this.approach();}this.controls.enabled=true;}
 skyTargetDirection(){
  const target=this.skyTarget?.point;
  if(!target)return null;
  if(this.mode!=='stars')return icrsDirection(target.ra,target.dec);
  const a=THREE.MathUtils.degToRad(target.ra),d=THREE.MathUtils.degToRad(target.dec);
  return this.vector([Math.cos(d)*Math.cos(a),Math.cos(d)*Math.sin(a),Math.sin(d)]);
 }
 skyTargetItem(){
  const source=this.skyTarget?.source;
  if(!source?.id||this.mode!==(source.solarBody?'solar':'stars'))return null;
  return this.items.find(item=>item.data.id===source.id);
 }
 centerSkyTarget(){
  this.leaveSunSky();
  if(this.journey||this.surface)return;
  if(this.mode==='sizes')return;
  this.exitLocal();
  const item=this.skyTargetItem();
  if(item){this.onSelect(item.data.id,true);return;}
  const direction=this.skyTarget?.source?null:this.skyTargetDirection();
  if(direction)this.turnLeftTo(direction,650,'');
 }
 renderSkyTarget(){
  const marker=$('sky-target-marker');
  if(!marker)return;
  if(this.journey||this.surface||this.sunSky||this.mode==='sizes'){marker.hidden=true;return;}
  const item=this.skyTargetItem();
  let point;
  if(this.local){
   if(!item||item!==this.local.item||!this.localGroup){marker.hidden=true;return;}
   point=this.localGroup.getWorldPosition(new THREE.Vector3());
  }else if(item){
   point=item.pos.clone();
  }else if(!this.skyTarget?.source){
   const direction=this.skyTargetDirection();
   if(direction)point=this.camera.position.clone().addScaledVector(direction,Math.min(this.camera.far*.5,100));
  }
  if(!point){marker.hidden=true;return;}
  const p=point.project(this.camera);
  marker.hidden=p.z<=-1||p.z>=1||Math.abs(p.x)>.97||Math.abs(p.y)>.96;
  if(!marker.hidden)marker.style.transform='translate('+((p.x*.5+.5)*this.w)+'px,'+((-p.y*.5+.5)*this.h)+'px)';
 }
 theme(light){this.lightTheme=light;this.scene.background.set('#080b10');}
 animate(){requestAnimationFrame(()=>this.animate());let now=performance.now(),dt=Math.min(.05,(now-(this.lastTick||now))/1000);this.lastTick=now;if(this.sunSky){this.renderSunSky(dt);return;}if(this.activityEnabled&&!this.loading&&!this.journey)this.activityTime+=dt;this.navigationTick(dt);if(this.surface){const marker=$('sky-target-marker');if(marker)marker.hidden=true;this.surface.update();return;}const panning=!!this.pan,flying=!!this.flight;if(this.pan){const p=this.pan,k=Math.min(1,(now-p.start)/p.duration),t=k*k*k*(k*(k*6-15)+10);this.camera.quaternion.slerpQuaternions(p.fromQuaternion,p.toQuaternion,t);const direction=new THREE.Vector3(0,0,-1).applyQuaternion(this.camera.quaternion);this.controls.target.copy(this.camera.position).addScaledVector(direction,p.distance);if(k===1){this.pan=null;p.done(true);}}if(this.flight){const f=this.flight;if(f.continuousEarth)f.elapsed=(f.elapsed||0)+Math.min(48,Math.max(0,now-(f.lastFrame||f.start)));f.lastFrame=now;const k=Math.min(1,(f.continuousEarth?f.elapsed:now-f.start)/f.duration),pose=f.sample?f.sample(k):f.heading?cruisePose(f.from,f.pos,f.heading,f.clearance,k):orbitPose(f.from,f.fromTarget,f.pos,f.target,k);this.camera.position.copy(pose.position);this.controls.target.copy(pose.target);this.camera.lookAt(pose.target);if(k===1){this.flight=null;f.done(true);}}if(!panning&&!flying)this.controls.update();if(this.localGroup)this.localGroup.traverse(o=>{if(o.material?.uniforms?.clock)o.material.uniforms.clock.value=this.activityTime;});let occupied=[];
  if(this.mode==='solar'&&!this.loading&&!this.journey&&!this.surface&&!this.flight&&!this.pan&&this.activityEnabled&&(this.orbitRate??1)>0){this.orbitDays=(this.orbitDays||0)+dt*(this.orbitRate??1);for(let i of this.items){let curve=i.data.orbit_au,period=i.data.orbital_period_days;if(!curve||!period)continue;let t=(128+this.orbitDays/period*256)%256,k=Math.floor(t),f=t-k,a=this.vector(curve[k]),b=this.vector(curve[(k+1)%256]),next=a.lerp(b,f),delta=next.clone().sub(i.pos),follow=i.data.id===this.selected&&this.controls.target.distanceTo(i.pos)<i.radius*.1;i.pos.copy(next);i.mesh.position.copy(next);if(i.model)i.model.position.copy(next);if(follow&&!this.flight){this.controls.target.add(delta);this.camera.position.add(delta);}}let el=document.getElementById('simulation-time');if(el)el.textContent='COMPUTED orbit time +'+this.orbitDays.toFixed(1)+' d · '+(this.orbitRate??1)+' d/s';if(this.orbitEpoch&&document.activeElement.id!=='date')document.getElementById('date').value=new Date(Date.parse(this.orbitEpoch)+this.orbitDays*86400000).toISOString().slice(0,10);}
   // Catalog sky positions and visibility are updated by addCatalogSky's callback.
   this.scene.traverse(o=>{o.userData.update?.(this.activityTime);});if(this.activityEnabled&&!this.loading&&this.mode==='solar'&&!this.journey){
    // Independent, deliberately accelerated display spin; these are not orbital periods.
    const spins={sun:.04,mercury:.055,venus:-.035,earth:.19,mars:.18,jupiter:.29,saturn:.27,uranus:-.21,neptune:.23};
    for(const i of this.items){if(spins[i.data.id]!=null)(i.model||i.mesh).rotation.y+=dt*spins[i.data.id];}
   }
  if(!this.local){this.camera.near=Math.max(1e-10,Math.min(.01,this.camera.position.distanceTo(this.controls.target)*.0005));this.camera.updateProjectionMatrix();}this.camera.updateMatrixWorld();this.renderSkyTarget();
  for(let i of [...this.items].sort((a,b)=>(b.data.id===this.selected)-(a.data.id===this.selected))){if(i.mesh.material?.uniforms?.clock)i.mesh.material.uniforms.clock.value=this.activityTime;let p=i.pos.clone().project(this.camera),depth=i.pos.distanceTo(this.camera.position),pixelRadius=i.radius/Math.max(depth,1e-12)*this.h/(2*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2)));if(this.mode==='stars'){let mag=i.data.phot_g_mean_mag??8,px=i.data.id===this.selected?8:THREE.MathUtils.clamp(6-mag*.3,2,5);i.mesh.scale.setScalar(px*(this.starSize||1)*depth*2*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))/this.h);}
   let selected=i.data.id===this.selected,x=(p.x*.5+.5)*this.w,y=(-p.y*.5+.5)*this.h,width=i.label.offsetWidth||110;let visible=this.showLabels&&selected&&!this.local&&!this.journey&&p.z>-1&&p.z<1&&x>8&&x<this.w-8&&y>4&&y<this.h-10;i.label.hidden=!visible;if(visible)i.label.style.transform='translate('+Math.min(this.w-width-8,Math.max(8,x+Math.max(9,pixelRadius*.65)))+'px,'+Math.max(8,y-15)+'px)';
  }
  if(this.beaconLabel&&this.earthBeacon){let p=this.camera.position.clone().addScaledVector(this.earthBeacon,10).project(this.camera);this.beaconLabel.hidden=!this.journey||p.z<0||p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1;this.beaconLabel.style.transform='translate('+((p.x*.5+.5)*this.w)+'px,'+((-p.y*.5+.5)*this.h)+'px)';}this.renderer.render(this.scene,this.camera);let d=this.controls.target.distanceTo(this.camera.position),width=2*d*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))*this.camera.aspect,amount=width*100/(this.w||1);$('scale').textContent=this.local?'Modeled photosphere · normalized size':amount.toFixed(amount<.1?5:amount<10?2:0)+(this.mode==='sizes'?' R☉':this.mode==='solar'?' AU':' pc')+' / 100 px';
  let selected=this.items.find(i=>i.data.id===this.selected);if(!this.flight&&!this.journey&&!this.local&&selected&&this.mode==='solar'&&this.camera.position.distanceTo(selected.pos)<selected.radius*1.025){let dir=this.camera.position.clone().sub(selected.pos).normalize();if(!dir.lengthSq())dir.set(0,0,1);this.camera.position.copy(selected.pos).addScaledVector(dir,selected.radius*1.025);}
 }
}

installNavigation(ObservatoryScene);
installContext(ObservatoryScene);

installSunSky(ObservatoryScene);

installEarthFlight(ObservatoryScene);
