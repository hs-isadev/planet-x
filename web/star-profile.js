// Optical halo and diffraction wings shared by both sky views.
export const stellarProfileGLSL = `
uniform float flare;
float stellarProfile(vec2 q, float brightness) {
  float r = length(q);
  float edge = 1.0 - smoothstep(0.75, 1.0, r);
  float core = exp(-10.0 * r * r);
  float halo = 0.48 * exp(-3.6 * r);
  vec2 axis = abs(q);
  float rays = exp(-56.0 * min(axis.x, axis.y)) * exp(-2.4 * r);
  return edge * (core + flare * brightness * (halo + 0.25 * rays));
}
`;
