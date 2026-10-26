// The set: wooden skene with its central double door, the ekkyklema with its
// tableau props, the beaten-earth orchestra, a hint of hillside seating, hills, sky.
// Everything here belongs to the "plate". Character slots live in cast.js.
import * as THREE from 'three';
import { GB, roundedBox, lathe, tr } from './geom.js';
import { GEO } from './timeline.js';
import { timberTextures, earthTextures, weaveTextures } from './textures.js';
import { patchMaterial, makeSky } from './lighting.js';
import { rng, fbm } from './util.js';

export const LAYER_SET = 1;

function std(o) { return patchMaterial(new THREE.MeshStandardMaterial(o)); }

function mats() {
  const tb = timberTextures(11, { dark: '#352b23', mid: '#5c4f43', light: '#857563', grey: '#7e7a75', weather: 0.6 });
  const tp = timberTextures(23, { dark: '#2f241b', mid: '#54412f', light: '#7a6650', grey: '#6e6862', weather: 0.4 });
  const td = timberTextures(37, { dark: '#7a5534', mid: '#b08458', light: '#d4b48c', grey: '#b0a593', weather: 0.18 });
  const tc = timberTextures(41, { dark: '#3a2416', mid: '#5e3c24', light: '#7e5a3a', grey: '#6a5a4c', weather: 0.05 });
  const earth = earthTextures(5);
  const linen = weaveTextures(3, '#e4d9c4');
  const madder = weaveTextures(4, '#9a4a36');
  const M = {};
  M.boards = std({ map: tb.map, normalMap: tb.normalMap, roughnessMap: tb.roughnessMap, vertexColors: true, roughness: 1, metalness: 0, envMapIntensity: 0.9 });
  M.timber = std({ map: tp.map, normalMap: tp.normalMap, roughnessMap: tp.roughnessMap, vertexColors: true, roughness: 1, envMapIntensity: 0.9 });
  M.deck = std({ map: td.map, normalMap: td.normalMap, roughnessMap: td.roughnessMap, vertexColors: true, roughness: 1, envMapIntensity: 0.9 });
  M.couch = std({ map: tc.map, normalMap: tc.normalMap, vertexColors: true, roughness: 0.55, envMapIntensity: 1.0 });
  M.iron = std({ color: '#2a2724', roughness: 0.5, metalness: 0.75, envMapIntensity: 1.1 });
  M.backing = std({ color: '#2a1d14', roughness: 1 });
  M.earth = std({ map: earth.map, normalMap: earth.normalMap, normalScale: new THREE.Vector2(0.8, 0.8), vertexColors: true, roughness: 0.97, envMapIntensity: 0.8 });
  M.linen = std({ map: linen.map, normalMap: linen.normalMap, color: '#ffffff', roughness: 0.92, envMapIntensity: 0.8 });
  M.madder = std({ map: madder.map, normalMap: madder.normalMap, color: '#ffffff', roughness: 0.9, envMapIntensity: 0.8 });
  M.glaze = std({ color: '#141110', roughness: 0.22, metalness: 0.0, envMapIntensity: 1.3 });
  M.terracotta = std({ color: '#b5653a', roughness: 0.55, envMapIntensity: 1.0 });
  M.hills = new THREE.MeshLambertMaterial({ vertexColors: true });
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

// ------------------------------------------------------------------ ground, seating, hills
const FAN_C = new THREE.Vector2(0, 10.5);   // nominal centre of the bench fan (x, z)
const FAN_R0 = 12.5, ROW = 0.8, RISE = 0.42, ROWS = 22, FAN_A = 124 * Math.PI / 180;
function smoothstep01(x) { const t = Math.min(1, Math.max(0, x)); return t * t * (3 - 2 * t); }
export function terrainH(x, z) {
  const dx = x - FAN_C.x, dz = z - FAN_C.y, rr = Math.hypot(dx, dz);
  const ang = Math.abs(Math.atan2(dx, dz));          // 0 = straight up the auditorium axis
  let h = 0;
  const inFan = 1 - Math.min(1, Math.max(0, (ang - FAN_A) / 0.35));
  if (rr > FAN_R0 - 0.6) {
    // terraced rows (one earth step per bench row), smoothing out above the top row
    const u = Math.min(rr - FAN_R0 + 0.6, ROWS * ROW + 4) / ROW;
    const step = Math.floor(u) + smoothstep01((u - Math.floor(u) - 0.72) / 0.28);
    const terr = u < ROWS + 0.5 ? step : u;
    h = terr * RISE * inFan;
  }
  // gentle undulation away from the orchestra
  const far = Math.min(1, Math.max(0, (Math.hypot(x, z - 3) - 16) / 30));
  h += (fbm(x * 0.03 + 50, z * 0.03 + 50, 9, 3, 1024) - 0.45) * 6 * far;
  if (z < -6) h -= Math.min(1, (-6 - z) / 20) * 2.0;
  return h;
}

function buildGround(M) {
  const S = 220, N = 220;
  const g = new THREE.PlaneGeometry(S, S, N, N);
  g.rotateX(-Math.PI / 2);
  const p = g.attributes.position, uv = g.attributes.uv, col = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) {
    // concentrate vertices near the theatre (nonlinear remap)
    let x = p.getX(i), z = p.getZ(i);
    const remap = (v) => Math.sign(v) * Math.pow(Math.abs(v) / (S / 2), 1.8) * (S / 2);
    x = remap(x); z = remap(z) + 4;
    const y = terrainH(x, z);
    p.setXYZ(i, x, y, z);
    uv.setXY(i, x / 4, -z / 4);
    const low = fbm(x * 0.08 + 7, z * 0.08 + 3, 3, 4, 4096);
    const slope = Math.min(1, Math.max(0, y / 3));
    const dist = Math.min(1, Math.hypot(x, z - 4) / 60);
    const orch = 1 - Math.min(1, Math.max(0, (Math.hypot(x - FAN_C.x, z - FAN_C.y + 1.5) - 7.5) / 4));
    let rC = 0.86 + 0.26 * low + 0.07 * orch, gC = 0.86 + 0.22 * low + 0.065 * orch, bC = 0.86 + 0.18 * low + 0.05 * orch;
    // the hillside: drier, slightly olive scrub
    rC *= 1 - 0.18 * slope; gC *= 1 - 0.06 * slope; bC *= 1 - 0.25 * slope;
    rC *= 1 - 0.1 * dist; bC *= 1 - 0.15 * dist;
    col[i * 3] = rC; col[i * 3 + 1] = gC; col[i * 3 + 2] = bC;
  }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  g.computeVertexNormals();
  const m = mesh(g, M.earth, { shadow: false, receive: true });
  m.name = 'ground';
  return m;
}

