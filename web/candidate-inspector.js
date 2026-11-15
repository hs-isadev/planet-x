// Review aids operate only on real measurements; no chemistry classifier is implied.
import {sameCalibrationRelease} from './exposure-sequence.js';

const $=id=>document.getElementById(id);
const references=[
 {name:'H₂O ice',lambda:3.05,R:35,url:'https://spherex.caltech.edu/page/the-origin-of-water-in-planetary-systems'},
 {name:'CO₂ ice',lambda:4.27,R:112,url:'https://spherex.caltech.edu/page/the-origin-of-water-in-planetary-systems'},
 {name:'CO ice',lambda:4.67,R:128,url:'https://spherex.caltech.edu/page/the-origin-of-water-in-planetary-systems'},
 {name:'H I Paβ (air)',lambda:1.2818,R:41,url:'https://www.nist.gov/pml/atomic-spectroscopy-compendium-basic-ideas-notation-data-and-formulas/atomic-spectroscopy-atomic'}
];
export function strongestSpectralDip(points) {
 const bands=new Map();
 for(const p of points){
  if(p.status!=='ok'||!p.date||!p.detector||![p.wavelength_um,p.flux_ujy,p.error_ujy].every(Number.isFinite)||
     p.error_ujy<=0||p.flux_ujy<0)continue;
  const key=p.date.slice(0,10)+'/'+p.detector;
  if(!bands.has(key))bands.set(key,[]);
  bands.get(key).push(p);
 }
 let best;
 for(const samples of bands.values()){
  samples.sort((a,b)=>a.wavelength_um-b.wavelength_um);
  for(const point of samples){
   const wave=point.wavelength_um;
   const halfBand=Math.max(.012,((point.passband_high_um??wave)-(point.passband_low_um??wave))/2);
   const left=samples.findLast(p=>wave-p.wavelength_um>=halfBand*2);
   const right=samples.find(p=>p.wavelength_um-wave>=halfBand*2);
   if(!left||!right||wave-left.wavelength_um>.2||right.wavelength_um-wave>.2||
       left.flux_ujy<3*left.error_ujy||right.flux_ujy<3*right.error_ujy)continue;
   const t=(wave-left.wavelength_um)/(right.wavelength_um-left.wavelength_um);
   const baseline=(1-t)*left.flux_ujy+t*right.flux_ujy;
   const sigma=(baseline-point.flux_ujy)/Math.hypot(point.error_ujy,(1-t)*left.error_ujy,t*right.error_ujy);
   if(sigma>=4&&(!best||sigma>best.sigma))best={point,wave,sigma,halfBand,depth:1-point.flux_ujy/baseline};
  }
 }
 return best;
}

