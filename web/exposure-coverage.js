import {chronological, sameCalibrationRelease} from './exposure-sequence.js';

const colors = ['#b579d4', '#678ce5', '#258fbb', '#339681', '#b9893e', '#bd6260'];
const $ = id => document.getElementById(id);
const wavelength = frame => Number.isFinite(frame?.wavelength_um);
const date = frame => frame.date.slice(0, 10);
const label = frame => date(frame) + ' · D' + frame.detector + ' · ' + frame.release.toUpperCase() +
  (wavelength(frame) ? ' · ' + frame.wavelength_um.toFixed(3) + ' µm' : ' · wavelength unavailable');

export function matchingEpochs(frames, anchor) {
  if (!wavelength(anchor)) return [];
  return frames.filter(frame => frame?.status === 'ready' && frame.id !== anchor.id &&
    frame.detector === anchor.detector && sameCalibrationRelease(frame.release, anchor.release) &&
    Math.abs(frame.mjd - anchor.mjd) >= 1 && wavelength(frame) &&
    Math.abs(frame.wavelength_um - anchor.wavelength_um) <= .025);
}

export function coverageCSV(frames) {
  const rows = [['exposure_id','date_utc','mjd','release','detector','field_center_wavelength_um','usable_pixel_fraction','status','original_fits_url']];
  for (const frame of chronological(frames)) rows.push([
    frame.id, frame.date, frame.mjd, frame.release, frame.detector, frame.wavelength_um,
    frame.valid_fraction, frame.status, frame.url
  ]);
  return rows.map(row => row.map(value => '"' + String(value ?? '').replaceAll('"', '""') + '"').join(',')).join('\r\n') + '\r\n';
}