function buildSeating(M) {
  const b = new GB(), r = rng(808), tint = tintFn(r, 0.16, 0.06);
  for (let i = 0; i < ROWS; i++) {
    const rr = FAN_R0 + i * ROW + 0.48;   // middle of terrace i
    const segs = Math.max(6, Math.round(rr * 2 * FAN_A / 2.6));
    for (let k = 0; k < segs; k++) {
      const a0 = -FAN_A + (2 * FAN_A) * k / segs, a1 = -FAN_A + (2 * FAN_A) * (k + 1) / segs;
      const am = (a0 + a1) / 2;
      const len = 2 * rr * Math.sin((a1 - a0) / 2) - 0.03;
      const x = FAN_C.x + rr * Math.sin(am), z = FAN_C.y + rr * Math.cos(am);
      const y = terrainH(x, z);
      const m = tr(x, y, z, 0, am, 0);
      const tt = tint();
      b.box(-len / 2, len / 2, 0.38, 0.44, -0.22, 0.2, { grain: 'x', matrix: m, tint: tt, off: [r() * 9, r() * 9] });
      b.box(-len / 2, len / 2, -0.25, 0.38, 0.14, 0.2, { grain: 'x', matrix: m, tint: tt.map((v) => v * 0.82), off: [r() * 9, r() * 9] });
    }
  }
  const m = mesh(b.build(), M.timber, { shadow: false, receive: false });
  m.name = 'seating';
  // rubble retaining walls at the two wing ends, stepping up with the slope
  const w = new GB();
  for (const sgn of [-1, 1]) {
    const a = sgn * (FAN_A + 0.03);
    for (let rr = FAN_R0 - 0.4; rr < FAN_R0 + ROWS * ROW; rr += 0.8) {
      const x = FAN_C.x + rr * Math.sin(a), z = FAN_C.y + rr * Math.cos(a);
      const y = terrainH(FAN_C.x + (rr + 0.4) * Math.sin(a - sgn * 0.05), FAN_C.y + (rr + 0.4) * Math.cos(a - sgn * 0.05));
      w.box(-0.3, 0.3, -0.5, y + 0.55, -0.42, 0.42, { matrix: tr(x, 0, z, 0, a, 0), grain: 'y', tint: [0.9 + 0.1 * r(), 0.9, 0.88] });
    }
  }
  const wall = mesh(w.build(), new THREE.MeshStandardMaterial({ color: '#b3a48c', roughness: 1, vertexColors: true }), { shadow: false });
  patchMaterial(wall.material);
  const g = new THREE.Group(); g.add(m, wall);
  return g;
}

