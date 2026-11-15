export function epochPair(frames){
 const rows=frames.filter(f=>f.status==='ready'&&Number.isFinite(f.wavelength_um)&&Number.isFinite(f.mjd)).sort((a,b)=>a.mjd-b.mjd);
 let best=null;
 for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
  const a=rows[i],b=rows[j],days=b.mjd-a.mjd;
  if(a.detector!==b.detector||Math.abs(a.wavelength_um-b.wavelength_um)>.025||days<1)continue;
  // Prefer usable coverage, then time span. Never select by residual amplitude.
  const usable=Math.min(a.valid_fraction??1,b.valid_fraction??1)>=.5;
  if(!best||Number(usable)>Number(best.usable)||(usable===best.usable&&days>best.days))best={frames:[a,b],days,usable};
 }
 return best;
}
export function epochSequence(frames){
 const rows=frames.filter(f=>f.status==='ready'&&Number.isFinite(f.wavelength_um)&&Number.isFinite(f.mjd));
 let best=null;
 for(const anchor of rows){
  const selected=rows.filter(f=>f.detector===anchor.detector&&f.wavelength_um>=anchor.wavelength_um&&f.wavelength_um<=anchor.wavelength_um+.025).sort((a,b)=>a.mjd-b.mjd);
  const nights=new Set(selected.map(f=>Math.floor(f.mjd))).size,days=selected.at(-1).mjd-selected[0].mjd;
  if(days<1)continue;
  if(!best||nights>best.nights||(nights===best.nights&&selected.length>best.frames.length)||(nights===best.nights&&selected.length===best.frames.length&&days>best.days))best={frames:selected,nights,days,detector:anchor.detector,minWave:anchor.wavelength_um};
 }
 return best;
}
export function installEpochCompare(view){
 const $=id=>document.getElementById(id);
 $('compare-epochs').onclick=async()=>{
  if(!view.jobId)return;
  view.stop();view.clearComputed();view.epochComparison=null;view.targetFrame=null;view.position=0;
  $('group').value='all';$('compare-mode').value='single';$('enhance').checked=true;$('red-changes').checked=true;$('speed').value='100';$('filmstrip').hidden=false;
  view.refreshFrames();$('epoch-note').textContent='Every loaded exposure plays in date order. Red compares each frame with its nearest earlier compatible date, not the previous image when its band differs. Missing and loading frames stay marked in the timeline.';
  const job=view.jobId;await view.show();if(view.jobId===job)view.togglePlay();
  try{await view.api('/api/jobs/'+job+'/resume',{method:'POST'});if(view.jobId===job&&!view.polling)view.poll(view.generation);}catch(e){view.toast(e.message);}
 };
 $('fetch-all').onclick=async()=>{if(!view.jobId)return;const id=view.jobId;try{$('epoch-note').textContent='Fetching every remaining exposure; new frames join in date order. No two-frame limit.';await view.api('/api/jobs/'+id+'/resume',{method:'POST'});if(view.jobId===id&&!view.polling)view.poll(view.generation);}catch(e){view.toast(e.message);}};
 $('all-epochs').hidden=true;
}
