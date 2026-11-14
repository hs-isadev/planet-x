const byId = id => document.getElementById(id);
const radians = Math.PI / 180;
const obliquity = 23.439291111 * radians;
const storageKey = 'planet-x-earth-targets-v1';

export function viewCoordinates({x, y, z}, ecliptic) {
  const east = -z, north = y;
  const equatorialY = ecliptic ? Math.cos(obliquity) * east - Math.sin(obliquity) * north : east;
  const equatorialZ = ecliptic ? Math.sin(obliquity) * east + Math.cos(obliquity) * north : north;
  return {
    ra: (Math.atan2(equatorialY, x) / radians + 360) % 360,
    dec: Math.atan2(equatorialZ, Math.hypot(x, equatorialY)) / radians,
  };
}

// Screen-space guidance for the selected catalog star before its illustrative close-up.
export function stellarMarkerSize(distancePc) {
  return Math.max(8, Math.min(24, 8 * Math.pow(1.2 / Math.max(distancePc, .01), .43)));
}

export function formatDirection({ra, dec}) {
  return 'RA ' + (Number(ra.toFixed(3)) % 360).toFixed(3) +
    '° · Dec ' + (dec >= 0 ? '+' : '') + dec.toFixed(3) + '°';
}

function savedTargets() {
  try {
    const records = JSON.parse(localStorage.getItem(storageKey) || '[]');
    return Array.isArray(records) ? records.filter(record => record && typeof record.key === 'string' &&
      typeof record.name === 'string' && typeof record.constellation === 'string' &&
      Number.isFinite(record.ra) && Number.isFinite(record.dec) &&
      Array.isArray(record.ecliptic) && record.ecliptic.length === 3 && record.ecliptic.every(Number.isFinite) &&
      Math.hypot(...record.ecliptic) > 0) : [];
  } catch {
    return [];
  }
}

export class EarthTargets {
  constructor(scene) {
    this.scene = scene;
    this.targets = new Map();
    this.cameraDirection = scene.camera.position.clone();
    this.aim = byId('look-direction');
    this.edge = byId('earth-targets-offscreen');
    this.layer = byId('earth-targets');
    this.popup = byId('earth-target-popup');
    this.chart = byId('earth-chart-target');
    this.chart.onclick = () => this.open(this.chartKey);
    byId('earth-target-close').onclick = () => this.popup.close();
    byId('earth-target-remove').onclick = () => this.remove(this.activeKey);
    for (const record of savedTargets()) this.add(record);
  }

  persist() {
    try {
      localStorage.setItem(storageKey, JSON.stringify([...this.targets.values()].map(({record}) => record)));
    } catch {
      // A blocked storage policy still allows pins for the current session.
    }
  }

  add(record) {
    const old = this.targets.get(record.key);
    if (old) {
      old.button.remove();
      this.targets.delete(record.key);
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'earth-target-marker';
    button.innerHTML = '<span class="earth-target-reticle" aria-hidden="true"></span><span></span>';
    button.lastElementChild.textContent = record.name;
    button.setAttribute('aria-label', 'Target: ' + record.name);
    button.onclick = () => this.open(record.key);
    this.edge.append(button);
    this.targets.set(record.key, {
      record, button, direction: this.scene.vector(record.ecliptic).normalize(),
      projected: this.cameraDirection.clone(),
    });
  }

  pin(key, name, context) {
    const {ra, dec, constellation, direction_ecliptic: ecliptic} = context;
    this.add({key, name, ra, dec, constellation, ecliptic});
    this.persist();
  }

  showChart(key) {
    this.chartKey = key;
    const target = this.targets.get(key);
    this.chart.hidden = !target;
    this.chart.setAttribute('aria-label', target ? 'Target: ' + target.record.name : 'Earth sky target');
    if (target) this.chart.lastElementChild.textContent = target.record.name;
  }

  open(key) {
    const target = this.targets.get(key);
    if (!target || this.popup.open) return;
    this.activeKey = key;
    const {record} = target;
    byId('earth-target-name').textContent = record.name;
    byId('earth-target-direction').textContent = formatDirection(record) + ' · ' + record.constellation;
    this.popup.showModal();
  }

  remove(key) {
    this.popup.close();
    this.targets.get(key)?.button.remove();
    this.targets.delete(key);
    this.activeKey = null;
    this.showChart(this.chartKey);
    this.persist();
    const fallback = byId('earth-sky').hidden ? this.aim : byId('journey-sky');
    fallback.focus({preventScroll: true});
  }

  update(now) {
    const {scene} = this;
    const applicable = scene.mode === 'solar' && !scene.surface && !scene.loading && this.targets.size > 0;
    this.layer.hidden = !applicable;
    this.edge.hidden = !applicable;
    if (!scene.surface && !scene.loading && scene.mode !== 'sizes' && now - (this.lastReadout ?? -Infinity) >= 100) {
      this.lastReadout = now;
      scene.camera.getWorldDirection(this.cameraDirection);
      const label = 'Looking at · ' + formatDirection(viewCoordinates(this.cameraDirection, scene.mode === 'solar'));
      if (this.aim.textContent !== label) this.aim.textContent = label;
      this.aim.hidden = false;
    } else if (scene.surface || scene.loading || scene.mode === 'sizes') this.aim.hidden = true;
    if (!applicable) return;

    scene.camera.getWorldDirection(this.cameraDirection);
    for (const {button, direction, projected} of this.targets.values()) {
      const ahead = direction.dot(this.cameraDirection) > 0;
      projected.copy(scene.camera.position).addScaledVector(direction, 10).project(scene.camera);
      const x = (projected.x * .5 + .5) * scene.w;
      const y = (.5 - projected.y * .5) * scene.h;
      const onScreen = ahead && projected.z >= -1 && projected.z <= 1 &&
        x > 25 && y > 24 && x < scene.w - 25 && y < scene.h - 24;
      const parent = onScreen ? this.layer : this.edge;
      if (button.parentElement !== parent) {
        const focused = button === document.activeElement;
        parent.append(button);
        if (focused) button.focus({preventScroll: true});
      }
      if (onScreen) {
        button.style.left = x + 'px';
        button.style.top = y + 'px';
        button.classList.toggle('label-left', x > scene.w * .67);
      }
    }
  }
}
