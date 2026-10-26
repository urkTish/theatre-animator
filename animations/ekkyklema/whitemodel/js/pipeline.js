// Offscreen render pipeline shared by every layer:
//   scene -> HDR target (4x MSAA, depth texture)
//         -> screen-space ambient occlusion (half resolution, depth only)
//         -> depth of field (gather, driven by the camera's focus/aperture)
//         -> output: neutral tone map, grade, and (layer "all" only) a vignette.
// Layers: "all" | "plate" | "cast" | "matte". See README.md.
import * as THREE from 'three';
import { LAYER_SET } from './set.js';

export const LAYER_CAST = 2;

const VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const DEPTH_FN = `
uniform float cNear, cFar;
float viewZ(float d) { return (cNear * cFar) / ((cFar - cNear) * d - cFar); }   // negative in front
`;

const AO_FS = `
precision highp float;
varying vec2 vUv;
uniform sampler2D tDepth;
uniform vec2 texel;           // full-res texel size
uniform mat4 projInv;
uniform float projScale;      // pixels per metre at 1 m
uniform float radius, strength;
${DEPTH_FN}
vec3 viewPos(vec2 uv) {
  float d = texture2D(tDepth, uv).r;
  vec4 c = vec4(uv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
  vec4 v = projInv * c; return v.xyz / v.w;
}
void main() {
  float d0 = texture2D(tDepth, vUv).r;
  if (d0 >= 0.99999) { gl_FragColor = vec4(1.0); return; }
  vec3 p = viewPos(vUv);
  vec3 px1 = viewPos(vUv + vec2(texel.x, 0.0)) - p, px0 = p - viewPos(vUv - vec2(texel.x, 0.0));
  vec3 py1 = viewPos(vUv + vec2(0.0, texel.y)) - p, py0 = p - viewPos(vUv - vec2(0.0, texel.y));
  vec3 dx = abs(px1.z) < abs(px0.z) ? px1 : px0;
  vec3 dy = abs(py1.z) < abs(py0.z) ? py1 : py0;
  vec3 n = normalize(cross(dx, dy));
  float rpx = radius * projScale / -p.z;
  rpx = min(rpx, 90.0);
  float ao = 0.0;
  // fixed interleaved pattern (deterministic): golden-angle spiral rotated per 4x4 cell
  vec2 cell = mod(floor(gl_FragCoord.xy), 4.0);
  float rot = (cell.x * 4.0 + cell.y) * 0.3927;
  const int N = 12;
  for (int i = 0; i < N; i++) {
    float fi = float(i) + 0.5;
    float a = fi * 2.39996 + rot;
    float r = sqrt(fi / float(N)) * rpx;
    vec2 suv = vUv + vec2(cos(a), sin(a)) * r * texel;
    vec3 s = viewPos(suv);
    vec3 v = s - p;
    float l = length(v);
    float fall = 1.0 - smoothstep(radius * 0.5, radius, l);
    ao += max(0.0, dot(n, v / max(l, 1e-4)) - 0.08) * fall;
  }
  ao = 1.0 - strength * ao / float(N);
  gl_FragColor = vec4(vec3(clamp(ao, 0.0, 1.0)), 1.0);
}`;

const BLUR_FS = `
precision highp float;
varying vec2 vUv;
uniform sampler2D tAO, tDepth;
uniform vec2 dir;    // texel step
${DEPTH_FN}
void main() {
  float z0 = viewZ(texture2D(tDepth, vUv).r);
  float acc = 0.0, wsum = 0.0;
  for (int i = -4; i <= 4; i++) {
    vec2 uv = vUv + dir * float(i);
    float z = viewZ(texture2D(tDepth, uv).r);
    float w = exp(-float(i * i) / 10.0) * exp(-abs(z - z0) / (0.04 * -z0 + 0.02));
    acc += texture2D(tAO, uv).r * w; wsum += w;
  }
  gl_FragColor = vec4(vec3(acc / wsum), 1.0);
}`;

const COMBINE_FS = `
precision highp float;
varying vec2 vUv;
uniform sampler2D tColor, tAO;
uniform float aoMix;
void main() {
  vec4 c = texture2D(tColor, vUv);
  c.rgb *= mix(1.0, texture2D(tAO, vUv).r, aoMix);
  gl_FragColor = c;
}`;

