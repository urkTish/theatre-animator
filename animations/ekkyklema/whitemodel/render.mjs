#!/usr/bin/env node
// Offline renderer: serves this folder, drives scene.html in headless Chromium
// (software WebGL), captures each frame/layer and encodes with ffmpeg.
//
//   node render.mjs --out /path/out [--start 0 --end 10 --fps 24 --w 1920 --h 1080]
//                   [--layers all,plate,cast,matte] [--style clay|vase] [--cast cast.json]
//                   [--tracks] [--prores] [--contact-shadows] [--stills 0,3,5,8] [--crf 18]
//   node render.mjs --serve            # just serve the folder for a live preview
//
// Outputs in --out:  composite.mp4 (layer all), plate.mp4, matte.mp4,
//   cast_rgba/0000.png... (+ cast_rgba.mov ProRes 4444 with --prores),
//   tracks.json (one entry per frame), render_stats.json, stills/<layer>_<t>.png
import { createRequire } from 'module';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import crypto from 'crypto';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const HERE = path.dirname(fileURLToPath(import.meta.url));

// ------------------------------------------------------------------ args
const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf('--' + name); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : def; };
const flag = (name) => argv.includes('--' + name);
const FPS = +opt('fps', 24), W = +opt('w', 1920), H = +opt('h', 1080);
const START = +opt('start', 0), END = +opt('end', 10);
const LAYERS = opt('layers', 'all').split(',').filter(Boolean);
const OUT = path.resolve(opt('out', path.join(HERE, 'out')));
const STYLE = opt('style', '');
const CAST = opt('cast', 'cast.json');
const CRF = opt('crf', '18');
const STILLS = opt('stills', '') ? opt('stills', '').split(',').map(Number) : null;
const NAMES = { all: 'composite', plate: 'plate', matte: 'matte', cast: 'cast_rgba' };
// with both cast and matte requested, the matte is taken from the cast alpha (exactly the
// same pixels the 'matte' layer renders) instead of rendering it a second time
const MATTE_FROM_CAST = LAYERS.includes('cast') && LAYERS.includes('matte') && !flag('render-matte');
const RENDER_LAYERS = MATTE_FROM_CAST ? LAYERS.filter((l) => l !== 'matte') : LAYERS;

// ------------------------------------------------------------------ static server
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.ttf': 'font/ttf', '.png': 'image/png', '.jpg': 'image/jpeg', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.bin': 'application/octet-stream', '.mp4': 'video/mp4', '.webm': 'video/webm' };
function serve(port = 0) {
  return new Promise((res) => {
    const srv = http.createServer((req, rsp) => {
      const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      const f = path.join(HERE, path.normalize(p).replace(/^(\.\.[/\\])+/, ''));
      if (!f.startsWith(HERE) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { rsp.writeHead(404); rsp.end(); return; }
      rsp.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      fs.createReadStream(f).pipe(rsp);
    });
    srv.listen(port, '127.0.0.1', () => res(srv));
  });
}

function ffmpeg(args) {
  const p = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => p.on('close', (c) => (c === 0 ? res() : rej(new Error('ffmpeg exit ' + c)))));
  return { p, done };
}
const write = (stream, buf) => new Promise((res) => (stream.write(buf) ? res() : stream.once('drain', res)));

