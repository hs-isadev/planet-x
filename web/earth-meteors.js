import * as THREE from 'three';

const count = 9;
const outer = 1.065;
const inner = 1.012;

export function createEarthMeteors(center, radius, random = Math.random) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const brightness = new Float32Array(count);
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setAttribute('brightness', new THREE.BufferAttribute(brightness, 1).setUsage(THREE.DynamicDrawUsage));
  const material = new THREE.ShaderMaterial({
    uniforms: {pixelRatio: {value: Math.min(globalThis.devicePixelRatio || 1, 2)}},
    vertexShader: `
      attribute float brightness;
      uniform float pixelRatio;
      varying float glow;
      void main() {
        glow = brightness;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.);
        gl_PointSize = pixelRatio * (2. + 8. * glow);
      }`,
    fragmentShader: `
      varying float glow;
      void main() {
        vec2 point = 2. * gl_PointCoord - 1.;
        float distanceSquared = dot(point, point);
        float halo = exp(-5. * distanceSquared) * (1. - smoothstep(.65, 1., distanceSquared));
        float core = exp(-22. * distanceSquared);
        gl_FragColor = vec4(mix(vec3(1., .49, .21), vec3(1., .96, .78), core), glow * halo);
      }`,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  });
  const points = new THREE.Points(geometry, material);
  points.name = 'Illustrative atmospheric meteors';
  points.visible = false;
  points.frustumCulled = false;
  const towardCamera = new THREE.Vector3();
  const sideways = new THREE.Vector3();
  const up = new THREE.Vector3();
  const radial = new THREE.Vector3();
  const tangent = new THREE.Vector3();
  const sample = new THREE.Vector3();
  let wait = .9;
  let age = -1;
  let duration = .8;
  let sweep = .24;

  function start() {
    const angle = random() * Math.PI * 2;
    const roll = random() * Math.PI * 2;
    const facing = .32 + random() * .47;
    const rim = Math.sqrt(1 - facing * facing);
    const pole = Math.abs(towardCamera.y) < .9 ? up.set(0, 1, 0) : up.set(1, 0, 0);
    sideways.crossVectors(pole, towardCamera).normalize();
    up.crossVectors(towardCamera, sideways).normalize();
    radial.copy(towardCamera).multiplyScalar(facing)
      .addScaledVector(sideways, rim * Math.cos(angle))
      .addScaledVector(up, rim * Math.sin(angle));
    sideways.crossVectors(towardCamera, radial).normalize();
    up.crossVectors(radial, sideways).normalize();
    tangent.copy(sideways).multiplyScalar(Math.cos(roll)).addScaledVector(up, Math.sin(roll));
    age = 0;
    duration = .57 + random() * .32;
    sweep = .17 + random() * .13;
  }

  function update(camera, delta, enabled) {
    towardCamera.copy(camera).sub(center);
    const distance = towardCamera.length() / radius;
    if (!enabled || distance < inner || distance > 8) {
      points.visible = false;
      age = -1;
      wait = .9;
      return;
    }
    towardCamera.normalize();
    if (age < 0) {
      wait -= delta;
      if (wait > 0) return;
      start();
      age = -wait;
    } else {
      age += delta;
    }
    if (age > duration) {
      age = -1;
      wait = 2.1 + 4 * random();
      points.visible = false;
      return;
    }
    points.position.copy(center);
    points.visible = true;
    for (let i = 0; i < count; i++) {
      const elapsed = age - i * .023;
      const fraction = THREE.MathUtils.clamp(elapsed / duration, 0, 1);
      const arc = fraction * sweep;
      sample.copy(radial).multiplyScalar(Math.cos(arc)).addScaledVector(tangent, Math.sin(arc))
        .multiplyScalar(radius * THREE.MathUtils.lerp(outer, inner, fraction));
      sample.toArray(positions, i * 3);
      brightness[i] = Math.sin(Math.PI * fraction) ** .65 * (1 - i / count) ** 1.7;
    }
    geometry.attributes.position.needsUpdate = true;
    geometry.attributes.brightness.needsUpdate = true;
  }

  return {points, update};
}
