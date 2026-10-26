// Signed-distance modelling + surface nets meshing for the built-in stand-ins.
// A figure is a smooth union of round cones / ellipsoids / tori, so limbs and
// drapery blend like a sculpted clay maquette. Fully deterministic.
import * as THREE from 'three';

// --------------------------------------------------------------- primitives
// Each primitive: {type, ..., k (blend radius), reg (region id), bound: [cx,cy,cz,r]}
const V = THREE.Vector3;

function frameFromAxis(d, ref) {
  const e1 = new V().copy(ref).addScaledVector(d, -ref.dot(d));
  if (e1.lengthSq() < 1e-8) e1.set(1, 0, 0).addScaledVector(d, -d.x);
  e1.normalize();
  const e2 = new V().crossVectors(e1, d).normalize();
  return [e1, e2];
}

// round cone from a (radius ra) to b (radius rb); optional elliptical section
// (sx along `ref`, sz across), optional folds {n, amp0, amp1, phase}
export function cone(a, b, ra, rb, o = {}) {
  const d = new V().subVectors(b, a); const L = d.length(); d.divideScalar(L || 1);
  const [e1, e2] = frameFromAxis(d, o.ref || new V(1, 0, 0));
  const sx = o.sx || 1, sz = o.sz || 1;
  const bc = new V().addVectors(a, b).multiplyScalar(0.5);
  return {
    type: 0, ax: a.x, ay: a.y, az: a.z, dx: d.x, dy: d.y, dz: d.z, L,
    e1x: e1.x, e1y: e1.y, e1z: e1.z, e2x: e2.x, e2y: e2.y, e2z: e2.z,
    ra, rb, sx, sz, smin: Math.min(sx, sz, 1),
    cb: (ra - rb) / L, ca: Math.sqrt(Math.max(0, 1 - ((ra - rb) / L) ** 2)),
    folds: o.folds || null, k: o.k ?? 0.03, reg: o.reg ?? 0,
    bound: [bc.x, bc.y, bc.z, L / 2 + Math.max(ra, rb) * Math.max(sx, sz, 1) + 0.05],
    aabb: (() => { const m = Math.max(ra, rb) * Math.max(sx, sz, 1) + (o.folds ? o.folds.amp1 : 0) + 0.01; return [Math.min(a.x, b.x) - m, Math.min(a.y, b.y) - m, Math.min(a.z, b.z) - m, Math.max(a.x, b.x) + m, Math.max(a.y, b.y) + m, Math.max(a.z, b.z) + m]; })(),
  };
}

// ellipsoid centred at c with axes (q rotates the local frame), radii r=[rx,ry,rz]
export function ell(c, q, r, o = {}) {
  const m = new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromQuaternion(q));
  const e = m.elements;  // column-major: columns are the local axes in world
  return {
    type: 1, cx: c.x, cy: c.y, cz: c.z,
    m00: e[0], m01: e[1], m02: e[2], m10: e[3], m11: e[4], m12: e[5], m20: e[6], m21: e[7], m22: e[8],
    rx: r[0], ry: r[1], rz: r[2], k: o.k ?? 0.03, reg: o.reg ?? 0,
    bound: [c.x, c.y, c.z, Math.max(...r) + 0.05],
    aabb: (() => { const m = Math.max(...r) + 0.01; return [c.x - m, c.y - m, c.z - m, c.x + m, c.y + m, c.z + m]; })(),
  };
}

// torus (belt) around axis d at centre c
export function torus(c, d, R, r, o = {}) {
  const dd = d.clone().normalize();
  const [e1, e2] = frameFromAxis(dd, o.ref || new V(1, 0, 0));
  return {
    type: 2, cx: c.x, cy: c.y, cz: c.z, dx: dd.x, dy: dd.y, dz: dd.z,
    e1x: e1.x, e1y: e1.y, e1z: e1.z, e2x: e2.x, e2y: e2.y, e2z: e2.z,
    R, r, sx: o.sx || 1, sz: o.sz || 1, k: o.k ?? 0.012, reg: o.reg ?? 0,
    bound: [c.x, c.y, c.z, R * Math.max(o.sx || 1, o.sz || 1) + r + 0.05],
    aabb: (() => { const m = R * Math.max(o.sx || 1, o.sz || 1) + r + 0.01; return [c.x - m, c.y - m, c.z - m, c.x + m, c.y + m, c.z + m]; })(),
  };
}

