// Educational terrain, never presented as a measured elevation map.
export const environments={
 mercury:{color:[122,116,108],gravity:3.7,craters:true},
 venus:{color:[151,117,68],gravity:8.87,atmosphere:'#ac8853'},
 mars:{color:[156,87,52],gravity:3.71,atmosphere:'#ac8068',dust:true,craters:true},
 moon:{color:[135,134,132],gravity:1.62,craters:true},
 jupiter:{color:[180,151,119],gravity:24.79,atmosphere:'#b4a08b',gas:true},
 saturn:{color:[193,175,131],gravity:10.44,atmosphere:'#c1af83',gas:true},
 uranus:{color:[117,173,180],gravity:8.69,atmosphere:'#75adb4',gas:true},
 neptune:{color:[65,98,176],gravity:11.15,atmosphere:'#4162b0',gas:true}
};
export function planetTerrain(body,lat,lon){
 const e=environments[body];if(!e)throw Error('Surface exploration is unavailable for this body.');
 const n=129,span=1800,heights=[];
 const seed=lat*.071+lon*.037;
 for(let j=0;j<n;j++)for(let i=0;i<n;i++){
  const x=(i/(n-1)-.5)*span,z=(j/(n-1)-.5)*span;
  let h=e.gas?0:18*Math.sin(x*.006+seed)*Math.cos(z*.004)+7*Math.sin(x*.019+z*.012)+2*Math.cos(x*.061-z*.047);
  if(e.craters)for(let k=0;k<5;k++){const cx=Math.sin(seed+k*31)*650,cz=Math.cos(seed+k*17)*650,r=70+k*24,d=Math.hypot(x-cx,z-cz)/r;h+=16*Math.exp(-(((d-1)*6)**2))-22*Math.exp(-((d*1.5)**4));}
  heights.push(h);
 }
 return {body,name:body[0].toUpperCase()+body.slice(1)+(e.gas?' Â· atmospheric flight':' Â· surface expedition'),latitude:lat,longitude:lon,n,span_m:span,heights_m:heights,context_rgb:e.color,gravity:e.gravity,atmosphere:e.atmosphere,dust:e.dust,gas:e.gas,water:false,resolution_m:span/(n-1),source:'Illustrative procedural environment; not measured terrain',note:e.gas?'No solid landing surface. Free-flight cloud-deck visualization.':'Relief, rocks and lighting are illustrative. Coordinates select a repeatable scene, not a surveyed landing site.',temperature_note:'No current weather measurements.'};
}
