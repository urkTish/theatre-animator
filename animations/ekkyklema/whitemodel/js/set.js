// The set as a white museum model: the wooden skene with its central double door, the ekkyklema with
// its tableau props, on a white base plate and a dark plinth. Geometry is unchanged from ../motion/js/set.js.
// Everything here belongs to the "plate". Character slots live in cast.js.
import * as THREE from 'three';
import { GB, roundedBox, lathe, tr } from './geom.js';
import { GEO } from './timeline.js';
import { patchMaterial, PLATE } from './lighting.js';
import { rng } from './util.js';

export const LAYER_SET = 1;

function std(o, kind = 0) { return patchMaterial(new THREE.MeshStandardMaterial(o), kind); }

// The white model: every part keeps its geometry; only the material changes. Matte white, crisp edges.
// Joints stay legible because the sheathing behind the boards is a light grey.
function mats() {
  const M = {};
  const white = (c = '#f3f3f1', r = 0.9) => std({ color: c, vertexColors: true, roughness: r, metalness: 0 });
  M.boards = white('#f3f3f1');
  M.timber = white('#f1f1ef');
  M.deck = white('#f6f6f4', 0.88);
  M.couch = white('#f0f0ee', 0.85);
  M.iron = white('#d6d6d3', 0.75);
  M.backing = white('#a9aaa8', 1.0);
  M.linen = std({ color: '#f5f5f3', roughness: 0.92 });
  M.madder = std({ color: '#e4e2de', roughness: 0.92 });
  M.glaze = std({ color: '#e9e9e7', roughness: 0.6 });
  M.terracotta = std({ color: '#e9e9e7', roughness: 0.6 });
  M.plate = std({ color: '#f0f0ee', roughness: 0.92 }, 1);
  M.plateSide = std({ color: '#dddbd6', roughness: 0.9 }, 2);
  M.plinth = std({ color: '#17181a', roughness: 0.5, metalness: 0 }, 2);
  return M;
}

function mesh(geom, mat, { shadow = true, receive = true } = {}) {
  const m = new THREE.Mesh(geom, mat);
  m.castShadow = shadow; m.receiveShadow = receive;
  m.layers.enable(LAYER_SET);
  return m;
}

function tintFn(r, amt = 0.12, hue = 0.04) {
  return () => {
    const k = 1 - amt + 2 * amt * r();
    const h = (r() - 0.5) * hue;
    return [k * (1 + h), k, k * (1 - h)];
  };
}

