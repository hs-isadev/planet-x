// Free-range orbit controls for the 3D context.
//
// Drop-in for the parts of OrbitControls this app uses (target, enabled, min/maxDistance,
// enableDamping, dampingFactor, zoomSpeed, update(), 'start'/'change'/'end' events) with
// different behaviour:
//  - Orbiting has no pole lock. Dragging rotates the camera around the target in its own
//    frame (yaw about the camera's up, pitch about its right), and the up vector turns with
//    it, so you can roll over the top and keep going.
//  - Pan with right-drag, middle-drag, shift/ctrl+drag, or two fingers.
//  - Zoom is not done here. Wheel and pinch go through onZoom(factor), which the scene
//    turns into a smooth, constant-ratio zoom (see navigation.js).
//  - Q / E roll the view around the line of sight.
//  - `upright = true` (set by the scene while an object is focused) switches to an upright orbit: yaw turns about
//    world up, pitch stops just short of the poles, and any tilt eases back to level. With `upright = false` the
//    free, tiltable orbit above applies.
import {EventDispatcher, Quaternion, Vector2, Vector3} from 'three';

const _offset = new Vector3(), _right = new Vector3(), _up = new Vector3(), _q = new Quaternion();
const _forward = new Vector3();

export class FreeOrbitControls extends EventDispatcher {
  constructor(camera, element) {
    super();
    this.object = camera;
    this.domElement = element;
    this.target = new Vector3();
    this.enabled = true;
    this.enableDamping = true;
    this.dampingFactor = .12;
    this.rotateSpeed = 1;
    this.panSpeed = 1;
    this.zoomSpeed = 1;
    this.minDistance = 0;
    this.maxDistance = Infinity;
    this.upright = false;
    this.worldUp = new Vector3(0, 1, 0);
    this.onZoom = null;
    this._yaw = 0; this._pitch = 0; this._roll = 0;
    this._pan = new Vector2();
    this._pointers = new Map();
    this._mode = null;
    this._pinch = 0;
    this._keys = new Set();

    this._onDown = this._onDown.bind(this);
    this._onMove = this._onMove.bind(this);
    this._onUp = this._onUp.bind(this);
    this._onKeyDown = e => {
      if (!this.enabled || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || '')) return;
      if (e.code === 'KeyQ' || e.code === 'KeyE') this._keys.add(e.code);
    };
    this._onKeyUp = e => this._keys.delete(e.code);
    element.style.touchAction = 'none';
    element.addEventListener('pointerdown', this._onDown);
    element.addEventListener('contextmenu', this._onContext = e => e.preventDefault());
    document.addEventListener('keydown', this._onKeyDown);
    document.addEventListener('keyup', this._onKeyUp);
    window.addEventListener('blur', this._onBlur = () => this._keys.clear());
  }

  dispose() {
    const el = this.domElement;
    el.removeEventListener('pointerdown', this._onDown);
    el.removeEventListener('contextmenu', this._onContext);
    el.ownerDocument.removeEventListener('pointermove', this._onMove);
    el.ownerDocument.removeEventListener('pointerup', this._onUp);
    document.removeEventListener('keydown', this._onKeyDown);
    document.removeEventListener('keyup', this._onKeyUp);
    window.removeEventListener('blur', this._onBlur);
  }

  _onDown(e) {
    if (!this.enabled) return;
    this._pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
    this.domElement.setPointerCapture?.(e.pointerId);
    const doc = this.domElement.ownerDocument;
    doc.addEventListener('pointermove', this._onMove);
    doc.addEventListener('pointerup', this._onUp);
    doc.addEventListener('pointercancel', this._onUp);
    if (this._pointers.size === 2) { this._mode = 'touch'; this._pinch = this._spread(); }
    else this._mode = e.button === 2 || e.button === 1 || e.shiftKey || e.ctrlKey || e.metaKey ? 'pan' : 'rotate';
    this.dispatchEvent({type: 'start'});
  }

  _spread() {
    const [a, b] = [...this._pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  _onMove(e) {
    if (!this.enabled) return;
    const p = this._pointers.get(e.pointerId);
    if (!p) return;
    const h = this.domElement.clientHeight || 1;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    if (this._mode === 'touch' && this._pointers.size === 2) {
      // Two fingers: average motion pans, change of spread zooms.
      p.x = e.clientX; p.y = e.clientY;
      this._pan.x += dx / 2 / h * this.panSpeed; this._pan.y += dy / 2 / h * this.panSpeed;
      const spread = this._spread();
      if (this._pinch > 0 && spread > 0) this._zoom(this._pinch / spread);
      this._pinch = spread;
      return;
    }
    p.x = e.clientX; p.y = e.clientY;
    if (this._mode === 'pan') { this._pan.x += dx / h * this.panSpeed; this._pan.y += dy / h * this.panSpeed; }
    else if (this._mode === 'rotate') {
      this._yaw -= 2 * Math.PI * dx / h * this.rotateSpeed;
      this._pitch -= 2 * Math.PI * dy / h * this.rotateSpeed;
    }
  }

  _onUp(e) {
    this._pointers.delete(e.pointerId);
    if (this._pointers.size === 1) { this._mode = 'rotate'; this._pinch = 0; }
    if (this._pointers.size) return;
    const doc = this.domElement.ownerDocument;
    doc.removeEventListener('pointermove', this._onMove);
    doc.removeEventListener('pointerup', this._onUp);
    doc.removeEventListener('pointercancel', this._onUp);
    this._mode = null;
    this.dispatchEvent({type: 'end'});
  }

  _zoom(factor) {
    if (this.onZoom) this.onZoom(factor);
    else {
      _offset.copy(this.object.position).sub(this.target);
      _offset.setLength(Math.min(this.maxDistance, Math.max(this.minDistance, _offset.length() * factor)));
      this.object.position.copy(this.target).add(_offset);
    }
  }

  // Stop any coasting motion (used when a flight or focus takes over the camera).
  halt() { this._yaw = this._pitch = this._roll = 0; this._pan.set(0, 0); }

  update(dt) {
    const camera = this.object, now = performance.now();
    if (dt == null) dt = this._last ? Math.min(.1, (now - this._last) / 1000) : 1 / 60;
    this._last = now;
    if (!this.upright && this._keys.has('KeyQ')) this._roll += dt * 1.4;
    if (!this.upright && this._keys.has('KeyE')) this._roll -= dt * 1.4;
    // Frame-rate independent damping: the same feel at 30, 60 or 144 fps.
    const share = this.enableDamping ? 1 - Math.pow(1 - this.dampingFactor, dt * 60) : 1;
    const yaw = this._yaw * share, pitch = this._pitch * share, roll = this._roll * share;
    const panX = this._pan.x * share, panY = this._pan.y * share;
    this._yaw -= yaw; this._pitch -= pitch; this._roll -= roll;
    this._pan.x -= panX; this._pan.y -= panY;

    _offset.copy(camera.position).sub(this.target);
    let distance = _offset.length();
    if (!(distance > 0)) { _offset.set(0, 0, 1); distance = Math.max(this.minDistance, 1e-9); }
    _forward.copy(_offset).negate().normalize();
    // Keep up perpendicular to the view direction so lookAt never degenerates.
    _up.copy(camera.up).addScaledVector(_forward, -camera.up.dot(_forward));
    if (_up.lengthSq() < 1e-12) _up.set(0, 1, 0).applyQuaternion(camera.quaternion);
    _up.normalize();
    _right.crossVectors(_forward, _up).normalize();

    if (this.upright) {
      // Upright orbit: yaw about world up, pitch about the camera's right axis, clamped short of the poles.
      const world = this.worldUp;
      if (yaw) { _q.setFromAxisAngle(world, yaw); _offset.applyQuaternion(_q); _up.applyQuaternion(_q); _right.applyQuaternion(_q); }
      if (pitch) {
        const polar = Math.acos(Math.min(1, Math.max(-1, _offset.clone().normalize().dot(world))));
        const limit = 0.035;
        const next = Math.min(Math.PI - limit, Math.max(limit, polar - pitch));
        _q.setFromAxisAngle(_right, polar - next);
        _offset.applyQuaternion(_q); _up.applyQuaternion(_q);
      }
      // Ease the horizon back to level: the up vector moves toward world up (kept perpendicular to the view).
      _forward.copy(_offset).negate().normalize();
      const level = world.clone().addScaledVector(_forward, -world.dot(_forward));
      if (level.lengthSq() > 1e-6) {
        level.normalize();
        const blend = 1 - Math.exp(-dt * 5);
        _up.lerp(level, blend).addScaledVector(_forward, -_up.dot(_forward)).normalize();
      }
      _right.crossVectors(_forward, _up).normalize();
    } else if (yaw || pitch) {
      _q.setFromAxisAngle(_up, yaw);
      _offset.applyQuaternion(_q); _right.applyQuaternion(_q);
      _q.setFromAxisAngle(_right, pitch);
      _offset.applyQuaternion(_q); _up.applyQuaternion(_q);
    }
    if (roll) {
      _forward.copy(_offset).negate().normalize();
      _up.applyQuaternion(_q.setFromAxisAngle(_forward, roll));
      _right.crossVectors(_forward, _up).normalize();
    }
    if (panX || panY) {
      const fov = (camera.fov || 50) * Math.PI / 180;
      const scale = 2 * distance * Math.tan(fov / 2);
      const move = _right.clone().multiplyScalar(-panX * scale).addScaledVector(_up, panY * scale);
      this.target.add(move);
    }
    const clamped = Math.min(this.maxDistance, Math.max(this.minDistance, distance));
    _offset.setLength(clamped);
    camera.position.copy(this.target).add(_offset);
    camera.up.copy(_up);
    camera.lookAt(this.target);
    if (yaw || pitch || roll || panX || panY) this.dispatchEvent({type: 'change'});
    return true;
  }
}
