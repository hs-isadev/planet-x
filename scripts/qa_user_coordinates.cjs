const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
(async()=>{
 const b=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const p=await b.newPage({viewport:{width:1440,height:1000}});const report={at:new Date().toISOString()};
 try{
  await p.goto('http://127.0.0.1:8000/');
  await p.locator('#ra').fill('10h24m22.3876s');
  await p.locator('#dec').fill('-41d38m40.7879s');
  await p.locator('#fov').fill('4');
  await p.locator('#coordinate-form button[type=submit]').click();
  await p.waitForFunction(()=>{const v=window.parallax?.observations;return v?.image||['error','empty'].includes(v?.job?.status);},undefined,{timeout:150000});
  Object.assign(report,await p.evaluate(()=>{const v=window.parallax.observations,j=v.job;return {ra:j.ra,dec:j.dec,fov:j.fov,status:j.status,discovered:j.discovered,loaded:j.loaded,failed:j.failed,firstFrame:v.current(),readout:document.getElementById('frame-readout').textContent,loadedURL:v.loadedURL,message:j.message,detail:j.detail}}));
  await p.evaluate(async()=>await fetch('/api/jobs/'+window.parallax.observations.jobId+'/pause',{method:'POST'}));
 }catch(e){report.error=e.message;throw e;}
 finally{fs.writeFileSync('docs/user-coordinate-workflow.json',JSON.stringify(report,null,2));await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});