// ------------------------------------------------------------------ skene
function buildSkene(M, set) {
  const { SKENE_W, SKENE_H, SKENE_D, WALL_T, DOOR_W, DOOR_H } = GEO;
  const hw = SKENE_W / 2, dx = DOOR_W / 2;
  const r = rng(1201), tint = tintFn(r, 0.14, 0.06);
  const boards = new GB(), timber = new GB(), backing = new GB(), iron = new GB();
  const off = () => [r() * 10, r() * 10];

  // backing (dark sheathing seen through the board joints), facade
  const bz0 = -WALL_T, bz1 = -0.07;
  for (const [a, c] of [[-hw, -dx - 0.24], [dx + 0.24, hw]]) backing.box(a, c, 0, SKENE_H - 0.12, bz0, bz1);
  backing.box(-dx - 0.24, dx + 0.24, DOOR_H + 0.32, SKENE_H - 0.12, bz0, bz1);

  // vertical facade boards with 8 mm joints, slightly irregular widths
  const boardRun = (x0, x1, y0, y1, z0, z1, axis = 'x') => {
    let x = x0;
    while (x < x1 - 0.05) {
      let w = 0.24 + r() * 0.08;
      if (x1 - (x + w) < 0.12) w = x1 - x;
      const zj = (r() - 0.5) * 0.006;
      if (axis === 'x') boards.box(x + 0.004, x + w - 0.004, y0, y1, z0 + zj, z1 + zj, { grain: 'y', off: off(), tint: tint() });
      else boards.box(z0 + zj, z1 + zj, y0, y1, x + 0.004, x + w - 0.004, { grain: 'y', off: off(), tint: tint() });
      x += w;
    }
  };
  boardRun(-hw, -dx - 0.24, 0.0, SKENE_H - 0.12, -0.07, -0.03);
  boardRun(dx + 0.24, hw, 0.0, SKENE_H - 0.12, -0.07, -0.03);
  boardRun(-dx - 0.24, dx + 0.24, DOOR_H + 0.32, SKENE_H - 0.12, -0.07, -0.03);
  // side walls and back wall (outer faces), boards along z / x
  for (const s of [-1, 1]) {
    backing.box(s * hw, s * (hw - 0.13), 0, SKENE_H - 0.12, -SKENE_D, -WALL_T);
    boardRun(-SKENE_D, -0.2, 0, SKENE_H - 0.12, s * (hw + 0.04), s * hw, 'z');
  }
  backing.box(-hw, hw, 0, SKENE_H - 0.12, -SKENE_D, -SKENE_D + 0.13);
  boardRun(-hw, hw, 0, SKENE_H - 0.12, -SKENE_D - 0.04, -SKENE_D);

  // posts every 2 m on the facade, corner posts
  for (const x of [-hw + 0.13, -4, -2, 2, 4, hw - 0.13]) {
    timber.box(x - 0.13, x + 0.13, 0, SKENE_H - 0.2, -0.23, 0.06, { grain: 'y', off: off(), tint: tint() });
  }
  for (const s of [-1, 1]) timber.box(s * (hw - 0.0), s * (hw - 0.26), 0, SKENE_H - 0.2, -SKENE_D - 0.06, -SKENE_D + 0.2, { grain: 'y', off: off(), tint: tint() });
  // rails: top rail full width, low rail either side of the door
  timber.box(-hw - 0.03, hw + 0.03, SKENE_H - 0.56, SKENE_H - 0.30, -0.05, 0.03, { grain: 'x', off: off(), tint: tint() });
  for (const s of [-1, 1]) {
    const a = s * (dx + 0.24), c = s * (hw + 0.02);
    timber.box(Math.min(a, c), Math.max(a, c), 0.38, 0.58, -0.05, 0.02, { grain: 'x', off: off(), tint: tint() });
  }
  // door frame: jambs, lintel (with a shallow drip cap), worn threshold
  for (const s of [-1, 1]) timber.box(s * dx, s * (dx + 0.24), 0, DOOR_H, -0.25, 0.02, { grain: 'y', off: off(), tint: tint() });
  timber.box(-dx - 0.40, dx + 0.40, DOOR_H, DOOR_H + 0.32, -0.25, 0.04, { grain: 'x', off: off(), tint: tint() });
  timber.box(-dx - 0.48, dx + 0.48, DOOR_H + 0.32, DOOR_H + 0.38, -0.08, 0.10, { grain: 'x', off: off(), tint: tint() });
  timber.box(-dx, dx, -0.04, 0.025, -0.24, 0.02, { grain: 'x', off: off(), tint: [0.85, 0.82, 0.8] });
  // roof: plank deck with an eave, exposed joist ends and a fascia
  timber.box(-hw - 0.30, hw + 0.30, SKENE_H - 0.12, SKENE_H, -SKENE_D - 0.3, 0.42, { grain: 'z', off: off(), tint: tint() });
  timber.box(-hw - 0.30, hw + 0.30, SKENE_H - 0.36, SKENE_H + 0.02, 0.36, 0.44, { grain: 'x', off: off(), tint: tint() });
  timber.box(-hw - 0.34, hw + 0.34, SKENE_H + 0.02, SKENE_H + 0.09, 0.30, 0.50, { grain: 'x', off: off(), tint: tint() });
  for (const s of [-1, 1]) timber.box(s * (hw + 0.30), s * (hw + 0.38), SKENE_H - 0.36, SKENE_H + 0.02, -SKENE_D - 0.3, 0.44, { grain: 'z', off: off(), tint: tint() });
  for (let x = -hw + 0.2; x < hw; x += 0.6) {
    timber.box(x - 0.06, x + 0.06, SKENE_H - 0.30, SKENE_H - 0.12, -SKENE_D + 0.1, 0.36, { grain: 'z', off: off(), tint: tint() });
  }
  // interior: posts, a mid beam, a floor sill line (all in darkness, but they read)
  for (const x of [-4, 4]) timber.box(x - 0.11, x + 0.11, 0, SKENE_H - 0.58, -2.46, -2.24, { grain: 'y', off: off(), tint: tint() });
  timber.box(-hw + 0.1, hw - 0.1, SKENE_H - 0.58, SKENE_H - 0.30, -2.47, -2.23, { grain: 'x', off: off(), tint: tint() });
  // interior faces of the walls (a second skin of boards so the inside is not black void)
  boardRun(-hw + 0.13, -dx - 0.24, 0, SKENE_H - 0.3, -WALL_T - 0.03, -WALL_T);
  boardRun(dx + 0.24, hw - 0.13, 0, SKENE_H - 0.3, -WALL_T - 0.03, -WALL_T);
  boardRun(-hw + 0.13, hw - 0.13, 0, SKENE_H - 0.3, -SKENE_D + 0.13, -SKENE_D + 0.16);
  // iron: a few big nail heads on the rails and posts
  const nail = roundedBox(0.035, 0.035, 0.02, 0.008, 2);
  for (const x of [-hw + 0.13, -4, -2, 2, 4, hw - 0.13]) {
    for (const y of [0.48, SKENE_H - 0.43]) iron.add(nail, tr(x, y, 0.035));
  }

  const g = new THREE.Group(); g.name = 'skene';
  const parts = [mesh(boards.build(), M.boards), mesh(timber.build(), M.timber), mesh(backing.build(), M.backing), mesh(iron.build(), M.iron)];
  parts.forEach((p) => g.add(p));
  set.occluders.push(...parts.slice(0, 3));
  return g;
}

