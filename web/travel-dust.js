// Illustrated debris drawn as individual grains and irregular fragments.
// The camera's travel clock drives the field; manual dolly has no overlay.
export function travelDust(view){
 const canvas=document.createElement('canvas');
 canvas.className='travel-dust';
 canvas.setAttribute('aria-hidden','true');
 document.getElementById('stage').append(canvas);
 const ctx=canvas.getContext('2d');
 if(!ctx)return ()=>{};

 let seed=31021;
 function random(){
  seed=(Math.imul(seed,1664525)+1013904223)>>>0;
  return seed/4294967296;
 }
 const debris=Array.from({length:72},(_,i)=>({
  x:(random()-.5)*3.6,y:(random()-.5)*2.7,depth:random(),
  size:i<12?.65+random()*1.2:.15+random()*.38,
  spin:(random()-.5)*3,angle:random()*Math.PI*2,rock:i<12,
  shade:i%3===0?'#a99a86':i%3===1?'#b1b3b4':'#827c72',
  edges:Array.from({length:6},()=>.62+random()*.48),
 }));
 let wasVisible=false;
 return ()=>{
  const flight=view.flight;
  const visible=Boolean(!view.reduced&&view.journey&&flight?.earthTravel&&view.w>0&&view.h>0);
  if(visible!==wasVisible){canvas.style.opacity=visible?'1':'0';wasVisible=visible;}
  if(!visible)return;

  const w=view.w,h=view.h;
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  ctx.clearRect(0,0,w,h);
  const progress=Math.max(0,Math.min(1,(performance.now()-flight.start)/flight.duration));
  const envelope=Math.min(1,progress*9)*(1-Math.min(1,Math.max(0,(progress-.77)*4.35)));
  const focal=Math.min(w,h)*.47;
  for(const p of debris){
   const depth=(p.depth-progress*1.9+2)%1;
   const z=.14+depth*1.65;
   const x=w*.5+p.x*focal/z,y=h*.5+p.y*focal/z;
   if(x<0||x>w||y<0||y>h)continue;
   ctx.globalAlpha=envelope*Math.min(1,(1-depth)*6,depth*9)*(p.rock?.50:.35);
   ctx.fillStyle=p.shade;
   const size=Math.min(p.rock?5:1.8,p.size/z);
   ctx.beginPath();
   if(p.rock){
    for(let i=0;i<p.edges.length;i++){
     const a=p.angle+progress*p.spin+i*Math.PI/3,r=size*p.edges[i];
     const px=x+Math.cos(a)*r,py=y+Math.sin(a)*r;
     if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
    }
    ctx.closePath();
   }else ctx.arc(x,y,size,0,Math.PI*2);
   ctx.fill();
  }
  ctx.globalAlpha=1;
 };
}
