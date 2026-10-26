// Entry point. Exposes the deterministic contract:
//   await window.ready
//   await window.renderAt(t, {layer: 'all'|'plate'|'cast'|'matte', contactShadows, finish})
//   window.trackAt(t) -> JSON (camera + per-slot transforms and screen anchors)
// URL params: ?t=<sec> (render one frame, no animation loop) &layer= &style=clay|vase
//             &cast=<path to cast json> &render=1 (driven by render.mjs) &w= &h=
import * as THREE from 'three';
import { buildSet } from './set.js';
import { makeLightProbe, makeSun, OCC, FOG_COLOR } from './lighting.js';
import { Pipeline } from './pipeline.js';
import { cameraAt, doorAngle, platformZ, wheelAngle, rollDistance, GEO, FPS, DURATION } from './timeline.js';
import { buildOverlay, updateOverlay } from './overlay.js';
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
document.documentElement.style.setProperty('--ui', (H / 1080).toFixed(4));
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.shadowMap.autoUpdate = false;
renderer.toneMapping = THREE.AgXToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(FOG_COLOR, 70, 520);
const set = buildSet(scene);
scene.add(makeLightProbe(0.75));
const sun = makeSun(scene);
const camera = new THREE.PerspectiveCamera(33, W / H, 0.1, 1500);
const pipeline = new Pipeline(renderer, W, H);
OUTLINE_RES.value.set(W, H);
const overlay = buildOverlay(document.getElementById('overlay'));

let cast = null;
const base = new URL(CAST_URL, location.href);

function applyTime(t) {
  const a = doorAngle(t);
  for (const l of set.leaves) l.hinge.rotation.y = l.side > 0 ? -a : a;
  OCC.uDoorOpen.value = Math.sin(a);
  const pz = platformZ(t);
  set.platform.root.position.set(0, 0, pz);
  for (const w of set.platform.wheels) w.rotation.x = wheelAngle(t);
  OCC.uPlat.value.set(0, 0, pz);
  const c = cameraAt(t);
  camera.position.fromArray(c.position);
  camera.fov = c.fov; camera.aspect = W / H;
  camera.up.set(0, 1, 0);
  camera.lookAt(new THREE.Vector3(...c.target));
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  scene.updateMatrixWorld(true);
  if (cast) cast.apply(t, camera);
  return c;
}

function project(p) {
  const v = p.clone().project(camera);
  return [(v.x * 0.5 + 0.5) * W, (1 - (v.y * 0.5 + 0.5)) * H, v.z];
}

// platform box corners in overlay space (the overlay is laid out at 1920x1080 and scaled)
function platformCorners(t) {
  const pz = platformZ(t), pts = [], k = 1080 / H;
  for (const x of [-1.2, 1.2]) for (const y of [0.0, 0.30]) for (const z of [pz - 0.8, pz + 0.8]) {
    const p = project(new THREE.Vector3(x, y, z));
    pts.push([p[0] * k, p[1] * k]);
  }
  return pts;
}

const round = (v, n = 5) => +v.toFixed(n);
const arr = (a, n) => Array.from(a).map((v) => round(v, n));

function trackAt(t) {
  applyTime(t);
  const c = cameraAt(t);
  const out = {
    t: round(t, 6), frame: Math.round(t * FPS),
    image: { width: W, height: H, origin: 'top-left' },
    camera: {
      position: arr(camera.position.toArray(), 5), quaternion: arr(camera.quaternion.toArray(), 6),
      fov_deg: round(camera.fov, 5), aspect: round(camera.aspect, 6), near: camera.near, far: camera.far,
      focus_distance: round(c.focus, 4), aperture: round(c.aperture, 4),
    },
    props: {
      door_angle_deg: round(doorAngle(t) / DEG, 4), platform_center_z: round(platformZ(t), 5),
      roll_distance: round(rollDistance(t), 5), platform_front_edge_z: round(platformZ(t) + GEO.PLAT_D / 2, 5),
      wheel_angle_rad: round(wheelAngle(t), 5),
    },
    slots: {},
  };
  const boxes = occluderBoxes(t);
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
    const q = slot.root.quaternion;
    out.slots[slot.name] = {
      world: { position: arr(slot.root.position.toArray(), 5), quaternion: arr(q.toArray(), 6), yaw_deg: round(ev.root.yaw, 4) },
      pose: ev.label,
      anchors: { head: anchor(headCentre), pelvis: anchor(ev.J.pelvis.p), foot_l: anchor(footL), foot_r: anchor(footR) },
      bbox: clampBox(bb), bbox_unoccluded: clampBox(bbAll),
      visible_fraction: round(vis / pts.length, 4),
      joints: Object.fromEntries(Object.entries(ev.J).map(([k, j]) => [k, arr(toW(j.p).toArray(), 4)])),
    };
  }
  return out;
}

async function renderAt(t, opts = {}) {
  await ready;
  const layer = opts.layer || params.get('layer') || 'all';
  const tA = performance.now();
  const c = applyTime(t);
  if (opts.cameraOverride) {   // debugging only: look from elsewhere, same scene state
    const o = opts.cameraOverride;
    camera.position.fromArray(o.position); camera.fov = o.fov || camera.fov;
    camera.lookAt(new THREE.Vector3(...o.target)); camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
    c.aperture = 0;
  }
  await cast.prepare(t);
  const tB = performance.now();
  pipeline.render(scene, camera, cast.roots, {
    layer, contactShadows: !!opts.contactShadows, finish: opts.finish,
    frame: Math.round(t * FPS), dof: { focus: c.focus, aperture: c.aperture },
  });
  const ov = document.getElementById('overlay');
  ov.style.display = layer === 'all' && opts.overlay !== false ? 'block' : 'none';
  if (layer === 'all') updateOverlay(overlay, t, { platformCorners: platformCorners(t) });
  document.body.classList.toggle('transparent', layer === 'cast');
  let gpu = 0;
  if (opts.sync) {   // block until the GPU (SwiftShader) has finished, for honest timings
    const tC = performance.now();
    const gl = renderer.getContext(); const px = new Uint8Array(4);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    gpu = performance.now() - tC;
  }
  return { t, layer, cpu_pose_ms: tB - tA, submit_ms: performance.now() - tB - gpu, gpu_wait_ms: gpu };
}

const ready = (async () => {
  const json = await (await fetch(CAST_URL)).json();
  cast = new Cast(scene, json, base, { style: STYLE });
  await cast.load();
  await document.fonts.ready;
  // warm up every program once so the first measured frame is representative
  for (const layer of ['all', 'cast']) { applyTime(5); pipeline.render(scene, camera, cast.roots, { layer, dof: { focus: 8, aperture: 1 } }); }
  return true;
})();

window.ready = ready;
window.renderAt = renderAt;
window.trackAt = (t) => trackAt(t);
window.sceneInfo = { FPS, DURATION, W, H, slots: SLOT_NAMES };

if (!RENDER_MODE) {
  // interactive preview only: plays the timeline in real time
  ready.then(() => {
    const t0 = performance.now();
    const loop = async () => {
      const t = ((performance.now() - t0) / 1000) % DURATION;
      await renderAt(t);
      requestAnimationFrame(loop);
    };
    loop();
  });
} else if (params.has('t')) {
  ready.then(() => renderAt(+params.get('t')));
}
window.__dbg = { scene, renderer, sun, pipeline, camera, set, THREE, getCast: () => cast };
