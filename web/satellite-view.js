import {formatDirection} from './sky-direction.js?v=2';
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

export function installSatelliteView(view, {openObservations, openContext, loadSources, getTarget}) {
  const byId = id => document.getElementById(id);
  const panel = byId('satellite-camera');
  const canvas = byId('satellite-camera-canvas'), ctx = canvas.getContext('2d');
  const status = byId('satellite-status'), sky = byId('satellite-sky');
  const defaultFocal = canvas.width * .85;
  let focal = defaultFocal;
  const pointers = new Map();
  let tap;
  let camera, catalogDraw, catalogLoad, catalogFailed;
  let target, selection, turn = 0, request = 0;
  let sources=[], drawnSources=[], sourcesRequest, sourceStatus='';
  let referenceKey, pendingKey, attemptedJob;
  const frameKey = frame => view.jobId + '|' + frame.id;
  const fallbackDirection = {ra: 0, dec: 0};
  const visible = () => !panel.hidden;

  function catalogCamera({ra, dec}) {
    const lon = ra * radians, lat = dec * radians;
    return {
      forward: skyVector({ra, dec}),
      right: [Math.sin(lon), -Math.cos(lon), 0],
      up: [-Math.sin(lat) * Math.cos(lon), -Math.sin(lat) * Math.sin(lon), Math.cos(lat)],
    };
  }

  function openCatalog() {
    if (catalogLoad) return;
    catalogFailed = false;
    catalogLoad = loadCatalogSky(sky).then(render => { catalogDraw = render; }).catch(() => {
      catalogFailed = true;
      catalogLoad = null;
    }).finally(() => { if (visible()) draw(); });
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
      if (!visible()) return;
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
    drawSources();
    if (target) drawTarget(screenPosition(camera, target, canvas.width, canvas.height, focal));
    const gesture = matchMedia('(pointer: coarse)').matches
      ? 'Swipe to turn, pinch to zoom, or tap a catalog star.'
      : 'Drag to turn. Click a catalog star, or right-click anywhere to open SPHEREx images.';
    const backdrop=hasCatalog?'Catalog sky · NASA Goddard SVS. ':
      catalogFailed?'Catalog background unavailable. ':'Loading the catalog background. ';
    showCenter(skyRay(camera,0,0),backdrop+gesture+sourceStatus);
  }

  function drawSources() {
    drawnSources=[];
    for(const source of sources){
      const point=screenPosition(camera,source,canvas.width,canvas.height,focal);
      if(!point)continue;
      const [x,y]=point;
      if(x<0||x>canvas.width||y<0||y>canvas.height)continue;
      drawnSources.push({source,x,y});
    }
    const shown=drawnSources.slice(0,120);
    drawnSources=shown;
    ctx.lineWidth=1;
    ctx.strokeStyle='#91b7ce88';
    ctx.fillStyle='#dcefff';
    for(const {x,y} of shown){
      ctx.beginPath();ctx.arc(x,y,4.5,0,2*Math.PI);ctx.stroke();
      ctx.beginPath();ctx.arc(x,y,1.4,0,2*Math.PI);ctx.fill();
    }
  }

  function pickSource(x,y) {
    const hitRadius=(matchMedia('(pointer: coarse)').matches?20:12)*canvas.width/canvas.getBoundingClientRect().width;
    let closest, distance=hitRadius;
    for(const hit of drawnSources){
      const delta=Math.hypot(x-hit.x,y-hit.y);
      if(delta<distance){closest=hit.source;distance=delta;}
    }
    return closest;
  }

  function prepareSources(){
    if(sourcesRequest)return;
    const unique=new Map();
    function addCatalog({objects}){
      for(const source of objects){
        if(source.id&&source.name&&Number.isFinite(source.ra)&&Number.isFinite(source.dec)&&
          source.distance_pc>0&&source.xyz_pc?.length===3&&source.xyz_pc.every(Number.isFinite)){
          unique.set(source.id,source);
        }
      }
      sources=[...unique.values()].sort((a,b)=>(a.phot_g_mean_mag??12)-(b.phot_g_mean_mag??12));
      if(sources.length)sourceStatus=' · Circled stars have catalog distances.';
      if(visible())draw();
    }
    sourcesRequest=Promise.allSettled(loadSources().map(catalog=>catalog.then(addCatalog))).then(results=>{
      if(sources.length)return;
      sourceStatus=' · No interactive stars are available.';
      if(results.every(result=>result.status==='rejected'))sourcesRequest=null;
      if(visible())draw();
    });
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
    ctx.fillText(target.name, ctx.textAlign === 'right' ? -34 : 34, 5, canvas.width * .31);
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
    byId('satellite-direction').textContent = 'Looking at · ' + formatDirection(sky);
    byId('satellite-detail').textContent = message;
  }

  function coordinatesAt(x,y){
    return skyRay(camera,(x-canvas.width/2)/focal,(canvas.height/2-y)/focal);
  }

  function selectTarget(x,y){
    const source=pickSource(x,y);
    selection=source?{name:source.name,ra:source.ra,dec:source.dec,source}:
      {name:'Selected sky direction',...coordinatesAt(x,y)};
    target=selection;
    byId('satellite-target').disabled=false;
    byId('satellite-selection-label').textContent=selection.name+' · '+formatDirection(selection)+
      (source?' · '+source.distance_pc.toFixed(2)+' pc':' · Sky direction');
    byId('satellite-selection').hidden=false;
    draw();
  }

  function search(x,y){
    if(!camera||!visible())return;
    const coords=coordinatesAt(x,y);
    target={name:'Selected sky direction',...coords};
    selection=null;
    byId('satellite-selection').hidden=true;
    byId('satellite-target').disabled=false;
    return openObservations(target);
  }

  byId('satellite-selection-images').onclick=()=>{
    if(selection){byId('satellite-selection').hidden=true;openObservations(selection);}
  };
  byId('satellite-selection-context').onclick=()=>{
    if(selection){byId('satellite-selection').hidden=true;openContext(selection);}
  };
  byId('satellite-selection-close').onclick=()=>{byId('satellite-selection').hidden=true;};
  byId('satellite-target').onclick=()=>{if(target)centerTarget();};
  byId('satellite-search').onclick=()=>search(canvas.width/2,canvas.height/2);

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
    if (!camera || !visible() || event.button !== 0 || pointers.size === 2) return;
    cancelAnimationFrame(turn);
    if(pointers.size)tap=null;
    else tap={id:event.pointerId,x:event.clientX,y:event.clientY};
    pointers.set(event.pointerId, canvasPoint(event));
    if (event.pointerType === 'mouse') canvas.focus({preventScroll: true});
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    const previous = pointers.get(event.pointerId);
    if (!camera || !previous) return;
    if(tap&&Math.hypot(event.clientX-tap.x,event.clientY-tap.y)>6)tap=null;
    const point = canvasPoint(event);
    if (pointers.size === 2) {
      const other = [...pointers].find(([id]) => id !== event.pointerId)[1];
      const oldDistance = Math.hypot(previous[0] - other[0], previous[1] - other[1]);
      const newDistance = Math.hypot(point[0] - other[0], point[1] - other[1]);
      if (oldDistance > 2 && newDistance > 2) zoom(newDistance / oldDistance);
    } else {
      look((previous[0] - point[0]) / focal, (point[1] - previous[1]) / focal);
    }
    pointers.set(event.pointerId, point);
  });
  for(const type of ['pointercancel','lostpointercapture','pointerup']){
    canvas.addEventListener(type,event=>{
      pointers.delete(event.pointerId);
      if(tap?.id!==event.pointerId)return;
      tap=null;
      if(type==='pointerup'&&visible())selectTarget(...canvasPoint(event));
    });
  }
  function zoom(factor) {
    focal = Math.max(canvas.width * .42, Math.min(canvas.width * 3, focal * factor));
    draw();
  }
  canvas.addEventListener('wheel', event => {
    if (!camera) return;
    event.preventDefault();
    const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.height : 1;
    zoom(Math.exp(-event.deltaY * multiplier * .001));
  }, {passive: false});
  function look(horizontal, vertical) {
    [camera.forward, camera.right] = rotatePair(camera.forward, camera.right, horizontal);
    [camera.forward, camera.up] = rotatePair(camera.forward, camera.up, vertical);
    draw();
  }
  canvas.addEventListener('keydown', event => {
    const moves = {ArrowLeft: [-.08,0], ArrowRight: [.08,0], ArrowUp: [0,.08], ArrowDown: [0,-.08]};
    if(!camera)return;
    if(event.key==='Enter'){
      event.preventDefault();
      selectTarget(canvas.width/2,canvas.height/2);
      return;
    }
    if(!Object.hasOwn(moves,event.key))return;
    event.preventDefault();
    cancelAnimationFrame(turn);
    look(...moves[event.key]);
  });

  const referenceButton = byId('satellite-reference');
  const exposure = byId('satellite-exposure');
  const source = byId('satellite-source');

  async function useExposure(frame, manual = false) {
    if (!frame || !view.jobId) return;
    const jobId = view.jobId, key = frameKey(frame), token = ++request;
    if (manual) view.stop();
    pendingKey = key;
    referenceButton.disabled = true;
    status.textContent = 'Loading pointing for the selected exposure…';
    try {
      const result = await view.api('/api/jobs/' + jobId + '/satellite-view/' + frame.index + '?' +
        new URLSearchParams({exposure_id: frame.id, preview: 'false'}));
      if (token !== request || jobId !== view.jobId) return;
      camera = cameraBasis(result);
      const field=result.target??result.crop_center;
      target=getTarget()??{...field,name:byId('observation-title').textContent.trim()||'Selected field'};
      focal = defaultFocal;
      referenceKey = key;
      byId('satellite-target').disabled = false;
      const position = result.spacecraft;
      exposure.textContent = 'Camera reference · ' + result.date + ' · Detector ' + result.detector +
        (position ? ' · Recorded spacecraft position (' + position.sample + '), geocentric XYZ ' +
          position.xyz_km.map(n => n.toFixed(0)).join(', ') + ' km.'
          : ' · Spacecraft position unavailable.');
      source.hidden = !result.archive_url?.startsWith('https://');
      if (!source.hidden) {
        source.href = result.archive_url;
        source.textContent = 'Open camera reference exposure';
      }
      status.textContent = '';
      if (visible()) { draw(); centerTarget(); }
      else camera = aimAt(camera, target);
    } catch (error) {
      if (token === request) status.textContent = 'Could not use this exposure. ' + error.message;
    } finally {
      if (token === request) {
        pendingKey = null;
        updateReference(view.current());
      }
    }
  }

  function updateReference(frame) {
    const key = frame && view.jobId ? frameKey(frame) : null;
    referenceButton.disabled = !key || key === referenceKey || key === pendingKey;
  }

  view.onCameraFrame = frame => {
    if (!frame) {
      request++;
      cancelAnimationFrame(turn);
      referenceKey = pendingKey = attemptedJob = null;
      source.hidden = true;
      byId('satellite-target').disabled = !target;
      exposure.textContent = 'Catalog orientation · waiting for an exposure.';
      status.textContent = '';
      updateReference(null);
      if (visible()) draw();
      return;
    }
    updateReference(frame);
    // Anchor once per search. Chronological playback can then run without
    // reorienting the camera or reading the FITS header on every frame.
    if (view.jobId && attemptedJob !== view.jobId) {
      attemptedJob = view.jobId;
      useExposure(frame);
    }
  };
  referenceButton.onclick = () => useExposure(view.current(), true);
  target=getTarget();
  camera=catalogCamera(target??fallbackDirection);
  byId('satellite-target').disabled=!target;
  exposure.textContent = 'Catalog orientation · load an exposure for recorded spacecraft pointing.';
  return {
    show(){openCatalog();prepareSources();draw();},
    hide(){cancelAnimationFrame(turn);pointers.clear();tap=null;},
    setTarget(value){target=value;byId('satellite-target').disabled=false;if(visible())draw();},
    clearTarget(){target=selection=null;byId('satellite-target').disabled=true;byId('satellite-selection').hidden=true;if(visible())draw();},
  };
}
