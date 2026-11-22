import * as THREE from 'three';

const base='/assets/sky/constellations/';
const tint=new THREE.Color().setRGB(.52,.66,.95);

export function makeSkyIllustrations(group) {
  const loader=new THREE.TextureLoader();
  const staticGlow=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const geometry=new THREE.PlaneGeometry(2,2,16,16);
  const corner=()=>({value:new THREE.Vector3()});
  const makeLayer=()=>{
    const material=new THREE.ShaderMaterial({
      depthWrite:false, transparent:true, blending:THREE.AdditiveBlending, side:THREE.DoubleSide,
      uniforms:{art:{value:null}, opacity:{value:0}, tint:{value:tint}, focus:{value:0}, time:{value:0},
        topLeft:corner(), topRight:corner(), bottomLeft:corner(), bottomRight:corner()},
      vertexShader:`uniform vec3 topLeft,topRight,bottomLeft,bottomRight;
        varying vec2 artUV; varying float altitude;
        void main(){
          artUV=uv;
          vec3 positionOnSky=normalize(mix(mix(bottomLeft,bottomRight,uv.x),mix(topLeft,topRight,uv.x),uv.y))*1010.;
          vec4 world=modelMatrix*vec4(positionOnSky,1.);
          altitude=normalize(world.xyz).y;
          gl_Position=projectionMatrix*viewMatrix*world;
        }`,
      fragmentShader:`uniform sampler2D art; uniform float opacity; uniform vec3 tint;
        uniform float focus; uniform float time;
        varying vec2 artUV; varying float altitude;
        float lightAt(vec2 uv){
          return dot(texture2D(art,uv).rgb,vec3(.299,.587,.114));
        }
        void main(){
          float light=lightAt(artUV);
          float coverage=smoothstep(.006,.043,altitude);
          vec3 color=tint;
          float alpha=pow(light,.82)*opacity;
          if(focus>.005){
            float wave=.86+.14*sin(17.*artUV.y-2.3*time+2.1*sin(8.*artUV.x+time));
            float drift=.005+.003*wave;
            float spread=(lightAt(artUV+vec2(drift,0.))+lightAt(artUV-vec2(drift,0.))
              +lightAt(artUV-vec2(0.,2.2*drift)))*.3333;
            float embers=max(spread-light,0.);
            color=mix(tint,mix(vec3(1.,.48,.17),vec3(1.,.91,.69),light),focus*wave);
            alpha+=focus*wave*(pow(light,.68)*.92+embers*.7);
          }
          gl_FragColor=vec4(color,clamp(alpha*coverage,0.,1.));
        }`,
    });
    const mesh=new THREE.Mesh(geometry,material);
    mesh.frustumCulled=false;mesh.renderOrder=1.5;mesh.visible=false;group.add(mesh);
    return {mesh, uniforms:material.uniforms, file:null, request:0, targetFocus:0};
  };
  const layers=Array.from({length:12},makeLayer);
  const cache=new Map(), pending=new Map();
  function textureFor(file){
    if(cache.has(file)){
      const texture=cache.get(file);cache.delete(file);cache.set(file,texture);
      return Promise.resolve(texture);
    }
    if(pending.has(file))return pending.get(file);
    const load=loader.loadAsync(base+file+'.webp').then(texture=>{
      texture.colorSpace=THREE.NoColorSpace;
      cache.set(file,texture);
      while(cache.size>22){
        const stale=[...cache.keys()].find(name=>layers.every(layer=>layer.file!==name));
        if(!stale)break;
        cache.get(stale).dispose();cache.delete(stale);
      }
      return texture;
    }).finally(()=>pending.delete(file));
    pending.set(file,load);
    return load;
  }
  function update(entries, fade){
    const visible=new Set(entries.map(entry=>entry.record[0]));
    for(const layer of layers){
      if(layer.file && (!fade || !visible.has(layer.file))){
        layer.mesh.visible=false;layer.file=null;layer.request++;
      }
    }
    if(!fade)return;
    for(const {record,focus,selected} of entries){
      const [file,corners]=record;
      let layer=layers.find(candidate=>candidate.file===file);
      const assigned=Boolean(layer);
      layer??=layers.find(candidate=>!candidate.file);
      if(!layer)continue;
      layer.uniforms.opacity.value=fade*(selected ? .40 : .24);
      layer.targetFocus=fade*focus;
      if(assigned)continue;
      layer.file=file;
      layer.uniforms.focus.value=0;
      const request=++layer.request;
      ['topLeft','topRight','bottomLeft','bottomRight'].forEach((name,i)=>layer.uniforms[name].value.fromArray(corners[i]));
      textureFor(file).then(texture=>{
        if(request!==layer.request)return;
        layer.uniforms.art.value=texture;layer.mesh.visible=true;
      }).catch(()=>{if(request===layer.request)layer.file=null;});
    }
  }
  function animate(time,dt){
    const easing=1-Math.exp(-dt*5);
    for(const layer of layers){
      if(!layer.mesh.visible)continue;
      const focus=layer.uniforms.focus;
      focus.value+=(layer.targetFocus-focus.value)*easing;
      layer.uniforms.time.value=staticGlow?0:time;
    }
  }
  return {update,animate};
}