// evaluate primitive i at p; also writes param u (around) / v (along) into out
function evalPrim(P, x, y, z, out) {
  if (P.type === 0) {
    const px = x - P.ax, py = y - P.ay, pz = z - P.az;
    const lx = (px * P.e1x + py * P.e1y + pz * P.e1z) / P.sx;
    const ly = px * P.dx + py * P.dy + pz * P.dz;
    const lz = (px * P.e2x + py * P.e2y + pz * P.e2z) / P.sz;
    const q = Math.sqrt(lx * lx + lz * lz);
    let d;
    const k = -P.cb * q + P.ca * ly;
    if (k < 0) d = Math.sqrt(q * q + ly * ly) - P.ra;
    else if (k > P.ca * P.L) d = Math.sqrt(q * q + (ly - P.L) * (ly - P.L)) - P.rb;
    else d = q * P.ca + ly * P.cb - P.ra;
    d *= P.smin;
    const t = Math.min(1, Math.max(0, ly / P.L));
    let ang = 0;
    if (P.folds || out) ang = Math.atan2(lz, lx);
    if (P.folds) {
      const f = P.folds;
      const amp = f.amp0 + (f.amp1 - f.amp0) * Math.pow(t, f.pow || 1.5);
      const w = Math.sin(ang * f.n + f.phase + Math.sin(ang * 3 + f.phase * 2) * 0.8 + t * (f.twist || 0));
      d -= amp * (0.5 + 0.5 * w) * (w > 0 ? 1 : 0.6);
    }
    if (out) { out.u = ang / (2 * Math.PI) + 0.5; out.v = t; }
    return d;
  }
  if (P.type === 1) {
    const px = x - P.cx, py = y - P.cy, pz = z - P.cz;
    const lx = (px * P.m00 + py * P.m01 + pz * P.m02) / P.rx;
    const ly = (px * P.m10 + py * P.m11 + pz * P.m12) / P.ry;
    const lz = (px * P.m20 + py * P.m21 + pz * P.m22) / P.rz;
    const k0 = Math.sqrt(lx * lx + ly * ly + lz * lz);
    const k1 = Math.sqrt((lx / P.rx) ** 2 + (ly / P.ry) ** 2 + (lz / P.rz) ** 2);
    if (out) { out.u = Math.atan2(lz, lx) / (2 * Math.PI) + 0.5; out.v = 0.5 - ly * 0.5; }
    return k1 > 1e-9 ? (k0 * (k0 - 1)) / k1 : -Math.min(P.rx, P.ry, P.rz);
  }
  // torus
  const px = x - P.cx, py = y - P.cy, pz = z - P.cz;
  const lx = (px * P.e1x + py * P.e1y + pz * P.e1z) / P.sx;
  const ly = px * P.dx + py * P.dy + pz * P.dz;
  const lz = (px * P.e2x + py * P.e2y + pz * P.e2z) / P.sz;
  const qx = Math.sqrt(lx * lx + lz * lz) - P.R;
  if (out) { out.u = Math.atan2(lz, lx) / (2 * Math.PI) + 0.5; out.v = 0.5; }
  return (Math.sqrt(qx * qx + ly * ly) - P.r) * Math.min(P.sx, P.sz, 1);
}

function smin(a, b, k) {
  if (k <= 0) return Math.min(a, b);
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
}

export function sdfValue(prims, x, y, z) {
  let d = 1e9;
  for (let i = 0; i < prims.length; i++) {
    const P = prims[i], b = P.bound;
    const bx = x - b[0], by = y - b[1], bz = z - b[2];
    const lb = Math.sqrt(bx * bx + by * by + bz * bz) - b[3];
    if (lb > d + P.k) continue;          // cannot affect the blend
    d = smin(d, evalPrim(P, x, y, z, null), P.k);
  }
  return d;
}

