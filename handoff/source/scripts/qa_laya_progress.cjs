const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const report={at:new Date().toISOString(),stages:[],errors:[]};
 const save=()=>fs.writeFileSync('docs/laya-browser-progress.json',JSON.stringify(report,null,2));
 page.on('pageerror',e=>report.errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8000/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
  await page.waitForFunction(()=>window.parallax?.observations?.image,undefined,{timeout:90000});
  await page.locator('summary').filter({hasText:'Experimental AI review'}).click();
  await page.locator('#laya-sequence').click();
  const link=page.locator('#laya-coverage');await link.waitFor({state:'visible'});
  const url=await link.getAttribute('href');
  const get=()=>page.evaluate(async u=>await(await fetch(u)).json(),url+'?summary=true');
  let r=await get();const previous=r.batches_done;
  const until=async minimum=>{
   const start=Date.now();
   while(Date.now()-start<250000){
    r=await get();
    if(report.stages.at(-1)?.stage!==r.stage||report.stages.at(-1)?.reviewed!==r.reviewed){report.stages.push({stage:r.stage,status:r.status,loaded:r.loaded,prepared:r.prepared,reviewed:r.reviewed,batches:r.batches_done,lastProgress:r.last_progress_at,message:r.message});save();}
    if(r.batches_done>=minimum&&r.reviewed>0)return;
    if(r.status!=='running')throw Error(r.message);
    await page.waitForTimeout(600);
   }
   throw Error('Timed out waiting for new Laya crop receipts');
  };
  await until(previous+4);
  report.live=await page.locator('#laya-sequence-note').innerText();
  await page.screenshot({path:'docs/laya-browser-progress.png',fullPage:true});
  const cancel=async()=>{
   const started=Date.now();await page.locator('#laya-cancel').click();
   await page.waitForFunction(()=>document.getElementById('laya-sequence-note').textContent.includes('cancelled'),undefined,{timeout:15000});
   const receipt=await get();return {latency_ms:Date.now()-started,status:receipt.status,reviewed:receipt.reviewed,batches:receipt.batches_done,progress:await page.locator('#laya-sequence-note').innerText()};
  };
  report.cancelled=await cancel();save();
  const [restart]=await Promise.all([page.waitForResponse(res=>res.url().includes('/laya-sequence?summary=true')&&res.request().method()==='POST'),page.locator('#laya-sequence').click()]);
  if(!restart.ok())throw Error(await restart.text());
  await until(report.cancelled.batches+2);
  report.resumed=await cancel();
  const full=await page.evaluate(async u=>await(await fetch(u)).json(),url);
  report.exposureIdsUnique=new Set(full.reviewed_ids).size===full.reviewed;
  report.cropKeysUnique=new Set(full.batches.map(b=>b.key)).size===full.batches.length;
  report.model=await page.evaluate(async()=>await(await fetch('/api/laya/status')).json());
  await page.evaluate(async()=>await fetch('/api/jobs/'+window.parallax.observations.jobId+'/pause',{method:'POST'}));
  save();
 }catch(e){report.failure=e.stack;save();throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
