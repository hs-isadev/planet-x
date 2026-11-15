const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
const base=process.env.PLANET_X_TEST_ORIGIN || 'http://127.0.0.1:8001';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const report={base,errors:[]};
 const save=()=>fs.writeFileSync('docs/image-and-stars-browser.json',JSON.stringify(report,null,2));
 page.on('pageerror',error=>report.errors.push(error.message));
 try{
  await page.goto(base+'/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
  await page.waitForFunction(()=>window.parallax?.observations?.image,{},{timeout:90000});
  report.initial=await page.locator('#image-zoom-readout').innerText();
  await page.locator('#image-zoom-in').click();
  const viewport=await page.locator('#science-frame').boundingBox();
  await page.mouse.move(viewport.x+viewport.width*.6,viewport.y+viewport.height*.5);
  await page.mouse.wheel(0,-160);
  await page.waitForFunction(()=>document.getElementById('image-zoom-readout').textContent.startsWith('1.9×'));
  const beforePan=await page.locator('#science').evaluate(el=>el.style.transform);
  await page.mouse.move(viewport.x+viewport.width*.50,viewport.y+viewport.height*.5);
  await page.mouse.down();
  await page.mouse.move(viewport.x+viewport.width*.62,viewport.y+viewport.height*.55,{steps:7});
  await page.mouse.up();
  report.panned=await page.locator('#science').evaluate((el,previous)=>el.style.transform!==previous,beforePan);
  await page.locator('summary').filter({hasText:'Measure a source'}).click();
  await page.locator('#click-action').selectOption('track');
  const sky={x:.48,y:.53};
  const rect=await page.locator('#science').boundingBox();
  await page.mouse.click(rect.x+rect.width*sky.x,rect.y+rect.height*sky.y);
  const mark=await page.evaluate(()=>window.parallax.observations.marks.at(-1));
  report.zoomedMark={expected:sky,measured:mark};
  if(!report.panned||!mark||Math.hypot(mark.x-sky.x,mark.y-sky.y)>.006)throw Error('Zoomed source click moved the sky coordinates');
  await page.locator('#image-zoom-out').click();
  await page.locator('#image-zoom-fit').click();
  report.fit=await page.locator('#image-zoom-readout').innerText();
  await page.locator('#image-wider-field').click();
  await page.waitForFunction(()=>window.parallax?.observations?.job?.fov===12&&window.parallax.observations.image,{},{timeout:120000});
  report.wider=await page.evaluate(()=>{const v=window.parallax.observations;return {fov:v.job.fov,ra:v.job.ra,dec:v.job.dec,ready:v.job.ready,discovered:v.job.discovered,url:v.current()?.url,readout:document.getElementById('image-zoom-readout').textContent};});
  await page.evaluate(async()=>{const id=window.parallax.observations.jobId;await fetch('/api/jobs/'+id+'/pause',{method:'POST'});});
  save();
  await page.locator('#observation-close').click();
  await page.waitForFunction(()=>window.parallax?.scene?.sky?.children[0]?.material?.map?.image?.data,{},{timeout:60000});
  report.stars=await page.evaluate(async()=>{
   const scene=window.parallax.scene, p=scene.sky.children[0], tex=p.material.map.image;
   const dt=[];let last=performance.now();
   await new Promise(done=>requestAnimationFrame(function tick(t){dt.push(t-last);last=t;if(dt.length<90)requestAnimationFrame(tick);else done();}));
   dt.sort((a,b)=>a-b);
   const at=(x,y)=>tex.data[4*(y*tex.width+x)+3];
   return {catalogStars:p.userData.catalogEntries.length,batchedObjects:scene.sky.children.length,
           drawCalls:scene.renderer.info.render.calls,p95Ms:dt[85],cornerAlpha:at(0,0),
           centerAlpha:at(32,32),haloAlpha:at(52,32)};
  });
  if(report.stars.cornerAlpha!==0||report.stars.centerAlpha<=report.stars.haloAlpha||report.stars.haloAlpha<=0||report.stars.batchedObjects!==1)throw Error('Star profile is not a soft circular point batch');
  await page.screenshot({path:'docs/round-stars-browser.png'});
  save();
 }catch(error){report.failure=error.stack;save();throw error;}finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
