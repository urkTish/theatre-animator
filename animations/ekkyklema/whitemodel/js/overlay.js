// HTML/CSS overlays (chapter card, "How sure?" gauge, breadcrumb outline).
// They exist only in layer "all"; every style is set from t, nothing uses CSS
// transitions, so any frame is exact.
import { clamp, smoothstep, smootherstep } from './util.js';
import { T } from './timeline.js';

const LEVEL = { attested: 0, inferred: 1, choice: 2 };

export function buildOverlay(root) {
  root.innerHTML = `
  <div id="card" class="card">
    <div class="row r1"><span class="counter">06 / 10</span><span class="dot">·</span><span class="name">THE ROLL-OUT</span></div>
    <div class="row r2"><span class="translit">ekkyklein</span> <span class="greek">ἐκκυκλεῖν</span> <span class="gloss">“to roll out”</span></div>
    <div class="row r3"><span class="cite">Ar. <i>Acharnians</i> 408</span></div>
  </div>
  <div id="gauge" class="gauge">
    <div class="gtitle">HOW SURE?</div>
    <div class="gtrack">
      <div class="gline"></div>
      <div class="gtick t0"><span class="glab">ATTESTED</span><span class="gsub">an ancient text says so</span></div>
      <div class="gtick t1"><span class="glab">INFERRED</span><span class="gsub">scholars deduce it</span></div>
      <div class="gtick t2"><span class="glab">OUR CHOICE</span><span class="gsub">reconstruction</span></div>
      <div class="gmarker"><i></i></div>
    </div>
    <div class="gnote">Word: attested.<br>Wheels: inferred.</div>
  </div>
  <svg id="crumb" class="crumb" viewBox="0 0 1920 1080" width="1920" height="1080">
    <defs><filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/></filter></defs>
    <path class="cglow" d="" filter="url(#glow)"/>
    <path class="cline" d=""/>
  </svg>
  <div id="crumbLabel" class="crumbLabel">next: the platform</div>`;
  return {
    card: root.querySelector('#card'),
    rows: [...root.querySelectorAll('#card .row')],
    gauge: root.querySelector('#gauge'),
    marker: root.querySelector('.gmarker'),
    crumb: root.querySelector('#crumb'),
    crumbPaths: [...root.querySelectorAll('#crumb path')],
    crumbLabel: root.querySelector('#crumbLabel'),
  };
}

function hull(pts) {
  const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.reverse()) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}

// info.platformCorners: screen-space [x, y] of the platform's bounding box corners
export function updateOverlay(o, t, info) {
  // chapter card: slides in with staggered rows
  const ci = smootherstep(T.card_in[0], T.card_in[1], t);
  o.card.style.opacity = ci.toFixed(4);
  o.card.style.transform = `translateX(${((1 - ci) * -26).toFixed(2)}px)`;
  o.rows.forEach((row, i) => {
    const k = smootherstep(T.card_in[0] + 0.12 + i * 0.16, T.card_in[0] + 0.62 + i * 0.16, t);
    row.style.opacity = k.toFixed(4);
    row.style.transform = `translateY(${((1 - k) * 8).toFixed(2)}px)`;
  });
  // gauge: fades in, then the marker settles on "Inferred"
  const gi = smootherstep(0.55, 1.35, t);
  o.gauge.style.opacity = gi.toFixed(4);
  o.gauge.style.transform = `translateX(${((1 - gi) * 22).toFixed(2)}px)`;
  const level = LEVEL.inferred * smootherstep(1.0, 1.9, t);
  o.marker.style.top = `${(level * 50).toFixed(3)}%`;
  o.marker.style.opacity = smoothstep(0.9, 1.2, t).toFixed(4);
  // breadcrumb: thin accent outline on the platform, ~0.8 s before it moves
  const [c0, c1] = T.crumb;
  const k = smoothstep(c0, c0 + 0.18, t) * (1 - smoothstep(c1 - 0.05, c1 + 0.25, t));
  if (k > 0.001 && info && info.platformCorners) {
    const h = hull(info.platformCorners);
    const d = 'M' + h.map((p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' L') + ' Z';
    o.crumbPaths.forEach((p) => p.setAttribute('d', d));
    o.crumb.style.opacity = k.toFixed(4);
    const xs = h.map((p) => p[0]), ys = h.map((p) => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, by = Math.max(...ys);
    o.crumbLabel.style.left = `${cx.toFixed(1)}px`;
    o.crumbLabel.style.top = `${(by + 14).toFixed(1)}px`;
    o.crumbLabel.style.opacity = k.toFixed(4);
    // the line draws itself on
    const draw = smootherstep(c0, c0 + 0.35, t);
    o.crumbPaths[1].style.strokeDasharray = `${(draw * 4000).toFixed(1)} 4000`;
  } else {
    o.crumb.style.opacity = '0';
    o.crumbLabel.style.opacity = '0';
  }
}
