// The 2D layer over the model (layer "all" only): identity label, left-third readouts (one per projected
// layer), the door's dimension lines, the roll's measured line, the evidence pins and their legend.
// Grammar after lemo-opuscar's white-model overlay (readout / pin / range line), written for this film.
// Everything is a function of t; anything that sits on the model goes through project(world) -> screen.
// Every text that must be read is registered (window.TEXTS) for the reading-time check.
import { clamp, lerp, smoothstep } from './util.js';
import { F, env, seg, eo, OFFSET } from './film.js';
import { GEO, rollDistance, platformZ } from './timeline.js';
import { PAL } from './lighting.js';

const W0 = 1920, H0 = 1080;
const FONT = { it2: '200 {}px IT', it4: '400 {}px IT', pm: '400 {}px PM', pm5: '500 {}px PM', in4: '400 {}px Inter', in5: '500 {}px Inter', in6: '600 {}px Inter', gd: '400 {}px Didot', gdi: 'italic 400 {}px Didot' };
const font = (k, px) => FONT[k].replace('{}', px);
const EVID = PAL.evid, MEAS = PAL.meas;
const EVID_LIGHT = '#ffd9a6';

export function makeOverlay(canvas, W, H) {
  canvas.width = W; canvas.height = H;
  const g = canvas.getContext('2d');
  const k = W / W0;
  let TX = [];
  const begin = () => { g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, W, H); g.setTransform(k, 0, 0, k, 0, 0); TX = []; };
  function txt(id, s, x, y, f, px, col, a = 1, o = {}) {
    if (a <= 0.001) return 0;
    g.save(); g.globalAlpha = a; g.font = font(f, px); g.fillStyle = col; g.textBaseline = 'alphabetic';
    g.letterSpacing = (o.ls || 0) + 'px';
    if (o.shadow) { g.shadowColor = 'rgba(0,0,0,.65)'; g.shadowBlur = o.shadow; }
    const w = g.measureText(s).width, xx = o.right ? x - w : o.center ? x - w / 2 : x;
    g.fillText(s, xx, y); g.restore();
    if (id && a > 0.98) TX.push({ id, text: s, x0: xx * k, y0: (y - px * 0.9) * k, x1: (xx + w) * k, y1: (y + px * 0.25) * k });
    return w;
  }
  const width = (s, f, px, ls = 0) => { g.save(); g.font = font(f, px); g.letterSpacing = ls + 'px'; const w = g.measureText(s).width; g.restore(); return w; };
  // a run of differently set pieces on one line: [[text, font, px, colour], ...]
  function runs(id, parts, x, y, a, o = {}) {
    if (a <= 0.001) return 0;
    let xx = x;
    for (const [s, f, px, col] of parts) xx += txt(null, s, xx, y, f, px, col, a, o);
    if (id && a > 0.98) TX.push({ id, text: parts.map((p) => p[0]).join(''), x0: x * k, y0: (y - 26) * k, x1: xx * k, y1: (y + 8) * k });
    return xx - x;
  }
  const line = (pts, col, w, a, dash) => {
    if (a <= 0 || pts.length < 2) return;
    g.save(); g.globalAlpha = a; g.lineCap = 'round'; g.lineJoin = 'round';
    if (dash) g.setLineDash(dash);
    g.strokeStyle = 'rgba(0,0,0,.45)'; g.lineWidth = w + 3; g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
    g.strokeStyle = col; g.lineWidth = w; g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
    g.restore();
  };
  const dot = (p, r, col, a) => { if (a <= 0) return; g.save(); g.globalAlpha = a; g.fillStyle = col; g.beginPath(); g.arc(p[0], p[1], r, 0, 7); g.fill(); g.restore(); };
  const plate = (x, y, w, h, a) => { if (a <= 0) return; g.save(); g.globalAlpha = a * 0.66; g.fillStyle = '#05070b'; g.fillRect(x, y, w, h); g.restore(); };

  // soft dark field behind the readouts in the left third
  function scrim(a) {
    if (a <= 0) return;
    const gr = g.createRadialGradient(330, 610, 40, 330, 610, 660);
    gr.addColorStop(0, `rgba(4,5,8,${0.62 * a})`); gr.addColorStop(0.55, `rgba(4,5,8,${0.36 * a})`); gr.addColorStop(1, 'rgba(4,5,8,0)');
    g.fillStyle = gr; g.fillRect(0, 0, W0, H0);
  }

  // readout: index + layer name, one figure (+ unit), one label, one source line, an optional legend
  function readout(t, t0, t1, o) {
    const a = env(t, t0, t1); if (a <= 0) return;
    const kk = eo(seg(t, t0, t0 + 0.5)), dy = (1 - kk) * 22, X = 96, Y = 590 + dy;
    g.save(); g.globalAlpha = a; g.fillStyle = o.col; g.fillRect(X, Y - 124, 46 * kk + 2, 2); g.restore();
    txt(o.id + 'i', o.idx, X, Y - 138, 'pm', 20, 'rgba(235,238,242,.72)', a, { ls: 2 });
    txt(o.id + 'n', o.name, X + 50, Y - 138, 'in6', 21, '#eef1f4', a, { ls: 3 });
    if (o.big) {
      const w = txt(o.bigId === null ? null : o.id + 'b', o.big, X - 6, Y + 4, 'it2', 124, '#ffffff', a, { shadow: 18 });
      if (o.unit) txt(o.bigId === null ? null : o.id + 'u', o.unit, X + w + 10, Y + 4, 'it2', 58, '#ffffff', a, { shadow: 12 });
    }
    if (o.label) txt(o.id + 'l', o.label, X, Y + 56, 'in5', 30, '#f4f5f6', a, { shadow: 10 });
    if (o.note) txt(o.id + 's', o.note, X, Y + 94, 'in4', 21, 'rgba(225,230,236,.8)', a, { ls: 0.5 });
    if (o.legend) o.legend(X, Y + 124, a);
  }

  // the evidence chip: [A] solid, [I] lighter, [R1] dashed outline (shared/STYLE.md evidence code)
  function chip(code, x, y, a) {
    const w = code.length > 1 ? 44 : 30, h = 26;
    g.save(); g.globalAlpha = a;
    if (code === 'A') { g.fillStyle = EVID; g.fillRect(x, y - h + 6, w, h); }
    else if (code === 'I') { g.fillStyle = EVID_LIGHT; g.globalAlpha = a * 0.85; g.fillRect(x, y - h + 6, w, h); }
    else { g.strokeStyle = EVID; g.lineWidth = 2; g.setLineDash([5, 3.5]); g.strokeRect(x + 1, y - h + 7, w - 2, h - 2); }
    g.restore();
    txt(null, code, x + w / 2, y - 1, 'pm5', 17, code === 'R1' ? EVID : '#141008', a, { center: true });
    return w;
  }

  // pin: a hairline from a point on the model to a tag on a dark plate (chip + title runs + one sub line)
  function pin(t, t0, t1, p, o) {
    const a = env(t, t0, t1, 0.3, 0.3); if (a <= 0 || !p) return;
    const [x, y] = p;
    const L = (o.len || 110) * eo(seg(t, t0, t0 + 0.45)), x2 = x + (o.dx || 0) * eo(seg(t, t0, t0 + 0.45)), y2 = y - L;
    line([[x, y], [x2, y2]], o.col || '#ffffff', 1.6, a);
    dot([x, y], 4.5, o.col || '#ffffff', a);
    const ta = a * seg(t, t0 + 0.15, t0 + 0.4), left = !!o.left;
    const titleW = o.title.reduce((s, [str, f, px]) => s + width(str, f, px), 0);
    const chipW = o.chip ? (o.chip.length > 1 ? 44 : 30) + 12 : 0;
    const w = Math.max(chipW + titleW, o.sub ? width(o.sub, 'in4', 20) : 0);
    const bx = left ? x2 - 12 - w - 10 : x2 + 2, by = y2 - 24;
    plate(bx, by, w + 22, o.sub ? 70 : 40, ta);
    let cx = bx + 11;
    if (o.chip) cx += chip(o.chip, cx, y2 + 7, ta) + 12;
    runs(o.id, o.title, cx, y2 + 8, ta, { shadow: 6 });
    if (o.sub) txt(o.id + 's', o.sub, bx + 11, y2 + 37, 'in4', 20, 'rgba(240,242,245,.9)', ta, { shadow: 6 });
  }

  // a dimension line between two model points: grows A -> B, end ticks, label on a plate when complete
  function dim(t, t0, t1, tOut, A, B, tickA, tickB, label, o = {}) {
    const a = 1 - smoothstep(tOut - 0.35, tOut, t); if (t < t0 || a <= 0 || !A || !B) return;
    const kk = eo(seg(t, t0, t1));
    const P = [A[0] + (B[0] - A[0]) * kk, A[1] + (B[1] - A[1]) * kk];
    line(tickA, MEAS, 1.6, a * seg(t, t0, t0 + 0.12));
    line([A, P], MEAS, 2.4, a);
    dot(P, 4, '#ffffff', a * (1 - seg(t, t1, t1 + 0.2)));
    if (kk >= 1) line(tickB, MEAS, 1.6, a);
    const la = a * seg(t, t1 - 0.1, t1 + 0.2);
    if (la > 0) {
      const mx = (A[0] + B[0]) / 2 + (o.lx || 0), my = (A[1] + B[1]) / 2 + (o.ly || 0);
      const w = width(label, 'pm5', 24);
      const x0 = o.right ? mx - w - 22 : o.left ? mx + 4 : mx - w / 2 - 11;
      plate(x0, my - 26, w + 22, 36, la);
      txt(o.id, label, x0 + 11, my + 1, 'pm5', 24, '#ffffff', la);
    }
  }

  return { g, begin, txt, width, runs, line, dot, plate, scrim, readout, pin, dim, chip, texts: () => TX, k };
}

