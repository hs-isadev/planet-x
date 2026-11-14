import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const StarLock = createRequire(import.meta.url)('../web/observation-lab/star-lock.js');

// A synthetic preview: grey background with one Gaussian star, blank corner, 8-bit stretched like the lab's PNGs.
function frame(size, x, y, peak = 220) {
  const data = new Uint8ClampedArray(size * size * 4);
  for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) {
    const r2 = (i - x) ** 2 + (j - y) ** 2, v = 12 + peak * Math.exp(-r2 / (2 * 1.2 ** 2));
    const k = (j * size + i) * 4;
    data[k] = data[k + 1] = data[k + 2] = Math.min(255, v);
    data[k + 3] = i < 6 && j < 6 ? 0 : 255;
  }
  return {width: size, height: size, data};
}

// 1. A star well off the field centre is found to sub-pixel accuracy.
const found = StarLock.detect(frame(98, 30.4, 61.7), {x: 48.5, y: 48.5}, 40);
assert.ok(found && Math.abs(found.x - 30.4) < 0.3 && Math.abs(found.y - 61.7) < 0.3, 'star near (30.4, 61.7)');

// 2. Nothing star-like: no lock instead of a made-up position.
assert.equal(StarLock.detect(frame(98, 30, 30, 0), {x: 30, y: 30}, 10), null);

// 3. A catalog rate moves the box by rate x elapsed days from the locked start.
const days = [0, 60, 120, 200, 300, 400];
const rate = {vx: 0, vy: -0.005};            // 0.005 px/day north
const items = days.map(t => ({t, image: frame(98, 40 + 0.0, 55 - 0.005 * t), prior: {x: 40, y: 55 - 0.005 * t}}));
const lock = StarLock.solve(items, {size: 98, catalogRate: rate});
assert.equal(lock.source, 'catalog');
const end = StarLock.positionAt(lock, 400);
assert.ok(Math.abs(end.y - 53) < 0.4 && Math.abs(end.x - 40) < 0.4, 'moved 2 px north over 400 days');

// 4. No catalog and no real motion: the star is found but the box stays put.
const still = days.map(t => ({t, image: frame(98, 62.2, 35.1), prior: null}));
const fixed = StarLock.solve(still, {size: 98});
assert.equal(fixed.source, 'stationary');
const a = StarLock.positionAt(fixed, 0), b = StarLock.positionAt(fixed, 400);
assert.ok(Math.hypot(a.x - 62.2, a.y - 35.1) < 0.4 && Math.hypot(a.x - b.x, a.y - b.y) < 1e-9);

// 5. A large drift with no catalog is measured from the span.
const drifting = [0, 50, 100, 150, 200, 250, 300, 350, 400].map(t => ({t, image: frame(98, 30 + 0.02 * t, 50), prior: null}));
const measured = StarLock.solve(drifting, {size: 98});
assert.equal(measured.source, 'measured');
assert.ok(Math.abs(StarLock.positionAt(measured, 400).x - 38) < 0.5);

console.log('PASS: star lock finds the star, anchors the span start, and moves it by catalog or measured drift.');