// two ledged leaves with iron straps outside; hinged at the inner face, swing inward (R6)
function buildDoors(M, set) {
  const { DOOR_W, DOOR_H, WALL_T, LEAF_T } = GEO;
  const r = rng(77), tint = tintFn(r, 0.10, 0.05);
  const leaves = [];
  for (const side of [1, -1]) {
    const hinge = new THREE.Group();
    hinge.position.set(side * DOOR_W / 2, 0, -WALL_T + 0.002);
    const wood = new GB(), iron = new GB();
    const w = DOOR_W / 2 - 0.006, n = 6;
    for (let i = 0; i < n; i++) {
      const a = -side * (w * i / n + 0.003), c = -side * (w * (i + 1) / n - 0.003);
      wood.box(a, c, 0.012, DOOR_H - 0.012, 0.0, LEAF_T, { grain: 'y', off: [r() * 9, r() * 9], tint: tint() });
    }
    // inner ledges and a diagonal brace
    for (const yc of [0.5, DOOR_H - 0.55]) wood.box(-side * 0.08, -side * (w - 0.08), yc - 0.09, yc + 0.09, -0.04, 0.0, { grain: 'x', off: [r() * 9, r() * 9], tint: tint() });
    {
      const len = Math.hypot(w - 0.3, DOOR_H - 1.05 - 0.18), ang = Math.atan2(DOOR_H - 1.05 - 0.18, w - 0.3);
      const m = tr(-side * w / 2, DOOR_H / 2, -0.02, 0, 0, side * -ang);
      wood.box(-len / 2, len / 2, -0.07, 0.07, -0.018, 0.018, { grain: 'x', matrix: m, tint: tint(), off: [r() * 9, r() * 9] });
    }
    // outer iron straps with nail heads, strap ends forged to a point
    for (const yc of [0.42, 1.62, 2.80]) {
      iron.box(-side * 0.02, -side * (w - 0.10), yc - 0.03, yc + 0.03, LEAF_T, LEAF_T + 0.007);
      const tip = -side * (w - 0.10);
      iron.box(tip, tip - side * 0.06, yc - 0.018, yc + 0.018, LEAF_T, LEAF_T + 0.007);
      for (let k = 0; k < 7; k++) {
        const x = -side * (0.08 + k * (w - 0.22) / 6);
        iron.add(roundedBox(0.022, 0.022, 0.012, 0.006, 2), tr(x, yc, LEAF_T + 0.010));
      }
    }
    // ring pull on the outer face near the meeting edge
    const ring = new THREE.TorusGeometry(0.075, 0.011, 8, 28);
    iron.add(ring, tr(-side * (w - 0.17), 1.13, LEAF_T + 0.02, 0, 0, 0));
    iron.add(roundedBox(0.07, 0.07, 0.015, 0.006, 2), tr(-side * (w - 0.17), 1.21, LEAF_T + 0.007));
    const lw = mesh(wood.build(), M.timber), li = mesh(iron.build(), M.iron);
    hinge.add(lw, li);
    set.occluders.push(lw);
    leaves.push({ side, hinge });
  }
  return leaves;
}

