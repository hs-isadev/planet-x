// Project the catalog map through the same camera rays used by the archive search.
const vertex = 'attribute vec2 corner; void main(){gl_Position=vec4(corner,0.,1.);}';
const fragment = `
precision highp float;
uniform vec2 size;
uniform float focal;
uniform vec3 forward, right, up;
uniform sampler2D stars;
uniform float brightness;
void main() {
  vec2 offset = (gl_FragCoord.xy - size * .5) / focal;
  vec3 ray = normalize(forward + offset.x * right + offset.y * up);
  float longitude = abs(ray.x) + abs(ray.y) < 1e-8 ? 0. : atan(ray.y, ray.x);
  float u = fract(.5 - longitude / 6.28318530718);
  float v = .5 - asin(clamp(ray.z, -1., 1.)) / 3.14159265359;
  vec3 field = texture2D(stars, vec2(u, v)).rgb;
  vec3 sky = max(field - vec3(.025, .025, .033), 0.);
  vec3 color = vec3(.022, .030, .055) + pow(sky, vec3(.66)) * brightness;
  gl_FragColor = vec4(min(color, 1.), 1.);
}`;

export async function loadCatalogSky(canvas) {
  const gl = canvas.getContext('webgl', {alpha: false, antialias: false});
  if (!gl) throw new Error('WebGL is unavailable');
  const image = new Image();
  image.src = '/assets/sky/satellite-sky.jpg';
  await image.decode();

  const program = gl.createProgram();
  const shaders = [];
  for (const [type, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]]) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    gl.attachShader(program, shader);
    shaders.push(shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  shaders.forEach(shader => gl.deleteShader(shader));
  gl.useProgram(program);
  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  const corner = gl.getAttribLocation(program, 'corner');
  gl.enableVertexAttribArray(corner);
  gl.vertexAttribPointer(corner, 2, gl.FLOAT, false, 0, 0);
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, image);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  if (gl.getError() !== gl.NO_ERROR) throw new Error('This device cannot render the catalog texture');
  const uniform = Object.fromEntries(['size', 'focal', 'forward', 'right', 'up', 'brightness']
    .map(name => [name, gl.getUniformLocation(program, name)]));
  canvas.addEventListener('webglcontextlost', () => { canvas.hidden = true; });
  return (camera, focal, brightness) => {
    if (gl.isContextLost()) return false;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(uniform.size, canvas.width, canvas.height);
    gl.uniform1f(uniform.focal, focal);
    gl.uniform1f(uniform.brightness, brightness);
    for (const axis of ['forward', 'right', 'up']) gl.uniform3fv(uniform[axis], camera[axis]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    return true;
  };
}
