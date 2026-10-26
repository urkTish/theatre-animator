// motion.js: evaluates a slot's motion track (cast/cast.js) at time t into a pose for rigPerson() and a place in the
// world. Everything is a pure function of t, so frames render in any order.
//
// track = {
//   space: 'world' | 'platform',   // 'platform': root keys are relative to the ekkyklema's deck (it rides out with it)
//   root:  [[t, x, z, dur?], ...],  // ground point (metres); each key is an eased move of `dur` seconds (default .6)
//   steps: true,                    // feet step (alternately) while the root moves
//   keys:  [[t, { params }, dur?, ease?], ...],   // pose keys: each param eases from its previous value to this one
//   add:   [[t0, t1, 'param', amp, freq, phase?], ...],   // sine layers (beckons, waggles, writing), faded in and out
//   idle:  { breath, sway, seed },  // always-on life: breathing, a slow weight sway, a drifting head
// }
// Pose params: heading, headHeading, lean, hip, crouch, bob, headTilt, headDx, headDy, recline, kneeUp,
// r.a r.e r.w r.h r.palm r.stylus r.hand r.bend (and l.*), tablet, headDown, tabletRot.
// Overlapping action is built in: the head leads, the body follows, the arms and then the hands trail (DELAY).
const DELAY = { headHeading: -.07, headTilt: -.05, headDx: -.05, headDy: -.05, heading: 0, lean: .02, hip: .03, crouch: .02, 'r.a': .05, 'r.e': .09, 'r.w': .13, 'l.a': .07, 'l.e': .11, 'l.w': .15, 'r.hand': .04, 'l.hand': .06 };
const EASES = { ease, easeOut, easeIn, backOut, smoother, lin: x => clamp(x) };
function flatKeys(o, pre = '', out = {}) { for (const k in o) { const v = o[k]; if (v && typeof v === 'object' && !Array.isArray(v)) flatKeys(v, pre + k + '.', out); else out[pre + k] = v; } return out; }
function setPath(o, path, v) { const ks = path.split('.'); let c = o; for (let i = 0; i < ks.length - 1; i++) c = c[ks[i]] = c[ks[i]] || {}; c[ks[ks.length - 1]] = v; }
function evalTrack(M, t, spaceZ = () => 0) {
  // pose: sequential tweens per parameter
  const vals = {}, disc = {};
  for (const [kt, params, dur = .45, en = 'ease'] of M.keys) {
    const f = flatKeys(params), E = EASES[en] || ease;
    for (const p in f) {
      const v = f[p], dl = DELAY[p] || 0, t0 = kt + dl, t1 = t0 + dur;
      if (typeof v === 'number') { const k = E(seg(t, t0, t1)); if (!(p in vals)) vals[p] = v; else if (t >= t0) vals[p] = lerp(vals[p], v, k); }
      else if (Array.isArray(v)) { const k = E(seg(t, t0, t1)); if (!(p in vals)) vals[p] = v.slice(); else if (t >= t0) vals[p] = vals[p].map((a, i) => lerp(a, v[i], k)); }
      else { if (!(p in disc) || t >= t0 + dur * .45) disc[p] = v; }
    }
  }
  for (const [t0, t1, p, amp, freq, ph = 0] of (M.add || [])) {
    if (t < t0 || t > t1) continue;
    const env = smoother(seg(t, t0, t0 + .15)) * (1 - smoother(seg(t, t1 - .15, t1))), w = amp * env * Math.sin(TAU * freq * (t - t0) + ph);
    const ix = p.match(/^(.*)\[(\d)\]$/);
    if (ix) { if (vals[ix[1]]) vals[ix[1]][+ix[2]] += w; } else vals[p] = (vals[p] || 0) + w;
  }
  const I = M.idle || {}, sd = I.seed || 0;
  vals.bob = (vals.bob || 0) + (I.breath ?? 1) * .006 * Math.sin(TAU * t / 3.3 + sd);
  vals.hip = (vals.hip || 0) + (I.sway ?? 1) * .01 * Math.sin(TAU * t / 5.7 + sd * 2);
  vals.headTilt = (vals.headTilt || 0) + (I.sway ?? 1) * .02 * Math.sin(TAU * t / 4.3 + sd * 3);
  const P = {};
  for (const p in vals) setPath(P, p, vals[p]);
  for (const p in disc) setPath(P, p, disc[p]);
  // root: eased moves; feet step while it moves (in local metres, relative to the root)
  const RZ = k => k[2] + (k[4] ? spaceZ(k[4], t) : 0);
  const R0 = M.root[0]; let x = R0[1], z = RZ(R0); const feet = { r: { dx: 0, dy: 0 }, l: { dx: 0, dy: 0 } };
  let fx = { r: x, l: x }, fz = { r: z, l: z };
  for (let i = 1; i < M.root.length; i++) {
    const [kt, nx, , dur = .6] = M.root[i], nz = RZ(M.root[i]), k = ease(seg(t, kt, kt + dur));
    if (t >= kt) {
      const px = x, pz = z; x = lerp(x, nx, k); z = lerp(z, nz, k);
      if (M.steps) for (const [side, a, b] of [['r', 0, .58], ['l', .42, 1]]) {
        const u = ease(seg(t, kt + a * dur, kt + b * dur)); fx[side] = lerp(fx[side], nx, u); fz[side] = lerp(fz[side], nz, u);
        feet[side].dy += .045 * Math.sin(Math.PI * seg(t, kt + a * dur, kt + b * dur));
      } else { fx = { r: x, l: x }; fz = { r: z, l: z }; }
    }
  }
  for (const s of ['r', 'l']) { feet[s].dx += fx[s] - x; feet[s].dy -= (fz[s] - z) * .3; }
  if (M.steps) { P.feet = P.feet || {}; for (const s of ['r', 'l']) { const F = P.feet[s] = P.feet[s] || {}; F.dx = (F.dx || 0) + feet[s].dx; F.dy = (F.dy || 0) + feet[s].dy; } }
  // the hem's follow-through: it drags behind the root's sideways speed
  const v = (() => { let xa = R0[1], xb = R0[1]; for (let i = 1; i < M.root.length; i++) { const [kt, nx, , dur = .6] = M.root[i]; xa = lerp(xa, nx, ease(seg(t - .08, kt, kt + dur))); xb = lerp(xb, nx, ease(seg(t, kt, kt + dur))); } return (xb - xa) / .08; })();
  P.swing = (P.swing || 0) - v * .05;
  return { P, root: [x, 0, z] };
}
