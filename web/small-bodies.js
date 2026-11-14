import * as THREE from 'three';

// Solar System small bodies for the 3D context.
//
// What is real: the named bodies use approximate published orbital elements (a, e, i, node,
// argument of perihelion) and real sizes; the belt structure (Kirkwood gaps at the 3:1, 5:2,
// 7:3 and 2:1 Jupiter resonances, Hildas, Trojans at L4/L5, Plutinos at 39.4 AU, the cold
// classical Kuiper belt) follows the observed populations. What is illustrative: the unnamed
// rocks are a statistical sample, and positions along every orbit (the mean anomaly) are not
// ephemeris positions.

const tau = 2 * Math.PI, AU_KM = 149597870.7, DEG = Math.PI / 180;

export function randomFrom(seed) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
}

// a [AU], e, i [deg], node [deg], peri [deg], radius [km], spin period [h]
export const NAMED = [
  {id: 'ceres', name: '1 Ceres', a: 2.766, e: .0785, i: 10.59, node: 80.3, peri: 73.6, km: 470, spin: 9.07, shape: 'round', type: 'C-type · dwarf planet', color: '#77736d',
   note: 'The largest object in the main belt, about a third of its total mass. The bright spots in Occator crater are salt left by briny water. NASA’s Dawn orbited it from 2015 to 2018.'},
  {id: 'vesta', name: '4 Vesta', a: 2.362, e: .0886, i: 7.14, node: 103.8, peri: 151.2, km: 263, spin: 5.34, shape: 'vesta', type: 'V-type · basaltic protoplanet', color: '#a39a8c',
   note: 'A layered mini-planet with an iron core and a lava crust. A giant impact carved the 500 km Rheasilvia basin at its south pole. Dawn orbited it in 2011–2012. Vesta is one of the Parallax preset targets.'},
  {id: 'pallas', name: '2 Pallas', a: 2.773, e: .230, i: 34.8, node: 173.0, peri: 310.4, km: 256, spin: 7.81, shape: 'potato', type: 'B-type', color: '#7d7b78',
   note: 'Its orbit is tilted 35°, so it spends most of its time far above or below the rest of the belt. That makes it hard for spacecraft to reach.'},
  {id: 'hygiea', name: '10 Hygiea', a: 3.142, e: .112, i: 3.83, node: 283.2, peri: 312.3, km: 217, spin: 13.8, shape: 'round', type: 'C-type', color: '#615e5a',
   note: 'Nearly round in VLT images, so it may count as a dwarf planet. It is the largest member of a collision family in the outer belt.'},
  {id: 'psyche', name: '16 Psyche', a: 2.924, e: .134, i: 3.10, node: 150.0, peri: 229.0, km: 113, spin: 4.20, shape: 'potato', type: 'M-type · metal-rich', color: '#8f8a83',
   note: 'Rich in iron and nickel, possibly the exposed core of a shattered protoplanet. NASA’s Psyche spacecraft launched in October 2023 and is due to arrive in 2029.'},
  {id: 'eros', name: '433 Eros', a: 1.458, e: .223, i: 10.83, node: 304.3, peri: 178.9, km: 8.4, spin: 5.27, shape: 'elong', type: 'S-type · near-Earth', color: '#9f8a72',
   note: 'A 34 km long, peanut-shaped near-Earth asteroid. NEAR Shoemaker orbited it in 2000, then landed on it in 2001, the first landing on an asteroid.'},
  {id: 'bennu', name: '101955 Bennu', a: 1.126, e: .204, i: 6.03, node: 2.06, peri: 66.2, km: .245, spin: 4.30, shape: 'top', type: 'B-type · near-Earth rubble pile', color: '#4c4946',
   note: 'A loose pile of boulders shaped like a spinning top. OSIRIS-REx collected a sample in 2020 that landed in Utah in September 2023.'},
  {id: 'ryugu', name: '162173 Ryugu', a: 1.190, e: .190, i: 5.87, node: 251.3, peri: 211.6, km: .45, spin: 7.63, shape: 'top', type: 'Cb-type · near-Earth', color: '#454240',
   note: 'Another spinning-top rubble pile. Japan’s Hayabusa2 returned samples from it in December 2020, which contain amino acids and water-altered minerals.'},
  {id: 'apophis', name: '99942 Apophis', a: .922, e: .191, i: 3.34, node: 204.0, peri: 126.6, km: .17, spin: 30.6, shape: 'elong', type: 'Sq-type · near-Earth', color: '#8b7d6d',
   note: 'On 13 April 2029 it will pass about 32,000 km above Earth, closer than geostationary satellites and visible to the naked eye. There is no risk of impact for at least a century.'},
  {id: 'arrokoth', name: '486958 Arrokoth', a: 44.6, e: .04, i: 2.45, node: 158.9, peri: 174.4, km: 9, spin: 15.9, shape: 'bilobe', type: 'Cold classical Kuiper belt object', color: '#8a5a45',
   note: 'A reddish contact binary, two lobes that merged gently long ago. New Horizons flew past on 1 January 2019, the most distant object ever explored up close.'},
  {id: 'haumea', name: '136108 Haumea', a: 43.1, e: .195, i: 28.2, node: 122.2, peri: 239.0, km: 780, spin: 3.92, shape: 'ellipsoid', type: 'Dwarf planet · Kuiper belt', color: '#c9c5bd',
   note: 'Spins every 3.9 hours, so fast that it has stretched into an egg shape about twice as long as it is thick. It has a ring and two moons.'},
  {id: 'makemake', name: '136472 Makemake', a: 45.5, e: .16, i: 29.0, node: 79.6, peri: 297.0, km: 715, spin: 22.8, shape: 'round', type: 'Dwarf planet · Kuiper belt', color: '#b48c74',
   note: 'Covered in frozen methane, which gives it a reddish-brown tint. It has one small, dark moon.'},
  {id: 'eris', name: '136199 Eris', a: 67.9, e: .436, i: 44.0, node: 35.9, peri: 151.6, km: 1163, spin: 378, shape: 'round', type: 'Dwarf planet · scattered disk', color: '#d8d6d2',
   note: 'Almost the size of Pluto and a little more massive. Its discovery in 2005 led astronomers to define “dwarf planet” in 2006.'},
];

