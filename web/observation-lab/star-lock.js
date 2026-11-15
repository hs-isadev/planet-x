"use strict";
/*
 * StarLock: find where the target star is in a SPHEREx preview and estimate how far it moved.
 *
 * The lab used to draw the "Expected position" box from the catalog position alone. That put the box on the
 * field centre whenever the catalog had no proper motion (or the star had drifted away from the catalog epoch),
 * and the box never visibly moved. Here we
 *   1. find the star's centre with a small matched filter (Gaussian smoothing, brightest peak near a prior,
 *      sub-pixel weighted centroid) in a handful of frames spread across the time span,
 *   2. lock the box to the start of the time span, and
 *   3. move it by velocity x elapsed time. Velocity is the catalog proper motion when there is one, otherwise
 *      the slope of the measured centres, otherwise zero (a star that did not measurably move).
 * Nothing is traced: the box follows a straight line fitted over the whole span, not each frame's noise.
 *
 * Positions are in preview pixel units (centre of the first pixel is 0, 0). Time is in days.
 */
(function (root) {
  const SIGMA = 1.0;            // PSF-sized smoothing, in preview pixels (~6 arcsec per pixel)
  const MIN_STRENGTH = 0.12;    // smoothed peak above background, as a fraction of the remaining 8-bit range
  const YEAR = 365.25;

  function kernel(sigma) {
    const half = Math.max(1, Math.ceil(sigma * 3));
    const values = [];
    for (let i = -half; i <= half; i++) values.push(Math.exp(-(i * i) / (2 * sigma * sigma)));
    const total = values.reduce((a, b) => a + b, 0);
    return values.map(v => v / total);
  }

  // Separable Gaussian blur; invalid pixels are filled with the background first so they never form a peak.
  function smooth(values, width, height, sigma) {
    const k = kernel(sigma), half = (k.length - 1) / 2;
    const pass = new Float32Array(values.length), out = new Float32Array(values.length);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let i = -half; i <= half; i++) sum += k[i + half] * values[y * width + Math.min(width - 1, Math.max(0, x + i))];
      pass[y * width + x] = sum;
    }
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let i = -half; i <= half; i++) sum += k[i + half] * pass[Math.min(height - 1, Math.max(0, y + i)) * width + x];
      out[y * width + x] = sum;
    }
    return out;
  }

  function median(values) {
    if (!values.length) return NaN;
    const sorted = [...values].sort((a, b) => a - b), mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  /**
   * image: {width, height, data}, data is RGBA bytes (the lab's preview PNG: grey level in R, alpha 0 = no data).
   * prior: {x, y} pixel coordinates to search around.   radius: search radius in pixels.
   * Returns {x, y, strength} or null when nothing star-like is there.
   */
  // A saturated star has no usable pixels in its core, so the preview shows a hole ringed by bright pixels. Left as
  // background, the brightest point would be one side of the ring and the lock would sit off-centre. Small enclosed
  // holes whose rim is bright are filled as saturated (255) so the star is found at its middle.
  function fillSaturatedHoles(grey, valid, width, height, background) {
    const seen = new Uint8Array(width * height), bright = background + 0.5 * (255 - background);
    for (let start = 0; start < width * height; start++) {
      if (valid[start] || seen[start]) continue;
      const stack = [start], part = [];
      let edge = false, rimSum = 0, rimCount = 0;
      seen[start] = 1;
      while (stack.length) {
        const k = stack.pop(), x = k % width, y = (k - x) / width;
        part.push(k);
        if (x === 0 || y === 0 || x === width - 1 || y === height - 1) edge = true;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const n = ny * width + nx;
          if (valid[n]) { rimSum += grey[n]; rimCount++; }
          else if (!seen[n]) { seen[n] = 1; stack.push(n); }
        }
      }
      if (!edge && part.length <= 400 && rimCount && rimSum / rimCount > bright) {
        for (const k of part) { grey[k] = 255; valid[k] = 1; }
      }
    }
  }

  function detect(image, prior, radius) {
    const {width, height, data} = image;
    const grey = new Float32Array(width * height), valid = new Uint8Array(width * height);
    const samples = [];
    for (let i = 0; i < width * height; i++) {
      grey[i] = data[i * 4];
      valid[i] = data[i * 4 + 3] > 0 ? 1 : 0;
      if (valid[i]) samples.push(grey[i]);
    }
    if (samples.length < width * height * 0.25) return null;
    const background = median(samples);
    fillSaturatedHoles(grey, valid, width, height, background);
    for (let i = 0; i < grey.length; i++) if (!valid[i]) grey[i] = background;
    const smoothed = smooth(grey, width, height, SIGMA);
    const range = Math.max(1, 255 - background);
    let best = null;
    const r2 = radius * radius;
    const x0 = Math.max(1, Math.floor(prior.x - radius)), x1 = Math.min(width - 2, Math.ceil(prior.x + radius));
    const y0 = Math.max(1, Math.floor(prior.y - radius)), y1 = Math.min(height - 2, Math.ceil(prior.y + radius));
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const dx = x - prior.x, dy = y - prior.y;
      if (dx * dx + dy * dy > r2 || !valid[y * width + x]) continue;
      const v = smoothed[y * width + x];
      let isMax = true;
      for (let j = -1; j <= 1 && isMax; j++) for (let i = -1; i <= 1; i++) {
        if ((i || j) && smoothed[(y + j) * width + x + i] > v) { isMax = false; break; }
      }
      if (!isMax) continue;
      const strength = (v - background) / range;
      // Among comparable peaks, prefer the one closer to the prior so a bright neighbour cannot steal the lock.
      const score = strength - 0.15 * Math.sqrt(dx * dx + dy * dy) / Math.max(1, radius);
      if (!best || score > best.score) best = {x, y, strength, score};
    }
    if (!best || best.strength < MIN_STRENGTH) return null;
    // Sub-pixel centroid of the background-subtracted, unsmoothed pixels around the peak.
    let sw = 0, sx = 0, sy = 0;
    for (let j = -2; j <= 2; j++) for (let i = -2; i <= 2; i++) {
      const x = best.x + i, y = best.y + j;
      if (x < 0 || y < 0 || x >= width || y >= height || !valid[y * width + x]) continue;
      const w = Math.max(0, grey[y * width + x] - background);
      sw += w; sx += w * x; sy += w * y;
    }
    if (sw <= 0) return null;
    return {x: sx / sw, y: sy / sw, strength: best.strength};
  }

  // Theil-Sen slope: robust to a few bad frames. Returns {slope, intercept} for y = intercept + slope * t.
  function robustLine(ts, ys) {
    const slopes = [];
    for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
      if (Math.abs(ts[j] - ts[i]) > 1e-9) slopes.push((ys[j] - ys[i]) / (ts[j] - ts[i]));
    }
    const slope = slopes.length ? median(slopes) : 0;
    const intercept = median(ys.map((y, i) => y - slope * ts[i]));
    return {slope, intercept};
  }

  /**
   * samples: [{t, x, y}] measured star centres (t in days). t0: the reference time (start of the span), days.
   * catalogRate: optional {vx, vy} in pixels per day (catalog proper motion on the preview grid).
   * Returns {x0, y0, vx, vy, source, count, spanDays}; velocities in pixels per day.
   */
  function fitMotion(samples, t0, catalogRate) {
    if (!samples.length) return null;
    const ts = samples.map(s => s.t - t0), xs = samples.map(s => s.x), ys = samples.map(s => s.y);
    const span = Math.max(...ts) - Math.min(...ts);
    let vx = 0, vy = 0, source = 'stationary';
    if (catalogRate && Number.isFinite(catalogRate.vx) && Number.isFinite(catalogRate.vy) &&
        Math.hypot(catalogRate.vx, catalogRate.vy) > 0) {
      vx = catalogRate.vx; vy = catalogRate.vy; source = 'catalog';
    } else if (samples.length >= 4 && span >= 30) {
      const fx = robustLine(ts, xs), fy = robustLine(ts, ys);
      const resid = ts.map((t, i) => Math.hypot(xs[i] - (fx.intercept + fx.slope * t), ys[i] - (fy.intercept + fy.slope * t)));
      const rms = Math.sqrt(resid.reduce((sum, r) => sum + r * r, 0) / resid.length);
      const moved = Math.hypot(fx.slope, fy.slope) * span;
      // Centres from different detectors are offset by a few pixels, so only believe a drift that is large
      // next to that scatter. Anything smaller is reported as stationary rather than invented.
      if (moved >= Math.max(2.5, 4 * rms)) { vx = fx.slope; vy = fy.slope; source = 'measured'; }
    }
    // Lock the start of the span to the measured centres: remove the expected motion, keep the typical remainder.
    const x0 = median(xs.map((x, i) => x - vx * ts[i]));
    const y0 = median(ys.map((y, i) => y - vy * ts[i]));
    return {x0, y0, vx, vy, source, count: samples.length, spanDays: span};
  }

  function positionAt(lock, tDays) {
    const dt = tDays - lock.t0;
    return {x: lock.x0 + lock.vx * dt, y: lock.y0 + lock.vy * dt};
  }

  /**
   * items: [{t, image, prior}] one per observing date, sorted by time. t is in days, prior is the catalog
   * position {x, y} on that frame's grid or null when the catalog gives none.
   * options: {size, catalogRate (px/day or null), maxSamples}
   * Returns a lock {t0, x0, y0, vx, vy, source, count} or null when the star cannot be found.
   */
  function solve(items, options) {
    const size = options.size, hasCatalog = items.some(item => item.prior);
    const maxSamples = options.maxSamples || 16;
    if (!items.length) return null;
    const picked = items.length <= maxSamples ? items
      : Array.from({length: maxSamples}, (_, i) => items[Math.round(i * (items.length - 1) / (maxSamples - 1))]);
    const centre = {x: (size - 1) / 2, y: (size - 1) / 2};
    let detections;
    if (hasCatalog) {
      // The catalog says roughly where the star is on each date; look within a few pixels of that.
      detections = picked.map(item => item.prior && {item, ...(detect(item.image, item.prior, 6) || {})}).filter(d => d && d.x != null);
      if (detections.length >= 3) {
        const dx = median(detections.map(d => d.x - d.item.prior.x)), dy = median(detections.map(d => d.y - d.item.prior.y));
        detections = detections.filter(d => Math.hypot(d.x - d.item.prior.x - dx, d.y - d.item.prior.y - dy) <= 2.5);
      }
    } else {
      // No catalog motion: take the brightest compact source near the field centre, then keep the ones that agree.
      const radius = Math.min(40, Math.max(10, 0.2 * size));
      const first = picked.map(item => ({item, ...(detect(item.image, centre, radius) || {})})).filter(d => d.x != null);
      if (first.length < 2) return null;
      const mx = median(first.map(d => d.x)), my = median(first.map(d => d.y));
      detections = picked.map(item => ({item, ...(detect(item.image, {x: mx, y: my}, 4) || {})})).filter(d => d.x != null);
    }
    if (detections.length < 2) return null;
    const t0 = items[0].t;
    const fit = fitMotion(detections.map(d => ({t: d.item.t, x: d.x, y: d.y})), t0,
                          hasCatalog ? options.catalogRate : null);
    return fit && Object.assign(fit, {t0, strength: median(detections.map(d => d.strength))});
  }

  const api = {detect, fitMotion, positionAt, solve, robustLine, smooth, YEAR};
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.StarLock = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
