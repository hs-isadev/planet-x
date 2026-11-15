const { chromium } = require('../frontend/node_modules/playwright');
const fs = require('node:fs');
const base = process.env.PLANET_X_TEST_ORIGIN || 'http://127.0.0.1:8001';
(async () => {
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
 const report = {at:new Date().toISOString(),base,errors:[]};
 const save = () => fs.writeFileSync('docs/calibrated-browser.json',JSON.stringify(report,null,2));
 page.on('pageerror',e=>report.errors.push(e.message));
 try {
  await page.goto(base+'/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
  const first='c9ebd523ba243452226933f4', second='ede7a7b40665bbfbf5ffcf7e';
  await page.waitForFunction(ids=>ids.every(id=>window.parallax?.observations?.frames?.some(f=>f.id===id)),[first,second],{timeout:90000});
  report.archive=await page.evaluate(async id=>{
   const view=window.parallax.observations;
   view.stop();view.position=view.frames.findIndex(f=>f.id===id);
   await view.show();
   return {discovered:view.job.discovered,loaded:view.job.ready,stage:view.job.stage,anchor:view.current().id};
  },first);
  await page.locator('summary').filter({hasText:'Measure a source'}).click();
  await page.locator('#click-action').selectOption('spectrum');
  const box=await page.locator('#science').boundingBox();
  await page.locator('#science').click({position:{x:box.width/2,y:box.height/2}});
  await page.locator('#candidate-inspector').waitFor({state:'visible',timeout:45000});
  await page.locator('#candidate-reference').selectOption(second);
  const [reply]=await Promise.all([
    page.waitForResponse(r=>r.url().includes('/calibrated-pair?'),{timeout:55000}),
    page.locator('#candidate-compare').click()
  ]);
  if(!reply.ok())throw Error(await reply.text());
  report.comparison=await reply.json();
  if(!['unassessed','measured'].includes(report.comparison.status))throw Error('Missing assessment state');
  await page.waitForFunction(()=>document.getElementById('candidate-comparison-status').textContent.includes('→'));
  report.comparisonText=await page.locator('#candidate-comparison-status').innerText();
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#evidence-export').click()]);
  const card=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  report.calibratedSpectrumPoints=card.candidate.measurements.filter(p=>p.status==='ok'&&p.calibration_url).length;
  report.exportedComparison=card.calibrated_comparison?.exposures?.map(f=>f.id);
  if(report.exportedComparison?.join(',')!==[first,second].join(','))throw Error('Evidence export lost the selected exposures');
  await page.locator('summary').filter({hasText:'SPHEREx observing perspective'}).click();
  await page.waitForFunction(()=>document.getElementById('observing-note').textContent.includes('Start and end positions'));
  report.spacecraft=await page.locator('#observing-note').innerText();
  await page.screenshot({path:'docs/calibrated-browser.png',fullPage:true});
  save();
 } catch(e) {
  report.failure=e.stack;save();throw e;
 } finally {await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
