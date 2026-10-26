// The showroom light: a soft house key with shadows, a neutral studio ambient (spherical harmonics,
// cheap in software WebGL), the analytic "visibility" term that keeps the skene interior and the ground
// under the platform dark, and the PROJECTOR: data drawn as light added to the lit white surface.
//
// Projection (after lemo-opuscar's white-model engine, rewritten for this scene):
//   colour x (0.42 + 0.58 * max(N . toProjector, 0)) x throw mask, scaled by albedo, never a texture on the mesh.
// Each surface is given a KIND when its material is patched:
//   0 model (skene, doors, platform, tableau)   1 base plate (the floor)   2 plinth   3 figure (cast)
// Figures receive only the projector's neutral black level: data colours land on the model, never on
// the people, so the plate stays identical whatever fills the character slots.
import * as THREE from 'three';
import { GEO } from './timeline.js';

export const OCC = {
  uDoorOpen: { value: 0 },                 // 0 shut .. 1 fully open
  uPlat: { value: new THREE.Vector3(0, 0, GEO.PLAT_Z_IN) },
};

const lin = (h) => new THREE.Color(h);
export const PAL = {
  meas: '#5cc8ff',      // layer palette 1: measurement (door, swing, roll) - cool
  evid: '#ffae45',      // layer palette 2: evidence (how sure) - warm; solid / lighter / hatched
  black: '#0a0e16',     // projector black level
};

export const PJ = {
  pjOn: { value: 0 }, pjPos: { value: new THREE.Vector3(5.5, 11.0, 15.0) },
  pjDoor: { value: 0 }, pjArcs: { value: 0 }, pjDoorA: { value: 0 }, pjPick: { value: 0 },
  pjLane: { value: 0 }, pjLaneDraw: { value: 0 }, pjFront: { value: GEO.PLAT_FRONT_IN }, pjLand: { value: 0 },
  pjEvA: { value: 0 }, pjEvI: { value: 0 }, pjEvR: { value: 0 }, pjFA: { value: 0 }, pjFI: { value: 0 }, pjFR: { value: 0 },
  cMeas: { value: lin(PAL.meas) }, cEvid: { value: lin(PAL.evid) }, cBlack: { value: lin(PAL.black) },
};

// house key: from the audience's front-left, high, so the boards and joints of the facade read
export const KEY_DIR = new THREE.Vector3(-0.52, 0.78, 0.62).normalize();
export const PLATE = { x0: -9.5, x1: 9.5, z0: -7.4, z1: 8.6, top: 0.0, thick: 0.45 };

const OCC_GLSL = /* glsl */ `
uniform float uDoorOpen;
uniform vec3 uPlat;
varying vec3 vOccWorld;
float occBox(vec2 p, vec2 c, vec2 h, float soft) {
  vec2 d = abs(p - c) - h;
  float o = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
  return 1.0 - smoothstep(-soft * 0.4, soft, o);
}
// fraction of the ambient light that reaches a point (1 = open room)
float skyVisibility(vec3 p, vec3 n) {
  float vis = 1.0;
  float inside = smoothstep(-0.02, -0.30, p.z) * (1.0 - smoothstep(5.9, 6.1, abs(p.x))) * step(p.z, 0.2) * step(-4.9, p.z) * (1.0 - step(5.05, p.y));
  if (inside > 0.0) {
    vec3 q = vec3(clamp(p.x, -1.4, 1.4), clamp(p.y, 0.0, 3.2), -0.1);
    vec3 dc = q - p;
    float d2 = dot(dc, dc) + 0.12;
    float cosT = max(0.0, -p.z - 0.1) / sqrt(d2);
    float sa = 8.96 * cosT / d2;
    float facing = clamp(dot(n, normalize(dc)) * 0.6 + 0.4, 0.0, 1.0);
    float doorVis = clamp(sa / 6.2832, 0.0, 0.85) * facing * uDoorOpen;
    vis = mix(1.0, 0.07 + doorVis, inside);
  }
  float under = occBox(p.xz, uPlat.xz, vec2(1.2, 0.8), 0.32) * (1.0 - smoothstep(0.05, 0.30, p.y));
  vis *= 1.0 - 0.72 * under;
  float crease = (1.0 - smoothstep(0.0, 0.9, p.z + p.y * 0.6)) * step(0.0, p.z) * (1.0 - smoothstep(5.8, 6.4, abs(p.x)));
  vis *= 1.0 - 0.30 * crease;
  return vis;
}
`;

