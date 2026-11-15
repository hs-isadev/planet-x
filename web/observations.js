import {installPartnerEvidence} from './partner-evidence.js';
import {installImageViewport} from './image-viewport.js?v=2';
import {installObservingView} from './observing-view.js';
import {installCandidateInspector} from './candidate-inspector.js?v=2';
import {installEpochCompare} from './epoch-compare.js';
import {chronological,sameCalibrationRelease,sequenceSummary} from './exposure-sequence.js';
import {installTimeTools} from './time-tools.js';
import {installExposureCoverage} from './exposure-coverage.js?v=3';
const $=id=>document.getElementById(id);
const PLAYBACK_LOOKAHEAD=24,MAX_PREFETCH_REQUESTS=4;
export class ObservationDrawer {
 constructor({api,toast,icon}){this.api=api;this.toast=toast;this.icon=icon;this.job=null;this.frames=[];this.position=0;this.playing=false;this.generation=0;this.groups=[];this.image=null;this.reference=null;this.computed=null;this.markers=[];this.marks=[];this.polling=false;this.loadToken=0;this.measureToken=0;this.imageRequests=new Map();this.prefetchQueue=[];this.prefetchInFlight=0;this.playToken=0;this.bind();installTimeTools(this);installEpochCompare(this);installCandidateInspector(this);installObservingView(this);installImageViewport(this);this.updateCoverage=installExposureCoverage(this);}
 async refreshSavedArchive(){
  const status=$('saved-archive-status');
  status.textContent='Reading the saved archive inventory…';
  try{
   const data=await this.api('/api/archive/prefetch-status');
   const releases=Object.entries(data.releases);
   if(!releases.length){status.textContent='The bulk archive inventory is empty. Field searches still prepare cutouts as they load.';return;}
   const count=n=>Number(n||0).toLocaleString();
   const lines=releases.map(([release,stats])=>release.toUpperCase()+': '+count(stats.saved)+' originals saved ('+(stats.saved_bytes/2**30).toFixed(2)+' GiB) · '+count(stats.inventory)+' files indexed'+(stats.errors?' · '+count(stats.errors)+' failed transfers':''));
   status.textContent=lines.join(' | ')+' · '+count(data.periods_indexed)+' / '+count(data.periods)+' archive periods indexed in full.';
  }catch(error){status.textContent=error.message;}
 }
 bind(){ this.updatePartnerEvidence=installPartnerEvidence(this); $('saved-archive-progress').addEventListener('toggle',()=>{if($('saved-archive-progress').open)this.refreshSavedArchive();});$('saved-archive-refresh').onclick=()=>this.refreshSavedArchive();$('laya-review').onclick=()=>this.reviewLaya();let on=(id,event,fn)=>$(id).addEventListener(event,fn);on('observation-close','click',()=>this.close());on('resume-loading','click',async()=>{try{await this.api('/api/jobs/'+this.jobId+'/resume',{method:'POST'});this.poll(this.generation);}catch(e){this.toast(e.message);}});on('play','click',()=>this.togglePlay());on('loop','change',()=>this.prefetchPlayback());on('prev','click',()=>this.step(-1));on('next','click',()=>this.step(1));on('scrubber','input',e=>{this.stop();this.clearComputed();this.targetFrame=null;this.position=+e.target.value;this.show();});on('speed','change',()=>{if(this.playing){this.stop();this.togglePlay();}});on('group','change',()=>{this.autoDetector=false;this.stop();this.clearComputed();this.position=0;this.refreshFrames();this.show();});for(let id of ['enhance','red-changes','cmap','stretch','black','white'])on(id,id==='black'||id==='white'?'input':'change',()=>{if(id==='red-changes'&&$('red-changes').checked)$('enhance').checked=true;if(!['enhance','red-changes'].includes(id))$('enhance').checked=false;this.stop();this.clearComputed();if(id==='enhance'){this.filmSignature=null;this.refreshFrames();}this.show();});for(let id of ['grid','crosshair','split'])on(id,'input',()=>this.draw());on('compare-mode','change',()=>{$('split-control').hidden=$('compare-mode').value!=='split';this.computed=null;$('computed-note').textContent='';this.show();});on('apply-compute','click',()=>this.compute());on('reference','change',()=>this.show());on('click-action','change',()=>{$('aperture-radius-control').hidden=$('click-action').value!=='spectrum';});on('science','click',e=>this.click(e));on('science','mousemove',e=>this.hover(e));on('science','mouseleave',()=>$('marker-tooltip').hidden=true);on('fit-track','click',()=>this.fitTrack());on('clear-track','click',()=>{this.marks=[];$('measurement-note').textContent='Marks cleared.';this.draw();});on('gaia-overlay','change',()=>this.overlays());on('wise-overlay','change',()=>this.overlays());on('export-png','click',()=>this.exportPNG());on('export-gif','click',()=>this.exportGIF());on('copy-link','click',()=>this.copyLink());document.addEventListener('keydown',e=>{if($('observations').hidden||/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName))return;if(e.code==='Space'){e.preventDefault();this.togglePlay();}if(e.key==='ArrowRight'){e.preventDefault();this.step(1);}if(e.key==='ArrowLeft'){e.preventDefault();this.step(-1);}if(e.key==='['||e.key===']'){let s=$('speed');s.selectedIndex=Math.max(0,Math.min(s.options.length-1,s.selectedIndex+(e.key===']'?1:-1)));s.dispatchEvent(new Event('change'));}});}
 open(){document.body.classList.add('observing');$('search-panel').hidden=false;$('observations').hidden=false;this.prefetchPlayback();window.dispatchEvent(new Event('spherex-open'));}close(){document.body.classList.remove('observing');$('search-panel').hidden=true;$('observations').hidden=true;this.prefetchQueue=[];this.stop();}
 status(text,error=false){$('archive-status').textContent=text;$('archive-status').classList.toggle('error',error);}
 reset(title){this.stop();this.generation++;this.jobId=null;this.pendingSearch=null;this.targetFrame=null;$('resume-loading').hidden=true;this.measureToken++;this.filmSignature=null;this.loadedURL=null;this.prefetchQueue=[];this.imageRequests.clear();this.layaReview=null;$('laya-note').textContent='Local Laya Vision: experimental review of real before/after images. Scores are not calibrated for SPHEREx.';$('group').replaceChildren(new Option('All observed frames','all'));$('reference').replaceChildren();$('measurement-note').textContent='';$('computed-note').textContent='';$('overlay-note').textContent='Catalog predictions, not detections.';this.job=null;this.autoDetector=false;this.frames=[];this.groups=[];this.position=0;this.marks=[];this.markers=[];this.overlayKey=null;this.computed=null;this.image=null;this.reference=null;this.loadToken++;this.open();$('observation-title').textContent=title;$('filmstrip').replaceChildren();$('frame-meta').replaceChildren();$('frame-readout').textContent='No frame loaded';$('sequence-note').textContent='';$('image-empty').hidden=false;$('image-empty').querySelector('p').textContent='Searching the real SPHEREx archive';$('image-empty').querySelector('small').textContent='The first usable cutout will appear while the rest load.';$('scrubber').disabled=true;$('play').disabled=true;$('prev').disabled=true;$('next').disabled=true;$('spectrum').hidden=true;this.updateCoverage();this.draw();return this.generation;}
 async search(title='Sky field',frame=null,exposureId=null){const query={ra:$('ra').value,dec:$('dec').value,fov:+$('fov').value};let previous=this.jobId;let generation=this.reset(title);this.pendingSearch=query;if(previous){try{await this.api('/api/jobs/'+previous+'/pause',{method:'POST'});}catch{}}if(generation!==this.generation)return;this.status('Discovering every released exposure covering these coordinates…');try{let result=await this.api('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...query,...(exposureId?{exposure_id:exposureId}:frame!=null?{frame}:{})})});if(generation!==this.generation)return;const url=new URL(location.href);url.searchParams.delete('key');url.searchParams.delete('frame');url.searchParams.delete('exposure');for(const [key,value] of Object.entries(query))url.searchParams.set(key,value);if(frame!=null)url.searchParams.set('frame',frame);if(exposureId)url.searchParams.set('exposure',exposureId);history.replaceState(null,'',url);this.targetFrame=exposureId||frame;this.jobId=result.id;this.poll(generation);}catch(e){if(generation===this.generation){this.pendingSearch=null;this.fail(e.message);}}}
 async openFile(key){let generation=this.reset('Selected archive exposure');this.status('Reading one manually selected exposure. This is not a complete coordinate search.');try{let r=await this.api('/api/archive/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,fov:+$('fov').value})});if(generation!==this.generation)return;this.jobId=r.id;this.poll(generation);}catch(e){if(generation===this.generation)this.fail(e.message);}}
 fail(text){this.status(text,true);if(!this.image){$('image-empty').hidden=false;$('image-empty').querySelector('p').textContent='No observed image is available';$('image-empty').querySelector('small').textContent='The archive request failed. No substitute imagery is displayed.';}this.polling=false;}
 async poll(generation){if(generation!==this.generation)return;this.polling=true;try{let job=await this.api('/api/jobs/'+this.jobId);if(generation!==this.generation)return;let oldReady=this.job?.ready,oldId=this.current()?.id;this.job=job;if($('partner-evidence').open)this.updatePartnerEvidence();$('resume-loading').hidden=job.status!=='paused';this.refreshFrames();if(this.targetFrame!=null&&job.ready){let wanted=this.frames.findIndex(f=>f.id===this.targetFrame||f.index===this.targetFrame);if(wanted>=0){this.position=wanted;this.targetFrame=null;}}
 if(job.status==='error'){this.fail(job.message+(job.detail?' '+job.detail:''));return;}if(job.status==='empty'){this.status(job.message);$('image-empty').querySelector('p').textContent='No released images cover this position';$('image-empty').querySelector('small').textContent='Coverage depends on the archive release. Try another field.';this.polling=false;return;}
 let full=job.frames.length,ready=job.ready;this.status(job.source==='cloud'?ready+' manually selected exposure · not a full archive sequence':job.status==='querying'?'Discovering complete released coverage…':ready+' / '+full+' cutouts loaded'+(job.failed?' · '+job.failed+' unavailable':'')+' · '+(job.status==='complete'?(job.discovery_complete===false?'fallback results loaded':'archive search complete'):job.status==='paused'?'background loading paused':'prefetching in background')+(job.discovery_note?' · '+job.discovery_note:''));
 if(job.ready!==oldReady||oldId!==this.current()?.id){if(this.playing)this.prefetchPlayback();else await this.show();this.loadGroups();}
 if(['querying','fetching'].includes(job.status)){setTimeout(()=>this.poll(generation),1500);}else{this.polling=false;if(this.targetFrame!=null&&job.status==='complete'){this.targetFrame=null;this.toast('The shared exposure is unavailable in this sequence.');}}
 }catch(e){if(generation===this.generation)this.fail(e.message);}}
 clearComputed(){this.computed=null;this.computedMetadata=null;this.proof=null;this.reference=null;$('computed-note').textContent='';}
 current(){return this.frames[this.position];}
 async selectExposure(id){
  if(!this.job?.frames.some(frame=>frame.id===id&&frame.status==='ready'))return;
  this.stop();this.clearComputed();this.targetFrame=null;
  if(!this.frames.some(frame=>frame.id===id)){
   $('group').value='all';
   this.refreshFrames();
  }
  this.position=this.frames.findIndex(frame=>frame.id===id);
  if(this.position>=0)await this.show();
 }
 refreshFrames(){
  if(!this.job)return;
  const oldId=this.current()?.id,oldRef=$('reference').value,oldScroll=$('filmstrip').scrollLeft,filter=$('group').value;
  let timeline=chronological(this.job.frames);
  if(/^D[1-6]$/.test(filter))timeline=timeline.filter(f=>f.detector===+filter.slice(1));
  else if(filter!=='all'){const group=this.groups.find(g=>g.id===filter);timeline=group?timeline.filter(f=>group.frames.includes(f.index)):[];}
  this.timeline=timeline;this.frames=timeline.filter(f=>f.status==='ready');
  const previous=this.frames.findIndex(f=>f.id===oldId);
  this.position=previous>=0?previous:Math.min(this.position,Math.max(0,this.frames.length-1));
  $('scrubber').max=Math.max(0,this.frames.length-1);$('scrubber').value=this.position;
  for(const id of ['play','scrubber','prev','next'])$(id).disabled=this.frames.length<(id==='scrubber'?1:2);
  $('sequence-note').textContent=sequenceSummary(this.job,this.frames.length,filter);
  this.updateCoverage?.();
  const signature=timeline.map(f=>f.id+':'+f.status).join('|')+'|'+$('enhance').checked;
  if(signature===this.filmSignature)return;this.filmSignature=signature;
  $('filmstrip').replaceChildren();$('reference').replaceChildren();
  for(const f of timeline){
   const button=document.createElement('button');button.dataset.id=f.id;
   button.title=f.date+' · '+f.band+(f.status==='error'?' · '+(f.error||'Unavailable'):f.status!=='ready'?' · Loading':'');
   button.setAttribute('aria-label','Exposure '+(f.index+1)+' '+button.title);button.disabled=f.status!=='ready';
   if(f.status==='ready'){
    const image=new Image();image.loading='lazy';image.alt='Observed exposure '+f.date;
    image.src='/api/jobs/'+this.jobId+'/frames/'+f.index+'.png?thumbnail=true&cmap=gray&stretch=asinh&enhanced='+$('enhance').checked;button.append(image);
    button.onclick=()=>this.selectExposure(f.id);
    $('reference').add(new Option((f.index+1)+' · '+f.date.slice(0,10)+' · D'+f.detector,f.index));
   }else{const status=document.createElement('span');status.className='pending-exposure';status.textContent=f.status==='error'?'Unavailable':'Loading';button.append(status);}
   const date=document.createElement('span');date.textContent=f.date.slice(0,10);button.append(date);$('filmstrip').append(button);
  }
  if(this.frames.some(f=>String(f.index)===oldRef))$('reference').value=oldRef;else if(this.frames.length>1)$('reference').selectedIndex=this.frames.length-1;
  $('filmstrip').scrollLeft=oldScroll;
 }
 async loadGroups(){let requestedJob=this.jobId;try{let r=await this.api('/api/jobs/'+requestedJob+'/groups');if(!this.job||this.jobId!==requestedJob)return;let selected=$('group').value;this.groups=r.groups;let options=[new Option('All observed frames','all')];for(let d=1;d<=6;d++){let n=this.job.frames.filter(f=>f.status==='ready'&&f.detector===d).length;if(n)options.push(new Option('Detector '+d+' · '+n+' ready','D'+d));}for(let g of r.groups)options.push(new Option('D'+g.detector+' · '+(g.wavelength_min_um!=null?g.wavelength_min_um.toFixed(3):g.label||g.id)+' µm · '+g.frames.length,g.id));$('group').replaceChildren(...options);$('group').value=options.some(o=>o.value===selected)?selected:'all';}catch{}}
 params(index=this.current()?.index,updateLabels=true){const frame=this.job?.frames.find(f=>f.index===index);let c=this.job?.contrasts?.['D'+frame?.detector]||this.job?.contrast;if(!c)return new URLSearchParams();let lo=c.black,span=c.white-lo;let b=lo+span*(+$('black').value/100),w=lo+span*(+$('white').value/100);if(w<=b)w=b+Math.max(span*.01,.001);if(updateLabels){$('black-value').textContent=b.toFixed(2);$('white-value').textContent=w.toFixed(2);}return new URLSearchParams({cmap:$('cmap').value,stretch:$('stretch').value,black:b,white:w});}
 imageURL(index,updateLabels=true){
  const p=this.params(index,updateLabels);
  let note='OBSERVED input with a physical intensity scale locked within this detector. Background and faint signals are retained.';
  if($('enhance').checked){
   p.set('enhanced','true');
   const red=$('red-changes').checked;
   const f=this.job.frames.find(f=>f.index===index);
   const candidates=red?this.job.frames.filter(b=>b.status==='ready'&&b.detector===f.detector&&sameCalibrationRelease(b.release,f.release)&&b.wavelength_um!=null&&f.wavelength_um!=null&&Math.abs(b.wavelength_um-f.wavelength_um)<=.025&&f.mjd-b.mjd>=1):[];
   if(candidates.length){
    const ref=candidates.sort((a,b)=>b.mjd-a.mjd||b.index-a.index)[0];
    p.set('changes','true');
    p.set('reference_index',ref.index);
    if(updateLabels)note='COMPUTED: background removed; signals below 2.5σ suppressed. Red = source appearance/disappearance candidates or ≥4σ residuals versus '+ref.date.slice(0,10)+'. Source peaks ≥5σ with faint counterparts <2σ; ≥2 usable pixels. Per-pixel wavelengths must agree within 0.025 µm. Both signs red. Interpretation uncertain because PSF and field-star registration have not been validated.';
   }else if(updateLabels)note='COMPUTED: local median background removed; below 2.5σ suppressed; every frame uses 2.5–12σ grayscale. '+(red?'No same-detector, similar-wavelength exposure on an earlier date is loaded yet; this frame has no change assessment.':'Raw pixels and aperture photometry are unchanged.');
  }
  if(updateLabels){
   if(this.layaReview?.jobId===this.jobId&&this.layaReview.frame===index&&this.layaReview.status==='complete')note+=' COMPUTED: normalized observed pixels. Amber rings are uncalibrated AI review suggestions; red pixels remain the statistical residual layer. Not confirmed detections.';
   if(this.sequence?.jobId===this.jobId&&this.sequence.status==='complete')note+=' COMPUTED: full-sequence Laya review. '+this.sequence.supported_motion_candidates+' model-supported motion candidates; none are confirmed detections. Original pixels are unchanged.';
   $('enhance-note').textContent=note;
  }
  return '/api/jobs/'+this.jobId+'/frames/'+index+'.png?'+p;
 }

 async reviewLaya(){if(!this.current())return;this.stop();this.clearComputed();$('compare-mode').value='single';let job=this.jobId,frame=this.current().index,generation=this.generation;this.layaPendingFrame=frame;let button=$('laya-review');button.disabled=true;this.layaReview=null;$('laya-note').textContent='Starting local Laya Vision review…';try{let r=await this.api('/api/jobs/'+job+'/laya?frame='+frame,{method:'POST'});while(r.status==='running'){if(this.jobId!==job||this.generation!==generation||this.current()?.index!==frame)return;$('laya-note').textContent=r.message;await new Promise(ok=>setTimeout(ok,1200));r=await this.api('/api/laya/reviews/'+r.id);}if(r.status==='error')throw new Error(r.message);if(this.jobId!==job||this.current()?.index!==frame)return;let switched=r.frame!==frame;if(switched){this.job=await this.api('/api/jobs/'+job);$('group').value='all';this.refreshFrames();this.position=Math.max(0,this.frames.findIndex(f=>f.index===r.frame));}this.layaReview={...r,jobId:job};let choices=r.regions.map((x,i)=>(x.pixels?'L'+(i+1)+': ':'Whole field: ')+x.choice);$('laya-note').textContent=(switched?'Switched to a compatible loaded band/date pair. ':'')+r.message+' · '+r.dates.map(d=>d.slice(0,10)).join(' → ')+'. '+choices.join('; ')+'. '+r.note;await this.show();}catch(e){$('laya-note').textContent='Laya review failed: '+e.message+' No AI decision was substituted.';}finally{button.disabled=false;this.layaPendingFrame=null;}}

 async imageLoad(url,prefetch=false){
  const cached=this.imageRequests.get(url);
  if(cached){
   if(!prefetch)cached.image.fetchPriority='high';
   this.imageRequests.delete(url);
   this.imageRequests.set(url,cached);
   return cached.promise;
  }
  const image=new Image();
  const entry={image};
  image.fetchPriority=prefetch?'low':'high';
  entry.promise=new Promise((resolve,reject)=>{
   image.onload=()=>resolve(image);
   image.onerror=()=>{
    if(this.imageRequests.get(url)===entry)this.imageRequests.delete(url);
    reject(new Error('The frame image could not be loaded.'));
   };
  });
  this.imageRequests.set(url,entry);
  if(this.imageRequests.size>64)this.imageRequests.delete(this.imageRequests.keys().next().value);
  image.src=url;
  return entry.promise;
 }
 async show(){this.updateCoverage?.();if($('partner-evidence').open)this.updatePartnerEvidence();let f=this.current();if(!f)return;if((this.layaReview&&this.layaReview.frame!==f.index)||(this.layaPendingFrame!=null&&this.layaPendingFrame!==f.index))$('laya-note').textContent='This frame has no Laya review. Choose Review with Laya to assess a compatible pair.';let token=++this.loadToken;$('scrubber').value=this.position;const frameReadout=(this.position+1)+' / '+this.frames.length+' · '+f.date+' · '+f.band+' · '+(f.wavelength_um?.toFixed(3)||'unknown')+' µm';$('sequence-note').textContent=sequenceSummary(this.job,this.frames.length,$('group').value);
 $('frame-meta').replaceChildren();let p=document.createElement('p');p.textContent='MJD '+f.mjd.toFixed(6)+' · '+f.release+' · '+Math.round((f.valid_fraction||0)*100)+'% usable pixels';$('frame-meta').append(p);for(let text of [f.band,'FLAGS '+(f.source_flag_values||[]).join(', '),'OBSERVED']){let s=document.createElement('span');s.className='chip';s.textContent=text;$('frame-meta').append(s);}let note=document.createElement('p');note.className='micro';note.textContent=f.flags_policy||'Conservative quality mask applied.';$('frame-meta').append(note);
 $('filmstrip').querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',b.dataset.id===f.id));let requestedURL=this.imageURL(f.index);if(this.loadedURL!==requestedURL)$('frame-readout').textContent='Buffering frame '+(this.position+1)+' / '+this.frames.length;if(this.loadedURL!==requestedURL&&!this.computed&&!this.imageRequests?.has(requestedURL)){this.image=null;this.reference=null;this.draw();$('image-empty').hidden=false;$('image-empty').querySelector('p').textContent='Loading observed frame '+(this.position+1);$('image-empty').querySelector('small').textContent='Waiting for the matching observed pixels.';}try{const request=this.imageLoad(requestedURL);this.prefetchPlayback();let img=await request;if(token!==this.loadToken)return;$('frame-readout').textContent=frameReadout;this.image=img;this.loadedURL=requestedURL;$('image-empty').hidden=true;if($('compare-mode').value==='split'){let ref=await this.imageLoad(this.imageURL(+$('reference').value));if(token!==this.loadToken)return;this.reference=ref;}this.draw();this.colorbar(this.computed?this.computedMetadata?.display:null);if($('gaia-overlay').checked||$('wise-overlay').checked)this.overlays();}catch(e){if(token!==this.loadToken)return;this.status(e.message,true);if(!this.image){$('image-empty').hidden=false;$('image-empty').querySelector('p').textContent='This observation could not load';$('image-empty').querySelector('small').textContent='Retry or select another real frame.';}}}
 draw(){let canvas=$('science'),ctx=canvas.getContext('2d'),w=canvas.width;ctx.clearRect(0,0,w,w);ctx.fillStyle='#05070d';ctx.fillRect(0,0,w,w);ctx.imageSmoothingEnabled=false;let img=this.computed||this.image;if(img)ctx.drawImage(img,0,0,w,w);if(this.reference&&$('compare-mode').value==='split'&&!this.computed){let x=w*+$('split').value/100;ctx.save();ctx.beginPath();ctx.rect(x,0,w-x,w);ctx.clip();ctx.drawImage(this.reference,0,0,w,w);ctx.restore();ctx.strokeStyle='#e8ecf4';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,w);ctx.stroke();}document.querySelector('.observed-tag').textContent=this.computed||$('enhance').checked?'COMPUTED / OBSERVED INPUT':'OBSERVED';if(!img)return;if(this.layaReview?.jobId===this.jobId&&this.layaReview.frame===this.current()?.index){for(let [number,r] of this.layaReview.regions.entries()){if(!r.pixels)continue;ctx.strokeStyle='#d9b66f';ctx.lineWidth=2;ctx.beginPath();ctx.arc(r.x*w,r.y*w,12,0,Math.PI*2);ctx.stroke();ctx.font='10px monospace';ctx.fillStyle=ctx.strokeStyle;ctx.fillText('L'+(number+1),Math.min(w-190,r.x*w+12),Math.max(14,r.y*w-12));}}if($('grid').checked){ctx.strokeStyle='#ffffff40';ctx.lineWidth=.6;ctx.setLineDash([3,6]);for(let n=1;n<4;n++){ctx.beginPath();ctx.moveTo(n*w/4,0);ctx.lineTo(n*w/4,w);ctx.moveTo(0,n*w/4);ctx.lineTo(w,n*w/4);ctx.stroke();}ctx.setLineDash([]);ctx.fillStyle='#cdd7e3';ctx.font='10px monospace';ctx.fillText('ICRS TAN · '+this.job.ra.toFixed(5)+'°, '+this.job.dec.toFixed(5)+'°',12,w-14);}if($('crosshair').checked){ctx.strokeStyle='#f0f3f3a0';ctx.lineWidth=.8;ctx.beginPath();for(let [x1,y1,x2,y2] of [[w/2-14,w/2,w/2-4,w/2],[w/2+4,w/2,w/2+14,w/2],[w/2,w/2-14,w/2,w/2-4],[w/2,w/2+4,w/2,w/2+14]]){ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);}ctx.stroke();}for(let m of this.markers){ctx.strokeStyle=m.catalog==='Gaia DR3'?'#e4eaf3':'#d4b894';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(m.x*w,m.y*w,6,0,Math.PI*2);ctx.stroke();}let points=this.marks.filter(m=>m.frame===this.current()?.index);ctx.strokeStyle='#e7bf87';ctx.fillStyle='#e7bf87';for(let m of points){ctx.beginPath();ctx.arc(m.x*w,m.y*w,5,0,Math.PI*2);ctx.stroke();}if(this.marks.length>1){ctx.beginPath();this.marks.forEach((m,i)=>i?ctx.lineTo(m.x*w,m.y*w):ctx.moveTo(m.x*w,m.y*w));ctx.stroke();}}
 colorbar(display=null){if(!display&&$('enhance').checked){let ctx=$('colorbar').getContext('2d'),im=ctx.createImageData(260,16);for(let y=0;y<16;y++)for(let x=0;x<260;x++){let i=(y*260+x)*4,v=Math.asinh(3*x/259)/Math.asinh(3)*232;im.data[i]=im.data[i+1]=im.data[i+2]=v;im.data[i+3]=255;}ctx.putImageData(im,0,0);$('colorbar-label').textContent='2.5 — 12 σ · computed signal / noise';return;}let img=new Image();img.onload=()=>$('colorbar').getContext('2d').drawImage(img,0,0,260,16);img.src='/api/colorbar?cmap='+(display?.colormap||$('cmap').value)+'&stretch='+(display?.stretch||$('stretch').value);let p=this.params();$('colorbar-label').textContent=Number(display?.black??p.get('black')).toFixed(2)+' — '+Number(display?.white??p.get('white')).toFixed(2)+' '+(display?.unit||this.job?.contrast?.unit||'');}
 stop(){this.playing=false;this.blinking=false;this.updateCoverage?.();this.playToken++;clearTimeout(this.timer);$('play').innerHTML=this.icon('play');$('play').setAttribute('aria-label','Play time sequence');}
 prefetchPlayback(){
  this.prefetchQueue=[];
  if(!this.job||!this.frames.length||$('observations').hidden)return;
  if(this.blinking)return;
  const available=$('loop').checked?this.frames.length-1:this.frames.length-1-this.position;
  for(let offset=1;offset<=Math.min(PLAYBACK_LOOKAHEAD,available);offset++){
   const next=this.frames[(this.position+offset)%this.frames.length];
   const url=this.imageURL(next.index,false);
   if(!this.imageRequests.has(url))this.prefetchQueue.push(url);
  }
  this.drainPrefetch();
 }
 drainPrefetch(){
  while(this.prefetchInFlight<MAX_PREFETCH_REQUESTS&&this.prefetchQueue.length){
   const url=this.prefetchQueue.shift();
   if(this.imageRequests.has(url))continue;
   this.prefetchInFlight++;
   this.imageLoad(url,true).catch(()=>{}).finally(()=>{
    this.prefetchInFlight--;
    this.drainPrefetch();
   });
  }
 }
 togglePlay(){if(this.playing){this.stop();return;}if(this.frames.length<2)return;this.playing=true;let token=++this.playToken;$('play').innerHTML=this.icon('pause');$('play').setAttribute('aria-label','Pause time sequence');this.prefetchPlayback();let advance=async()=>{if(!this.playing||token!==this.playToken)return;if(this.position===this.frames.length-1&&!$('loop').checked){this.stop();return;}const started=performance.now();await this.step(1,true);if(this.playing&&token===this.playToken){this.timer=setTimeout(advance,Math.max(0,+$('speed').value-(performance.now()-started)));}};this.timer=setTimeout(advance,+$('speed').value);}
 async blinkExposures(ids){
  const frames=ids.map(id=>this.job?.frames.find(frame=>frame.id===id&&frame.status==='ready'));
  if(frames.some(frame=>!frame))return;
  this.stop();this.clearComputed();this.targetFrame=null;
  if(ids.some(id=>!this.frames.some(frame=>frame.id===id))){
   $('group').value='all';
   this.refreshFrames();
  }
  $('compare-mode').value='single';$('split-control').hidden=true;
  $('red-changes').checked=false;
  this.playing=true;this.blinking=true;
  const token=++this.playToken;
  $('play').innerHTML=this.icon('pause');
  $('play').setAttribute('aria-label','Stop pair blink');
  for(const frame of frames)this.imageLoad(this.imageURL(frame.index,false),true).catch(()=>{});
  let next=0;
  const drawFrame=async()=>{
   if(token!==this.playToken||!this.blinking)return;
   this.position=this.frames.findIndex(frame=>frame.id===ids[next]);
   if(this.position<0){this.stop();return;}
   await this.show();
   if(token!==this.playToken||!this.blinking)return;
   next=1-next;
   this.timer=setTimeout(drawFrame,400);
  };
  await drawFrame();
 }
 async step(n,fromPlayer=false){if(!fromPlayer)this.stop();this.targetFrame=null;if(!this.frames.length)return;this.position=(this.position+n+this.frames.length)%this.frames.length;this.clearComputed();await this.show();}
 async compute(){if(!this.job||!this.current())return;let requestedJob=this.jobId,generation=this.generation;let mode=$('compare-mode').value;if(mode==='single'||mode==='split'){this.computed=null;await this.show();return;}try{let q={mode,a:this.current().index,b:+$('reference').value};if(mode==='stack'){if($('group').value==='all'||/^D[1-6]$/.test($('group').value))throw new Error('Choose a narrow detector/wavelength group before stacking.');q.group=$('group').value;}let r=await this.api('/api/jobs/'+this.jobId+'/computed?'+new URLSearchParams(q));let computedImage=await this.imageLoad(r.image);if(this.jobId!==requestedJob||this.generation!==generation)return;this.computed=computedImage;this.computedMetadata=r;$('computed-note').textContent=r.note;this.draw();this.colorbar(r.display);}catch(e){$('computed-note').textContent=e.message;}}
 async click(e){let action=$('click-action').value;if(!this.current()||action==='none')return;if(!this.image){this.toast('Wait for this observed frame to load.');return;}let rect=$('science').getBoundingClientRect(),x=(e.clientX-rect.left)/rect.width,y=(e.clientY-rect.top)/rect.height;if(action==='track'){let f=this.current();this.marks=this.marks.filter(m=>m.frame!==f.index);this.marks.push({frame:f.index,frame_id:f.id,x,y});$('measurement-note').textContent=this.marks.length+' frame positions marked. Use the same source in separated epochs.';this.draw();return;}let token=++this.measureToken;$('measurement-note').textContent='Measuring native observed pixels…';try{let r=await this.api('/api/jobs/'+this.jobId+'/spectrum?'+new URLSearchParams({x,y,radius:$('aperture-radius').value}));if(token!==this.measureToken)return;this.plotSpectrum(r);$('measurement-note').textContent=r.notes.join(' ');}catch(e){$('measurement-note').textContent=e.message;}}
 plotSpectrum(r){let p=r.points.filter(p=>p.status==='ok'&&Number.isFinite(p.wavelength_um)&&Number.isFinite(p.flux_ujy));let c=$('spectrum'),ctx=c.getContext('2d');c.hidden=false;ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#10151c';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#c7d0dc';ctx.font='13px monospace';if(!p.length){ctx.fillText('No valid aperture measurements.',20,40);return;}let xx=p.map(p=>p.wavelength_um),yy=p.map(p=>p.flux_ujy),x0=Math.min(...xx),x1=Math.max(...xx),y0=Math.min(0,...yy),y1=Math.max(...yy);let x=v=>45+(v-x0)/(x1-x0||1)*450,y=v=>250-(v-y0)/(y1-y0||1)*220;ctx.strokeStyle='#84929f';ctx.beginPath();ctx.moveTo(40,20);ctx.lineTo(40,250);ctx.lineTo(500,250);ctx.stroke();ctx.fillText('λ '+x0.toFixed(2)+'–'+x1.toFixed(2)+' µm',150,282);ctx.fillText('Flux / µJy',45,15);ctx.fillText(y1.toPrecision(3),45,32);for(let a of p){ctx.strokeStyle='#c4d5e3';ctx.fillStyle='#c4d5e3';ctx.beginPath();ctx.arc(x(a.wavelength_um),y(a.flux_ujy),3,0,Math.PI*2);ctx.fill();if(a.error_ujy){ctx.beginPath();ctx.moveTo(x(a.wavelength_um),y(a.flux_ujy-a.error_ujy));ctx.lineTo(x(a.wavelength_um),y(a.flux_ujy+a.error_ujy));ctx.stroke();}}}
 async fitTrack(){if(!this.jobId||this.marks.length<2){$('measurement-note').textContent='Mark the same source in at least two frames first.';return;}let requestedJob=this.jobId,generation=this.generation;try{let r=await this.api('/api/jobs/'+requestedJob+'/track',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points:this.marks})});if(this.jobId!==requestedJob||this.generation!==generation)return;$('measurement-note').textContent=r.motion_arcsec_per_year.toFixed(2)+' arcsec / year · baseline '+r.baseline_days.toFixed(1)+' days. Nominal component error ±'+r.nominal_component_error_arcsec_per_year.toFixed(2)+' arcsec / year. '+r.notes.join(' ');this.draw();}catch(e){$('measurement-note').textContent=e.message;}}
 async overlays(){if(!this.current())return;let token=this.current().id,key=this.jobId+'|'+token+'|'+$('gaia-overlay').checked+'|'+$('wise-overlay').checked;if(key===this.overlayKey)return;this.overlayKey=key;this.markers=[];$('overlay-note').textContent=($('gaia-overlay').checked||$('wise-overlay').checked)?'Loading catalog predictions…':'Catalog markers are off.';for(let [id,catalog] of [['gaia-overlay','gaia'],['wise-overlay','wise']]){if(!$(id).checked)continue;try{let r=await this.api('/api/jobs/'+this.jobId+'/catalog?'+new URLSearchParams({frame:this.current().index,catalog}));if(this.current()?.id!==token||this.overlayKey!==key)return;this.markers.push(...r.markers);$('overlay-note').textContent=r.notes.join(' ');}catch(e){if(this.overlayKey===key)$('overlay-note').textContent=e.message;}}this.draw();}
 hover(e){let r=$('science').getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;let nearest=this.markers.map(m=>({m,d:Math.hypot(m.x-x,m.y-y)})).sort((a,b)=>a.d-b.d)[0];let tip=$('marker-tooltip');if(!nearest||nearest.d>12/r.width){tip.hidden=true;return;}tip.hidden=false;tip.textContent=nearest.m.name+' · '+nearest.m.catalog+'\nCatalog prediction; '+(nearest.m.motion_applied?'proper motion applied':'motion not applied');const area=$('science-frame').getBoundingClientRect();tip.style.left=Math.max(5,Math.min(area.width-190,e.clientX-area.left+12))+'px';tip.style.top=Math.max(5,e.clientY-area.top-40)+'px';}
 async copyLink(){if(!this.job)return;let u=new URL(location.href);u.search='';if(this.job.source==='cloud'){u.searchParams.set('key',this.current()?.source_key||this.job.cloud_key);}else{for(let [k,v] of Object.entries({ra:this.job.ra,dec:this.job.dec,fov:this.job.fov,exposure:this.current()?.id||''}))u.searchParams.set(k,v);}u.searchParams.set('fov',this.job.fov);try{await navigator.clipboard.writeText(u.href);history.replaceState(null,'',u);this.toast('View link copied.');}catch{this.toast(u.href);}}
 download(url,name){let a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();}
 exportPNG(){if(!this.image){this.toast('Load an observed frame first.');return;}let source=$('science'),c=document.createElement('canvas');c.width=source.width;c.height=source.height+96;let x=c.getContext('2d');x.fillStyle='#080b10';x.fillRect(0,0,c.width,c.height);x.drawImage(source,0,0);x.fillStyle='#dce4ee';x.font='10px monospace';let f=this.current(),mode=$('compare-mode').value;let lines=[this.computed?'COMPUTED '+mode.toUpperCase()+' / from observed SPHEREx pixels':$('enhance').checked?'COMPUTED background/noise suppression'+($('red-changes').checked?' / red residual candidates':'')+' / SPHEREx input':'OBSERVED SPHEREx / NASA-IPAC-IRSA'+(mode==='split'?' / computed split display':''),this.computed?'Contributing frame indices: '+(this.computedMetadata?.frames||[]).join(', '):f.date+' / '+f.band+' / '+(f.wavelength_um?.toFixed(3)||'?')+' um','ICRS '+this.job.ra.toFixed(8)+' deg, '+this.job.dec.toFixed(8)+' deg / '+this.job.fov+' arcmin',this.markers.length||this.marks.length?'Catalog/manual layers are computed; not image detections.':'Missing pixels remain blank. No image-derived depth.'];if(this.layaReview?.frame===f.index)lines[0]='COMPUTED / experimental local Laya Vision review / SPHEREx input';lines.forEach((t,i)=>x.fillText(t,12,source.height+20+i*20,c.width-24));this.download(c.toDataURL('image/png'),this.computed?'spherex-computed-'+mode+'.png':'spherex-observed-view.png');}

 async exportGIF(){if(!this.job||this.job.ready<2){this.toast('At least two real frames are needed.');return;}try{this.toast('Preparing observed-frame GIF…');let r=await fetch('/api/jobs/'+this.jobId+'/export.gif?'+new URLSearchParams({fps:1000/(+$('speed').value),indices:this.frames.map(f=>f.index).join(','),cmap:$('cmap').value,stretch:$('stretch').value,black:this.params().get('black'),white:this.params().get('white')}));if(!r.ok){let e=await r.json();throw new Error(e.detail);}let url=URL.createObjectURL(await r.blob());this.download(url,'spherex-sequence.gif');setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){this.toast(e.message);}}
 async waitForResult(continueRunning=()=>true){let started=Date.now();while(continueRunning()&&this.polling&&this.frames.length<3&&Date.now()-started<180000)await new Promise(ok=>setTimeout(ok,1000));if(continueRunning()&&this.frames.length>1)this.togglePlay();}
}
