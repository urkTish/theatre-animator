// people.js: the masked actors and the stagehands, painted like the rest of the kit (flat wash, ink outline, boil).
//
// Two halves, kept apart on purpose, so a character's LOOK can be swapped without moving anything:
//   RIG     rigPerson(slot, pose) -> joints and anchors in local metres. It knows the body proportions of the slot
//           (in the cast file) and the pose (from the motion track). It knows nothing about colours or costume.
//   PAINTER paintPerson(rig, look, env) -> paints the rig with a look (src/looks.js): mask, hair, robe, patterns.
// Tracks (tracks.json) are made from the rig alone, so they are identical whatever look fills a slot.
//
// Local space: metres, origin on the ground between the feet (for the reclining figure: the middle of the couch's
// mattress top), +x = screen right, +y = up. Views are drawn KEY VIEWS (front, q = 3/4, side), all facing screen-right;
// flip mirrors them to face left. A turn snaps through the key views; nothing is projected.
// Arm angles are in the facing frame: a = 0 hangs down, + swings forward (toward the facing side; in the front view,
// outward from the body). e bends the elbow further the same way, w the wrist. Hands: relax, open, point, fist, beckon,
// hold, flat, cup, grip.

// ---------------------------------------------------------------- local transform (metres, y up -> screen px)
const XF = { m: [1, 0, 0, 1, 0, 0], st: [], k: 1, ox: 0, oy: 0, fl: 1, J: 1 };
function xfBegin(ox, oy, k, flip) { XF.m = [1, 0, 0, 1, 0, 0]; XF.st = []; XF.k = k; XF.ox = ox; XF.oy = oy; XF.fl = flip ? -1 : 1; XF.J = clamp(k / 300, .3, 1.6) * .9; }
const xfPush = () => XF.st.push(XF.m.slice());
const xfPop = () => { XF.m = XF.st.pop(); };
function xfT(x, y) { const m = XF.m; m[4] += m[0] * x + m[2] * y; m[5] += m[1] * x + m[3] * y; }
function xfR(a) { const m = XF.m, c = Math.cos(a), s = Math.sin(a), [a0, b0, c0, d0] = m; m[0] = a0 * c + c0 * s; m[1] = b0 * c + d0 * s; m[2] = -a0 * s + c0 * c; m[3] = -b0 * s + d0 * c; }
function xfS(sx, sy = sx) { const m = XF.m; m[0] *= sx; m[1] *= sx; m[2] *= sy; m[3] *= sy; }
const xfLocal = (x, y) => { const m = XF.m; return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]; };
const S = (x, y) => { const [lx, ly] = xfLocal(x, y); return [XF.ox + XF.fl * lx * XF.k, XF.oy - ly * XF.k]; };
// local points -> screen points, with boil jitter (j scales it)
const L = (pts, j = 1) => pts.map(([x, y]) => { const p = S(x, y); return [p[0] + jit(XF.J * j), p[1] + jit(XF.J * j)]; });
// smooth closed curve through local points (Catmull-Rom), n samples per span
function cloop(P, n = 4) {
  const N = P.length, out = [];
  for (let i = 0; i < N; i++) {
    const p0 = P[(i - 1 + N) % N], p1 = P[i], p2 = P[(i + 1) % N], p3 = P[(i + 2) % N];
    for (let k = 0; k < n; k++) { const u = k / n, u2 = u * u, u3 = u2 * u; out.push([0, 1].map(d => .5 * (2 * p1[d] + (p2[d] - p0[d]) * u + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * u2 + (3 * p1[d] - p0[d] - 3 * p2[d] + p3[d]) * u3))); }
  }
  return out;
}
const ellL = (cx, cy, rx, ry, n = 14, rot = 0) => { const p = []; for (let i = 0; i < n; i++) { const a = rot + i / n * TAU; p.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]); } return p; };
// ribbon (tapered) around an open local path, as one closed outline
function ribbonL(P, w0, w1 = w0, n = 5) {
  const C = P.length > 2 ? through(P, n) : P, N = C.length, A = [], B = [];
  for (let i = 0; i < N; i++) {
    const a = C[Math.max(0, i - 1)], b = C[Math.min(N - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy) || 1, w = lerp(w0, w1, i / Math.max(1, N - 1)) / 2;
    A.push([C[i][0] - dy / d * w, C[i][1] + dx / d * w]); B.push([C[i][0] + dy / d * w, C[i][1] - dx / d * w]);
  }
  return A.concat(B.reverse());
}

// the same, with round ends (sleeves, limbs): no square cut where a limb meets the body
function limbL(P, w0, w1 = w0, n = 5) {
  const C = P.length > 2 ? through(P, n) : P, N = C.length, A = [], B = [];
  for (let i = 0; i < N; i++) {
    const a = C[Math.max(0, i - 1)], b = C[Math.min(N - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy) || 1, w = lerp(w0, w1, i / Math.max(1, N - 1)) / 2;
    A.push([C[i][0] - dy / d * w, C[i][1] + dx / d * w]); B.push([C[i][0] + dy / d * w, C[i][1] - dx / d * w]);
  }
  const d0 = Math.atan2(C[1][1] - C[0][1], C[1][0] - C[0][0]), cap = [];
  for (let i = 1; i < 6; i++) { const t = d0 + 1.5 * Math.PI - i / 6 * Math.PI; cap.push([C[0][0] + Math.cos(t) * w0 / 2, C[0][1] + Math.sin(t) * w0 / 2]); }
  return [...A, ...B.reverse(), ...cap];
}

// ---------------------------------------------------------------- colour under the scene light
// env.shade 0..1 sinks every colour toward the dark of the skene's interior; env.warm 0..1 adds the low sun.
const DARK = '#1D1416', SUNC = '#FFD9A0';   // DARK = the skene's interior (SET.dark)
let ENV = { shade: 0, warm: 0 };
const C = c => { let o = c; if (ENV.warm > 0) o = mixCol(o, SUNC, .12 * ENV.warm); if (ENV.shade > 0) o = mixCol(o, DARK, ENV.shade); return o; };
const INK = () => C(PAL.ink);
// painting shortcuts (local points)
const SWB = () => clamp(XF.k / 520, .22, 1.1);                         // base outline weight for this size
function shp(pts, col, o = {}) { paint(L(pts, o.j ?? 1), { wash: C(col), washOp: o.op ?? 255, ink: o.ink === null ? null : C(o.ink || PAL.ink), sw: (o.sw ?? 1) * SWB(), curv: o.curv }); }
function tone(pts, col, op = 120) { paint(L(pts, .6), { wash: C(col), washOp: op, ink: null }); }   // a flat glaze, no outline (shading, light)
function ln(pts, w = .6, col = PAL.ink, br = 'ink', curv = .5) { if (pts.length > 1) inkLine(L(pts, .7), w * SWB(), C(col), br, curv); }

// ---------------------------------------------------------------- hands
// A hand outline from finger parameters, in hand space: x from the wrist (0) toward the fingertips, +y = thumb side.
// fingers: [baseY, angle, length, width] little -> index; thumb: [baseX, baseY, angle, length, width].
const HANDS = {
  relax:  { f: [[-.026, -.02, .07, .021], [-.009, -.005, .078, .022], [.008, .005, .074, .022], [.024, .02, .066, .021]], th: [.03, .03, .62, .052, .024] },
  flat:   { f: [[-.026, -.03, .072, .02], [-.009, -.01, .082, .021], [.008, .01, .078, .021], [.024, .03, .07, .02]], th: [.028, .031, .38, .056, .023] },
  open:   { f: [[-.027, -.34, .058, .019], [-.01, -.12, .074, .02], [.007, .08, .072, .02], [.024, .27, .064, .019]], th: [.025, .032, 1.0, .056, .024] },
  beckon: { f: [[-.026, -.5, .03, .022], [-.009, -.3, .036, .023], [.008, -.1, .04, .023], [.024, .2, .05, .022]], th: [.03, .03, .8, .05, .024] },
  point:  { f: [[-.024, -.9, .022, .024], [-.008, -.8, .025, .024], [.008, -.6, .027, .024], [.022, .06, .082, .02]], th: [.03, .03, 1.2, .045, .024] },
  fist:   { f: [[-.024, -1.0, .022, .025], [-.008, -.9, .025, .025], [.008, -.8, .026, .025], [.024, -.7, .026, .025]], th: [.035, .028, 1.5, .04, .025] },
  hold:   { f: [[-.024, -.9, .022, .025], [-.008, -.8, .025, .025], [.008, -.6, .028, .025], [.024, -.3, .034, .023]], th: [.035, .03, .5, .05, .024] },
  cup:    { f: [[-.026, -.25, .05, .021], [-.009, -.12, .06, .022], [.008, -.02, .06, .022], [.024, .08, .055, .021]], th: [.03, .032, .7, .052, .024] },
};
function handOutline(name) {
  const H = HANDS[name] || HANDS.relax, out = [], palmX = .085;
  out.push([0, -.03], [.04, -.038], [palmX - .006, -.036]);
  H.f.forEach(([by, a, len, w], i) => {
    const bx = palmX - (i === 0 ? .008 : 0) + (i === 3 ? -.004 : 0), c = Math.cos(a), s = Math.sin(a), hw = w / 2;
    const tip = [bx + c * len, by + s * len];
    out.push([bx - s * -hw, by - hw * c], [tip[0] - s * -hw * .9 - c * .002, tip[1] - hw * .9 * c], [tip[0] + c * hw * .8, tip[1] + s * hw * .8], [tip[0] + s * -hw * .9, tip[1] + hw * .9 * c], [bx + s * -hw * .6 + c * .004, by + hw * .9 * c]);
  });
  const [tx, ty, ta, tl, tw] = H.th, c = Math.cos(ta), s = Math.sin(ta), tip = [tx + c * tl, ty + s * tl];
  out.push([palmX - .02, .03], [tip[0] + s * tw * .45, tip[1] - c * tw * .45], [tip[0] + c * tw * .4, tip[1] + s * tw * .4], [tip[0] - s * tw * .5, tip[1] + c * tw * .5], [tx - .012, ty + .012], [.012, .032], [0, .03]);
  return out;
}
// paint a hand at the current transform (origin = wrist, +x along the hand)
function paintHand(name, skin, shadeCol, o = {}) {
  const pts = handOutline(name);
  shp(pts, skin, { sw: .85, j: .4 });
  const H = HANDS[name] || HANDS.relax;
  if (['fist', 'hold', 'point', 'beckon'].includes(name)) ln([[.07, -.03], [.078, 0], [.075, .025]], .45, PAL.ink, 'inkfine', .5);   // knuckle line
  else ln([[.034, .022], [.06, .012], [.075, .016]], .4, PAL.ink, 'inkfine', .5);                                                  // the thumb's crease
  if (o.stylus) ln([[.06, .0], [.03, -.07], [.0, -.13]], .55, '#5b4630', 'inkfine', 0);
}

// ---------------------------------------------------------------- the masks (heads)
// Head space: origin at the eyes' midline, metres, facing right. The masks are whole-head, painted linen: a calm face,
// painted eyes (white, iris, a small dark pupil opening), small parted lips, attached hair and beard (Pronomos Vase).
// look.mask = { skin, shade, hair, hairDk, beard, beardDk, iris, lip, fillet, style: 'prime' | 'elder' }
function curlRow(x0, y0, x1, y1, n, r, up = 1) {   // a scalloped edge of curls from (x0,y0) to (x1,y1)
  const p = [];
  for (let i = 0; i <= n * 3; i++) { const u = i / (n * 3), b = Math.abs(Math.sin(u * n * Math.PI)); p.push([lerp(x0, x1, u), lerp(y0, y1, u) - up * r * b]); }
  return p;
}
function spiral(cx, cy, r, turns = 1.3, dir = 1) { const p = []; for (let i = 0; i <= 10; i++) { const u = i / 10, a = dir * u * turns * TAU, rr = r * (1 - u * .8); p.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]); } return p; }