async function main() {
  if (flag('serve')) {
    const srv = await serve(+opt('port', 8123));
    console.log(`serving ${HERE} at http://127.0.0.1:${srv.address().port}/scene.html`);
    return;
  }
  fs.mkdirSync(OUT, { recursive: true });
  const srv = await serve();
  const port = srv.address().port;
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-gpu-vsync', '--force-color-profile=srgb'] });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  const q = new URLSearchParams({ render: '1', w: W, h: H, cast: CAST });
  if (STYLE) q.set('style', STYLE);
  const t0 = Date.now();
  await page.goto(`http://127.0.0.1:${port}/scene.html?${q}`);
  await page.evaluate(() => window.ready);
  const loadMs = Date.now() - t0;
  console.log(`scene ready in ${(loadMs / 1000).toFixed(1)} s`);
  const cdp = await page.context().newCDPSession(page);
  let transparentBg = false;
  const capture = async (alpha) => {
    if (alpha !== transparentBg) {
      await cdp.send('Emulation.setDefaultBackgroundColorOverride', alpha ? { color: { r: 0, g: 0, b: 0, a: 0 } } : {});
      transparentBg = alpha;
    }
    const r = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true, captureBeyondViewport: false, clip: { x: 0, y: 0, width: W, height: H, scale: 1 } });
    return Buffer.from(r.data, 'base64');
  };

  const stats = { width: W, height: H, fps: FPS, style: STYLE || 'from cast.json', load_s: loadMs / 1000, layers: {}, errors };
  const shoot = async (t, layer) => {
    const a = Date.now();
    const info = await page.evaluate(([t, layer, cs]) => window.renderAt(t, { layer, contactShadows: cs, sync: true }), [t, layer, flag('contact-shadows')]);
    const b = Date.now();
    const buf = await capture(layer === 'cast');
    const c = Date.now();
    const s = (stats.layers[layer] ||= { frames: 0, render_ms: 0, capture_ms: 0, pose_ms: 0, gpu_ms: 0 });
    s.frames++; s.render_ms += b - a; s.capture_ms += c - b; s.pose_ms += info.cpu_pose_ms; s.gpu_ms += info.submit_ms + info.gpu_wait_ms;
    return buf;
  };

  if (STILLS) {
    fs.mkdirSync(path.join(OUT, 'stills'), { recursive: true });
    for (const t of STILLS) for (const layer of RENDER_LAYERS.concat(MATTE_FROM_CAST ? ['matte'] : [])) {
      const buf = await shoot(t, layer);
      fs.writeFileSync(path.join(OUT, 'stills', `${NAMES[layer]}_${t.toFixed(2)}.png`), buf);
    }
  } else {
    const first = Math.round(START * FPS), last = Math.round(END * FPS) - 1;
    const enc = {};
    const hashes = {};
    for (const layer of RENDER_LAYERS) {
      if (layer === 'cast') { fs.mkdirSync(path.join(OUT, 'cast_rgba'), { recursive: true }); continue; }
      enc[layer] = ffmpeg(['-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', CRF, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(OUT, NAMES[layer] + '.mp4')]);
    }
    const tracks = [];
    const tStart = Date.now();
    for (let f = first; f <= last; f++) {
      const t = f / FPS;
      for (const layer of RENDER_LAYERS) {
        const buf = await shoot(t, layer);
        (hashes[layer] ||= []).push(crypto.createHash('md5').update(buf).digest('hex'));
        if (layer === 'cast') fs.writeFileSync(path.join(OUT, 'cast_rgba', String(f).padStart(4, '0') + '.png'), buf);
        else await write(enc[layer].p.stdin, buf);
      }
      if (flag('tracks')) tracks.push(await page.evaluate((t) => window.trackAt(t), t));
      if ((f - first) % 12 === 0) {
        const el = (Date.now() - tStart) / 1000, n = f - first + 1;
        console.log(`frame ${f} (t=${t.toFixed(2)}) ${n}/${last - first + 1}  ${(el / n).toFixed(2)} s/frame`);
      }
    }
    for (const e of Object.values(enc)) { e.p.stdin.end(); await e.done; }
    fs.writeFileSync(path.join(OUT, 'frame_hashes.json'), JSON.stringify(hashes, null, 0));
    if (MATTE_FROM_CAST) {
      await ffmpeg(['-framerate', String(FPS), '-start_number', String(first), '-i', path.join(OUT, 'cast_rgba', '%04d.png'), '-vf', 'alphaextract,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', CRF, '-movflags', '+faststart', path.join(OUT, 'matte.mp4')]).done;
    }
    if (LAYERS.includes('cast') && flag('prores')) {
      await ffmpeg(['-framerate', String(FPS), '-start_number', String(first), '-i', path.join(OUT, 'cast_rgba', '%04d.png'), '-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', '-vendor', 'apl0', path.join(OUT, 'cast_rgba.mov')]).done;
    }
    if (flag('tracks')) fs.writeFileSync(path.join(OUT, 'tracks.json'), JSON.stringify({ fps: FPS, width: W, height: H, frames: tracks }, null, 1));
    stats.total_s = (Date.now() - tStart) / 1000;
    stats.frames = last - first + 1;
  }
  for (const s of Object.values(stats.layers)) { s.render_ms_per_frame = +(s.render_ms / s.frames).toFixed(1); s.capture_ms_per_frame = +(s.capture_ms / s.frames).toFixed(1); s.pose_ms_per_frame = +(s.pose_ms / s.frames).toFixed(1); s.gpu_ms_per_frame = +(s.gpu_ms / s.frames).toFixed(1); }
  fs.writeFileSync(path.join(OUT, 'render_stats.json'), JSON.stringify(stats, null, 1));
  console.log(JSON.stringify(stats.layers));
  if (errors.length) console.log('page messages:\n' + [...new Set(errors)].slice(0, 20).join('\n'));
  await browser.close();
  srv.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