// ------------------------------------------------------------------ the ekkyklema
function buildPlatform(M, set) {
  const { PLAT_W, PLAT_D, PLAT_H, WHEEL_R } = GEO;
  const hw = PLAT_W / 2, hd = PLAT_D / 2, H = PLAT_H, bt = 0.055;
  const r = rng(96), tint = tintFn(r, 0.08, 0.04);
  const root = new THREE.Group(); root.name = 'platform';
  const deck = new GB(), frame = new GB(), iron = new GB();
  const nb = 8;
  for (let i = 0; i < nb; i++) {
    const z0 = -hd + i * PLAT_D / nb + 0.004, z1 = -hd + (i + 1) * PLAT_D / nb - 0.004;
    const dz = (r() - 0.5) * 0.004;
    deck.box(-hw, hw, H - bt + dz, H + dz, z0, z1, { grain: 'x', tile: [0.4, 1.6], off: [r() * 9, r() * 9], tint: tint() });
  }
  for (const s of [-1, 1]) frame.box(s * 0.86, s * 1.02, 0.135, H - bt, -hd + 0.03, hd - 0.03, { grain: 'z', off: [r() * 9, r() * 9], tint: tint() });
  for (const s of [-1, 1]) frame.box(-hw + 0.02, hw - 0.02, 0.15, H - bt, s * (hd - 0.075), s * (hd - 0.005), { grain: 'x', off: [r() * 9, r() * 9], tint: tint() });
  frame.box(-0.86, 0.86, 0.16, H - bt, -0.06, 0.06, { grain: 'x', off: [r() * 9, r() * 9], tint: tint() });
  for (const s of [-1, 1]) for (const za of [-0.55, 0.55]) frame.box(s * 0.84, s * 1.05, 0.075, 0.14, za - 0.08, za + 0.08, { grain: 'z', tint: tint() });
  for (const za of [-0.55, 0.55]) iron.add(new THREE.CylinderGeometry(0.022, 0.022, 2.32, 12), tr(0, WHEEL_R, za, 0, 0, Math.PI / 2));
  // iron corner plates on the deck edge
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) iron.box(sx * hw, sx * (hw - 0.16), H - 0.05, H + 0.003, sz * hd, sz * (hd - 0.16));
  const parts = [mesh(deck.build(), M.deck), mesh(frame.build(), M.timber), mesh(iron.build(), M.iron)];
  parts.forEach((p) => root.add(p));
  set.occluders.push(parts[0], parts[1]);

  // four solid wheels: three planks (visible joints so the rotation reads), iron tyre and hub
  const wheels = [];
  const wheelGeo = (() => {
    const w = new GB();
    w.add(new THREE.CylinderGeometry(WHEEL_R - 0.008, WHEEL_R - 0.008, 0.06, 40), tr(0, 0, 0, 0, 0, Math.PI / 2), [1, 1, 1], [3, 1]);
    return w.build();
  })();
  const seamGeo = new GB();
  for (const y of [-0.035, 0.035]) for (const s of [-1, 1]) seamGeo.box(s * 0.0305, s * 0.0315, y - 0.003, y + 0.003, -WHEEL_R * 0.93, WHEEL_R * 0.93);
  const seam = seamGeo.build();
  const tyre = new GB();
  tyre.add(new THREE.TorusGeometry(WHEEL_R - 0.006, 0.009, 6, 40), tr(0, 0, 0, 0, Math.PI / 2, 0));
  tyre.add(new THREE.CylinderGeometry(0.045, 0.05, 0.085, 16), tr(0, 0, 0, 0, 0, Math.PI / 2));
  // a dowel peg across the planks (also makes the rotation visible)
  for (const s of [-1, 1]) tyre.box(s * 0.031, s * 0.034, -0.012, 0.012, 0.055, 0.085);
  const tyreGeo = tyre.build();
  for (const s of [-1, 1]) {
    for (const za of [-0.55, 0.55]) {
      const wg = new THREE.Group();
      wg.position.set(s * 1.115, WHEEL_R, za);
      wg.add(mesh(wheelGeo, M.timber), mesh(seam, M.backing), mesh(tyreGeo, M.iron));
      root.add(wg);
      wheels.push(wg);
    }
  }
  return { root, wheels };
}

