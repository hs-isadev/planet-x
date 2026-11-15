const $ = id => document.getElementById(id);

export function installObservationTools(view) {
 const canvas = $('science'), options = $('click-action');
 const maskToggle = $('detector-mask'), pixelNote = $('native-pixel-note');
 const status = $('ephemeris-note'), select = $('ephemeris-exposure');
 let masks = new Map(), request = 0, track = null;

 function canInspect() {
  return view.current() && view.image && !view.computed && $('compare-mode').value === 'single';
 }
 function resetNotice() {
  pixelNote.textContent = options.value === 'pixel' ? 'Click the observed image to inspect a native detector pixel.' : options.value === 'identify' ? 'Click a source to check SkyBoT and SIMBAD at the exposure time.' : '';
 }
 options.addEventListener('change', () => { request++; resetNotice(); });
 const click = view.click.bind(view);
 view.click = async event => {
  const mode=options.value;
  if (mode !== 'pixel' && mode !== 'identify') return click(event);
  if (!canInspect()) {
   pixelNote.textContent = 'Open a loaded exposure in Single view to inspect it.';
   return;
  }
  view.stop();
  const frame = view.current(), job = view.jobId, token = ++request;
  const rect = canvas.getBoundingClientRect();
  const q = new URLSearchParams({
   x: (event.clientX-rect.left)/rect.width,
   y: (event.clientY-rect.top)/rect.height
  });
  pixelNote.textContent = mode==='pixel'?'Reading native FITS pixel…':'Matching the point against SkyBoT and SIMBAD…';
  try {
   const p = await view.api('/api/jobs/'+job+'/'+(mode==='pixel'?'pixels':'identify')+'/'+frame.id+'?'+q);
   if (token !== request || job !== view.jobId || frame.id !== view.current()?.id) return;
   if(mode==='identify'){
    const matches=p.matches.map(m=>m.name+' · '+m.source+' · '+m.separation_arcsec.toFixed(2)+'″ away');
    const main=p.matches[0];
    if(main?.designation)$('ephemeris-object').value=main.designation;
    if(main)$('ephemeris-tools').open=true;
    pixelNote.textContent=(matches.length?matches.join(' | ')+'. Positional matches require confirmation.':'No positional match within '+p.tolerance_arcsec+'″.')+(p.unavailable.length?' Unavailable: '+p.unavailable.join(', ')+'.':'');
    return;
   }
   if (!p.inside) {
    pixelNote.textContent = 'This sky point falls outside the native detector cutout.';
    return;
   }
   const value = p.value == null ? 'brightness unavailable' : p.value.toPrecision(5)+' '+p.unit;
   const sigma = p.sigma == null ? 'uncertainty unavailable' : 'σ '+p.sigma.toPrecision(3)+' '+p.unit;
   const wave = p.wavelength_um == null ? 'wavelength unavailable' : p.wavelength_um.toFixed(4)+' µm';
   pixelNote.textContent = [
    'Native cutout x '+p.pixel_x+', y '+p.pixel_y, p.ra.toFixed(6)+'°, '+p.dec.toFixed(6)+'°',
    value, sigma, wave, 'FLAGS '+p.flags+(p.flag_names.length?' ('+p.flag_names.join(', ')+')':''),
    p.usable?'Included by the display mask':'Excluded by the display mask'
   ].join(' · ');
  } catch (error) {
   if (token === request && job === view.jobId && frame.id === view.current()?.id) pixelNote.textContent = error.message;
  }
 };

 const draw = view.draw.bind(view);
 let displayed = null;
 view.draw = function (...args) {
  draw(...args);
  const id = view.current()?.id;
  if (id !== displayed) {
   displayed = id;
   request++;
   resetNotice();
  }
  if (!canInspect()) return;
  const ctx = canvas.getContext('2d'), size = canvas.width;
  if (maskToggle.checked) {
   const url = '/api/jobs/'+view.jobId+'/flags/'+id+'.png';
   let entry = masks.get(url);
   if (!entry) {
    entry = {};
    masks.set(url, entry);
    if (masks.size > 20) masks.delete(masks.keys().next().value);
    view.imageLoad(url).then(image => {
     entry.image = image;
     if (view.current()?.id === id && maskToggle.checked) view.draw();
    }).catch(() => {
     if (view.current()?.id === id && maskToggle.checked) $('detector-mask-note').textContent = 'Native flag mask unavailable for this exposure.';
    });
   } else if (entry.image) {
    ctx.drawImage(entry.image, 0, 0, size, size);
    $('detector-mask-note').textContent = 'Rose overlay marks pixels excluded by the detector flag mask.';
   }
  }
  if (!track) return;
  const row = track.byExposure.get(id);
  if (!row?.prediction || row.prediction.x == null) return;
  ctx.save();
  ctx.lineWidth = 1.7;
  ctx.strokeStyle = '#c9aaff';
  ctx.setLineDash([4,3]);
  ctx.beginPath();
  ctx.arc(row.prediction.x*size, row.prediction.y*size, 10, 0, Math.PI*2);
  ctx.stroke();
  if (row.measured) {
   ctx.setLineDash([]);
   ctx.strokeStyle = '#82e6d5';
   ctx.beginPath();
   ctx.arc(row.measured.x*size, row.measured.y*size, 5, 0, Math.PI*2);
   ctx.stroke();
  }
  ctx.restore();
 };
 maskToggle.onchange = () => {
  $('detector-mask-note').textContent = maskToggle.checked ? 'Open a loaded exposure in Single view to see its flag mask.' : '';
  view.draw();
 };

 const reset = view.reset.bind(view);
 let trackVersion = 0;
 function clearTrack() {
  trackVersion++;
  track = null;
  status.textContent = '';
  select.replaceChildren();
  select.hidden = true;
  $('ephemeris-motion').replaceChildren();$('ephemeris-motion').hidden=true;
  $('ephemeris-export').hidden = true;
  $('ephemeris-start').disabled = false;
 }
 view.reset = function (...args) {
  clearTrack();
  masks = new Map();
  $('detector-mask-note').textContent = '';
  return reset(...args);
 };
 $('ephemeris-clear').onclick = () => { clearTrack(); view.marks=[]; $('measurement-note').textContent='Track and marks cleared.'; view.draw(); };
 $('ephemeris-start').onclick = async () => {
  if (!view.jobId || !view.current()) { status.textContent = 'Load a SPHEREx sequence first.'; return; }
  const designation = $('ephemeris-object').value.trim();
  const anchors=view.marks.length>1?[view.marks[0],view.marks.at(-1)]:view.marks.slice();
  if (!designation&&!anchors.length) { status.textContent = 'Enter a designation or mark one or two exposures.'; return; }
  const version = ++trackVersion, button = $('ephemeris-start');
  const showFrame = view.current().id;
  button.disabled = true;
  status.textContent = designation?'Querying Horizons at the observation times, then measuring native centroids…':'Measuring native centroids near the marked sky path…';
  try {
   const result = await view.api('/api/jobs/'+view.jobId+'/ephemeris', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({designation, anchors:designation?[]:anchors, group:$('group').value})
   });
   if (version !== trackVersion) return;
   track = {result, byExposure:new Map(result.points.map(p => [p.exposure_id, p]))};
   select.replaceChildren(new Option('Jump to a measured or predicted exposure…', ''), ...result.points.map(row =>
    new Option(row.date+' · '+row.status+(row.offset_arcsec == null?'':' · '+row.offset_arcsec.toFixed(2)+'″ offset'),row.exposure_id)));
   select.hidden = false;
   $('ephemeris-export').hidden = false;
   const measured = result.points.filter(p => p.measured);
   showMotionPlot(measured);
   const flagged = measured.filter(p => p.agreement === false).length;
   const outside = result.points.filter(p => p.status === 'outside field').length;
   status.textContent = result.name+' · '+result.observer+' · '+result.evaluated+' of '+result.available+' loaded exposures checked · '+outside+' outside the field · '+measured.length+' measured · '+flagged+' offsets beyond the screening threshold. Dashed purple is predicted; teal is the native PSF fit.';
   await view.selectExposure(showFrame);
  } catch (error) {
   if (version === trackVersion) status.textContent = error.message;
  } finally {
   if (version === trackVersion) button.disabled = false;
  }
 };
 function showMotionPlot(measured) {
  const motion=$('ephemeris-motion'), steps=measured.filter(row=>row.motion);
  motion.replaceChildren();
  motion.hidden=!steps.length;
  if(!steps.length)return;
  const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 590 150');
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Per-step measured speed over time; select a point to open its exposure');
  svg.style.width='100%';
  const left=48, right=570, top=18, bottom=124;
  const start=measured[0].mjd_utc, end=steps.at(-1).mjd_utc;
  const max=Math.max(.01,...steps.map(row=>row.motion.speed_arcsec_per_hour));
  const svgNode=(tag,props,text)=>{
   const el=document.createElementNS(ns,tag);
   for(const [name,value] of Object.entries(props))el.setAttribute(name,value);
   if(text)el.textContent=text;
   return el;
  };
  svg.append(svgNode('path',{d:'M48 18 V124 H570',fill:'none',stroke:'currentColor'}),
   svgNode('text',{x:5,y:20,fill:'currentColor'},max.toFixed(1)),
   svgNode('text',{x:4,y:123,fill:'currentColor'},'0'),
   svgNode('text',{x:50,y:146,fill:'currentColor'},'Speed (″/hr) · Exposure date (UTC)'));
  for(const row of steps){
   const rate=row.motion;
   const x=left+((row.mjd_utc-start)/(end-start||1))*(right-left);
   const y=bottom-rate.speed_arcsec_per_hour/max*(bottom-top);
   const point=svgNode('circle',{cx:x,cy:y,r:5,fill:'#82e6d5',tabindex:0});
   const details=row.date+' · '+rate.speed_arcsec_per_hour.toFixed(2)+'″/hr · PA '+rate.position_angle_deg.toFixed(1)+'°';
   point.append(svgNode('title',{},details));
   point.setAttribute('aria-label',details);
   point.onclick=()=>view.selectExposure(row.exposure_id);
   point.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();point.click();}};
   svg.append(point);
  }
  const p=document.createElement('p');
  p.className='micro';
  const last=steps.at(-1).motion;
  p.textContent='Last measured step '+last.displacement_arcsec.toFixed(2)+'″ ± '+last.nominal_shift_error_arcsec.toFixed(2)+'″ nominal error · '+last.speed_arcsec_per_hour.toFixed(2)+'″/hr · position angle '+last.position_angle_deg.toFixed(1)+'°. These are projected sky-plane changes.';
  motion.append(svg,p);
 }
 select.onchange = () => { if(select.value) view.selectExposure(select.value); };
 $('ephemeris-export').onclick = () => {
  if (!track) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(track.result, null, 2)], {type:'application/json'}));
  view.download(url,'spherex-horizons-track.json');
  setTimeout(() => URL.revokeObjectURL(url), 1000);
 };
}
