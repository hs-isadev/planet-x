import {installSatelliteView} from './satellite-view.js?v=4';
const $=id=>document.getElementById(id);
const icons={search:'<circle cx="7.5" cy="7.5" r="5"/><path d="m11.5 11.5 4 4"/>',close:'<path d="m4 4 10 10M14 4 4 14"/>',theme:'<circle cx="9" cy="9" r="5.5"/><path d="M9 3.5v11a5.5 5.5 0 0 0 0-11"/>',info:'<circle cx="9" cy="9" r="7"/><path d="M9 8v5M9 5v.2"/>',expand:'<path d="M2 6V2h4M12 2h4v4M16 12v4h-4M6 16H2v-4"/>',target:'<circle cx="9" cy="9" r="5"/><path d="M9 1v4M9 13v4M1 9h4M13 9h4"/>',arrow:'<path d="M3 9h12M10 4l5 5-5 5"/>',link:'<path d="m7 11 4-4M6 13l-1 1a3 3 0 0 1-4-4l4-4a3 3 0 0 1 4 0M12 5l1-1a3 3 0 0 1 4 4l-4 4a3 3 0 0 1-4 0"/>',play:'<path d="m5 3 9 6-9 6Z"/>',pause:'<path d="M6 3v12M12 3v12"/>',prev:'<path d="M4 4v10M14 4l-8 5 8 5Z"/>',next:'<path d="M14 4v10M4 4l8 5-8 5Z"/>',image:'<rect x="2" y="2" width="14" height="14" rx="2"/><circle cx="6" cy="6" r="1"/><path d="m2 13 5-5 4 4 2-2 3 3"/>'};
function icon(k){return '<svg viewBox="0 0 18 18" aria-hidden="true">'+(icons[k]||icons.info)+'</svg>';}document.querySelectorAll('[data-icon]').forEach(e=>e.innerHTML=icon(e.dataset.icon));
export function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>$('toast').hidden=true,5500);}
export async function api(url,options={}){let c=new AbortController(),timer=setTimeout(()=>c.abort(),100000);try{let r=await fetch(url,{...options,signal:c.signal});if(!r.ok){let t=await r.json().catch(()=>({detail:'Request failed ('+r.status+')'}));throw new Error(typeof t.detail==='string'?t.detail:JSON.stringify(t.detail));}return await r.json();}catch(e){if(e.name==='AbortError')throw new Error('The data service is taking too long. Please retry.');throw e;}finally{clearTimeout(timer);}}
const state={mode:'solar',solar:null,stars:null,selected:'earth',presets:[],scope:'nearby'};let scene=null;let cosmicBusy=false,cosmicReady=null;
function message(text){$('scene-message').textContent=text;$('scene-message').hidden=!text;}
function facts(rows,id='object-facts'){
 const list=$(id);
 list.replaceChildren();
 for(const [label,value] of rows){
  const dt=document.createElement('dt'),dd=document.createElement('dd');
  dt.textContent=label;dd.textContent=value;list.append(dt,dd);
 }
 list.hidden=!rows.length;
}
let selectionToken=0;
function selectedData(){return state.mode==='solar'?state.solar?.objects.find(x=>x.id===state.selected):state.stars?.objects.find(x=>x.id===state.selected);}
function contextParams(d){return new URLSearchParams({date:$('date').value,...(state.mode==='solar'||state.selected==='origin'?{body:state.selected==='origin'?'sun':state.selected}:{ra:d.ra,dec:d.dec,distance_pc:d.distance_pc})});}
function select(id,focus=false){let token=++selectionToken;state.selected=id;scene?.select(id,focus);let d=selectedData();if(id==='origin')d={id,name:'Sun',kind:'G-type star',description:'Our star is the origin of this catalog-distance view.',distance_pc:0,teff_gspphot:5772};if(!d)return;
 $('object-name').textContent=d.name;
 $('object-kind').textContent=d.kind || (d.spectral_type ? 'Spectral type '+d.spectral_type : 'Catalog source');
 $('object-description').textContent=d.description||'';
 $('object-description').hidden=!d.description;
 if(state.mode==='solar'){
  const rows=[['From Sun',d.distance_sun_au.toFixed(3)+' AU'],['Mean radius',d.radius_km.toLocaleString('en-US')+' km']];
  if(d.effective_temperature_k)rows.push(['Temperature',d.effective_temperature_k.toLocaleString()+' K']);
  else if(d.orbital_period_days)rows.push(['Orbital period',d.orbital_period_days.toLocaleString()+' days']);
  facts(rows);
  facts([],'object-extra-facts');
  $('object-source').textContent=d.asset_error||(d.id==='sun'?'Illustrative plasma and granulation at 5,772 K.':d.texture_note||'');
  $('observe-selected').hidden=true;
 }else{
  const rows=[['Distance from Sun',id==='origin'?'Solar origin':Number.isFinite(d.distance_pc)?(d.distance_pc*3.26156).toFixed(2)+' ly':'Unavailable']];
  if(Number.isFinite(d.teff_gspphot)&&d.teff_gspphot>0)rows.push(['Estimated temperature',Math.round(d.teff_gspphot).toLocaleString()+' K']);
  if(d.spectral_type&&d.kind)rows.push(['Spectral type',d.spectral_type]);
  facts(rows);
  const extra=[];
  if(d.distance_lower_pc!=null&&d.distance_upper_pc!=null)extra.push(['Distance interval',d.distance_lower_pc.toFixed(3)+'–'+d.distance_upper_pc.toFixed(3)+' pc']);
  if(d.phot_g_mean_mag!=null)extra.push(['Gaia G magnitude',d.phot_g_mean_mag.toFixed(2)]);
  if(d.ra!=null&&d.dec!=null)extra.push(['RA / Dec',d.ra.toFixed(3)+'°, '+d.dec.toFixed(3)+'°']);
  if(d.catalog)extra.push(['Catalog',d.catalog]);
  if(d.object_type)extra.push(['Catalog type',d.object_type]);
  if(d.bp_rp!=null)extra.push(['Gaia color (BP−RP)',d.bp_rp.toFixed(2)]);
  facts(extra,'object-extra-facts');
  $('object-source').textContent=(d.uncertain?'Distance is uncertain or model-based. ':'')+
   (d.teff_gspphot&&id!=='origin'?'Temperature is a catalog estimate. ':'')+
   'The close-up is an illustration of the source.';
  $('observe-selected').hidden=id==='origin';
 }
 $('object-source').hidden=!$('object-source').textContent;
 $('trace-earth').hidden=id==='earth'||!!d.parent;$('context-note').textContent='';
 if(id!=='earth')api('/api/journey?'+contextParams(d)).then(c=>{if(token!==selectionToken)return;$('context-note').textContent='Seen from Earth: '+c.constellation+'. Light travel time: '+(c.light_time_years<.01?(c.light_time_years*365.25*24*60).toFixed(1)+' minutes':c.light_time_years.toFixed(2)+' years')+'.';}).catch(()=>{if(token===selectionToken)$('context-note').textContent='Earth sky context is unavailable.';});
 $('object-strip').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.id===id));let b=[...$('object-strip').children].find(x=>x.dataset.id===id);b?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
}
function strip(items,solar){
 $('object-strip').replaceChildren();
 if(!solar){const home=document.createElement('button');home.className='solar-home';home.textContent='Solar System';home.onclick=()=>showSolar();const note=document.createElement('small');note.textContent='SUN · PLANETS · EARTH';home.append(note);$('object-strip').append(home);}
 const visible=solar?items:[{id:'origin',name:'Sun',distance_pc:0},...[...items].filter(i=>i.id!=='origin').sort((a,b)=>a.distance_pc-b.distance_pc).slice(0,18)];
 for(const d of visible){const button=document.createElement('button');button.dataset.id=d.id;button.setAttribute('aria-pressed',d.id===state.selected);const span=document.createElement('span'),small=document.createElement('small');span.textContent=d.name.replace('Gaia DR3 ','');small.textContent=solar?(d.id==='sun'?'STAR':d.kind.includes('Terrestrial')?'ROCKY PLANET':d.kind.toUpperCase()):d.id==='origin'?'SOLAR SYSTEM':d.distance_pc.toFixed(2)+' pc';button.append(span,small);button.onclick=()=>d.id==='origin'?showSolar():select(d.id,true);$('object-strip').append(button);}
}
function filterStars(){if(!scene||state.mode!=='stars')return;scene.filterRadius=+$('visible-radius').value;scene.filterMagnitude=+$('visible-magnitude').value;let visible=scene.applyFilter();strip(visible,false);$('visible-count').textContent=visible.length+' visible · '+state.stars.objects.length+' loaded';}
let sceneLoadGeneration=0;
function solarControls(){
 $('star-filters').hidden=true;document.body.dataset.scene='solar';
 $('solar-tab').setAttribute('aria-pressed','true');$('stars-tab').setAttribute('aria-pressed','false');
 $('date').hidden=false;$('date-label').hidden=false;$('catalog-epoch').hidden=true;$('paths-toggle').hidden=false;
 $('size-note').textContent='Distances to scale · radii enlarged';$('scene-eyebrow').textContent='COMPUTED / EPHEMERIS';
 $('scene-title').textContent='Our place in space.';$('scene-subtitle').textContent='The Sun and eight planets, at their calculated positions.';
}
async function showSolar(date=$('date').value){
 const generation=++sceneLoadGeneration,started=performance.now(),minimumDelay=state.solarLoaded?0:5000;state.mode='solar';solarControls();
 scene?.clear();if(scene){scene.loading=true;scene.controls.enabled=false;}
 $('scene-loading').hidden=false;$('inspector').hidden=true;$('object-strip').replaceChildren();message('');
 try{
  const data=await api('/api/solar?date='+date);if(generation!==sceneLoadGeneration)return;
  state.solar=data;await scene?.solar(data);if(generation!==sceneLoadGeneration)return;
  strip(data.objects,true);select(data.objects.some(x=>x.id===state.selected)?state.selected:'earth');
  // Put the camera in its initial view behind the loading cover, rather than
  // exposing a partially loaded world and then snapping into place.
  if(scene){const item=scene.items.find(i=>i.data.id===state.selected);scene.stopFlight();if(item){scene.controls.target.copy(item.pos);scene.camera.position.copy(item.pos).add(item.pos.clone().set(0,item.radius*1.8,item.radius*5));scene.controls.update();}}
  await new Promise(resolve=>setTimeout(resolve,Math.max(0,minimumDelay-(performance.now()-started))));
  if(generation!==sceneLoadGeneration)return;
  state.solarLoaded=true;$('inspector').hidden=false;$('data-notes').textContent='Photos are flat; 3D depth comes from catalog distances. '+data.notes.join(' ');
 }catch(error){if(generation===sceneLoadGeneration){scene?.clear();message(error.message);}}
 finally{if(generation===sceneLoadGeneration){$('scene-loading').hidden=true;if(scene){scene.loading=false;scene.controls.enabled=true;}}}
}
async function showStars(scope='nearby'){sceneLoadGeneration++;$('scene-loading').hidden=true;if(scene){scene.loading=false;scene.controls.enabled=true;}state.mode='stars';$('star-filters').hidden=false;scene?.clear();$('inspector').hidden=true;$('object-strip').replaceChildren();document.body.dataset.scene='stars';state.scope=scope;$('solar-tab').setAttribute('aria-pressed','false');$('stars-tab').setAttribute('aria-pressed','true');$('date').hidden=true;$('date-label').hidden=true;$('catalog-epoch').hidden=false;$('paths-toggle').hidden=true;$('size-note').textContent='Catalog distances · unresolved starlight';$('scene-eyebrow').textContent='CATALOG / COMPUTED DEPTH';$('scene-title').textContent=scope==='nearby'?'Our stellar neighborhood.':'Your field, with distance.';$('scene-subtitle').textContent='Fetching measured catalog distances…';message('Querying Gaia DR3…');try{let d=await api('/api/space?'+new URLSearchParams({ra:$('ra').value,dec:$('dec').value,fov:$('fov').value,scope,radius_pc:$('radius').value,include_simbad:true}));if(state.mode!=='stars')return;state.stars=d;scene?.stars(d);$('inspector').hidden=false;$('visible-radius').value=scope==='field'?'1000':'5';filterStars();select(d.objects[0]?.id||'origin');$('scene-subtitle').textContent=d.objects.length+' catalog sources'+(scope==='nearby'?' within '+$('radius').value+' pc':' with usable distances')+' · '+d.unknown.length+' without depth'+(d.truncated?' · sample capped':'');$('data-notes').textContent='Photos are flat; 3D depth comes from catalog distances. '+d.notes.join(' ');message(d.objects.length?'':'No reliable catalog distances in this field. Try a larger field.');}catch(e){scene?.clear();$('inspector').hidden=true;$('object-strip').replaceChildren();$('scene-subtitle').textContent='No invented sources or distances are shown.';message(e.message);}}
$('solar-tab').onclick=async()=>{await contextView();await showSolar();};$('stars-tab').onclick=()=>showStars();$('date').value=new Date().toISOString().slice(0,10);$('date').onchange=()=>showSolar();$('focus').onclick=()=>scene?.focus();$('overview').onclick=()=>scene?.overview();$('labels-toggle').onclick=e=>{if(!scene)return;scene.showLabels=!scene.showLabels;e.currentTarget.textContent=scene.showLabels?'Selected label':'Labels off';e.currentTarget.setAttribute('aria-pressed',scene.showLabels);};$('paths-toggle').onclick=e=>{if(!scene)return;scene.showPaths=!scene.showPaths;scene.orbits.visible=scene.showPaths;e.currentTarget.textContent='Orbits '+(scene.showPaths?'on':'off');e.currentTarget.setAttribute('aria-pressed',scene.showPaths);};
function theme(light){document.documentElement.dataset.theme=light?'light':'dark';scene?.theme(light);$('theme').setAttribute('aria-label','Switch to '+(light?'dark':'light')+' theme');try{localStorage.setItem('parallax-theme',light?'light':'dark');}catch{};}
$('theme').onclick=()=>theme(document.documentElement.dataset.theme!=='light');try{theme(localStorage.getItem('parallax-theme')==='light');}catch{};
function searchPanel(open){if(document.body.classList.contains('observing')){$('search-panel').hidden=false;document.body.classList.remove('mobile-search');return;}$('search-panel').hidden=!open;document.body.classList.toggle('searching',open);$('search-toggle').setAttribute('aria-expanded',open);if(open)$('object-query').focus();} $('search-toggle').onclick=()=>searchPanel($('search-panel').hidden);$('search-close').onclick=()=>searchPanel(false);$('about-open').onclick=()=>$('about').showModal();$('about-close').onclick=()=>$('about').close();$('about').addEventListener('click',e=>{if(e.target===$('about'))$('about').close();});for(let id of ['ra','dec'])$(id).addEventListener('input',()=>$('object-query').value='');$('fov').oninput=()=>$('fov-value').textContent=$('fov').value+' arcmin';
let observations;
async function resolve(){let name=$('object-query').value.trim();if(!name)return;let r=await api('/api/resolve?name='+encodeURIComponent(name));$('ra').value=r.ra.toFixed(8);$('dec').value=r.dec.toFixed(8);}
$('coordinate-form').onsubmit=async e=>{e.preventDefault();try{await resolve();searchPanel(false);await observations.search($('object-query').value||'Sky field');}catch(e){toast(e.message);}};$('volume-load').onclick=async()=>{await contextView();searchPanel(false);showStars('nearby');};$('field-stars').onclick=async()=>{try{await contextView();await resolve();searchPanel(false);showStars('field');}catch(e){toast(e.message);}};$('observe-selected').onclick=()=>{let d=state.stars?.objects.find(x=>x.id===state.selected);if(d){$('object-query').value='';$('ra').value=d.ra;$('dec').value=d.dec;observations.search(d.name);}};
async function presets(){try{state.presets=await api('/api/presets');for(let p of state.presets){let b=document.createElement('button'),s=document.createElement('small');b.textContent=p.name;s.textContent=p.description;b.append(s);b.onclick=()=>{if(p.ra==null){$('object-query').value=p.simbad||p.name;toast(p.error+' Retrying name resolution.');return;}$('object-query').value='';$('ra').value=p.ra;$('dec').value=p.dec;$('fov').value=p.id==='barnard'?12:8;$('fov').oninput();searchPanel(false);observations.search(p.name);};$('presets').append(b);}}catch(e){toast(e.message);}}
let archive={prefix:'qr3/level2/',cursor:null};async function loadArchive(more=false){$('archive-path').textContent=archive.prefix;if(!more)$('archive-list').replaceChildren();try{let r=await api('/api/archive?'+new URLSearchParams({prefix:archive.prefix,...(more&&archive.cursor?{cursor:archive.cursor}:{})}));if(!more&&archive.prefix!=='qr3/level2/'){let up=document.createElement('button');up.textContent='← Parent folder';up.onclick=()=>{archive.prefix=archive.prefix.split('/').slice(0,-2).join('/')+'/';loadArchive();};$('archive-list').append(up);}for(let folder of r.prefixes||r.folders||[]){let key=typeof folder==='string'?folder:folder.prefix;let b=document.createElement('button');b.textContent='↳ '+key.replace(archive.prefix,'');b.onclick=()=>{archive.prefix=key;loadArchive();};$('archive-list').append(b);}for(let file of r.files||[]){let key=typeof file==='string'?file:file.key;let b=document.createElement('button');b.textContent=key.split('/').at(-1);b.onclick=()=>{searchPanel(false);observations.openFile(key);};$('archive-list').append(b);}archive.cursor=r.next_cursor;$('archive-more').hidden=!archive.cursor;}catch(e){$('archive-path').textContent=e.message;}}$('archive-section').ontoggle=()=>{if($('archive-section').open&&!$('archive-list').children.length)loadArchive();};$('archive-more').onclick=()=>loadArchive(true);
$('atlas-open').onclick=async()=>{try{
 $('atlas').hidden=false;$('atlas-status').textContent='Loading the sky atlas…';
 if(!window.A){const module=await Promise.race([import('/vendor/aladin-lite.js'),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Atlas initialization timed out.')),15000))]);window.A=module.default;await Promise.race([A.init,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Atlas WebGL initialization timed out.')),15000))]);}
 if(!window.skyAtlas){window.skyAtlas=A.aladin('#atlas',{survey:'P/DSS2/color',fov:10,target:'133.795129 -7.245147',showReticle:true,showLayersControl:false,showCooGrid:true,showCooGridControl:true});skyAtlas.on('click',p=>{if(p?.ra!=null&&p?.dec!=null){$('object-query').value='';$('ra').value=p.ra.toFixed(7);$('dec').value=p.dec.toFixed(7);}});skyAtlas.on('positionChanged',p=>{$('object-query').value='';$('ra').value=p.ra.toFixed(7);$('dec').value=p.dec.toFixed(7);});}
 $('atlas-status').textContent='Coordinate grid ready. Observed DSS2 tiles require access to CDS; a blank survey means tiles are unavailable. Select or pan to fill coordinates.';
 }catch(e){$('atlas-status').textContent=e.message+' Enter coordinates directly to continue.';}};

