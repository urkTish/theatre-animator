// Canonical character skeleton, named poses and forward kinematics.
// Motion (cast.json) drives THIS skeleton; every representation (stand-in, glTF,
// sprite, video) follows it, and trackAt() reads anchors from it, so anchors are
// identical whatever fills the slot.
//
// Figure-local frame: root on the ground between the feet, facing +z, up +y,
// the figure's left = +x. Joint rotations are Euler XYZ in degrees:
//   x+ = bend forward (spine, neck, head) / swing limb backward (shoulder, hip)
//   x- = raise an arm or thigh forward, elbows flex with x-, knees flex with x+
//   z+ = left arm / left leg outward; right side mirrors with z-
//   y+ = turn toward the figure's left
import * as THREE from 'three';
import { DEG } from './util.js';

export const REST = {
  pelvis: [null, [0, 0.96, 0]],
  spine: ['pelvis', [0, 0.10, -0.012]],
  chest: ['spine', [0, 0.20, 0.0]],
  neck: ['chest', [0, 0.195, -0.012]],
  head: ['neck', [0, 0.095, 0.012]],
  shoulder_l: ['chest', [0.178, 0.150, -0.012]],
  elbow_l: ['shoulder_l', [0, -0.285, 0]],
  wrist_l: ['elbow_l', [0, -0.255, 0]],
  hand_l: ['wrist_l', [0, -0.165, 0.0]],
  shoulder_r: ['chest', [-0.178, 0.150, -0.012]],
  elbow_r: ['shoulder_r', [0, -0.285, 0]],
  wrist_r: ['elbow_r', [0, -0.255, 0]],
  hand_r: ['wrist_r', [0, -0.165, 0.0]],
  hip_l: ['pelvis', [0.090, -0.065, 0]],
  knee_l: ['hip_l', [0, -0.425, 0.005]],
  ankle_l: ['knee_l', [0, -0.395, -0.01]],
  toe_l: ['ankle_l', [0, -0.055, 0.15]],
  hip_r: ['pelvis', [-0.090, -0.065, 0]],
  knee_r: ['hip_r', [0, -0.425, 0.005]],
  ankle_r: ['knee_r', [0, -0.395, -0.01]],
  toe_r: ['ankle_r', [0, -0.055, 0.15]],
};
export const JOINT_NAMES = Object.keys(REST);
export const BONES = JOINT_NAMES.filter((n) => REST[n][0]).map((n) => [REST[n][0], n]);

