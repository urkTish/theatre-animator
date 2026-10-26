// The film's own timeline, laid over the reused scene timeline (timeline.js, unchanged from ../motion).
// Film time t runs 0..DUR. The scene (doors, roll, wheels, every character slot) runs on scene time
// ts = t - OFFSET, so the 2.8 s lead-in (house light, lamp, the door layer) never touches the facts:
// doors 1.0-2.9 s scene = 3.8-5.7 s film, roll 3.0-7.0 s scene = 5.8-9.8 s film (2.93 m in 4.0 s).
// Everything here is a pure function of t.
import { clamp, lerp, smoothstep, smootherstep } from './util.js';
import { GEO, T as ST } from './timeline.js';

export const FPS = 24;
export const OFFSET = 2.8;
export const DUR = 15.0;
export const sceneT = (t) => t - OFFSET;

// cue sheet (film seconds)
export const F = {
  idIn: 0.25,
  relay: 1.45,                       // house light cuts (0.25 s)
  lamp: 1.8,                         // lamp strikes, projector black level + grid
  door: 2.05,                        // 01 THE DOOR: cool wash on the doorway, outline
  dimW: [2.35, 3.05],                // dimension line, width 2.8 m
  dimH: [2.55, 3.2],               // dimension line, height 3.2 m
  doors: [ST.doors[0] + OFFSET, ST.doors[1] + OFFSET],   // 3.8-5.7: leaves swing inward, swing quadrants traced
  pick: 5.25,                        // the waiting platform picked out inside
  lane: 5.35,                        // 02 THE ROLL: the lane draws on
  roll: [ST.roll[0] + OFFSET, ST.roll[1] + OFFSET],      // 5.8-9.8
  evid: 10.25,                        // 03 HOW SURE?
  pinA: 10.45, pinI: 10.9, pinR: 11.35,
  lightsUp: 12.9,                   // house light returns slowly (1 s); the evidence layer stays on alone
  end: DUR,
};

const ss = smoothstep, s5 = smootherstep;
export const seg = (t, a, b) => clamp((t - a) / (b - a));
export const eo = (x) => 1 - (1 - x) ** 3;
export const env = (t, t0, t1, fin = 0.35, fout = 0.3) => Math.min(eo(seg(t, t0, t0 + fin)), 1 - ss(t1 - fout, t1, t));

// ------------------------------------------------------------------ light state
export function lightAt(t) {
  const off = ss(F.relay, F.relay + 0.25, t);                 // relay: fast
  const back = ss(F.lightsUp, F.lightsUp + 1.0, t);           // returns slowly
  const house = lerp(1, 0.27, off) * (1 - back) + 0.66 * back;
  const strike = seg(t, F.lamp, F.lamp + 0.12);
  const flick = t > F.lamp && t < F.lamp + 0.28 ? 0.72 + 0.28 * Math.sin((t - F.lamp) * 95) : 1;
  const proj = strike * flick;
  // layer amounts (0..1). Earlier layers dim as later ones arrive, and all but the evidence fade with the lights.
  const keep = 1 - 0.85 * back;
  const door = ss(F.door, F.door + 0.5, t) * lerp(1, 0.2, ss(F.lane, F.lane + 0.6, t)) * (1 - ss(F.evid, F.evid + 0.6, t));
  const arcs = ss(F.doors[0] - 0.2, F.doors[0] + 0.2, t) * lerp(1, 0.5, ss(F.roll[0], F.roll[0] + 0.8, t)) * (1 - ss(F.evid, F.evid + 0.6, t));
  const pick = ss(F.pick, F.pick + 0.25, t) * (1 - ss(F.roll[0] + 0.6, F.roll[0] + 1.6, t));
  const lane = ss(F.lane, F.lane + 0.3, t) * keep;
  const laneDraw = eo(seg(t, F.lane, F.lane + 0.55));
  const land = t > F.roll[1] ? Math.exp(-(t - F.roll[1]) / 0.35) : 0;
  const evA = ss(F.pinA, F.pinA + 0.35, t), evI = ss(F.pinI, F.pinI + 0.35, t), evR = ss(F.pinR, F.pinR + 0.35, t);
  const flash = (t0) => (t > t0 ? Math.exp(-(t - t0) / 0.18) : 0);
  return { house, proj, door, arcs, pick, lane, laneDraw, land, evA, evI, evR, fA: flash(F.pinA), fI: flash(F.pinI), fR: flash(F.pinR), back };
}