const DOF_FS = `
precision highp float;
varying vec2 vUv;
uniform sampler2D tColor, tDepth;
uniform vec2 texel;
uniform float focus, cocScale, maxCoc;
${DEPTH_FN}
float coc(float z) { return min(maxCoc, cocScale * abs(z - focus) / z); }
vec4 shade(vec2 uv) { return texture2D(tColor, uv); }
void main() {
  float z0 = -viewZ(texture2D(tDepth, vUv).r);
  vec4 c0 = shade(vUv);
  float cc = coc(z0);
  vec4 acc = c0; float wsum = 1.0;
  const int N = 28;
  for (int i = 0; i < N; i++) {
    float fi = float(i) + 0.5;
    float r = sqrt(fi / float(N)) * maxCoc;
    float a = fi * 2.39996;
    vec2 uv = vUv + vec2(cos(a), sin(a)) * r * texel;
    float z = -viewZ(texture2D(tDepth, uv).r);
    float sc = coc(z);
    float w = smoothstep(r - 0.75, r + 0.75, sc);
    if (z > z0) w *= smoothstep(r - 0.75, r + 0.75, cc);
    acc += shade(uv) * w; wsum += w;
  }
  gl_FragColor = acc / wsum;
}`;

const OUT_FS = `
precision highp float;
varying vec2 vUv;
uniform sampler2D tColor;
uniform float mode;          // 0 all/plate, 1 cast (premultiplied alpha), 2 matte
uniform float finish;        // vignette + grain
uniform float seed;
uniform vec2 res;
float hash(vec2 p) { p = fract(p * vec2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
vec3 grade(vec3 c) {
  // neutral for a white model: a gentle S-curve, a cool near-black floor, no warm cast
  c = clamp(c, 0.0, 1.0);
  c = clamp((c - 0.012) / 0.988, 0.0, 1.0);
  c = mix(c, c * c * (3.0 - 2.0 * c), 0.22);
  c += vec3(-0.004, 0.0, 0.006) * (1.0 - smoothstep(0.02, 0.25, dot(c, vec3(0.2126, 0.7152, 0.0722))));
  return c;
}
void main() {
  vec4 src = texture2D(tColor, vUv);
  if (mode > 1.5) { float a = clamp(src.a, 0.0, 1.0); gl_FragColor = vec4(a, a, a, 1.0); return; }
  float a = mode > 0.5 ? clamp(src.a, 0.0, 1.0) : 1.0;
  vec3 c = mode > 0.5 ? (a > 0.0 ? src.rgb / a : vec3(0.0)) : src.rgb;
  #ifdef TONE_MAPPING
  c = toneMapping(c);
  #endif
  vec4 o = linearToOutputTexel(vec4(c, 1.0));
  c = grade(o.rgb);
  if (finish > 0.5) {
    vec2 q = vUv - 0.5; q.x *= res.x / res.y;
    float v = smoothstep(1.05, 0.25, length(q * vec2(0.92, 1.05)));
    c *= mix(0.62, 1.0, v);        // vignette only; grain is added in ffmpeg (mux.sh), so frames stay compressible
  }
  gl_FragColor = vec4(c * a, a);
}`;