const PROJ_GLSL = /* glsl */ `
uniform float pjOn, pjDoor, pjArcs, pjDoorA, pjPick, pjLane, pjLaneDraw, pjFront, pjLand;
uniform float pjEvA, pjEvI, pjEvR, pjFA, pjFI, pjFR;
uniform vec3 pjPos, cMeas, cEvid, cBlack;
float aaLine(float d, float w) { float fw = max(fwidth(d), 1e-5); return 1.0 - smoothstep(w, w + fw * 1.5, abs(d)); }
float inRange(float x, float a, float b, float s) { return smoothstep(a - s, a + s, x) * (1.0 - smoothstep(b - s, b + s, x)); }
float sdBox(vec2 p, vec2 c, vec2 h) { vec2 d = abs(p - c) - h; return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0); }
float dashes(float s, float period, float duty) { float fw = max(fwidth(s), 1e-5) * 1.5; float f = fract(s / period); return smoothstep(0.0, fw / period, f) * (1.0 - smoothstep(duty - fw / period, duty, f)); }

vec3 projLight(float kind, vec3 P, vec3 N) {
  float dirK = 0.42 + 0.58 * max(dot(N, normalize(pjPos - P)), 0.0);
  // the throw: the base plate and a little spill onto the plinth top
  float thr = 1.0 - smoothstep(0.0, 0.6, sdBox(P.xz, vec2(0.0, 0.6), vec2(9.5, 8.0)));
  vec3 c = cBlack;
  bool fig = kind > 2.5, floorK = kind > 0.5 && kind < 1.5, model = kind < 0.5;
  if (fig) return c * dirK * thr * pjOn;
  if (floorK) c += vec3(0.010, 0.015, 0.026) * (aaLine(fract(P.x + 0.5) - 0.5, 0.008) + aaLine(fract(P.z + 0.5) - 0.5, 0.008));

  // ---- 01 the door: a cool wash on the doorway, the opening outlined
  if (P.z > -0.32 && P.z < 0.7 && !floorK) {
    float wash = 1.0 - smoothstep(-0.05, 0.35, sdBox(P.xy, vec2(0.0, 1.85), vec2(1.85, 1.9)));
    float so = max(abs(P.x) - 1.4, P.y - 3.2);
    float edge = aaLine(so, 0.022) * step(-0.27, P.z) * step(P.z, 0.08);
    c += cMeas * (0.16 * wash + 1.25 * edge) * pjDoor;
  }
  // ---- 01b the leaves' sweep, drawn like a plan: two quadrants on the floor inside, growing with the angle
  if (floorK && P.z < -0.19 && pjArcs > 0.0) {
    for (int k = 0; k < 2; k++) {
      float s = k == 0 ? 1.0 : -1.0;
      vec2 v = P.xz - vec2(s * 1.4, -0.2);
      float r = length(v);
      float th = atan(-v.y, -s * v.x);                         // 0 = shut, PI/2 = fully open (inward)
      float inQ = smoothstep(-0.02, 0.0, th) * (1.0 - smoothstep(pjDoorA, pjDoorA + 0.02, th));
      float arc = aaLine(r - 1.4, 0.016) * inQ;
      float fill = (1.0 - smoothstep(1.38, 1.4, r)) * inQ;
      c += cMeas * (1.7 * arc + 0.22 * fill) * pjArcs;
    }
  }
  // ---- the waiting platform picked out inside the dark skene
  if (model && P.z < 0.2) {
    float onP = (1.0 - smoothstep(-0.05, 0.08, sdBox(P.xz, uPlat.xz, vec2(1.22, 0.82)))) * (1.0 - smoothstep(1.45, 1.6, P.y));
    c += cMeas * 0.55 * onP * pjPick;
  }
  // ---- 02 the roll: the lane on the floor, the target footprint, the facade line, a ruler every 0.5 m
  float zb = ${(GEO.PLAT_Z_IN - GEO.PLAT_D / 2).toFixed(4)}, zs = ${GEO.PLAT_FRONT_IN.toFixed(4)}, ze = ${(GEO.PLAT_FRONT_IN + GEO.ROLL).toFixed(4)};
  if (floorK && pjLane > 0.0) {
    float zDraw = mix(zb, ze + 0.02, pjLaneDraw);
    float alongL = step(P.z, zDraw) * step(zb - 0.02, P.z);
    float edges = aaLine(abs(P.x) - 1.2, 0.018) * alongL;
    float ahead = inRange(P.z, pjFront, ze, 0.02) * (1.0 - smoothstep(1.18, 1.2, abs(P.x)));
    float target = aaLine(sdBox(P.xz, vec2(0.0, ze - 0.8), vec2(1.2, 0.8)), 0.016) * dashes(P.x + P.z + 10.0, 0.16, 0.55);
    float facade = aaLine(P.z - 0.02, 0.02) * (1.0 - smoothstep(1.5, 1.52, abs(P.x)));
    float rz = P.z - zs, tick = aaLine(fract(rz / 0.5 + 0.5) - 0.5, 0.012 / 0.5 * 2.0) * inRange(rz, -0.01, 2.94, 0.005) * inRange(P.x, -1.42, -1.27, 0.005);
    float endTick = aaLine(P.z - ze, 0.014) * inRange(P.x, -1.55, -1.22, 0.005);
    float l = 1.5 * edges + 0.30 * ahead * pjLaneDraw + 1.2 * target * pjLaneDraw + 1.4 * facade * pjLaneDraw + 1.5 * (tick + endTick) * pjLaneDraw;
    l += pjLand * 2.2 * (1.0 - smoothstep(-0.02, 0.06, sdBox(P.xz, vec2(0.0, ze - 0.8), vec2(1.2, 0.8))));
    c += cMeas * l * pjLane * (1.0 - 0.75 * pjEvA);
  }
  // the platform's front edge carries the light front while it rolls
  if (model && pjLane > 0.0) {
    float onPlat = 1.0 - smoothstep(-0.02, 0.03, sdBox(P.xz, uPlat.xz, vec2(1.22, 0.82)));
    float front = onPlat * (1.0 - smoothstep(0.0, 0.05, pjFront - P.z)) * step(P.y, 0.31);
    c += cMeas * 1.1 * front * pjLane * (1.0 - pjEvR);
  }
  // ---- 03 how sure: [A] the rolling out (solid), [I] the wheels (lighter), [R1] the platform's size (hatched, dashed edge)
  if (floorK && pjEvA > 0.0) {
    // the lane outline in amber, and a solid arrow on the floor in front of the platform: "rolled out"
    float edge = aaLine(abs(P.x) - 1.2, 0.02) * inRange(P.z, zb, ze, 0.01);
    float shaft = (1.0 - smoothstep(0.11, 0.13, abs(P.x))) * inRange(P.z, ze + 0.22, ze + 0.95, 0.015);
    float hz = (P.z - (ze + 0.95)) / 0.5;                   // 0 at the head's base, 1 at the tip
    float head = step(0.0, hz) * (1.0 - smoothstep(0.98, 1.0, hz)) * (1.0 - smoothstep(-0.015, 0.015, abs(P.x) - 0.36 * (1.0 - hz)));
    c += cEvid * (0.9 * edge + 1.25 * max(shaft, head)) * (pjEvA + 1.2 * pjFA);
  }
  if (pjEvI > 0.0) {
    float wl = 0.0;
    for (int k = 0; k < 2; k++) {
      float zz = uPlat.z + (k == 0 ? -0.55 : 0.55);
      if (model) wl += (1.0 - smoothstep(0.12, 0.15, length(vec2(P.y - 0.12, P.z - zz)))) * inRange(abs(P.x), 1.07, 1.17, 0.01);
      if (floorK) wl += aaLine(length(vec2((abs(P.x) - 1.115) * 1.6, P.z - zz)) - 0.22, 0.014);
    }
    c += mix(cEvid, vec3(1.0), 0.45) * 0.85 * wl * (pjEvI + 1.2 * pjFI);
  }
  if (model && pjEvR > 0.0) {
    float sd = sdBox(P.xz, uPlat.xz, vec2(1.2, 0.8));
    float deck = (1.0 - smoothstep(-0.01, 0.025, sd)) * step(0.13, P.y) * step(P.y, 0.305);
    // band-limited diagonal hatch: a cosine stripe, sharpened, faded to its mean where it would alias
    float hu = (P.x - P.z + P.y) / 0.13, hfw = fwidth(hu);
    float hatch = mix(smoothstep(0.25, 0.75, 0.5 + 0.5 * cos(6.2832 * hu)), 0.45, clamp(hfw * 2.2 - 0.25, 0.0, 1.0));
    float top = step(0.295, P.y) * step(0.8, N.y);
    float dash = aaLine(sd + 0.03, 0.012) * top * dashes(P.x + P.z + 7.0, 0.14, 0.55);
    c += cEvid * (0.12 * deck + 0.55 * hatch * deck + 1.5 * dash) * (pjEvR + 1.2 * pjFR);
  }
  return c * dirK * thr * pjOn;
}
`;

