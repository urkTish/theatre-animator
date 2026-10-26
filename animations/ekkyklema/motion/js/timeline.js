// The one shared timeline: geometry facts, machinery motion and the camera.
// Everything here is a pure function of t (seconds). Nothing reads the clock.
import { clamp, lerp, smootherstep, smoothstep } from './util.js';

export const FPS = 24;
export const DURATION = 10.0;

// Facts (STORYBOARD R1-R7, layout.svg, SHOTLIST). Units: metres.
// Axes: x along the facade (+x = audience's right), y up, z toward the audience.
// The facade face is the plane z = 0; the boarded wall runs from z = -WALL_T to 0.
export const GEO = {
  SKENE_W: 12.0, SKENE_H: 5.0, SKENE_D: 4.7, WALL_T: 0.20,
  DOOR_W: 2.8, DOOR_H: 3.2, LEAF_T: 0.065,
  PLAT_W: 2.4, PLAT_D: 1.6, PLAT_H: 0.30, WHEEL_R: 0.12,
  PLAT_FRONT_IN: -1.68,      // front edge waits 1.68 m behind the facade face (R6)
  ROLL: 2.93,                // rolls 2.93 m ...
};
GEO.PLAT_Z_IN = GEO.PLAT_FRONT_IN - GEO.PLAT_D / 2;   // platform centre, rolled in
GEO.PLAT_Z_OUT = GEO.PLAT_Z_IN + GEO.ROLL;           // ... front edge ends 1.25 m beyond the facade

export const T = {
  card_in: [0.25, 1.05],
  doors: [1.0, 2.9],          // leaves swing inward, fully open before the roll
  crumb: [2.15, 3.0],         // breadcrumb outline on the platform (~0.8 s before it moves)
  roll: [3.0, 7.0],           // 2.93 m in 4.0 s, quintic ease in and out, no overshoot
  hold: [7.0, 10.0],
};

export function doorAngle(t) {            // radians, 0 = shut, PI/2 = fully open (inward)
  return (Math.PI / 2) * smootherstep(T.doors[0], T.doors[1], t);
}
export function rollDistance(t) {         // metres travelled by the platform
  return GEO.ROLL * smootherstep(T.roll[0], T.roll[1], t);
}
export function platformZ(t) {            // platform centre z
  return GEO.PLAT_Z_IN + rollDistance(t);
}
export function wheelAngle(t) {           // rolling without slip: angle = distance / radius
  return rollDistance(t) / GEO.WHEEL_R;
}

// ---- camera -------------------------------------------------------------------
// Cubic Hermite segments with explicit velocities, so the move is C1 smooth:
// a slow drift (0-3 s), a dolly down to audience eye height centred on the door
// (3-7 s), then a very slow push-in on the tableau (7-10 s).
const K = [
  { t: 0.0, p: [-10.6, 3.9, 15.6], q: [1.5, 2.35, 0.0], fov: 34.0 },
  { t: 3.0, p: [-9.9, 3.7, 14.9], q: [1.4, 2.2, 0.0], fov: 34.0 },
  { t: 7.0, p: [0.32, 1.62, 9.9], q: [0.3, 1.42, 0.2], fov: 31.0 },
  { t: 10.0, p: [0.30, 1.59, 9.15], q: [0.29, 1.39, 0.25], fov: 31.0 },
];
function vel(i, key) {
  // drift velocity in the first segments, push velocity in the last
  if (i === 0 || i === 1) {
    const a = K[0][key], b = K[1][key];
    return Array.isArray(a) ? a.map((v, j) => (b[j] - v) / (K[1].t - K[0].t)) : (b - a) / (K[1].t - K[0].t);
  }
  const a = K[2][key], b = K[3][key];
  const s = i === 2 ? 1.0 : 0.55;          // the push decelerates gently towards 10 s
  return Array.isArray(a) ? a.map((v, j) => s * (b[j] - v) / (K[3].t - K[2].t)) : s * (b - a) / (K[3].t - K[2].t);
}
function hermite(p0, v0, p1, v1, u, h) {
  const u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * v0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * v1;
}
function seg(t, key) {
  const tt = clamp(t, K[0].t, K[K.length - 1].t);
  let i = 0;
  while (i < K.length - 2 && tt > K[i + 1].t) i++;
  const a = K[i], b = K[i + 1], h = b.t - a.t, u = (tt - a.t) / h;
  const va = vel(i, key), vb = vel(i + 1, key);
  if (Array.isArray(a[key])) return a[key].map((v, j) => hermite(v, va[j], b[key][j], vb[j], u, h));
  return hermite(a[key], va, b[key], vb, u, h);
}

export const TABLEAU_FOCUS = [0.1, 0.95, 0.35];

export function cameraAt(t) {
  const p = seg(t, 'p'), q = seg(t, 'q'), fov = seg(t, 'fov');
  const dx = p[0] - TABLEAU_FOCUS[0], dy = p[1] - TABLEAU_FOCUS[1], dz = p[2] - TABLEAU_FOCUS[2];
  // depth of field: none on the wide establishing view, subtle on the hold
  const aperture = lerp(0.0, 1.0, smoothstep(5.6, 7.6, t));
  return { position: p, target: q, fov, focus: Math.hypot(dx, dy, dz), aperture };
}