// couch (kline) with mattress, bolster and a madder throw; stool with a kylix (R5)
function buildTableau(M, set, plat) {
  const H = GEO.PLAT_H;
  const g = new THREE.Group(); g.name = 'tableau';
  const wood = new GB(), r = rng(5150), tint = tintFn(r, 0.06, 0.03);
  const cx = -0.12, cz = -0.12, L = 1.84, W = 0.80, top = 0.40;
  const x0 = cx - L / 2, x1 = cx + L / 2, z0 = cz - W / 2, z1 = cz + W / 2;
  const leg = lathe([[0.0, 0], [0.034, 0], [0.04, 0.03], [0.028, 0.07], [0.05, 0.12], [0.03, 0.17], [0.026, 0.25], [0.042, 0.29], [0.034, 0.33], [0.04, top - 0.06], [0.0, top - 0.06]], 20);
  for (const x of [x0 + 0.05, x1 - 0.05]) for (const z of [z0 + 0.05, z1 - 0.05]) wood.add(leg, tr(x, H, z), tint(), [2, 1]);
  wood.box(x0, x1, H + top - 0.10, H + top - 0.02, z0, z0 + 0.06, { grain: 'x', tint: tint(), off: [r(), r()] });
  wood.box(x0, x1, H + top - 0.10, H + top - 0.02, z1 - 0.06, z1, { grain: 'x', tint: tint(), off: [r(), r()] });
  for (const x of [x0, x1 - 0.06]) wood.box(x, x + 0.06, H + top - 0.10, H + top - 0.02, z0, z1, { grain: 'z', tint: tint() });
  // raised, outward-curving headrest at the head end (+x): a curved board, extruded across the couch
  {
    const sh = new THREE.Shape();
    const pts = [];
    for (let i = 0; i <= 12; i++) { const a = i / 12; pts.push([0.0 + a * a * 0.12, a * 0.32]); }
    sh.moveTo(pts[0][0], pts[0][1]);
    pts.forEach(([x, y]) => sh.lineTo(x, y));
    for (let i = 12; i >= 0; i--) { const a = i / 12; sh.lineTo(0.05 + a * a * 0.12 + 0.01 * a, a * 0.32 + (i === 12 ? 0.03 : 0)); }
    sh.closePath();
    const eg = new THREE.ExtrudeGeometry(sh, { depth: W - 0.04, bevelEnabled: true, bevelThickness: 0.008, bevelSize: 0.008, bevelSegments: 2, curveSegments: 4 });
    eg.translate(0, 0, -(W - 0.04) / 2);
    wood.add(eg, tr(x1 - 0.07, H + top - 0.04, cz), [0.95, 0.95, 0.95], [3, 3]);
  }
  g.add(mesh(wood.build(), M.couch));
  // mattress (linen) and bolster
  const mat = mesh(roundedBox(L - 0.04, 0.12, W - 0.02, 0.045, 5), M.linen);
  mat.position.set(cx - 0.01, H + top + 0.04, cz);
  mat.geometry.attributes.uv.array.forEach((v, i, a) => (a[i] = v * 7));
  g.add(mat);
  const bol = mesh(roundedBox(0.30, 0.20, W - 0.06, 0.09, 5), M.madder);
  bol.position.set(x1 - 0.30, H + top + 0.15, cz); bol.rotation.z = 0.2;
  g.add(bol);
  // a folded throw hanging over the front edge at the foot end
  const throwG = new GB();
  throwG.add(roundedBox(0.55, 0.035, W + 0.02, 0.016, 3), tr(x0 + 0.42, H + top + 0.115, cz));
  throwG.add(roundedBox(0.55, 0.30, 0.03, 0.014, 3), tr(x0 + 0.42, H + top - 0.03, z1 + 0.025, -0.08, 0, 0));
  g.add(mesh(throwG.build(), M.madder));
  // stool (diphros) at the front right, with a black-glaze kylix
  const st = new GB();
  const sx = 0.86, sz = 0.42, sh = 0.40, ss = 0.34;
  const sleg = lathe([[0.0, 0], [0.022, 0], [0.026, 0.05], [0.018, 0.12], [0.028, 0.22], [0.02, 0.32], [0.024, sh - 0.035], [0.0, sh - 0.035]], 14);
  for (const ox of [-1, 1]) for (const oz of [-1, 1]) st.add(sleg, tr(sx + ox * (ss / 2 - 0.03), H, sz + oz * (ss / 2 - 0.03)), tint(), [2, 1]);
  st.box(sx - ss / 2, sx + ss / 2, H + sh - 0.035, H + sh, sz - ss / 2, sz + ss / 2, { grain: 'x', tint: tint() });
  for (const oz of [-1, 1]) st.box(sx - ss / 2 + 0.03, sx + ss / 2 - 0.03, H + 0.13, H + 0.155, sz + oz * (ss / 2 - 0.03) - 0.01, sz + oz * (ss / 2 - 0.03) + 0.01, { grain: 'x', tint: tint() });
  g.add(mesh(st.build(), M.couch));
  const kylix = lathe([[0, 0], [0.04, 0], [0.042, 0.008], [0.012, 0.02], [0.01, 0.05], [0.03, 0.058], [0.085, 0.075], [0.105, 0.095], [0.1, 0.098], [0.08, 0.08], [0.0, 0.066]], 32);
  const cup = mesh(kylix, M.glaze); cup.position.set(sx - 0.03, H + sh, sz + 0.01);
  const band = mesh(new THREE.CylinderGeometry(0.0425, 0.0425, 0.006, 32, 1, true), M.terracotta); band.position.set(sx - 0.03, H + sh + 0.004, sz + 0.01);
  const handles = new GB();
  for (const s of [-1, 1]) handles.add(new THREE.TorusGeometry(0.022, 0.0045, 6, 14, Math.PI), tr(s * 0.105, 0.088, 0, Math.PI / 2, 0, s > 0 ? -Math.PI / 2 : Math.PI / 2));
  const hm = mesh(handles.build(), M.glaze); hm.position.copy(cup.position);
  g.add(cup, band, hm);
  plat.root.add(g);
  set.occluders.push(...g.children.slice(0, 4));
  return g;
}

