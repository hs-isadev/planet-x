import * as THREE from 'three';
const noise=`
float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
float noise3(vec3 p){vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
float fbm(vec3 p){return noise3(p)*.57+noise3(p*2.03)*.28+noise3(p*4.07)*.15;}
`;
export function surfaceMaterial(base){
 return new THREE.ShaderMaterial({uniforms:{base:{value:base},clock:{value:0}},
 vertexShader:`varying vec3 p;varying vec3 n;varying vec3 v;void main(){p=normalize(position);vec4 mv=modelViewMatrix*vec4(position,1.);n=normalize(normalMatrix*normal);v=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}`,
 fragmentShader:`uniform vec3 base;uniform float clock;varying vec3 p;varying vec3 n;varying vec3 v;${noise}
 void main(){float t=clock;float angle=t*(.32-.10*p.y*p.y);vec3 q=vec3(p.x*cos(angle)-p.z*sin(angle),p.y,p.x*sin(angle)+p.z*cos(angle));
 float flow=fbm(q*9.+vec3(t*.18,-t*.27,t*.11));
 float granules=fbm(q*85.+vec3(flow*3.,t*.9,-t*.45));
 float fire=fbm(q*24.+vec3(t*.5,t*.22,0.));
 float spots=0.;float penumbra=0.;for(int j=0;j<7;j++){float a=float(j)*2.399;vec3 center=normalize(vec3(cos(a),sin(a*2.1)*.42,sin(a)));float d=length(q-center);float life=.65+.35*sin(t*.4+a);spots=max(spots,(1.-smoothstep(.024,.065,d))*life);penumbra=max(penumbra,(1.-smoothstep(.06,.105,d))*life);}
 float limb=.32+.68*pow(max(0.,dot(normalize(n),normalize(v))),.42);
 vec3 heat=mix(base*.52,base*1.65,smoothstep(.24,.78,granules));heat+=vec3(1.,.35,.04)*pow(fire,5.)*.8;
 heat*=limb*(1.-penumbra*.36)*(1.-spots*.88);gl_FragColor=vec4(heat,1.);}`});
}
export function corona(radius){
 const material=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.BackSide,
 uniforms:{clock:{value:0}},vertexShader:`uniform float clock;varying vec3 p;varying vec3 n;varying vec3 v;${noise}
 void main(){p=normalize(position);float plume=fbm(p*13.+vec3(0.,-clock*.7,clock*.2));vec3 pos=position*(1.+plume*.12);vec4 mv=modelViewMatrix*vec4(pos,1.);n=normalize(normalMatrix*normal);v=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}`,
 fragmentShader:`uniform float clock;varying vec3 p;varying vec3 n;varying vec3 v;${noise}
 void main(){float edge=pow(1.-abs(dot(normalize(n),normalize(v))),2.8);float flame=fbm(p*24.+vec3(clock*.2,-clock*1.1,clock*.3));float rays=pow(fbm(p*57.+vec3(0.,-clock*1.8,0.)),3.);float a=edge*(.1+flame*.42+rays*.7);gl_FragColor=vec4(1.,.24+flame*.43,.035,a);}`});
 const mesh=new THREE.Mesh(new THREE.SphereGeometry(radius*1.10,96,64),material);
 mesh.userData.update=t=>material.uniforms.clock.value=t;return mesh;
}
