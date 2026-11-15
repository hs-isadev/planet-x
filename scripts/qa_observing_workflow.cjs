const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
const base='http://127.0.0.1:8000';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
 const sceneOnly=process.argv.includes('--scene-only'), scienceOnly=process.argv.includes('--science-only');
 const report={at:new Date().toISOString(),errors:[]};
 const save=()=>fs.writeFileSync(sceneOnly?'docs/scene-workflow.json':'docs/observing-workflow.json',JSON.stringify(report,null,2));
 page.on('pageerror',e=>report.errors.push(e.message));
 try{
  if(sceneOnly)await page.goto(base);
  else {
  await page.goto(base+'/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
  await page.waitForFunction(()=>window.parallax?.observations?.image,undefined,{timeout:90000});
  const readout=await page.locator('#frame-readout').innerText();
  await page.locator('#enhance').check();
  await page.waitForFunction(()=>window.parallax?.observations?.loadedURL?.includes('enhanced=true'));
  await page.locator('#enhance').uncheck();
  await page.waitForFunction(()=>!window.parallax?.observations?.loadedURL?.includes('enhanced=true'));
  report.playback=await page.evaluate(async()=>{
   const view=window.parallax.observations;
   const raw=view.show.bind(view);const displayed=[];
   view.show=async(...args)=>{await raw(...args);const f=view.current();if(f&&view.image)displayed.push({index:f.index,mjd:f.mjd,date:document.getElementById('frame-readout').textContent,url:view.loadedURL});};
   view.position=0;view.togglePlay();
   const t=performance.now();while(displayed.length<12&&performance.now()-t<15000)await new Promise(r=>setTimeout(r,50));
   view.stop();view.show=raw;
   return {displayed,ordered:displayed.every((f,i)=>!i||f.mjd>=displayed[i-1].mjd),datesMatch:displayed.every(f=>f.url?.includes('/frames/'+f.index+'.png')&&!f.date.includes('Buffering'))};
  });
  report.initial=readout;save();
  await page.locator('summary').filter({hasText:'SPHEREx observing perspective'}).click();
  await page.waitForFunction(()=>document.getElementById('observing-note').textContent.includes('arcmin patch'));
  report.observingView=await page.locator('#observing-note').innerText();
  await page.locator('summary').filter({hasText:'Measure a source'}).click();
  await page.locator('#click-action').selectOption('spectrum');
  await page.locator('#science').click({position:{x:180,y:180}});
  await page.locator('#candidate-inspector').waitFor({state:'visible',timeout:45000});
  await page.locator('#spectrum-features').check();
  const options=await page.locator('#spectrum-date-a option').allTextContents();
  if(options.length>2){await page.locator('#spectrum-date-a').selectOption({index:1});await page.locator('#spectrum-date-b').selectOption({index:2});}
  await page.locator('#candidate-class').selectOption('uncertain');
  const [dl]=await Promise.all([page.waitForEvent('download'),page.locator('#evidence-export').click()]);
  const card=JSON.parse(fs.readFileSync(await dl.path(),'utf8'));
  report.spectrum={allDates:options.length-1,measurements:card.candidate.measurements.length,usable:card.candidate.measurements.filter(p=>p.status==='ok').length,coverage:await page.locator('#spectrum-coverage').innerText(),evidenceExport:dl.suggestedFilename(),observations:card.observations.length};
  save();
  if(scienceOnly){
   await page.locator('#candidate-lightcurve').click();
   await page.waitForFunction(()=>{const t=document.getElementById('lightcurve-note').textContent;return t.length>0&&!t.startsWith('Measuring');},undefined,{timeout:45000});
   report.brightnessHistory=await page.locator('#lightcurve-note').innerText();
   save();
  }
  await page.screenshot({path:'docs/observing-workflow.png',fullPage:true});
  if(scienceOnly)return;
  await page.evaluate(async()=>{const id=window.parallax.observations.jobId;await fetch('/api/jobs/'+id+'/pause',{method:'POST'});});
  }
  await page.locator('#observation-close').click();
  await page.waitForFunction(()=>!window.parallax?.scene?.loading&&window.parallax?.scene?.sky?.children[0]?.userData.catalogEntries?.length>0,undefined,{timeout:60000});
  const picks=await page.evaluate(()=>{
   const s=window.parallax.scene,points=s.sky.children[0],array=points.geometry.attributes.position.array;
   const rect=s.renderer.domElement.getBoundingClientRect();
   const v=s.camera.position.clone();const pick=[];
   for(let i=0;i<points.userData.catalogEntries.length;i++){
    v.fromArray(array,i*3).applyMatrix4(points.matrixWorld).project(s.camera);
    if(v.z>0&&v.z<1&&Math.abs(v.x)<.57&&Math.abs(v.y)<.48){
     const x=rect.left+(v.x*.5+.5)*rect.width,y=rect.top+(-v.y*.5+.5)*rect.height;
     if(document.elementFromPoint(x,y)===s.renderer.domElement)pick.push({x,y,id:points.userData.catalogEntries[i].id});
    }
   }
   return pick;
  });
  if(!picks.length)throw Error('No selectable catalog point in the visible viewport');
  await page.mouse.click(picks[0].x,picks[0].y);
  await page.waitForFunction(()=>window.parallax?.scene?.selected?.startsWith('host:'),undefined,{timeout:10000});
  report.selectedCatalog=await page.evaluate(()=>window.parallax.scene.selected);save();
  await page.locator('#approach').click();
  await page.waitForFunction(()=>window.parallax?.scene?.local?.planets?.length>0,undefined,{timeout:45000});
  report.systemPlanets=await page.evaluate(()=>window.parallax.scene.local.planets.length);save();
  await page.waitForFunction(()=>!window.parallax.scene.flight,undefined,{timeout:20000});
  const zoomDistance=()=>page.evaluate(()=>{const s=window.parallax.scene;return s.camera.position.distanceTo(s.controls.target);});
  const beforeZoom=await zoomDistance();
  const canvas=await page.locator('#scene canvas').boundingBox();
  await page.mouse.move(canvas.x+canvas.width*.65,canvas.y+canvas.height*.45);await page.mouse.wheel(0,-150);
  await page.waitForTimeout(600);const zoomed=await zoomDistance();await page.mouse.wheel(0,150);await page.waitForTimeout(600);
  report.zoom={before:beforeZoom,closer:zoomed,after:await zoomDistance(),planets:await page.evaluate(()=>window.parallax.scene.local?.planets?.length)};save();
  const start=Date.now();await page.locator('#trace-earth').click();
  await page.waitForFunction(()=>+document.querySelector('canvas.travel-dust').style.opacity>.1,undefined,{timeout:45000});
  report.travelDustOpacity=await page.locator('canvas.travel-dust').evaluate(el=>+el.style.opacity);save();
  await page.waitForFunction(()=>window.parallax.scene.selected==='earth'&&!document.getElementById('journey-stay').hidden,undefined,{timeout:90000});
  report.earth={arrivalMs:Date.now()-start,stay:await page.locator('#journey-stay').isVisible(),return:await page.locator('#journey-exit').isVisible(),dustVisible:true};save();
  await page.locator('#journey-stay').click();
  await page.waitForFunction(()=>!window.parallax.scene.journey&&window.parallax.scene.selected==='earth');
  await page.locator('#return-object').click();
  await page.waitForFunction(()=>!window.parallax.scene.journey&&window.parallax.scene.selected.startsWith('host:'),undefined,{timeout:90000});
  report.roundTrip=true;save();
  await page.locator('#solar-tab').click();
  await page.waitForFunction(()=>{const s=window.parallax.scene;return s.mode==='solar'&&!s.loading&&s.items.some(x=>x.data.id==='earth');},undefined,{timeout:45000});
  report.solarNavigation=true;save();
 }catch(e){report.failure=e.stack;save();throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
