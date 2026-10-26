// layers.js: the green-screen renderer. Every frame is painted twice, from the same seeds:
//   plate  the set and everything that isn't a character (opaque, on paper)
//   cast   the characters only, on a transparent canvas, held out by whatever set piece is in front of them
// and then composite = cast over plate. The paper grain and vignette are multiplied into both (a per-pixel scale, so
// grain(over(cast, plate)) == over(grain(cast), grain(plate)) exactly).
//
// p5.brush composites every mark with a spectral-mixing shader that writes alpha = 1 and treats a transparent pixel as
// white, so a brush painting on a transparent canvas comes out opaque. For the cast pass the shader is swapped for a
// copy that un-premultiplies the canvas, mixes the pigment into the existing colour with the right weight, and writes
// premultiplied colour and alpha, with p5's blend mode set to REPLACE. On an opaque canvas it reduces to the original.
let PASS = 'all';
if (location.search.includes('origshader')) window.EXP = { origShader: true };
const ALPHA_KEY = 'vec3 bgColor=mix(vec3(1.0),source.rgb,source.a);outColor=vec4(spectral_mix(bgColor,pigment.rgb,mixIntensity),1.);';
// The replacement main(): the same spectral (Kubelka-Munk) mix and the same pigment darkening as p5.brush's, with two
// changes for speed in software GL: (1) it exits early where the mask is empty or the pigment covers the pixel
// completely (the mix would return the pigment itself), and (2) the edge "pooling" boost is computed from finite
// differences of the mask instead of dFdx/dFdy, so whole pixel quads can skip the work (derivatives keep them alive).
// OUT(mixed) is the last line: plate = the original opaque write; cast = premultiplied colour with real alpha.
const MAIN = OUT => `void main(void){ivec2 sz=textureSize(u_mask,0);ivec2 fc=ivec2(gl_FragCoord.xy);ivec2 mc=u_targetIsFramebuffer?fc:ivec2(fc.x,sz.y-1-fc.y);
vec4 maskColor=texelFetch(u_mask,mc,0);if(maskColor.a==0.0){outColor=texelFetch(u_source,fc,0);return;}
vec4 pigment=vec4(u_color.xyz,1.0);if(u_isBrush&&(maskColor.a>DARKEN_THRESHOLD)){float blacken=0.5*(min(maskColor.a,1.0)-DARKEN_THRESHOLD);pigment=pigment*(1.0-blacken)-vec4(0.5)*blacken;pigment.rgb=max(pigment.rgb,vec3(0.0));}
float mixIntensity=min(maskColor.a,1.0);if(mixIntensity>=0.999){outColor=vec4(pigment.rgb,1.0);return;}
if(!u_isBrush){ivec2 m1=sz-1;float aL=texelFetch(u_mask,clamp(mc-ivec2(1,0),ivec2(0),m1),0).a,aR=texelFetch(u_mask,clamp(mc+ivec2(1,0),ivec2(0),m1),0).a,aD=texelFetch(u_mask,clamp(mc-ivec2(0,1),ivec2(0),m1),0).a,aU=texelFetch(u_mask,clamp(mc+ivec2(0,1),ivec2(0),m1),0).a;
float blurEdge=smoothstep(EDGE_MIN,EDGE_MAX,length(vec2(aR-aL,aU-aD))*7.5);mixIntensity=clamp(maskColor.a+blurEdge*0.1,0.0,1.0);}
vec4 source=texelFetch(u_source,fc,0);${OUT}}`;
const OUT_PLATE = 'vec3 bgColor=mix(vec3(1.0),source.rgb,source.a);outColor=vec4(spectral_mix(bgColor,pigment.rgb,mixIntensity),1.);';
const OUT_CAST = 'float as_=source.a;vec3 cs=as_>0.0?source.rgb/as_:vec3(1.0);float ao=as_+mixIntensity*(1.0-as_);float kk=ao>0.0?mixIntensity/ao:0.0;vec3 cc=spectral_mix(cs,pigment.rgb,kk);outColor=vec4(cc*ao,ao);';
const SHD = { orig: null, alpha: null, plate: null };
function alphaShader(on) {
  const inst = window.p5.instance;
  if (!inst.shaderProgram) { push(); boilSeed('shader warmup'); paint([[-90, -90], [-80, -90], [-80, -80]], { wash: '#000000', ink: null }); flushBrush(); pop(); }
  if (!SHD.orig) {
    SHD.orig = inst.shaderProgram;
    const f = SHD.orig._fragSrc, i = f.indexOf('void main(void){');
    if (i < 0 || !f.includes(ALPHA_KEY)) throw new Error('p5.brush blend shader changed: re-check the replacement main() in layers.js');
    SHD.alpha = createShader(SHD.orig._vertSrc, f.slice(0, i) + MAIN(OUT_CAST));
    SHD.plate = createShader(SHD.orig._vertSrc, f.slice(0, i) + MAIN(OUT_PLATE));
    // a new shader's first composite comes out in the wrong colour (its uniforms aren't live yet): warm each one up with
    // a throwaway mark, then repaint what was under it
    for (const sh of [SHD.plate, SHD.alpha]) { inst.shaderProgram = sh; boilSeed('warmup'); _paint([[1, 1], [6, 1], [6, 6], [1, 6]], { wash: '#808080', ink: null }); flushBrush(); _paint([[1, 1], [6, 1], [6, 6]], { wash: '#404040', ink: null }); flushBrush(); }
    inst.shaderProgram = SHD.orig; flushBrush();
    if (typeof PASS !== 'undefined' && PASS === 'cast') clear(); else image(paperG, 0, 0);
  }
  flushBrush();
  if (window.EXP && window.EXP.noAlpha) on = false;
  inst.shaderProgram = on ? SHD.alpha : (window.EXP && window.EXP.origShader ? SHD.orig : SHD.plate);
  blendMode(on ? REPLACE : BLEND);
}
// ---------------------------------------------------------------- holdouts (cast pass): erase what a set piece hides
function dilate(pts, d) { let cx = 0, cy = 0; for (const p of pts) { cx += p[0]; cy += p[1]; } cx /= pts.length; cy /= pts.length; return pts.map(([x, y]) => { const dx = x - cx, dy = y - cy, l = Math.hypot(dx, dy) || 1; return [x + dx / l * d, y + dy / l * d]; }); }
function erasePoly(pts) { erase(); noStroke(); fill(255); beginShape(); for (const p of pts) vertex(p[0], p[1]); endShape(CLOSE); noErase(); }
function eraseOutside(pts, far = 5000) {   // everything outside a convex (or star-shaped) polygon
  let cx = 0, cy = 0; for (const p of pts) { cx += p[0]; cy += p[1]; } cx /= pts.length; cy /= pts.length;
  const out = p => { const dx = p[0] - cx, dy = p[1] - cy, d = Math.hypot(dx, dy) || 1; return [cx + dx / d * far, cy + dy / d * far]; };
  for (let i = 0; i < pts.length; i++) { const a = pts[i], b = pts[(i + 1) % pts.length], ex = (b[0] - a[0]) * .08, ey = (b[1] - a[1]) * .08, a2 = [a[0] - ex, a[1] - ey], b2 = [b[0] + ex, b[1] + ey]; erasePoly([a2, b2, out(b2), out(a2)]); }
}
function holdOut(list) {
  if (window.EXP && window.EXP.noHold) return;
  flushBrush();
  push();
  for (const o of list) {
    if (o.outside) eraseOutside(dilate(o.outside, -2));
    else if (o.shape && o.shape.pts && o.shape.pts.length > 2) erasePoly(dilate(o.shape.pts, o.shape.o && o.shape.o.ink === null ? .6 : 2.2));
  }
  pop();
}
// ---------------------------------------------------------------- frame: plate pass, cast pass, composite
let plateC = null, castC = null, grainD = null;
function fnv(d) { let h1 = 2166136261, h2 = 0x9747b28c; for (let i = 0; i < d.length; i++) { h1 = Math.imul(h1 ^ d[i], 16777619); h2 = Math.imul(h2 ^ d[i], 2246822507) ^ (h2 >>> 13); } return (h1 >>> 0).toString(16).padStart(8, '0') + (h2 >>> 0).toString(16).padStart(8, '0'); }
async function renderLayers(t, o = {}) {
  if (!plateC) {
    for (const k of ['plateC', 'castC']) { const c = document.createElement('canvas'); c.width = W; c.height = H; if (k === 'plateC') plateC = c; else castC = c; }
    const g = document.createElement('canvas'); g.width = W; g.height = H; const gx = g.getContext('2d'); gx.drawImage(grainC, 0, 0); grainD = gx.getImageData(0, 0, W, H).data;
  }
  const px = plateC.getContext('2d', { willReadFrequently: true }), cx = castC.getContext('2d', { willReadFrequently: true });
  const ms = {}; let t0 = performance.now();
  // plate
  PASS = 'plate'; T = t; await redraw();
  px.globalCompositeOperation = 'source-over'; px.drawImage(drawingContext.canvas, 0, 0, W, H);
  px.globalCompositeOperation = 'multiply'; px.drawImage(grainC, 0, 0); px.globalCompositeOperation = 'source-over';
  ms.plate = Math.round(performance.now() - t0); t0 = performance.now();
  // cast
  PASS = 'cast'; T = t; await redraw();
  cx.clearRect(0, 0, W, H); cx.drawImage(drawingContext.canvas, 0, 0, W, H);
  const cd = cx.getImageData(0, 0, W, H), d = cd.data;
  for (let i = 0; i < d.length; i += 4) if (d[i + 3]) { d[i] = d[i] * grainD[i] / 255; d[i + 1] = d[i + 1] * grainD[i + 1] / 255; d[i + 2] = d[i + 2] * grainD[i + 2] / 255; }
  cx.putImageData(cd, 0, 0);
  ms.cast = Math.round(performance.now() - t0); t0 = performance.now();
  PASS = 'all';
  // composite
  outX.globalCompositeOperation = 'source-over'; outX.drawImage(plateC, 0, 0); outX.drawImage(castC, 0, 0);
  const R = { t, ms };
  if (o.hash) { R.plateHash = fnv(px.getImageData(0, 0, W, H).data); R.castHash = fnv(d); }
  if (o.images) {
    R.composite = outC.toDataURL('image/jpeg', .95);
    R.plate = plateC.toDataURL('image/jpeg', .95);
    R.cast = castC.toDataURL('image/png');
  }
  if (o.tracks && window.trackAt) R.track = window.trackAt(t);
  ms.encode = Math.round(performance.now() - t0);
  return R;
}
// the kit's sheets and stills go through the same layered frame when the video (not a loop) is showing
FRAME = async t => { if (window.LOOP) { T = t; await redraw(); composite(t); } else await renderLayers(t); };
window.renderLayers = renderLayers;