let tourActive=false;$('tour-stop').onclick=()=>{tourActive=false;observations?.stop();$('tour-view-caption').hidden=true;$('tour-stop').hidden=true;};$('tour').onclick=async()=>{if(tourActive){tourActive=false;$('tour').textContent='Start guided tour';$('tour-view-caption').hidden=true;$('tour-stop').hidden=true;return;}tourActive=true;$('tour').textContent='Stop tour';for(let p of state.presets){if(!tourActive)break;$('tour-caption').textContent=p.name+' — '+p.description;$('tour-view-caption').hidden=false;$('tour-stop').hidden=false;$('tour-view-caption').textContent=p.name+' — '+({barnard:'Look across well-separated dates with one detector.',epsilon:'A nearby brown-dwarf system; compare similar wavelengths.',wise:'Use the longest wavelengths. The faint moving-source candidate remains tentative.',rw:'A young dusty star. Wavelength differences can mimic variability.',rdraconis:'A Mira variable; compare repeated epochs at similar wavelengths.'}[p.id]||p.description);if(p.ra==null){toast(p.name+': coordinates unavailable.');continue;}$('ra').value=p.ra;$('dec').value=p.dec;$('fov').value=p.id==='barnard'?12:8;$('fov').oninput();searchPanel(false);await observations.search(p.name);await observations.waitForResult(()=>tourActive);if(!tourActive)break;await new Promise(ok=>setTimeout(ok,6000));}tourActive=false;$('tour').textContent='Start guided tour';$('tour-view-caption').hidden=true;$('tour-stop').hidden=true;observations.stop();if(observations.jobId){try{await api('/api/jobs/'+observations.jobId+'/pause',{method:'POST'});}catch{}}};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){searchPanel(false);observations?.close();}if(!e.ctrlKey&&!e.metaKey&&e.key==='/'&&!/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)){e.preventDefault();searchPanel(true);}});