export class Pipeline {
  constructor(renderer, w, h) {
    this.r = renderer; this.w = w; this.h = h;
    const depth = new THREE.DepthTexture(w, h);
    depth.type = THREE.FloatType;
    this.rt = new THREE.WebGLRenderTarget(w, h, { type: THREE.HalfFloatType, samples: 4, depthTexture: depth, depthBuffer: true });
    const hw = Math.ceil(w / 2), hh = Math.ceil(h / 2);
    const lin = { type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false };
    this.aoA = new THREE.WebGLRenderTarget(hw, hh, lin);
    this.aoB = new THREE.WebGLRenderTarget(hw, hh, lin);
    this.dof = new THREE.WebGLRenderTarget(w, h, lin);
    this.comb = new THREE.WebGLRenderTarget(w, h, lin);
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    quad.frustumCulled = false;
    this.quadScene = new THREE.Scene(); this.quadScene.add(quad); this.quad = quad;
    this.quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const U = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, { value: v }]));
    this.mAO = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: AO_FS, uniforms: U({ tDepth: depth, texel: new THREE.Vector2(1 / w, 1 / h), projInv: new THREE.Matrix4(), projScale: 1, radius: 0.5, strength: 1.6, cNear: 0.1, cFar: 100 }), depthTest: false, depthWrite: false });
    this.mBlur = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: BLUR_FS, uniforms: U({ tAO: null, tDepth: depth, dir: new THREE.Vector2(), cNear: 0.1, cFar: 100 }), depthTest: false, depthWrite: false });
    this.mComb = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: COMBINE_FS, uniforms: U({ tColor: this.rt.texture, tAO: this.aoA.texture, aoMix: 0.75 }), depthTest: false, depthWrite: false });
    this.mDOF = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: DOF_FS, uniforms: U({ tColor: this.comb.texture, tDepth: depth, texel: new THREE.Vector2(1 / w, 1 / h), focus: 8, cocScale: 0, maxCoc: 0, cNear: 0.1, cFar: 100 }), depthTest: false, depthWrite: false });
    this.mOut = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: OUT_FS, uniforms: U({ tColor: this.dof.texture, mode: 0, finish: 1, seed: 0, res: new THREE.Vector2(w, h) }), depthTest: false, depthWrite: false, toneMapped: true });
    this.depthOnly = new THREE.MeshBasicMaterial({ colorWrite: false });
  }

  pass(mat, target) {
    this.quad.material = mat;
    this.r.setRenderTarget(target);
    this.r.render(this.quadScene, this.quadCam);
  }

  // cast: the character group(s); opts: {layer, contactShadows, finish, frame, dof:{focus, aperture}}
  render(scene, camera, castRoots, opts) {
    const r = this.r, layer = opts.layer || 'all';
    const castShadowsInPlate = !!opts.contactShadows;
    // character visibility to the shadow camera (layer 0) and main camera (LAYER_CAST)
    for (const c of castRoots) c.traverse((o) => {
      if (!o.isMesh && !o.isSprite) return;
      o.layers.disableAll();
      o.layers.enable(LAYER_CAST);
      const shadowOn = layer !== 'plate' || castShadowsInPlate;
      if (shadowOn && o.userData.castsShadow !== false) o.layers.enable(0);
    });
    r.shadowMap.needsUpdate = true;
    r.setRenderTarget(this.rt);
    const cam = camera;
    if (layer === 'all' || layer === 'plate') {
      cam.layers.disableAll(); cam.layers.enable(LAYER_SET);
      if (layer === 'all') cam.layers.enable(LAYER_CAST);
      r.setClearColor(0x000000, 1); r.clear(true, true, true);
      r.render(scene, cam);
    } else {
      // set as depth only (it occludes), then the characters, on transparent black
      r.setClearColor(0x000000, 0); r.clear(true, true, true);
      cam.layers.disableAll(); cam.layers.enable(LAYER_SET);
      const bg = scene.background; scene.background = null;
      scene.overrideMaterial = this.depthOnly;
      r.render(scene, cam);
      scene.overrideMaterial = null;
      r.autoClear = false;
      cam.layers.disableAll(); cam.layers.enable(LAYER_CAST);
      r.render(scene, cam);
      r.autoClear = true;
      scene.background = bg;
    }
    cam.layers.enableAll();
    // AO (half res) from depth
    const near = cam.near, far = cam.far;
    for (const m of [this.mAO, this.mBlur, this.mDOF]) { m.uniforms.cNear.value = near; m.uniforms.cFar.value = far; }
    this.mAO.uniforms.projInv.value.copy(cam.projectionMatrixInverse);
    this.mAO.uniforms.projScale.value = cam.projectionMatrix.elements[5] * 0.5 * this.h;
    this.pass(this.mAO, this.aoA);
    this.mBlur.uniforms.tAO.value = this.aoA.texture; this.mBlur.uniforms.dir.value.set(2 / this.w, 0);
    this.pass(this.mBlur, this.aoB);
    this.mBlur.uniforms.tAO.value = this.aoB.texture; this.mBlur.uniforms.dir.value.set(0, 2 / this.h);
    this.pass(this.mBlur, this.aoA);
    // DOF
    const dof = opts.dof || { focus: 10, aperture: 0 };
    const A = dof.aperture * 7.0;                // circle of confusion at infinity, in pixels
    this.mDOF.uniforms.focus.value = dof.focus;
    this.mDOF.uniforms.cocScale.value = A;
    this.mDOF.uniforms.maxCoc.value = A > 0.05 ? Math.min(12, A * 1.6) : 0;
    this.pass(this.mComb, this.comb);
    if (this.mDOF.uniforms.maxCoc.value >= 0.35) { this.pass(this.mDOF, this.dof); this.mOut.uniforms.tColor.value = this.dof.texture; }
    else this.mOut.uniforms.tColor.value = this.comb.texture;
    // output to the canvas
    const u = this.mOut.uniforms;
    u.mode.value = layer === 'cast' ? 1 : layer === 'matte' ? 2 : 0;
    u.finish.value = (opts.finish ?? (layer === 'all')) ? 1 : 0;
    u.seed.value = (opts.frame || 0) % 997;
    r.setClearColor(0x000000, 0);
    this.pass(this.mOut, null);
  }
}
