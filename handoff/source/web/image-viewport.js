const $ = id => document.getElementById(id);
const clamp = (value, low, high) => Math.min(high,Math.max(low,value));

export function installImageViewport(view) {
 const canvas=$('science'), frame=$('science-frame');
 let zoom=1, panX=0, panY=0, drag=null, dragged=false;

 function update() {
  const limit=(zoom-1)/2;
  panX=clamp(panX,-limit,limit);
  panY=clamp(panY,-limit,limit);
  canvas.style.transform=zoom===1?'':'translate('+panX*100+'%, '+panY*100+'%) scale('+zoom+')';
  canvas.style.cursor=drag?.moved?'grabbing':zoom>1?'grab':'';
  const loaded=Boolean(view.image||view.computed);
  const fov=Number(view.job?.fov);
  $('image-zoom-out').disabled=!loaded||zoom<=1;
  $('image-zoom-in').disabled=!loaded||zoom>=4;
  $('image-zoom-fit').disabled=!loaded||zoom===1;
  $('image-wider-field').disabled=!loaded||!Number.isFinite(fov)||fov>=20;
  $('image-zoom-readout').textContent=Number.isFinite(fov)
    ? zoom.toFixed(1)+'× · '+(fov/zoom).toFixed(1)+'′ visible of '+fov+'′ loaded'
    : '1.0×';
  $('image-scale').textContent=Number.isFinite(fov)?Math.round(fov*60/(6*zoom))+'″':'';
 }

 function setZoom(next,x=.5,y=.5) {
  const value=clamp(next,1,4), factor=value/zoom;
  panX=x-.5-(x-.5-panX)*factor;
  panY=y-.5-(y-.5-panY)*factor;
  zoom=value;
  $('marker-tooltip').hidden=true;
  update();
 }

 $('image-zoom-in').onclick=()=>setZoom(zoom*1.4);
 $('image-zoom-out').onclick=()=>setZoom(zoom/1.4);
 $('image-zoom-fit').onclick=()=>setZoom(1);
 $('image-wider-field').onclick=async()=>{
  const job=view.job;
  if(!job||job.fov>=20)return;
  const fov=Math.min(20,Math.ceil(job.fov*1.5));
  const title=$('observation-title').textContent;
  $('ra').value=String(job.ra);
  $('dec').value=String(job.dec);
  $('fov').value=String(fov);
  $('fov').oninput?.();
  await view.search(title,null,job.source==='cloud'?null:view.current()?.id);
 };

 frame.addEventListener('wheel',e=>{
  if(!view.image&&!view.computed)return;
  if(e.deltaY>0&&zoom===1&&!e.ctrlKey)return;
  e.preventDefault();
  const rect=frame.getBoundingClientRect();
  if(!rect.width||!rect.height)return;
  setZoom(zoom*Math.exp(clamp(-e.deltaY*.0018,-.42,.42)),(e.clientX-rect.left)/rect.width,(e.clientY-rect.top)/rect.height);
 },{passive:false});
 canvas.addEventListener('pointerdown',e=>{
  dragged=false;
  if(zoom<=1||e.button!==0)return;
  drag={id:e.pointerId,x:e.clientX,y:e.clientY,panX,panY,moved:false};
 });
 canvas.addEventListener('pointermove',e=>{
  if(!drag||drag.id!==e.pointerId)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(!drag.moved&&Math.hypot(dx,dy)<4)return;
  if(!drag.moved)canvas.setPointerCapture(e.pointerId);
  drag.moved=dragged=true;
  const rect=frame.getBoundingClientRect();
  panX=drag.panX+dx/rect.width;
  panY=drag.panY+dy/rect.height;
  $('marker-tooltip').hidden=true;
  update();
 });
 function endDrag(e){
  if(drag?.id!==e.pointerId)return;
  drag=null;
  update();
 }
 canvas.addEventListener('pointerup',endDrag);
 canvas.addEventListener('pointercancel',endDrag);
 canvas.addEventListener('lostpointercapture',endDrag);
 canvas.addEventListener('click',e=>{
  if(dragged){dragged=false;e.preventDefault();e.stopImmediatePropagation();}
 },true);
 const draw=view.draw.bind(view);
 view.draw=function(...args){draw(...args);update();};
 const reset=view.reset.bind(view);
 view.reset=function(...args){zoom=1;panX=panY=0;drag=null;dragged=false;return reset(...args);};
 update();
}
