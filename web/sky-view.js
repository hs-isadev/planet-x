// "Your sky": a planetarium view of the real sky from the user's location and time (Stellarium-style).
//
// Data: 25,700 Hipparcos/HYG stars to V 7.5 with B−V colours, IAU constellation lines, Messier objects and the
// Milky Way brightness map (built by scripts/build_sky_assets.py from d3-celestial, BSD-3-Clause); Sun, Moon
// and planet positions, magnitudes and phases from astronomy-engine (MIT), computed in the browser.
// Physics on screen: precession/nutation to the date (Rotation_EQJ_HOR), atmospheric refraction near the
// horizon, extinction and reddening with airmass, scintillation (twinkling) that grows towards the horizon,
// Rayleigh/Mie daylight and twilight sky, and a limiting magnitude that depends on sky brightness, light
// pollution and zoom. The SPHEREx study targets are marked so you can see which are up tonight.
import * as THREE from 'three';
import {Sky} from 'three/addons/objects/Sky.js';

const $ = id => document.getElementById(id);
const DEG = Math.PI / 180;
const ASSETS = '/assets/sky/';
const TARGETS = [
  ['Barnard’s Star', 269.4521, 4.6934], ['Proxima Centauri', 217.4290, -62.6795], ['Epsilon Indi B', 330.8003, -56.7853],
  ['WISE 0855−0714', 133.7862, -7.2444], ['RW Aurigae', 76.9565, 30.4014], ['R Draconis', 248.1676, 66.7550],
];
const BODIES = [
  ['Mercury', '#c9b9a6'], ['Venus', '#fff3d6'], ['Mars', '#ff9b6a'], ['Jupiter', '#f4e2c4'], ['Saturn', '#f1d9a0'],
  ['Uranus', '#c6f0f4'], ['Neptune', '#9db6ff'],
];
const POLLUTION = {dark: [0, 'Dark site (Bortle 1–2)'], rural: [.35, 'Rural (Bortle 3–4)'], suburb: [.7, 'Suburban (Bortle 5–6)'], city: [1, 'City (Bortle 8–9)']};
const SPEEDS = [[0, 'Paused'], [1, 'Real time'], [60, '1 min / s'], [600, '10 min / s'], [3600, '1 h / s'], [86400, '1 day / s']];

let Astronomy = null;
function loadAstronomy() {
  if (Astronomy) return Promise.resolve(Astronomy);
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/vendor/astronomy.browser.min.js';
    s.onload = () => { Astronomy = window.Astronomy; resolve(Astronomy); };
    s.onerror = () => reject(new Error('Ephemeris library failed to load.'));
    document.head.append(s);
  });
}

// B−V → linear RGB via temperature (Ballesteros 2012) and a black-body colour approximation.
function bvColor(bv) {
  const t = 4600 * (1 / (.92 * bv + 1.7) + 1 / (.92 * bv + .62));
  const k = Math.min(400, Math.max(10, t / 100));
  const r = k <= 66 ? 1 : Math.min(1, 1.2929 * Math.pow(k - 60, -.1332));
  const g = k <= 66 ? Math.min(1, Math.max(0, .3901 * Math.log(k) - .6318)) : Math.min(1, 1.1299 * Math.pow(k - 60, -.0755));
  const b = k >= 66 ? 1 : k <= 19 ? 0 : Math.min(1, Math.max(0, .5432 * Math.log(k - 10) - 1.1963));
  const c = new THREE.Color(r, g, b);
  return c.lerp(new THREE.Color(1, 1, 1), .35);      // the eye sees star colours much paler than black bodies
}

const eqVector = (ra, dec, r = 1) => new THREE.Vector3(Math.cos(dec * DEG) * Math.cos(ra * DEG), Math.cos(dec * DEG) * Math.sin(ra * DEG), Math.sin(dec * DEG)).multiplyScalar(r);

// GLSL shared by everything placed on the sky: altitude-dependent extinction and the ground cut-off.
const EXTINCTION = `
  float airmass(float s){ return 1. / (max(s, 0.) + .025 * exp(-11. * max(s, 0.))); }      // s = sin(altitude)
  float extinctMag(float s){ return .22 * (airmass(s) - 1.); }                              // V-band, clear air
`;

