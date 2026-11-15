export function chronological(frames){
 return [...frames].sort((a,b)=>(Number(a.mjd)-Number(b.mjd))||String(a.date||'').localeCompare(String(b.date||''))||(a.index-b.index));
}

export function sequenceSummary(job,shown,filter='all'){
 const ready=job.frames.filter(f=>f.status==='ready').length;
 const pending=job.frames.length-ready-job.frames.filter(f=>f.status==='error').length;
 const failed=job.frames.filter(f=>f.status==='error').length;
 return (filter==='all'?'Full chronological sequence: ':'Filtered chronological sequence: ')+shown+' playable / '+job.frames.length+' discovered exposures. '+
  (filter!=='all'?ready+' loaded across all detectors. ':'')+
  (pending?pending+' still loading. ':'')+(failed?failed+' unavailable (marked in the timeline). ':'')+
  'All available exposures are included in time order. Use similar wavelengths for motion comparisons; brightness changes alone do not establish motion.';
}

export function sameCalibrationRelease(first, second){
 return Boolean(first && second && (first===second || (first==='dr1' && second==='qr3') || (first==='qr3' && second==='dr1')));
}
