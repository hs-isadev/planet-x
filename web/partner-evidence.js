const SOURCES = [
 ['NASA/IPAC SPHEREx archive','https://irsa.ipac.caltech.edu/Missions/spherex.html'],
 ['SPHEREx Python tutorials','https://caltech-ipac.github.io/irsa-tutorials/spherex/'],
 ['Gaia DR3 at MAST','https://archive.stsci.edu/missions-and-data/gaia'],
 ['Canadian Astronomy Data Centre','https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/'],
 ['CSA NEOSSat mission','https://www.asc-csa.gc.ca/eng/satellites/neossat/'],
 ['CSA NEOSSat dataset','https://data.asc-csa.gc.ca/dataset/neossat'],
 ['CSA NEOSSat tutorial','https://github.com/asc-csa/NEOSSAT_Tutorial'],
];

function external(link,label,url){
 link.textContent=label;link.href=url;link.target='_blank';link.rel='noopener noreferrer';
 return link;
}

export function installPartnerEvidence(view){
 const $=id=>document.getElementById(id);
 const panel=$('partner-evidence');
 let fieldKey,lookup=null,generation=0,pending=false;
 const sources=$('partner-sources');
 for(const [label,url] of SOURCES){
  const row=document.createElement('li');row.append(external(document.createElement('a'),label,url));sources.append(row);
 }
 function update(){
  const field=view.job;
  const valid=Number.isFinite(field?.ra)&&Number.isFinite(field?.dec);
  const key=valid?field.ra+','+field.dec+','+field.fov:null;
  if(fieldKey!==key){
   fieldKey=key;lookup=null;pending=false;generation++;
   $('partner-neossat-status').textContent='';
   $('partner-neossat-results').replaceChildren();
   $('partner-cadc').hidden=true;
  }
  $('partner-coordinates').textContent=valid?'ICRS '+field.ra.toFixed(5)+'°, '+field.dec.toFixed(5)+'° · '+field.fov+'′ field':'Search for a SPHEREx field to prepare partner checks.';
  $('partner-wiseview').hidden=!valid;
  $('partner-neossat').disabled=!valid||pending;
  $('partner-gaia').disabled=!view.current();
  $('partner-export').disabled=!valid||!view.current();
  if(valid){
   const args=new URLSearchParams({ra:field.ra,dec:field.dec,size:Math.min(2000,Math.round(field.fov*60)),band:2});
   external($('partner-wiseview'),'Open older WISE epochs in WiseView ↗','http://byw.tools/wiseview#'+args);
  }
 }
 panel.addEventListener('toggle',()=>{if(panel.open)update();});
 $('partner-gaia').onclick=()=>{
  const overlay=$('gaia-overlay');
  overlay.checked=true;overlay.dispatchEvent(new Event('change'));
  $('partner-gaia').textContent='Gaia DR3 overlay enabled';
 };
 $('partner-neossat').onclick=async()=>{
  const field=view.job,token=++generation,button=$('partner-neossat');
  if(!field||pending)return;
  pending=true;button.disabled=true;
  $('partner-neossat-status').textContent='Checking public NEOSSat footprints at CADC…';
  try{
   const result=await view.api('/api/partners/neossat?'+new URLSearchParams({ra:field.ra,dec:field.dec}));
   if(token!==generation)return;
   lookup=result;
   const list=$('partner-neossat-results');list.replaceChildren();
   for(const record of result.records){
    const row=document.createElement('li');
    const date=record.date_utc?.slice(0,10)||'Date unavailable';
    row.append(external(document.createElement('a'),date+' · '+record.observation_id+' · '+record.product_id,record.archive_url));
    list.append(row);
   }
   $('partner-neossat-status').textContent=result.status==='unavailable'
    ? 'CADC could not be reached. Use the direct query or retry. Coverage is unknown.'
    : result.records.length+' public NEOSSat products cover this point'+(result.capped?' (latest '+result.limit+')':'')+'. Coverage alone does not identify a source.';
   external($('partner-cadc'),'Open the exact query at CADC ↗',result.query_url).hidden=false;
  }catch(error){
   if(token===generation)$('partner-neossat-status').textContent='CADC lookup unavailable: '+error.message;
  }finally{if(token===generation){pending=false;button.disabled=false;}}
 };
 $('partner-export').onclick=()=>{
  const field=view.job,frame=view.current();
  if(!field||!frame)return;
  const evidence={field:{ra_deg:field.ra,dec_deg:field.dec,width_arcmin:field.fov},
   spherex:{id:frame.id,archive_url:frame.url,observed_utc:frame.date,detector:frame.detector,wavelength_um:frame.wavelength_um},
   gaia_dr3:{overlay_enabled:$('gaia-overlay').checked,reference_epoch:'J2016.0',source:SOURCES[2][1]},
   wiseview_url:$('partner-wiseview').href,neossat:lookup,
   interpretation:'Different missions, epochs, bandpasses, resolutions and footprints. Partner results are independent follow-up evidence.'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'}));
  view.download(url,'parallax-partner-evidence.json');setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 return update;
}