export function installExposureCoverage(view) {
  const panel = $('exposure-coverage');
  const canvas = $('coverage-plot');
  const context = canvas.getContext('2d');
  const list = $('coverage-exposure');
  const match = $('coverage-match');
  const clear = $('coverage-clear');
  const blink = $('coverage-blink');
  const exportButton = $('coverage-export');
  const measure = $('coverage-measure');
  const measureStatus = $('coverage-measure-status');
  const difference = $('coverage-difference');
  const status = $('coverage-status');
  let pinned = null, jobId, dataKey, hovered, scheduled = false, points = [];
  let blinkPair = null, measuredKey, comparing = false;

  function clearMeasurement(){
    measuredKey = null;
    measureStatus.textContent = "";
    difference.hidden = true;
  }

  function openExposure(id) {
    if (!id) return;
    view.selectExposure(id);
  }

  function draw() {
    const job = view.job;
    const current = view.current();
    if (jobId !== view.jobId) {
      jobId = view.jobId;
      pinned = null;
      hovered = null;
      blinkPair = null;
      clearMeasurement();
    }
    match.disabled = !wavelength(current);
    clear.hidden = !pinned;
    if (!view.blinking) blinkPair = null;
    blink.hidden = !pinned;
    blink.textContent = view.blinking ? "Stop blink" : "Blink selected pair";
    const ready = chronological((job?.frames || []).filter(frame => frame.status === 'ready'));
    const available = pinned ? matchingEpochs(ready, pinned) : ready;
    const shown = pinned ? chronological([pinned, ...available]) : available;
    const canCompare = available.some(frame => frame.id === current?.id);
    blink.disabled = !view.blinking && !canCompare;
    measure.hidden = !pinned;
    measure.disabled = comparing || view.blinking || !canCompare;
    if (measuredKey && !view.blinking && measuredKey !== pinned?.id + ":" + current?.id) clearMeasurement();
    const nextKey = jobId + ':' + (pinned?.id || '') + ':' + shown.map(frame => frame.id).join(',');
    if (nextKey !== dataKey) {
      dataKey = nextKey;
      list.replaceChildren(new Option('Select an exposure…', ''), ...shown.map(frame => new Option(label(frame), frame.id)));
    }
    list.value = shown.some(frame => frame.id === current?.id) ? current.id : '';
    list.disabled = !shown.length;
    exportButton.disabled = !job?.frames.length;

    const onPlot = shown.filter(wavelength);
    const pending = job?.frames.filter(frame => !['ready', 'error'].includes(frame.status)).length || 0;
    const failed = job?.failed || 0;
    status.textContent = blinkPair && view.blinking
      ? 'Blinking ' + blinkPair.map(label).join(' ↔ ') + '. Looking for a consistent position shift. Brightness changes alone do not establish motion.'
      : pinned
      ? available.length + ' matching exposures for ' + label(pinned) + '. Same detector, within 0.025 µm, at least one day apart. Wavelengths are measured at the field center.'
      : ready.length + ' loaded · ' + onPlot.length + ' with a field-center wavelength · ' + pending + ' loading · ' + failed + ' unavailable.';
    if (hovered && shown.some(frame => frame.id === hovered.id)) {
      $('coverage-point').textContent = label(hovered);
    } else {
      $('coverage-point').textContent = current ? label(current) : '';
    }

    const width = Math.max(240, Math.round(canvas.clientWidth || canvas.width));
    const height = 210;
    const density = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * density) || canvas.height !== height * density) {
      canvas.width = Math.round(width * density);
      canvas.height = Math.round(height * density);
    }
    context.setTransform(density, 0, 0, density, 0, 0);
    context.clearRect(0, 0, width, height);
    points = [];
    const style = getComputedStyle(panel);
    const muted = style.getPropertyValue('--muted').trim();
    const line = style.getPropertyValue('--line').trim();
    const text = style.getPropertyValue('--text').trim();
    context.font = '11px ' + style.getPropertyValue('--mono');
    context.fillStyle = muted;
    if (!onPlot.length) {
      context.fillText('No ready exposures with a wavelength.', 14, 30);
      return;
    }

    const left = 52, right = width - 18, top = 16, bottom = 166;
    const lowDate = Math.min(...onPlot.map(frame => frame.mjd));
    const highDate = Math.max(...onPlot.map(frame => frame.mjd));
    const lowWave = pinned ? pinned.wavelength_um - .027 : .7;
    const highWave = pinned ? pinned.wavelength_um + .027 : 5.1;
    const xAt = mjd => lowDate === highDate ? (left + right) / 2 :
      left + (mjd - lowDate) / (highDate - lowDate) * (right - left);
    const yAt = wave => bottom - (wave - lowWave) / (highWave - lowWave) * (bottom - top);
    context.strokeStyle = line;
    context.fillText('µm', 7, 15);
    const waveTicks = pinned ? [-.025, 0, .025].map(offset => pinned.wavelength_um + offset) : [1, 2, 3, 4, 5];
    for (const wave of waveTicks) {
      const y = yAt(wave);
      context.beginPath();
      context.moveTo(left, y);
      context.lineTo(right, y);
      context.stroke();
      context.fillText(wave.toFixed(pinned ? 3 : 1), 7, y + 4);
    }
    const fractions = lowDate === highDate ? [.5] : width >= 525 ? [0, .25, .5, .75, 1] : [0, .5, 1];
    for (const fraction of fractions) {
      const x = left + fraction * (right - left);
      context.beginPath();
      context.moveTo(x, top);
      context.lineTo(x, bottom);
      context.stroke();
      const mjd = lowDate + fraction * (highDate - lowDate);
      const day = new Date((mjd - 40587) * 86400000).toISOString().slice(0, 10);
      context.fillText(day, Math.min(width - 69, Math.max(0, x - 34)), bottom + 17);
    }

    for (const frame of onPlot) {
      const x = xAt(frame.mjd), y = yAt(frame.wavelength_um);
      if (y < top || y > bottom) continue;
      points.push({frame, x, y});
      context.fillStyle = colors[frame.detector - 1] || muted;
      context.beginPath();
      context.arc(x, y, 3, 0, 2 * Math.PI);
      context.fill();
    }
    for (const {frame, x, y} of points) {
      if (frame.id !== current?.id && frame.id !== pinned?.id && frame.id !== hovered?.id) continue;
      context.strokeStyle = text;
      context.beginPath();
      context.arc(x, y, 6, 0, 2 * Math.PI);
      context.stroke();
    }
    colors.forEach((color, index) => {
      const x = left + index * Math.min(42, (right - left) / 6);
      context.fillStyle = color;
      context.fillRect(x, 194, 7, 7);
      context.fillStyle = text;
      context.fillText('D' + (index + 1), x + 10, 201);
    });
  }

  function update() {
    if (!panel.open || scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (panel.open) draw();
    });
  }

  function pointAt(event) {
    const bounds = canvas.getBoundingClientRect();
    let nearest = null, distance = 10;
    for (const point of points) {
      const delta = Math.hypot(point.x - event.clientX + bounds.left, point.y - event.clientY + bounds.top);
      if (delta < distance) {
        nearest = point.frame;
        distance = delta;
      }
    }
    return nearest;
  }

  panel.addEventListener('toggle', () => {
    if (!panel.open && view.blinking) view.stop();
    update();
  });
  window.addEventListener('resize', update);
  new MutationObserver(update).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  match.addEventListener('click', () => {
    pinned = view.current();
    hovered = null;
    update();
  });
  blink.addEventListener('click', () => {
    if (view.blinking) {view.stop();update();return;}
    const current = view.current();
    if (!pinned || !matchingEpochs([current], pinned).length) return;
    blinkPair = chronological([pinned, current]);
    view.blinkExposures(blinkPair.map(frame => frame.id));
    update();
  });
  measure.addEventListener('click', async () => {
    const current = view.current();
    if (comparing || !pinned || !matchingEpochs([current], pinned).length) return;
    const job = view.jobId;
    const key = pinned.id + ':' + current.id;
    comparing = true;
    measuredKey = key;
    difference.hidden = true;
    measureStatus.textContent = 'Checking wavelength overlap, the point spread function, and nearby reference stars…';
    update();
    try {
      const params = new URLSearchParams({a: pinned.id, b: current.id, x: .5, y: .5});
      const result = await view.api('/api/jobs/' + job + '/calibrated-pair?' + params);
      if (view.jobId !== job || measuredKey !== key) return;
      const dates = result.exposures.map(frame => frame.date.slice(0,10)).join(' → ');
      if (result.status === 'measured') {
        const [east,north] = result.displacement_arcsec;
        const [eastError,northError] = result.component_error_arcsec;
        measureStatus.textContent = dates + ' · ' + east.toFixed(2) + ' ± ' + eastError.toFixed(2) +
          '″ east · ' + north.toFixed(2) + ' ± ' + northError.toFixed(2) + '″ north. Source association is provisional.';
      } else {
        measureStatus.textContent = dates + ' · ' + result.reason;
      }
      if (result.difference) {
        difference.src = result.difference.image;
        difference.hidden = false;
      }
    } catch (error) {
      if (view.jobId === job && measuredKey === key) measureStatus.textContent = error.message;
    } finally {
      comparing = false;
      update();
    }
  });
  clear.addEventListener('click', () => {
    if (view.blinking) view.stop();
    pinned = null;
    hovered = null;
    update();
  });
  list.addEventListener('change', () => openExposure(list.value));
  exportButton.addEventListener('click', () => {
    if (!view.job?.frames.length) return;
    const frames = pinned ? [pinned, ...matchingEpochs(view.job.frames, pinned)] : view.job.frames;
    const url = URL.createObjectURL(new Blob([coverageCSV(frames)], {type: 'text/csv;charset=utf-8'}));
    view.download(url, pinned ? 'spherex-matching-exposures.csv' : 'spherex-exposure-manifest.csv');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  canvas.addEventListener('click', event => openExposure(pointAt(event)?.id));
  canvas.addEventListener('pointermove', event => {
    const next = pointAt(event);
    if (next?.id === hovered?.id) return;
    hovered = next;
    canvas.style.cursor = hovered ? 'pointer' : '';
    update();
  });
  canvas.addEventListener('pointerleave', () => {
    hovered = null;
    update();
  });
  return update;
}
