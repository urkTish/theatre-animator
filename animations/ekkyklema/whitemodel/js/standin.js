// Built-in stand-in figures, in three styles ("white" added for the white-model film):
//   "white": plaster-white museum maquettes with unpainted masks (stagehands dark, as shared/STYLE.md asks)
//   "clay": smooth matte maquettes with painted theatre masks and draped robes
//   "vase": Athenian red-figure: terracotta bodies, black glaze hair, black contour
//           and drapery lines (flat-shaded 3D with an ink outline)
// The geometry follows the canonical skeleton pose; nothing here changes motion.
import * as THREE from 'three';
import { cone, ell, torus, mesh as sdfMesh, surfaceInfo } from './sdf.js';
import { patchMaterial } from './lighting.js';

const V = THREE.Vector3;
const R = { SKIN: 0, CLOTH: 1, CLOTH2: 2, HAIR: 3, BELT: 4, SHOE: 5 };
const NREG = 6;

// palettes (sRGB hex), per costume and style
const PALETTES = {
  clay: {
    actor: ['#dccdbb', '#ebe4d8', '#c3ad94', '#7a6a5c', '#a8927a', '#a8927a'],
    reclining: ['#dccdbb', '#ebe4d8', '#bfa58a', '#7a6a5c', '#a8927a', '#a8927a'],
    stagehand: ['#9a8572', '#4e4842', '#4e4842', '#3c3632', '#35302c', '#3c3632'],
  },
  // white museum maquettes: one plaster white, the drapery a shade cooler; stagehands near-black so the dark interior hides them
  white: {
    actor: ['#f3f2ef', '#f6f5f2', '#e8e7e3', '#dedcd8', '#d9d7d2', '#dedcd8'],
    reclining: ['#f3f2ef', '#f6f5f2', '#e6e4e0', '#dedcd8', '#d9d7d2', '#dedcd8'],
    stagehand: ['#2b2b2a', '#1f1f1e', '#1f1f1e', '#181817', '#161615', '#181817'],   // dark, "not part of the fiction" (shared/STYLE.md)
  },
  vase: {
    actor: ['#c8743c', '#c8743c', '#c47040', '#17110d', '#17110d', '#c8743c'],
    reclining: ['#c8743c', '#c8743c', '#c47040', '#17110d', '#17110d', '#c8743c'],
    stagehand: ['#b86a3a', '#b86a3a', '#b86a3a', '#17110d', '#17110d', '#b86a3a'],
  },
};

const tmpQ = new THREE.Quaternion();
const up = (q) => new V(0, 1, 0).applyQuaternion(q);
const fwd = (q) => new V(0, 0, 1).applyQuaternion(q);
const lft = (q) => new V(1, 0, 0).applyQuaternion(q);
const along = (J, a, b, t) => new V().lerpVectors(J[a].p, J[b].p, t);