// resample a closed curve evenly and push every point out by a wave: curly edges for hair and beards
function bumpy(P, amp, n, phase = 0, from = 0, to = 1) {
  const C = cloop(P, 4), N = C.length, len = [0];
  for (let i = 1; i <= N; i++) len.push(len[i - 1] + Math.hypot(C[i % N][0] - C[i - 1][0], C[i % N][1] - C[i - 1][1]));
  const tot = len[N], M = Math.max(24, n * 6), out = [];
  let cx = 0, cy = 0; for (const p of C) { cx += p[0]; cy += p[1]; } cx /= N; cy /= N;
  let j = 0;
  for (let m = 0; m < M; m++) {
    const d = m / M * tot; while (len[j + 1] < d) j++;
    const a = C[j], b = C[(j + 1) % N], u = (d - len[j]) / ((len[j + 1] - len[j]) || 1), x = lerp(a[0], b[0], u), y = lerp(a[1], b[1], u);
    let nx = b[1] - a[1], ny = -(b[0] - a[0]); const nl = Math.hypot(nx, ny) || 1; nx /= nl; ny /= nl;
    if ((x - cx) * nx + (y - cy) * ny < 0) { nx = -nx; ny = -ny; }
    const f = m / M, on = f >= from && f <= to ? 1 : 0, w = on * amp * Math.abs(Math.sin((f * n + phase) * Math.PI));
    out.push([x + nx * w, y + ny * w]);
  }
  return out;
}
const curlC = (cx, cy, r, dir = 1, a0 = .3) => { const p = []; for (let i = 0; i <= 6; i++) { const a = a0 + dir * i / 6 * 4.2; p.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return p; };   // a 'c' stroke

function paintMask(view, M, o = {}) {
  const elder = M.style === 'elder', back = o.part !== 'front', front = o.part !== 'back';
  const hl = mixCol(M.hair, '#F3E6CF', .28), bhl = mixCol(M.beard, '#F3E6CF', .28), bl = elder ? -.27 : -.2;
  // a painted almond eye: white, iris, the small dark pupil opening, a fine upper lid
  const eye = (cx, cy, w, h, iw, kind = 'front') => {
    const al = kind === 'side' ? [[cx - w * .42, cy + h * .3], [cx - w * .05, cy + h * .62], [cx + w * .5, cy + h * .12], [cx + w * .38, cy - h * .2], [cx - w * .05, cy - h * .48], [cx - w * .4, cy - h * .28]]
                               : [[cx - w / 2, cy + h * .02], [cx - w * .22, cy + h * .62], [cx + w * .22, cy + h * .62], [cx + w / 2, cy + h * .08], [cx + w * .2, cy - h * .5], [cx - w * .22, cy - h * .48]];
    shp(al, M.white || '#F4E9D6', { ink: null, j: .25, curv: .3 });
    const ix = kind === 'side' ? cx + w * .2 : cx + (kind === 'far' ? w * .12 : 0);
    shp(ellL(ix, cy + h * .04, iw, iw * 1.04, 12), M.iris, { ink: null, j: .15 });
    shp(ellL(ix, cy + h * .04, iw * .45, iw * .48, 10), '#100b0d', { ink: null, j: .1 });
    ln(kind === 'side' ? [[cx - w * .46, cy + h * .34], [cx - w * .05, cy + h * .66], [cx + w * .55, cy + h * .14]] : [[cx - w * .56, cy + h * .02], [cx - w * .2, cy + h * .66], [cx + w * .25, cy + h * .66], [cx + w * .56, cy + h * .1]], .85, PAL.ink, 'ink', .6);
    ln(kind === 'side' ? [[cx - w * .25, cy - h * .4], [cx + w * .25, cy - h * .3]] : [[cx - w * .3, cy - h * .46], [cx + w * .25, cy - h * .48]], .35, M.shade, 'inkfine', .5);
    if (elder) ln(kind === 'side' ? [[cx - w * .45, cy + h * .95], [cx + w * .35, cy + h * .8]] : [[cx - w * .42, cy + h * 1.0], [cx + w * .38, cy + h * 1.02]], .45, M.shade, 'inkfine', .5);
  };
  const brow = pts => ln(pts, elder ? 1.5 : 1.1, elder ? M.hairDk : M.hairDk, 'ink', .5);
  const beardCurls = (x0, x1, y0, y1, n) => { for (let i = 0; i < n; i++) { const u = (i + .5) / n, x = lerp(x0, x1, u), y = lerp(y0, y1, (i * 37 % n) / n) - .01 * (i % 2); ln(curlC(x, y, .0085, i % 2 ? 1 : -1), .5, bhl, 'inkfine', .5); } };
  const V = {
    front: { hair: [[0, .142], [.085, .124], [.118, .06], [.12, -.04], [.118, -.12], [.1, -.17], [.05, -.18], [-.05, -.18], [-.1, -.17], [-.118, -.12], [-.12, -.04], [-.118, .06], [-.085, .124]],
             face: [[0, .112], [.06, .1], [.078, .05], [.077, -.01], [.066, -.075], [.035, -.115], [0, -.125], [-.035, -.115], [-.066, -.075], [-.077, -.01], [-.078, .05], [-.06, .1]],
             shadow: [[-.078, .05], [-.05, .07], [-.036, .02], [-.042, -.05], [-.062, -.08], [-.077, -.01]], sheen: [.022, .07],
             eyes: [[-.035, .012, .037, .018, .0085, 'front'], [.035, .012, .037, .018, .0085, 'front']],
             brows: [[[-.06, .038], [-.037, .046], [-.013, .04]], [[.013, .04], [.037, .046], [.06, .038]]],
             nose: [[-.005, .03], [-.009, -.005], [-.012, -.03]], nost: [[-.018, -.036], [-.008, -.042], [0, -.039], [.008, -.042], [.018, -.036]],
             beard: [[-.078, .005], [-.074, -.05], [-.042, -.07], [-.02, -.085], [0, -.088], [.02, -.085], [.042, -.07], [.074, -.05], [.078, .005], [.088, -.07], [.074, -.14], [.04, bl + .035], [0, bl], [-.04, bl + .035], [-.074, -.14], [-.088, -.07]],
             bshade: [[-.088, -.07], [-.064, -.06], [-.05, -.12], [-.03, bl + .045], [-.065, -.15]], curls: [-.06, .06, -.1, bl + .05, 7],
             mous: [[-.004, -.054], [-.03, -.061], [-.05, -.08], [-.026, -.071], [0, -.065], [.026, -.071], [.05, -.08], [.03, -.061], [.004, -.054]],
             mouth: [0, -.0755, .017], fringe: [[-.082, .058], [.082, .058], 6], fringeTop: [[.075, .108], [0, .136], [-.075, .108]],
             locks: [[[-.078, .06], [-.088, .0], [-.084, -.06], [-.092, -.12]], [[.078, .06], [.088, .0], [.084, -.06], [.092, -.12]]],
             fillet: [[-.078, .087], [0, .11], [.078, .087], [.076, .099], [0, .122], [-.076, .099]],
             elderSide: [[[-.058, .1], [-.088, .078], [-.098, .02], [-.09, -.035], [-.074, .02], [-.072, .07]], [[.058, .1], [.088, .078], [.098, .02], [.09, -.035], [.074, .02], [.072, .07]]] },
    q: { hair: [[.035, .142], [.075, .112], [.062, .02], [.0, -.1], [-.03, -.18], [-.09, -.19], [-.135, -.16], [-.142, -.06], [-.135, .05], [-.105, .118], [-.04, .145]],
         face: [[.0, .112], [.055, .1], [.073, .06], [.079, .034], [.086, .022], [.11, -.03], [.092, -.04], [.09, -.06], [.074, -.09], [.03, -.122], [-.02, -.115], [-.052, -.08], [-.064, -.01], [-.062, .05], [-.04, .1]],
         shadow: [[-.062, .05], [-.036, .06], [-.026, .0], [-.032, -.06], [-.052, -.08], [-.064, -.01]], sheen: [.034, .07],
         eyes: [[-.006, .012, .036, .018, .0082, 'front'], [.06, .012, .022, .017, .0062, 'far']],
         brows: [[[-.034, .037], [-.008, .046], [.016, .041]], [[.044, .041], [.062, .045], [.078, .038]]],
         nose: [[.046, .03], [.052, .0], [.058, -.026]], nost: [[.07, -.037], [.081, -.043], [.094, -.041]],
         beard: [[-.06, .005], [-.052, -.05], [-.012, -.072], [.03, -.084], [.06, -.082], [.088, -.07], [.094, -.1], [.082, -.15], [.054, bl + .022], [.03, bl], [-.012, bl + .035], [-.054, -.15], [-.074, -.07]],
         bshade: [[-.074, -.07], [-.052, -.06], [-.036, -.12], [-.014, bl + .05], [-.054, -.15]], curls: [-.04, .075, -.1, bl + .05, 6],
         mous: [[.082, -.051], [.058, -.06], [.03, -.077], [.054, -.072], [.074, -.067], [.093, -.078], [.1, -.063]],
         mouth: [.07, -.076, .013], fringe: [[-.064, .06], [.078, .064], 5], fringeTop: [[.062, .115], [.0, .142], [-.072, .11]],
         locks: [[[-.06, .06], [-.07, .0], [-.066, -.06], [-.074, -.12]]],
         fillet: [[-.08, .09], [0, .112], [.07, .095], [.068, .107], [0, .124], [-.08, .102]],
         elderSide: [[[-.03, .11], [-.078, .09], [-.103, .04], [-.098, -.03], [-.072, .0], [-.06, .06]]] },
    side: { hair: [[.065, .13], [.0, .15], [-.08, .132], [-.128, .07], [-.136, -.03], [-.126, -.12], [-.095, -.18], [-.045, -.17], [-.02, -.06], [.02, .0], [.06, .07]],
            face: [[.04, .112], [.075, .092], [.082, .052], [.086, .03], [.09, .02], [.118, -.03], [.1, -.04], [.098, -.056], [.095, -.07], [.082, -.1], [.04, -.12], [.0, -.1], [-.02, -.03], [-.01, .05], [.01, .1]],
            shadow: [[-.02, -.03], [.0, .02], [.02, -.06], [.0, -.1]], sheen: [.062, .072],
            eyes: [[.058, .012, .032, .018, .0064, 'side']],
            brows: [[[.042, .039], [.064, .046], [.083, .04]]],
            nose: null, nost: [[.088, -.037], [.098, -.043], [.106, -.041]],
            beard: [[.0, .01], [.03, -.06], [.072, -.077], [.098, -.074], [.103, -.1], [.093, -.15], [.072, bl + .015], [.04, bl + .02], [.0, -.16], [-.03, -.08]],
            bshade: [[-.03, -.08], [.0, -.06], [.02, -.13], [.0, -.16]], curls: [.0, .085, -.1, bl + .05, 5],
            mous: [[.1, -.049], [.082, -.059], [.064, -.074], [.082, -.07], [.102, -.067]],
            mouth: null, fringe: [[-.01, .072], [.082, .072], 3], fringeTop: [[.072, .118], [.0, .148], [-.04, .1]],
            locks: [[[-.0, .05], [-.016, -.02], [-.012, -.08], [-.022, -.14]]],
            fillet: [[-.08, .102], [.0, .117], [.076, .096], [.074, .108], [.0, .129], [-.08, .114]],
            elderSide: [[[.0, .1], [-.05, .1], [-.077, .04], [-.062, -.03], [-.03, .0], [-.01, .06]]] },
  }[view];
  if (back) {
    // long hair falls behind, to the shoulders, in curly locks
    const H = elder ? V.hair.map(([x, y]) => [x, y > .08 ? y - .01 : y]) : V.hair;
    shp(bumpy(H, .011, 14, 0, .45, 1.0), M.hair, { sw: .9 });
    for (let i = 0; i < 4; i++) { const x = lerp(-.1, .1, i / 3) * (view === 'front' ? 1 : .6) - (view === 'front' ? 0 : .06); ln([[x, .02], [x + .008, -.06], [x - .004, -.15]], .5, hl, 'inkfine', .6); }
  }
  if (!front) return;
  shp(cloop(V.face, 3), M.skin, { sw: 1 });
  tone(cloop(V.shadow, 3), M.shade, 110);
  tone(ellL(V.sheen[0], V.sheen[1], .028, .012, 10, -.12), M.sheen || '#FFF0D8', 80);
  if (elder) for (const yy of [.075, .089]) ln([[V.sheen[0] - .03, yy], [V.sheen[0], yy + .004], [V.sheen[0] + .028, yy - .001]], .45, M.shade, 'inkfine', .6);
  for (const e of V.eyes) eye(...e);
  for (const b of V.brows) brow(elder ? b.map(([x, y], i) => [x, y + (i === 0 ? .004 : 0)]) : b);
  if (V.nose) ln(V.nose, .5, M.shade, 'inkfine', .3);
  ln(V.nost, .6, PAL.ink, 'inkfine', .5);
  // the beard: curly edge, lighter curls on it; the moustache; the small parted lips
  const B = elder ? V.beard.map(([x, y]) => [x, y < -.09 ? y - .02 : y]) : V.beard;
  shp(bumpy(B, .008, 16, .3, .3, .95), M.beard, { sw: .9 });
  tone(cloop(V.bshade, 3), M.beardDk, 110);
  beardCurls(...V.curls);
  shp(V.mous, M.beard, { sw: .6, curv: .4 });
  if (V.mouth) { const [mx, my, mw] = V.mouth; shp(ellL(mx, my, mw, mw * .34, 10), '#2a1316', { ink: null, j: .15 }); shp([[mx - mw * .8, my - .004], [mx, my - .009], [mx + mw * .8, my - .004], [mx + mw * .45, my - .011], [mx - mw * .45, my - .011]], M.lip, { ink: null, j: .15 }); }
  else shp([[.094, -.073], [.085, -.075], [.097, -.081], [.101, -.075]], '#2a1316', { ink: null, j: .1 });
  // hair in front: a fringe of curls (or, for the elder, a bald brow with grey locks at the temples)
  if (elder) {
    for (const E of V.elderSide) shp(bumpy(E, .007, 6), M.hair, { sw: .7 });
    for (const E of V.elderSide) for (let i = 0; i < 3; i++) { const p = E[3 + (i % 2)]; ln(curlC(lerp(E[1][0], p[0], .5), lerp(E[1][1], p[1], .3) - i * .025, .008, -1), .45, hl, 'inkfine', .5); }
  } else {
    const [[fx0, fy0], [fx1, fy1], fn] = V.fringe;
    shp([...curlRow(fx0, fy0, fx1, fy1, fn, .014, 1), ...V.fringeTop], M.hair, { sw: .8 });
    for (let i = 0; i < fn; i++) { const u = (i + .5) / fn; ln(curlC(lerp(fx0, fx1, u), lerp(fy0, fy1, u) + .002, .0075, i % 2 ? 1 : -1, 3.6), .45, hl, 'inkfine', .5); }
    for (const Lk of V.locks) { shp(limbL(Lk, .027, .02), M.hair, { sw: .7 }); ln(Lk.map(([x, y]) => [x + .003, y]), .4, hl, 'inkfine', .6); }
  }
  if (M.fillet) shp(elder ? V.fillet.map(([x, y]) => [x * .85, y + .012]) : V.fillet, M.fillet, { sw: .5, curv: .5 });
}

// The stagehands' own heads (no mask): smaller, short curly hair, simple features.
function paintBareHead(view, M, o = {}) {
  const sw = .9;
  if (view === 'front') {
    shp(cloop([[0, .1], [.06, .085], [.072, .03], [.068, -.03], [.05, -.075], [.0, -.095], [-.05, -.075], [-.068, -.03], [-.072, .03], [-.06, .085]], 3), M.skin, { sw });
    for (const s of [-1, 1]) shp(ellL(s * .074, .0, .013, .022, 10), M.skin, { sw: .6 });
    tone(cloop([[-.07, .03], [-.045, .03], [-.04, -.04], [-.05, -.075], [-.068, -.03]], 3), M.shade, 100);
    shp(cloop([[-.074, .03], [-.08, .07], [-.05, .11], [0, .12], [.05, .11], [.08, .07], [.074, .03], [.06, .05], [.03, .07], [0, .065], [-.03, .07], [-.06, .05]], 3), M.hair, { sw: .8 });
    for (let i = 0; i < 4; i++) ln(spiral(-.045 + i * .03, .09, .007, 1.1, i % 2 ? 1 : -1), .3, M.hairDk, 'inkfine', .5);
    if (!o.down) {
      for (const s of [-1, 1]) { shp(ellL(s * .028, .012, .0065, .008, 8), PAL.ink, { ink: null, j: .2 }); ln([[s * .042, .03], [s * .028, .036], [s * .014, .032]], .5, M.hairDk, 'ink', .5); }
      ln([[-.004, .01], [-.008, -.025], [.006, -.03]], .4, M.shade, 'inkfine', .4);
      ln([[-.016, -.052], [0, -.056], [.016, -.051]], .45, PAL.ink, 'inkfine', .5);
      tone(cloop([[-.05, -.03], [-.03, -.06], [0, -.07], [.03, -.06], [.05, -.03], [.045, -.07], [0, -.092], [-.045, -.07]], 3), M.stubble || M.hairDk, 60);
    }
  } else {
    const side = view === 'side';
    shp(cloop(side ? [[.02, .1], [.07, .07], [.078, .03], [.092, -.005], [.08, -.02], [.078, -.045], [.06, -.08], [.0, -.095], [-.05, -.06], [-.07, .02], [-.04, .09]] : [[.0, .1], [.065, .08], [.074, .03], [.084, .0], [.075, -.02], [.06, -.075], [.0, -.095], [-.05, -.075], [-.068, -.02], [-.065, .05], [-.04, .09]], 3), M.skin, { sw });
    shp(ellL(side ? -.015 : -.035, .0, .014, .022, 10), M.skin, { sw: .6 });
    shp(cloop(side ? [[-.075, .02], [-.07, .08], [-.02, .12], [.04, .115], [.075, .07], [.05, .06], [.0, .07], [-.03, .05], [-.045, .01]] : [[-.07, .03], [-.075, .08], [-.03, .118], [.03, .118], [.075, .075], [.06, .055], [.02, .07], [-.02, .062], [-.05, .04]], 3), M.hair, { sw: .8 });
    for (let i = 0; i < 3; i++) ln(spiral(-.04 + i * .03, .09, .007, 1.1, -1), .3, M.hairDk, 'inkfine', .5);
    if (!o.down) {
      const ex = side ? .055 : .045;
      shp(ellL(ex, .012, .0055, .008, 8), PAL.ink, { ink: null, j: .2 }); ln([[ex - .014, .032], [ex + .012, .034]], .5, M.hairDk, 'ink', .5);
      if (!side) shp(ellL(.0, .012, .006, .008, 8), PAL.ink, { ink: null, j: .2 });
      ln([[ex + .022, -.05], [ex + .008, -.054]], .45, PAL.ink, 'inkfine', .5);
      tone(cloop([[-.02, -.04], [.02, -.06], [.06, -.06], [.07, -.08], [.0, -.092]], 3), M.stubble || M.hairDk, 60);
    }
  }
}

// ---------------------------------------------------------------- band patterns (the poikilon)
// A band between two y levels across the robe, clipped to the robe's outline, with a pattern painted inside it.
function xAt(outline, y) {   // leftmost and rightmost x where the closed outline crosses height y
  let lo = Infinity, hi = -Infinity; const N = outline.length;
  for (let i = 0; i < N; i++) {
    const [x0, y0] = outline[i], [x1, y1] = outline[(i + 1) % N];
    if ((y0 - y) * (y1 - y) <= 0 && y0 !== y1) { const x = x0 + (x1 - x0) * (y - y0) / (y1 - y0); lo = Math.min(lo, x); hi = Math.max(hi, x); }
  }
  return lo < hi ? [lo, hi] : null;
}
// keep a shading shape inside an outline: clamp each point's x into the outline's span at that height
function clampIn(outline, pts, eps = .006) { return pts.map(([x, y]) => { const r = xAt(outline, y); return r ? [clamp(x, r[0] + eps, r[1] - eps), y] : [x, y]; }); }
function bandPts(outline, y0, y1, sag, cx = 0, n = 10) {
  const a = xAt(outline, y0), b = xAt(outline, y1); if (!a || !b) return null;
  const top = [], bot = [], sg = x => -sag * (1 - Math.pow((x - cx) / .3, 2));
  for (let i = 0; i <= n; i++) { const x = lerp(a[0], a[1], i / n); top.push([x, y1 + sg(x)]); }
  for (let i = n; i >= 0; i--) { const x = lerp(b[0], b[1], i / n); bot.push([x, y0 + sg(x)]); }
  return { pts: top.concat(bot), a, b, sg };
}
function paintBand(outline, B, sag, cx) {
  const R = bandPts(outline, B.y, B.y + B.h, sag, cx); if (!R) return;
  shp(R.pts, B.col, { ink: null, j: .4 });
  const yMid = B.y + B.h / 2, x0 = Math.max(R.a[0], R.b[0]) + .012, x1 = Math.min(R.a[1], R.b[1]) - .012, n = Math.max(2, Math.round((x1 - x0) / (B.h * 1.1)));
  const fg = B.fg, h = B.h;
  switch (B.pat) {
    case 'wave': {   // running spiral ("wave") border
      const p = []; for (let i = 0; i <= n * 8; i++) { const u = i / (n * 8), x = lerp(x0, x1, u), ph = u * n * TAU; p.push([x + Math.sin(ph) * h * .12, yMid + Math.cos(ph) * h * .3 + R.sg(x)]); }
      ln(p, .5, fg, 'inkfine', .5); break;
    }
    case 'meander': {   // a simple key pattern
      const p = [], w = (x1 - x0) / n;
      for (let i = 0; i < n; i++) { const x = x0 + i * w, yb = B.y + h * .22, yt = B.y + h * .78; p.push([x, yb], [x, yt], [x + w * .75, yt], [x + w * .75, yb + h * .28], [x + w * .35, yb + h * .28]); }
      ln(p.map(([x, y]) => [x, y + R.sg(x)]), .45, fg, 'inkfine', 0); break;
    }
    case 'dots': for (let i = 0; i < n; i++) { const x = lerp(x0, x1, (i + .5) / n); shp(ellL(x, yMid + R.sg(x), h * .17, h * .17, 7), fg, { ink: null, j: .2 }); } break;
    case 'tri': for (let i = 0; i < n; i++) { const x = lerp(x0, x1, i / n), w = (x1 - x0) / n; shp([[x, B.y + h * .15 + R.sg(x)], [x + w, B.y + h * .15 + R.sg(x + w)], [x + w / 2, B.y + h * .85 + R.sg(x + w / 2)]], fg, { ink: null, j: .2 }); } break;
    case 'palmette': for (let i = 0; i < n; i++) {
      const x = lerp(x0, x1, (i + .5) / n), y = B.y + h * .2 + R.sg(x);
      shp([[x, y], [x - h * .32, y + h * .45], [x - h * .2, y + h * .62], [x, y + h * .7], [x + h * .2, y + h * .62], [x + h * .32, y + h * .45]], fg, { ink: null, j: .2, curv: .4 });
    } break;
    case 'zig': { const p = []; for (let i = 0; i <= n * 2; i++) { const x = lerp(x0, x1, i / (n * 2)); p.push([x, B.y + h * (i % 2 ? .8 : .2) + R.sg(x)]); } ln(p, .5, fg, 'inkfine', 0); break; }
  }
  // thin ink rules on both edges of the band
  ln(R.pts.slice(0, 11), .3, PAL.ink, 'inkfine', .5); ln(R.pts.slice(11), .3, PAL.ink, 'inkfine', .5);
}

// ---------------------------------------------------------------- views and rest geometry (standing actors)
// Key view for a heading in turns: 0 = front, .125 = 3/4 right, .25 = side right; negative = facing left (flip).
function viewOf(h) { const a = Math.abs(h); return { view: a < .0625 ? 'front' : a < .1875 ? 'q' : 'side', flip: h < -.0001 && a >= .0625 }; }
const ROBE = {   // ankle-length robe, facing right (metres, for a 1.78 m figure)
  front: [[-.06, 1.45], [-.14, 1.425], [-.19, 1.385], [-.205, 1.33], [-.185, 1.2], [-.155, 1.07], [-.172, .9], [-.21, .55], [-.25, .25], [-.285, .07], [-.21, .042], [-.1, .028], [0, .025], [.1, .028], [.21, .042], [.285, .07], [.25, .25], [.21, .55], [.172, .9], [.155, 1.07], [.185, 1.2], [.205, 1.33], [.19, 1.385], [.14, 1.425], [.06, 1.45], [0, 1.43]],
  q:     [[-.045, 1.45], [-.12, 1.425], [-.165, 1.375], [-.17, 1.22], [-.145, 1.07], [-.16, .88], [-.2, .5], [-.248, .08], [-.15, .048], [-.04, .031], [.07, .031], [.17, .045], [.258, .07], [.212, .5], [.168, .88], [.142, 1.07], [.155, 1.25], [.128, 1.37], [.075, 1.435], [.02, 1.42]],
  side:  [[-.03, 1.45], [-.09, 1.42], [-.122, 1.33], [-.112, 1.1], [-.122, .88], [-.152, .5], [-.172, .08], [-.08, .042], [.04, .036], [.15, .05], [.19, .08], [.152, .5], [.122, .88], [.107, 1.06], [.132, 1.25], [.112, 1.37], [.06, 1.43], [.015, 1.42]],
};
const MANTLE = {   // the himation over the left shoulder (screen-right in the front view; the far shoulder facing right)
  front: { pts: [[-.178, .99], [-.06, 1.1], [.06, 1.24], [.15, 1.36], [.198, 1.425], [.226, 1.36], [.232, 1.15], [.24, .9], [.262, .62], [.258, .43], [.2, .5], [.1, .56], [-.02, .62], [-.12, .665], [-.205, .72], [-.205, .88]], edge: [0, 4], lo: [9, 15],
           folds: [[[-.1, 1.03], [.0, .82], [.2, .64]], [[.02, 1.16], [.12, .96], [.232, .84]], [[.12, 1.3], [.18, 1.13], [.234, 1.04]], [[-.17, .9], [-.05, .74], [.1, .6]]] },
  q:     { pts: [[-.152, .99], [-.04, 1.11], [.06, 1.27], [.112, 1.425], [.148, 1.38], [.16, 1.2], [.168, .92], [.2, .62], [.214, .44], [.14, .52], [.02, .6], [-.1, .65], [-.188, .7], [-.17, .86]], edge: [0, 3], lo: [8, 13],
           folds: [[[-.08, 1.04], [.0, .84], [.18, .66]], [[.02, 1.18], [.1, .98], [.165, .86]], [[-.15, .9], [-.04, .76], [.1, .6]]] },
  side:  { pts: [[-.125, .99], [-.03, 1.08], [.06, 1.2], [.118, 1.32], [.128, 1.1], [.13, .88], [.15, .6], [.162, .45], [.08, .55], [-.05, .6], [-.155, .66], [-.13, .84]], edge: [0, 3], lo: [7, 11],
           folds: [[[-.05, 1.04], [.02, .84], [.13, .68]], [[.04, 1.14], [.1, .98], [.128, .9]]] },
};
const SHOULDERS = {   // [x, y, arm, layer]  arm r/l = the actor's right/left; layer 0 behind the robe, 1 in front
  front: [[-.178, 1.36, 'r', 0], [.178, 1.36, 'l', 0]],
  q:     [[-.13, 1.365, 'r', 1], [.1, 1.375, 'l', 0]],
  side:  [[-.01, 1.37, 'r', 1], [.01, 1.38, 'l', 0]],
};
const HEADC = { front: [0, 1.6], q: [.012, 1.6], side: [.03, 1.598] };
const FEET = { front: [[-.075, 0, 'r'], [.075, 0, 'l']], q: [[-.045, 0, 'r'], [.07, .018, 'l']], side: [[-.01, 0, 'r'], [.035, .012, 'l']] };

// ---------------------------------------------------------------- the rig (look-independent)
// slot = { body: 'actor' | 'recliner' | 'stagehand', height }. pose: see the motion tracks in cast/cast.js.
function rigPerson(slot, P) {
  if (slot.body === 'recliner') return rigRecliner(slot, P);
  const sc = (slot.height || 1.78) / 1.78, stage = slot.body === 'stagehand';
  const { view, flip } = viewOf(P.heading ?? 0), hv = viewOf(P.headHeading ?? P.heading ?? 0);
  const lean = P.lean || 0, hip = P.hip || 0, drop = (P.crouch || 0) * .32 + (P.bob || 0), swing = P.swing || 0, pelvisY = .95 * sc;
  // skinning: rest point -> posed point. The upper body leans about the pelvis; the skirt shears toward the feet.
  const piv = [hip, pelvisY - drop];
  const deform = (x, y) => {
    x *= sc; y *= sc;
    const w = smooth01((y - (pelvisY - .1)) / .35), a = -lean * w;
    if (y < pelvisY) { const u = clamp(y / pelvisY); const sx = lerp(swing, hip, u * u * (3 - 2 * u)); x += sx; y -= drop * u; }
    else { x += hip; y -= drop; }
    if (w > 0) { const dx = x - piv[0], dy = y - piv[1], c = Math.cos(a), s = Math.sin(a); x = piv[0] + dx * c - dy * s; y = piv[1] + dx * s + dy * c; }
    return [x, y];
  };
  const R = { slot, P, view, flip, hview: hv.view, hflip: hv.flip, sc, deform, lean, stage };
  // head: on the neck, follows the lean (a little less), plus its own tilt
  const hc = HEADC[view]; R.head = deform(hc[0] + (P.headDx || 0), hc[1] + (P.headDy || 0)); R.headRot = -lean * .6 - (P.headTilt || 0);
  if (stage) { R.head = deform(hc[0] * .6 + (P.headDx || 0), 1.6 + (P.headDy || 0)); }
  // arms (angles absolute, in the facing frame)
  R.arms = {};
  for (const [sx, sy, side, layer] of SHOULDERS[view]) {
    const A = P[side] || {}, sgn = view === 'front' ? (side === 'r' ? -1 : 1) : 1;
    const sh = deform(sx * (stage ? .9 : 1), sy * (stage ? .985 : 1)), ua = (stage ? .3 : .29) * sc, fa = (stage ? .27 : .26) * sc;
    const a = A.a ?? .08, e = A.e ?? .1, w = A.w ?? 0;
    const el = [sh[0] + sgn * Math.sin(a) * ua, sh[1] - Math.cos(a) * ua], b = a + e;
    const wr = [el[0] + sgn * Math.sin(b) * fa, el[1] - Math.cos(b) * fa], hd = b + w;
    const hand = [wr[0] + sgn * Math.sin(hd) * .09 * sc, wr[1] - Math.cos(hd) * .09 * sc];
    R.arms[side] = { sh, el, wr, hand, a, b, hd, sgn, layer, pose: A.h || 'relax', palm: A.palm, stylus: A.stylus };
  }
  // feet: planted points relative to the root (the motion may lift and slide them)
  R.feet = {};
  for (const [fx, fy, side] of FEET[view]) { const F = (P.feet && P.feet[side]) || {}; R.feet[side] = [fx * sc + (F.dx || 0) + (stage ? hip * .3 : 0), fy + (F.dy || 0)]; }
  if (stage) rigLegs(R, P);
  R.anchors = {
    head: R.head, pelvis: piv, hand_r: R.arms.r.hand, hand_l: R.arms.l.hand,
    foot_r: R.feet.r, foot_l: R.feet.l,
  };
  return R;
}
const smooth01 = x => { x = clamp(x); return x * x * (3 - 2 * x); };
// bare legs (stagehands): two-bone IK from the hip to the planted foot
function rigLegs(R, P) {
  const sc = R.sc, hipY = .93 * sc - (P.crouch || 0) * .32 - (P.bob || 0), th = .46 * sc, sh = .44 * sc;
  R.legs = {};
  const hx = { front: { r: -.08, l: .08 }, q: { r: -.06, l: .06 }, side: { r: 0, l: .01 } }[R.view];
  for (const side of ['r', 'l']) {
    const hp = [hx[side] * sc + (P.hip || 0), hipY], ft = [R.feet[side][0], R.feet[side][1] + .055 * sc], dx = ft[0] - hp[0], dy = ft[1] - hp[1], d = Math.min(Math.hypot(dx, dy), th + sh - .001);
    const ang = Math.atan2(dy, dx), cosA = (th * th + d * d - sh * sh) / (2 * th * d), front = R.view === 'front';
    const kneeA = ang + (front ? (side === 'r' ? -1 : 1) * .35 : 1) * Math.acos(clamp(cosA, -1, 1));
    const kn = [hp[0] + Math.cos(kneeA) * th, hp[1] + Math.sin(kneeA) * th];
    if (front) { const m = [lerp(hp[0], ft[0], th / (th + sh)), lerp(hp[1], ft[1], th / (th + sh))]; kn[1] = lerp(m[1], kn[1], .5) - (1 - d / (th + sh)) * .25; }
    R.legs[side] = { hip: hp, knee: kn, ankle: ft };
  }
}
// The reclining figure, as on symposium vases: the torso nearly upright, propped on the left elbow on a pillow at the
// head end (screen-right), the legs along the couch under the mantle, one knee raised. Local origin: the middle of the
// mattress top. Hands are placed by IK targets in this space: P.r = { hand: [x, y], bend, w, h }, P.l likewise.
function ik2(sh, tg, l1, l2, bend) {   // two-bone IK: elbow position for shoulder sh reaching target tg
  const dx = tg[0] - sh[0], dy = tg[1] - sh[1], d = clamp(Math.hypot(dx, dy), .02, l1 + l2 - .002), a = Math.atan2(dy, dx);
  const c = clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1), e = a + bend * Math.acos(c);
  const el = [sh[0] + Math.cos(e) * l1, sh[1] + Math.sin(e) * l1], b = Math.atan2(tg[1] - el[1], tg[0] - el[0]);
  return { el, wr: [el[0] + Math.cos(b) * l2, el[1] + Math.sin(b) * l2], b };
}
function rigRecliner(slot, P) {
  const sc = (slot.height || 1.74) / 1.78, hv = viewOf(P.headHeading ?? 0);
  const pel = [-.02 + (P.hip || 0), .1], tor = -.3 + (P.lean || 0);   // torso angle from vertical (- = toward the head end)
  const rot = (x, y) => { const c = Math.cos(tor), s = Math.sin(tor); return [pel[0] + x * c - y * s, pel[1] + x * s + y * c]; };
  const R = { slot, P, view: 'front', flip: false, hview: hv.view, hflip: hv.flip, sc, recl: true, pel, tor, rot };
  R.neck = rot(0, .5 * sc);
  R.head = [R.neck[0] + .01 + (P.headDx || 0), R.neck[1] + .14 * sc + (P.headDy || 0)];
  R.headRot = tor * .25 - (P.headTilt || 0);
  R.arms = {};
  const ua = .29 * sc, fa = .26 * sc;
  for (const side of ['l', 'r']) {
    const A = P[side] || {}, sh = rot((side === 'l' ? .18 : -.18) * sc, .42 * sc);
    const tg = A.hand || (side === 'l' ? [.22, .3] : [.17, .33]);
    const k = ik2(sh, tg, ua, fa, A.bend ?? (side === 'l' ? 1 : -1)), hd = k.b + (A.w || 0);
    R.arms[side] = { sh, el: k.el, wr: k.wr, hand: [k.wr[0] + Math.cos(hd) * .1, k.wr[1] + Math.sin(hd) * .1], hdAng: hd, pose: A.h || (side === 'l' ? 'hold' : 'hold'), stylus: A.stylus, layer: 1, flipHand: A.flipHand };
  }
  R.knee = [-.42 + (P.kneeDx || 0), .4 + (P.kneeUp || 0)];
  R.tablet = P.tablet !== false ? [R.arms.l.wr[0] + Math.cos(R.arms.l.hdAng) * .08, R.arms.l.wr[1] + Math.sin(R.arms.l.hdAng) * .08 + .035] : null;
  R.anchors = { head: R.head, pelvis: pel, hand_r: R.arms.r.hand, hand_l: R.arms.l.hand, foot_r: [-.98, .1], foot_l: [-.66, .04] };
  return R;
}
// ---------------------------------------------------------------- the painters (look-dependent)
// paintPerson(R, look, env, sx, sy, k): R from rigPerson, (sx, sy) = the root on screen, k = px per metre.
// env = { shade, key }: shade sinks the colours into the dark of the skene; key seeds the boil (stable per slot).
function paintPerson(R, look, env, sx, sy, k) {
  ENV = { shade: env.shade || 0, warm: env.warm || 0 };
  const key = env.key || 'p', rs = part => boilSeed(key + ' ' + part);
  xfBegin(sx, sy, k, R.flip);
  if (R.recl) paintRecliner(R, look, rs);
  else if (R.stage) paintStagehand(R, look, rs);
  else paintActor(R, look, rs);
  rs('after');
  ENV = { shade: 0, warm: 0 };
}
// head, placed on the rig, mirrored when it looks the other way from the body
function paintHeadAt(R, look, rs, part) {
  rs('head ' + part);
  xfPush(); xfT(R.head[0], R.head[1]); xfR(R.headRot || 0);
  if (R.hflip !== R.flip) xfS(-1, 1);
  xfS(R.stage ? 1.12 : 1.12);
  if (look.mask) paintMask(R.hview, look.mask, { part }); else if (part !== 'back') paintBareHead(R.hview, look.head, { down: R.P.headDown });
  xfPop();
}
// a sleeved (or bare) arm: hand first, then the sleeve over the wrist, then a cuff band
function paintArm(R, A, look, rs, side, dark = 0) {
  rs('arm ' + side);
  const sleeve = look.robe && look.robe.sleeve !== false, sc = R.sc, hw = look.handScale || 1.25;
  const robeCol = dark ? mixCol(look.robe ? look.robe.col : look.tunic.col, PAL.ink, .22) : (look.robe ? look.robe.col : look.tunic.col);
  const skin = dark ? mixCol(look.skin, PAL.ink, .18) : look.skin;
  // the hand at the wrist, along the forearm
  const dir = R.recl ? A.hdAng : Math.atan2(-Math.cos(A.hd), A.sgn * Math.sin(A.hd));
  xfPush(); xfT(A.wr[0], A.wr[1]); xfR(dir); xfS(sc * hw);
  const mirror = R.recl ? !!A.flipHand : (R.view === 'front' ? A.sgn > 0 : !!A.palm);
  if (mirror) xfS(1, -1);
  paintHand(A.pose, skin, look.skinDk, { stylus: A.stylus });
  xfPop();
  // the sleeve (or a bare arm), shoulder -> elbow -> wrist
  const path = [A.sh, [lerp(A.sh[0], A.el[0], .55), lerp(A.sh[1], A.el[1], .55)], A.el, A.wr];
  if (sleeve) {
    const w0 = .118 * sc, w1 = .098 * sc;
    shp(limbL(path, w0, w1, 4), robeCol, { sw: .9 });
    const cuff = [[lerp(A.el[0], A.wr[0], .72), lerp(A.el[1], A.wr[1], .72)], A.wr];
    shp(ribbonL(cuff, w1 * 1.02, w1 * 1.02, 2), dark ? mixCol(look.robe.cuff, PAL.ink, .2) : look.robe.cuff, { sw: .55 });
    const m = [lerp(cuff[0][0], cuff[1][0], .5), lerp(cuff[0][1], cuff[1][1], .5)];
    ln(ribbonL([cuff[0], cuff[1]], w1 * .45, w1 * .45, 2).slice(0, 3), .3, look.robe.cuffFg || PAL.ink, 'inkfine', .3);
    // a fold at the elbow
    ln([[lerp(A.sh[0], A.el[0], .8), lerp(A.sh[1], A.el[1], .8)], [A.el[0], A.el[1]]], .35, PAL.ink, 'inkfine', .5);
  } else {
    shp(limbL(path, .1 * sc, .072 * sc, 4), skin, { sw: .8 });
    ln([[lerp(A.sh[0], A.el[0], .7), lerp(A.sh[1], A.el[1], .7) - .01], [A.el[0], A.el[1] - .01]], .3, look.skinDk, 'inkfine', .5);
  }
}
function paintBoot(x, y, view, col, dk, sc, back = false) {
  const P = view === 'front' ? [[-.036, 0], [.036, 0], [.042, .03], [.034, .1], [-.034, .1], [-.042, .03]]
          : view === 'q' ? [[-.04, .0], [.075, .0], [.085, .025], [.04, .05], [.02, .1], [-.04, .1], [-.05, .04]]
          : [[-.05, .0], [.1, .0], [.11, .025], [.05, .052], [.025, .1], [-.04, .1], [-.055, .04]];
  shp(cloop(P.map(([a, b]) => [x + a * sc, y + b * sc]), 2), back ? mixCol(col, PAL.ink, .2) : col, { sw: .7 });
  ln([[x - .02 * sc, y + .05 * sc], [x + .02 * sc, y + .07 * sc]], .3, dk, 'inkfine', .3);
}

