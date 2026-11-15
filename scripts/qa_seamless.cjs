const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const report={errors:[],flights:[]};page.on('pageerror',e=>report.errors.push(e.stack));
try{
 await page.goto(process.argv[2]||process.env.PARALLAX_QA_URL||'http://127.0.0.1:8001/');await page.waitForFunction(()=>window.parallax);
 await page.locator('#satellite-view-tab').click();await page.locator('#satellite-camera').waitFor({state:'visible'});
 assert.ok(await page.evaluate(()=>window.parallax.observations.jobId==null));report.emptySatellite=await page.locator('#satellite-detail').innerText();
 await page.waitForFunction(()=>document.querySelector('#satellite-catalog-count').textContent.includes('240'));
 await page.locator('#satellite-star-source').selectOption('expanded');await page.locator('#satellite-star-query').fill('Altair');await page.locator('#satellite-star-results button').first().click();
 report.target=await page.locator('#sky-target-name').innerText();
 await page.screenshot({path:'docs/seamless-satellite.png'});
 await page.locator('#universe-home').click();await page.waitForFunction(()=>window.parallax.scene?.mode==='stars'&&window.parallax.scene?.selected?.startsWith('hyg:'),null,{timeout:60000});
 report.context=await page.evaluate(()=>({id:window.parallax.scene.selected,count:window.parallax.scene.sky?.children[0]?.userData.catalogEntries?.length,sceneMessage:document.getElementById('scene-message').textContent,cachedSolar:!!window.parallax.scene.cachedFlightSolar}));
 await page.waitForFunction(()=>window.parallax.scene.sky?.children[0]?.userData.catalogEntries?.length>500,null,{timeout:15000});
 await page.locator('#satellite-view-tab').click();assert.equal(await page.locator('#sky-target-name').innerText(),report.target);await page.locator('#universe-home').click();
 await page.waitForFunction(()=>!document.getElementById('trace-earth').disabled,null,{timeout:15000});
 async function flight(label){
  const req=[];const record=r=>{if(r.url().includes('/api/')||r.url().includes('/assets/'))req.push(r.url());};page.on('request',record);
  await page.evaluate(()=>{window.flightSamples=[];const tick=()=>{const s=window.parallax.scene;if(s.journey)window.flightSamples.push({t:performance.now(),mode:s.mode,flight:!!s.flight,cover:!!document.querySelector('.travel-rebase'),pos:s.camera.position.toArray()});if(s.journey||!window.flightSamples.length)window.flightHandle=requestAnimationFrame(tick);};window.flightHandle=requestAnimationFrame(tick);});
  const start=Date.now();console.log('FLIGHT',label);await page.locator('#trace-earth').click();await page.waitForFunction(()=>window.parallax.scene.selected==='earth'&&!document.getElementById('journey-stay').hidden,null,{timeout:30000});
  page.off('request',record);const stats=await page.evaluate(()=>{cancelAnimationFrame(window.flightHandle);const s=window.parallax.scene,e=s.items.find(i=>i.data.id==='earth'),offset=s.camera.position.clone().sub(e.pos);return {samples:window.flightSamples,clearance:offset.length()/e.radius,lit:offset.normalize().dot(e.pos.clone().negate().normalize()),earthSky:!document.getElementById('earth-sky').hidden};});
  const finite=stats.samples.every(s=>s.pos.every(Number.isFinite));assert.ok(finite);assert.ok(stats.clearance>=6.49);assert.ok(stats.lit>.95);assert.equal(stats.earthSky,false);assert.ok(!stats.samples.some(s=>s.cover));
  report.flights.push({label,duration:Date.now()-start,...stats,samples:stats.samples.filter((s,i)=>i%10===0),sampleCount:stats.samples.length,idleFrames:stats.samples.slice(1,-1).filter(s=>!s.flight).length,requests:req});fs.writeFileSync('docs/seamless-browser.json',JSON.stringify(report,null,2));
  await page.screenshot({path:'docs/seamless-earth-'+label+'.png'});await page.locator('#journey-stay').click();console.log('ARRIVED',label);
 }
 await flight('star');
 await page.evaluate(()=>window.parallax.select('mars',true));console.log('SELECTED MARS');await page.waitForFunction(()=>!document.getElementById('trace-earth').disabled,null,{timeout:20000});await flight('mars');
 await page.locator('#guide-toggle').click();report.guide=await page.locator('#guide-status').innerText();await page.locator('#guide-question').fill('What can I do in this view?');await page.locator('#guide-send').click();await page.waitForFunction(()=>!document.getElementById('guide-send').disabled);report.guideNoKey=await page.locator('#guide-status').innerText();await page.locator('#guide-close').click();
 await page.setViewportSize({width:390,height:844});await page.locator('#satellite-view-tab').click();report.mobile=await page.evaluate(()=>({width:document.documentElement.scrollWidth,inner:innerWidth,nav:document.querySelector('nav').getBoundingClientRect().toJSON()}));await page.screenshot({path:'docs/seamless-mobile.png'});
 assert.deepEqual(report.errors,[]);
}catch(e){report.failure=e.stack;report.diagnostic=await page.evaluate(()=>({toast:document.getElementById('toast').textContent,journey:window.parallax?.scene?.journey,flight:!!window.parallax?.scene?.flight,selected:window.parallax?.scene?.selected,mode:window.parallax?.scene?.mode,panelHidden:document.getElementById('journey-panel').hidden,title:document.getElementById('journey-title').textContent,note:document.getElementById('journey-note').textContent,ready:window.parallax?.scene?.readyJourneyContext}));await page.screenshot({path:'docs/seamless-failure.png'});throw e;}finally{fs.writeFileSync('docs/seamless-browser.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
