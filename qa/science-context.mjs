import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:8000',e={date:new Date().toISOString(),errors:[],checks:{}};
const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader']});
const p=await b.newPage({viewport:{width:1440,height:1000}});
p.on('pageerror',err=>e.errors.push(err.message));
const save=()=>fs.writeFile('docs/science-context-validation.json',JSON.stringify(e,null,2));
try{
 await p.goto(base+'/?ra=133.79512916666667&dec=-7.245147222222222&fov=8&frame=118');
 await p.waitForFunction(()=>window.parallax?.observations.image&&parallax.observations.current()?.index===118,null,{timeout:30000});
 let id=await p.evaluate(()=>parallax.observations.jobId);e.job=id;
 e.checks.share=await p.evaluate(()=>({index:parallax.observations.current().index,detector:parallax.observations.current().detector,ra:parallax.observations.job.ra,dec:parallax.observations.job.dec,fov:parallax.observations.job.fov}));
 let r=await fetch(base+'/api/jobs/'+id+'/spectrum?x=.5&y=.5').then(async r=>({status:r.status,result:await r.json()}));
 e.checks.spectrum={status:r.status,total:r.result.points?.length,valid:r.result.points?.filter(p=>p.status==='ok').length,notes:r.result.notes};await save();
 for(let catalog of ['gaia','wise']){
  r=await fetch(base+'/api/jobs/'+id+'/catalog?frame=118&catalog='+catalog).then(async r=>({status:r.status,result:await r.json()}));
  e.checks[catalog]={status:r.status,markers:r.result.markers?.length,motionApplied:r.result.markers?.filter(p=>p.motion_applied).length,notes:r.result.notes,detail:r.result.detail};await save();
 }
 await p.locator('summary').filter({hasText:'Sky atlas'}).click();await p.click('#atlas-open');
 await p.waitForFunction(()=>!document.querySelector('#atlas-status').textContent.startsWith('Loading'),null,{timeout:30000});
 e.checks.atlas={status:await p.locator('#atlas-status').textContent(),canvasCount:await p.locator('#atlas canvas').count()};
 await p.screenshot({path:'docs/screenshots/final-science-first-desktop.png',fullPage:false});
 await p.setViewportSize({width:390,height:844});await p.waitForTimeout(500);await p.locator('#observations').scrollIntoViewIfNeeded();await p.waitForTimeout(200);
 e.checks.mobile={overflow:await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),canvas:await p.locator('#science').boundingBox()};
 await p.screenshot({path:'docs/screenshots/final-science-first-mobile.png',fullPage:false});await save();
 await p.setViewportSize({width:1440,height:1000});await p.click('#tour');let seen=new Set();
 for(let i=0;i<240;i++){
  let s=await p.evaluate(()=>({title:document.querySelector('#observation-title').textContent,playing:parallax.observations.playing,frames:parallax.observations.frames.length,done:document.querySelector('#tour').textContent==='Start guided tour'}));
  if(s.playing&&s.frames>=2&&!seen.has(s.title)){seen.add(s.title);console.log('TOUR',s.title,s.frames);}
  if(s.done){e.checks.tour={done:true,seen:[...seen]};break;}
  await p.waitForTimeout(1000);
 }
 if(!e.checks.tour)e.checks.tour={done:false,seen:[...seen]};
 await save();console.log('RESULT',JSON.stringify(e));
}catch(err){e.failure=String(err);await save();console.error(err);}
finally{await b.close();}