function paintActor(R, look, rs) {
  const v = R.view, sc = R.sc, D = R.deform, robe = look.robe, mant = look.mantle;
  const def = pts => pts.map(([x, y]) => D(x, y));
  rs('shadow'); tone(ellL(0, .0, .34 * sc, .05 * sc, 16), '#2a1d1a', 70);
  // far arm and back hair behind everything
  for (const s of ['r', 'l']) if (R.arms[s].layer === 0) paintArm(R, R.arms[s], look, rs, s, 1);
  paintHeadAt(R, look, rs, 'back');
  // boots under the hem
  rs('boots');
  const fe = Object.entries(R.feet).sort((a, b) => b[1][1] - a[1][1]);
  for (const [s, [fx, fy]] of fe) paintBoot(fx, fy, v, look.boots, PAL.ink, sc, fy > .005);
  // the robe: one shape, then its bands, belt, and the shadow side
  rs('robe');
  const out = cloop(ROBE[v], 3), outP = def(out);
  shp(outP, robe.col, { sw: 1.05 });
  const sag = v === 'side' ? .004 : .014, cx = v === 'q' ? .03 : 0;
  robe.bands.forEach((B, i) => {
    rs('band' + i);
    const Rb = bandPts(out, B.y, B.y + B.h, sag, cx); if (!Rb) return;
    xfPush(); paintBandDeformed(out, B, sag, cx, D); xfPop();
  });
  rs('belt'); const bR = bandPts(out, 1.025, 1.065, sag * .6, cx); if (bR) shp(def(bR.pts), robe.belt, { sw: .5 });
  rs('robeshade');
  const shadeW = v === 'side' ? .06 : .085, sh = [];
  for (let y = 1.36; y >= .1; y -= .09) { const r = xAt(out, y); if (r) sh.push([r[0] + .004, y]); }
  for (let y = .1; y <= 1.36; y += .09) { const r = xAt(out, y); if (r) sh.push([r[0] + shadeW * (y < 1 ? 1.1 : .8) + .02 * Math.sin(y * 9), y]); }
  tone(def(clampIn(out, cloop(sh, 2), .004)), robe.dk, 95);
  for (const fx of [.05, -.04]) tone(def(clampIn(out, ribbonL([[fx, .92], [fx * 1.3, .5], [fx * 1.6, .12]], .012, .03, 3))), robe.dk, 60);
  // the mantle over the left shoulder, with a border and folds
  if (mant) {
    rs('mantle');
    const M = MANTLE[v], mp = cloop(M.pts, 3);
    shp(def(mp), mant.col, { sw: 1 });
    const lo = M.pts.slice(M.lo[0], M.lo[1] + 1), mo = cloop(M.pts, 3);
    tone(def(clampIn(mo, cloop([...lo.map(([x, y]) => [x, y + .012]), ...lo.slice().reverse().map(([x, y]) => [x, y + .14])], 2), .008)), mant.dk, 85);
    M.folds.forEach((f, i) => { tone(def(clampIn(mo, ribbonL(f.map(([x, y]) => [x, y - .012]), .012, .026, 3), .01)), mant.dk, 70); ln(def(f), .5, PAL.ink, 'inkfine', .6); });
    const e0 = M.pts[M.edge[0]], e1 = M.pts[M.edge[1]];
    shp(def(ribbonL([e0, [lerp(e0[0], e1[0], .5) + .008, lerp(e0[1], e1[1], .5) - .008], e1], .03, .03, 3)), mant.border, { sw: .45 });
    shp(def(ribbonL(lo.map(([x, y]) => [x, y + .018]), .026, .026, 3)), mant.border, { ink: null });
  }
  for (const s of ['r', 'l']) if (R.arms[s].layer === 1) paintArm(R, R.arms[s], look, rs, s, 0);
  paintHeadAt(R, look, rs, 'front');
}
// bands drawn through the skinning deform, so they lean and sway with the robe
function paintBandDeformed(out, B, sag, cx, D) {
  const R = bandPts(out, B.y, B.y + B.h, sag, cx); if (!R) return;
  shp(R.pts.map(([x, y]) => D(x, y)), B.col, { ink: null, j: .4 });
  const yMid = B.y + B.h / 2, x0 = Math.max(R.a[0], R.b[0]) + .012, x1 = Math.min(R.a[1], R.b[1]) - .012, h = B.h, n = Math.max(2, Math.round((x1 - x0) / (B.h * 1.1)));
  const d = pts => pts.map(([x, y]) => D(x, y)), fg = B.fg;
  switch (B.pat) {
    case 'wave': { const p = []; for (let i = 0; i <= n * 8; i++) { const u = i / (n * 8), x = lerp(x0, x1, u), ph = u * n * TAU; p.push([x + Math.sin(ph) * h * .14, yMid + Math.cos(ph) * h * .28 + R.sg(x)]); } ln(d(p), .5, fg, 'inkfine', .5); break; }
    case 'meander': { const p = [], w = (x1 - x0) / n; for (let i = 0; i < n; i++) { const x = x0 + i * w, yb = B.y + h * .22, yt = B.y + h * .78; p.push([x, yb], [x, yt], [x + w * .75, yt], [x + w * .75, yb + h * .28], [x + w * .38, yb + h * .28]); } ln(d(p.map(([x, y]) => [x, y + R.sg(x)])), .45, fg, 'inkfine', 0); break; }
    case 'dots': for (let i = 0; i < n; i++) { const x = lerp(x0, x1, (i + .5) / n); shp(d(ellL(x, yMid + R.sg(x), h * .17, h * .17, 7)), fg, { ink: null, j: .2 }); } break;
    case 'tri': for (let i = 0; i < n; i++) { const w = (x1 - x0) / n, x = x0 + i * w; shp(d([[x, B.y + h * .15 + R.sg(x)], [x + w, B.y + h * .15 + R.sg(x + w)], [x + w / 2, B.y + h * .85 + R.sg(x + w / 2)]]), fg, { ink: null, j: .2 }); } break;
    case 'palmette': for (let i = 0; i < n; i++) { const x = lerp(x0, x1, (i + .5) / n), y = B.y + h * .18 + R.sg(x); shp(d([[x, y], [x - h * .34, y + h * .42], [x - h * .22, y + h * .64], [x, y + h * .72], [x + h * .22, y + h * .64], [x + h * .34, y + h * .42]]), fg, { ink: null, j: .2, curv: .4 }); } break;
    case 'zig': { const p = []; for (let i = 0; i <= n * 2; i++) { const x = lerp(x0, x1, i / (n * 2)); p.push([x, B.y + h * (i % 2 ? .8 : .2) + R.sg(x)]); } ln(d(p), .5, fg, 'inkfine', 0); break; }
  }
  ln(d(R.pts.slice(0, 11)), .3, PAL.ink, 'inkfine', .5); ln(d(R.pts.slice(11)), .3, PAL.ink, 'inkfine', .5);
}