// ------------------------------------------------------------------ pose library
// root: { offset: [x,y,z] (m, added to the pelvis rest position), rot: [x,y,z] (deg) }
export const POSES = {
  stand: {
    root: { offset: [0, 0, 0], rot: [0, 0, 0] },
    spine: [-2, 0, 0], chest: [-1, 0, 0], neck: [4, 0, 0], head: [2, 0, 0],
    shoulder_l: [2, 0, 5], elbow_l: [-10, 0, 0], shoulder_r: [2, 0, -5], elbow_r: [-10, 0, 0],
    hip_l: [0, 0, 2], knee_l: [2, 0, 0], ankle_l: [-2, 0, 0], hip_r: [0, 0, -2], knee_r: [2, 0, 0], ankle_r: [-2, 0, 0],
  },
  // Standing actor (root on the ground, figure faces +z). Waiting by the door,
  // weight on the right leg, hands loosely clasped, looking at the door.
  stand_wait: {
    root: { offset: [-0.015, -0.012, 0], rot: [0, -4, -2] },
    spine: [-1, 2, 1.5], chest: [-2, 3, 1], neck: [5, 0, 0], head: [2, 0, 0],
    wrist_l: [0, 0, -12], wrist_r: [0, 0, 12],
    ik: {
      hand_l: { t: [0.035, 0.965, 0.215], pole: [0.6, 1.15, -0.3] },
      hand_r: { t: [-0.025, 0.985, 0.235], pole: [-0.6, 1.15, -0.3] },
      foot_l: { t: [0.135, 0.075, 0.07], pole: [0.2, 0.5, 1.0] },
      foot_r: { t: [-0.095, 0.075, -0.02], pole: [-0.1, 0.5, 1.0] },
      look: { t: [-2.2, 1.55, 1.5], w: 0.55 },
    },
  },
  // the open gesture toward the reclining figure (to the actor's right-front)
  gesture: {
    root: { offset: [0.0, -0.014, 0.03], rot: [0, -8, 1] },
    spine: [1, -5, -1], chest: [3, -9, -1], neck: [4, 0, 0], head: [2, 0, 0],
    wrist_r: [-10, -80, 18], wrist_l: [0, 0, -8],
    ik: {
      hand_l: { t: [0.235, 0.94, 0.12], pole: [0.6, 1.2, -0.4] },
      hand_r: { t: [-0.42, 1.13, 0.37], pole: [-0.45, 0.6, -0.3] },
      foot_l: { t: [0.14, 0.075, 0.17], pole: [0.2, 0.5, 1.0] },
      foot_r: { t: [-0.10, 0.075, -0.05], pole: [-0.1, 0.5, 1.0] },
      look: { t: [-1.57, 1.2, 1.46], w: 0.9 },
    },
  },
  gesture_hold: {
    root: { offset: [0.0, -0.016, 0.035], rot: [0, -9, 1] },
    spine: [2, -6, -1], chest: [4, -10, -1], neck: [5, 0, 0], head: [3, 0, 0],
    wrist_r: [-12, -85, 20], wrist_l: [0, 0, -8],
    ik: {
      hand_l: { t: [0.235, 0.94, 0.12], pole: [0.6, 1.2, -0.4] },
      hand_r: { t: [-0.40, 1.10, 0.39], pole: [-0.45, 0.6, -0.3] },
      foot_l: { t: [0.14, 0.075, 0.17], pole: [0.2, 0.5, 1.0] },
      foot_r: { t: [-0.10, 0.075, -0.05], pole: [-0.1, 0.5, 1.0] },
      look: { t: [-1.57, 1.15, 1.46], w: 0.95 },
    },
  },
  // Reclining figure. Root = mattress top under the pelvis; x runs along the couch
  // toward the head end, z toward the audience. Propped on the left elbow (on the
  // bolster), right leg drawn up, right hand resting on the knee.
  recline: {
    root: { offset: [0, -0.83, 0], rot: [0, 0, -58] },
    spine: [0, 0, 12], chest: [4, 0, 14], neck: [0, 0, 2], head: [0, 0, 4],
    wrist_l: [0, 0, 0], wrist_r: [0, 0, 0],
    ik: {
      hand_l: { t: [0.56, 0.18, 0.09], pole: [0.52, 0.1, -0.45] },
      hand_r: { t: [-0.24, 0.46, 0.20], pole: [0.1, 0.9, -0.3] },
      foot_l: { t: [-0.88, 0.07, 0.02], pole: [-0.4, 0.1, 1.0] },
      foot_r: { t: [-0.63, 0.10, 0.17], pole: [-0.3, 0.8, 0.3] },
      look: { t: [0.8, 0.9, 3.0], w: 0.6 },
    },
  },
  // turns his head to the standing actor and lifts the right hand a little
  recline_turn: {
    root: { offset: [0, -0.83, 0], rot: [0, 0, -57] },
    spine: [0, 3, 13], chest: [4, 6, 15], neck: [0, 0, 2], head: [0, 0, 4],
    wrist_l: [0, 0, 0], wrist_r: [20, 40, 0],
    ik: {
      hand_l: { t: [0.56, 0.18, 0.09], pole: [0.52, 0.1, -0.45] },
      hand_r: { t: [-0.06, 0.50, 0.31], pole: [0.2, 0.2, -0.6] },
      foot_l: { t: [-0.88, 0.07, 0.02], pole: [-0.4, 0.1, 1.0] },
      foot_r: { t: [-0.63, 0.10, 0.17], pole: [-0.3, 0.8, 0.3] },
      look: { t: [2.54, 0.85, 0.81], w: 0.85 },
    },
  },
  // Stagehand (root on the ground, faces +z = the push direction): crouched low at
  // the rear rail, arms straight to the rail, one leg back.
  crouch_push: {
    root: { offset: [0, -0.45, 0.02], rot: [56, 0, 0] },
    spine: [6, 0, 0], chest: [4, 0, 0], neck: [-30, 0, 0], head: [-14, 0, 0],
    wrist_l: [-25, 0, 0], wrist_r: [-25, 0, 0],
    ik: {
      hand_l: { t: [0.17, 0.30, 0.47], pole: [0.45, 0.2, 0.1] },
      hand_r: { t: [-0.17, 0.30, 0.47], pole: [-0.45, 0.2, 0.1] },
      foot_l: { t: [0.13, 0.075, 0.12], pole: [0.15, 0.6, 1.0] },
      foot_r: { t: [-0.13, 0.075, -0.42], pole: [-0.15, 0.4, 1.0] },
    },
  },
  // let go, still crouched, slipping away sideways behind the wall
  crouch_low: {
    root: { offset: [0, -0.56, -0.02], rot: [48, 0, 0] },
    spine: [10, 0, 0], chest: [8, 0, 0], neck: [-14, 0, 0], head: [6, 0, 0],
    ik: {
      hand_l: { t: [0.20, 0.30, 0.36], pole: [0.5, 0.6, -0.2] },
      hand_r: { t: [-0.20, 0.30, 0.36], pole: [-0.5, 0.6, -0.2] },
      foot_l: { t: [0.15, 0.075, 0.14], pole: [0.2, 0.6, 1.0] },
      foot_r: { t: [-0.15, 0.075, -0.22], pole: [-0.2, 0.6, 1.0] },
    },
  },
};

