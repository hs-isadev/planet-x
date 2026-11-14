// Focus on individual small bodies in the 3D context: click a rock, pick a named asteroid,
// jump to a random one, or frame the whole belt. The camera follows the body along its orbit
// and the rock is replaced by a detailed, sunlit close-up model at its true size.
import * as THREE from 'three';
import {positionAt, rockGeometry} from './small-bodies.js';

const $ = id => document.getElementById(id);
const AU_KM = 149597870.7;
const GROUPS = {
  main: 'Main-belt asteroid', hilda: 'Hilda asteroid', near: 'Near-Earth asteroid',
  'mars-crosser': 'Mars-crossing asteroid', trojan: 'Jupiter Trojan', centaur: 'Centaur', kuiper: 'Kuiper belt object',
  plutino: 'Plutino', scattered: 'Scattered-disk object',
};
const TYPES = {S: 'S-type · stony', C: 'C-type · carbon-rich, dark', D: 'D-type · very dark, reddish', K: 'Icy, reddish surface', M: 'M-type · metallic'};
const GROUP_NOTES = {
  main: 'One of over a million main-belt asteroids larger than 1 km. Most orbit between Mars and Jupiter, where Jupiter’s gravity kept a planet from forming.',
  hilda: 'Hildas go around the Sun three times for every two Jupiter orbits. Together they trace a slowly rotating triangle.',
  near: 'Its orbit brings it within 1.3 AU of the Sun, close to Earth’s path. Surveys track these objects to rule out impacts.',
  'mars-crosser': 'Its orbit crosses Mars’s, so it will eventually be scattered by Mars or pushed into a near-Earth orbit.',
  trojan: 'It shares Jupiter’s orbit, leading or trailing it by 60° at a stable Lagrange point. NASA’s Lucy mission is touring these.',
  centaur: 'An icy body between the giant planets on an unstable orbit. Centaurs can become comets if pushed inward.',
  kuiper: 'An icy leftover from planet formation beyond Neptune. Most have barely changed in 4.5 billion years.',
  plutino: 'Like Pluto, it orbits the Sun twice for every three Neptune orbits, which keeps it safe from Neptune.',
  scattered: 'Neptune flung it onto a long, tilted, eccentric orbit. Many comets are thought to come from here.',
};

function fmtKm(km) { return km >= 10 ? `${Math.round(km * 2).toLocaleString('en-US')} km` : km >= 1 ? `${(km * 2).toFixed(1)} km` : `${Math.round(km * 2000)} m`; }
function ease(t) { return t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2; }

function closeUpMaterial(color) {
  return new THREE.MeshStandardMaterial({color: new THREE.Color(color), roughness: .96, metalness: 0, vertexColors: true,
    emissive: 0x0b0a09, emissiveIntensity: .35});
}

