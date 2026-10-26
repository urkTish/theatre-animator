// Geometry builder: merges many boxes / lathes into one BufferGeometry with
// world-scaled UVs (so wood grain has a true size) and a per-part colour tint.
import * as THREE from 'three';

const AX = { x: 0, y: 1, z: 2 };

export class GB {
  constructor() { this.pos = []; this.nrm = []; this.uv = []; this.col = []; this.idx = []; }

  // axis-aligned box in the builder's frame; grain = axis the wood grain follows
  box(x0, x1, y0, y1, z0, z1, o = {}) {
    const grain = AX[o.grain || 'y'], tile = o.tile || [0.6, 2.4], off = o.off || [0, 0], tint = o.tint || [1, 1, 1];
    const lo = [Math.min(x0, x1), Math.min(y0, y1), Math.min(z0, z1)], hi = [Math.max(x0, x1), Math.max(y0, y1), Math.max(z0, z1)];
    const m = o.matrix;
    for (let a = 0; a < 3; a++) {
      const b = (a + 1) % 3, c = (a + 2) % 3;
      for (const s of [0, 1]) {
        const base = this.pos.length / 3;
        const n = [0, 0, 0]; n[a] = s ? 1 : -1;
        const corners = [[0, 0], [1, 0], [1, 1], [0, 1]];
        for (const [i, j] of corners) {
          const p = [0, 0, 0];
          p[a] = s ? hi[a] : lo[a];
          p[b] = i ? hi[b] : lo[b];
          p[c] = j ? hi[c] : lo[c];
          // uv: v along the grain when it lies in this face, else the two face axes
          let u, v;
          if (grain === b) { v = p[b]; u = p[c]; } else if (grain === c) { v = p[c]; u = p[b]; } else { u = p[b]; v = p[c]; }
          this.uv.push(u / tile[0] + off[0], v / tile[1] + off[1]);
          if (m) {
            const vv = new THREE.Vector3(...p).applyMatrix4(m); this.pos.push(vv.x, vv.y, vv.z);
            const nn = new THREE.Vector3(...n).transformDirection(m); this.nrm.push(nn.x, nn.y, nn.z);
          } else { this.pos.push(...p); this.nrm.push(...n); }
          this.col.push(...tint);
        }
        // winding: counter-clockwise seen from outside
        const flip = (s === 1);
        if (flip) this.idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
        else this.idx.push(base, base + 2, base + 1, base, base + 3, base + 2);
      }
    }
    return this;
  }

  // append an existing (indexed or not) geometry, transformed
  add(geom, matrix, tint = [1, 1, 1], uvScale = [1, 1]) {
    const g = geom.index ? geom : geom.clone();
    const p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
    const base = this.pos.length / 3;
    const v = new THREE.Vector3(), nm = new THREE.Matrix3();
    if (matrix) nm.getNormalMatrix(matrix);
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i); if (matrix) v.applyMatrix4(matrix); this.pos.push(v.x, v.y, v.z);
      v.fromBufferAttribute(n, i); if (matrix) v.applyMatrix3(nm).normalize(); this.nrm.push(v.x, v.y, v.z);
      if (uv) this.uv.push(uv.getX(i) * uvScale[0], uv.getY(i) * uvScale[1]); else this.uv.push(0, 0);
      this.col.push(...tint);
    }
    if (g.index) for (let i = 0; i < g.index.count; i++) this.idx.push(base + g.index.getX(i));
    else for (let i = 0; i < p.count; i++) this.idx.push(base + i);
    return this;
  }

  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.setIndex(this.idx);
    g.computeBoundingBox(); g.computeBoundingSphere();
    return g;
  }
}

// a box with rounded edges (cushions, mattress, nail heads)
export function roundedBox(w, h, d, r, seg = 4) {
  const g = new THREE.BoxGeometry(w, h, d, seg * 2, seg * 2, seg * 2);
  const p = g.attributes.position, v = new THREE.Vector3(), c = new THREE.Vector3();
  const inner = new THREE.Vector3(w / 2 - r, h / 2 - r, d / 2 - r);
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    c.copy(v).clamp(inner.clone().negate(), inner);
    const dlt = v.clone().sub(c);
    if (dlt.lengthSq() > 1e-12) v.copy(c).addScaledVector(dlt.normalize(), r);
    p.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals();
  return g;
}

// lathe from a [radius, height] profile around +y
export function lathe(profile, seg = 32) {
  return new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(Math.max(r, 1e-4), y)), seg);
}

export function tr(x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, s = 1) {
  const m = new THREE.Matrix4();
  m.compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(s, s, s));
  return m;
}
