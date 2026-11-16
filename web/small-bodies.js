import * as THREE from 'three';

const tau = 2 * Math.PI;

function randomFrom(seed) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
}

export function smallBodyOrbits(jupiter, outer = true) {
  const random = randomFrom(140905);
  const range = (low, high) => low + (high - low) * random();
  const populations = [
    ['main', 520, () => [range(2.13, 3.28), range(.015, .13), range(0, .24), range(0, tau), range(.0025, .012)]],
    ['near', 42, () => [range(1.05, 1.78), range(.26, .44), range(0, .37), range(0, tau), range(.003, .009)]]
  ];
  if (jupiter) {
    const phase = Math.atan2(jupiter[1], jupiter[0]);
    for (const side of [-1, 1]) {
      populations.push(['trojan', 76, () => [
        range(5.04, 5.36), range(.008, .12), range(0, .29),
        phase + side * Math.PI / 3 + (random() + random() - 1) * .52, range(.0035, .016)
      ]]);
    }
  }
  if (outer) {
    populations.push(['kuiper', 380, () => [range(32, 48), range(.01, .075), range(0, .26), range(0, tau), range(.038, .09)]]);
  }
  return populations.flatMap(([group, count, sample]) => Array.from({length: count}, () => {
    const [a, e, inclination, phase, size] = sample();
    const node = range(0, tau);
    return {
      group, a, e, phase, size, cosI: Math.cos(inclination), sinI: Math.sin(inclination),
      cosNode: Math.cos(node), sinNode: Math.sin(node), node, spin: range(0, tau),
      rate: tau / (365.256 * a ** 1.5)
    };
  }));
}

export function createSmallBodies(jupiter) {
  const orbits = smallBodyOrbits(jupiter);
  const geometry = new THREE.DodecahedronGeometry(1);
  const vertices = geometry.attributes.position;
  for (let i = 0; i < vertices.count; i++) {
    const x = vertices.getX(i), y = vertices.getY(i), z = vertices.getZ(i);
    const scale = 1 + .26 * Math.sin(x * 7 + y * 9 + z * 13);
    vertices.setXYZ(i, x * scale, y * scale * .8, z * scale);
  }
  geometry.computeVertexNormals();
  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff, roughness: 1, flatShading: true, emissive: 0x281f19, emissiveIntensity: .8
  });
  const mesh = new THREE.InstancedMesh(geometry, material, orbits.length);
  mesh.name = 'Illustrative Solar System small bodies';
  mesh.frustumCulled = false;
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  const dummy = new THREE.Object3D();
  const palette = [
    new THREE.Color('#b69b81'), new THREE.Color('#99938f'), new THREE.Color('#81796d'),
    new THREE.Color('#c4af90'), new THREE.Color('#a4becb')
  ];
  orbits.forEach((orbit, i) => mesh.setColorAt(i, palette[orbit.group === 'kuiper' ? 4 : i % 4]));
  let lastDay = NaN, lastTick = -Infinity;

  function update(days, now) {
    if (!mesh.visible || days === lastDay || now - lastTick < 90) return;
    lastDay = days;
    lastTick = now;
    orbits.forEach((orbit, i) => {
      // First-order eccentric orbit. Locations and sizes here are illustrative.
      const m = orbit.phase - orbit.node + days * orbit.rate;
      const a = m + 2 * orbit.e * Math.sin(m);
      const r = orbit.a * (1 - orbit.e * Math.cos(m));
      const x = r * Math.cos(a), y = r * Math.sin(a);
      dummy.position.set(x * orbit.cosNode - y * orbit.cosI * orbit.sinNode,
        y * orbit.sinI, -(x * orbit.sinNode + y * orbit.cosI * orbit.cosNode));
      dummy.rotation.set(orbit.spin, orbit.spin * 1.7 + days * .045, orbit.spin * .7);
      dummy.scale.setScalar(orbit.size);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }

  update(0, 0);
  return {mesh, update};
}
