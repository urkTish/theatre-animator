// Procedural, seeded, tileable textures drawn once into canvases at load time.
// No image files: the look is fully reproducible from the seeds below.
import * as THREE from 'three';
import { clamp, fbm, hash2, lerp, vnoise } from './util.js';

function canvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

function toTexture(c, srgb, repeat = true) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.needsUpdate = true;
  return t;
}

// height field (Float32Array, w*h, tileable) -> tangent-space normal map
function normalFromHeight(hgt, w, h, strength) {
  const c = canvas(w, h), ctx = c.getContext('2d');
  const img = ctx.createImageData(w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const xl = (x - 1 + w) % w, xr = (x + 1) % w, yu = (y - 1 + h) % h, yd = (y + 1) % h;
      const dx = (hgt[y * w + xr] - hgt[y * w + xl]) * strength;
      const dy = (hgt[yd * w + x] - hgt[yu * w + x]) * strength;
      const len = Math.hypot(dx, dy, 1);
      const i = (y * w + x) * 4;
      d[i] = (-dx / len * 0.5 + 0.5) * 255;
      d[i + 1] = (dy / len * 0.5 + 0.5) * 255;
      d[i + 2] = (1 / len * 0.5 + 0.5) * 255;
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return toTexture(c, false);
}

function mix3(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }
const hex = (s) => [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)];

