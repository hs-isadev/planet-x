const $=id=>document.getElementById(id);
export function reviewProgress(r){return [r.stage||r.status,r.message,(r.discovered??r.total)+' discovered',r.loaded+' loaded',(r.prepared??0)+' prepared',r.reviewed+' exposures with eligible crops reviewed',(r.failed_downloads??0)+' unavailable cutouts',(r.review_errors??r.failed?.length??0)+' review errors',(r.batches_done??0)+' crops reviewed',(r.pending_crop_batches??0)+' queued crops',(r.unassessed??Math.max(0,(r.loaded||0)-(r.reviewed||0)))+' loaded exposures unassessed','Last progress: '+(r.last_progress_at?new Date(r.last_progress_at).toLocaleString():'none yet')].filter(x=>x!=null).join(' · ');}
export function installSequenceReview(view){
 let timer,epoch=0,activeId,jobId,starting=false;
 let reportVersion;
 const report = $('laya-report');
 const availability=$('laya-availability');
 availability.closest('details').addEventListener('toggle',async event=>{
  if(!event.currentTarget.open)return;
  try{const state=await view.api('/api/laya/status');availability.textContent=state.inference_verified?'Laya has completed inference on this server.':state.note;}
  catch(error){availability.textContent=error.message;}
 });
 const labels = {
  possible_position_shift: 'Possible position shift',
  appeared_or_brightened: 'Appeared or brightened',
  disappeared_or_faded: 'Disappeared or faded',
  artifact_or_missing_data: 'Artifact or missing data',
  no_convincing_change: 'No convincing change',
  uncertain: 'Uncertain',
 };
 async function showReport(r) {
  if(!r?.batches_done)return;
  const version=r.id+':'+r.batches_done+':'+r.status+':'+r.loaded;
  if(reportVersion===version)return;
  reportVersion=version;
  $('laya-guide').disabled=true;
  $('laya-findings').replaceChildren();
  $('laya-example-list').replaceChildren();
  $('laya-report-status').textContent='Reading saved crop comparisons…';
  try{
   const result=await view.api('/api/laya/sequence/'+r.id+'/report?compact=true');
   if(reportVersion!==version)return;
   $('laya-report-status').textContent=result.completed_comparisons+' overlapping crop comparisons. Visual suggestions require calibrated measurements to establish motion or variability.';
   for(const [key,label] of Object.entries(labels)){
    const term=document.createElement('dt'),count=document.createElement('dd');
    term.textContent=label;count.textContent=result.classification_counts[key];$('laya-findings').append(term,count);
   }
   const examples=$('laya-example-list');
   for(const example of result.example_comparisons){
    const row=document.createElement('li');
    const title=document.createElement('strong');
    title.textContent=labels[example.classification];
    const detail=document.createElement('span');
    detail.textContent=example.dates_utc.map(date=>date.slice(0,10)).join(' → ')+
     ' · '+(example.detector_group||'detector unavailable')+
     (example.baseline_days!=null?' · '+example.baseline_days.toFixed(1)+' days':'');
    row.append(title,detail);
    for(const [index,id] of example.exposure_ids.entries()){
     if(!view.job?.frames.some(f=>f.id===id&&f.status==='ready'))continue;
     const button=document.createElement('button');
     button.type='button';button.className='quiet';
     button.textContent=index?'Open later exposure':'Open earlier exposure';
     button.onclick=()=>view.selectExposure(id);
     row.append(button);
    }
    examples.append(row);
   }
   $('laya-examples').hidden=!examples.childElementCount;
   $('laya-guide').disabled=!result.completed_comparisons;
  }catch(error){
   if(reportVersion!==version)return;
   reportVersion=null;$('laya-report-status').textContent=error.message;
  }
 }
 report.addEventListener('toggle',()=>{if(report.open)showReport(view.sequence);});
 $('laya-guide').onclick=()=>window.dispatchEvent(new CustomEvent('explain-laya-report',{detail:{reviewId:activeId}}));
 function render(r){view.sequence={...r,jobId};$('laya-sequence-note').textContent=(r.ra!=null?'Review field '+r.ra.toFixed(5)+'°, '+r.dec.toFixed(5)+'° · ':'')+reviewProgress(r);$('laya-cancel').hidden=r.status!=='running';$('laya-coverage').href='/api/laya/sequence/'+r.id;$('laya-coverage').hidden=false;report.hidden=!r.batches_done;
  $('laya-report-download').href='/api/laya/sequence/'+r.id+'/report';
  if(report.open&&!report.hidden)showReport(r);
 }
 function save(){try{localStorage.setItem('parallax-laya-review',JSON.stringify({id:activeId,jobId}));}catch{}}
 async function poll(token){if(token!==epoch||!activeId)return;try{const r=await view.api('/api/laya/sequence/'+activeId+'?summary=true');if(token!==epoch)return;render(r);if(r.status==='running')timer=setTimeout(()=>poll(token),2000);}catch(e){if(token!==epoch)return;$('laya-sequence-note').textContent='Review connection interrupted: '+e.message+' Completed crops remain saved. Retrying status…';timer=setTimeout(()=>poll(token),6000);}}
 $('laya-sequence').onclick=async()=>{
  if(starting)return;if(!view.jobId){$('laya-sequence-note').textContent='Find observations first. Review starts when the archive has discovered exposures.';return;}
  starting=true;$('laya-sequence').disabled=true;
  try{const requestedJob=view.jobId,r=await view.api('/api/jobs/'+requestedJob+'/laya-sequence?summary=true',{method:'POST'});clearTimeout(timer);const token=++epoch;activeId=r.id;jobId=requestedJob;save();render(r);if(r.status==='running')timer=setTimeout(()=>poll(token),1000);}
  catch(e){$('laya-sequence-note').textContent=e.message+' No AI result was substituted.';}
  finally{starting=false;$('laya-sequence').disabled=false;}
 };
 $('laya-cancel').onclick=async()=>{if(!activeId)return;$('laya-cancel').disabled=true;try{await view.api('/api/laya/sequence/'+activeId+'/cancel',{method:'POST'});$('laya-sequence-note').textContent='Cancellation requested. Completed crops are saved.';clearTimeout(timer);timer=setTimeout(()=>poll(epoch),300);}catch(e){$('laya-sequence-note').textContent='Cancellation failed: '+e.message;}finally{$('laya-cancel').disabled=false;}};
 try{const saved=JSON.parse(localStorage.getItem('parallax-laya-review')||'null');if(/^laya-seq-[a-zA-Z0-9]+$/.test(saved?.id||'')){activeId=saved.id;jobId=saved.jobId;poll(epoch);}}catch{}
}
