// Character slots. cast.json gives each slot a motion track (shared timeline) and a
// representation. Motion -> canonical skeleton -> (any) representation.
// Changing a representation never touches motion, camera or set.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { fk, blendPoses, POSES, JOINT_NAMES, BONES, REST } from './skeleton.js';
import { StandIn } from './standin.js';
import { GEO, platformZ, doorAngle } from './timeline.js';
import { clamp, DEG, lerp, smoothstep, smootherstep } from './util.js';
import { patchMaterial } from './lighting.js';

export const SLOT_NAMES = ['standing_actor', 'reclining_figure', 'stagehand_1', 'stagehand_2'];
const BASE_HEIGHT = 1.76;

// ------------------------------------------------------------------ motion
function resolvePos(key, t) {
  const p = key.pos;
  if (key.space === 'platform') return [p[0], p[1] + GEO.PLAT_H * 0, p[2] + platformZ(t)];
  return p;
}
const EASE = { linear: (u) => u, inout: (u) => smootherstep(0, 1, u), in: (u) => u * u, out: (u) => 1 - (1 - u) * (1 - u), smooth: (u) => smoothstep(0, 1, u) };

export function rootAt(motion, t) {
  const K = motion.root;
  if (t <= K[0].t || K.length === 1) return { pos: resolvePos(K[0], t), yaw: K[0].yaw || 0 };
  const last = K[K.length - 1];
  if (t >= last.t) return { pos: resolvePos(last, t), yaw: last.yaw || 0 };
  let i = 0;
  while (t >= K[i + 1].t) i++;
  const a = K[i], b = K[i + 1];
  const e = (EASE[b.ease || 'inout'])(clamp((t - a.t) / (b.t - a.t)));
  const pa = resolvePos(a, t), pb = resolvePos(b, t);
  return { pos: pa.map((v, j) => lerp(v, pb[j], e)), yaw: lerp(a.yaw || 0, b.yaw || 0, e) };
}

function poseAt(motion, t) {
  const seq = motion.poses;
  let cur = blendPoses([[seq[0].pose, 1]]);
  let label = { pose: seq[0].pose, from: null, w: 1 };
  for (let i = 1; i < seq.length; i++) {
    const k = seq[i];
    if (t < k.t) break;
    const w = smootherstep(k.t, k.t + (k.blend ?? 0.6), t);
    cur = blendPoses([[cur, 1 - w], [k.pose, w]]);
    label = { pose: k.pose, from: seq[i - 1].pose, w: +w.toFixed(4) };
  }
  return { pose: cur, label };
}

// distance walked along the root path from 0 to t (fixed-step, deterministic)
function walked(motion, t) {
  const dt = 1 / 96;
  let d = 0, prev = rootAt(motion, 0).pos;
  for (let s = dt; s <= t + 1e-9; s += dt) {
    const p = rootAt(motion, Math.min(s, t)).pos;
    d += Math.hypot(p[0] - prev[0], p[2] - prev[2]);
    prev = p;
  }
  return d;
}

export function evaluateSlot(spec, t) {
  const m = spec.motion;
  const root = rootAt(m, t);
  const { pose, label } = poseAt(m, t);
  // procedural layers (all functions of t only)
  const ph = spec.phase || 0;
  const br = (m.breath ?? 1) * Math.sin((t / 4.2) * 2 * Math.PI + ph);
  pose.chest[0] -= 0.8 * br; pose.spine[0] -= 0.4 * br;
  pose.shoulder_l[2] += 0.5 * br; pose.shoulder_r[2] -= 0.5 * br;
  if (m.sway) {
    pose.root.rot[2] += m.sway * Math.sin((t / 5.3) * 2 * Math.PI + ph * 1.7);
    pose.head[1] += m.sway * 1.5 * Math.sin((t / 6.1) * 2 * Math.PI + ph);
  }
  if (m.gait) {
    const g = m.gait, dist = walked(m, t);
    const p0 = rootAt(m, Math.max(0, t - 0.05)).pos, p1 = rootAt(m, t + 0.05).pos;
    const speed = Math.hypot(p1[0] - p0[0], p1[2] - p0[2]) / 0.1;
    const amp = smoothstep(0.03, 0.25, speed);
    const phase = (dist / g.stride) * Math.PI * 2;
    const s = Math.sin(phase), c = Math.cos(phase);
    if (pose.ik.foot_l && pose.ik.foot_r) {
      const half = g.stride * 0.25 * amp;
      pose.ik.foot_l.t[2] += half * s; pose.ik.foot_r.t[2] -= half * s;
      pose.ik.foot_l.t[1] += amp * 0.06 * Math.max(0, c); pose.ik.foot_r.t[1] += amp * 0.06 * Math.max(0, -c);
    } else {
      pose.hip_l[0] += amp * g.swing * s; pose.hip_r[0] -= amp * g.swing * s;
      pose.knee_l[0] += amp * g.knee * Math.max(0, c); pose.knee_r[0] += amp * g.knee * Math.max(0, -c);
    }
    pose.root.offset[1] += amp * 0.012 * Math.abs(c);
    pose.root.rot[1] += amp * 3 * s;
  }
  return { root, pose, label };
}