// Weathered timber. One tile = 0.6 m (u) x 2.4 m (v), grain along v.
// Sun-bleached silver-brown with darker grain, a few knots, faint vertical checks.
export function timberTextures(seed, opts = {}) {
  const W = 256, H = 1024;
  const dark = hex(opts.dark || '#4e3826'), mid = hex(opts.mid || '#7d5f45'), light = hex(opts.light || '#a88a6c');
  const grey = hex(opts.grey || '#8f877e');
  const weather = opts.weather ?? 0.45;
  const c = canvas(W, H), ctx = c.getContext('2d');
  const img = ctx.createImageData(W, H), d = img.data;
  const hgt = new Float32Array(W * H), rough = canvas(W, H), rctx = rough.getContext('2d');
  const rimg = rctx.createImageData(W, H), rd = rimg.data;
  // knots: a few per tile
  const knots = [];
  for (let k = 0; k < 3; k++) knots.push([hash2(k, 1, seed) * W, hash2(k, 2, seed) * H, 6 + hash2(k, 3, seed) * 7]);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const u = x / W, v = y / H;
      // warped grain: periodic in u (8 cycles across the tile) and v
      let warp = (fbm(u * 4, v * 2, seed, 3, 4) - 0.5) * 0.9 + (vnoise(u * 16, v * 3, seed + 5, 16) - 0.5) * 0.15;
      let kx = 0;
      for (const [cx, cy, r] of knots) {
        let ddx = Math.abs(x - cx); ddx = Math.min(ddx, W - ddx);
        let ddy = Math.abs(y - cy); ddy = Math.min(ddy, H - ddy);
        const dist = Math.hypot(ddx, ddy * 0.6);
        kx += Math.exp(-dist / (r * 2.2)) * 1.6;
        if (dist < r) kx += 2.5 * (1 - dist / r);
      }
      const g = 0.5 + 0.5 * Math.sin((u * 22 + warp * 3 + kx) * Math.PI * 2);
      const lines = Math.pow(g, 10);                       // thin dark latewood lines
      const fine = vnoise(u * 128, v * 6, seed + 9, 128);
      const streak = fbm(u * 8, v * 1.5, seed + 13, 3, 8);  // vertical weather staining
      const blotch = fbm(u * 3, v * 0.8, seed + 31, 3, 3);
      let col = mix3(mid, light, clamp(0.42 + 0.35 * (fine - 0.5) + 0.45 * (streak - 0.5) + 0.3 * (blotch - 0.5)));
      col = mix3(col, dark, lines * 0.18 + clamp((0.32 - streak) * 1.3) * 0.30 + Math.min(1, kx * 0.25) * 0.35);
      col = mix3(col, grey, clamp(weather * (0.75 + 0.9 * (blotch - 0.5))));
      // hairline checks
      const check = Math.pow(clamp(1 - Math.abs(vnoise(u * 40, v * 1.2, seed + 21, 40) - 0.5) * 60), 2) * (fine > 0.55 ? 1 : 0);
      col = mix3(col, dark, check * 0.45);
      const i = (y * W + x) * 4;
      d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = 255;
      hgt[y * W + x] = g * 0.35 + fine * 0.45 + streak * 0.6 - lines * 0.5 - check * 1.5;
      const r = clamp(0.62 + (1 - g) * 0.2 + (streak - 0.5) * 0.2) * 255;
      rd[i] = rd[i + 1] = rd[i + 2] = r; rd[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  rctx.putImageData(rimg, 0, 0);
  return { map: toTexture(c, true), normalMap: normalFromHeight(hgt, W, H, 2.2), roughnessMap: toTexture(rough, false), tile: [0.6, 2.4] };
}

// Beaten earth. One tile = 4 m x 4 m: fine grit, small stones, faint scuffs.
export function earthTextures(seed) {
  const N = 1024;
  const c = canvas(N, N), ctx = c.getContext('2d');
  const img = ctx.createImageData(N, N), d = img.data;
  const hgt = new Float32Array(N * N);
  const base = hex('#a98d6c'), dark = hex('#836a4f'), pale = hex('#c4ad8c'), stone = hex('#bba98d');
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const u = x / N, v = y / N;
      const low = fbm(u * 6, v * 6, seed, 4, 6);
      const mid = fbm(u * 40, v * 40, seed + 3, 3, 40);
      const grit = hash2(x, y, seed + 7);
      // pebbles: cellular-ish bumps
      const cu = u * 90, cv = v * 90, ci = Math.floor(cu), cj = Math.floor(cv);
      let peb = 0;
      for (let oy = -1; oy <= 1; oy++) for (let ox = -1; ox <= 1; ox++) {
        const ii = ((ci + ox) % 90 + 90) % 90, jj = ((cj + oy) % 90 + 90) % 90;
        if (hash2(ii, jj, seed + 11) > 0.93) {
          const px = ci + ox + hash2(ii, jj, seed + 12), py = cj + oy + hash2(ii, jj, seed + 13);
          const r = 0.18 + 0.25 * hash2(ii, jj, seed + 14);
          const dd = Math.hypot(cu - px, cv - py) / r;
          if (dd < 1) peb = Math.max(peb, Math.sqrt(1 - dd * dd));
        }
      }
      let col = mix3(dark, base, clamp(low * 1.5 - 0.15));
      col = mix3(col, pale, clamp((mid - 0.45) * 1.6) * 0.55);
      col = mix3(col, dark, (grit > 0.93 ? 0.35 : 0) + (1 - grit) * 0.08);
      col = mix3(col, stone, peb * 0.3);
      const i = (y * N + x) * 4;
      d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = 255;
      hgt[y * N + x] = low * 0.6 + mid * 0.5 + grit * 0.2 + peb * 0.8;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { map: toTexture(c, true), normalMap: normalFromHeight(hgt, N, N, 1.6), tile: [4, 4] };
}

// Linen / wool weave for the couch mattress and cushion. One tile = 0.25 m.
export function weaveTextures(seed, color = '#e2d7c3') {
  const N = 256;
  const c = canvas(N, N), ctx = c.getContext('2d');
  const img = ctx.createImageData(N, N), d = img.data;
  const hgt = new Float32Array(N * N);
  const base = hex(color);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const wx = Math.sin((x / N) * Math.PI * 2 * 48), wy = Math.sin((y / N) * Math.PI * 2 * 48);
      const over = ((Math.floor(x / N * 48) + Math.floor(y / N * 48)) & 1) ? wx : wy;
      const slub = fbm(x / N * 8, y / N * 64, seed, 2, 8);
      const k = 0.9 + 0.08 * over + 0.12 * (slub - 0.5);
      const i = (y * N + x) * 4;
      d[i] = base[0] * k; d[i + 1] = base[1] * k; d[i + 2] = base[2] * k; d[i + 3] = 255;
      hgt[y * N + x] = over * 0.5 + slub * 0.5;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { map: toTexture(c, true), normalMap: normalFromHeight(hgt, N, N, 1.2), tile: [0.25, 0.25] };
}