function buildHills(M) {
  const b = new GB(), r = rng(4242);
  // distant ridges to the south, east and west, in two layers of haze
  const ridge = (rad, h0, hv, seed, tintC, a0, a1) => {
    const n = 120, pos = [];
    const g = new THREE.BufferGeometry();
    const verts = [], cols = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const a = a0 + (a1 - a0) * i / n;
      const hh = h0 + hv * fbm(i * 0.06 + seed, seed * 0.3, seed, 4, 1024);
      const x = Math.sin(a) * rad, z = -Math.cos(a) * rad + 4;
      verts.push(x, -8, z, x, hh, z);
      cols.push(...tintC, ...tintC);
      if (i < n) { const k = i * 2; idx.push(k, k + 2, k + 1, k + 1, k + 2, k + 3); }
    }
    g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
    g.setIndex(idx); g.computeVertexNormals();
    return g;
  };
  const grp = new THREE.Group(); grp.name = 'hills';
  const mk = (geo, c) => { const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, fog: false, side: THREE.DoubleSide })); m.layers.enable(LAYER_SET); return m; };
  grp.add(mk(ridge(420, 8, 55, 3, [0.60, 0.66, 0.74], -2.2, 2.2)));
  grp.add(mk(ridge(260, 3, 24, 7, [0.52, 0.53, 0.47], -2.0, 2.0)));
  return grp;
}

// low trees in the far middle ground: clustered silvery olive canopies and slender cypresses
function buildTrees(M) {
  const b = new GB(), cy = new GB(), r = rng(999);
  const leaf = std({ color: '#ffffff', vertexColors: true, roughness: 0.95, envMapIntensity: 0.7 });
  const trunk = std({ color: '#4a3a2c', roughness: 1 });
  const blob = new THREE.IcosahedronGeometry(1, 2);
  const cypress = lathe([[0.0, 0], [0.38, 0.2], [0.55, 1.2], [0.5, 3.0], [0.32, 4.8], [0.12, 5.9], [0.0, 6.2]], 12);
  const tb = new GB();
  const spots = [];
  for (let i = 0; i < 46; i++) {
    const a = (r() - 0.5) * 2.4, d = 18 + r() * 40;
    const x = Math.sin(a) * d * 1.4, z = -Math.cos(a) * d - 2;
    if (Math.abs(x) < 9 && z > -9) continue;
    spots.push([x, z, r()]);
  }
  const olive = [0.11, 0.13, 0.065], dark = [0.035, 0.05, 0.028];   // linear (vertex colours)
  for (const [x, z, k] of spots) {
    const y = terrainH(x, z);
    if (k < 0.22) { cy.add(cypress, tr(x, y, z, 0, k * 10, 0, 0.8 + k * 1.2), dark); continue; }
    const s = 1.2 + k * 1.5;
    for (let j = 0; j < 5; j++) {
      const ox = (r() - 0.5) * 1.6 * s, oz = (r() - 0.5) * 1.4 * s, oy = 1.1 * s + r() * 0.6 * s;
      const sc = s * (0.55 + r() * 0.35);
      const m = new THREE.Matrix4().compose(new THREE.Vector3(x + ox, y + oy, z + oz), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, r() * 6, 0)), new THREE.Vector3(sc * 1.15, sc * 0.72, sc));
      const v = 0.85 + r() * 0.3;
      b.add(blob, m, olive.map((c) => c * v));
    }
    tb.add(new THREE.CylinderGeometry(0.12, 0.22, s * 1.2, 6), tr(x, y + s * 0.5, z, 0.08, 0, 0.1));
  }
  const g = new THREE.Group();
  g.add(mesh(b.build(), leaf, { shadow: false }), mesh(cy.build(), leaf, { shadow: false }), mesh(tb.build(), trunk, { shadow: false }));
  return g;
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
  root.add(buildGround(M));
  root.add(buildSeating(M));
  root.add(buildTrees(M));
  root.add(buildHills(M));
  const sky = makeSky(); sky.layers.enable(LAYER_SET);
  root.add(sky);
  scene.add(root);
  set.root = root;
  return set;
}