$('visible-radius').onchange=filterStars;$('visible-magnitude').onchange=filterStars;
$('approach').onclick=()=>scene?.approach();
$('zoom-in').onclick=()=>zoom(.75);$('zoom-out').onclick=()=>zoom(1.33);
function zoom(f){scene?.zoomBy(f);}
$('stellar-exit').onclick=()=>scene?.smoothExit();$('stellar-surface').onclick=()=>{if(!scene?.local)return;scene.local.followPlanet=null;scene.fly(scene.controls.target.clone().set(0,0,0),scene.camera.position.clone().normalize().multiplyScalar(4.4),6500);};
window.addEventListener('scene-error',e=>toast(e.detail));
let journeyGeneration=0;
function syncSceneControls(){
 if(!scene)return;state.mode=scene.mode;
 if(scene.mode==='solar'){state.solar=scene.solarData;solarControls();strip(state.solar.objects,true);}
 else{state.stars=scene.starsData;document.body.dataset.scene='stars';$('star-filters').hidden=false;$('date').hidden=true;$('date-label').hidden=true;$('catalog-epoch').hidden=false;$('paths-toggle').hidden=true;$('solar-tab').setAttribute('aria-pressed','false');$('stars-tab').setAttribute('aria-pressed','true');$('scene-eyebrow').textContent='CATALOG / COMPUTED DEPTH';$('scene-title').textContent='Our stellar neighborhood.';$('scene-subtitle').textContent='Catalog stars and known planetary systems';$('size-note').textContent='Catalog distances in parsecs';strip(state.stars.objects,false);}
 $('inspector').hidden=false;select(scene.selected);$('return-object').hidden=!scene.traceReturn;
}
async function closeEarthSky(){
 const sky=$('earth-sky');window.skyToken=null;window.skyCleanup?.();
 if(!sky.hidden){const fade=sky.animate([{opacity:1},{opacity:0}],{duration:350});await fade.finished.catch(()=>{});sky.hidden=true;}
}
$('trace-earth').onclick=async()=>{
 const token=++journeyGeneration,data=selectedData()||{name:'Sun'};
 try{
  $('journey-panel').hidden=false;$('journey-sky').hidden=true;$('journey-overview').hidden=true;$('journey-stay').hidden=true;$('journey-exit').hidden=true;$('journey-cancel').hidden=false;
  $('journey-title').textContent='Preparing Earth journey';$('journey-note').textContent='Computing the direction to Earth.';document.body.classList.add('journey-active');
  if(scene.mode==='sizes')await scene.scaleTransition(()=>scene.solar(state.solar));
  const context=await api('/api/journey?'+contextParams(data));if(token!==journeyGeneration)return;
  const date=$('date').value;
  const solar=state.solar?.date?.slice(0,10)===date?state.solar:await api('/api/solar?date='+date);
  if(token!==journeyGeneration)return;
  const reached=await scene.trace(context,solar,(title,note)=>{$('journey-title').textContent=title;$('journey-note').textContent=note;});
  if(token!==journeyGeneration||!reached)return;
  const targetKey=scene.traceReturn.mode+'|'+scene.traceReturn.selected;
  scene.earthTargets.pin(targetKey,data.name,context);
  syncSceneControls();$('journey-overview').hidden=false;$('journey-stay').hidden=false;$('journey-exit').hidden=false;$('journey-cancel').hidden=true;
  const skyButton=$('journey-sky');
  skyButton.hidden=false;skyButton.textContent='Show source sky chart';
  skyButton.onclick=async()=>{
   if(!$('earth-sky').hidden){await closeEarthSky();skyButton.textContent='Show source sky chart';return;}
   try{
    const {earthSky}=await import('./journey.js?v=earth-target-1');
    if(token!==journeyGeneration)return;
    skyButton.textContent='Show Earth';scene.earthTargets.showChart(targetKey);await earthSky(context,data.name,api);
   }catch(error){if(token===journeyGeneration)toast(error.message);}
  };
 }catch(error){if(token!==journeyGeneration)return;toast(error.message);await scene?.cancelTrace();if(token===journeyGeneration){syncSceneControls();$('journey-panel').hidden=true;document.body.classList.remove('journey-active');}}
};
$('journey-exit').onclick=async()=>{
 const generation=++journeyGeneration,button=$('journey-exit');button.disabled=true;await closeEarthSky();if(generation!==journeyGeneration){button.disabled=false;return;}
 $('journey-stay').hidden=true;$('journey-sky').hidden=true;$('journey-overview').hidden=true;$('journey-cancel').hidden=false;document.body.classList.add('journey-active');$('journey-panel').hidden=false;
 try{await scene?.returnFromTrace((title,note)=>{if(generation===journeyGeneration){$('journey-title').textContent=title;$('journey-note').textContent=note;}});if(generation===journeyGeneration)syncSceneControls();}
 catch(error){if(generation===journeyGeneration){toast(error.message);await scene?.cancelTrace();syncSceneControls();}}
 finally{if(generation===journeyGeneration){$('journey-panel').hidden=true;document.body.classList.remove('journey-active');}button.disabled=false;}
};
$('journey-stay').onclick=async()=>{journeyGeneration++;await closeEarthSky();scene.stayOnEarth();syncSceneControls();$('journey-panel').hidden=true;document.body.classList.remove('journey-active');};
$('journey-cancel').onclick=async()=>{journeyGeneration++;await closeEarthSky();await scene?.cancelTrace();syncSceneControls();$('journey-panel').hidden=true;document.body.classList.remove('journey-active');};
$('journey-overview').onclick=async()=>{
 const generation=++journeyGeneration;
 await closeEarthSky();
 if(generation!==journeyGeneration)return;
 scene.stayOnEarth();
 $('journey-panel').hidden=true;document.body.classList.remove('journey-active');
 syncSceneControls();
 scene.overview();
};
$('return-object').onclick=()=>$('journey-exit').click();
$('activity-toggle').onclick=()=>{if(!scene)return;scene.activityEnabled=!scene.activityEnabled;$('activity-toggle').textContent='Activity '+(scene.activityEnabled?'on':'off');$('activity-toggle').setAttribute('aria-pressed',scene.activityEnabled);};


