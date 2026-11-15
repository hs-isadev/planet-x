const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/');await page.waitForSelector('#presets button');
 const result={at:new Date().toISOString(),targets:[],errors};
 for(const name of ['Barnard’s Star','Epsilon Indi B','WISE 0855','RW Aurigae','R Draconis']){
  if(!await page.locator('#search-panel').isVisible())await page.locator('#search-toggle').click();
  await page.locator('#presets button').filter({hasText:name}).click();
  await page.waitForFunction(()=>window.parallax?.observations?.job?.frames?.length>0,{},{timeout:120000});
  await page.waitForFunction(()=>window.parallax?.observations?.job?.ready>=2||['error','empty'].includes(window.parallax?.observations?.job?.status),{},{timeout:120000});
  const snap=await page.evaluate(()=>{const v=window.parallax.observations,j=v.job;return {jobId:v.jobId,ra:j.ra,dec:j.dec,status:j.status,discovered:j.frames.length,loaded:j.ready,failed:j.failed,pending:j.pending,chronological:v.frames.every((f,i,a)=>!i||f.mjd>=a[i-1].mjd),all_loaded:v.frames.length===j.ready,dates:v.frames.map(f=>f.date),frame_count:v.frames.length}});
  await page.locator('#enhance').check();await page.waitForTimeout(300);const on=await page.locator('#enhance-note').innerText();await page.locator('#enhance').uncheck();
  await page.locator('#speed').selectOption('50');await page.locator('#play').click();const indices=[];
  for(let i=0;i<12;i++){await page.waitForTimeout(100);indices.push(await page.evaluate(()=>window.parallax.observations.current()?.index));}
  await page.locator('#play').click();
  const job=await page.evaluate(async()=>await(await fetch('/api/jobs/'+window.parallax.observations.jobId)).json());
  snap.errors=job.frames.filter(f=>f.status==='error').map(f=>({id:f.id,error:f.error,detail:f.detail}));
  snap.name=name;snap.playback_samples=indices;snap.noise_note=on;
  snap.comparable_preliminary=job.frames.filter(a=>a.status==='ready'&&job.frames.some(b=>b.status==='ready'&&a.id!==b.id&&a.detector===b.detector&&a.release===b.release&&Math.abs(a.mjd-b.mjd)>=1&&a.wavelength_um!=null&&b.wavelength_um!=null&&Math.abs(a.wavelength_um-b.wavelength_um)<=.025)).length;
  snap.scientifically_validated=0;snap.reviewed=0;
  result.targets.push(snap);fs.writeFileSync('docs/pipeline-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify({...snap,dates:undefined,errors:snap.errors.slice(0,2)}));
  await page.evaluate(async()=>await fetch('/api/jobs/'+window.parallax.observations.jobId+'/pause',{method:'POST'}));
 }
 await page.screenshot({path:'docs/pipeline-browser.png',fullPage:true});
 await browser.close();
})().catch(e=>{console.error(e.stack);process.exit(1)});
