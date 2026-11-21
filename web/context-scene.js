import {stellarProfileGLSL} from './star-profile.js';
import * as THREE from 'three';
import {corona} from './plasma.js';
import {addMoons,addPlanets} from './companions.js?v=gaia-host';
import {travelDust} from './travel-dust.js';
const $=id=>document.getElementById(id);
function starProfile() {
 const width=64,pixels=new Uint8Array(width*width*4);
 for(let y=0;y<width;y++)for(let x=0;x<width;x++){
  const r=Math.hypot(2*(x+.5)/width-1,2*(y+.5)/width-1);
  const edge=THREE.MathUtils.clamp((1-r)/.22,0,1);
  const alpha=edge*(.82*Math.exp(-14*r*r)+.22*Math.exp(-4.4*r*r));
  const i=4*(y*width+x);
  pixels[i]=pixels[i+1]=pixels[i+2]=255;
  pixels[i+3]=Math.round(255*Math.min(1,alpha));
 }
 const texture=new THREE.DataTexture(pixels,width,width,THREE.RGBAFormat);
 texture.minFilter=texture.magFilter=THREE.LinearFilter;
 texture.needsUpdate=true;
 return texture;
}

export function installContext(C){
 const solar=C.prototype.solar,close=C.prototype.stellarCloseup,exit=C.prototype.exitLocal,stars=C.prototype.stars;
 C.prototype.solar=async function(data){
  data.objects=data.objects.filter(d=>!d.parent);
  const assets=solar.call(this,data),version=this.version;
  this.camera.far=100000;this.camera.updateProjectionMatrix();
  const sun=this.items.find(item=>item.data.id==='sun');
  if(sun)sun.mesh.add(corona(sun.radius));
  this.installTravelDust();this.loadContextSky();
  const moons=addMoons(this,data,version).catch(error=>{
   if(this.version===version)window.dispatchEvent(new CustomEvent('scene-error',{detail:'Moon catalog unavailable: '+error.message}));
  });
  await Promise.all([assets,moons]);
 };
 C.prototype.stars=function(...args){stars.apply(this,args);this.installTravelDust();this.loadContextSky();};
 C.prototype.installTravelDust=function(){if(this.dustUpdate)return;this.dustUpdate=travelDust(this);const tick=new THREE.Group();tick.userData.update=()=>this.dustUpdate();this.scene.add(tick);};
 C.prototype.loadContextSky=function(){
  if(!this.contextCatalogReady)this.contextCatalogReady=fetch('/api/context-sky').then(response=>{
   if(!response.ok)throw Error('Catalog backdrop unavailable');
   return response.json();
  }).then(data=>{this.addCatalogSky(data);return data;}).catch(()=>{
   this.contextCatalogReady=null;
   return null;
  });
  return this.contextCatalogReady;
 };
 C.prototype.addCatalogSky=function(data){
  if(this.sky)return;
  // Limit angular density across the catalog. Keep real rows with valid distances.
  const counts=new Map(), entries=[];
  const sorted=data.objects.filter(source=>!source.expanded_catalog).sort((a,b)=>a.distance_pc-b.distance_pc||a.id.localeCompare(b.id));
  for(const source of sorted){
   if(!source.xyz_pc?.every(Number.isFinite)||!Number.isFinite(source.ra)||!Number.isFinite(source.dec))continue;
   const cell=Math.floor(source.ra/12)+':'+Math.floor((source.dec+90)/12);
   const count=counts.get(cell)||0;
   if(count>=4)continue;
   counts.set(cell,count+1);
   entries.push(source);
   if(entries.length>=1024)break;
  }
  entries.push(...data.objects.filter(source=>source.expanded_catalog&&source.xyz_pc?.every(Number.isFinite)));
  this.sky=new THREE.Group();
  this.sky.userData.catalog=true;
  this.sky.userData.sourceCount=data.objects.length;
  this.scene.add(this.sky);
  const directions=entries.map(source=>this.vector(source.xyz_pc));
  const positions=new Float32Array(entries.length*3), colors=new Float32Array(entries.length*3), flux=new Float32Array(entries.length);
  // Absolute magnitude from the catalog's apparent G magnitude and distance, so the apparent brightness can be
  // recomputed from wherever the camera is (Sun or another star).
  const absolute=entries.map(source=>{const m=Number.isFinite(source.phot_g_mean_mag)?source.phot_g_mean_mag:(source.v_mag??9),d=Math.max(source.distance_pc||10,.01);return m-5*Math.log10(d/10);});
  entries.forEach((source,index)=>starColor(source.teff_gspphot).toArray(colors,index*3));
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  geometry.setAttribute('flux',new THREE.BufferAttribute(flux,1));
  geometry.boundingSphere=new THREE.Sphere(new THREE.Vector3(),3001);
  const material=starMaterial();
  const points=new THREE.Points(geometry,material);
  points.userData.catalogEntries=entries;
  this.sky.add(points);
  addDeepSky(this);
  const raw=new THREE.Vector3(), lastOrigin=new THREE.Vector3(Infinity,Infinity,Infinity);
  let lastMode,lastLocal,lastCatalogStars;
  const epsilon=THREE.MathUtils.degToRad(23.439291111);
  const sin=Math.sin(epsilon),cos=Math.cos(epsilon);
  this.sky.userData.update=()=>{
   this.sky.visible=!this.surface;
   this.sky.position.copy(this.camera.position);
   material.uniforms.gain.value=this.starGain||1;
   material.uniforms.flare.value=this.starFlare??1;
   material.uniforms.boost.value=THREE.MathUtils.clamp((this.starSize||1)/2.5,.4,2);
   material.uniforms.pixel.value=this.renderer.getPixelRatio();
   const origin=this.local?.item?.pos||this.camera.position;
   const local=this.local?.item?.data.id;
   const catalogStars=this.mode==='stars'?this.visibleCatalogStars:null;
   if(this.mode===lastMode&&local===lastLocal&&lastCatalogStars===catalogStars&&(this.mode!=='stars'||origin.equals(lastOrigin)))return;
   lastMode=this.mode;lastLocal=local;lastCatalogStars=catalogStars;lastOrigin.copy(origin);
   for(let i=0;i<entries.length;i++){
    raw.copy(directions[i]);
    if(this.mode==='stars')raw.sub(origin);
    else {const y=-raw.z,z=raw.y;raw.set(raw.x,-sin*y+cos*z,-(cos*y+sin*z));}
    const hidden=entries[i].id===local||(!local&&catalogStars?.has(entries[i].id))||raw.lengthSq()<1e-12;
    // apparent magnitude from this vantage point, then relative flux (mag 0 → 1)
    flux[i]=hidden?0:Math.pow(10,-.4*(absolute[i]+5*Math.log10(Math.max(raw.length(),1e-6)/10)));
    if(hidden)raw.set(0,0,0);
    else raw.setLength(3000);
    raw.toArray(positions,i*3);
   }
   geometry.attributes.position.needsUpdate=true;
   geometry.attributes.flux.needsUpdate=true;
  };
  this.sky.userData.update();
 };
 C.prototype.catalogAtPointer=function(pointer){
  const points=this.sky?.children[0];
  const entries=points?.userData.catalogEntries;
  if(!this.sky?.visible||!entries)return null;
  const positions=points.geometry.attributes.position.array;
  const projected=new THREE.Vector3();
  let best=null, radius=6;
  for(let i=0;i<entries.length;i++){
   if(!points.geometry.attributes.flux.array[i])continue;
   projected.fromArray(positions,i*3).applyMatrix4(points.matrixWorld).project(this.camera);
   if(projected.z<0||projected.z>=1)continue;
   const distance=Math.hypot((projected.x-pointer.x)*this.w/2,(projected.y-pointer.y)*this.h/2);
   if(distance<radius){radius=distance;best=entries[i];}
  }
  return best;
 };
 C.prototype.stellarCloseup=function(item,...args){
  close.call(this,item,...args);
  if((item.data.teff_gspphot||0)>=2300)this.localGroup.add(corona(1));
  const reliable=Number.isFinite(item.data.teff_gspphot)&&item.data.teff_gspphot>0;
  $('stellar-provenance').textContent=reliable?'COMPUTED appearance using catalog temperature. Faint visible-light glow; any surface activity is illustrative and accelerated.':'TEMPERATURE UNKNOWN: close-up color and appearance are illustrative and may be inaccurate. No measured stellar activity is claimed.';
  if(reliable&&item.data.teff_gspphot<2300)$('stellar-provenance').textContent+=' Cool brown-dwarf appearance is illustrative; this is not a visible-light photograph.';
  $('stellar-system').hidden=false;$('stellar-system').disabled=true;$('stellar-system').textContent='Loading planet catalog…';
  $('planet-list')?.replaceChildren();
  $('stellar-system').onclick=()=>this.systemOverview();
  const context=this.local;
  const show=planets=>{if(this.local!==context)return;item.data.planets=planets;addPlanets(this,item,planets);};
  this.companionsReady=item.data.planets?Promise.resolve(show(item.data.planets)):
    this.journey?Promise.resolve(show([])):
   item.data.ra!=null?fetch('/api/companions?'+new URLSearchParams({ra:item.data.ra,dec:item.data.dec,name:item.data.name})).then(r=>{if(!r.ok)throw Error('Planet catalog unavailable');return r.json();}).then(data=>show(data.planets||[])).catch(()=>{if(this.local===context){$('stellar-system').textContent='Planet catalog unavailable';$('stellar-provenance').textContent+=' Planet catalog could not load; no orbit has been invented.';}}):Promise.resolve(show([]));
 };
 C.prototype.systemOverview=function(){
  if(!this.local)return;this.local.followPlanet=null;const distance=Math.max(6,(this.local.systemExtent||2)*3.4);
  this.controls.maxDistance=Math.max(1800,distance*4);this.camera.far=Math.max(100000,distance*10);this.camera.updateProjectionMatrix();
  return this.fly(new THREE.Vector3(),new THREE.Vector3(0,distance*.5,distance),5500);
 };
 C.prototype.planetCloseup=async function(planet){
  if(!this.local||!planet)return;
  this.local.followPlanet=planet;const radius=planet.userData.displayRadius||.1,target=planet.position.clone();
  return this.fly(target,target.clone().add(new THREE.Vector3(0,radius*3,radius*8)),4500);
 };
 C.prototype.exitLocal=function(){exit.call(this);if(this.mode==='solar')for(const i of this.items){i.mesh.visible=!i.model;if(i.model)i.model.visible=true;}if($('stellar-system'))$('stellar-system').hidden=true;$('planet-list')?.replaceChildren();};
 C.prototype.focus=async function(){
  this.exitLocal();const i=this.items.find(i=>i.data.id===this.selected);if(!i)return;
  const selected=this.selected,d=Math.max(i.radius*4.4,this.camera.position.distanceTo(this.controls.target));
  const direction=this.camera.position.clone().sub(i.pos).normalize();if(!direction.length())direction.set(0,.25,1).normalize();
  const finished=await this.turnLeftTo(i.pos.clone().sub(this.camera.position),550,'');
  if(!finished||this.journey||this.selected!==selected)return;
  return this.fly(i.pos,i.pos.clone().addScaledVector(direction,d),1050);
 };
 // Every orbit-camera zoom uses the same gradual geometric-distance path.
 const fly=C.prototype.fly;
 C.prototype.fly=function(target,pos,duration=1800){this.zoomImpulse=0;return fly.call(this,target,pos,duration);};
 const orbit=C.prototype.planetOrbit;
 C.prototype.planetOrbit=function(id=this.selected){if(this.mode==='solar'&&id==='sun'){this.showPaths=true;this.orbits.visible=true;this.orbits.children.forEach(o=>o.visible=true);return this.overview();}return orbit.call(this,id);};
}