// region weights and surface params at a surface point (for colour / linework)
const _o = { u: 0, v: 0 };
export function surfaceInfo(prims, x, y, z, nReg) {
  const w = new Float32Array(nReg);
  let best = 1e9, second = 1e9, bu = 0, bv = 0, breg = 0, bi = -1;
  const ds = new Float32Array(prims.length);
  for (let i = 0; i < prims.length; i++) {
    const d = evalPrim(prims[i], x, y, z, _o);
    ds[i] = d;
    if (d < best) { second = best; best = d; bu = _o.u; bv = _o.v; breg = prims[i].reg; bi = i; }
    else if (d < second) second = d;
  }
  let sum = 0;
  for (let i = 0; i < prims.length; i++) {
    const t = Math.max(0, 1 - (ds[i] - best) / 0.007);
    const ww = t * t;
    w[prims[i].reg] += ww; sum += ww;
  }
  for (let i = 0; i < nReg; i++) w[i] /= sum || 1;
  return { w, u: bu, v: bv, reg: breg, prim: bi, margin: second - best };
}

// primitives that can matter (|d| < reach) somewhere inside a sphere (c, r)
function primsNear(prims, cx, cy, cz, r, reach) {
  const out = [];
  for (const P of prims) {
    const b = P.bound;
    if (Math.hypot(cx - b[0], cy - b[1], cz - b[2]) - b[3] - r < reach + P.k) out.push(P);
  }
  return out;
}