$('size-compare').onclick=async()=>{if(state.mode!=='solar')await showSolar();await scene.sizeComparison();select('sun');};
$('planet-orbit').onclick=()=>{if(state.mode==='solar')scene.planetOrbit();else if(scene.local)scene.systemOverview();else scene.approach();};
$('orbit-rate').onchange=e=>scene.orbitRate=+e.target.value;
$('star-size').oninput=e=>{if(scene)scene.starSize=+e.target.value;};
$('view-fill').oninput=e=>{scene.viewFill=+e.target.value;scene.resize();};
$('systems-toggle').onclick=()=>{observations?.close();$('systems-panel').hidden=!$('systems-panel').hidden;};
$('systems-close').onclick=()=>$('systems-panel').hidden=true;
async function loadSystems(){const home=document.createElement('button');home.className='secondary';home.textContent='Solar System · Sun, Earth and planets';home.onclick=async()=>{$('systems-panel').hidden=true;await contextView();await showSolar();};$('system-targets').append(home);
 let names=['Barnard’s Star','Epsilon Indi B','WISE 0855','RW Aurigae','R Draconis'];
 for(let [i,name] of names.entries()){let card=document.createElement('div'),title=document.createElement('p'),view=document.createElement('button'),observe=document.createElement('button');title.textContent=name;view.textContent='3D system';observe.textContent='SPHEREx images';card.append(title,view,observe);$('system-targets').append(card);view.onclick=async()=>{try{await contextView();let data=await api('/api/target-systems'),target=data.targets[i];if(!target||target.ra==null)throw Error('Catalog coordinates unavailable.');$('ra').value=target.ra;$('dec').value=target.dec;$('object-query').value='';$('systems-panel').hidden=true;if(!target.distance_pc){await showStars('field');$('scene-title').textContent=name;$('scene-subtitle').textContent='Surrounding catalog field; target depth is not established.';toast(name+': reliable target depth is unavailable; surrounding catalog sources are shown.');return;}state.mode='stars';state.stars=data;document.body.dataset.scene='stars';$('solar-tab').setAttribute('aria-pressed','false');$('stars-tab').setAttribute('aria-pressed','true');scene.stars(data,false);scene.filterRadius=Math.max(5,...data.objects.map(o=>o.distance_pc));scene.applyFilter();$('inspector').hidden=false;select(target.id);scene.controls.target.copy(scene.items.find(x=>x.data.id===target.id).pos);scene.camera.position.copy(scene.controls.target);scene.camera.position.z+=1;scene.controls.update();strip(data.objects,false);$('scene-title').textContent=name;$('scene-subtitle').textContent='Catalog system and surrounding stars · catalog distance · known planet orbits shown during close-up';$('size-note').textContent='Catalog parsec scale · photos are flat; depth comes from catalog distances';message('');}catch(e){toast(e.message);}};observe.onclick=()=>{let p=state.presets[i];if(!p?.ra){toast('Target coordinates still loading.');return;}$('ra').value=p.ra;$('dec').value=p.dec;$('systems-panel').hidden=true;observations.search(name);};}
}loadSystems();


