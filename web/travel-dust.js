// Illustrative travel particles: never catalog stars or observed image pixels.
export function travelDust(view){
 const canvas=document.createElement('canvas');canvas.className='travel-dust';canvas.setAttribute('aria-hidden','true');document.getElementById('stage').append(canvas);
 const ctx=canvas.getContext('2d'),particles=Array.from({length:150},(_,j)=>({angle:j*2.399963,depth:(j*.6180339)%1,size:.5+(j%5)*.22}));
 let previous=performance.now(),phase=0,opacity=0;
 const update=()=>{let now=performance.now(),dt=Math.min(.05,(now-previous)/1000);previous=now;
  const moving=!view.reduced&&(view.journey&&view.flight||Math.abs(view.zoomImpulse||0)>.015);
  opacity+=(Number(moving)-opacity)*Math.min(1,dt*5);canvas.style.opacity=opacity.toFixed(3);
  if(opacity<.005)return;const w=view.w,h=view.h;if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  ctx.clearRect(0,0,w,h);phase+=dt*(view.journey ? .65 : .23);
  for(const p of particles){let z=(p.depth+phase)%1,r=(.05+z*z)*Math.hypot(w,h)*.65,dx=Math.cos(p.angle),dy=Math.sin(p.angle),x=w/2+dx*r,y=h/2+dy*r;
   let length=(view.journey?50:12)*z*z;ctx.strokeStyle=`rgba(205,193,175,${z*.34})`;ctx.lineWidth=p.size;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+dx*length,y+dy*length);ctx.stroke();}
 };
 return update;
}
