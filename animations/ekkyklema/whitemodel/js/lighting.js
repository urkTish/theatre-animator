// Sun, sky, environment and the analytic "sky visibility" term that darkens the
// skene interior and the ground under the platform. Every lit material in the scene
// (set and characters, including loaded glTF) goes through patchMaterial(), so a
// swapped-in character is lit exactly like the stand-in it replaces.
import * as THREE from 'three';
import { GEO } from './timeline.js';

export const OCC = {
  uDoorOpen: { value: 0 },                 // 0 shut .. 1 fully open
  uPlat: { value: new THREE.Vector3(0, 0, GEO.PLAT_Z_IN) },
};

// late-afternoon sun from the audience's front-right, raking across the facade
export const SUN_DIR = new THREE.Vector3(0.70, 0.33, 0.63).normalize();
export const SUN_COLOR = new THREE.Color('#ffd7a6');
export const SKY_TOP = new THREE.Color('#4a86c8');
export const SKY_HORIZON = new THREE.Color('#f3d9b5');
export const SKY_MID = new THREE.Color('#a9c6e2');
export const FOG_COLOR = new THREE.Color('#e9d8c2');

const OCC_GLSL = /* glsl */ `
uniform float uDoorOpen;
uniform vec3 uPlat;
varying vec3 vOccWorld;
float occBox(vec2 p, vec2 c, vec2 h, float soft) {
  vec2 d = abs(p - c) - h;
  float o = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
  return 1.0 - smoothstep(-soft * 0.4, soft, o);
}
// fraction of the sky/bounce light that reaches a point (1 = open air)
float skyVisibility(vec3 p, vec3 n) {
  float vis = 1.0;
  // inside the skene (behind the inner face of the facade)
  float inside = smoothstep(-0.02, -0.30, p.z) * (1.0 - smoothstep(5.9, 6.1, abs(p.x))) * step(p.z, 0.2) * step(-4.9, p.z) * (1.0 - step(5.05, p.y));
  if (inside > 0.0) {
    vec3 q = vec3(clamp(p.x, -1.4, 1.4), clamp(p.y, 0.0, 3.2), -0.1);
    vec3 dc = q - p;
    float d2 = dot(dc, dc) + 0.12;
    float cosT = max(0.0, -p.z - 0.1) / sqrt(d2) ;
    float sa = 8.96 * cosT / d2;                    // door area * cos / d^2 (steradians)
    float facing = clamp(dot(n, normalize(dc)) * 0.6 + 0.4, 0.0, 1.0);
    float doorVis = clamp(sa / 6.2832, 0.0, 0.85) * facing * uDoorOpen;
    vis = mix(1.0, 0.045 + doorVis, inside);
  }
  // ground and lower frame under the moving platform (2.4 x 1.6 m footprint)
  float under = occBox(p.xz, uPlat.xz, vec2(1.2, 0.8), 0.32) * (1.0 - smoothstep(0.05, 0.30, p.y));
  vis *= 1.0 - 0.72 * under;
  // a soft crease where the ground meets the facade, outside
  float crease = (1.0 - smoothstep(0.0, 0.9, p.z + p.y * 0.6)) * step(0.0, p.z) * (1.0 - smoothstep(5.8, 6.4, abs(p.x)));
  crease *= 1.0 - smoothstep(1.2, 1.7, abs(p.x)) * 0.0;
  vis *= 1.0 - 0.35 * crease;
  return vis;
}
`;

export function patchMaterial(mat) {
  if (!mat || mat.userData.occPatched) return mat;
  if (!(mat.isMeshStandardMaterial || mat.isMeshPhysicalMaterial || mat.isMeshLambertMaterial || mat.isMeshPhongMaterial || mat.isMeshToonMaterial)) return mat;
  mat.userData.occPatched = true;
  const prev = mat.onBeforeCompile;
  mat.onBeforeCompile = (shader, renderer) => {
    if (prev) prev(shader, renderer);
    shader.uniforms.uDoorOpen = OCC.uDoorOpen;
    shader.uniforms.uPlat = OCC.uPlat;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vOccWorld;')
      .replace('#include <project_vertex>', `#include <project_vertex>
        vec4 occW = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          occW = instanceMatrix * occW;
        #endif
        vOccWorld = (modelMatrix * occW).xyz;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\n' + OCC_GLSL)
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
        #include <lights_fragment_end>`);
  };
  const key = mat.customProgramCacheKey ? mat.customProgramCacheKey.bind(mat) : () => '';
  mat.customProgramCacheKey = () => key() + '|occ1';
  return mat;
}

