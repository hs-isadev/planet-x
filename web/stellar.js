import {surfaceMaterial} from './plasma.js';
import * as THREE from 'three';
// Educational photosphere and unresolved light response. Not an observed spot map.
export function stellarColor(d){
 const t=d.id==='sun'||d.id==='origin'?5772:d.teff_gspphot;
 if(t){const k=Math.max(1800,Math.min(40000,t))/100;let r,g,b;if(k<=66){r=255;g=99.4708*Math.log(k)-161.1196;b=k<=19?0:138.5177*Math.log(k-10)-305.0448;}else{r=329.6987*Math.pow(k-60,-.1332);g=288.1222*Math.pow(k-60,-.07551);b=255;}return new THREE.Color(...[r,g,b].map(v=>Math.max(0,Math.min(255,v))/255));}
 if(d.bp_rp!=null){let c=new THREE.Color('#c7dbff');c.lerp(new THREE.Color('#ffc08b'),Math.max(0,Math.min(1,(d.bp_rp+.3)/3.6)));return c;}return new THREE.Color('#e1e4e8');
}
export function photosphere(d){return surfaceMaterial(stellarColor(d));}
export function halo(d){let c=document.createElement('canvas');c.width=c.height=128;let x=c.getContext('2d'),a=x.createImageData(128,128),col=stellarColor(d);for(let y=0;y<128;y++)for(let z=0;z<128;z++){let r=Math.hypot(z-63.5,y-63.5)/63.5,i=(y*128+z)*4,intensity=Math.exp(-r*r*11)*.62+Math.exp(-r*r*110)*.38;a.data[i]=col.r*255;a.data[i+1]=col.g*255;a.data[i+2]=col.b*255;a.data[i+3]=Math.round(Math.max(0,intensity-.0001)*255);}x.putImageData(a,0,0);let t=new THREE.CanvasTexture(c);return new THREE.Sprite(new THREE.SpriteMaterial({map:t,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));}