// ------------------------------------------------------------------ representations
class StandinRep {
  constructor(rep) { this.si = new StandIn(rep); this.object = this.si.group; }
  async load() {}
  update(J, s) { this.si.update(J, s); }
}

class GltfRep {
  constructor(rep, base) { this.rep = rep; this.base = base; this.object = new THREE.Group(); }
  async load() {
    const gltf = await new GLTFLoader().loadAsync(new URL(this.rep.src, this.base).href);
    const sc = SkeletonUtils.clone(gltf.scene);
    const r = this.rep;
    sc.scale.setScalar(r.scale ?? 1);
    if (r.offset) sc.position.fromArray(r.offset);
    if (r.rotation) sc.rotation.set(r.rotation[0] * DEG, r.rotation[1] * DEG, r.rotation[2] * DEG);
    sc.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = true; o.receiveShadow = true;
        const ms = Array.isArray(o.material) ? o.material : [o.material];
        ms.forEach((m) => patchMaterial(m));
        o.frustumCulled = false;
      }
    });
    this.object.add(sc);
    this.scene = sc;
    // optional: drive named bones from the canonical pose (rest-relative rotations)
    this.bones = {};
    if (r.bones) for (const [joint, bone] of Object.entries(r.bones)) {
      const b = sc.getObjectByName(bone);
      if (b) this.bones[joint] = { b, rest: b.quaternion.clone() };
    }
    // optional: sample an animation clip at the shared time
    if (r.clip && gltf.animations.length) {
      const clip = THREE.AnimationClip.findByName(gltf.animations, r.clip) || gltf.animations[0];
      this.mixer = new THREE.AnimationMixer(sc);
      this.action = this.mixer.clipAction(clip); this.action.play();
      this.clipLen = clip.duration;
    }
  }
  update(J, s, t, pose) {
    if (this.mixer) {
      const r = this.rep, lt = (t - (r.clipStart || 0)) * (r.clipSpeed ?? 1);
      this.mixer.setTime(r.clipLoop === false ? clamp(lt, 0, this.clipLen - 1e-4) : ((lt % this.clipLen) + this.clipLen) % this.clipLen);
    }
    // rest-relative local rotations from the solved canonical skeleton (FK + IK)
    for (const [joint, { b, rest }] of Object.entries(this.bones)) {
      if (!J[joint]) continue;
      b.quaternion.copy(rest).multiply(J[joint].local);
    }
  }
}

