import {loadCatalogSky} from './satellite-stars.js?v=1';

// Look around from the detector pointing of the selected archive exposure.
const radians = Math.PI / 180;
const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
const scaleVector = (vector, factor) => vector.map(value => value * factor);
const add = (a, b) => a.map((value, i) => value + b[i]);
const unit = vector => scaleVector(vector, 1 / Math.hypot(...vector));
const orthogonal = (vector, axis) => add(vector, scaleVector(axis, -dot(vector, axis)));
const skyVector = ({ra, dec}) => [
  Math.cos(dec * radians) * Math.cos(ra * radians),
  Math.cos(dec * radians) * Math.sin(ra * radians),
  Math.sin(dec * radians)
];

function cameraBasis(data) {
  const forward = skyVector(data.detector_center);
  const right = unit(orthogonal(skyVector(data.camera_right), forward));
  const up = unit(orthogonal(orthogonal(skyVector(data.camera_up), forward), right));
  return {forward, right, up};
}

function aimAt(camera, target) {
  const forward = skyVector(target);
  // Preserve the detector roll while turning to the selected sky direction.
  const alignment = dot(camera.forward, forward);
  const tangent = orthogonal(forward, camera.forward);
  const sine = Math.hypot(...tangent);
  if (sine < 1e-10) {
    return alignment > 0 ? camera : {forward, right: scaleVector(camera.right, -1), up: camera.up};
  }
  const toward = scaleVector(tangent, 1 / sine);
  function rotate(vector) {
    const a = dot(vector, camera.forward), b = dot(vector, toward);
    return add(vector, add(scaleVector(camera.forward, (alignment - 1) * a - sine * b),
      scaleVector(toward, sine * a + (alignment - 1) * b)));
  }
  return {forward, right: rotate(camera.right), up: rotate(camera.up)};
}

function screenPosition(camera, sky, width, height, focal) {
  const vector = skyVector(sky);
  const depth = dot(vector, camera.forward);
  if (depth <= 0) return null;
  return [width / 2 + focal * dot(vector, camera.right) / depth,
    height / 2 - focal * dot(vector, camera.up) / depth];
}

function rotatePair(first, second, angle) {
  const cosine = Math.cos(angle), sine = Math.sin(angle);
  return [add(scaleVector(first, cosine), scaleVector(second, sine)),
    add(scaleVector(first, -sine), scaleVector(second, cosine))];
}

export function skyRay(camera, x, y) {
  const [a, b, c] = add(add(camera.forward, scaleVector(camera.right, x)), scaleVector(camera.up, y));
  return {ra: (Math.atan2(b, a) / radians + 360) % 360, dec: Math.atan2(c, Math.hypot(a, b)) / radians};
}

function setupViewNavigation(byId) {
  byId('universe-home').textContent = 'Free View';
  byId('satellite-view-tab').textContent = 'SPHEREx View';
  const destinations = document.createElement('details');
  destinations.className = 'free-destinations';
  const summary = document.createElement('summary');
  summary.textContent = 'Destinations';
  const menu = document.createElement('div');
  destinations.append(summary, menu);
  for (const id of ['solar-tab', 'stars-tab', 'systems-toggle']) {
    const button = byId(id);
    button.hidden = false;
    button.addEventListener('click', () => { destinations.open = false; });
    menu.append(button);
  }
  document.querySelector('.view-tools').prepend(destinations);
}

