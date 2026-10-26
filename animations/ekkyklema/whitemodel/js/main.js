// Entry point for the white-model film. Same deterministic contract as ../motion (plus the lemo-opuscar page globals):
//   await window.ready
//   await window.renderAt(t, {layer: 'all'|'plate'|'cast'|'matte', contactShadows, overlay})   t = film seconds
//   window.trackAt(t) -> JSON (camera + per-slot transforms and screen anchors), representation-independent
//   window.DUR, window.render(t), window.READY, window.EV (sound events), window.TEXTS(t) (reading-time check)
// URL params: ?t=<sec> &layer= &style=white|clay|vase (overrides every stand-in) &cast=<cast json> &render=1 &w= &h=
import * as THREE from 'three';
import { buildSet } from './set.js';
import { makeLightProbe, makeKey, roomBackground, OCC, PJ } from './lighting.js';
import { Pipeline } from './pipeline.js';
import { doorAngle, platformZ, wheelAngle, rollDistance, GEO } from './timeline.js';
import { FPS, DUR, OFFSET, F, cameraAt, lightAt } from './film.js';
import { makeOverlay, drawOverlay } from './overlay.js';
import { Cast, SLOT_NAMES, occluderBoxes, visible, bodySamples } from './cast.js';
import { DEG } from './util.js';
import { OUTLINE_RES } from './standin.js';

const params = new URLSearchParams(location.search);
const W = +params.get('w') || 1920, H = +params.get('h') || 1080;
const STYLE = params.get('style') || null;
const CAST_URL = params.get('cast') || 'cast.json';
const RENDER_MODE = params.has('render') || params.has('t');

const stage = document.getElementById('stage');
stage.style.width = W + 'px'; stage.style.height = H + 'px';
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.shadowMap.autoUpdate = false;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = roomBackground();
const set = buildSet(scene);
const probe = makeLightProbe(1.0); scene.add(probe);
const key = makeKey(scene);
const camera = new THREE.PerspectiveCamera(30, W / H, 0.1, 400);
const pipeline = new Pipeline(renderer, W, H);
OUTLINE_RES.value.set(W, H);
const ovCanvas = document.getElementById('ov');
const overlay = makeOverlay(ovCanvas, W, H);

let cast = null;
const base = new URL(CAST_URL, location.href);

function applyTime(t, withCast = true) {
  const ts = t - OFFSET;                              // scene time: the reused timeline (doors, roll, cast)
  const a = doorAngle(ts);
  for (const l of set.leaves) l.hinge.rotation.y = l.side > 0 ? -a : a;
  OCC.uDoorOpen.value = Math.sin(a);
  const pz = platformZ(ts);
  set.platform.root.position.set(0, 0, pz);
  for (const w of set.platform.wheels) w.rotation.x = wheelAngle(ts);
  OCC.uPlat.value.set(0, 0, pz);
  // light: house key + studio ambient, then the projector
  const L = lightAt(t);
  key.intensity = 2.9 * L.house;
  probe.intensity = 0.72 * L.house + 0.03;
  PJ.pjOn.value = L.proj;
  PJ.pjDoor.value = L.door; PJ.pjArcs.value = L.arcs; PJ.pjDoorA.value = a; PJ.pjPick.value = L.pick;
  PJ.pjLane.value = L.lane; PJ.pjLaneDraw.value = L.laneDraw; PJ.pjFront.value = pz + GEO.PLAT_D / 2; PJ.pjLand.value = L.land;
  PJ.pjEvA.value = L.evA; PJ.pjEvI.value = L.evI; PJ.pjEvR.value = L.evR; PJ.pjFA.value = L.fA; PJ.pjFI.value = L.fI; PJ.pjFR.value = L.fR;
  // camera (film)
  const c = cameraAt(t);
  camera.position.fromArray(c.position);
  camera.fov = c.fov; camera.aspect = W / H;
  camera.up.set(0, 1, 0);
  camera.lookAt(new THREE.Vector3(...c.target));
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  scene.updateMatrixWorld(true);
  if (cast && withCast) cast.apply(ts, camera);
  return c;
}