const GAPS = [[2.47, 2.53], [2.80, 2.84], [2.94, 2.97], [3.23, 3.31]];

export function smallBodyOrbits(jupiter, outer = true) {
  const random = randomFrom(140905);
  const range = (low, high) => low + (high - low) * random();
  const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(tau * random());
  const rayleigh = s => s * Math.sqrt(-2 * Math.log(1 - random()));
  // Power-law sizes: many small rocks, few big ones.
  const size = (min, max, slope = 2.3) => Math.min(max, min * Math.pow(1 - random(), -1 / slope));
  const bodies = [];
  const push = (group, a, e, inc, node, peri, km, extra = {}) => bodies.push({
    group, a, e: Math.min(.95, Math.max(0, e)), inc, node, peri, M0: range(0, tau), km,
    spin: range(0, tau), spinRate: range(.15, .9), ...extra,
  });

  for (let n = 0; n < 2600; n++) {
    let a;
    do { a = 2.06 + Math.pow(random(), 1.25) * 1.26; } while (GAPS.some(([lo, hi]) => a > lo && a < hi));
    const type = a < 2.5 ? (random() < .7 ? 'S' : 'C') : a < 2.82 ? (random() < .45 ? 'S' : 'C') : (random() < .15 ? 'S' : 'C');
    push('main', a, rayleigh(.07), Math.abs(gauss()) * .14, range(0, tau), range(0, tau), size(1, 80), {type});
  }
  for (let n = 0; n < 160; n++) push('hilda', 3.97 + gauss() * .04, range(.1, .3), rayleigh(.12), range(0, tau), range(0, tau), size(2, 60), {type: 'D'});
  for (let n = 0; n < 110; n++) push('near', range(.85, 1.9), range(.12, .6), rayleigh(.18), range(0, tau), range(0, tau), size(.05, 12, 1.8), {type: random() < .6 ? 'S' : 'C'});
  for (let n = 0; n < 24; n++) push('mars-crosser', range(1.6, 2.0), range(.2, .4), rayleigh(.2), range(0, tau), range(0, tau), size(.5, 15), {type: 'S'});
  if (jupiter) {
    const phase = Math.atan2(jupiter[1], jupiter[0]);
    for (const side of [-1, 1]) for (let n = 0; n < 220; n++) {
      const b = {group: 'trojan', a: 5.2 + gauss() * .05, e: rayleigh(.05), inc: rayleigh(.22), node: range(0, tau), peri: 0,
        M0: 0, km: size(3, 90), spin: range(0, tau), spinRate: range(.15, .9), type: 'D'};
      // Place the mean longitude 60° ahead of or behind Jupiter, with the observed libration spread.
      const lambda = phase + side * Math.PI / 3 + gauss() * .28;
      b.M0 = lambda - b.node - b.peri;
      bodies.push(b);
    }
  }
  for (let n = 0; n < 30; n++) push('centaur', range(6, 28), range(.1, .6), rayleigh(.3), range(0, tau), range(0, tau), size(5, 120), {type: 'D'});
  if (outer) {
    for (let n = 0; n < 650; n++) push('kuiper', range(42, 47.5), rayleigh(.05), rayleigh(.04), range(0, tau), range(0, tau), size(20, 200), {type: 'K'});
    for (let n = 0; n < 220; n++) push('kuiper', range(36, 48), rayleigh(.12), rayleigh(.28), range(0, tau), range(0, tau), size(20, 200), {type: 'K'});
    for (let n = 0; n < 170; n++) push('plutino', 39.4 + gauss() * .2, range(.08, .32), rayleigh(.2), range(0, tau), range(0, tau), size(20, 200), {type: 'K'});
    for (let n = 0; n < 120; n++) push('scattered', range(48, 110), range(.3, .7), rayleigh(.35), range(0, tau), range(0, tau), size(30, 250), {type: 'K'});
  }
  for (const b of bodies) b.rate = tau / (365.256 * b.a ** 1.5);
  for (const n of NAMED) bodies.push({
    group: 'named', ...n, inc: n.i * DEG, node: n.node * DEG, peri: n.peri * DEG,
    M0: range(0, tau), spinRate: Math.min(.7, 1.6 / Math.sqrt(n.spin)), spin: 0, rate: tau / (365.256 * n.a ** 1.5),
  });
  return bodies;
}

