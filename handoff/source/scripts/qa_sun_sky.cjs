const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('node:fs');
const base=process.env.PLANET_X_TEST_ORIGIN||'http://127.0.0.1:8001';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const report={base,errors:[]};
 const save=()=>fs.writeFileSync('docs/sun-sky-browser.json',JSON.stringify(report,null,2));
 page.on('pageerror',e=>report.errors.push(e.message));
 try{
  await page.goto(base+'/?ra=133.79512916666667&dec=-7.245147222222222&fov=8');
  await page.waitForFunction(()=>window.parallax?.observations?.image,{},{timeout:90000});
  await page.locator('#sun-sky-tab').click();
  await page.locator('#sun-sky-panel').waitFor({state:'visible',timeout:60000});
  const canvas=page.locator('#scene canvas');
  await page.waitForFunction(()=>window.parallax?.scene?.sky?.children[0]?.userData?.catalogEntries?.length);
  const measure=()=>page.evaluate(()=>{const s=window.parallax.scene;
    return {center:s.sunSkyDirection(),distanceAU:s.camera.position.distanceTo(s.sunSky.origin),
      planetaryContentVisible:s.content.visible,freeCamera:s.controls.enabled};});
  report.before=await measure();
  const rect=await canvas.boundingBox();
  const cx=rect.x+rect.width*.5,cy=rect.y+rect.height*.5;
  await page.mouse.move(cx,cy);await page.mouse.down();await page.mouse.move(cx+12,cy-8,{steps:5});await page.mouse.up();
  report.after=await measure();
  if(Math.abs(report.after.distanceAU-1)>1e-10||report.after.planetaryContentVisible||report.after.freeCamera)
   throw Error('Sun-anchored constraints failed');
  if(Math.hypot(report.before.center.ra-report.after.center.ra,report.before.center.dec-report.after.center.dec)<.1)
   throw Error('Dragging did not change the sky direction');
  const x=cx+12,y=cy+17;
  report.clickedDirection=await page.evaluate(({x,y})=>{
   const s=window.parallax.scene,r=s.renderer.domElement.getBoundingClientRect();
   return s.sunSkyDirection((x-r.left)*2/r.width-1,1-(y-r.top)*2/r.height);
  },{x,y});
  await page.screenshot({path:'docs/sun-sky-browser.png'});
  const [request]=await Promise.all([
   page.waitForRequest(r=>r.url()===base+'/api/search'&&r.method()==='POST'),
   page.mouse.click(x,y,{button:'right'})
  ]);
  report.search=request.postDataJSON();
  if(Math.hypot(+report.search.ra-report.clickedDirection.ra,+report.search.dec-report.clickedDirection.dec)>1e-6)
   throw Error('The archive query did not use the clicked sky direction');
  save();
  await page.waitForFunction(()=>{const v=window.parallax?.observations;return v?.image||['error','empty'].includes(v?.job?.status);},{},{timeout:150000});
  report.archive=await page.evaluate(()=>{const v=window.parallax.observations,j=v.job;
   return {ra:j.ra,dec:j.dec,status:j.status,discovered:j.discovered,loaded:j.ready,source:v.current()?.url,image:!!v.image,message:j.message};});
  await page.evaluate(async()=>{const id=window.parallax.observations.jobId;await fetch('/api/jobs/'+id+'/pause',{method:'POST'});});
  await page.locator('#sun-sky-tab').click();
  await page.locator('#sun-sky-panel').waitFor({state:'visible'});
  report.returned=await measure();
  await page.locator('#universe-home').click();
  await page.waitForFunction(()=>!window.parallax?.scene?.sunSky);
  report.exited=true;
  save();
 }catch(e){report.failure=e.stack;save();throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
