const byId = id => document.getElementById(id);
const dwarfReference = 'https://hero.epa.gov/reference/2669638/';
const bands = [
  ['Methane (CH₄)', 3.25, 3.40, dwarfReference],
  ['Carbon dioxide (CO₂)', 4.15, 4.40, dwarfReference],
  ['Carbon monoxide (CO)', 4.55, 4.85, dwarfReference],
];

export function spectrumDays(points) {
  return [...new Set(points.map(point => point.date?.slice(0, 10)).filter(Boolean))].sort();
}

export function selectMeasurements(points, day) {
  return points.filter(point => !day || point.date?.slice(0, 10) === day);
}

export function isSpectrumPoint(point) {
  return point.status === 'ok' &&
    [point.wavelength_um, point.flux_ujy, point.error_ujy].every(Number.isFinite) && point.error_ujy >= 0;
}

function plot(canvas, primary, comparison, showBands) {
  const points = [...primary, ...comparison];
  const ctx = canvas.getContext('2d'), {width, height} = canvas;
  ctx.fillStyle = '#10151c';
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = '#c7d0dc';
  ctx.font = '13px monospace';
  if (!points.length) {
    ctx.fillText('No usable spectrum for the selected dates.', 20, 40);
    return;
  }
  const left = 68, right = width - 16, top = 28, bottom = height - 54;
  const minWave = Math.min(...points.map(p => p.wavelength_min_um ?? p.wavelength_um));
  const maxWave = Math.max(...points.map(p => p.wavelength_max_um ?? p.wavelength_um));
  const margin = Math.max(.035, (maxWave - minWave) * .06);
  const lo = minWave - margin, hi = maxWave + margin;
  const minFlux = Math.min(0, ...points.map(p => p.flux_ujy - p.error_ujy));
  const maxFlux = Math.max(0, ...points.map(p => p.flux_ujy + p.error_ujy));
  const yRange = Math.max(maxFlux - minFlux, 1e-9);
  const x = value => left + (value - lo) / (hi - lo) * (right - left);
  const y = value => bottom - (value - minFlux) / yRange * (bottom - top);
  if (showBands) {
    ctx.fillStyle = '#daa65642';
    for (const [, low, high] of bands) {
      const first = Math.max(lo, low), last = Math.min(hi, high);
      if (first < last) ctx.fillRect(x(first), top, x(last) - x(first), bottom - top);
    }
  }
  ctx.fillStyle = '#c7d0dc';
  ctx.strokeStyle = '#64758b';
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, bottom);
  ctx.lineTo(right, bottom);
  ctx.stroke();
  ctx.fillText('Flux (µJy)', left, 18);
  ctx.fillText('Wavelength (µm)', (left + right) / 2 - 62, height - 12);
  for (let i = 0; i <= 4; i++) {
    const wave = lo + (hi - lo) * i / 4;
    const flux = minFlux + yRange * i / 4;
    ctx.fillText(wave.toFixed(2), x(wave) - 13, bottom + 20);
    ctx.fillText(flux.toPrecision(2), 8, y(flux) + 4, left - 12);
  }
  for (const [series, color] of [[primary, '#b7dcf5'], [comparison, '#ffc88d']]) for (const p of series) {
    const px = x(p.wavelength_um), py = y(p.flux_ujy);
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(px, y(p.flux_ujy - p.error_ujy));
    ctx.lineTo(px, y(p.flux_ujy + p.error_ujy));
    ctx.moveTo(x(p.wavelength_min_um ?? p.wavelength_um), py);
    ctx.lineTo(x(p.wavelength_max_um ?? p.wavelength_um), py);
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(px, py, 2.7, 0, 2 * Math.PI);
    ctx.fill();
  }
}

function exposureRow(point) {
  const li = document.createElement('li');
  li.textContent = (point.date || 'Date unavailable') + ' · D' + (point.detector ?? '?') + ' · ';
  if (isSpectrumPoint(point)) {
    li.append(point.wavelength_um.toFixed(3) + ' µm · ' + point.flux_ujy.toPrecision(4) +
      ' ± ' + point.error_ujy.toPrecision(3) + ' µJy · ');
    if (point.aperture_flags?.length) li.append('FITS FLAGS ' + point.aperture_flags.join(', ') + ' · ');
  } else li.append((point.reason || 'Unusable aperture') + ' · ');
  const id = point.observation || point.exposure_id || 'Exposure ' + (point.frame + 1);
  if (point.archive_url?.startsWith('https://')) {
    const link = document.createElement('a');
    link.href = point.archive_url;
    link.target = '_blank';
    link.rel = 'noreferrer';
    link.textContent = id;
    li.append(link);
  } else li.append(id);
  return li;
}

export function showSpectrum(result, selectedDate) {
  const container = byId('spectrum-result'), date = byId('spectrum-date'), overlay = byId('spectrum-bands');
  const references = byId('spectrum-references'), comparisonDate = byId('spectrum-compare-date');
  const days = spectrumDays(result.points);
  date.replaceChildren(new Option('All dates · may mix variability', ''), ...days.map(day => new Option(day, day)));
  date.value = days.includes(selectedDate) ? selectedDate : days[0] ?? '';
  comparisonDate.value = '';
  container.hidden = false;
  function render() {
    const compare = comparisonDate.value;
    const compareDays = date.value ? days.filter(day => day !== date.value) : [];
    comparisonDate.replaceChildren(new Option('Off', ''), ...compareDays.map(day => new Option(day, day)));
    comparisonDate.value = compareDays.includes(compare) ? compare : '';
    comparisonDate.disabled = !compareDays.length;
    const comparison = comparisonDate.value ? selectMeasurements(result.points, comparisonDate.value) : [];
    const measurements = selectMeasurements(result.points, date.value);
    const valid = measurements.filter(isSpectrumPoint);
    const comparisonPoints = comparison.filter(isSpectrumPoint);
    plot(byId('spectrum'), valid, comparisonPoints, overlay.checked);
    byId('spectrum-exposures').replaceChildren(...[...measurements, ...comparison].map(exposureRow));
    byId('spectrum-key').textContent = comparisonDate.value
      ? 'Blue: ' + date.value + ' · amber: ' + comparisonDate.value +
        ' (' + comparisonPoints.length + ' usable). Compare only overlapping wavelengths.'
      : '';
    byId('spectrum-coverage').textContent = valid.length + ' usable of ' + measurements.length +
      ' loaded exposures measured for this date selection. ' +
      (valid.length ? Math.min(...valid.map(p => p.wavelength_um)).toFixed(3) + '–' +
        Math.max(...valid.map(p => p.wavelength_um)).toFixed(3) + ' µm (sample centers). ' : '') +
      (new Set(valid.map(p => p.wavelength_um.toFixed(2))).size < 3
        ? 'Too few distinct wavelength samples to assess an absorption feature.'
        : 'Coverage can have gaps. Compare dates where sampled wavelengths overlap.');
    references.hidden = !overlay.checked;
    references.replaceChildren();
    if (overlay.checked) for (const [name, low, high, source] of bands) {
      const item = document.createElement('li'), link = document.createElement('a');
      const inside = valid.filter(p => p.wavelength_um >= low && p.wavelength_um <= high).length;
      link.href = source; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = name;
      item.append(link, ' · ' + low.toFixed(2) + '–' + high.toFixed(2) + ' µm · ' +
        (inside ? inside + ' measured samples in range' : 'No measured samples in range'));
      references.append(item);
    }
  }
  date.onchange = render;
  comparisonDate.onchange = render;
  overlay.onchange = render;
  render();
}