function project(p) {
  const v = p.clone().project(camera);
  return [(v.x * 0.5 + 0.5) * W, (1 - (v.y * 0.5 + 0.5)) * H, v.z];
}
// overlay space (1920 x 1080 whatever the render size), null when behind the camera
const k1080 = 1920 / W;
const projectOv = (x, y, z) => { const v = new THREE.Vector3(x, y, z).project(camera); return v.z < 1 ? [(v.x * 0.5 + 0.5) * W * k1080, (1 - (v.y * 0.5 + 0.5)) * H * k1080] : null; };

const round = (v, n = 5) => +v.toFixed(n);
const arr = (a, n) => Array.from(a).map((v) => round(v, n));

function trackAt(t) {
  const c = applyTime(t);
  const ts = t - OFFSET;
  const out = {
    t: round(t, 6), frame: Math.round(t * FPS), scene_t: round(ts, 6),
    image: { width: W, height: H, origin: 'top-left' },
    camera: {
      position: arr(camera.position.toArray(), 5), quaternion: arr(camera.quaternion.toArray(), 6),
      fov_deg: round(camera.fov, 5), aspect: round(camera.aspect, 6), near: camera.near, far: camera.far,
      focus_distance: round(c.focus, 4), aperture: round(c.aperture, 4),
    },
    props: {
      door_angle_deg: round(doorAngle(ts) / DEG, 4), platform_center_z: round(platformZ(ts), 5),
      roll_distance: round(rollDistance(ts), 5), platform_front_edge_z: round(platformZ(ts) + GEO.PLAT_D / 2, 5),
      wheel_angle_rad: round(wheelAngle(ts), 5),
    },
    slots: {},
  };
  const boxes = occluderBoxes(ts);
  const cam = camera.position.clone();
  for (const slot of cast.slots) {
    const ev = slot.last;
    const M = slot.root.matrixWorld;
    const toW = (p) => p.clone().applyMatrix4(M);
    const { pts, headCentre } = bodySamples(ev.J, slot.s);
    const anchor = (p) => {
      const w = toW(p), s = project(w);
      return { world: arr(w.toArray(), 4), screen: [round(s[0], 2), round(s[1], 2)], visible: visible(cam, w, boxes) && Math.abs(s[2]) < 1 };
    };
    const footL = new THREE.Vector3().lerpVectors(ev.J.ankle_l.p, ev.J.toe_l.p, 0.5);
    const footR = new THREE.Vector3().lerpVectors(ev.J.ankle_r.p, ev.J.toe_r.p, 0.5);
    let vis = 0, bb = null, bbAll = null;
    const pad = 0.09 * slot.s;
    for (const p of pts) {
      const w = toW(p), s = project(w);
      const d = w.distanceTo(cam), rpx = pad / (d * Math.tan(camera.fov * DEG / 2)) * (H / 2);
      const grow = (b) => (b ? [Math.min(b[0], s[0] - rpx), Math.min(b[1], s[1] - rpx), Math.max(b[2], s[0] + rpx), Math.max(b[3], s[1] + rpx)] : [s[0] - rpx, s[1] - rpx, s[0] + rpx, s[1] + rpx]);
      bbAll = grow(bbAll);
      if (visible(cam, w, boxes)) { vis++; bb = grow(bb); }
    }
    const clampBox = (b) => (b ? [round(Math.max(0, b[0]), 1), round(Math.max(0, b[1]), 1), round(Math.min(W, b[2]), 1), round(Math.min(H, b[3]), 1)] : null);
    out.slots[slot.name] = {
      world: { position: arr(slot.root.position.toArray(), 5), quaternion: arr(slot.root.quaternion.toArray(), 6), yaw_deg: round(ev.root.yaw, 4) },
      pose: ev.label,
      anchors: { head: anchor(headCentre), pelvis: anchor(ev.J.pelvis.p), foot_l: anchor(footL), foot_r: anchor(footR) },
      bbox: clampBox(bb), bbox_unoccluded: clampBox(bbAll),
      visible_fraction: round(vis / pts.length, 4),
      joints: Object.fromEntries(Object.entries(ev.J).map(([k, j]) => [k, arr(toW(j.p).toArray(), 4)])),
    };
  }
  return out;
}