let sceneReady=null;
async function ensureScene(){
 if(!sceneReady)sceneReady=(async()=>{const {ObservatoryScene}=await import('./scene.js?v=earth-sweep-1');scene=new ObservatoryScene(select);scene.theme(document.documentElement.dataset.theme==='light');$('activity-toggle').textContent='Activity '+(scene.activityEnabled?'on':'off');$('activity-toggle').setAttribute('aria-pressed',scene.activityEnabled);await showSolar();prefetchUniverse().catch(()=>{});})();
 try{await sceneReady;}catch(error){sceneReady=null;throw error;}
}
async function contextView(){observations?.close();document.body.classList.remove('observing');$('observations').hidden=true;$('search-panel').hidden=true;try{await ensureScene();scene.resize();}catch(e){message('3D is unavailable: '+e.message+'. Return to observations to continue.');}}
// Wire navigation before importing optional views or starting catalog requests.
$('universe-home').onclick=()=>contextView();
$('observation-close').onclick=()=>contextView();
let {ObservationDrawer}=await import('./observations.js?v=inline-camera-1');observations=new ObservationDrawer({api,toast,icon});installSatelliteView(observations);observations.open();
// Catalog availability must never gate navigation or shared-view initialization.
presets();
$('observation-close').onclick=()=>contextView();
$('search-toggle').onclick=()=>{observations.open();$('search-panel').hidden=false;document.body.classList.toggle('mobile-search');$('object-query').focus();};
let params=new URLSearchParams(location.search);if(params.has('fov')){$('fov').value=params.get('fov');$('fov').oninput();}if(params.has('ra')&&params.has('dec')){$('ra').value=params.get('ra');$('dec').value=params.get('dec');observations.search('Shared sky field',Number(params.get('frame')||0));}else if(params.get('key'))observations.openFile(params.get('key'));