// ------------------------------------------------------------------ anatomy + costume
export function figurePrims(J, costume, s = 1) {
  const P = [];
  const add = (p) => (P.push(p), p);
  const pel = J.pelvis, sp = J.spine, ch = J.chest, nk = J.neck, hd = J.head;
  // torso
  add(ell(new V(0, -0.015 * s, -0.005).applyQuaternion(pel.q).add(pel.p), pel.q, [0.158 * s, 0.115 * s, 0.118 * s], { k: 0.05 }));
  add(cone(pel.p.clone().addScaledVector(up(pel.q), 0.03 * s), ch.p, 0.122 * s, 0.13 * s, { ref: lft(sp.q), sx: 1.18, sz: 0.74, k: 0.06 }));
  add(ell(new V(0, 0.075 * s, -0.004).applyQuaternion(ch.q).add(ch.p), ch.q, [0.165 * s, 0.135 * s, 0.100 * s], { k: 0.05 }));
  add(cone(nk.p.clone().addScaledVector(up(ch.q), -0.03 * s), hd.p, 0.056 * s, 0.05 * s, { k: 0.03 }));
  // head (skull + jaw), turned with the head joint
  const hc = new V(0, 0.105 * s, 0.018 * s).applyQuaternion(hd.q).add(hd.p);
  add(ell(hc, hd.q, [0.088 * s, 0.112 * s, 0.102 * s], { k: 0.03 }));
  add(ell(new V(0, 0.04 * s, 0.055 * s).applyQuaternion(hd.q).add(hd.p), hd.q, [0.06 * s, 0.05 * s, 0.05 * s], { k: 0.03 }));
  // arms
  for (const sd of ['l', 'r']) {
    const sh = J['shoulder_' + sd], el = J['elbow_' + sd], wr = J['wrist_' + sd], hn = J['hand_' + sd];
    add(ell(sh.p.clone().addScaledVector(up(sh.q), -0.02 * s), sh.q, [0.06 * s, 0.07 * s, 0.06 * s], { k: 0.05 }));
    add(cone(sh.p, el.p, 0.05 * s, 0.04 * s, { k: 0.025 }));
    add(cone(el.p, wr.p, 0.04 * s, 0.028 * s, { k: 0.02 }));
    // mitten hand: flattened toward the palm
    const hm = along(J, 'wrist_' + sd, 'hand_' + sd, 0.42);
    add(ell(hm, wr.q, [0.026 * s, 0.07 * s, 0.045 * s].map((v, i) => (i === 2 ? v * 0.55 : v)), { k: 0.02 }));
    add(ell(hm, wr.q, [0.045 * s, 0.06 * s, 0.022 * s], { k: 0.02 }));
  }
  // legs and feet
  for (const sd of ['l', 'r']) {
    const hp = J['hip_' + sd], kn = J['knee_' + sd], an = J['ankle_' + sd], to = J['toe_' + sd];
    add(cone(hp.p, kn.p, 0.084 * s, 0.054 * s, { k: 0.05 }));
    add(cone(kn.p, an.p, 0.052 * s, 0.034 * s, { k: 0.03 }));
    const heel = an.p.clone().addScaledVector(fwd(an.q), -0.03 * s).addScaledVector(up(an.q), -0.045 * s);
    add(cone(heel, to.p, 0.034 * s, 0.026 * s, { ref: lft(an.q), sx: 1.25, sz: 0.62, k: 0.025, reg: costume === 'actor' ? R.SHOE : R.SKIN }));
  }

  const torsoUp = new V().subVectors(ch.p, pel.p).normalize();
  if (costume === 'actor') {
    // long chiton to the ankles, hanging under gravity from the chest
    const top = ch.p.clone().addScaledVector(up(ch.q), 0.09 * s);
    const hem = new V(pel.p.x * 0.8, 0.035 * s, pel.p.z + 0.03 * s);
    add(cone(top, hem, 0.165 * s, 0.255 * s, { ref: lft(pel.q), sx: 1.12, sz: 0.86, k: 0.07, reg: R.CLOTH, folds: { n: 9, amp0: 0.004, amp1: 0.03, phase: 0.7, pow: 1.3, twist: 1.2 } }));
    add(torus(pel.p.clone().addScaledVector(torsoUp, 0.15 * s), torsoUp, 0.15 * s, 0.014 * s, { ref: lft(pel.q), sx: 1.12, sz: 0.84, reg: R.BELT, k: 0.012 }));
    // short sleeves
    for (const sd of ['l', 'r']) add(cone(J['shoulder_' + sd].p, along(J, 'shoulder_' + sd, 'elbow_' + sd, 0.55), 0.072 * s, 0.062 * s, { reg: R.CLOTH, k: 0.03 }));
    // himation: pinned on the left shoulder, a diagonal fold across the chest and a heavy fall down the back
    const ls = J.shoulder_l.p, rh = J.hip_r.p;
    // himation: wrapped round the hips, its end thrown over the left shoulder and falling down the back
    const hipC = pel.p.clone().addScaledVector(up(pel.q), -0.10 * s);
    add(cone(hipC.clone().addScaledVector(up(pel.q), 0.12 * s), new V(pel.p.x * 0.8, 0.17 * s, pel.p.z + 0.02 * s), 0.215 * s, 0.27 * s, { ref: lft(pel.q), sx: 1.12, sz: 0.9, reg: R.CLOTH2, k: 0.015, folds: { n: 7, amp0: 0.005, amp1: 0.016, phase: 2.4, pow: 1.0, twist: 0.6 } }));
    add(cone(ls.clone().addScaledVector(fwd(ch.q), 0.07 * s).addScaledVector(up(ch.q), 0.02 * s), hipC.clone().addScaledVector(lft(pel.q), -0.12 * s).addScaledVector(fwd(pel.q), 0.17 * s).addScaledVector(up(pel.q), 0.12 * s), 0.06 * s, 0.07 * s, { ref: fwd(ch.q), sx: 0.6, sz: 1.0, reg: R.CLOTH2, k: 0.02, folds: { n: 5, amp0: 0.006, amp1: 0.012, phase: 1.3 } }));
    add(cone(ls.clone().addScaledVector(fwd(ch.q), -0.08 * s).addScaledVector(up(ch.q), 0.02 * s), new V(ls.x * 0.85, 0.42 * s, ls.z - 0.16 * s), 0.075 * s, 0.15 * s, { ref: lft(ch.q), sx: 1.0, sz: 0.5, reg: R.CLOTH2, k: 0.02, folds: { n: 6, amp0: 0.004, amp1: 0.02, phase: 2.1 } }));
  } else if (costume === 'stagehand') {
    // a plain short tunic (exomis-like), belted, to mid thigh
    const top = ch.p.clone().addScaledVector(up(ch.q), 0.10 * s);
    const hem = pel.p.clone().addScaledVector(up(pel.q), -0.30 * s);
    add(cone(top, hem, 0.16 * s, 0.215 * s, { ref: lft(pel.q), sx: 1.14, sz: 0.88, k: 0.06, reg: R.CLOTH, folds: { n: 7, amp0: 0.003, amp1: 0.014, phase: 0.2 } }));
    add(torus(pel.p.clone().addScaledVector(torsoUp, 0.13 * s), torsoUp, 0.148 * s, 0.013 * s, { ref: lft(pel.q), sx: 1.12, sz: 0.84, reg: R.BELT, k: 0.01 }));
    for (const sd of ['l', 'r']) add(cone(J['shoulder_' + sd].p, along(J, 'shoulder_' + sd, 'elbow_' + sd, 0.35), 0.066 * s, 0.06 * s, { reg: R.CLOTH, k: 0.03 }));
    // short cropped hair
    add(ell(hc.clone().addScaledVector(up(hd.q), 0.018 * s).addScaledVector(fwd(hd.q), -0.012 * s), hd.q, [0.092 * s, 0.10 * s, 0.098 * s], { reg: R.HAIR, k: 0.01 }));
  } else if (costume === 'reclining') {
    // chiton over the torso, then a himation over the hips and legs
    const top = ch.p.clone().addScaledVector(up(ch.q), 0.09 * s);
    const hem = pel.p.clone().addScaledVector(up(pel.q), -0.12 * s);
    add(cone(top, hem, 0.165 * s, 0.19 * s, { ref: lft(pel.q), sx: 1.1, sz: 0.88, k: 0.06, reg: R.CLOTH, folds: { n: 8, amp0: 0.003, amp1: 0.01, phase: 0.9 } }));
    for (const sd of ['l', 'r']) add(cone(J['shoulder_' + sd].p, along(J, 'shoulder_' + sd, 'elbow_' + sd, 0.5), 0.07 * s, 0.062 * s, { reg: R.CLOTH, k: 0.03 }));
    const drapeK = 0.13;
    add(ell(pel.p.clone().addScaledVector(up(pel.q), -0.03 * s), pel.q, [0.19 * s, 0.15 * s, 0.15 * s], { reg: R.CLOTH2, k: drapeK }));
    for (const sd of ['l', 'r']) {
      add(cone(J['hip_' + sd].p, J['knee_' + sd].p, 0.115 * s, 0.085 * s, { reg: R.CLOTH2, k: drapeK, folds: { n: 6, amp0: 0.006, amp1: 0.012, phase: sd === 'l' ? 0.3 : 1.7, twist: 4 } }));
      add(cone(J['knee_' + sd].p, along(J, 'knee_' + sd, 'ankle_' + sd, 0.82), 0.085 * s, 0.072 * s, { reg: R.CLOTH2, k: drapeK, folds: { n: 6, amp0: 0.006, amp1: 0.01, phase: sd === 'l' ? 2.3 : 0.9, twist: 3 } }));
    }
    // the cloth sagging between the knees and down to the mattress
    add(cone(J.knee_r.p, along(J, 'ankle_l', 'ankle_r', 0.5).add(new V(0, -0.02, 0)), 0.07 * s, 0.07 * s, { reg: R.CLOTH2, k: 0.1 }));
  }
  if (costume === 'actor' || costume === 'reclining') {
    // wig (onkos) behind the mask: a mass of hair framing the face
    add(ell(hc.clone().addScaledVector(up(hd.q), 0.03 * s).addScaledVector(fwd(hd.q), -0.03 * s), hd.q, [0.112 * s, 0.13 * s, 0.112 * s], { reg: R.HAIR, k: 0.03 }));
    add(cone(hc.clone().addScaledVector(fwd(hd.q), -0.05 * s), hc.clone().addScaledVector(up(hd.q), -0.13 * s).addScaledVector(fwd(hd.q), -0.06 * s), 0.085 * s, 0.075 * s, { reg: R.HAIR, k: 0.04, ref: lft(hd.q), sx: 1.25, sz: 0.75, folds: { n: 16, amp0: 0.006, amp1: 0.008, phase: 0 } }));
    add(ell(hc.clone().addScaledVector(up(hd.q), 0.085 * s).addScaledVector(fwd(hd.q), -0.01 * s), hd.q, [0.09 * s, 0.06 * s, 0.085 * s], { reg: R.HAIR, k: 0.03 }));
  }
  return P;
}

