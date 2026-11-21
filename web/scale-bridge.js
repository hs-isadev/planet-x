// Keeps the Solar System on screen after zooming out into the star (parsec) view, so leaving and entering it is
// one continuous zoom: the planets' orbits and positions are redrawn at their true size in parsecs (1 AU =
// 1/206264.8 pc) around the Sun and fade out only once they shrink to a few pixels.
import * as THREE from 'three';

const AU_PC = 1 / 206264.806247;
const EPS = 23.439291111 * Math.PI / 180;
const PLANET_COLOR = {mercury: '#a39d94', venus: '#e3cfa1', earth: '#6ea8dc', mars: '#c9714a', jupiter: '#d8b892',
  saturn: '#e1cc95', uranus: '#9fd6dc', neptune: '#6b8fe0', pluto: '#c8b39c'};

// Solar-scene vector (ecliptic, AU) → star-scene vector (equatorial, pc). Same rotation the app uses on exit.
function toStars(v) {
  const x = v.x, y = -v.z, z = v.y;
  return v.set(x, Math.sin(EPS) * y + Math.cos(EPS) * z, -(Math.cos(EPS) * y - Math.sin(EPS) * z)).multiplyScalar(AU_PC);
}

export function installScaleBridge(C) {
  const stars = C.prototype.stars;
  C.prototype.stars = function (...args) {
    // Snapshot where the planets are right now (orbits advance while you watch) before the scene is cleared.
    const snapshot = this.mode === 'solar' ? this.items.filter(i => PLANET_COLOR[i.data.id]).map(i => ({id: i.data.id, pos: i.pos.clone()})) : null;
    stars.apply(this, args);
    this.addSolarProxy(snapshot);
  };

  C.prototype.addSolarProxy = function (snapshot) {
    const data = this.solarData;
    if (!data?.objects) return;
    const group = new THREE.Group();
    group.name = 'Solar System at true scale';
    const lines = [], dots = [], radii = [];
    for (const d of data.objects) {
      if (!PLANET_COLOR[d.id]) continue;
      const color = new THREE.Color(PLANET_COLOR[d.id]);
      if (d.orbit_au) {
        const points = d.orbit_au.map(a => toStars(this.vector(a)));
        const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points),
          new THREE.LineBasicMaterial({color: 0x6b7988, transparent: true, opacity: .4, depthWrite: false}));
        lines.push(line); group.add(line);
      }
      const at = snapshot?.find(s => s.id === d.id)?.pos.clone() || (d.xyz_au ? this.vector(d.xyz_au) : null);
      if (!at) continue;
      const pos = toStars(at);
      const geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pos.toArray(), 3));
      const material = new THREE.ShaderMaterial({
        transparent: true, depthWrite: false,
        uniforms: { tint: {value: color}, alpha: {value: 1}, pixels: {value: 12},
          bands: {value: ['jupiter', 'saturn'].includes(d.id) ? 1 : 0} },
        vertexShader: `uniform float pixels;
          void main(){ gl_PointSize=pixels; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
        fragmentShader: `uniform vec3 tint; uniform float alpha, bands;
          void main(){
            vec2 xy=2.*gl_PointCoord-1.;
            float r2=dot(xy,xy); if(r2>1.) discard;
            vec3 normal=vec3(xy,sqrt(1.-r2));
            float light=.30+.84*max(0.,dot(normal,normalize(vec3(-.5,-.4,.8))));
            vec3 albedo=tint*(1.+bands*.12*sin(18.*xy.y));
            gl_FragColor=vec4(albedo*light,alpha*(1.-smoothstep(.77,1.,r2)));
            #include <colorspace_fragment>
          }`
      });
      const dot = new THREE.Points(geometry, material);
      dot.userData.id = d.id;
      dots.push(dot); radii.push(pos.length()); group.add(dot);
    }
    const outer = Math.max(...radii, 30 * AU_PC);
    group.userData.update = () => {
      group.visible = this.mode === 'stars' && !this.local && !this.surface;
      if (!group.visible) return;
      const distance = this.camera.position.length();
      const pxPerPc = this.h / (2 * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * Math.max(distance, 1e-12));
      const fade = r => THREE.MathUtils.clamp((r * pxPerPc - 3) / 25, 0, 1);   // gone once an orbit is ~3 px across
      lines.forEach(l => { l.material.opacity = .4 * fade(outer); l.visible = l.material.opacity > .01; });
      dots.forEach((p, k) => { const separation = radii[k] * pxPerPc;
        p.material.uniforms.pixels.value = THREE.MathUtils.clamp(separation * .22, 6, 15) * this.renderer.getPixelRatio();
        p.material.uniforms.alpha.value = fade(radii[k]);
        p.visible = p.material.uniforms.alpha.value > .01; });
    };
    this.content.add(group);
    this.solarProxy = group;
  };
}