let lastTexts = [];
async function renderAt(t, opts = {}) {
  await ready;
  const layer = opts.layer || params.get('layer') || 'all';
  const tA = performance.now();
  const c = applyTime(t);
  await cast.prepare(t - OFFSET);
  const tB = performance.now();
  pipeline.render(scene, camera, cast.roots, {
    layer, contactShadows: !!opts.contactShadows, finish: opts.finish,
    frame: Math.round(t * FPS), dof: { focus: c.focus, aperture: c.aperture },
  });
  const showOv = layer === 'all' && opts.overlay !== false;
  ovCanvas.style.display = showOv ? 'block' : 'none';
  if (showOv) lastTexts = drawOverlay(overlay, t, projectOv);
  document.body.classList.toggle('transparent', layer === 'cast');
  let gpu = 0;
  if (opts.sync) {
    const tC = performance.now();
    const gl = renderer.getContext(); const px = new Uint8Array(4);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    gpu = performance.now() - tC;
  }
  return { t, layer, cpu_pose_ms: tB - tA, submit_ms: performance.now() - tB - gpu, gpu_wait_ms: gpu };
}

// ------------------------------------------------------------------ sound events (window.EV), for mix.py
const EV = [];
const ev = (t, type, o = {}) => EV.push({ t: +t.toFixed(4), type, ...o });
ev(F.relay, 'relay'); ev(F.lamp, 'lamp'); ev(F.door, 'wash', { dur: 0.6 });
ev(F.dimW[0], 'tick'); ev(F.dimW[1], 'tickEnd'); ev(F.dimH[0], 'tick'); ev(F.dimH[1], 'tickEnd');
ev(F.doors[0], 'doors', { dur: F.doors[1] - F.doors[0] }); ev(F.doors[1], 'doorStop');
ev(F.pick, 'pick'); ev(F.lane, 'lane', { dur: 0.55 });
ev(F.roll[0], 'roll', { dur: F.roll[1] - F.roll[0], dist: GEO.ROLL, wheel_r: GEO.WHEEL_R });
ev(F.roll[1], 'land'); ev(F.evid, 'layer');
ev(F.pinA, 'pin', { code: 'A' }); ev(F.pinI, 'pin', { code: 'I' }); ev(F.pinR, 'pin', { code: 'R' });
ev(F.lightsUp, 'lights');
window.EV = EV;

const ready = (async () => {
  const json = await (await fetch(CAST_URL)).json();
  cast = new Cast(scene, json, base, { style: STYLE });
  await cast.load();
  await document.fonts.ready;
  await Promise.all(['200 20px IT', '400 20px IT', '400 20px PM', '500 20px PM', '400 20px Inter', '500 20px Inter', '600 20px Inter', '400 20px Didot', 'italic 400 20px Didot'].map((f) => document.fonts.load(f, 'Aaἐκκυκλεῖν0×')));
  for (const layer of ['all', 'cast']) { applyTime(8); pipeline.render(scene, camera, cast.roots, { layer, dof: { focus: 8, aperture: 1 } }); }
  return true;
})();

window.ready = ready;
window.renderAt = renderAt;
window.trackAt = (t) => trackAt(t);
window.sceneInfo = { FPS, DURATION: DUR, OFFSET, W, H, slots: SLOT_NAMES };
window.DUR = DUR;
window.render = (t) => renderAt(t, { layer: 'all' });
window.TEXTS = async (t) => { await renderAt(t, { layer: 'all' }); return lastTexts; };
// fast path for the reading-time check: camera, props and the 2D layer only (no WebGL, no figure meshing)
window.textsAt = (t) => { applyTime(t, false); return drawOverlay(overlay, t, projectOv); };
ready.then(() => { window.READY = true; });

if (!RENDER_MODE) {
  ready.then(() => {
    const t0 = performance.now();
    const loop = async () => { await renderAt(((performance.now() - t0) / 1000) % DUR); requestAnimationFrame(loop); };
    loop();
  });
} else if (params.has('t')) {
  ready.then(() => renderAt(+params.get('t')));
}
window.__dbg = { scene, renderer, key, pipeline, camera, set, THREE, getCast: () => cast };