// Heliocentric ecliptic position -> scene axes (x, z, -y), the same convention as scene.vector().
export function positionAt(body, days, out = new THREE.Vector3()) {
  const M = body.M0 + days * body.rate;
  let E = M;
  for (let k = 0; k < (body.e > .3 ? 6 : 3); k++) E -= (E - body.e * Math.sin(E) - M) / (1 - body.e * Math.cos(E));
  const cx = body.a * (Math.cos(E) - body.e), cy = body.a * Math.sqrt(1 - body.e * body.e) * Math.sin(E);
  const cw = Math.cos(body.peri), sw = Math.sin(body.peri), cn = Math.cos(body.node), sn = Math.sin(body.node);
  const ci = Math.cos(body.inc), si = Math.sin(body.inc);
  const xo = cx * cw - cy * sw, yo = cx * sw + cy * cw;
  const X = xo * cn - yo * ci * sn, Y = xo * sn + yo * ci * cn, Z = yo * si;
  return out.set(X, Z, -Y);
}

// ---- rock shapes -------------------------------------------------------------------------
function hash3(x, y, z, seed) {
  let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(z | 0, 2147483647) ^ Math.imul(seed, 144665);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function valueNoise(x, y, z, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), xf = x - xi, yf = y - yi, zf = z - zi;
  const s = t => t * t * (3 - 2 * t), u = s(xf), v = s(yf), w = s(zf);
  let out = 0;
  for (let dx = 0; dx < 2; dx++) for (let dy = 0; dy < 2; dy++) for (let dz = 0; dz < 2; dz++)
    out += hash3(xi + dx, yi + dy, zi + dz, seed) * (dx ? u : 1 - u) * (dy ? v : 1 - v) * (dz ? w : 1 - w);
  return out * 2 - 1;
}
function fbm(x, y, z, seed, octaves) {
  let sum = 0, amp = .5, f = 1;
  for (let o = 0; o < octaves; o++) { sum += amp * valueNoise(x * f, y * f, z * f, seed + o * 17); f *= 2.03; amp *= .5; }
  return sum;
}