export function installSkyView({toast = () => {}} = {}) {
  const view = {open: false, ready: null, time: new Date(), live: true, speed: 1, lat: 51.4779, lon: 0, place: 'Greenwich, UK (default)',
    yaw: 180, pitch: 25, fov: 70, fovTarget: 70, pollution: 'rural', layers: {lines: true, labels: true, grid: false, atmosphere: true, ground: true, targets: true},
    selected: null, drag: null};
  let renderer, scene, camera, skyGroup, sky, twilightMesh, starMat, mwMat, lineMat, gridGroup, ground, horizonMat, sunSprite, moonMesh, bodyPoints = [], labels = [], data;
  const root = buildDom();

  function buildDom() {
    const el = document.createElement('section');
    el.id = 'sky-view';
    el.hidden = true;
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-label', 'Your sky');
    el.innerHTML = `
      <canvas id="sky-canvas" aria-label="Planetarium view of the sky"></canvas>
      <div id="sky-labels" aria-hidden="true"></div>
      <div class="sky-top">
        <div class="sky-title"><span class="eyebrow">YOUR SKY · COMPUTED</span><strong id="sky-place">Locating…</strong><small id="sky-when"></small></div>
        <div class="sky-actions">
          <button type="button" id="sky-locate" class="quiet">Use my location</button>
          <details class="sky-menu"><summary>Place &amp; time</summary>
            <label>Latitude<input id="sky-lat" type="number" step="0.0001" min="-90" max="90"></label>
            <label>Longitude<input id="sky-lon" type="number" step="0.0001" min="-180" max="180"></label>
            <label>Date &amp; time (local)<input id="sky-datetime" type="datetime-local" step="60"></label>
            <button type="button" id="sky-apply">Apply</button>
          </details>
          <details class="sky-menu"><summary>Show</summary>
            <label class="sky-check"><input type="checkbox" data-layer="lines" checked> Constellations</label>
            <label class="sky-check"><input type="checkbox" data-layer="labels" checked> Names</label>
            <label class="sky-check"><input type="checkbox" data-layer="targets" checked> SPHEREx targets</label>
            <label class="sky-check"><input type="checkbox" data-layer="grid"> Alt/az grid</label>
            <label class="sky-check"><input type="checkbox" data-layer="atmosphere" checked> Atmosphere</label>
            <label class="sky-check"><input type="checkbox" data-layer="ground" checked> Ground</label>
            <label>Sky brightness<select id="sky-pollution">${Object.entries(POLLUTION).map(([k, v]) => `<option value="${k}">${v[1]}</option>`).join('')}</select></label>
          </details>
          <button type="button" id="sky-close" class="quiet" aria-label="Close sky view">Close</button>
        </div>
      </div>
      <div class="sky-bottom">
        <div class="sky-time">
          <button type="button" id="sky-now" class="quiet">Now</button>
          <button type="button" data-step="-3600" class="quiet" aria-label="One hour back">−1 h</button>
          <select id="sky-speed" aria-label="Time speed">${SPEEDS.map(([v, n]) => `<option value="${v}">${n}</option>`).join('')}</select>
          <button type="button" data-step="3600" class="quiet" aria-label="One hour forward">+1 h</button>
        </div>
        <div id="sky-readout" class="sky-readout"></div>
      </div>
      <article id="sky-card" class="sky-card" hidden></article>
      <p class="sky-credit">Stars: Hipparcos/HYG via d3-celestial · ephemeris: astronomy-engine · computed for your place and time; not a photograph.</p>`;
    document.body.append(el);
    return el;
  }

  // ---------------------------------------------------------------------------------------------------------
  async function init() {
    await loadAstronomy();
    const [json, bin] = await Promise.all([
      fetch(ASSETS + 'sky.json').then(r => { if (!r.ok) throw Error('Sky catalog unavailable'); return r.json(); }),
      fetch(ASSETS + 'stars.bin').then(r => { if (!r.ok) throw Error('Star catalog unavailable'); return r.arrayBuffer(); }),
    ]);
    data = json;
    const canvas = $('sky-canvas');
    renderer = new THREE.WebGLRenderer({canvas, antialias: true});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = .55;
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(70, 1, .1, 5000);
    camera.rotation.order = 'YXZ';

    // daylight / twilight sky (Preetham model)
    sky = new Sky();
    sky.scale.setScalar(4500);
    sky.material.uniforms.turbidity.value = 3.2;
    sky.material.uniforms.rayleigh.value = 2.4;
    sky.material.uniforms.mieCoefficient.value = .004;
    sky.material.uniforms.mieDirectionalG.value = .82;
    if (sky.material.uniforms.cloudCoverage) sky.material.uniforms.cloudCoverage.value = 0;
    sky.material.depthWrite = false;
    sky.renderOrder = -10;
    scene.add(sky);
    twilightMesh = twilightSky();
    scene.add(twilightMesh);

    // everything fixed to the celestial sphere lives in skyGroup (J2000 equatorial axes)
    skyGroup = new THREE.Group();
    skyGroup.matrixAutoUpdate = false;
    scene.add(skyGroup);
    skyGroup.add(milkyWay());
    skyGroup.add(stars(new Float32Array(bin)));
    skyGroup.add(constellationLines());
    gridGroup = altAzGrid();
    scene.add(gridGroup);
    ground = landscape();
    scene.add(ground);
    sunSprite = sunDisc();
    skyGroup.add(sunSprite);
    moonMesh = moonDisc();
    skyGroup.add(moonMesh);
    for (const [name, color] of BODIES) {
      const p = planetPoint(color);
      p.userData.name = name;
      bodyPoints.push(p);
      skyGroup.add(p);
    }
    bindControls();
    resize();
    window.addEventListener('resize', resize);
  }

  function pointsShaderMaterial(vertex, fragment, uniforms) {
    return new THREE.ShaderMaterial({transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms, vertexShader: vertex, fragmentShader: fragment});
  }

  function stars(buffer) {
    const n = buffer.length / 4, pos = new Float32Array(n * 3), mag = new Float32Array(n), col = new Float32Array(n * 3), seed = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      eqVector(buffer[i * 4], buffer[i * 4 + 1], 1000).toArray(pos, i * 3);
      mag[i] = buffer[i * 4 + 2];
      bvColor(buffer[i * 4 + 3]).toArray(col, i * 3);
      seed[i] = Math.random() * 100;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('mag', new THREE.BufferAttribute(mag, 1));
    g.setAttribute('tint', new THREE.BufferAttribute(col, 3));
    g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
    starMat = pointsShaderMaterial(`
      attribute float mag; attribute vec3 tint; attribute float seed;
      uniform float limit; uniform float pixel; uniform float zoom; uniform float time; uniform float twinkle;
      varying vec3 vColor; varying float vGlow;
      ${EXTINCTION}
      void main(){
        vec4 world = modelMatrix * vec4(position, 1.);
        float s = normalize(world.xyz).y;
        float m = mag + extinctMag(s);                        // dimmer through more air
        // scintillation: a few hundredths of a magnitude overhead, several tenths near the horizon
        float tw = twinkle * (.04 + .5 * pow(1. - clamp(s, 0., 1.), 4.)) * (sin(time * (7. + seed) + seed * 3.) * .6 + sin(time * (13.1 + seed * .7)) * .4);
        m += tw;
        float b = pow(10., -.4 * (m - limit));                // flux relative to the faintest visible star
        float visible = smoothstep(-.012, .01, s) * smoothstep(.0, .6, b);
        float size = clamp(1.7 + 2.3 * pow(b, .25), 1.7, 30.) * zoom;
        vec3 c = tint;
        c = mix(c, c * vec3(1., .78, .55), clamp((airmass(s) - 1.) / 9., 0., 1.));   // reddening low down
        vColor = c * visible * clamp(.16 * pow(b, .45), .05, 2.6);
        vGlow = clamp(log(b) / 4. - .45, 0., 1.);
        gl_PointSize = visible > .001 ? size * pixel : 0.;
        gl_Position = projectionMatrix * viewMatrix * world;
      }`, `
      varying vec3 vColor; varying float vGlow;
      void main(){
        vec2 q = gl_PointCoord - .5; float r = length(q) * 2.;
        float core = exp(-r * r * 6.) + .25 * exp(-r * r * 2.2);
        float halo = vGlow * (exp(-r * 3.2) * .55 + .08 * (exp(-abs(q.x) * 70.) + exp(-abs(q.y) * 70.)) * (1. - r));
        float i = core + halo; if (i < .004) discard;
        gl_FragColor = vec4(vColor * i, 1.);
      }`, {limit: {value: 6}, pixel: {value: 1}, zoom: {value: 1}, time: {value: 0}, twinkle: {value: 1}});
    const p = new THREE.Points(g, starMat);
    p.frustumCulled = false;
    p.renderOrder = 2;
    return p;
  }

  function milkyWay() {
    const tex = new THREE.TextureLoader().load(ASSETS + 'milkyway.jpg');
    tex.colorSpace = THREE.NoColorSpace;
    tex.wrapS = THREE.RepeatWrapping;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    mwMat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.BackSide,
      uniforms: {map: {value: tex}, strength: {value: 1}},
      vertexShader: `varying vec3 vDir; varying float vS; void main(){ vDir = position; vec4 w = modelMatrix * vec4(position,1.); vS = normalize(w.xyz).y; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: `uniform sampler2D map; uniform float strength; varying vec3 vDir; varying float vS;
        ${EXTINCTION}
        void main(){
          vec3 d = normalize(vDir);
          float ra = atan(d.y, d.x); if (ra < 0.) ra += 6.2831853;
          float dec = asin(clamp(d.z, -1., 1.));
          float v = texture2D(map, vec2(ra / 6.2831853, .5 + dec / 3.1415926)).r;
          float ext = pow(10., -.4 * extinctMag(vS)) * smoothstep(-.01, .08, vS);
          vec3 tint = mix(vec3(.55, .6, .78), vec3(1., .9, .76), v);        // faint arms bluish-grey, core warm
          gl_FragColor = vec4(tint * pow(v, 1.35) * .34 * strength * ext, 1.);
        }`,
    });
    const m = new THREE.Mesh(new THREE.SphereGeometry(1500, 96, 48), mwMat);
    m.renderOrder = 1;
    m.frustumCulled = false;
    return m;
  }

  function constellationLines() {
    const pts = [];
    for (const [, seg] of data.lines) {
      for (let i = 0; i < seg.length - 1; i++) {
        const a = eqVector(seg[i][0], seg[i][1], 990), b = eqVector(seg[i + 1][0], seg[i + 1][1], 990);
        // stop short of the stars so the lines do not cover them
        const d = b.clone().sub(a), len = d.length(), cut = Math.min(len * .2, 6);
        d.normalize();
        pts.push(...a.clone().addScaledVector(d, cut).toArray(), ...b.clone().addScaledVector(d, -cut).toArray());
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    lineMat = new THREE.ShaderMaterial({transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: {strength: {value: .5}},
      vertexShader: `varying float vS; void main(){ vec4 w = modelMatrix * vec4(position,1.); vS = normalize(w.xyz).y; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: `uniform float strength; varying float vS; void main(){ gl_FragColor = vec4(vec3(.33,.52,.78) * strength * smoothstep(-.01,.03,vS), 1.); }`});
    const lines = new THREE.LineSegments(g, lineMat);
    lines.frustumCulled = false;
    return lines;
  }

  function altAzGrid() {
    const group = new THREE.Group(), pts = [];
    const v = (az, alt) => new THREE.Vector3(Math.sin(az * DEG) * Math.cos(alt * DEG), Math.sin(alt * DEG), -Math.cos(az * DEG) * Math.cos(alt * DEG)).multiplyScalar(980);
    for (let alt = 0; alt < 90; alt += 15) for (let az = 0; az < 360; az += 3) pts.push(...v(az, alt).toArray(), ...v(az + 3, alt).toArray());
    for (let az = 0; az < 360; az += 15) for (let alt = 0; alt < 88; alt += 3) pts.push(...v(az, alt).toArray(), ...v(az, alt + 3).toArray());
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    group.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({color: 0x3f5a46, transparent: true, opacity: .55, depthWrite: false})));
    group.visible = false;
    return group;
  }

  // Ground with a low, irregular horizon (hills and a tree line) so the sky has a place to stand in.
  function landscape() {
    const group = new THREE.Group();
    const seg = 720, pos = [], idx = [];
    const noise = a => .55 * Math.sin(a * 3 + 1.3) + .3 * Math.sin(a * 7.3 + .2) + .2 * Math.sin(a * 17.9 + 2.1) + .08 * Math.sin(a * 61 + 1) + .06 * Math.sin(a * 113 + 4);
    for (let i = 0; i <= seg; i++) {
      const az = i / seg * Math.PI * 2;
      const tree = Math.max(0, Math.sin(az * 41) * Math.sin(az * 9 + 1)) * .7;
      const h = Math.max(.15, 1.25 + 1.1 * noise(az) + tree) * DEG;           // horizon height, 0.2°–3.5°
      const r = 900, x = Math.sin(az), z = -Math.cos(az);
      pos.push(x * r * Math.cos(h), r * Math.sin(h), z * r * Math.cos(h), x * r, -r * .35, z * r);
      if (i < seg) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    horizonMat = new THREE.ShaderMaterial({uniforms: {light: {value: new THREE.Color(0x05070a)}, glow: {value: new THREE.Color(0x000000)}},
      side: THREE.DoubleSide,
      vertexShader: `varying float vY; void main(){ vY = position.y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`,
      fragmentShader: `uniform vec3 light; uniform vec3 glow; varying float vY; void main(){ gl_FragColor = vec4(light + glow * smoothstep(-40., 30., vY) * .25, 1.); }`});
    const ridge = new THREE.Mesh(g, horizonMat);
    ridge.renderOrder = 5;
    group.add(ridge);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(950, 64).rotateX(-Math.PI / 2).translate(0, -300, 0), horizonMat);
    floor.renderOrder = 5;
    group.add(floor);
    return group;
  }

  // Twilight, night airglow and light-pollution glow. The Preetham daylight model goes black as soon as the Sun
  // sets; real skies keep a coloured glow until the Sun is 18° down: warm on the Sun's side, a deep blue zenith,
  // and opposite the Sun the grey-blue shadow of the Earth under the pink Belt of Venus.
  function twilightSky() {
    const mat = new THREE.ShaderMaterial({transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.BackSide,
      uniforms: {sun: {value: new THREE.Vector3(0, -1, 0)}, sunAlt: {value: -30}, pollution: {value: 0}, moon: {value: 0}},
      vertexShader: `varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`,
      fragmentShader: `uniform vec3 sun; uniform float sunAlt; uniform float pollution; uniform float moon; varying vec3 vDir;
        void main(){
          vec3 d = normalize(vDir);
          float alt = max(d.y, 0.);
          vec2 ds = normalize(d.xz + 1e-5), ss = normalize(sun.xz + 1e-5);
          float toward = dot(ds, ss) * .5 + .5;                         // 1 = Sun's azimuth, 0 = opposite
          float h = sunAlt;
          float tw = smoothstep(-18., -3., h) * (1. - smoothstep(2., 10., h));   // twilight strength
          float low = exp(-alt * 5.5), lowest = exp(-alt * 14.);
          vec3 zenith = mix(vec3(.0015, .003, .009), vec3(.03, .07, .19), smoothstep(-16., -1., h));
          vec3 warm = mix(vec3(.45, .09, .02), vec3(1., .5, .16), smoothstep(-7., 3., h));
          vec3 sunSide = mix(vec3(.05, .07, .16), warm, pow(toward, 2.5)) * low;
          vec3 col = zenith * (1. - low) * tw + sunSide * tw * (.35 + .65 * lowest);
          // Earth's shadow (blue-grey band on the horizon) under the Belt of Venus, opposite the Sun
          float anti = pow(1. - toward, 3.);
          float belt = smoothstep(-7., -1., h) * (1. - smoothstep(-1., 3., h));
          col += anti * belt * (vec3(.32, .16, .2) * exp(-pow((alt - .14) / .07, 2.)) + vec3(.03, .045, .08) * exp(-alt * 12.));
          // natural airglow + city light dome, strongest on the horizon
          float night = 1. - smoothstep(-18., -10., h);
          col += night * (vec3(.004, .007, .006) * exp(-alt * 4.) + pollution * vec3(.11, .065, .03) * exp(-alt * 3.2) + pollution * vec3(.012, .013, .02));
          col += moon * vec3(.012, .02, .04) * (.4 + .6 * exp(-alt * 2.));       // moonlit sky
          gl_FragColor = vec4(col, 1.);
        }`});
    const m = new THREE.Mesh(new THREE.SphereGeometry(4000, 64, 32), mat);
    m.renderOrder = -9;
    m.frustumCulled = false;
    return m;
  }

  function radialTexture(stops) {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const x = c.getContext('2d'), g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
    stops.forEach(([o, col]) => g.addColorStop(o, col));
    x.fillStyle = g; x.fillRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  }

  function sunDisc() {
    const m = new THREE.SpriteMaterial({map: radialTexture([[0, '#ffffff'], [.09, '#fffbe8'], [.12, 'rgba(255,240,200,.85)'], [.3, 'rgba(255,214,150,.18)'], [1, 'rgba(255,200,140,0)']]),
      blending: THREE.AdditiveBlending, depthWrite: false, transparent: true});
    const s = new THREE.Sprite(m);
    s.renderOrder = 3;
    return s;
  }

  // The Moon: a lit sphere with procedural maria; phase and bright-limb angle follow from the true Sun direction.
  function moonDisc() {
    const mat = new THREE.ShaderMaterial({uniforms: {sun: {value: new THREE.Vector3(1, 0, 0)}, fade: {value: 1}},
      vertexShader: `varying vec3 vN; varying vec3 vP; void main(){ vN = normalize(mat3(modelMatrix) * normal); vP = position; gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(position,1.); }`,
      fragmentShader: `uniform vec3 sun; uniform float fade; varying vec3 vN; varying vec3 vP;
        float h(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,37.719))) * 43758.5453); }
        float n3(vec3 p){ vec3 i = floor(p), f = fract(p); f = f*f*(3.-2.*f);
          return mix(mix(mix(h(i),h(i+vec3(1,0,0)),f.x),mix(h(i+vec3(0,1,0)),h(i+vec3(1,1,0)),f.x),f.y),
                     mix(mix(h(i+vec3(0,0,1)),h(i+vec3(1,0,1)),f.x),mix(h(i+vec3(0,1,1)),h(i+vec3(1,1,1)),f.x),f.y),f.z); }
        void main(){
          vec3 p = normalize(vP);
          float maria = smoothstep(.42, .62, n3(p * 1.7 + vec3(3.1, .4, 1.7)) * .65 + n3(p * 4.2) * .35);
          float albedo = mix(.92, .5, maria) * (.86 + .14 * n3(p * 22.)) * (.94 + .06 * n3(p * 70.));
          float lit = smoothstep(-.03, .12, dot(vN, normalize(sun)));
          vec3 earthshine = vec3(.02, .025, .035);
          gl_FragColor = vec4((vec3(1., .97, .92) * albedo * lit * .82 + earthshine) * fade, 1.);
        }`});
    const m = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), mat);
    m.renderOrder = 4;
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({map: radialTexture([[0, 'rgba(230,236,255,.5)'], [.25, 'rgba(200,215,255,.12)'], [1, 'rgba(200,215,255,0)']]),
      blending: THREE.AdditiveBlending, depthWrite: false, transparent: true}));
    glow.scale.setScalar(9);
    m.add(glow);
    m.userData.glow = glow;
    return m;
  }

  function planetPoint(color) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0], 3));
    const mat = pointsShaderMaterial(`uniform float size; uniform float pixel; void main(){ gl_PointSize = size * pixel; gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(position,1.); }`,
      `uniform vec3 color; uniform float alpha; void main(){ vec2 q = gl_PointCoord - .5; float r = length(q) * 2.; float i = exp(-r*r*7.) + exp(-r*3.) * .35; gl_FragColor = vec4(color * i * alpha, 1.); }`,
      {size: {value: 6}, pixel: {value: 1}, color: {value: new THREE.Color(color)}, alpha: {value: 1}});
    const p = new THREE.Points(g, mat);
    p.frustumCulled = false;
    p.renderOrder = 3;
    return p;
  }

  // ---------------------------------------------------------------------------------------------------------
  // state → scene

  let observer, lastAstro = 0, sunAlt = -90, moonInfo = null, bodyInfo = [];
  function horToScene(x, y, z) { return new THREE.Vector3(-y, z, -x); }            // HOR: x north, y west, z zenith

  function updateSky(force = false) {
    const A = Astronomy;
    observer = new A.Observer(view.lat, view.lon, 0);
    const time = A.MakeTime(view.time);
    const rot = A.Rotation_EQJ_HOR(time, observer).rot;                      // J2000 equatorial → horizontal (of date)
    // scene = S · HOR, HOR = R · EQJ  (astronomy-engine matrices are column-major: rot[col][row])
    const m = new THREE.Matrix4();
    const R = i => horToScene(rot[i][0], rot[i][1], rot[i][2]);
    const ex = R(0), ey = R(1), ez = R(2);
    m.makeBasis(ex, ey, ez);
    skyGroup.matrix.copy(m);
    skyGroup.matrixWorldNeedsUpdate = true;

    const now = performance.now();
    if (!force && now - lastAstro < 120) return;
    lastAstro = now;
    const place = (body, r) => {
      const eq = A.Equator(body, time, observer, false, true);                  // topocentric J2000 RA/Dec
      return eqVector(eq.ra * 15, eq.dec, r);
    };
    // Sun
    const sunEq = A.Equator('Sun', time, observer, true, true);
    const sunHor = A.Horizon(time, observer, sunEq.ra, sunEq.dec, 'normal');
    sunAlt = sunHor.altitude;
    sunSprite.position.copy(place('Sun', 1200));
    sunSprite.scale.setScalar(1200 * .53 * DEG * 11);
    const sunScene = sunSprite.position.clone().applyMatrix4(skyGroup.matrix).normalize();
    sky.material.uniforms.sunPosition.value.copy(sunScene);
    // Moon
    const moonPos = place('Moon', 1100);
    moonMesh.position.copy(moonPos);
    const ill = A.Illumination('Moon', time);
    moonMesh.scale.setScalar(1100 * Math.tan(.259 * DEG) * (384400 / (ill.geo_dist * 149597870.7)));
    moonMesh.material.uniforms.sun.value.copy(sunScene);   // the Sun is ~400× farther than the Moon: same direction
    const moonEq = A.Equator('Moon', time, observer, true, true);
    const moonHor = A.Horizon(time, observer, moonEq.ra, moonEq.dec, 'normal');
    moonInfo = {name: 'Moon', mag: ill.mag, phase: ill.phase_fraction, alt: moonHor.altitude, az: moonHor.azimuth, ra: moonEq.ra * 15, dec: moonEq.dec,
      dist_km: ill.geo_dist * 149597870.7, pos: moonPos};
    // planets
    bodyInfo = BODIES.map(([name], k) => {
      const p = bodyPoints[k];
      p.position.copy(place(name, 1050));
      const il = A.Illumination(name, time);
      const eq = A.Equator(name, time, observer, true, true);
      const hor = A.Horizon(time, observer, eq.ra, eq.dec, 'normal');
      p.userData.mag = il.mag;
      return {name, mag: il.mag, alt: hor.altitude, az: hor.azimuth, ra: eq.ra * 15, dec: eq.dec, dist_au: il.geo_dist, phase: il.phase_fraction, pos: p.position};
    });
    updateLighting();
  }

  function updateLighting() {
    const pol = POLLUTION[view.pollution][0];
    // sky brightness: day > civil > nautical > astronomical twilight > night
    const day = THREE.MathUtils.smoothstep(sunAlt, -6, 4);
    const twilight = THREE.MathUtils.smoothstep(sunAlt, -18, -4);
    const moonUp = moonInfo && moonInfo.alt > 0 ? moonInfo.phase * Math.min(1, moonInfo.alt / 20) : 0;
    // naked-eye limiting magnitude: ~6.6 at a dark site, ~3.5 in a city, ~0 in daylight; zooming in adds a little
    let limit = 6.6 - 3.2 * pol - 1.6 * moonUp - 6.2 * twilight;
    limit = Math.max(-1.5, limit - 2.5 * day) + Math.max(0, Math.log2(70 / view.fov)) * .8;
    starMat.uniforms.limit.value = limit;
    mwMat.uniforms.strength.value = (1 - twilight) * (1 - pol * .9) * (1 - moonUp * .7);
    lineMat.uniforms.strength.value = view.layers.lines ? .24 * (1 - day) * (1 - twilight * .5) : 0;
    view.daylight = day;
    sky.visible = view.layers.atmosphere && sunAlt > -8;
    twilightMesh.visible = view.layers.atmosphere;
    sky.material.uniforms.turbidity.value = 2.2 + pol * 2.5;
    renderer.toneMappingExposure = .2 + .22 * (1 - day);
    const tu = twilightMesh.material.uniforms;
    tu.sun.value.copy(sky.material.uniforms.sunPosition.value);
    tu.sunAlt.value = sunAlt;
    tu.pollution.value = pol;
    tu.moon.value = moonUp * (1 - day);
    // night: city glow on the horizon, otherwise near-black ground lit by the sky
    const groundLight = new THREE.Color().setRGB(.006 + .05 * day + .01 * moonUp, .008 + .065 * day + .012 * moonUp, .01 + .04 * day + .016 * moonUp);
    horizonMat.uniforms.light.value.copy(groundLight);
    horizonMat.uniforms.glow.value.setRGB(.9 * pol * (1 - day), .55 * pol * (1 - day), .25 * pol * (1 - day));
    scene.background = new THREE.Color(0x000000);
    sunSprite.visible = view.layers.atmosphere ? true : sunAlt > -1;
    moonMesh.material.uniforms.fade.value = 1;
    moonMesh.userData.glow.material.opacity = (1 - day) * .9;
    for (const p of bodyPoints) {
      const b = Math.pow(10, -.4 * (p.userData.mag - limit));
      p.material.uniforms.alpha.value = THREE.MathUtils.clamp(b, 0, 1.4);
      p.material.uniforms.size.value = THREE.MathUtils.clamp(2.5 + 2.2 * Math.pow(Math.max(b, 0), .3), 2.5, 14) * zoomFactor();
    }
    starMat.uniforms.twinkle.value = 1 - day;
    ground.visible = view.layers.ground;
    gridGroup.visible = view.layers.grid;
  }

  const zoomFactor = () => THREE.MathUtils.clamp(Math.pow(70 / view.fov, .35), .8, 2.4);

  // ---------------------------------------------------------------------------------------------------------
  // labels (HTML), selection, readouts

  const labelPool = [];
  function label(i) {
    if (!labelPool[i]) { const d = document.createElement('span'); d.className = 'sky-label'; $('sky-labels').append(d); labelPool[i] = d; }
    return labelPool[i];
  }
  const tmp = new THREE.Vector3();
  function project(vEq, scene_ = false) {
    tmp.copy(vEq);
    if (!scene_) tmp.applyMatrix4(skyGroup.matrix);
    const alt = Math.asin(THREE.MathUtils.clamp(tmp.clone().normalize().y, -1, 1)) / DEG;
    tmp.project(camera);
    if (tmp.z > 1 || Math.abs(tmp.x) > 1.05 || Math.abs(tmp.y) > 1.05) return null;
    const r = renderer.domElement.getBoundingClientRect();
    return {x: (tmp.x * .5 + .5) * r.width, y: (-tmp.y * .5 + .5) * r.height, alt};
  }

  function drawLabels() {
    let n = 0;
    const put = (text, p, cls) => { if (!p) return; const el = label(n++); el.textContent = text; el.className = 'sky-label ' + cls; el.hidden = false; el.style.transform = `translate(${p.x.toFixed(1)}px,${p.y.toFixed(1)}px)`; };
    const lim = starMat.uniforms.limit.value;
    if (view.layers.labels) {
      for (const [ra, dec, mag, name] of data.named) {
        if (mag > Math.min(lim - 1.2, 1.4 + Math.log2(70 / view.fov) * 1.2)) continue;
        const p = project(eqVector(ra, dec, 1000)); if (p && p.alt > .5) put(name, p, 'star');
      }
      if (view.layers.lines && view.daylight < .5) for (const [, name, ra, dec, rank] of data.labels) {
        if (rank > (view.fov < 40 ? 3 : view.fov < 80 ? 2 : 1)) continue;
        const p = project(eqVector(ra, dec, 1000)); if (p && p.alt > 2) put(name.toUpperCase(), p, 'const');
      }
      if (view.fov < 60) for (const [m, alt, , mag, ra, dec] of data.dsos) {
        if (mag > lim) continue;
        const p = project(eqVector(ra, dec, 1000)); if (p && p.alt > 1) put(alt ? `${m} · ${alt}` : m, p, 'dso');
      }
      for (const b of bodyInfo) { const p = project(b.pos); if (p && p.alt > -.5 && b.mag < lim + 1) put(b.name, p, 'planet'); }
      if (moonInfo) { const p = project(moonInfo.pos); if (p && p.alt > -1) put('Moon', p, 'planet'); }
      const sp = project(sunSprite.position); if (sp && sp.alt > -1) put('Sun', sp, 'planet');
    }
    if (view.layers.targets) for (const [name, ra, dec] of TARGETS) {
      const p = project(eqVector(ra, dec, 1000)); if (p && p.alt > 0) put(name, p, 'target');
    }
    for (const [name, az] of [['N', 0], ['NE', 45], ['E', 90], ['SE', 135], ['S', 180], ['SW', 225], ['W', 270], ['NW', 315]]) {
      const v = new THREE.Vector3(Math.sin(az * DEG), .02, -Math.cos(az * DEG)).multiplyScalar(900);
      put(name, project(v, true), name.length === 1 ? 'cardinal' : 'cardinal minor');
    }
    for (let i = n; i < labelPool.length; i++) labelPool[i].hidden = true;
  }

  function readout() {
    const az = ((view.yaw % 360) + 360) % 360;
    const lim = starMat.uniforms.limit.value;
    const phase = sunAlt > -.833 ? 'Daytime' : sunAlt > -6 ? 'Civil twilight' : sunAlt > -12 ? 'Nautical twilight' : sunAlt > -18 ? 'Astronomical twilight' : 'Night';
    $('sky-readout').textContent = `Looking ${compass(az)} ${az.toFixed(0)}° · alt ${view.pitch.toFixed(0)}° · field ${view.fov.toFixed(0)}° · ${phase} · stars to mag ${lim.toFixed(1)}`;
    $('sky-when').textContent = view.time.toLocaleString(undefined, {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'})
      + ` · Sun ${sunAlt.toFixed(1)}°` + (view.live && view.speed === 1 ? ' · live' : '');
  }
  const compass = az => ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'][Math.round(az / 22.5) % 16];

  function pick(x, y) {
    let best = null, bestD = 16;
    const consider = (obj, v, isScene = false) => { const p = project(v, isScene); if (!p || p.alt < -1) return; const d = Math.hypot(p.x - x, p.y - y); if (d < bestD) { bestD = d; best = obj; } };
    for (const b of bodyInfo) consider({kind: 'planet', ...b}, b.pos);
    if (moonInfo) consider({kind: 'moon', ...moonInfo}, moonInfo.pos);
    for (const t of TARGETS) consider({kind: 'target', name: t[0], ra: t[1], dec: t[2]}, eqVector(t[1], t[2], 1000));
    for (const s of data.named) consider({kind: 'star', name: s[3], ra: s[0], dec: s[1], mag: s[2], con: s[4]}, eqVector(s[0], s[1], 1000));
    return best;
  }

  function showCard(o) {
    const card = $('sky-card');
    if (!o) { card.hidden = true; view.selected = null; return; }
    view.selected = o;
    const A = Astronomy, time = A.MakeTime(view.time);
    const hor = o.alt != null ? o : A.Horizon(time, observer, o.ra / 15, o.dec, 'normal');
    const rows = [['Altitude', `${hor.altitude?.toFixed?.(1) ?? hor.alt.toFixed(1)}°`], ['Azimuth', `${(hor.azimuth ?? hor.az).toFixed(1)}° (${compass(hor.azimuth ?? hor.az)})`],
      ['RA / Dec', `${(o.ra / 15).toFixed(3)} h / ${o.dec.toFixed(2)}°`]];
    if (o.mag != null) rows.push(['Magnitude', o.mag.toFixed(2)]);
    if (o.kind === 'moon') rows.push(['Illuminated', `${(o.phase * 100).toFixed(0)}%`], ['Distance', `${Math.round(o.dist_km).toLocaleString()} km`]);
    if (o.kind === 'planet') rows.push(['Distance', `${o.dist_au.toFixed(3)} AU`], ['Illuminated', `${(o.phase * 100).toFixed(0)}%`]);
    if (o.kind === 'planet' || o.kind === 'moon') {
      for (const [lbl, dir] of [['Rises', 1], ['Sets', -1]]) {
        try { const t = A.SearchRiseSet(o.name, observer, dir, time, 1); if (t) rows.push([lbl, t.date.toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit'})]); } catch { /* circumpolar */ }
      }
    }
    if (o.kind === 'target') {
      const alt = hor.altitude ?? hor.alt;
      rows.push(['Tonight', alt > 0 ? 'Above your horizon now' : 'Below your horizon now']);
    }
    card.innerHTML = `<header><span class="eyebrow">${{planet: 'PLANET', moon: 'MOON', star: 'STAR' + (o.con ? ' · ' + o.con : ''), target: 'SPHEREx STUDY TARGET'}[o.kind]}</span><h3>${o.name}</h3><button type="button" class="quiet" aria-label="Close">×</button></header>`
      + `<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`
      + (o.kind === 'target' ? '<p class="micro">One of the targets in the SPHEREx motion study. Its motion is far too small to see by eye; the study measures it in the images.</p>' : '');
    card.querySelector('button').onclick = () => showCard(null);
    card.hidden = false;
  }

  // ---------------------------------------------------------------------------------------------------------
  // controls

  function bindControls() {
    const canvas = $('sky-canvas');
    canvas.addEventListener('pointerdown', e => { view.drag = {x: e.clientX, y: e.clientY, yaw: view.yaw, pitch: view.pitch, moved: false}; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener('pointermove', e => {
      const d = view.drag; if (!d) return;
      const k = view.fov / canvas.clientHeight;
      if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 3) d.moved = true;
      view.yaw = d.yaw - (e.clientX - d.x) * k;
      view.pitch = THREE.MathUtils.clamp(d.pitch + (e.clientY - d.y) * k, -30, 90);
    });
    canvas.addEventListener('pointerup', e => {
      const d = view.drag; view.drag = null;
      if (d && !d.moved) { const r = canvas.getBoundingClientRect(); showCard(pick(e.clientX - r.left, e.clientY - r.top)); }
    });
    canvas.addEventListener('wheel', e => { e.preventDefault(); view.fovTarget = THREE.MathUtils.clamp(view.fovTarget * Math.exp(e.deltaY * .0012), 4, 120); }, {passive: false});
    let pinch = null;
    canvas.addEventListener('touchmove', e => {
      if (e.touches.length !== 2) { pinch = null; return; }
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      if (pinch) view.fovTarget = THREE.MathUtils.clamp(view.fovTarget * pinch / d, 4, 120);
      pinch = d; view.drag = null;
    }, {passive: true});
    window.addEventListener('keydown', e => {
      if (!view.open || /INPUT|SELECT/.test(document.activeElement?.tagName || '')) return;
      const step = view.fov / 20;
      if (e.key === 'ArrowLeft') view.yaw -= step; else if (e.key === 'ArrowRight') view.yaw += step;
      else if (e.key === 'ArrowUp') view.pitch = Math.min(90, view.pitch + step); else if (e.key === 'ArrowDown') view.pitch = Math.max(-30, view.pitch - step);
      else if (e.key === 'Escape') close(); else return;
      e.preventDefault();
    });
    $('sky-close').onclick = close;
    $('sky-locate').onclick = locate;
    $('sky-now').onclick = () => { view.time = new Date(); view.live = true; view.speed = 1; $('sky-speed').value = '1'; updateSky(true); };
    $('sky-speed').onchange = e => { view.speed = Number(e.target.value); view.live = view.speed === 1; };
    $('sky-speed').value = '1';
    for (const b of root.querySelectorAll('[data-step]')) b.onclick = () => { view.time = new Date(view.time.getTime() + Number(b.dataset.step) * 1000); view.live = false; updateSky(true); };
    for (const c of root.querySelectorAll('[data-layer]')) c.onchange = () => { view.layers[c.dataset.layer] = c.checked; updateLighting(); };
    $('sky-pollution').value = view.pollution;
    $('sky-pollution').onchange = e => { view.pollution = e.target.value; updateLighting(); };
    $('sky-apply').onclick = () => {
      const lat = Number($('sky-lat').value), lon = Number($('sky-lon').value);
      if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) setPlace(lat, lon, `${fmtCoord(lat, 'N', 'S')}, ${fmtCoord(lon, 'E', 'W')}`);
      const t = $('sky-datetime').value;
      if (t) { view.time = new Date(t); view.live = false; }
      updateSky(true);
    };
  }

  const fmtCoord = (v, p, n) => `${Math.abs(v).toFixed(2)}° ${v >= 0 ? p : n}`;
  function setPlace(lat, lon, name) {
    view.lat = lat; view.lon = lon; view.place = name;
    $('sky-place').textContent = name;
    $('sky-lat').value = lat.toFixed(4); $('sky-lon').value = lon.toFixed(4);
    try { localStorage.setItem('parallax-sky-place', JSON.stringify({lat, lon, name})); } catch { /* private mode */ }
    if (renderer) updateSky(true);
  }

  function locate() {
    if (!navigator.geolocation) { toast('Location is not available in this browser; enter latitude and longitude instead.'); return; }
    $('sky-place').textContent = 'Locating…';
    navigator.geolocation.getCurrentPosition(
      p => setPlace(p.coords.latitude, p.coords.longitude, `Your location · ${fmtCoord(p.coords.latitude, 'N', 'S')}, ${fmtCoord(p.coords.longitude, 'E', 'W')}`),
      () => { $('sky-place').textContent = view.place; toast('Location permission was not given; showing ' + view.place + '. Set it under Place & time.'); },
      {enableHighAccuracy: false, timeout: 10000, maximumAge: 600000});
  }

  function resize() {
    if (!renderer) return;
    const w = root.clientWidth || innerWidth, h = root.clientHeight || innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const px = renderer.getPixelRatio();
    starMat.uniforms.pixel.value = px;
    for (const p of bodyPoints) p.material.uniforms.pixel.value = px;
  }

  // ---------------------------------------------------------------------------------------------------------
  let last = 0, frame = 0;
  function tick(t) {
    if (!view.open) return;
    requestAnimationFrame(tick);
    const dt = Math.min(.1, (t - (last || t)) / 1000); last = t;
    if (view.live && view.speed === 1) view.time = new Date();
    else if (view.speed) view.time = new Date(view.time.getTime() + dt * 1000 * view.speed);
    view.fov += (view.fovTarget - view.fov) * (1 - Math.exp(-dt * 10));
    camera.fov = view.fov; camera.updateProjectionMatrix();
    camera.rotation.set(view.pitch * DEG, -view.yaw * DEG, 0);
    updateSky(view.speed > 60);
    starMat.uniforms.time.value = t / 1000;
    starMat.uniforms.zoom.value = zoomFactor();
    renderer.render(scene, camera);
    if ((frame++ & 1) === 0) { drawLabels(); readout(); }
  }

  async function open() {
    root.hidden = false;
    view.open = true;
    document.body.classList.add('sky-view-open');
    try {
      view.ready ||= init();
      await view.ready;
    } catch (error) {
      view.ready = null;
      toast(error.message);
      close();
      return;
    }
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('parallax-sky-place') || 'null'); } catch { /* ignore */ }
    if (saved) setPlace(saved.lat, saved.lon, saved.name); else { setPlace(view.lat, view.lon, view.place); locate(); }
    view.time = new Date(); view.live = true;
    resize();
    // face the brightest part of the sky to start: south-ish in the north, north-ish in the south
    view.yaw = view.lat >= 0 ? 180 : 0;
    updateSky(true);
    last = 0;
    requestAnimationFrame(tick);
  }

  function close() {
    view.open = false;
    root.hidden = true;
    document.body.classList.remove('sky-view-open');
  }

  return {open, close, view};
}