export function installAsteroidFocus(C) {
  const originalFly = C.prototype.fly, originalClear = C.prototype.clear, originalSolar = C.prototype.solar;

  C.prototype.fly = function (...args) {
    this.controls.halt?.();
    this.endSmallFocus();
    return originalFly.apply(this, args);
  };
  C.prototype.clear = function (...args) {
    this.endSmallFocus();
    return originalClear.apply(this, args);
  };
  C.prototype.solar = async function (...args) {
    const out = await originalSolar.apply(this, args);
    if (this.smallBodies) {
      this.smallBodies.setPixelRatio(this.renderer.getPixelRatio());
      if (this.dustPreference === false) this.smallBodies.setDust(false);
    }
    installUI(this);
    return out;
  };

  C.prototype.focusSmallBody = function (body) {
    const sb = this.smallBodies;
    if (!sb || !body || this.mode !== 'solar' || this.journey || this.surface) return;
    if (this.local) this.exitLocal();
    this.endSmallFocus(false);
    this.stopFlight();
    this.controls.halt?.();
    const radius = body.km / AU_KM;
    const seed = body.index + 1;
    const big = body.km > 150;
    const geometry = rockGeometry({seed, detail: 32, roughness: big ? .07 : body.shape === 'top' ? .12 : .26,
      craters: big ? 70 : 26, craterScale: big ? .35 : 1, shape: body.shape || ['potato', 'elong', 'potato', 'potato'][seed % 4]});
    const color = body.color || ({S: '#a48b72', C: '#5f5b57', D: '#6f5645', K: '#9a6c55', M: '#8f8a83'})[body.type] || '#7a7570';
    const rock = new THREE.Mesh(geometry, closeUpMaterial(color));
    rock.name = 'Small body close-up';
    rock.scale.setScalar(radius);
    rock.rotation.set(seed * .7, seed * 1.3, seed * .2);
    positionAt(body, this.orbitDays || 0, rock.position);
    this.content.add(rock);
    sb.hide(body.index);
    const savedMin = this.controls.minDistance, savedMax = this.controls.maxDistance;
    const fromTarget = this.controls.target.clone(), fromCamera = this.camera.position.clone();
    const startOffset = fromCamera.clone().sub(fromTarget);
    // Arrive on the day side, a little above the orbit plane, so the rock is lit.
    const sunward = rock.position.clone().normalize().negate();
    const endDir = sunward.clone().multiplyScalar(-.35).add(startOffset.clone().normalize()).add(new THREE.Vector3(0, .25, 0)).normalize();
    if (endDir.dot(sunward) < 0) endDir.addScaledVector(sunward, .9).normalize();
    const endDistance = radius * (body.shape === 'elong' || body.shape === 'bilobe' || body.shape === 'ellipsoid' ? 13 : 9);
    this.controls.minDistance = radius * 1.4;
    this.smallFocus = {body, rock, savedMin, savedMax, last: rock.position.clone(),
      anim: {start: performance.now(), duration: this.reduced ? 400 : 4200, fromTarget, fromCamera,
        fromDir: startOffset.clone().normalize(), endDir, fromDistance: Math.max(startOffset.length(), endDistance), endDistance}};
    showCard(this, body);
  };

  C.prototype.endSmallFocus = function (restore = true) {
    const f = this.smallFocus;
    if (!f) return;
    this.smallFocus = null;
    this.content.remove(f.rock);
    f.rock.geometry.dispose(); f.rock.material.dispose();
    this.smallBodies?.hide(-1);
    if (restore) { this.controls.minDistance = f.savedMin; this.controls.maxDistance = f.savedMax; }
    const card = $('small-body-card');
    if (card) card.classList.remove('sbc-on');
  };

  C.prototype.smallBodyTick = function (dt) {
    const f = this.smallFocus;
    if (!f || this.loading || this.journey || this.surface) return;
    const position = positionAt(f.body, this.orbitDays || 0, new THREE.Vector3());
    f.rock.position.copy(position);
    f.rock.rotation.y += dt * (f.body.spinRate || .35);
    if (f.anim) {
      const a = f.anim, k = Math.min(1, (performance.now() - a.start) / a.duration), t = ease(k);
      const target = a.fromTarget.clone().lerp(position, ease(Math.min(1, k * 1.6)));
      // Distance changes by a constant ratio per unit time, so the approach never feels like it lurches.
      const distance = a.fromDistance * Math.pow(a.endDistance / a.fromDistance, t);
      const dir = a.fromDir.clone().lerp(a.endDir, t).normalize();
      this.controls.target.copy(target);
      this.camera.position.copy(target).addScaledVector(dir, distance);
      this.zoomImpulse = 0;
      if (k >= 1) f.anim = null;
    } else {
      const delta = position.clone().sub(f.last);
      this.controls.target.add(delta);
      this.camera.position.add(delta);
    }
    f.last.copy(position);
    if (f.cardTick === undefined || performance.now() - f.cardTick > 400) { f.cardTick = performance.now(); updateCardDistances(this, f.body, position); }
  };

  C.prototype.randomSmallBody = function (filter) {
    const sb = this.smallBodies;
    if (!sb) return;
    const pool = sb.bodies.filter(b => b.group !== 'named' && (!filter || filter(b)));
    this.focusSmallBody(pool[Math.floor(Math.random() * pool.length)]);
  };

  C.prototype.viewAsteroidBelt = function () {
    if (this.mode !== 'solar' || !this.smallBodies) return;
    this.endSmallFocus();
    const target = new THREE.Vector3(0, 0, 0);
    const pos = new THREE.Vector3(2.6, 4.6, 6.4);
    this.fly(target, pos, 3200);
  };
}

function updateCardDistances(scene, body, position) {
  const sun = $('sbc-sun'), earth = $('sbc-earth');
  if (!sun) return;
  sun.textContent = `${position.length().toFixed(2)} AU`;
  const e = scene.items?.find(i => i.data.id === 'earth');
  earth.textContent = e ? `${position.distanceTo(e.pos).toFixed(2)} AU` : '—';
}

