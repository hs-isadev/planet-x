const byId = id => document.getElementById(id);
export function installObservingView(view) {
  const panel = document.createElement('details');
  panel.innerHTML = '<summary>SPHEREx observing perspective</summary><canvas id="observing-geometry" width="600" height="300" aria-label="Exposure position endpoints and original detector geometry"></canvas><p id="observing-note" class="micro" role="status"></p><p class="micro"><a href="https://www.jpl.nasa.gov/press-kits/spherex/quick-facts/" target="_blank" rel="noreferrer">NASA/JPL instrument and orbit ↗</a> · <a href="https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/" target="_blank" rel="noreferrer">IRSA FITS geometry ↗</a></p><a id="observing-original" target="_blank" rel="noreferrer" hidden>Open original archive exposure ↗</a>';
  byId('frame-meta').after(panel);
  let request = 0;
  const draw = geometry => {
    const ctx = byId('observing-geometry').getContext('2d');
    ctx.fillStyle = '#10151c'; ctx.fillRect(0, 0, 600, 300);
    ctx.font = '14px monospace'; ctx.fillStyle = '#dce4ee';
    const segment=geometry?.spacecraft_segment;
    ctx.fillText(segment?'Exposure position endpoints':'Illustrative polar orbit', 15, 24);
    ctx.fillText('Nominal 11° × 3.5° telescope field', 270, 24);
    const cx=114,cy=143,radius=72;
    ctx.fillStyle='#42627c';ctx.beginPath();ctx.arc(cx,cy,radius,0,2*Math.PI);ctx.fill();
    ctx.fillStyle='#dce4ee';ctx.fillText('Earth',91,149);
    ctx.strokeStyle='#84929f';ctx.setLineDash([6,4]);ctx.beginPath();
    if(segment){
      const [start,end]=segment.projection_earth_radii;
      ctx.arc(cx,cy,radius*(Math.hypot(...start)+Math.hypot(...end))/2,0,2*Math.PI);
      ctx.stroke();ctx.setLineDash([]);
      const xy=([x,y])=>[cx+x*radius,cy+y*radius];
      const a=xy(start),b=xy(end);
      ctx.strokeStyle='#f6ce82';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();
      ctx.fillStyle='#f6ce82';ctx.beginPath();ctx.arc(...a,3,0,2*Math.PI);ctx.fill();
      ctx.strokeRect(b[0]-2,b[1]-2,4,4);ctx.lineWidth=1;
      ctx.fillText('● Start   □ End',30,248);
      ctx.fillStyle='#dce4ee';ctx.fillText('Dashed: orbit guide',24,268);
    }else{
      ctx.ellipse(cx,cy,43,97,-.3,0,2*Math.PI);ctx.stroke();ctx.setLineDash([]);
      ctx.fillText('Orbit schematic',42,261);
    }
    ctx.strokeRect(285, 42, 281, 89);
    for (const x of [378.7, 472.3]) { ctx.beginPath();ctx.moveTo(x,42);ctx.lineTo(x,131);ctx.stroke(); }
    ctx.fillText('Original detector pixel grid', 270, 160);
    ctx.strokeRect(413, 173, 112, 112);
    if (geometry?.patch_vertices) {
      ctx.save();ctx.beginPath();ctx.rect(413,173,112,112);ctx.clip();
      ctx.strokeStyle = '#f6ce82';ctx.lineWidth=2;ctx.beginPath();
      geometry.patch_vertices.forEach(([x,y],i)=>{const px=413+x/geometry.detector_pixels*112,py=285-y/geometry.detector_pixels*112;if(i)ctx.lineTo(px,py);else ctx.moveTo(px,py);});
      ctx.closePath();ctx.stroke();ctx.restore();
      ctx.fillStyle='#f6ce82';ctx.fillText('Selected patch',271,228);
    } else { ctx.fillText('Patch unavailable',270,228); }
  };
  async function update() {
    const token=++request, frame=view.current(), job=view.jobId;
    const link=byId('observing-original');link.hidden=true;draw(null);
    if (!frame || !job) { byId('observing-note').textContent='Load an observation to locate its cutout on the detector.';return; }
    byId('observing-note').textContent='Reading geometry for '+frame.date+' · '+frame.id;
    try {
      const data=await view.api('/api/jobs/'+job+'/observing-view/'+frame.index);
      if(token!==request||view.jobId!==job||view.current()?.id!==frame.id)return;
      draw(data);
      byId('observing-note').textContent=[data.date,'D'+data.detector,data.id,data.patch_arcmin+' arcmin patch',data.geometry_status,data.orbit_status].join(' · ');
      if(data.spacecraft_segment){
        const seg=data.spacecraft_segment;
        byId('observing-note').textContent+=' · Exposure '+seg.dates.join(' → ')+' UTC · '+seg.height_above_reference_radius_km.map(x=>Math.round(x)).join(' → ')+' km above the reference Earth radius.';
      }
      if(data.exposure_url){link.href=data.exposure_url;link.hidden=false;}
    } catch(error) { if(token===request)byId('observing-note').textContent=error.message; }
  }
  let timer;
  panel.ontoggle=()=>{if(panel.open)update();};
  const show=view.show.bind(view);
  view.show=async function(...args){await show(...args);if(panel.open){clearTimeout(timer);timer=setTimeout(update,150);}};
  const reset=view.reset.bind(view);
  view.reset=function(...args){++request;clearTimeout(timer);panel.open=false;return reset(...args);};
}