const _e = new THREE.Euler(), _q = new THREE.Quaternion(), _v = new THREE.Vector3();
function rotQ(deg, out) {
  if (!deg) return out.identity();
  _e.set(deg[0] * DEG, deg[1] * DEG, deg[2] * DEG, 'XYZ');
  return out.setFromEuler(_e);
}

// linear blend of two (or more) poses, weights summing to 1
export function blendPoses(list) {
  const out = { root: { offset: [0, 0, 0], rot: [0, 0, 0] }, ik: {} };
  for (const n of JOINT_NAMES) if (n !== 'pelvis') out[n] = [0, 0, 0];
  const ikW = {};
  for (const [p, w] of list) {
    const pp = typeof p === 'string' ? POSES[p] : p;
    if (!pp) throw new Error('unknown pose ' + p);
    for (let i = 0; i < 3; i++) {
      out.root.offset[i] += w * ((pp.root && pp.root.offset[i]) || 0);
      out.root.rot[i] += w * ((pp.root && pp.root.rot[i]) || 0);
    }
    for (const n of JOINT_NAMES) if (n !== 'pelvis' && pp[n]) for (let i = 0; i < 3; i++) out[n][i] += w * pp[n][i];
    // IK targets / look-at: weighted average over the poses that define them
    for (const [k, v] of Object.entries(pp.ik || {})) {
      const o = (out.ik[k] ||= { t: [0, 0, 0], pole: [0, 0, 0], w: 0 });
      for (let i = 0; i < 3; i++) { o.t[i] += w * v.t[i]; o.pole[i] += w * (v.pole ? v.pole[i] : 0); }
      o.w += w * (v.w ?? 1);
      ikW[k] = (ikW[k] || 0) + w;
    }
  }
  for (const [k, o] of Object.entries(out.ik)) {
    const W = ikW[k] || 1;
    o.t = o.t.map((v) => v / W); o.pole = o.pole.map((v) => v / W); o.w /= W;
  }
  return out;
}