export function installCandidateInspector(view){
 const box=document.createElement('section');box.id='candidate-inspector';box.hidden=true;
 box.innerHTML='<h3>Candidate evidence</h3><p id="candidate-position" class="micro"></p><label>Observation date A<select id="spectrum-date-a"></select></label><label>Compare date B<select id="spectrum-date-b"></select></label><label class="check"><input id="spectrum-features" type="checkbox">Show reference-feature windows</label><p id="spectrum-coverage" class="micro" role="status"></p><p id="spectrum-dip" class="micro"></p><p class="micro">Reference windows are ±λ/(2R), calculated from nominal instrumental resolution, not measured absorption widths. H I reference uses air wavelength; no vacuum or redshift correction is applied. These overlays cannot identify a chemical.</p><div id="feature-sources" class="micro"></div><label>Your review<select id="candidate-class"><option value="uncertain">Uncertain</option><option value="possible_motion">Possible motion</option><option value="brightness_change">Brightness change</option><option value="artifact">Artifact</option></select></label><p id="classification-help" class="micro"></p><button id="candidate-lightcurve" class="quiet">Measure same-band brightness history</button><button id="spectrum-export" class="quiet">Download spectrum CSV</button><button id="evidence-export" class="quiet">Export reproducible evidence card</button><details><summary>Measurements and source observations</summary><div style="max-height:260px;overflow:auto"><table id="spectrum-measurements"><thead><tr><th>Date / detector</th><th>λ / µm</th><th>Flux ± error / µJy</th><th>Quality</th></tr></thead><tbody></tbody></table></div></details>';
 $('spectrum').after(box);
 $('measure-center-spectrum').onclick=async()=>{
  if(!view.current()){view.toast('Load an observed frame to measure the spectrum.');return;}
  const job=view.jobId,token=++view.measureToken;
  const button=$('measure-center-spectrum');
  button.disabled=true;$('measurement-note').textContent='Measuring native flux at each available wavelength…';
  try{
   const result=await view.api('/api/jobs/'+job+'/spectrum?'+new URLSearchParams({x:.5,y:.5,radius:$('aperture-radius').value}));
   if(job!==view.jobId||token!==view.measureToken)return;
   view.plotSpectrum(result);
   $('measurement-note').textContent='Field-center aperture spectrum.';
   $('spectrum').scrollIntoView({block:'nearest'});
  }catch(error){if(token===view.measureToken)$('measurement-note').textContent=error.message;}
  finally{button.disabled=false;}
 };
 for(const r of references){const a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noreferrer';a.textContent=r.name+' '+(r.lambda-r.lambda/r.R/2).toFixed(3)+'–'+(r.lambda+r.lambda/r.R/2).toFixed(3)+' µm ↗';const p=document.createElement('p');p.append(a);$('feature-sources').append(p);}
 const explanations={uncertain:'Use uncertain when wavelength coverage, masks, alignment or signal-to-noise do not support a conclusion.',possible_motion:'Look for a consistent position track across suitable dates. Band changes and frame-wide shifts are not object motion.',brightness_change:'A brightness change needs a stable aperture and compatible bandpass; it does not establish displacement.',artifact:'Inspect masks, detector edges, PSF differences and coherent field-wide residuals.'};
 const classify=()=>{$('classification-help').textContent=explanations[$('candidate-class').value];};$('candidate-class').onchange=classify;classify();
 // The selected frame is the comparison anchor. IDs stay stable as more frames load.
 const pairPanel=document.createElement('section');
 pairPanel.innerHTML='<h4>Check a source across two dates</h4><label>Reference exposure<select id="candidate-reference"></select></label><button id="candidate-compare" class="quiet">Measure source positions</button><p id="candidate-comparison-status" class="micro" role="status"></p><img id="candidate-difference" hidden style="width:100%;image-rendering:pixelated" alt="Registered difference, later minus earlier"><p id="candidate-difference-note" class="micro"></p>';
 $('candidate-lightcurve').after(pairPanel);
 let comparison=null;
 let anchor=null;
 function updateReferences(){
  const a=view.current();
  const key=a&&a.id+":"+view.job?.ready;
  if(!a||!view.job||anchor===key)return;
  const previous=$("candidate-reference").value;anchor=key;
  const refs=view.job.frames.filter(f=>f.status==='ready'&&f.id!==a.id&&f.detector===a.detector&&sameCalibrationRelease(f.release,a.release)&&Math.abs(f.mjd-a.mjd)>=1)
    .sort((b,c)=>Math.abs((b.wavelength_um??0)-(a.wavelength_um??0))-Math.abs((c.wavelength_um??0)-(a.wavelength_um??0))||Math.abs(c.mjd-a.mjd)-Math.abs(b.mjd-a.mjd));
  $('candidate-reference').replaceChildren(...refs.map(f=>new Option(f.date+' · D'+f.detector+' · '+(f.wavelength_um?.toFixed(3)??'?')+' µm',f.id)));
  if(refs.some(f=>f.id===previous))$('candidate-reference').value=previous;
  $('candidate-compare').disabled=!refs.length;
  $('candidate-difference').hidden=true;$('candidate-difference-note').textContent='';
  $('candidate-comparison-status').textContent=refs.length?'Compare with the displayed exposure. The check uses calibrated wavelength, PSF and nearby reference stars.':'Load a second date from the same detector with compatible calibration.';
 }
 $('candidate-compare').onclick=async()=>{
  const a=view.current(), b=$('candidate-reference').value, candidate=view.candidate;
  if(!a||!b||!candidate?.normalized_position)return;
  const job=view.jobId,button=$('candidate-compare');
  button.disabled=true;comparison=null;
  $('candidate-comparison-status').textContent='Checking the two exposures. The first request may download IRSA calibration files.';
  try{
   const [x,y]=candidate.normalized_position;
   const result=await view.api('/api/jobs/'+job+'/calibrated-pair?'+new URLSearchParams({a:a.id,b,x,y}));
   if(job!==view.jobId||candidate!==view.candidate||view.current()?.id!==a.id)return;
   comparison=result;
   const checks=result.checks||{};
   const dates=result.exposures.map(f=>f.date.slice(0,10)).join(' → ');
   let summary=result.reason;
   if(result.status==='measured'){
    const [east,north]=result.displacement_arcsec,[ex,ny]=result.component_error_arcsec;
    summary='Measured displacement '+east.toFixed(2)+' ± '+ex.toFixed(2)+'″ east, '+north.toFixed(2)+' ± '+ny.toFixed(2)+'″ north. Source association remains provisional.';
   }
   if(checks.reference_stars!=null)summary+=' '+checks.reference_stars+' reference stars.';
   if(checks.overlap_pixels!=null)summary+=' '+checks.overlap_pixels+' pixels passed the band-overlap and mask check.';
   $('candidate-comparison-status').textContent=dates+' · '+summary;
   const diff=$('candidate-difference');diff.hidden=!result.difference;
   if(result.difference){diff.src=result.difference.image;$('candidate-difference-note').textContent=result.difference.description+' Signed residuals can also be brightness changes.';}
   view.draw();
  }catch(e){if(job===view.jobId&&candidate===view.candidate)$('candidate-comparison-status').textContent=e.message;}
  finally{if(job===view.jobId&&candidate===view.candidate){button.disabled=false;}}
 };
 let full=null;
 $('spectrum-export').onclick=()=>{
  if(!full||view.candidate?.jobId!==view.jobId)return;
  const fields=['exposure_id','date','mjd','detector','wavelength_um','passband_low_um','passband_high_um','flux_ujy','error_ujy','valid_fraction','status','reason','wavelength_calibration','calibration_url','source_url'];
  const rows=[['ra_deg','dec_deg','aperture_radius_arcsec',...fields],...full.points.map(point=>[full.ra,full.dec,full.radius_arcsec,...fields.map(key=>point[key])])];
  const csv=rows.map(row=>row.map(value=>'"'+String(value??'').replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n';
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  view.download(url,'spherex-aperture-spectrum.csv');
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const oldDraw=view.draw.bind(view);
 view.draw=function(){
  oldDraw();
  if(!box.hidden)updateReferences();
  const xy=this.candidate?.normalized_position;
  if(!xy||!this.image||this.computed||this.candidate.jobId!==this.jobId)return;
  const canvas=$('science'), ctx=canvas.getContext('2d');
  ctx.strokeStyle='#d9b66f';ctx.lineWidth=1.5;ctx.beginPath();
  ctx.arc(xy[0]*canvas.width,xy[1]*canvas.height,this.candidate.radius_arcsec/(this.job.fov*60)*canvas.width,0,2*Math.PI);ctx.stroke();
 };
 $('candidate-lightcurve').onclick=async()=>{
  const point=view.candidate?.normalized_position;
  if(!point)return;
  $('lightcurve').closest('details').open=true;
  await view.sourceLightcurve(...point);
 };
 const oldReset=view.reset.bind(view);view.reset=function(...args){full=null;comparison=null;anchor=null;box.hidden=true;this.candidate=null;return oldReset(...args);};
 view.plotSpectrum=function(r){
  full=r;comparison=null;anchor=null;this.candidate={ra:r.ra,dec:r.dec,radius_arcsec:r.radius_arcsec,normalized_position:r.normalized_position,measurements:r.points,notes:r.notes,jobId:this.jobId};box.hidden=false;
  $('candidate-position').textContent='ICRS '+r.ra.toFixed(8)+'°, '+r.dec.toFixed(8)+'° · fixed '+r.radius_arcsec+'″ aperture. This is a fixed sky position, not an automatically tracked object.';
  const dates=[...new Set(r.points.map(p=>(p.date||'').slice(0,10)).filter(Boolean))].sort();
  $('spectrum-date-a').replaceChildren(new Option('All dates (mixed epochs)','all'),...dates.map(d=>new Option(d,d)));
  $('spectrum-date-b').replaceChildren(new Option('No second date','none'),...dates.map(d=>new Option(d,d)));
  $('candidate-lightcurve').disabled=!r.normalized_position;
  render();this.draw();
 };
 function render(){
  if(!full)return;const a=$('spectrum-date-a').value,b=$('spectrum-date-b').value;
  const selected=full.points.filter(p=>a==='all'||p.date?.startsWith(a)||b!=='none'&&p.date?.startsWith(b));
  const good=selected.filter(p=>p.status==='ok'&&Number.isFinite(p.wavelength_um)&&Number.isFinite(p.flux_ujy)&&Number.isFinite(p.error_ujy));
  const c=$('spectrum'),ctx=c.getContext('2d');c.hidden=false;ctx.fillStyle='#10151c';ctx.fillRect(0,0,c.width,c.height);ctx.font='11px monospace';ctx.fillStyle='#dce4ee';
  const rows=$('spectrum-measurements').querySelector('tbody');rows.replaceChildren();
  for(const p of selected){const tr=document.createElement('tr');for(const text of [(p.date||'MJD '+p.mjd)+' / D'+p.detector,p.wavelength_um==null?'unavailable':p.wavelength_um.toFixed(4)+(p.passband_low_um==null?' (approx.)':' ['+p.passband_low_um.toFixed(3)+'–'+p.passband_high_um.toFixed(3)+']'),p.status==='ok'?p.flux_ujy.toPrecision(4)+' ± '+p.error_ujy.toPrecision(3):'unavailable',(p.quality_flags||[]).join(', ')+' '+(p.reason||p.wavelength_calibration||'Conservative aperture mask')]){const td=document.createElement('td');td.textContent=text;tr.append(td);}if(p.source_url){const link=document.createElement('a');link.href=p.source_url;link.textContent='Original '+p.exposure_id;link.target='_blank';link.rel='noreferrer';tr.firstChild.append(document.createElement('br'),link);const jump=document.createElement('button');jump.className='quiet';jump.textContent='Show frame';jump.onclick=async()=>{view.stop();view.clearComputed();$('group').value='all';view.refreshFrames();const index=view.frames.findIndex(f=>f.index===p.frame);if(index>=0){view.position=index;await view.show();}};tr.firstChild.append(jump);}rows.append(tr);}
  let note=good.length+' / '+selected.length+' usable native aperture measurements. Missing values are never interpolated. ';
  note+=good.filter(p=>p.calibration_url).length+' use released wavelength calibration. ';
  note+=a==='all'?'Different dates are mixed; variability can resemble a spectral feature. ':'Date A is blue; date B is amber. No fitted chemical match. ';
  $('spectrum-dip').textContent='';
  if(!good.length){ctx.fillText('Insufficient unmasked native data for a spectrum.',20,40);$('spectrum-coverage').textContent=note;return;}
  const min=Math.min(...good.map(p=>p.wavelength_min_um??p.wavelength_um)),max=Math.max(...good.map(p=>p.wavelength_max_um??p.wavelength_um));
  const lo=Math.min(0,...good.map(p=>p.flux_ujy-p.error_ujy)),hi=Math.max(...good.map(p=>p.flux_ujy+p.error_ujy));
  const x=v=>48+(v-min)/(max-min||1)*450,y=v=>250-(v-lo)/(hi-lo||1)*210;
  ctx.strokeStyle='#84929f';ctx.beginPath();ctx.moveTo(45,35);ctx.lineTo(45,250);ctx.lineTo(505,250);ctx.stroke();ctx.fillText('Flux / µJy',48,15);ctx.fillText('λ '+min.toFixed(3)+'–'+max.toFixed(3)+' µm',125,282);
  if($('spectrum-features').checked)for(const r of references){if(r.lambda<min||r.lambda>max)continue;ctx.fillStyle='#d9b66f25';const left=Math.max(min,r.lambda-r.lambda/r.R/2),right=Math.min(max,r.lambda+r.lambda/r.R/2);ctx.fillRect(x(left),35,x(right)-x(left),215);ctx.fillStyle='#d9b66f';ctx.save();ctx.translate(x(r.lambda),145);ctx.rotate(-Math.PI/2);ctx.fillText(r.name,0,0);ctx.restore();}
  for(const p of good){ctx.strokeStyle=ctx.fillStyle=b!=='none'&&p.date?.startsWith(b)?'#d9b66f':'#c4d5e3';ctx.beginPath();ctx.moveTo(x(p.wavelength_um),y(p.flux_ujy-p.error_ujy));ctx.lineTo(x(p.wavelength_um),y(p.flux_ujy+p.error_ujy));ctx.moveTo(x(p.wavelength_min_um??p.wavelength_um),y(p.flux_ujy));ctx.lineTo(x(p.wavelength_max_um??p.wavelength_um),y(p.flux_ujy));ctx.stroke();ctx.beginPath();ctx.arc(x(p.wavelength_um),y(p.flux_ujy),3,0,2*Math.PI);ctx.fill();}
  const dip=strongestSpectralDip(good);
  if(dip){
   ctx.strokeStyle='#ffb764';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x(dip.wave),y(dip.point.flux_ujy),8,0,Math.PI*2);ctx.stroke();ctx.lineWidth=1;
   const matches=references.filter(ref=>Math.abs(ref.lambda-dip.wave)<=Math.max(dip.halfBand,ref.lambda/(2*ref.R)));
   $('spectrum-dip').textContent='Strongest supported dip: '+dip.wave.toFixed(4)+' µm · '+dip.point.date.slice(0,10)+' · D'+dip.point.detector+
    ' · '+Math.round(dip.depth*100)+'% below nearby samples. '+(matches.length?'Reference overlap: '+matches.map(ref=>ref.name).join(', ')+'. ':'No listed reference feature overlaps. ')+
    'Candidate only. Check another epoch and calibrated spectrum before assigning a species.';
  }else $('spectrum-dip').textContent='No supported absorption dip in the usable samples. A dip needs two nearby continuum samples from the same detector and date.';
  $('spectrum-coverage').textContent=note+'Coverage '+min.toFixed(3)+'–'+max.toFixed(3)+' µm is discontinuous. Absorption depends on source and intervening material, response, resolution and signal-to-noise. No identification is made.';
 }
 for(const id of ['spectrum-date-a','spectrum-date-b','spectrum-features'])$(id).onchange=render;
 $('evidence-export').onclick=()=>{if(!view.candidate||view.candidate.jobId!==view.jobId)return;const j=view.job;const card={schema:'planet-x-evidence-v1',created_at:new Date().toISOString(),source:'IRSA SPHEREx real observations',candidate:view.candidate,calibrated_comparison:comparison?{...comparison,difference:comparison.difference?{...comparison.difference,image:undefined}:undefined}:null,volunteer_classification:$('candidate-class').value,classification_status:'unverified user assessment',coordinate_search:{ra:j.ra,dec:j.dec,fov:j.fov},current_exposure:view.current(),manual_positions:view.marks,brightness_history:view.lightcurve||null,review_receipt:view.sequence||null,scientific_assessment:'uncertain',method:'Native fixed aperture spectrum; optional local-background residual quicklook; Laya suggestions separate from measured residuals',warnings:['A calibrated pair check, when present, applies only to its two listed exposures and tested neighborhood. The general red overlay is a quicklook.','No model scores are detection probabilities.','A fixed aperture does not automatically follow a moving source.'],observations:j.frames.map(f=>({id:f.id,date:f.date,mjd:f.mjd,detector:f.detector,wavelength_um:f.wavelength_um,url:f.url,status:f.status,error:f.error,quality_flags:f.source_flag_values})),reproduce_url:location.origin+'/?'+new URLSearchParams({ra:j.ra,dec:j.dec,fov:j.fov})};const u=URL.createObjectURL(new Blob([JSON.stringify(card,null,2)],{type:'application/json'}));view.download(u,'planet-x-evidence.json');setTimeout(()=>URL.revokeObjectURL(u),1000);};
}
