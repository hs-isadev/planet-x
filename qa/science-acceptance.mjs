import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:8000',e={date:new Date().toISOString(),errors:[],checks:{},presets:[]};
const save=()=>fs.writeFile('docs/science-acceptance.json',JSON.stringify(e,null,2));
const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader']});
const p=await b.newPage({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});
p.on('pageerror',err=>e.errors.push(err.message));
try{
 await p.goto(base);await p.waitForFunction(()=>window.parallax?.observations);
 e.checks.viewerFirst=await p.evaluate(()=>({observationsVisible:!document.querySelector('#observations').hidden,sceneUninitialized:parallax.scene===null,presetCount:document.querySelectorAll('#presets button').length,overflow:document.documentElement.scrollWidth>innerWidth}));
 await p.screenshot({path:'docs/screenshots/final-science-first-desktop.png'});
 const names=await p.locator('#presets button').allTextContents();
 for(let i=0;i<5;i++){
  let t=Date.now();await p.locator('#presets button').nth(i).click();await p.waitForFunction(()=>parallax.observations.image&&parallax.observations.frames.length>=2,null,{timeout:180000});
  let x=await p.evaluate(()=>{let v=parallax.observations;return {title:document.querySelector('#observation-title').textContent,ready:v.job.ready,total:v.job.frames.length,displayed:v.frames.length,group:document.querySelector('#group').value,dates:v.frames.map(f=>f.mjd),chronological:v.frames.every((f,i,a)=>!i||f.mjd>=a[i-1].mjd),firstId:v.current().id,firstDate:v.current().date,source:v.job.source||'TAP'}});x.firstSequenceMs=Date.now()-t;e.presets.push(x);await save();
  await p.locator('#play').click();await p.waitForFunction(id=>parallax.observations.current()?.id!==id,x.firstId,{timeout:10000});x.playerAdvanced=true;await p.evaluate(()=>parallax.observations.stop());
  if(i===0){
   e.barnardJob=await p.evaluate(()=>parallax.observations.jobId);
   e.motionTask={status:'not started during first-frame timing'};
   await p.screenshot({path:'docs/screenshots/final-barnard-sequence.png'});
  }
  await p.evaluate(async()=>{await fetch('/api/jobs/'+parallax.observations.jobId+'/pause',{method:'POST'});});
 }
 await p.locator('#presets button').nth(2).click();e.analysisJob=await p.evaluate(()=>parallax.observations.jobId);
 await p.waitForFunction(()=>parallax.observations.groups.some(g=>g.frames.length>=2),null,{timeout:180000});
 let group=await p.evaluate(()=>{let v=parallax.observations;return v.groups.filter(g=>g.frames.length>=2&&g.detector===6).sort((a,b)=>b.frames.length-a.frames.length)[0].id;});
 await p.selectOption('#group',group);await p.waitForFunction(()=>parallax.observations.image);
 await p.locator('summary').filter({hasText:'Compare & stack'}).click();
 for(let mode of ['subtract','add','stack']){
  await p.selectOption('#compare-mode',mode);await p.evaluate(()=>{parallax.observations.computed=null;});await p.click('#apply-compute');await p.waitForFunction(()=>parallax.observations.computed||document.querySelector('#computed-note').textContent,null,{timeout:90000});e.checks[mode]=await p.evaluate(()=>({image:!!parallax.observations.computed,note:document.querySelector('#computed-note').textContent}));await save();
 }
 await p.selectOption('#compare-mode','single');await p.evaluate(()=>parallax.observations.clearComputed());await p.evaluate(()=>parallax.observations.show());
 let resp=await fetch(base+'/api/jobs/'+e.analysisJob+'/spectrum?x=.5&y=.5').then(async r=>({status:r.status,result:await r.json()}));e.checks.spectrum={status:resp.status,points:resp.result.points?.length,valid:resp.result.points?.filter(x=>x.status==='ok').length,notes:resp.result.notes};
 e.checks.prediction=await fetch(base+'/api/jobs/'+e.barnardJob+'/predicted-target').then(r=>r.json());
 await p.click('#copy-link');let link=p.url();e.checks.share={url:link};
 const q=await b.newPage();await q.goto(link);await q.waitForFunction(()=>window.parallax?.observations.image,null,{timeout:120000});e.checks.share.reproduced=await q.evaluate(()=>({ra:parallax.observations.job.ra,dec:parallax.observations.job.dec,fov:parallax.observations.job.fov,index:parallax.observations.current().index}));await q.close();
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:'docs/screenshots/final-science-first-mobile.png',fullPage:true});e.checks.mobile={overflow:await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
 await save();console.log(JSON.stringify({presets:e.presets,checks:Object.keys(e.checks),errors:e.errors}));
}catch(err){e.failure=String(err);await p.screenshot({path:'docs/screenshots/final-science-failure.png',fullPage:true});await save();console.error(err);}
finally{await b.close();}