// --------------------------------------------------------------- surface nets
export function mesh(prims, h, info) {
  // bounds
  let x0 = 1e9, y0 = 1e9, z0 = 1e9, x1 = -1e9, y1 = -1e9, z1 = -1e9;
  for (const P of prims) {
    const b = P.aabb;
    x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); z0 = Math.min(z0, b[2]);
    x1 = Math.max(x1, b[3]); y1 = Math.max(y1, b[4]); z1 = Math.max(z1, b[5]);
  }
  x0 -= 2 * h; y0 -= 2 * h; z0 -= 2 * h; x1 += 2 * h; y1 += 2 * h; z1 += 2 * h;
  const nx = Math.ceil((x1 - x0) / h) + 2, ny = Math.ceil((y1 - y0) / h) + 2, nz = Math.ceil((z1 - z0) / h) + 2;
  const N = nx * ny * nz;
  const F = new Float32Array(N);
  // coarse pass (every 3rd sample) to skip empty space, then refine near the surface
  const C = 3;
  const cnx = Math.ceil(nx / C) + 1, cny = Math.ceil(ny / C) + 1, cnz = Math.ceil(nz / C) + 1;
  const CF = new Float32Array(cnx * cny * cnz);
  for (let k = 0; k < cnz; k++) for (let j = 0; j < cny; j++) for (let i = 0; i < cnx; i++) {
    CF[(k * cny + j) * cnx + i] = sdfValue(prims, x0 + i * C * h, y0 + j * C * h, z0 + k * C * h);
  }
  const band = C * h * 1.9;
  // per-block primitive lists (blocks of B^3 samples)
  const B = 8, bnx = Math.ceil(nx / B), bny = Math.ceil(ny / B), bnz = Math.ceil(nz / B);
  const blockR = B * h * 0.8660254 + h;
  const lists = new Array(bnx * bny * bnz);
  const listAt = (i, j, k) => {
    const bi = Math.min(bnx - 1, Math.floor(i / B)), bj = Math.min(bny - 1, Math.floor(j / B)), bk = Math.min(bnz - 1, Math.floor(k / B));
    const id = (bk * bny + bj) * bnx + bi;
    let L = lists[id];
    if (!L) L = lists[id] = primsNear(prims, x0 + (bi + 0.5) * B * h, y0 + (bj + 0.5) * B * h, z0 + (bk + 0.5) * B * h, blockR, band + h);
    return L;
  };
  for (let k = 0; k < nz; k++) {
    const ck = Math.min(cnz - 1, Math.round(k / C));
    for (let j = 0; j < ny; j++) {
      const cj = Math.min(cny - 1, Math.round(j / C));
      for (let i = 0; i < nx; i++) {
        const ci = Math.min(cnx - 1, Math.round(i / C));
        const c = CF[(ck * cny + cj) * cnx + ci];
        const idx = (k * ny + j) * nx + i;
        if (Math.abs(c) > band) { F[idx] = c; continue; }
        F[idx] = sdfValue(listAt(i, j, k), x0 + i * h, y0 + j * h, z0 + k * h);
      }
    }
  }
  const cellV = new Int32Array(N).fill(-1);
  const pos = [];
  const at = (i, j, k) => F[(k * ny + j) * nx + i];
  const EDGES = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
  const CO = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]];
  const v = new Float32Array(8);
  for (let k = 0; k < nz - 1; k++) for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    let mask = 0;
    for (let c = 0; c < 8; c++) { v[c] = at(i + CO[c][0], j + CO[c][1], k + CO[c][2]); if (v[c] < 0) mask |= 1 << c; }
    if (mask === 0 || mask === 255) continue;
    let sx = 0, sy = 0, sz = 0, n = 0;
    for (const [a, b] of EDGES) {
      if ((v[a] < 0) === (v[b] < 0)) continue;
      const t = v[a] / (v[a] - v[b]);
      sx += CO[a][0] + (CO[b][0] - CO[a][0]) * t;
      sy += CO[a][1] + (CO[b][1] - CO[a][1]) * t;
      sz += CO[a][2] + (CO[b][2] - CO[a][2]) * t;
      n++;
    }
    cellV[(k * ny + j) * nx + i] = pos.length / 3;
    pos.push(x0 + (i + sx / n) * h, y0 + (j + sy / n) * h, z0 + (k + sz / n) * h);
  }
  const idx = [];
  const cv = (i, j, k) => cellV[(k * ny + j) * nx + i];
  const quad = (a, b, c, d, flip) => {
    if (a < 0 || b < 0 || c < 0 || d < 0) return;
    if (flip) idx.push(a, c, b, a, d, c); else idx.push(a, b, c, a, c, d);
  };
  for (let k = 1; k < nz - 1; k++) for (let j = 1; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    const a = at(i, j, k), b = at(i + 1, j, k);
    if ((a < 0) !== (b < 0)) quad(cv(i, j - 1, k - 1), cv(i, j, k - 1), cv(i, j, k), cv(i, j - 1, k), !(a < 0));
  }
  for (let k = 1; k < nz - 1; k++) for (let j = 0; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const a = at(i, j, k), b = at(i, j + 1, k);
    if ((a < 0) !== (b < 0)) quad(cv(i - 1, j, k - 1), cv(i - 1, j, k), cv(i, j, k), cv(i, j, k - 1), !(a < 0));
  }
  for (let k = 0; k < nz - 1; k++) for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const a = at(i, j, k), b = at(i, j, k + 1);
    if ((a < 0) !== (b < 0)) quad(cv(i - 1, j - 1, k), cv(i, j - 1, k), cv(i, j, k), cv(i - 1, j, k), !(a < 0));
  }
  // one relaxation step toward the true surface (project along the gradient), and normals
  const nrm = new Float32Array(pos.length);
  const e = h * 0.35;
  const vLists = [];
  for (let i = 0; i < pos.length; i += 3) {
    let x = pos[i], y = pos[i + 1], z = pos[i + 2];
    const L = listAt(Math.round((x - x0) / h), Math.round((y - y0) / h), Math.round((z - z0) / h));
    vLists.push(L);
    {
      const a = sdfValue(L, x + e, y - e, z - e), b = sdfValue(L, x - e, y - e, z + e);
      const c = sdfValue(L, x - e, y + e, z - e), dd = sdfValue(L, x + e, y + e, z + e);
      const gx = a - b - c + dd, gy = -a - b + c + dd, gz = -a + b - c + dd;
      const d = (a + b + c + dd) * 0.25;
      const gl = Math.hypot(gx, gy, gz) || 1;
      const nx_ = gx / gl, ny_ = gy / gl, nz_ = gz / gl;
      const s = Math.max(-h * 0.5, Math.min(h * 0.5, d));
      x -= nx_ * s; y -= ny_ * s; z -= nz_ * s;
      nrm[i] = nx_; nrm[i + 1] = ny_; nrm[i + 2] = nz_;
    }
    pos[i] = x; pos[i + 1] = y; pos[i + 2] = z;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setIndex(idx);
  if (info) info(g, pos, vLists);
  g.computeBoundingSphere(); g.computeBoundingBox();
  return g;
}