// ------------------------------------------------------------------ the film's 2D layer
// project(x, y, z) -> [px, py] in the 1920x1080 overlay space, or null behind the camera
export function drawOverlay(O, t, project) {
  const { txt, readout, pin, dim, line, dot, scrim, runs, g } = O;
  O.begin();
  const ts = t - OFFSET;
  // the left-third field: on once the lamp strikes
  scrim(seg(t, F.lamp + 0.1, F.lamp + 0.6));

  // identity, top-left, quiet
  const ia = env(t, F.idIn, 99, 0.6, 0.3);
  txt('id1', 'THEATRE OF DIONYSUS, ATHENS  ·  c. 425 BC', 96, 92, 'in5', 23, '#f2f4f6', ia, { ls: 2, shadow: 10 });
  txt('id2', 'SKENE AND EKKYKLEMA  ·  WHITE MODEL 1:20  ·  OUR RECONSTRUCTION', 96, 124, 'pm', 18, 'rgba(225,230,236,.7)', ia, { ls: 1, shadow: 6 });

  // ---- 01 the door
  readout(t, F.door - 0.15, F.roll[0] - 0.15, {
    id: 'r1', idx: '01', name: 'THE DOOR', big: '2.8 × 3.2', unit: 'm', col: MEAS,
    label: 'Leaves swing inward', note: 'Our reconstruction · R2, R6',
    legend: (X, Y, a) => { g.save(); g.globalAlpha = a; g.fillStyle = MEAS; g.fillRect(X, Y, 64, 6); g.restore(); },
  });
  const hx = 1.4, top = 3.2;
  const wA = project(-hx, 3.86, 0.06), wB = project(hx, 3.86, 0.06);
  const tk = (x, y0, y1, z) => [project(x, y0, z), project(x, y1, z)].filter(Boolean);
  dim(t, F.dimW[0], F.dimW[1], F.roll[0] - 0.1, wA, wB, tk(-hx, 3.66, 3.98, 0.06), tk(hx, 3.66, 3.98, 0.06), '2.8 m', { id: 'dW', ly: -18 });
  const xL = -1.98;
  const hA = project(xL, 0.0, 0.08), hB = project(xL, top, 0.08);
  const tkx = (y) => [project(xL - 0.16, y, 0.08), project(xL + 0.22, y, 0.08)].filter(Boolean);
  dim(t, F.dimH[0], F.dimH[1], F.roll[0] - 0.1, hA, hB, tkx(0.0), tkx(top), '3.2 m', { id: 'dH', right: true, lx: -14, ly: 8 });

  // ---- 02 the roll: counter, travelled line beside the lane (dashed while it is behind the facade)
  const d = rollDistance(ts), frac = d / GEO.ROLL;
  readout(t, F.roll[0] - 0.15, F.evid + 0.05, {
    id: 'r2', idx: '02', name: 'THE ROLL', big: d.toFixed(2), bigId: null, unit: 'm', col: MEAS,
    label: 'Rolled out in 4 seconds', note: 'Front edge ends 1.25 m beyond the façade',
    legend: (X, Y, a) => {
      g.save(); g.globalAlpha = a; g.fillStyle = 'rgba(255,255,255,.22)'; g.fillRect(X, Y + 1, 320, 2);
      g.fillStyle = MEAS; g.fillRect(X, Y, 320 * frac, 4); g.beginPath(); g.arc(X + 320 * frac, Y + 2, 5, 0, 7); g.fill(); g.restore();
      const tr = clamp(ts - 3.0, 0, 4);
      txt(null, `${tr.toFixed(1)} s`, X + 320 * frac - 22, Y + 34, 'pm', 20, '#cfeeff', a);
    },
  });
  {
    const a = seg(t, F.lane + 0.2, F.lane + 0.6) * (1 - smoothstep(F.evid - 0.1, F.evid + 0.4, t));
    if (a > 0) {
      const xr = -1.66, z0 = GEO.PLAT_FRONT_IN, zf = platformZ(ts) + GEO.PLAT_D / 2;
      const pts = (za, zb) => { const n = 24, P = []; for (let i = 0; i <= n; i++) { const p = project(xr, 0.0, za + (zb - za) * i / n); if (p) P.push(p); } return P; };
      line(pts(z0, Math.min(0, zf)), MEAS, 1.6, a * 0.75, [6, 6]);
      if (zf > 0) line(pts(0, zf), MEAS, 2.4, a);
      const s0 = project(xr - 0.12, 0, z0), s1 = project(xr + 0.12, 0, z0);
      if (s0 && s1) line([s0, s1], MEAS, 1.6, a);
      const f0 = project(xr + 0.12, 0, 0), f1 = project(xr - 0.3, 0, 0);
      if (f0 && f1) { line([f0, f1], '#ffffff', 1.6, a); txt('fac', 'façade', f1[0] - 8, f1[1] + 6, 'pm', 18, 'rgba(235,240,245,.85)', a, { shadow: 8, right: true }); }
      const tip = project(xr, 0, zf);
      if (tip) {
        dot(tip, 5, '#ffffff', a);
        if (t > F.roll[0] - 0.2) txt(null, `${d.toFixed(2)} m`, tip[0] - 14, tip[1] + 30, 'pm5', 22, '#ffffff', a, { shadow: 10, right: true });
      }
    }
  }

  // ---- 03 how sure: legend in the readout, one pin per part
  readout(t, F.evid, 99, {
    id: 'r3', idx: '03', name: 'HOW SURE?', col: EVID,
    legend: (X, Y, a) => {
      const rows = [['A', 'Attested', 'an ancient text says so', F.pinA], ['I', 'Inferred', 'scholars deduce it', F.pinI], ['R1', 'Reconstruction', 'our choice, weakly supported', F.pinR]];
      rows.forEach(([c, name, sub, t0], i) => {
        const ra = a * seg(t, t0 - 0.1, t0 + 0.2); if (ra <= 0) return;
        const yy = Y - 150 + i * 66;
        O.chip(c, X, yy, ra);
        txt('lg' + c, name, X + 60, yy, 'in5', 26, '#ffffff', ra, { shadow: 8 });
        txt('lgs' + c, sub, X + 60, yy + 26, 'in4', 19, 'rgba(225,230,236,.8)', ra);
      });
    },
  });
  const pz = platformZ(ts);
  pin(t, F.pinA, 99, project(0.0, 0.0, GEO.PLAT_FRONT_IN + GEO.ROLL + 1.42), {
    id: 'pA', chip: 'A', col: EVID, len: -70, dx: 60,
    title: [['ekkyklein ', 'gdi', 27, '#ffffff'], ['ἐκκυκλεῖν ', 'gd', 27, '#ffffff'], ['“to roll out”', 'in4', 23, '#e9edf2']],
    sub: 'Aristophanes, Acharnians 408 · attested',
  });
  pin(t, F.pinI, 99, project(-1.115, 0.0, pz + 0.55 + 0.22), {
    id: 'pI', chip: 'I', col: EVID_LIGHT, len: -120, dx: -70, left: true,
    title: [['Wheels', 'in5', 25, '#ffffff']], sub: 'inferred from the scholia',
  });
  pin(t, F.pinR, 99, project(-0.95, 0.30, pz + 0.78), {
    id: 'pR', chip: 'R1', col: EVID, len: 430, dx: -24, left: true,
    title: [['2.4 × 1.6 m platform', 'in5', 25, '#ffffff']], sub: 'our reconstruction · R1',
  });
  return O.texts();
}
