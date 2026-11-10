const $=id=>document.getElementById(id);
export async function earthSky(context,name,api){
 window.skyCleanup?.();let token=Symbol();window.skyToken=token;
 $('earth-sky').hidden=false;$('sky-constellation').textContent=context.constellation;$('sky-direction').textContent=name+' · RA '+context.ra.toFixed(4)+'° · Dec '+context.dec.toFixed(4)+'°';
 let common='Computed sky chart from a virtual observer at '+context.observer_latitude.toFixed(1)+'°, '+context.observer_longitude.toFixed(1)+'°. Atmosphere omitted. ';
 $('sky-data-note').textContent=common+'Loading the Gaia star field…';let stars=[];
 function draw(){let canvas=$('earth-sky-canvas'),r=canvas.getBoundingClientRect();if(!r.width||!r.height)return;let dpr=Math.min(devicePixelRatio,2);canvas.width=r.width*dpr;canvas.height=r.height*dpr;let ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);let w=r.width,h=r.height;ctx.fillStyle='#05080d';ctx.fillRect(0,0,w,h);let ra=context.ra*Math.PI/180,dec=context.dec*Math.PI/180,f=Math.min(w,h)*1.5;
  for(let s of stars){let a=s.ra*Math.PI/180,d=s.dec*Math.PI/180,den=Math.sin(dec)*Math.sin(d)+Math.cos(dec)*Math.cos(d)*Math.cos(a-ra);if(den<=0)continue;let x=w/2-f*Math.cos(d)*Math.sin(a-ra)/den,y=h*.45-f*(Math.cos(dec)*Math.sin(d)-Math.sin(dec)*Math.cos(d)*Math.cos(a-ra))/den;if(x<0||x>w||y<0||y>h)continue;let size=Math.max(.8,3.5-(s.phot_g_mean_mag||8)*.28);ctx.fillStyle=s.bp_rp!=null&&s.bp_rp>1.4?'#e8c2a0':s.bp_rp!=null&&s.bp_rp<.5?'#c7d9f1':'#e5e5df';ctx.beginPath();ctx.arc(x,y,size,0,Math.PI*2);ctx.fill();}
  let x=w/2,y=h*.45;ctx.strokeStyle='#d8bd8e';ctx.lineWidth=1;ctx.beginPath();ctx.arc(x,y,16,0,Math.PI*2);ctx.moveTo(x-24,y);ctx.lineTo(x-12,y);ctx.moveTo(x+12,y);ctx.lineTo(x+24,y);ctx.moveTo(x,y-24);ctx.lineTo(x,y-12);ctx.moveTo(x,y+12);ctx.lineTo(x,y+24);ctx.stroke();ctx.fillStyle='#e8ecf4';ctx.font='14px "Space Grotesk",Arial';ctx.fillText(name,Math.min(w-130,x+28),y+5);ctx.fillStyle='#98a5b5';ctx.font='10px monospace';ctx.fillText('N',x-3,40);ctx.fillText('E',20,y);ctx.fillText('Target direction · not a visual detection',Math.max(20,x-140),y+48);
 }
 draw();window.addEventListener('resize',draw);window.skyCleanup=()=>window.removeEventListener('resize',draw);
 let note;try{let r=await api('/api/earth-sky?'+new URLSearchParams({ra:context.ra,dec:context.dec}));stars=r.objects;note=r.note;}catch(e){note=e.message;}
 if($('earth-sky').hidden||window.skyToken!==token)return;$('sky-data-note').textContent=common+note+' IAU boundaries determine the constellation; stellar coordinates use catalog epoch 2016.0.';draw();
}