// camera-facing card (cylindrical billboard) with an image, an image sequence or a video
class CardRep {
  constructor(rep, base, slotHeight) {
    this.rep = rep; this.base = base; this.object = new THREE.Group(); this.h = rep.height || slotHeight;
  }
  async load() {
    const r = this.rep;
    if (r.type === 'video') {
      const v = document.createElement('video');
      v.src = new URL(r.src, this.base).href; v.muted = true; v.playsInline = true; v.preload = 'auto'; v.crossOrigin = 'anonymous';
      await new Promise((res, rej) => { v.onloadeddata = res; v.onerror = rej; v.load(); });
      v.width = v.videoWidth; v.height = v.videoHeight;   // the element size is 0 until set
      this.video = v;
      this.tex = new THREE.VideoTexture(v);
      this.tex.generateMipmaps = false;
      this.tex.minFilter = THREE.LinearFilter;
      this.aspect = v.videoWidth / v.videoHeight;
    } else {
      const loader = new THREE.TextureLoader();
      const srcs = [];
      if (r.frames) for (let i = 0; i < r.frames; i++) srcs.push(r.src.replace(/%0(\d)d/, (_, n) => String(i + (r.firstFrame || 0)).padStart(+n, '0')).replace('{frame}', String(i + (r.firstFrame || 0))));
      else srcs.push(r.src);
      this.texs = await Promise.all(srcs.map((s) => loader.loadAsync(new URL(s, this.base).href)));
      this.texs.forEach((t) => { t.colorSpace = THREE.SRGBColorSpace; });
      this.tex = this.texs[0];
      this.aspect = this.tex.image.width / this.tex.image.height;
    }
    this.tex.colorSpace = THREE.SRGBColorSpace;
    const opts = { map: this.tex, transparent: true, alphaTest: r.alphaTest ?? 0.02, side: THREE.DoubleSide, depthWrite: true };
    const mat = r.lit ? patchMaterial(new THREE.MeshStandardMaterial({ ...opts, roughness: 0.9 })) : new THREE.MeshBasicMaterial(opts);
    const anchor = r.anchor || [0.5, 0.0];      // image point that sits on the slot root
    const g = new THREE.PlaneGeometry(this.h * this.aspect, this.h);
    g.translate((0.5 - anchor[0]) * this.h * this.aspect, (0.5 - anchor[1]) * this.h, 0);
    this.card = new THREE.Mesh(g, mat);
    this.card.castShadow = r.castShadow ?? false;
    this.card.userData.castsShadow = r.castShadow ?? false;
    this.object.add(this.card);
  }
  async prepare(t) {
    const r = this.rep;
    if (this.video) {
      const target = clamp((t - (r.start || 0)) * (r.speed ?? 1), 0, this.video.duration - 1e-3);
      if (Math.abs(this.video.currentTime - target) > 1e-4) {
        await new Promise((res) => { this.video.onseeked = res; this.video.currentTime = target; });
      }
      this.tex.needsUpdate = true;
    } else if (this.texs && this.texs.length > 1) {
      const i = Math.floor((t - (r.start || 0)) * (r.fps || 24) + 1e-6);
      this.card.material.map = this.texs[clamp(i, 0, this.texs.length - 1)];
    }
  }
  update(J, s, t, pose, camera, slotRoot) {
    // face the camera around the vertical axis (the card stays upright)
    const wp = new THREE.Vector3(); slotRoot.getWorldPosition(wp);
    const yawWorld = Math.atan2(camera.position.x - wp.x, camera.position.z - wp.z);
    const slotYaw = new THREE.Euler().setFromQuaternion(slotRoot.quaternion, 'YXZ').y;
    this.object.rotation.set(0, yawWorld - slotYaw, 0);
  }
}

// ------------------------------------------------------------------ slots
class Slot {
  constructor(name, spec, base, styleOverride) {
    this.name = name; this.spec = spec;
    this.height = spec.height || BASE_HEIGHT;
    this.s = this.height / BASE_HEIGHT;
    this.root = new THREE.Group(); this.root.name = 'slot:' + name;
    const rep = { ...(spec.representation || { type: 'standin' }) };
    if (rep.type === 'standin' && styleOverride) rep.style = styleOverride;
    this.repSpec = rep;
    if (rep.type === 'standin') this.rep = new StandinRep(rep);
    else if (rep.type === 'gltf') this.rep = new GltfRep(rep, base);
    else if (rep.type === 'sprite' || rep.type === 'video') this.rep = new CardRep(rep, base, this.height);
    else throw new Error(`slot ${name}: unknown representation type ${rep.type}`);
    this.root.add(this.rep.object);
  }
  evaluate(t) {
    const ev = evaluateSlot(this.spec, t);
    ev.J = fk(ev.pose, this.s);
    return ev;
  }
  apply(t, camera) {
    const ev = this.evaluate(t);
    this.root.position.fromArray(ev.root.pos);
    this.root.rotation.set(0, ev.root.yaw * DEG, 0);
    this.root.updateMatrixWorld(true);
    this.rep.update(ev.J, this.s, t, ev.pose, camera, this.root);
    this.last = ev;
    return ev;
  }
}

export class Cast {
  constructor(scene, castJson, base, opts = {}) {
    this.scene = scene; this.json = castJson; this.base = base;
    this.slots = [];
    for (const name of SLOT_NAMES) {
      const spec = castJson.slots[name];
      if (!spec) continue;
      if (spec.enabled === false) continue;
      this.slots.push(new Slot(name, spec, base, opts.style));
    }
    this.group = new THREE.Group(); this.group.name = 'cast';
    this.slots.forEach((s) => this.group.add(s.root));
    scene.add(this.group);
  }
  async load() { await Promise.all(this.slots.map((s) => s.rep.load())); }
  async prepare(t) { for (const s of this.slots) if (s.rep.prepare) await s.rep.prepare(t); }
  apply(t, camera) { for (const s of this.slots) s.apply(t, camera); }
  get roots() { return [this.group]; }
}

