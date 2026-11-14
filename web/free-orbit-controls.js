import {Vector3} from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

// Keep OrbitControls' pointer, pinch, pan and zoom handling. Apply rotation
// in the camera frame so pitching through a pole carries the up vector with it.
export class FreeOrbitControls extends OrbitControls {
  constructor(camera, element) {
    super(camera, element);
    this.orbitOffset = new Vector3();
    this.orbitUp = new Vector3();
    this.orbitRight = new Vector3();
    this.yAxis = new Vector3(0, 1, 0);
  }

  update(deltaTime = null) {
    if (!this.orbitOffset) return super.update(deltaTime);
    const delta = this._sphericalDelta;
    const damping = this.enableDamping ? this.dampingFactor : 1;
    const {theta, phi} = delta;
    const yaw = theta * damping;
    const pitch = phi * damping;
    const offset = this.orbitOffset.copy(this.object.position).sub(this.target);
    if ((yaw || pitch) && offset.lengthSq() > 0) {
      const up = this.orbitUp.copy(this.object.up).normalize();
      const right = this.orbitRight.crossVectors(up, offset);
      if (right.lengthSq() <= 1e-24) {
        right.set(1, 0, 0).applyQuaternion(this.object.quaternion);
        right.addScaledVector(offset, -right.dot(offset) / offset.lengthSq());
        if (right.lengthSq() <= 1e-24) right.set(0, 0, 1).cross(offset);
      }
      right.normalize();
      up.crossVectors(offset, right).normalize();
      offset.applyAxisAngle(up, yaw);
      right.applyAxisAngle(up, yaw);
      offset.applyAxisAngle(right, pitch);
      up.applyAxisAngle(right, pitch);
      this.object.up.copy(up);
      this.object.position.copy(this.target).add(offset);
    }
    // The parent only applies dolly and pan. Rebuild its up-axis conversion
    // whenever the camera has rolled, including after programmatic flights.
    this._quat.setFromUnitVectors(this.object.up, this.yAxis);
    this._quatInverse.copy(this._quat).invert();
    delta.theta = 0;
    delta.phi = 0;
    const changed = super.update(deltaTime);
    delta.theta = this.enableDamping ? theta * (1 - damping) : 0;
    delta.phi = this.enableDamping ? phi * (1 - damping) : 0;
    return changed;
  }
}