// kind: 0 model, 1 base plate, 2 plinth, 3 figure (the default for anything a cast brings in)
export function patchMaterial(mat, kind = 3) {
  if (!mat || mat.userData.occPatched) return mat;
  if (!(mat.isMeshStandardMaterial || mat.isMeshPhysicalMaterial || mat.isMeshLambertMaterial || mat.isMeshPhongMaterial || mat.isMeshToonMaterial)) return mat;
  mat.userData.occPatched = true;
  const prev = mat.onBeforeCompile;
  mat.onBeforeCompile = (shader, renderer) => {
    if (prev) prev(shader, renderer);
    Object.assign(shader.uniforms, OCC, PJ);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vOccWorld;')
      .replace('#include <project_vertex>', `#include <project_vertex>
        vec4 occW = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          occW = instanceMatrix * occW;
        #endif
        vOccWorld = (modelMatrix * occW).xyz;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\n' + OCC_GLSL + PROJ_GLSL)
      .replace('#include <lights_fragment_end>', `
        {
          vec3 nW = normalize((vec4(normal, 0.0) * viewMatrix).xyz);
          float skyK = skyVisibility(vOccWorld, nW);
          irradiance *= skyK;
          iblIrradiance *= skyK;
          #if defined( RE_IndirectSpecular )
            radiance *= mix(skyK, 1.0, 0.15) * skyK;
          #endif
        }
        #include <lights_fragment_end>`)
      .replace('#include <opaque_fragment>', `
        {
          vec3 nW2 = normalize((vec4(normal, 0.0) * viewMatrix).xyz);
          outgoingLight += projLight(${kind.toFixed(1)}, vOccWorld, nW2) * mix(diffuseColor.rgb, vec3(1.0), 0.1) * 1.35;
        }
        #include <opaque_fragment>`);
  };
  const key = mat.customProgramCacheKey ? mat.customProgramCacheKey.bind(mat) : () => '';
  mat.customProgramCacheKey = () => key() + '|occwm' + kind;
  return mat;
}

// neutral studio ambient: bright soft top, mid-grey walls, a darker floor bounce (no warm cast on the white)
function studioRadiance(d) {
  const top = new THREE.Color('#f4f6f8'), wall = new THREE.Color('#9a9da2'), floor = new THREE.Color('#4a4b4e');
  const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  if (d.y >= 0) return wall.clone().lerp(top, sm(0.05, 0.9, d.y));
  return wall.clone().lerp(floor, sm(0, 0.5, -d.y));
}
export function makeLightProbe(intensity = 1.0) {
  const sh = new THREE.SphericalHarmonics3(), basis = new Array(9).fill(0);
  const N = 4096, d = new THREE.Vector3();
  for (let i = 0; i < N; i++) {
    const y = 1 - (2 * (i + 0.5)) / N, r = Math.sqrt(1 - y * y), phi = i * 2.399963229728653;
    d.set(Math.cos(phi) * r, y, Math.sin(phi) * r);
    const c = studioRadiance(d);
    THREE.SphericalHarmonics3.getBasisAt(d, basis);
    for (let k = 0; k < 9; k++) {
      sh.coefficients[k].x += c.r * basis[k] * (4 * Math.PI / N);
      sh.coefficients[k].y += c.g * basis[k] * (4 * Math.PI / N);
      sh.coefficients[k].z += c.b * basis[k] * (4 * Math.PI / N);
    }
  }
  const probe = new THREE.LightProbe(sh, intensity);
  probe.layers.enableAll();
  return probe;
}

export function makeKey(scene) {
  const key = new THREE.DirectionalLight('#fffaf3', 2.4);
  const target = new THREE.Object3D();
  target.position.set(0, 0, 0.5);
  key.target = target;
  key.position.copy(target.position).addScaledVector(KEY_DIR, 40);
  key.castShadow = true;
  key.shadow.mapSize.set(4096, 4096);
  const c = key.shadow.camera;
  c.left = -12; c.right = 12; c.top = 12; c.bottom = -12; c.near = 15; c.far = 70;
  key.shadow.bias = -0.0003;
  key.shadow.normalBias = 0.015;
  key.shadow.radius = 2.5;
  key.layers.enableAll(); target.layers.enableAll();
  scene.add(key, target);
  return key;
}

// the dark room behind the plinth: a soft radial falloff (part of the plate)
export function roomBackground() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 288;
  const g = c.getContext('2d'), gr = g.createRadialGradient(256, 120, 10, 256, 150, 330);
  gr.addColorStop(0, '#24272b'); gr.addColorStop(0.5, '#101113'); gr.addColorStop(1, '#040405');
  g.fillStyle = gr; g.fillRect(0, 0, 512, 288);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