function rotateSpaceVector(v,outward){let e=23.439291111*Math.PI/180,x=v.x,y=-v.z,z=v.y;if(outward)return v.set(x,Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y-Math.sin(e)*z));return v.set(x,-Math.sin(e)*y+Math.cos(e)*z,-(Math.cos(e)*y+Math.sin(e)*z));}
function prefetchUniverse(){if(!cosmicReady)cosmicReady=api('/api/space?'+new URLSearchParams({ra:133.79512916666667,dec:-7.245147222222222,fov:8,scope:'nearby',radius_pc:10,include_simbad:true})).then(data=>{if(scene){scene.universeData=data;scene.addCatalogSky(data);}return data;}).catch(e=>{cosmicReady=null;throw e;});return cosmicReady;}
window.addEventListener('cosmic-exit',async()=>{
 if(cosmicBusy||state.mode!=='solar')return;
 cosmicBusy=true;
 try{
  const data=await prefetchUniverse();
  if(state.mode!=='solar'||document.body.classList.contains('observing')||scene.journey)return;
  const offset=rotateSpaceVector(scene.camera.position.clone(),true).setLength(3);
  const up=rotateSpaceVector(scene.camera.up.clone(),true);
  await scene.scaleTransition(()=>{
   scene.stars(data,false);
   scene.selected='origin';
   scene.zoomImpulse=0;
   scene.controls.target.set(0,0,0);
   scene.camera.position.copy(offset);
   scene.camera.up.copy(up);
   scene.controls.update();
   syncSceneControls();
   $('scene-title').textContent='Beyond the Solar System';
   $('scene-subtitle').textContent='Nearby stars · select a star and zoom to approach';
  });
 }catch(error){toast(error.message);}
 finally{cosmicBusy=false;}
});
window.addEventListener('cosmic-enter',async()=>{if(cosmicBusy||state.mode!=='stars')return;cosmicBusy=true;let offset=rotateSpaceVector(scene.camera.position.clone(),false).normalize().multiplyScalar(55),up=rotateSpaceVector(scene.camera.up.clone(),false);try{await scene.scaleTransition(async()=>{await showSolar();scene.stopFlight();scene.selected='sun';scene.controls.target.set(0,0,0);scene.camera.position.copy(offset);scene.camera.up.copy(up);scene.zoomImpulse=0;scene.controls.update();select('sun');});}finally{cosmicBusy=false;}});
window.addEventListener('cosmic-select',async event=>{if(cosmicBusy)return;cosmicBusy=true;try{let data=await prefetchUniverse();await scene.scaleTransition(()=>{state.mode='stars';state.stars=data;document.body.dataset.scene='stars';scene.stars(data,false);scene.selected=event.detail;let i=scene.items.find(i=>i.data.id===event.detail);if(i){scene.controls.target.copy(i.pos);scene.camera.position.copy(i.pos);scene.camera.position.z+=.7;}select(event.detail,false);strip(data.objects,false);$('scene-title').textContent=i?.data.name||'Catalog space';$('scene-subtitle').textContent='Catalog star · scroll or W/S to approach';});}finally{cosmicBusy=false;}});
$('universe-home').onclick=()=>contextView();
// Catalog volume is fetched only when optional 3D context is requested.

window.parallax={state,get scene(){return scene;},get observations(){return observations;},showStars,showSolar,select};

$('observations-home').onclick=()=>observations.open();