export function installSatelliteView(view) {
  const byId = id => document.getElementById(id);
  setupViewNavigation(byId);
  const dialog = document.createElement('dialog');
  dialog.id = 'satellite-camera';
  dialog.setAttribute('aria-labelledby', 'satellite-camera-title');
  dialog.innerHTML = `
    <div class="satellite-heading">
      <h2 id="satellite-camera-title">SPHEREx View</h2>
      <button type="button" id="satellite-close">Close</button>
    </div>
    <p id="satellite-exposure"></p>
    <p class="micro"><a id="satellite-source" target="_blank" rel="noreferrer" hidden></a></p>
    <div class="satellite-controls">
      <button type="button" id="satellite-free">Free View</button>
      <button type="button" id="satellite-images">Images</button>
      <button type="button" id="satellite-target">Center target</button>
      <button type="button" id="satellite-search">Search view center</button>
    </div>
    <div class="satellite-stage">
      <canvas id="satellite-sky" width="960" height="540" aria-hidden="true" hidden></canvas>
      <canvas id="satellite-camera-canvas" width="960" height="540" tabindex="0" aria-label="SPHEREx sky view. Use arrow keys to look around."></canvas>
    </div>
    <p id="satellite-detail" class="micro"></p>
    <p id="satellite-status" role="status"></p>`;
  document.body.append(dialog);
  const canvas = byId('satellite-camera-canvas'), ctx = canvas.getContext('2d');
  const status = byId('satellite-status'), sky = byId('satellite-sky');
  const defaultFocal = canvas.width * .85;
  let focal = defaultFocal;
  let camera, drag, catalogDraw, catalogLoad, catalogFailed;
  let target, targetName, turn = 0, request = 0;

  function openCatalog() {
    if (catalogLoad) return;
    catalogFailed = false;
    catalogLoad = loadCatalogSky(sky).then(render => { catalogDraw = render; }).catch(() => {
      catalogFailed = true;
      catalogLoad = null;
    }).finally(() => { if (dialog.open) draw(); });
  }

  function centerTarget() {
    cancelAnimationFrame(turn);
    const start = camera;
    const end = aimAt(start, target);
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const began = performance.now();
    const cosine = Math.max(-1, Math.min(1, dot(start.forward, end.forward)));
    const arc = Math.acos(cosine);
    const tangent = cosine < -.9999999 ? start.right : orthogonal(end.forward, start.forward);
    function step(now) {
      if (!dialog.open) return;
      const progress = reduced ? 1 : Math.min(1, (now - began) / 550);
      const ease = progress * progress * (3 - 2 * progress);
      if (progress === 1 || arc < 1e-8) camera = end;
      else {
        const ray = add(scaleVector(start.forward, Math.cos(ease * arc)), scaleVector(unit(tangent), Math.sin(ease * arc)));
        camera = aimAt(start, skyRay({forward: ray, right: start.right, up: start.up}, 0, 0));
        turn = requestAnimationFrame(step);
      }
      draw();
    }
    turn = requestAnimationFrame(step);
  }

  function drawSkyGrid() {
    ctx.strokeStyle = '#344b61';
    function curve(coords) {
      ctx.beginPath();
      let connected = false;
      for (const position of coords) {
        const vector = skyVector(position);
        const depth = dot(vector, camera.forward);
        if (depth < .1) {
          connected = false;
          continue;
        }
        const x = canvas.width / 2 + focal * dot(vector, camera.right) / depth;
        const y = canvas.height / 2 - focal * dot(vector, camera.up) / depth;
        if (connected) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
        connected = true;
      }
      ctx.stroke();
    }
    for (let dec = -75; dec <= 75; dec += 15) {
      curve(Array.from({length: 121}, (_, i) => ({ra: i * 3, dec})));
    }
    for (let ra = 0; ra < 360; ra += 15) {
      curve(Array.from({length: 61}, (_, i) => ({ra, dec: i * 3 - 90})));
    }
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!camera) {
      sky.hidden = true;
      return;
    }
    const hasCatalog = catalogDraw?.(camera, focal);
    sky.hidden = !hasCatalog;
    if (!hasCatalog) {
      ctx.fillStyle = '#080e18';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawSkyGrid();
    }
    crosshair(canvas.width / 2, canvas.height / 2);
    drawTarget(screenPosition(camera, target, canvas.width, canvas.height, focal));
    showCenter(skyRay(camera, 0, 0), hasCatalog
      ? 'Catalog sky · NASA Goddard SVS. Drag to turn, scroll to zoom, and right-click to search SPHEREx.'
      : catalogFailed ? 'Catalog map unavailable. Drag the coordinate grid or right-click to search SPHEREx.'
        : 'Loading the catalog sky. Right-click to search SPHEREx.');
  }

  function drawTarget(point) {
    if (!point) return;
    const [x, y] = point;
    if (x < 0 || y < 0 || x > canvas.width || y > canvas.height) return;
    ctx.save();
    ctx.translate(x, y);
    ctx.shadowColor = '#05080e';
    ctx.shadowBlur = 5;
    ctx.strokeStyle = ctx.fillStyle = '#ffc680';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let quarter = 0; quarter < 4; quarter++) {
      const angle = quarter * Math.PI / 2;
      ctx.moveTo(19 * Math.cos(angle + .17), 19 * Math.sin(angle + .17));
      ctx.arc(0, 0, 19, angle + .17, angle + Math.PI / 2 - .17);
      ctx.moveTo(22 * Math.cos(angle), 22 * Math.sin(angle));
      ctx.lineTo(28 * Math.cos(angle), 28 * Math.sin(angle));
    }
    ctx.stroke();
    ctx.font = '600 15px system-ui';
    ctx.textAlign = x > canvas.width * .68 ? 'right' : 'left';
    ctx.fillText(targetName, ctx.textAlign === 'right' ? -34 : 34, 5, canvas.width * .31);
    ctx.restore();
  }

  function crosshair(cx, cy) {
    ctx.strokeStyle = '#e3edf5';
    ctx.beginPath();
    ctx.moveTo(cx - 7, cy); ctx.lineTo(cx + 7, cy);
    ctx.moveTo(cx, cy - 7); ctx.lineTo(cx, cy + 7);
    ctx.stroke();
  }

  function showCenter(sky, message) {
    byId('satellite-detail').textContent = 'Center RA ' + sky.ra.toFixed(5) +
      '°, Dec ' + sky.dec.toFixed(5) + '°. ' + message;
  }

  async function search(x, y) {
    if (!camera || !dialog.open) return;
    cancelAnimationFrame(turn);
    const coords = skyRay(camera, (x - canvas.width / 2) / focal, (canvas.height / 2 - y) / focal);
    byId('object-query').value = '';
    byId('ra').value = coords.ra.toFixed(8);
    byId('dec').value = coords.dec.toFixed(8);
    dialog.close();
    await view.search('Sky direction from SPHEREx');
  }

  byId('satellite-close').onclick = () => dialog.close();
  byId('satellite-free').onclick = () => { dialog.close(); byId('universe-home').click(); };
  byId('satellite-images').onclick = () => { dialog.close(); view.open(); };
  byId('satellite-target').onclick = () => { if (camera) centerTarget(); };
  byId('satellite-search').onclick = () => search(canvas.width / 2, canvas.height / 2);
  dialog.addEventListener('close', () => {
    if (!dialog.open) {
      cancelAnimationFrame(turn);
      request++;
      drag = null;
    }
  });
  function canvasPoint(event) {
    const box = canvas.getBoundingClientRect();
    return [
      (event.clientX - box.left) * canvas.width / box.width,
      (event.clientY - box.top) * canvas.height / box.height];
  }
  canvas.addEventListener('contextmenu', event => {
    event.preventDefault();
    search(...canvasPoint(event));
  });
  canvas.addEventListener('pointerdown', event => {
    if (!camera || event.button !== 0) return;
    cancelAnimationFrame(turn);
    drag = {id: event.pointerId, point: canvasPoint(event)};
    canvas.focus({preventScroll: true});
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!camera || event.pointerId !== drag?.id) return;
    const point = canvasPoint(event);
    look((drag.point[0] - point[0]) / focal, (point[1] - drag.point[1]) / focal);
    drag.point = point;
  });
  canvas.addEventListener('lostpointercapture', () => { drag = null; });
  canvas.addEventListener('wheel', event => {
    if (!camera) return;
    event.preventDefault();
    const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.height : 1;
    focal = Math.max(canvas.width * .42, Math.min(canvas.width * 3,
      focal * Math.exp(-event.deltaY * multiplier * .001)));
    draw();
  }, {passive: false});
  function look(horizontal, vertical) {
    [camera.forward, camera.right] = rotatePair(camera.forward, camera.right, horizontal);
    [camera.forward, camera.up] = rotatePair(camera.forward, camera.up, vertical);
    draw();
  }
  canvas.addEventListener('keydown', event => {
    const moves = {ArrowLeft: [-.08,0], ArrowRight: [.08,0], ArrowUp: [0,.08], ArrowDown: [0,-.08]};
    if (!camera || !Object.hasOwn(moves, event.key)) return;
    event.preventDefault();
    cancelAnimationFrame(turn);
    look(...moves[event.key]);
  });

  byId('satellite-view-tab').onclick = async () => {
    const frame = view.current();
    if (!frame || !view.jobId) {
      view.open();
      view.toast('Load a sky field and select a SPHEREx exposure first.');
      return;
    }
    const token = ++request;
    view.stop();
    const url = '/api/jobs/' + view.jobId + '/satellite-view/' + frame.index;
    camera = null;
    focal = defaultFocal;
    targetName = byId('observation-title').textContent.trim() || 'Selected field';
    byId('satellite-search').disabled = true;
    byId('satellite-target').disabled = true;
    byId('satellite-source').hidden = true;
    byId('satellite-exposure').textContent = frame.date;
    byId('satellite-detail').textContent = '';
    status.textContent = 'Loading the spacecraft pointing for this exposure…';
    draw();
    if (!dialog.open) dialog.showModal();
    openCatalog();
    try {
      const result = await view.api(url + '?' + new URLSearchParams({exposure_id: frame.id, preview: 'false'}));
      if (token !== request || !dialog.open) return;
      camera = cameraBasis(result);
      target = result.target ?? result.crop_center;
      const position = result.spacecraft;
      const provenance = position
        ? 'Recorded spacecraft ' + position.sample + ' at ' + position.time + ' · geocentric XYZ ' +
          position.xyz_km.map(n => n.toFixed(0)).join(', ') + ' km.'
        : 'Spacecraft position is unavailable for this exposure.';
      byId('satellite-exposure').textContent = result.date + ' · Detector ' + result.detector + '. ' + provenance;
      if (result.archive_url?.startsWith('https://')) {
        const source = byId('satellite-source');
        source.href = result.archive_url;
        source.textContent = result.observation ? 'Original exposure · ' + result.observation : 'Original archive exposure';
        source.hidden = false;
      }
      byId('satellite-search').disabled = false;
      byId('satellite-target').disabled = false;
      status.textContent = '';
      draw();
      centerTarget();
    } catch (error) {
      if (token === request) status.textContent = error.message;
    }
  };
}