function showCard(scene, body) {
  const card = $('small-body-card');
  if (!card) return;
  const named = body.group === 'named';
  $('sbc-name').textContent = named ? body.name : `${GROUPS[body.group] || 'Small body'} · #${body.index + 1}`;
  $('sbc-kind').textContent = named ? body.type : TYPES[body.type] || '';
  $('sbc-note').textContent = named ? body.note : GROUP_NOTES[body.group] || '';
  const period = body.a ** 1.5;
  const rows = [
    ['Size', named ? fmtKm(body.km) : `~${fmtKm(body.km)}`],
    ['Orbit', `${body.a.toFixed(2)} AU · e ${body.e.toFixed(2)} · i ${(body.inc * 180 / Math.PI).toFixed(1)}°`],
    ['Year', period < 2 ? `${Math.round(period * 365.25)} days` : `${period.toFixed(period < 20 ? 1 : 0)} Earth years`],
    ['Perihelion', `${(body.a * (1 - body.e)).toFixed(2)} AU`],
    ['From Sun', '—', 'sbc-sun'], ['From Earth', '—', 'sbc-earth'],
  ];
  const list = $('sbc-facts');
  list.replaceChildren();
  for (const [label, value, id] of rows) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = value; if (id) dd.id = id;
    list.append(dt, dd);
  }
  $('sbc-source').textContent = named
    ? 'Orbit shape and size from published elements; the position along the orbit is illustrative.'
    : 'A statistical member of the real population. Its orbit and size are representative, not catalogued.';
  card.classList.remove('sbc-on'); void card.offsetWidth; card.classList.add('sbc-on');
}

function installUI(scene) {
  if (scene._smallBodyUI) return;
  scene._smallBodyUI = true;
  const stage = $('stage');
  if (!stage) return;

  const card = document.createElement('aside');
  card.id = 'small-body-card';
  card.setAttribute('aria-live', 'polite');
  card.innerHTML = '<p class="eyebrow" id="sbc-kind"></p><h3 id="sbc-name"></h3><p id="sbc-note"></p>' +
    '<dl id="sbc-facts"></dl><p class="micro" id="sbc-source"></p>' +
    '<div class="sbc-actions"><button type="button" id="sbc-random">Another random</button>' +
    '<button type="button" id="sbc-belt" class="quiet">Whole belt</button><button type="button" id="sbc-close" class="quiet" aria-label="Close">×</button></div>';
  stage.append(card);
  $('sbc-random').onclick = () => {
    const g = scene.smallFocus?.body.group;
    scene.randomSmallBody(g && g !== 'named' ? b => b.group === g : null);
  };
  $('sbc-belt').onclick = () => scene.viewAsteroidBelt();
  $('sbc-close').onclick = () => scene.endSmallFocus();

  // Controls in the Scale / orbit menu, right after the small-bodies toggle.
  const toggle = $('asteroids-toggle');
  if (toggle) {
    const box = document.createElement('div');
    box.className = 'small-body-tools';
    box.innerHTML = '<label>Fly to asteroid<select id="small-body-pick"><option value="">Choose…</option></select></label>' +
      '<div class="small-body-row"><button type="button" id="small-body-random">Random asteroid</button>' +
      '<button type="button" id="small-body-kbo">Random Kuiper object</button></div>' +
      '<div class="small-body-row"><button type="button" id="small-body-belt">Asteroid belt</button>' +
      '<button type="button" id="small-body-dust" aria-pressed="true">Dust on</button></div>' +
      '<p class="micro">Click any rock in the scene to follow it.</p>';
    toggle.after(box);
    const select = $('small-body-pick');
    for (const b of scene.smallBodies?.named || []) select.append(new Option(b.name, b.id));
    select.onchange = () => {
      const body = scene.smallBodies?.named.find(b => b.id === select.value);
      if (body) scene.focusSmallBody(body);
      select.value = '';
    };
    $('small-body-random').onclick = () => scene.randomSmallBody(b => ['main', 'near', 'hilda', 'trojan', 'mars-crosser'].includes(b.group));
    $('small-body-kbo').onclick = () => scene.randomSmallBody(b => ['kuiper', 'plutino', 'scattered'].includes(b.group));
    $('small-body-belt').onclick = () => scene.viewAsteroidBelt();
    $('small-body-dust').onclick = event => {
      const on = !(scene.smallBodies?.dustOn ?? true);
      scene.smallBodies?.setDust(on);
      scene.dustPreference = on;
      event.currentTarget.setAttribute('aria-pressed', String(on));
      event.currentTarget.textContent = on ? 'Dust on' : 'Dust off';
    };
  }

  // Click-to-focus. Runs in the capture phase so a rock click does not also select catalog stars.
  const canvas = scene.renderer.domElement;
  let down = null;
  canvas.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, true);
  canvas.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    if (scene.mode !== 'solar' || scene.local || scene.journey || scene.surface || scene.sunSky || !scene.smallBodies || scene.showSmallBodies === false) return;
    const r = canvas.getBoundingClientRect();
    const pointer = new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    scene.ray.setFromCamera(pointer, scene.camera);
    const hits = scene.ray.intersectObjects(scene.items.filter(x => x.model?.visible || x.mesh.visible).map(x => x.hit), true);
    if (hits.length) return;
    const body = scene.smallBodies.pick(scene.camera, [e.clientX - r.left, e.clientY - r.top], r.width, r.height, 9);
    if (!body || body.index === scene.smallFocus?.body.index) return;
    e.stopImmediatePropagation();
    scene.focusSmallBody(body);
  }, true);
}