// ------------------------------------------------------------------ base plate and plinth (the museum model's base)
function buildBase(M) {
  const { x0, x1, z0, z1, thick } = PLATE;
  const g = new THREE.Group(); g.name = 'base';
  const top = mesh(new THREE.PlaneGeometry(x1 - x0, z1 - z0, 1, 1).rotateX(-Math.PI / 2), M.plate, { shadow: false, receive: true });
  top.position.set((x0 + x1) / 2, 0, (z0 + z1) / 2);
  top.name = 'ground';
  const side = mesh(new THREE.BoxGeometry(x1 - x0, thick, z1 - z0), M.plateSide, { shadow: false, receive: true });
  side.position.set((x0 + x1) / 2, -thick / 2 - 0.002, (z0 + z1) / 2);
  const plinth = mesh(new THREE.BoxGeometry(x1 - x0 + 2.4, 30, z1 - z0 + 2.4), M.plinth, { shadow: false, receive: true });
  plinth.position.set((x0 + x1) / 2, -thick - 15, (z0 + z1) / 2);
  g.add(top, side, plinth);
  return g;
}

// soften the per-board tints: a white model reads by its edges and shadows, not by paint
function whiten(root) {
  root.traverse((o) => {
    const c = o.isMesh && o.geometry.attributes.color;
    if (!c || o.geometry.userData.whitened) return;
    o.geometry.userData.whitened = true;
    for (let i = 0; i < c.array.length; i++) c.array[i] = Math.min(1, 0.975 + (c.array[i] - 1) * 0.16);
    c.needsUpdate = true;
  });
}

export function buildSet(scene) {
  const M = mats();
  const set = { occluders: [], mats: M };
  const root = new THREE.Group(); root.name = 'set';
  root.add(buildSkene(M, set));
  set.leaves = buildDoors(M, set);
  set.leaves.forEach((l) => root.add(l.hinge));
  set.platform = buildPlatform(M, set);
  root.add(set.platform.root);
  set.tableau = buildTableau(M, set, set.platform);
  root.add(buildBase(M));
  whiten(root);
  scene.add(root);
  set.root = root;
  return set;
}