// ------------------------------------------------------------------ masks
function maskTexture(style, kind) {
  const c = document.createElement('canvas'); c.width = c.height = 512;
  const g = c.getContext('2d');
  const vase = style === 'vase', white = style === 'white';
  g.fillStyle = vase ? '#c8743c' : white ? '#f4f3f0' : '#efe7d8'; g.fillRect(0, 0, 512, 512);
  if (white) {   // an unpainted plaster mask: the openings read as soft shadow, not paint
    const grd = g.createRadialGradient(256, 230, 40, 256, 256, 300);
    grd.addColorStop(0, 'rgba(255,255,255,0.0)'); grd.addColorStop(1, 'rgba(90,92,96,0.10)');
    g.fillStyle = grd; g.fillRect(0, 0, 512, 512);
  } else if (!vase) {   // a little tonal modelling painted into the plaster
    const grd = g.createRadialGradient(256, 230, 40, 256, 256, 300);
    grd.addColorStop(0, 'rgba(255,255,255,0.0)'); grd.addColorStop(1, 'rgba(120,100,80,0.18)');
    g.fillStyle = grd; g.fillRect(0, 0, 512, 512);
  }
  const ink = vase ? '#17110d' : white ? '#8a8986' : '#2a221d';
  g.strokeStyle = ink; g.fillStyle = ink; g.lineCap = 'round'; g.lineJoin = 'round';
  // u: 0..1 left->right across the face, v: 0 top .. 1 chin (canvas y)
  const eye = (cx, cy, flip) => {
    g.beginPath();
    g.moveTo(cx - 34 * flip, cy + 2);
    g.quadraticCurveTo(cx, cy - 22, cx + 36 * flip, cy - 2);
    g.quadraticCurveTo(cx, cy + 16, cx - 34 * flip, cy + 2);
    g.closePath();
    if (vase) { g.lineWidth = 6; g.stroke(); g.beginPath(); g.arc(cx + 4 * flip, cy - 3, 8, 0, Math.PI * 2); g.fill(); }
    else { g.fill(); }
  };
  g.save(); g.translate(0, 0); g.scale(1.25, 1.25); g.translate(-51, -12);
  eye(190, 222, 1); eye(322, 222, -1);
  g.restore();
  // tragic brows, raised at the centre
  g.lineWidth = vase ? 8 : 12;
  g.beginPath(); g.moveTo(128, 196); g.quadraticCurveTo(186, 140, 240, 168); g.stroke();
  g.beginPath(); g.moveTo(384, 196); g.quadraticCurveTo(326, 140, 272, 168); g.stroke();
  // open mouth (the mask's speaking hole)
  g.beginPath(); g.ellipse(256, 380, 50, 36, 0, 0, Math.PI * 2);
  if (vase) { g.lineWidth = 7; g.stroke(); g.beginPath(); g.ellipse(256, 374, 26, 15, 0, 0, Math.PI * 2); g.fill(); }
  else g.fill();
  if (vase) {   // nose contour and beard line for the red-figure version
    g.lineWidth = 5; g.beginPath(); g.moveTo(256, 230); g.quadraticCurveTo(246, 290, 262, 316); g.stroke();
    if (kind !== 'young') { g.lineWidth = 4; for (let i = 0; i < 9; i++) { g.beginPath(); g.moveTo(130 + i * 31, 420); g.quadraticCurveTo(150 + i * 28, 470, 160 + i * 24, 505); g.stroke(); } }
  } else {
    g.strokeStyle = white ? 'rgba(120,120,116,0.5)' : 'rgba(42,34,29,0.55)'; g.lineWidth = 4;
    g.beginPath(); g.ellipse(256, 372, 52, 38, 0, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

// an oversized, deep, oval face shell (a theatre mask) with brow, nose and mouth relief;
// polar parametrisation so the outline is a clean oval. Attached to the head joint.
function maskGeometry() {
  const nr = 18, na = 64, pos = [], uv = [], idx = [];
  pos.push(0, 0, 0); uv.push(0.5, 0.5);
  const at = (u, v) => {
    // u: 0..1 left..right as seen from the front (+x is the viewer's right), v: 0 top .. 1 chin
    const th = (u - 0.5) * 2.5, ph = (0.5 - v) * 2.6;
    let x = Math.sin(th) * 0.112 * Math.cos(ph * 0.5);
    let y = Math.sin(ph) * 0.15 - 0.012;
    let z = Math.cos(th) * Math.cos(ph * 0.72) * 0.10 - 0.035;
    const nose = Math.exp(-((u - 0.5) ** 2) / 0.003) * Math.exp(-((v - 0.56) ** 2) / 0.011) * 0.03;
    const brow = Math.exp(-((v - 0.38) ** 2) / 0.0035) * (0.6 + 0.4 * Math.cos((u - 0.5) * 5)) * 0.013;
    const eyes = (Math.exp(-(((u - 0.37) ** 2) / 0.004 + ((v - 0.45) ** 2) / 0.0016)) + Math.exp(-(((u - 0.63) ** 2) / 0.004 + ((v - 0.45) ** 2) / 0.0016))) * -0.014;
    const cheeks = (Math.exp(-(((u - 0.3) ** 2) / 0.01 + ((v - 0.6) ** 2) / 0.01)) + Math.exp(-(((u - 0.7) ** 2) / 0.01 + ((v - 0.6) ** 2) / 0.01))) * 0.006;
    const mouth = Math.exp(-(((u - 0.5) ** 2) / 0.006 + ((v - 0.74) ** 2) / 0.0022)) * -0.018;
    const lips = Math.exp(-(((u - 0.5) ** 2) / 0.012 + ((v - 0.74) ** 2) / 0.006)) * 0.009;
    z += nose + brow + eyes + cheeks + mouth + lips;
    return [x, y, z];
  };
  for (let r = 1; r <= nr; r++) {
    for (let a = 0; a < na; a++) {
      const ang = (a / na) * Math.PI * 2, rr = r / nr;
      const u = 0.5 + 0.5 * rr * Math.cos(ang) * 0.92, v = 0.5 - 0.5 * rr * Math.sin(ang);
      pos.push(...at(u, v)); uv.push(u, 1 - v);
    }
  }
  for (let a = 0; a < na; a++) idx.push(0, 1 + a, 1 + ((a + 1) % na));
  for (let r = 1; r < nr; r++) for (let a = 0; a < na; a++) {
    const i0 = 1 + (r - 1) * na + a, i1 = 1 + (r - 1) * na + ((a + 1) % na);
    const j0 = 1 + r * na + a, j1 = 1 + r * na + ((a + 1) % na);
    idx.push(i0, j0, j1, i0, j1, i1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

// ------------------------------------------------------------------ materials
function clayMaterial(rough = 0.82) {
  return patchMaterial(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: rough, metalness: 0, envMapIntensity: 1.0 }));
}

function vaseMaterial() {
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0, envMapIntensity: 0.8 });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute vec4 aLine;\nvarying vec4 vLine;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvLine = aLine;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec4 vLine;')
      .replace('#include <color_fragment>', `#include <color_fragment>
        {
          // vLine: x = cloth weight, y = fold coordinate, z = position along the garment (1 = hem), w = folds on
          float cloth = smoothstep(0.55, 0.9, vLine.x);
          float f = vLine.y;
          float fw = max(fwidth(f), 1e-4);
          float fold = 1.0 - smoothstep(0.45 * fw, 1.25 * fw, abs(fract(f) - 0.5));
          // folds fade out near the top of the garment, like painted drapery
          fold *= smoothstep(0.12, 0.35, vLine.z) * vLine.w;
          float zw = max(fwidth(vLine.z), 1e-4);
          float hem1 = 1.0 - smoothstep(0.6 * zw, 1.6 * zw, abs(vLine.z - 0.93));
          float hem2 = 1.0 - smoothstep(0.6 * zw, 1.6 * zw, abs(vLine.z - 0.975));
          float dots = step(0.9, vLine.z) * step(vLine.z, 0.965) * (1.0 - smoothstep(0.0, fw * 2.0, length(vec2(fract(f * 2.0) - 0.5, (vLine.z - 0.9475) * 18.0)) - 0.18));
          float ink = cloth * max(max(fold, max(hem1, hem2) * vLine.w), dots * vLine.w);
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.03, 0.018, 0.01), ink * 0.92);
        }`)
      .replace('#include <opaque_fragment>', `
        // flatten the shading toward the painted look: two soft bands, light and shade
        {
          float L = dot(outgoingLight, vec3(0.299, 0.587, 0.114));
          float A = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114)) + 1e-4;
          float k = L / A;
          // dim light (the dark skene interior) stays natural; daylight is flattened into two bands
          float kb = mix(k, mix(0.62, 1.42, smoothstep(0.62, 0.95, k)), smoothstep(0.30, 0.55, k));
          outgoingLight = mix(outgoingLight, diffuseColor.rgb * kb, 0.75);
        }
        #include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => 'vase1';
  return patchMaterial(m);
}

// screen-space constant-width ink outline (inverted hull); px are at 1080p and scale with the frame
export const OUTLINE_RES = { value: new THREE.Vector2(1920, 1080) };
function outlineMaterial(px = 1.8) {
  const m = new THREE.MeshBasicMaterial({ color: '#0d0907', side: THREE.BackSide });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uPx = { value: px };
    sh.uniforms.uRes = OUTLINE_RES;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uPx;\nuniform vec2 uRes;')
      .replace('#include <project_vertex>', `#include <project_vertex>
        {
          vec4 cn = projectionMatrix * modelViewMatrix * vec4(normal, 0.0);
          vec2 dir = normalize(cn.xy + 1e-6);
          gl_Position.xy += dir * uPx * (uRes.y / 1080.0) * gl_Position.w * (2.0 / uRes);
        }`);
  };
  m.customProgramCacheKey = () => 'outline1';
  return m;
}

// ------------------------------------------------------------------ the stand-in object
export class StandIn {
  constructor(opts) {
    this.style = opts.style || 'clay';
    this.costume = opts.costume || 'actor';
    this.masked = opts.mask ?? (this.costume !== 'stagehand');
    this.res = opts.resolution || (this.costume === 'stagehand' ? 0.016 : 0.012);
    this.palette = (opts.palette || PALETTES[this.style][this.costume]).map((c) => new THREE.Color(c));
    this.group = new THREE.Group();
    this.body = new THREE.Mesh(new THREE.BufferGeometry(), this.style === 'vase' ? vaseMaterial() : clayMaterial(this.style === 'white' ? 0.9 : 0.82));
    this.body.castShadow = true; this.body.receiveShadow = true;
    this.group.add(this.body);
    if (this.style === 'vase') {
      this.outline = new THREE.Mesh(this.body.geometry, outlineMaterial(opts.outline || 2.4));
      this.outline.userData.castsShadow = false;
      this.group.add(this.outline);
    }
    if (this.masked) {
      const mm = patchMaterial(new THREE.MeshStandardMaterial({ map: maskTexture(this.style, opts.maskKind), roughness: this.style === 'vase' ? 0.6 : 0.55, envMapIntensity: 1.0 }));
      this.mask = new THREE.Mesh(maskGeometry(), mm);
      this.mask.castShadow = true; this.mask.receiveShadow = true;
      this.group.add(this.mask);
      if (this.style === 'vase') {
        const mo = new THREE.Mesh(this.mask.geometry, outlineMaterial(1.8));
        mo.userData.castsShadow = false;
        this.mask.add(mo);
      }
    }
    this.key = null;
  }

  // J: fk() joints in figure-local space; s: scale
  update(J, s) {
    const key = Object.values(J).map((j) => j.p.toArray().map((v) => v.toFixed(4)).join(',') + j.q.toArray().map((v) => v.toFixed(4)).join(',')).join('|');
    if (key !== this.key) {
      this.key = key;
      const prims = figurePrims(J, this.costume, s);
      const pal = this.palette, vase = this.style === 'vase';
      const g = sdfMesh(prims, this.res * s, (geo, pos, vLists) => {
        const n = pos.length / 3, col = new Float32Array(n * 3), line = new Float32Array(n * 4);
        const lin = pal.map((c) => c.clone().convertSRGBToLinear());
        for (let i = 0; i < n; i++) {
          const info = surfaceInfo(vLists[i], pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2], NREG);
          let r = 0, gg = 0, b = 0;
          for (let k = 0; k < NREG; k++) { r += info.w[k] * lin[k].r; gg += info.w[k] * lin[k].g; b += info.w[k] * lin[k].b; }
          col[i * 3] = r; col[i * 3 + 1] = gg; col[i * 3 + 2] = b;
          if (vase) {
            const P = vLists[i][info.prim];
            const cloth = info.w[R.CLOTH] + info.w[R.CLOTH2];
            const nf = P.folds ? P.folds.n : 0;
            line[i * 4] = cloth;
            line[i * 4 + 1] = info.u * Math.max(nf, 1) + (P.folds ? P.folds.phase / (2 * Math.PI) : 0);
            line[i * 4 + 2] = info.v;
            // linework only where one garment clearly dominates (no zig-zags where primitives meet)
            const conf = Math.min(1, Math.max(0, (info.margin - 0.003) / 0.012));
            line[i * 4 + 3] = P.folds && P.type === 0 ? conf : 0;
          }
        }
        // vertex colours are linear already
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        if (vase) geo.setAttribute('aLine', new THREE.BufferAttribute(line, 4));
      });
      const old = this.body.geometry;
      this.body.geometry = g;
      if (this.outline) this.outline.geometry = g;
      old.dispose();
    }
    if (this.mask) {
      const hd = J.head;
      this.mask.position.copy(new V(0, 0.115 * s, 0.072 * s).applyQuaternion(hd.q).add(hd.p));
      this.mask.quaternion.copy(hd.q);
      this.mask.scale.setScalar(s);
    }
  }
}