// sky dome: warm haze at the horizon, soft blue overhead, a glow around the sun
export function makeSky() {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: SKY_TOP }, mid: { value: SKY_MID }, hor: { value: SKY_HORIZON }, sun: { value: SUN_DIR }, sunCol: { value: SUN_COLOR } },
    vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position.z = gl_Position.w; }`,
    fragmentShader: `uniform vec3 top, mid, hor, sun, sunCol; varying vec3 vDir;
      void main(){
        vec3 d = normalize(vDir);
        float h = clamp(d.y, -0.2, 1.0);
        vec3 c = mix(hor, mid, smoothstep(0.0, 0.16, h));
        c = mix(c, top, smoothstep(0.12, 0.85, h));
        float s = max(dot(d, sun), 0.0);
        c += sunCol * (pow(s, 6.0) * 0.35 + pow(s, 64.0) * 0.6);
        // a few soft, high streaks of cloud, lit warm on the sun side
        vec2 uv = d.xz / max(d.y + 0.12, 0.05);
        float n = 0.0, a = 0.5;
        vec2 q = uv * 0.35 + vec2(3.1, 1.7);
        for (int i = 0; i < 4; i++) { n += a * (0.5 + 0.5 * sin(q.x * 1.7 + sin(q.y * 2.3)) * sin(q.y * 1.3 + sin(q.x * 1.1))); q = q * 2.03 + vec2(1.3, 0.7); a *= 0.5; }
        float cl = smoothstep(0.52, 0.78, n) * smoothstep(0.02, 0.25, d.y) * (1.0 - smoothstep(0.55, 0.9, d.y));
        c = mix(c, mix(vec3(1.0, 0.93, 0.84), sunCol, 0.25 * s) * 1.05, cl * 0.55);
        c = mix(c, hor * 0.95, smoothstep(0.02, -0.15, d.y));
        gl_FragColor = vec4(c * 1.15, 1.0);
      }`,
  });
  const m = new THREE.Mesh(new THREE.SphereGeometry(900, 48, 24), mat);
  m.frustumCulled = false;
  m.renderOrder = -10;
  return m;
}

// Ambient light as 3rd-order spherical harmonics projected from the same sky
// (plus warm bounce from the sunlit earth below the horizon). Far cheaper than a
// PMREM environment in software WebGL, and identical for every material.
function skyRadiance(d) {
  if (d.y >= 0) {
    const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
    const c = SKY_HORIZON.clone().lerp(SKY_MID, sm(0, 0.16, d.y)).lerp(SKY_TOP, sm(0.12, 0.85, d.y));
    const s = Math.max(0, d.dot(SUN_DIR));
    const k = Math.pow(s, 6) * 0.35;
    c.r += SUN_COLOR.r * k; c.g += SUN_COLOR.g * k; c.b += SUN_COLOR.b * k;
    return c.multiplyScalar(1.15);
  }
  const k = Math.min(1, -d.y * 6);
  const ground = new THREE.Color('#a08a70').multiplyScalar(0.5);
  return SKY_HORIZON.clone().multiplyScalar(0.8).lerp(ground, k);
}
export function makeLightProbe(intensity = 1.0) {
  const sh = new THREE.SphericalHarmonics3(), basis = new Array(9).fill(0);
  const N = 4096, d = new THREE.Vector3();
  for (let i = 0; i < N; i++) {
    const y = 1 - (2 * (i + 0.5)) / N, r = Math.sqrt(1 - y * y), phi = i * 2.399963229728653;
    d.set(Math.cos(phi) * r, y, Math.sin(phi) * r);
    const c = skyRadiance(d);
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

// (unused by default) prefiltered PMREM environment, for GPU renders where it is affordable
export function makeEnvironment(renderer) {
  const scene = new THREE.Scene();
  const sky = makeSky();
  sky.scale.setScalar(0.05);
  scene.add(sky);
  // warm bounce from the sunlit earth below the horizon
  const ground = new THREE.Mesh(new THREE.CircleGeometry(40, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color('#9a7a58').multiplyScalar(0.9), side: THREE.DoubleSide }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -2;
  scene.add(ground);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const rt = pmrem.fromScene(scene, 0.0, 0.1, 100);
  pmrem.dispose();
  return rt.texture;
}

export function makeSun(scene) {
  const sun = new THREE.DirectionalLight(SUN_COLOR, 3.6);
  const target = new THREE.Object3D();
  target.position.set(0.5, 0, 0.5);
  sun.target = target;
  sun.position.copy(target.position).addScaledVector(SUN_DIR, 40);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  const c = sun.shadow.camera;
  c.left = -11; c.right = 11; c.top = 9; c.bottom = -9; c.near = 10; c.far = 80;
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.015;
  sun.shadow.radius = 2.2;
  sun.layers.enableAll(); target.layers.enableAll();   // lights are filtered by camera layers
  scene.add(sun, target);
  return sun;
}