// limbs that IK can drive: end-effector name -> [upper joint, lower joint, end joint]
const CHAINS = {
  hand_l: ['shoulder_l', 'elbow_l', 'wrist_l'], hand_r: ['shoulder_r', 'elbow_r', 'wrist_r'],
  foot_l: ['hip_l', 'knee_l', 'ankle_l'], foot_r: ['hip_r', 'knee_r', 'ankle_r'],
};
const DOWN = new THREE.Vector3(0, -1, 0);

// forward kinematics in the figure-local frame. Returns {name: {p: Vector3, q: Quaternion}}
export function fk(pose, scale = 1) {
  const J = {};
  const ik = pose.ik || {};
  const solved = {};
  for (const n of JOINT_NAMES) {
    const [parent, off] = REST[n];
    const q = new THREE.Quaternion(), p = new THREE.Vector3();
    if (!parent) {
      p.set(off[0] * scale, off[1] * scale, off[2] * scale);
      const o = pose.root.offset;
      p.x += o[0] * scale; p.y += o[1] * scale; p.z += o[2] * scale;
      rotQ(pose.root.rot, q);
    } else {
      const P = J[parent];
      _v.set(off[0] * scale, off[1] * scale, off[2] * scale).applyQuaternion(P.q);
      p.copy(P.p).add(_v);
      if (solved[n]) q.copy(solved[n]);
      else q.copy(P.q).multiply(rotQ(pose[n], _q));
    }
    J[n] = { p, q };
    // two-bone IK: when the upper joint is placed, solve its chain toward the target
    for (const [eff, [a, b, c]] of Object.entries(CHAINS)) {
      if (n !== a || !ik[eff]) continue;
      const T = new THREE.Vector3(...ik[eff].t).multiplyScalar(scale);
      const pole = new THREE.Vector3(...ik[eff].pole).multiplyScalar(scale);
      const L1 = new THREE.Vector3(...REST[b][1]).length() * scale, L2 = new THREE.Vector3(...REST[c][1]).length() * scale;
      const S = p.clone();
      const st = T.clone().sub(S);
      const d = Math.min(Math.max(st.length(), Math.abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4);
      st.normalize();
      const x = (L1 * L1 - L2 * L2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, L1 * L1 - x * x));
      const pp = pole.clone().sub(S); pp.addScaledVector(st, -pp.dot(st));
      if (pp.lengthSq() < 1e-10) pp.set(0, 0, 1).addScaledVector(st, -st.z);
      pp.normalize();
      const E = S.clone().addScaledVector(st, x).addScaledVector(pp, h);
      const W = S.clone().addScaledVector(st, d);
      const u1 = E.clone().sub(S).normalize(), u2 = W.clone().sub(E).normalize();
      // upper bone: rotate the parent-carried frame so its -y follows the bone, keeping twist toward the pole
      const qa = new THREE.Quaternion().setFromUnitVectors(DOWN.clone().applyQuaternion(J[parent].q).normalize(), u1).multiply(J[parent].q);
      const qb = new THREE.Quaternion().setFromUnitVectors(u1, u2).multiply(qa);
      q.copy(qa);
      solved[b] = qb;
      // the end joint keeps its own local rotation on top of the lower bone
      solved[c] = qb.clone().multiply(rotQ(pose[c], new THREE.Quaternion()));
    }
    // look-at for the head: turn the face (+z) toward a target, blended over the neck
    if (n === 'head' && ik.look) {
      const T = new THREE.Vector3(...ik.look.t).multiplyScalar(scale);
      const hc = new THREE.Vector3(0, 0.1 * scale, 0).applyQuaternion(q).add(p);
      const want = T.sub(hc).normalize();
      const face = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
      const turn = new THREE.Quaternion().setFromUnitVectors(face, want);
      const w = Math.min(1, Math.max(0, ik.look.w ?? 1));
      const full = turn.multiply(q.clone());
      q.slerp(full, w);
    }
  }
  // local rotations (relative to the parent) for retargeting onto other rigs
  for (const n of JOINT_NAMES) {
    const par = REST[n][0];
    J[n].local = par ? J[par].q.clone().invert().multiply(J[n].q) : J[n].q.clone();
  }
  return J;
}