function paintStagehand(R, look, rs) {
  const v = R.view, sc = R.sc, D = R.deform, T_ = look.tunic, P = R.P, w = v === 'front' ? 1 : v === 'q' ? .86 : .68;
  rs('shadow'); tone(ellL(0, .0, .3 * sc, .045 * sc, 16), '#2a1d1a', 70);
  for (const s of ['r', 'l']) if (R.arms[s].layer === 0) paintArm(R, R.arms[s], look, rs, s, 1);
  // legs (far first): a thigh-to-shin limb with a calf, and a bare foot
  rs('legs');
  for (const s of (v === 'front' ? ['r', 'l'] : ['l', 'r'])) {
    const G = R.legs[s], far = v !== 'front' && s === 'l', skin = far ? mixCol(look.skin, PAL.ink, .16) : look.skin;
    const calf = [lerp(G.knee[0], G.ankle[0], .3) + (v === 'front' ? 0 : -.012), lerp(G.knee[1], G.ankle[1], .3)];
    shp(limbL([G.hip, G.knee, calf, G.ankle], .145 * sc, .07 * sc, 3), skin, { sw: .8 });
    ln([[G.knee[0] + .02, G.knee[1] + .01], [G.knee[0] + .03, G.knee[1] - .03]], .3, look.skinDk, 'inkfine', .5);
    const ft = R.feet[s], toe = v === 'front' ? 0 : .12 * sc;
    shp(cloop(v === 'front' ? [[ft[0] - .038, ft[1]], [ft[0] + .038, ft[1]], [ft[0] + .034, ft[1] + .05], [ft[0] - .034, ft[1] + .05]] : [[ft[0] - .05, ft[1]], [ft[0] + toe, ft[1]], [ft[0] + toe + .012, ft[1] + .025], [ft[0] + .04, ft[1] + .045], [ft[0] - .015, ft[1] + .07], [ft[0] - .055, ft[1] + .03]], 2), skin, { sw: .7 });
  }
  // neck
  rs('neck'); const nb = D(0, 1.36), hb = [R.head[0], R.head[1] - .07];
  shp(limbL([nb, hb], .085 * sc, .075 * sc, 2), mixCol(look.skin, PAL.ink, .08), { sw: .7 });
  // the tunic (exomis): one strap over the left shoulder, the right shoulder and chest bare; belted; hem at mid-thigh
  rs('tunic');
  const kR = R.legs.r.knee, kL = R.legs.l.knee, hemAt = (G, k) => [lerp(G.hip[0], k[0], .8), lerp(G.hip[1], k[1], .8)];
  const hr = hemAt(R.legs.r, kR), hl = hemAt(R.legs.l, kL);
  const lo = [Math.min(hr[0], hl[0]) - .09 * w, Math.min(hr[1], hl[1]) - .01], hi = [Math.max(hr[0], hl[0]) + .09 * w, Math.min(hr[1], hl[1]) - .01];
  if (v === 'front') { rs('chest'); shp(cloop([D(-.17, 1.34), D(-.1, 1.39), D(.0, 1.37), D(.02, 1.22), D(-.16, 1.2)], 2), look.skin, { sw: .7 }); }
  const tun = v === 'front'
    ? [D(.0, 1.36), D(.1, 1.42), D(.17, 1.39), D(.18, 1.3), D(.155, 1.12), D(.14, .99), [hi[0], hi[1]], [lerp(lo[0], hi[0], .5), lo[1] - .025], [lo[0], lo[1]], D(-.14, .99), D(-.15, 1.12), D(-.16, 1.21)]
    : [D(-.04 * w, 1.39), D(-.15 * w, 1.33), D(-.15 * w, 1.13), D(-.13 * w, .99), [lo[0], lo[1]], [lerp(lo[0], hi[0], .5), lo[1] - .02], [hi[0], hi[1]], D(.13 * w, .99), D(.15 * w, 1.14), D(.16 * w, 1.33), D(.08 * w, 1.41)];
  const tO = cloop(tun, 3);
  shp(tO, T_.col, { sw: 1 });
  tone(clampIn(tO, cloop([D(-.16 * w, 1.2), D(-.1 * w, 1.15), D(-.07 * w, .98), [lerp(lo[0], hi[0], .3), lo[1] + .02], [lo[0] + .01, lo[1] + .02], D(-.14 * w, .99)], 2), .006), T_.dk, 90);
  for (const f of [.3, .62]) ln([D(lerp(-.1, .1, f) * w, .97), [lerp(lo[0], hi[0], f), lo[1] + .01]], .4, PAL.ink, 'inkfine', .5);
  rs('belt'); shp(ribbonL([D(-.15 * w, .99), D(0, .975), D(.15 * w, .99)], .03, .03, 3), T_.belt, { sw: .45 });
  for (const s of ['r', 'l']) if (R.arms[s].layer === 1) paintArm(R, R.arms[s], look, rs, s, 0);
  paintHeadAt(R, look, rs, 'front');
}
function paintRecliner(R, look, rs) {
  const sc = R.sc, robe = look.robe, mant = look.mantle, kn = R.knee;
  rs('shadow'); tone(ellL(-.3, .0, .72, .035, 16), '#2a1d1a', 50);
  paintHeadAt(R, look, rs, 'back');
  // the left (pillow) arm's upper part, beside the torso
  rs('armL up'); const AL = R.arms.l;
  shp(limbL([AL.sh, [lerp(AL.sh[0], AL.el[0], .5), lerp(AL.sh[1], AL.el[1], .5)], AL.el], .118 * sc, .105 * sc, 3), mixCol(robe.col, PAL.ink, .12), { sw: .9 });
  // boots: the extended foot at the foot end, the raised knee's foot flat on the mattress
  rs('boots');
  xfPush(); xfT(-.98, .02); xfR(-.25); xfS(-1, 1); paintBoot(0, 0, 'side', look.boots, PAL.ink, sc * 1.05); xfPop();
  // torso: the robe's upper body, leaning back toward the pillow
  rs('torso');
  xfPush(); xfT(R.pel[0], R.pel[1]); xfR(R.tor); xfT(0, -.95 * sc);
  const T = cloop(ROBE.front.filter(p => p[1] > .8).concat([[.17, .82], [0, .8], [-.17, .82]]), 3).map(([x, y]) => [x * sc, y * sc]);
  shp(T, robe.col, { sw: 1 });
  const Tn = T.map(([x, y]) => [x / sc, y / sc]);
  robe.bands.filter(B => B.y > .95).forEach((B, i) => { rs('tband' + i); paintBandDeformed(Tn, B, .012, 0, (x, y) => [x * sc, y * sc]); });
  tone(clampIn(T, cloop([[-.2, 1.34], [-.13, 1.28], [-.1, .95], [-.12, .84], [-.19, .9], [-.19, 1.2]].map(([x, y]) => [x * sc, y * sc]), 3), .004), robe.dk, 90);
  xfPop();
  // the mantle: wrapped at the waist, over the raised knee and down the couch, hanging over the mattress edge
  rs('mantle');
  const drape = [[.16, .04], [.17, .22], [.08, .3], [-.06, .3], [-.2, .34], [kn[0] + .08, kn[1] + .02], [kn[0] - .01, kn[1] + .05], [kn[0] - .1, kn[1] - .02], [-.62, .2], [-.8, .17], [-.95, .15], [-1.0, .06], [-.97, -.05], [-.72, -.08], [-.45, -.06], [-.2, -.08], [.05, -.06]];
  shp(cloop(drape, 3), mant.col, { sw: 1 });
  const dO = cloop(drape, 3);
  tone(clampIn(dO, cloop([[-.98, .04], [-.95, -.04], [-.7, -.06], [-.45, -.045], [-.2, -.06], [.05, -.045], [.08, .02], [-.2, .03], [-.6, .05], [-.9, .07]], 3), .01), mant.dk, 100);
  tone(clampIn(dO, cloop([[kn[0] - .1, kn[1] - .02], [kn[0] - .02, kn[1] - .01], [kn[0] - .06, .1], [-.62, .05], [-.62, .18]], 3), .01), mant.dk, 80);
  shp(ribbonL([[-.98, -.03], [-.72, -.058], [-.45, -.04], [-.2, -.058], [.06, -.04]], .03, .03, 4), mant.border, { sw: .45 });
  shp(ribbonL([[.17, .2], [.08, .28], [-.06, .28], [-.2, .32]], .028, .028, 3), mant.border, { sw: .45 });
  for (const f of [[[kn[0] - .02, kn[1] + .02], [kn[0] + .02, .2], [-.3, -.04]], [[kn[0] - .06, kn[1]], [-.6, .1], [-.66, -.05]], [[.1, .26], [.0, .12], [-.08, -.05]], [[-.8, .16], [-.84, .05], [-.82, -.05]]]) ln(f, .5, PAL.ink, 'inkfine', .6);
  // the wax tablet in the left hand, in front of the belly
  rs('tablet');
  if (R.tablet) {
    xfPush(); xfT(R.tablet[0], R.tablet[1]); xfR(R.P.tabletRot ?? .32);
    shp([[-.135, -.09], [.135, -.09], [.135, .09], [-.135, .09]], '#946945', { sw: .75 });
    shp([[-.115, -.072], [.115, -.072], [.115, .072], [-.115, .072]], '#3a2b27', { ink: null, j: .3 });
    for (let i = 0; i < 4; i++) ln([[-.095, .05 - i * .03], [.09 - .03 * (i % 2), .05 - i * .03]], .5, '#C9A67A', 'inkfine', .2);
    xfPop();
  }
  paintArm(R, { ...AL, sh: [lerp(AL.sh[0], AL.el[0], .6), lerp(AL.sh[1], AL.el[1], .6)] }, look, rs, 'l', 0);
  paintHeadAt(R, look, rs, 'front');
  paintArm(R, R.arms.r, look, rs, 'r', 0);
}