// ------------------------------------------------------------------ tracking (representation-independent)
// Simple world-space occluder boxes for the set at time t (facade, door leaves,
// platform deck, couch, stool). Used only for anchor visibility in trackAt().
export function occluderBoxes(t) {
  const B = [];
  const box = (min, max, m) => B.push({ min, max, inv: m ? m.clone().invert() : null });
  const W = GEO.SKENE_W / 2, H = GEO.SKENE_H, dx = GEO.DOOR_W / 2;
  box([-W, 0, -0.25], [-dx, H, 0.04]);
  box([dx, 0, -0.25], [W, H, 0.04]);
  box([-dx - 0.5, GEO.DOOR_H, -0.25], [dx + 0.5, H, 0.04]);
  box([-W - 0.05, 0, -GEO.SKENE_D - 0.05], [-W + 0.15, H, 0]);
  box([W - 0.15, 0, -GEO.SKENE_D - 0.05], [W + 0.05, H, 0]);
  box([-W, 0, -GEO.SKENE_D - 0.05], [W, H, -GEO.SKENE_D + 0.15]);
  const a = doorAngle(t);
  for (const side of [1, -1]) {
    const m = new THREE.Matrix4().makeTranslation(side * dx, 0, -GEO.WALL_T).multiply(new THREE.Matrix4().makeRotationY(side > 0 ? -a : a));
    const x0 = side > 0 ? -dx : 0, x1 = side > 0 ? 0 : dx;
    box([x0, 0, 0], [x1, GEO.DOOR_H, GEO.LEAF_T], m);
  }
  const pz = platformZ(t);
  box([-1.2, 0.135, pz - 0.8], [1.2, 0.30, pz + 0.8]);
  box([-1.04, 0.62, pz - 0.52], [0.80, 0.84, pz + 0.28]);
  box([0.69, 0.66, pz + 0.25], [1.03, 0.70, pz + 0.59]);
  return B;
}

function rayBox(o, d, b, maxT) {
  let ox = o.x, oy = o.y, oz = o.z, dx = d.x, dy = d.y, dz = d.z;
  if (b.inv) {
    const O = new THREE.Vector3(ox, oy, oz).applyMatrix4(b.inv), D = new THREE.Vector3(dx, dy, dz).transformDirection(b.inv).multiplyScalar(d.length());
    ox = O.x; oy = O.y; oz = O.z; dx = D.x; dy = D.y; dz = D.z;
  }
  let t0 = 0, t1 = maxT;
  const o3 = [ox, oy, oz], d3 = [dx, dy, dz];
  for (let i = 0; i < 3; i++) {
    if (Math.abs(d3[i]) < 1e-12) { if (o3[i] < b.min[i] || o3[i] > b.max[i]) return false; continue; }
    let ta = (b.min[i] - o3[i]) / d3[i], tb = (b.max[i] - o3[i]) / d3[i];
    if (ta > tb) [ta, tb] = [tb, ta];
    t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
    if (t0 > t1) return false;
  }
  return true;
}

export function visible(cam, p, boxes) {
  const d = new THREE.Vector3().subVectors(p, cam);
  const L = d.length();
  d.divideScalar(L);
  if (p.y < -0.01) return false;
  for (const b of boxes) if (rayBox(cam, d, b, L - 0.015)) return false;
  return true;
}

// sample points over the canonical body (joints, bone segments, head)
export function bodySamples(J, s) {
  const pts = [];
  for (const [a, b] of BONES) for (let i = 0; i <= 4; i++) pts.push(new THREE.Vector3().lerpVectors(J[a].p, J[b].p, i / 4));
  const hc = new THREE.Vector3(0, 0.105 * s, 0.018 * s).applyQuaternion(J.head.q).add(J.head.p);
  for (const o of [[0, 0.13, 0], [0.1, 0, 0], [-0.1, 0, 0], [0, 0, 0.11], [0, 0, -0.1], [0, -0.11, 0.03]]) pts.push(new THREE.Vector3(...o).multiplyScalar(s).applyQuaternion(J.head.q).add(hc));
  return { pts, headCentre: hc };
}