// Star colour from effective temperature (black-body approximation, gently desaturated as the eye sees it).
function starColor(teff){
 const t=Math.min(40000,Math.max(2000,teff||5600))/100;
 let r=t<=66?255:329.7*Math.pow(t-60,-.1332);
 let g=t<=66?99.47*Math.log(t)-161.12:288.12*Math.pow(t-60,-.0755);
 let b=t>=66?255:t<=19?0:138.52*Math.log(t-10)-305.04;
 const c=new THREE.Color(Math.min(255,Math.max(0,r))/255,Math.min(255,Math.max(0,g))/255,Math.min(255,Math.max(0,b))/255);
 return c.lerp(new THREE.Color(1,1,1),.45);
}

// Point stars: brighter stars are drawn larger and with a soft glow, as a camera or the eye records them. The
// star itself is unresolved; the size encodes its apparent brightness (computed from the catalog magnitude).
function starMaterial(){
 return new THREE.ShaderMaterial({
  transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,
  uniforms:{flare:{value:1},gain:{value:1},boost:{value:1},pixel:{value:1}},
  vertexShader:`attribute float flux;attribute vec3 color;uniform float boost;uniform float pixel;varying vec3 vColor;varying float vGlow;
   void main(){
    float m=-2.5*log(max(flux,1e-12))/log(10.);          // apparent magnitude
    float s=clamp(1.6+9.5*pow(10.,-.13*(m-.5)),1.6,16.);   // mag 6 ≈ 3 px, mag 0 ≈ 10 px, Sirius-class ≈ 14 px
    float a=clamp(1.25-.11*m,.18,1.);                       // faint stars fade, bright ones saturate
    vColor=color*a; vGlow=clamp((2.5-m)/4.,0.,1.);
    gl_PointSize=(flux>0.?s*boost:0.)*pixel;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
  fragmentShader:`${stellarProfileGLSL}
uniform float gain;varying vec3 vColor;varying float vGlow;
   void main(){vec2 q=gl_PointCoord-.5;float r=length(q)*2.;
    float i=stellarProfile(q*2.,vGlow);if(i<.01)discard;
    gl_FragColor=vec4(vColor*i*gain,1.);}`,
 });
}

// Deep backdrop for the 3D views: 25,700 Hipparcos/HYG stars to V 7.5 and the Milky Way (same data as the
// "Your sky" planetarium). Directions only, so it sits at infinity behind both the AU and the parsec scenes.
function addDeepSky(scene){
 const group=new THREE.Group();group.name='Deep sky backdrop';group.matrixAutoUpdate=false;
 scene.sky.add(group);
 const eps=THREE.MathUtils.degToRad(23.439291111),sn=Math.sin(eps),cs=Math.cos(eps);
 // equatorial unit vector → scene direction, for each mode (same mapping the catalog points use)
 const toStars=v=>new THREE.Vector3(v.x,v.z,-v.y);
 const toSolar=v=>{const r=toStars(v),y=-r.z,z=r.y;return new THREE.Vector3(r.x,-sn*y+cs*z,-(cs*y+sn*z));};
 const basis=f=>new THREE.Matrix4().makeBasis(f(new THREE.Vector3(1,0,0)),f(new THREE.Vector3(0,1,0)),f(new THREE.Vector3(0,0,1)));
 const frames={stars:basis(toStars),solar:basis(toSolar)};
 let starMat=null,mwMat=null,lastMode=null;
 group.userData.update=()=>{
  const mode=scene.mode==='stars'?'stars':'solar';
  if(mode!==lastMode){group.matrix.copy(frames[mode]);group.matrixWorldNeedsUpdate=true;lastMode=mode;}
  if(starMat){starMat.uniforms.flare.value=scene.starFlare??1;starMat.uniforms.gain.value=scene.starGain||1;starMat.uniforms.minMag.value=mode==='stars'?3.2:-9;starMat.uniforms.pixel.value=scene.renderer.getPixelRatio();starMat.uniforms.boost.value=THREE.MathUtils.clamp((scene.starSize||2.5)/2.5,.5,2);}
  if(mwMat)mwMat.uniforms.strength.value=scene.local?.4:1;
 };
 const tex=new THREE.TextureLoader().load('/assets/sky/milkyway.jpg');
 tex.colorSpace=THREE.NoColorSpace;tex.minFilter=THREE.LinearMipmapLinearFilter;
 mwMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.BackSide,uniforms:{map:{value:tex},strength:{value:1}},
  vertexShader:`varying vec3 vDir;void main(){vDir=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
  fragmentShader:`uniform sampler2D map;uniform float strength;varying vec3 vDir;void main(){vec3 d=normalize(vDir);float ra=atan(d.y,d.x);if(ra<0.)ra+=6.2831853;float dec=asin(clamp(d.z,-1.,1.));
   float v=texture2D(map,vec2(ra/6.2831853,.5+dec/3.1415926)).r;vec3 tint=mix(vec3(.5,.56,.75),vec3(1.,.88,.72),v);gl_FragColor=vec4(tint*pow(v,1.35)*.16*strength,1.);}`});
 const mw=new THREE.Mesh(new THREE.SphereGeometry(2950,96,48),mwMat);mw.renderOrder=-3;mw.frustumCulled=false;group.add(mw);
 fetch('/assets/sky/stars.bin').then(r=>r.ok?r.arrayBuffer():null).then(buffer=>{
  if(!buffer)return;
  const b=new Float32Array(buffer),n=b.length/4,pos=new Float32Array(n*3),mag=new Float32Array(n),col=new Float32Array(n*3);
  for(let i=0;i<n;i++){const ra=THREE.MathUtils.degToRad(b[i*4]),dec=THREE.MathUtils.degToRad(b[i*4+1]);
   pos[i*3]=2900*Math.cos(dec)*Math.cos(ra);pos[i*3+1]=2900*Math.cos(dec)*Math.sin(ra);pos[i*3+2]=2900*Math.sin(dec);mag[i]=b[i*4+2];
   const bv=b[i*4+3],t=4600*(1/(.92*bv+1.7)+1/(.92*bv+.62));starColor(t).toArray(col,i*3);}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(pos,3));g.setAttribute('mag',new THREE.BufferAttribute(mag,1));g.setAttribute('tint',new THREE.BufferAttribute(col,3));
  starMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,uniforms:{flare:{value:1},pixel:{value:1},gain:{value:1},boost:{value:1},minMag:{value:-9}},
   vertexShader:`attribute float mag;attribute vec3 tint;uniform float pixel;uniform float boost;uniform float minMag;varying vec3 vC;varying float vG;
    void main(){float b=pow(10.,-.4*(mag-7.));float on=step(minMag,mag);
     vC=tint*clamp(.085*pow(b,.45),.025,2.4)*on;vG=clamp(log(b)/4.-.6,0.,1.);
     gl_PointSize=on>0.?clamp(1.3+2.1*pow(b,.24),1.3,22.)*boost*pixel:0.;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
   fragmentShader:`${stellarProfileGLSL}
uniform float gain;varying vec3 vC;varying float vG;void main(){vec2 q=gl_PointCoord-.5;float r=length(q)*2.;float i=stellarProfile(q*2.,vG);if(i<.004)discard;gl_FragColor=vec4(vC*i*gain,1.);}`});
  const p=new THREE.Points(g,starMat);p.frustumCulled=false;p.renderOrder=-2;group.add(p);
 }).catch(()=>{});
 group.userData.update();
}