// ------------------------------------------------------------------ camera
// One continuous take. Keys: position, target, vertical fov. Monotone cubic (Catmull-Rom with
// finite-difference tangents scaled to the segment), so the camera never stops dead and never overshoots much.
const K = [
  { t: 0.0, p: [15.5, 12.8, 26.5], q: [-1.6, 0.4, -0.2], fov: 30 },
  { t: 2.4, p: [9.8, 6.4, 16.8], q: [-1.45, 1.45, -0.3], fov: 30 },
  { t: 5.8, p: [7.3, 3.3, 11.8], q: [-1.35, 1.35, 0.0], fov: 30 },
  { t: 7.8, p: [5.5, 2.15, 9.9], q: [-1.0, 0.95, 0.35], fov: 30 },
  { t: 10.0, p: [2.5, 1.78, 9.7], q: [-0.25, 0.95, 0.45], fov: 30 },
  { t: DUR, p: [0.45, 1.62, 8.95], q: [0.05, 0.9, 0.5], fov: 29 },
];
function interp(key, t) {
  const tt = clamp(t, K[0].t, K[K.length - 1].t);
  let i = 0;
  while (i < K.length - 2 && tt > K[i + 1].t) i++;
  const a = K[i], b = K[i + 1], h = b.t - a.t, u = (tt - a.t) / h;
  const tan = (j) => {
    const A = K[Math.max(0, j - 1)], B = K[Math.min(K.length - 1, j + 1)];
    const f = (va, vb) => (vb - va) / (B.t - A.t);
    // first and last keys: ease in from / out to rest (zero velocity) only at the very ends
    if (j === 0) return Array.isArray(a[key]) ? a[key].map(() => 0) : 0;
    if (j === K.length - 1) return Array.isArray(a[key]) ? K[j][key].map((v, k) => 0.35 * (v - K[j - 1][key][k]) / (K[j].t - K[j - 1].t)) : 0;
    return Array.isArray(A[key]) ? A[key].map((v, k) => f(v, B[key][k])) : f(A[key], B[key]);
  };
  const va = tan(i), vb = tan(i + 1);
  const H = (p0, v0, p1, v1) => {
    const u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * v0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * v1;
  };
  return Array.isArray(a[key]) ? a[key].map((v, k) => H(v, va[k], b[key][k], vb[k])) : H(a[key], va, b[key], vb);
}

export const TABLEAU_FOCUS = [0.0, 0.85, 0.45];
export function cameraAt(t) {
  const p = interp('p', t), q = interp('q', t), fov = interp('fov', t);
  // focus: on the door while it is measured and opens, then pulled to the tableau as it arrives
  const door = [0, 1.6, 0];
  const k = s5(F.roll[0] + 1.0, F.roll[1], t);
  const f = door.map((v, i) => lerp(v, TABLEAU_FOCUS[i], k));
  const focus = Math.hypot(p[0] - f[0], p[1] - f[1], p[2] - f[2]);
  // miniature depth of field: shallow on the opening glide, a touch less on the door, shallow again on the tableau
  const aperture = lerp(1.25, 0.55, ss(1.2, 3.2, t)) + 0.75 * ss(F.roll[0] + 1.5, F.roll[1] + 1.0, t);
  return { position: p, target: q, fov, focus, aperture };
}

// platform front edge z at film time t (for overlays); same function the set uses
export { GEO };