// Irregular rock geometry: noise-shaped surface plus bowl craters with raised rims.
// Shared-vertex sphere so close-up rocks shade smoothly (IcosahedronGeometry is unindexed).
function indexedSphere(detail) {
  const source = new THREE.IcosahedronGeometry(1, detail), p = source.attributes.position;
  const map = new Map(), vertices = [], index = [];
  for (let k = 0; k < p.count; k++) {
    const x = p.getX(k), y = p.getY(k), z = p.getZ(k);
    const key = `${Math.round(x * 1e5)},${Math.round(y * 1e5)},${Math.round(z * 1e5)}`;
    let id = map.get(key);
    if (id === undefined) { id = vertices.length / 3; map.set(key, id); vertices.push(x, y, z); }
    index.push(id);
  }
  source.dispose();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(index);
  return geometry;
}

export function rockGeometry({seed = 1, detail = 3, roughness = .28, craters = 18, shape = 'potato', craterScale = 1} = {}) {
  const geometry = detail >= 8 ? indexedSphere(detail) : new THREE.IcosahedronGeometry(1, detail);
  const random = randomFrom(seed * 7919 + 13);
  const pits = Array.from({length: craters}, () => {
    const z = random() * 2 - 1, t = random() * tau, r = Math.sqrt(1 - z * z);
    return {d: new THREE.Vector3(r * Math.cos(t), z, r * Math.sin(t)), size: (.08 + Math.pow(random(), 2.2) * .42) * craterScale, depth: (.25 + random() * .5) * Math.sqrt(craterScale)};
  });
  if (shape === 'vesta') pits.push({d: new THREE.Vector3(0, -1, 0), size: .95, depth: .55});
  const p = geometry.attributes.position, v = new THREE.Vector3(), colors = new Float32Array(p.count * 3);
  for (let k = 0; k < p.count; k++) {
    v.fromBufferAttribute(p, k).normalize();
    let r = 1 + roughness * fbm(v.x * 1.6 + 3, v.y * 1.6, v.z * 1.6, seed, 5);
    for (const c of pits) {
      const angle = Math.acos(Math.min(1, v.dot(c.d))) / c.size;
      if (angle < 1.35) r += c.size * c.depth * .22 * (angle < 1 ? angle * angle - 1 : .6 * Math.sin((angle - 1) / .35 * Math.PI));
    }
    let x = v.x * r, y = v.y * r, z = v.z * r;
    if (shape === 'elong') { x *= 1.9; y *= .78; z *= .82; }
    else if (shape === 'potato') { x *= 1.18; y *= .88; }
    else if (shape === 'ellipsoid') { x *= 1.55; y *= .62; z *= 1.05; }
    else if (shape === 'top') { const k2 = 1 - .32 * Math.abs(y); x *= k2 * 1.05; z *= k2 * 1.05; y *= .92; }
    else if (shape === 'bilobe') { const big = x > 0; const s = big ? 1 : .72; x = x * s * .62 + (big ? .55 : -.5); y *= s * .62; z *= s * .48; }
    p.setXYZ(k, x, y, z);
    const tone = .86 + .14 * fbm(v.x * 4, v.y * 4, v.z * 4, seed + 99, 3) + .12 * (r - 1);
    colors[k * 3] = colors[k * 3 + 1] = colors[k * 3 + 2] = Math.max(.55, Math.min(1.15, tone));
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

const TYPE_COLORS = {
  S: ['#a48b72', '#b09479', '#9a8673'], C: ['#5d5a56', '#6a6661', '#54514e'], D: ['#6f5645', '#7a604c'],
  K: ['#9a6c55', '#a98a78', '#8c7b70'], M: ['#8f8a83'],
};

// ---- zodiacal and belt dust with sunlight scattering ---------------------------------------
function createDust(random) {
  const count = 42000, pos = new Float32Array(count * 3), bright = new Float32Array(count), size = new Float32Array(count);
  const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(tau * random());
  for (let n = 0; n < count; n++) {
    const kind = random();
    let r, h, b;
    if (kind < .62) { r = .25 + Math.pow(random(), .8) * 3.3; h = gauss() * .12 * r; b = .55; }           // zodiacal cloud
    else if (kind < .93) {                                                                                   // belt dust bands
      do { r = 2.06 + random() * 1.3; } while (GAPS.some(([lo, hi]) => r > lo && r < hi));
      h = gauss() * .16 * r; b = .8;
    } else { r = 39 + random() * 9; h = gauss() * .05 * r; b = 4; }                                          // Kuiper dust
    const t = random() * tau;
    pos[n * 3] = r * Math.cos(t); pos[n * 3 + 1] = h; pos[n * 3 + 2] = r * Math.sin(t);
    bright[n] = b * (.5 + random()); size[n] = 2.5 + random() * 5.5;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geometry.setAttribute('bright', new THREE.BufferAttribute(bright, 1));
  geometry.setAttribute('size', new THREE.BufferAttribute(size, 1));
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: {pixel: {value: 1}, strength: {value: 1}},
    vertexShader: `
      attribute float bright; attribute float size; uniform float pixel; uniform float strength; varying float vAlpha;
      // Henyey-Greenstein phase function: how strongly dust scatters sunlight toward the viewer.
      float hg(float g, float c) { return (1. - g * g) / pow(1. + g * g - 2. * g * c, 1.5); }
      void main() {
        vec4 world = modelMatrix * vec4(position, 1.);
        vec3 fromSun = normalize(world.xyz);
        vec3 toEye = normalize(cameraPosition - world.xyz);
        float c = dot(fromSun, -toEye);                // 1 = looking at the dust against the Sun (forward scatter)
        float phase = .78 * hg(.62, c) + .22 * hg(-.28, c);   // strong forward lobe + gegenschein back lobe
        float r = max(length(world.xyz), .3);
        vec4 view = viewMatrix * world;
        float d = -view.z;
        // Illumination falls as 1/r²; a gentler r^-1.2 display stretch keeps the outer dust faintly visible.
        vAlpha = min(.09, strength * bright * phase * pow(r, -1.2) * .05) * smoothstep(0., .02, d);
        gl_PointSize = size * pixel;
        gl_Position = projectionMatrix * view;
      }`,
    fragmentShader: `
      varying float vAlpha;
      void main() {
        vec2 q = gl_PointCoord - .5; float e = 1. - smoothstep(.1, .5, length(q));
        gl_FragColor = vec4(vec3(1., .93, .82) * vAlpha * e, 1.);
      }`,
  });
  const points = new THREE.Points(geometry, material);
  points.name = 'Interplanetary dust (illustrative)';
  points.frustumCulled = false;
  points.renderOrder = -1;
  return points;
}

export function createSmallBodies(jupiter) {
  const bodies = smallBodyOrbits(jupiter);
  const random = randomFrom(77);
  const group = new THREE.Group();
  group.name = 'Solar System small bodies';
  const variants = [0, 1, 2, 3].map(k => rockGeometry({seed: 11 + k, detail: 1, roughness: .32, craters: 6, shape: k === 2 ? 'elong' : 'potato'}));
  const material = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 1, metalness: 0, flatShading: true, vertexColors: true,
    emissive: 0x1a1612, emissiveIntensity: .55});
  const slots = variants.map(() => []);
  bodies.forEach((b, index) => { b.index = index; b.variant = b.group === 'named' ? 0 : index % 4; slots[b.variant].push(b); });
  const meshes = variants.map((geometry, k) => {
    const mesh = new THREE.InstancedMesh(geometry, material, slots[k].length);
    mesh.frustumCulled = false;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    slots[k].forEach((b, slot) => {
      b.slot = slot;
      const palette = b.color ? [b.color] : TYPE_COLORS[b.type] || TYPE_COLORS.C;
      const c = new THREE.Color(palette[slot % palette.length]);
      mesh.setColorAt(slot, b.group === 'named' ? c.multiplyScalar(1.25) : c);
    });
    group.add(mesh);
    return mesh;
  });
  const dust = createDust(random);
  group.add(dust);

  const dummy = new THREE.Object3D(), temp = new THREE.Vector3(), camera = new THREE.Vector3();
  let hidden = -1, lastTick = -Infinity, pixelRatio = 1, dustOn = true;
  for (const b of bodies) b.pos = new THREE.Vector3();

  function update(days, now, overviewDistance = 0, cameraPosition = null, viewHeight = 800, fov = 38) {
    if (!group.visible || now - lastTick < 16) return;
    lastTick = now;
    if (cameraPosition) camera.copy(cameraPosition);
    // Rocks keep a minimum apparent size (≈2 px) but grow to their true size when you are close.
    const perPixel = 2 * Math.tan(fov * DEG / 2) / Math.max(1, viewHeight);
    for (const b of bodies) {
      // Distant bodies barely move between frames; only re-solve the orbit when the change is visible.
      if (b.lastDays === undefined || Math.abs(days - b.lastDays) * b.rate > 2e-4) { positionAt(b, days, b.pos); b.lastDays = days; }
      const mesh = meshes[b.variant];
      const trueRadius = b.km / AU_KM;
      const distance = cameraPosition ? b.pos.distanceTo(camera) : overviewDistance;
      const minPx = b.group === 'named' ? 2.6 : b.group === 'kuiper' || b.group === 'plutino' || b.group === 'scattered' ? 1.15 : 1.35;
      const scale = b.index === hidden ? 0 : Math.max(trueRadius, distance * perPixel * minPx);
      dummy.position.copy(b.pos);
      dummy.rotation.set(b.spin, b.spin * 1.7 + days * b.spinRate * .2, b.spin * .7);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      mesh.setMatrixAt(b.slot, dummy.matrix);
    }
    for (const mesh of meshes) mesh.instanceMatrix.needsUpdate = true;
    dust.visible = dustOn;
    dust.rotation.y = days * tau / (365.256 * 2.4 ** 1.5);
    dust.material.uniforms.pixel.value = pixelRatio;
  }

  // Screen-space pick: nearest body within `radius` pixels of the pointer.
  function pick(camera3, pointerPx, width, height, radius = 10) {
    let best = null, bestD = radius;
    for (const b of bodies) {
      temp.copy(b.pos).project(camera3);
      if (temp.z < -1 || temp.z > 1) continue;
      const x = (temp.x * .5 + .5) * width, y = (-temp.y * .5 + .5) * height;
      const d = Math.hypot(x - pointerPx[0], y - pointerPx[1]) - (b.group === 'named' ? 4 : 0);
      if (d < bestD) { bestD = d; best = b; }
    }
    return best;
  }

  update(0, 0);
  group.dispose = () => { variants.forEach(g => g.dispose()); material.dispose(); dust.geometry.dispose(); dust.material.dispose(); meshes.forEach(m => m.dispose()); };
  return {
    mesh: group, update, pick, bodies,
    named: bodies.filter(b => b.group === 'named'),
    hide(index) { hidden = index; lastTick = -Infinity; },
    setDust(on) { dustOn = on; dust.visible = on; },
    get dustOn() { return dustOn; },
    setPixelRatio(value) { pixelRatio = value; },
  };
}
