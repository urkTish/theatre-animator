// stage.js: the set (the plate) and the machinery. The Theatre of Dionysus, c. 425 BC: a wooden skene, its central
// double door, the ekkyklema, and the tableau on it.
//
// World: metres. x runs along the facade (+ = the audience's right), y is up, z points toward the audience, and the
// facade face is the plane z = 0. The camera is the audience's eye, standing left of the door axis and looking straight
// at the facade (one-point perspective: verticals stay vertical, the facade is never foreshortened). proj() places a
// world point on screen; set pieces are painted flat (wash + ink, boiling) at the projected corners, and characters are
// flat drawings placed and scaled at their depth. Nothing rotates in 3D.
//
// Every set piece is built in two steps: shapes first (seeded by boilSeed with a stable key, so the same frame gives
// the same jittered points in every pass), then paint. The cast pass rebuilds the same shapes to hold the characters
// out (src/layers.js), so a door frame hides a stagehand exactly where the painted frame is.

// ---------------------------------------------------------------- the facts (see STORYBOARD.md)
const GEO = {
  facadeW: 12, facadeH: 5, doorW: 2.8, doorH: 3.2, leafW: 1.4, hingeZ: -.12, jambW: .22, frameDepth: .18,
  platW: 2.4, platD: 1.6, deckY: .3, deckT: .06, wheelR: .12, wheelX: 1.17,
  zFront0: -1.68, roll: 2.93,                        // the platform's front edge waits 1.68 m behind the facade, rolls 2.93 m
  couchL: 2.1, couchD: .8, couchH: .45, couchZ: -.78, // couch on the deck: its centre 0.78 m behind the deck's front edge
};
const TIMES = { knock: [2.12, 2.42], doors: [3.3, 5.4], roll: [5.5, 9.5], end: 15 };
const smoother = u => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };   // quintic: slow in, slow out
// the machinery as pure functions of t
const doorAngle = t => {
  const [a, b] = TIMES.doors, k = smoother(seg(t, a, b));
  const unlatch = t > a - .12 && t < a + .2 ? .015 * Math.sin(seg(t, a - .12, a + .2) * Math.PI) : 0;           // the bar lifts: a small jolt first
  const knock = TIMES.knock.reduce((s, tk) => s + .006 * spring(t, tk, 14, 60), 0);                               // the right leaf jolts at each knock
  return { L: k * Math.PI / 2 + unlatch * .6, R: k * Math.PI / 2 + unlatch + knock };
};
const rollDist = t => GEO.roll * smoother(seg(t, ...TIMES.roll));
const platFront = t => GEO.zFront0 + rollDist(t);
const wheelAngle = t => rollDist(t) / GEO.wheelR;

// ---------------------------------------------------------------- camera: audience eye, dollying in with the roll-out
// cz = distance of the eye from the facade plane, cx = its position along the facade, cy = its height; F = focal (px);
// (Xp, Yh) = where the eye's axis lands on screen (a lens shift, so verticals stay vertical).
function camAt(t) {
  const e = ease;
  const cz = kf(t, [[0, 12.6], [1.0, 12.5], [2.4, 11.7], [5.3, 11.2], [9.9, 8.0], [15, 7.75]], e);
  const Xp = kf(t, [[0, -30], [1.0, -30], [2.4, -60], [5.3, -110], [9.9, -840], [15, -880]], e) + 6 * Math.sin(t * .4);
  const Yh = kf(t, [[0, 525], [1.0, 525], [2.4, 505], [5.3, 470], [9.9, 168], [15, 152]], e) + 3 * Math.sin(t * .31 + 1);
  return { cx: -5, cy: 2.8, cz, F: 2100, Xp, Yh };
}
let CAMS = camAt(0);
const proj = (x, y, z, c = CAMS) => { const s = c.F / (c.cz - z); return [c.Xp + (x - c.cx) * s, c.Yh - (y - c.cy) * s, s]; };
const scaleAt = (z, c = CAMS) => c.F / (c.cz - z);
// projected points with boil jitter (world points -> screen)
const PJ = (pts, j = 1.2) => pts.map(([x, y, z]) => { const p = proj(x, y, z); return [p[0] + jit(j), p[1] + jit(j)]; });

// ---------------------------------------------------------------- palette of the world
const SET = {
  skyTop: '#9DB4C6', skyMid: '#D9CDB4', skyLow: '#F1D29E', sun: '#FFE0A8', hillFar: '#C2A7AC', hillNear: '#A88E95', tree: '#6B7150', treeDk: '#4E5640',
  wood: '#C99760', woodDk: '#A97A4A', woodShade: '#7A5235', post: '#8C5D37', postLit: '#D7A56A', rail: '#9A6A3E',
  frame: '#7A4E2F', leaf: '#A0744A', leafDk: '#6E4C30', iron: '#3A302E', dark: '#1D1416', darkFloor: '#2B1F1D',
  earth: '#CFAE82', earthDk: '#A9875E', earthLt: '#DDBF94',
  deck: '#C9A06E', deckDk: '#8A5A34', wheel: '#6E4C33', tyre: '#3A3030',
  couch: '#7A4B2C', couchDk: '#5A3620', linen: '#E9DCBB', stripe: '#A9432F', stripe2: '#3F5F8C', pillow: '#A9432F', stool: '#8A5A34', cup: '#201A1C',
};
// the dark of the skene's interior, by depth: 0 outside in the light, about 0.88 deep inside
const shadeAt = z => .9 * smoother(seg(z, .2, -1.4)) + .075 * smoother(seg(z, -2.0, -3.3));
// figures sink a little deeper into the dark than the set (cloth and skin catch less of the spill than linen and wood),
// so the couch hints at the tableau while the stagehands behind it stay unseen
const shadeFig = z => .965 * smoother(seg(z, .2, -1.3)) + .025 * smoother(seg(z, -2.0, -3.3));

// ---------------------------------------------------------------- shapes
// A shape is { pts (screen), o (paint options) }. mk(key, ...) seeds it, so its jitter depends on the key and the boil
// frame only, never on what was painted before it.
const mk = (key, worldPts, o = {}, j = 1.2) => { boilSeed(key); return { key, pts: PJ(worldPts, j), o }; };
const mkS = (key, screenPts, o = {}) => { boilSeed(key); return { key, pts: screenPts, o }; };
// Painting the SET. A wash at full opacity is a flat colour, so the set's washes and glazes are laid down as plain
// (jittered, boiling) polygons, and every outline and line stays a p5.brush ink stroke. That looks the same and saves a
// full-screen p5.brush composite per wash, which in software GL is most of a frame (README: render speed).
// Characters are painted entirely with p5.brush (src/people.js).
// p5.brush defers its marks; before a plain polygon goes down, whatever the brush still holds must be composited. Its
// own end-of-draw hook does exactly that (the kit's flushBrush() also works, but leaves a tiny fill pending each time).
// Also: a mark that lies entirely off the canvas gets an empty dirty rect, and p5.brush then composites the WHOLE frame
// for it (core/dirty_rect.js + color.js getCompositeRect). A character walking off-screen cost 20 s a frame that way, so
// marks entirely outside the canvas are skipped (they could not show anyway).
let BRUSH_PENDING = false;
const _paint = paint, _inkLine = inkLine;
const offCanvas = pts => { let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity; for (const [x, y] of pts) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; } const m = 40; return x1 < -m || x0 > W + m || y1 < -m || y0 > H + m; };
paint = (pts, o) => { if (!CAM_XFORM_ACTIVE() && offCanvas(pts)) return; BRUSH_PENDING = true; return _paint(pts, o); };
inkLine = (pts, ...a) => { if (!CAM_XFORM_ACTIVE() && offCanvas(pts)) return; BRUSH_PENDING = true; return _inkLine(pts, ...a); };
// the cull assumes screen coordinates: off when a kit camera (camBegin) or a loop (model sheets) transforms the canvas
const CAM_XFORM_ACTIVE = () => !!CAM || !!window.LOOP;
function brushFlush() { if (!BRUSH_PENDING) return; BRUSH_PENDING = false; for (const h of p5.lifecycleHooks.postdraw) h.call(p5.instance); }
function flatPoly(pts, col, op = 255) {
  brushFlush();
  push(); noStroke(); const c = color(col); c.setAlpha(op); fill(c); beginShape(); for (const p of pts) vertex(p[0], p[1]); endShape(CLOSE); pop();
}
// a hairline drawn as a thin tapered polygon (it boils with the jitter like everything else); for long, thin set lines
// (plank seams, the eave, ridge lines) where a brush stroke's texture doesn't show but costs a full composite
function hairline(pts, w, col) {
  if (pts.length < 2) return;
  const A = [], B = [], n = pts.length;
  for (let i = 0; i < n; i++) {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(n - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy) || 1, ww = w * (.55 + .45 * Math.sin(Math.PI * (i + .5) / n)) / 2;
    A.push([pts[i][0] - dy / d * ww, pts[i][1] + dx / d * ww]); B.push([pts[i][0] + dy / d * ww, pts[i][1] - dx / d * ww]);
  }
  flatPoly(A.concat(B.reverse()), col);
}
function setPaint(pts, o) {
  if ((o.wash) && !o.fill && !o.hatch && !(window.EXP && window.EXP.brushSet)) {
    flatPoly(pts, o.wash, o.washOp ?? 255);
    if (o.ink !== null) paint(pts, { ink: o.ink, sw: o.sw, curv: o.curv });
  } else paint(pts, o);
}
const drawLine = s => { if (s.o.hair) hairline(s.pts, s.o.hair, s.o.col || PAL.ink); else inkLine(s.pts, s.o.sw ?? 1, s.o.col || PAL.ink, s.o.br || 'ink', s.o.curv ?? .3); };
const paintShapes = list => { for (const s of list) { boilSeed(s.key + ' paint'); if (s.line) drawLine(s); else setPaint(s.pts, s.o); } };
// For a group of shapes that don't overlap each other: every wash first (grouped by colour), then every outline, then
// the lines. p5.brush composites once per colour change, and each composite has a fixed cost, so this is much faster.
function paintBatch(list) {
  const fills = list.filter(s => !s.line && (s.o.wash || s.o.fill)), inks = list.filter(s => !s.line && s.o.ink !== null), lines = list.filter(s => s.line);
  const byCol = (a, b) => ((a.o.wash || '') + (a.o.washOp || 255)).localeCompare((b.o.wash || '') + (b.o.washOp || 255));
  for (const s of fills.slice().sort(byCol)) { boilSeed(s.key + ' paint'); setPaint(s.pts, { ...s.o, ink: null }); }
  for (const s of inks) { boilSeed(s.key + ' ink'); paint(s.pts, { ink: s.o.ink, sw: s.o.sw, curv: s.o.curv }); }
  for (const s of lines.slice().sort((a, b) => (a.o.col || '').localeCompare(b.o.col || ''))) { boilSeed(s.key + ' paint'); drawLine(s); }
};
const over = (base, c, k) => mixCol(base, c, k);   // an opaque stand-in for a glaze over a known flat colour (no spectral cost)
const sh = (c, z) => { const k = shadeAt(z); return k > 0 ? mixCol(c, SET.dark, k) : c; };
const swAt = (z, base = 1) => base * clamp(scaleAt(z) / 260, .35, 1.25);

// ---------------------------------------------------------------- the backdrop: sky, distant hills, trees
function backdropShapes(t) {
  const c = CAMS, L = [], hz = c.Yh - 40;
  // the sky: lilac-blue above, warming to gold at the horizon (opaque bands with soft, wavering edges)
  const SKY = ['#A9B6CC', '#C4BDC6', '#DDC6B4', '#EDCFA6', '#F4D79E'];
  L.push(mkS('sky', rectPts(-80, -80, W + 160, H + 160), { wash: SKY[0], ink: null }));
  for (let i = 1; i < SKY.length; i++) {
    const y = hz - 620 + i * 125, P = [];
    for (let k = 0; k <= 12; k++) P.push([-80 + k * (W + 160) / 12, y + 14 * Math.sin(k * 1.3 + i * 2) + jitAt('sky' + i, k, 4)]);
    L.push(mkS('sky' + i, [...P, [W + 80, H + 80], [-80, H + 80]], { wash: SKY[i], ink: null }));
  }
  // hills to the right of the skene (Hymettos in the haze) and a nearer ridge
  L.push(mkS('hillFar', [[600, hz + 60], [1100, hz - 60], [1500, hz - 130], [1800, hz - 90], [2100, hz - 30], [2100, hz + 300], [600, hz + 300]].map(([x, y]) => [x + (c.Xp - 120) * .15, y]), { wash: SET.hillFar, ink: null }));
  const hn = [[900, hz + 70], [1300, hz + 10], [1650, hz - 30], [2000, hz + 20], [2100, hz + 60]].map(([x, y]) => [x + (c.Xp - 120) * .3, y]);
  L.push(mkS('hillNear', [...hn, [hn[4][0], hz + 400], [hn[0][0], hz + 400]], { wash: SET.hillNear, ink: null }));
  { const e = mkS('hillRidge', through(hn, 6), { hair: 2.2, col: mixCol(SET.hillNear, PAL.ink, .5) }); e.line = true; L.push(e); }
  // cypresses (tall flames) and olives (grey-green clumps on a short trunk) on the slope beyond the skene
  for (let i = 0; i < 5; i++) {
    const x = 6.7 + i * 1.25 + hash(i) * .4, z = -2.5 - hash(i + 9) * 3, cyp = i % 2 === 1;
    const [bx, by] = proj(x, 0, z), s = scaleAt(z), h = (cyp ? 5.2 + hash(i) : 3.2 + hash(i + 3)) * s, w = (cyp ? .62 : 2.0) * s;
    if (bx - w > W + 40) continue;
    if (cyp) L.push(mkS('tree' + i, through([[bx - w * .5, by], [bx - w * .52, by - h * .45], [bx - w * .18, by - h * .85], [bx, by - h], [bx + w * .2, by - h * .82], [bx + w * .52, by - h * .4], [bx + w * .5, by]], 4).map(([u, v]) => [u + jitAt('tree' + i, u, 1.5), v]), { wash: SET.treeDk, ink: PAL.ink, sw: .45 }));
    else {
      L.push(mkS('trunk' + i, [[bx - w * .05, by], [bx + w * .06, by], [bx + w * .03, by - h * .5], [bx - w * .03, by - h * .5]], { wash: '#6E5A48', ink: null }));
      for (const [k, dx, dy, r] of [[0, -.22, .62, .3], [1, .2, .66, .32], [2, 0, .82, .3]]) L.push(mkS('olive' + i + k, ellPts(bx + dx * w, by - dy * h, r * w, r * h * .55, 16).map(([u, v], j) => [u + jitAt('ol' + i + k, j, 2), v]), { wash: k === 2 ? '#8E9670' : SET.tree, ink: PAL.ink, sw: .4, curv: .4 }));
    }
  }
  return L;
}
// deterministic per-(key, index, boil frame) jitter, for shapes built in screen space
const jitAt = (key, i, a) => (hash(keyHash(key) + i * 7.31 + BOILN * 53.7) - .5) * 2 * a;

// ---------------------------------------------------------------- the ground: beaten earth
function groundShapes(t) {
  const L = [], g = (x, z) => [x, 0, z];
  const zn = Math.min(12, CAMS.cz - 1.2);   // the near edge, kept in front of the eye
  L.push(mk('earth', [g(-30, 0), g(30, 0), g(30, zn), g(-30, zn)], { wash: SET.earth, ink: null }, 2));
  L.push(mk('earthShade', [g(-30, 0), g(30, 0), g(30, .9), g(-30, .7)], { wash: over(SET.earth, SET.earthDk, .5), ink: null }, 2));   // the facade's shadow foot
  for (let i = 0; i < 14; i++) {   // dry-brush marks in the earth
    const x = -6 + hash(i * 3) * 14, z = .8 + hash(i * 5 + 1) * 4, l = .5 + hash(i) * 1.2;
    if (z > CAMS.cz - 2) continue;
    const s = mk('earthMark' + i, [g(x, z), g(x + l * .5, z + .02), g(x + l, z - .01)], { sw: .5, col: i % 2 ? SET.earthDk : SET.earthLt, br: 'dry', curv: .5 });
    s.line = true; L.push(s);
  }
  return L;
}

// ---------------------------------------------------------------- the skene facade
// The opening (where one sees into the skene): left edge = the left jamb's face edge, right edge = the back of the
// right jamb's inner face (we see that face from the left), top = the back of the lintel's underside.
function openingPts() {
  boilSeed('opening');
  const d = GEO.doorW / 2, hz = GEO.hingeZ, fz = .06;
  return PJ([[-d, 0, fz], [-d, GEO.doorH, fz], [-d + .01, GEO.doorH, hz], [d, GEO.doorH, hz], [d, 0, hz]], 1);
}
// the facade's colour along x: the low sun comes from the right, so the wall warms and brightens toward the right
const wallCol = x => mixCol(SET.woodDk, '#DCA668', smoother(clamp((x + 7) / 13)));
function facadeShapes(t) {
  const G = { wall: [], tone: [], seams: [], shade: [], rails: [], posts: [], lit: [], frameBack: [], frame: [], frameLit: [] };
  const d = GEO.doorW / 2, H_ = GEO.facadeH, X = GEO.facadeW / 2, jw = GEO.jambW, fz = .06, OP = openingPts();
  // the wall in vertical bands (the light gradient), with the doorway left open
  const bands = [-X, -4.6, -3.2, -d - jw, d + jw, 3.2, 4.6, X];
  for (let i = 0; i < bands.length - 1; i++) {
    const a = bands[i], b = bands[i + 1], c = wallCol((a + b) / 2);
    if (a === -d - jw) G.wall.push(mk('wallTop', [[a, GEO.doorH + jw, 0], [b, GEO.doorH + jw, 0], [b, H_, 0], [a, H_, 0]], { wash: c, ink: null }, 1.2));
    else G.wall.push(mk('wall' + i, [[a, 0, 0], [b, 0, 0], [b, H_, 0], [a, H_, 0]], { wash: c, ink: null }, 1.2));
  }
  // weathered boards: a few planks a shade lighter or darker than the wall around them
  for (let i = 0; i < 11; i++) {
    const x0 = -X + .1 + hash(i * 7) * (2 * X - .8), w = .3 + .3 * Math.floor(hash(i * 3) * 2);
    if (x0 + w > -d - jw - .05 && x0 < d + jw + .05) continue;
    G.tone.push(mk('board' + i, [[x0, .03, 0], [x0 + w, .03, 0], [x0 + w, H_ - .55, 0], [x0, H_ - .55, 0]], { wash: over(wallCol(x0 + w / 2), i % 2 ? SET.woodShade : '#F0C488', .22), ink: null }, .8));
  }
  for (let x = -X + .32; x < X; x += .32) {
    const k = 'seam' + x.toFixed(2), top = Math.abs(x) < d + jw;
    const s2 = top ? mk(k, [[x, GEO.doorH + jw, 0], [x, (GEO.doorH + H_) / 2, 0], [x, H_ - .55, 0]], { hair: swAt(0, 1.6), col: mixCol(SET.woodShade, wallCol(x), .25) }, .7)
                   : mk(k, [[x, .05, 0], [x + .004, H_ * .25, 0], [x, H_ * .5, 0], [x - .003, H_ * .75, 0], [x, H_ - .55, 0]], { hair: swAt(0, 1.6), col: mixCol(SET.woodShade, wallCol(x), .25) }, .7);
    s2.line = true; G.seams.push(s2);
  }
  // shadows the low sun casts on the wall: under the eave, under the rails, to the left of each post and the frame
  const shadeCol = x => over(wallCol(x), '#4A2E22', .38);
  G.shade.push(mk('eaveShade', [[-X, H_ - .62, 0], [X, H_ - .5, 0], [X, H_ - .1, 0], [-X, H_ - .1, 0]], { wash: shadeCol(0), ink: null }, 1.2));
  for (const [k, y] of [['railLo', .5], ['railHi', 4.25]]) for (const [a, b] of [[-X, -d - jw], [d + jw, X]]) G.shade.push(mk(k + 'Sh' + a, [[a, y - .2, 0], [b, y - .2, 0], [b, y - .1, 0], [a, y - .1, 0]], { wash: shadeCol((a + b) / 2), ink: null }, .8));
  for (const x of [-6, -4, -2.5, 2.5, 4, 6]) G.shade.push(mk('postSh' + x, [[x - .3, .0, 0], [x - .11, .0, 0], [x - .11, H_ - .55, 0], [x - .32, H_ - .55, 0]], { wash: shadeCol(x - .2), ink: null }, .8));
  G.shade.push(mk('jambShL', [[-d - jw - .26, 0, 0], [-d - jw, 0, 0], [-d - jw, GEO.doorH + jw, 0], [-d - jw - .3, GEO.doorH + jw, 0]], { wash: shadeCol(-d - jw - .15), ink: null }, .8));
  // rails, posts and their sunlit edges
  for (const [k, y] of [['railLo', .5], ['railHi', 4.25]]) for (const [a, b] of [[-X, -d - jw], [d + jw, X]]) {
    G.rails.push(mk(k + a, [[a, y - .1, .05], [b, y - .1, .05], [b, y + .1, .05], [a, y + .1, .05]], { wash: over(SET.rail, '#E0AE70', .3 * smoother(clamp(((a + b) / 2 + 7) / 13))), ink: null }, 1));
    for (const [e, yy] of [['T', y + .1], ['B', y - .1]]) { const l = mk(k + a + e, [[a, yy, .05], [(a + b) / 2, yy + .004, .05], [b, yy, .05]], { hair: swAt(0, e === 'B' ? 2.4 : 1.6), col: PAL.ink }, .8); l.line = true; G.rails.push(l); }
  }
  for (const x of [-6, -4, -2.5, 2.5, 4, 6]) {
    G.posts.push(mk('post' + x, [[x - .11, 0, .07], [x + .11, 0, .07], [x + .11, H_ - .12, .07], [x - .11, H_ - .12, .07]], { wash: over(SET.post, '#D7A56A', .25 * smoother(clamp((x + 7) / 13))), ink: PAL.ink, sw: swAt(0, .75) }, 1));
    G.lit.push(mk('postLit' + x, [[x + .045, .02, .07], [x + .1, .02, .07], [x + .1, H_ - .14, .07], [x + .045, H_ - .14, .07]], { wash: over(SET.post, SET.postLit, .55 + .3 * smoother(clamp((x + 7) / 13))), ink: null }, .8));
  }
  G.lit.push(mk('eave', [[-X - .3, H_ - .12, .35], [X + .3, H_ - .12, .35], [X + .3, H_ + .12, .35], [-X - .3, H_ + .12, .35]], { wash: SET.frame, ink: null }, 1.2));
  { const e = mk('eaveEdge', [[-X - .3, H_ - .12, .35], [0, H_ - .125, .35], [X + .3, H_ - .12, .35]], { hair: swAt(.3, 2.6), col: PAL.ink }, 1); e.line = true; G.lit.push(e); }
  // the door frame: the right jamb's inner face and the lintel's underside (seen from the left, from below), then the
  // jambs and lintel in front, the sunlit edges, and the sill
  G.frameBack.push(mk('jambInR', [[d, 0, fz], [d, GEO.doorH, fz], [d, GEO.doorH, GEO.hingeZ], [d, 0, GEO.hingeZ]], { wash: SET.woodShade, ink: PAL.ink, sw: swAt(0, .6) }, .8));
  G.frameBack.push(mk('lintelUnder', [[-d, GEO.doorH, fz], [d, GEO.doorH, fz], [d, GEO.doorH, GEO.hingeZ], [-d, GEO.doorH, GEO.hingeZ]], { wash: '#4E3424', ink: PAL.ink, sw: swAt(0, .5) }, .8));
  G.frameBack.push(mk('sill', [[-d, 0, fz], [d, 0, fz], [d, .05, GEO.hingeZ], [-d, .05, GEO.hingeZ]], { wash: SET.woodDk, ink: PAL.ink, sw: swAt(0, .5) }, .8));
  G.frame.push(mk('jambL', [[-d - jw, 0, fz], [-d, 0, fz], [-d, GEO.doorH, fz], [-d - jw, GEO.doorH, fz]], { wash: SET.frame, ink: PAL.ink, sw: swAt(0, .85) }, 1));
  G.frame.push(mk('jambR', [[d, 0, fz], [d + jw, 0, fz], [d + jw, GEO.doorH, fz], [d, GEO.doorH, fz]], { wash: over(SET.frame, '#B98A5A', .25), ink: PAL.ink, sw: swAt(0, .85) }, 1));
  G.frameLit.push(mk('lintel', [[-d - jw - .15, GEO.doorH, fz], [d + jw + .15, GEO.doorH, fz], [d + jw + .15, GEO.doorH + jw + .02, fz], [-d - jw - .15, GEO.doorH + jw + .02, fz]], { wash: SET.frame, ink: PAL.ink, sw: swAt(0, .85) }, 1));
  for (const x of [-d - jw * .5, d + jw * .5]) G.frameLit.push(mk('frameLit' + x, [[x + .03, .02, fz], [x + .09, .02, fz], [x + .09, GEO.doorH - .02, fz], [x + .03, GEO.doorH - .02, fz]], { wash: over(SET.frame, SET.postLit, .5), ink: null }, .8));
  return { G, OP, L: Object.values(G).flat() };
}
const paintFacade = F => { for (const k of ['wall', 'tone', 'seams', 'shade', 'rails', 'posts', 'lit', 'frameBack', 'frame', 'frameLit']) paintBatch(F.G[k]); };

// ---------------------------------------------------------------- the interior (seen through the doorway)
function interiorShapes(t, OP) {
  const L = [];
  L.push(mkS('interior', OP.map(p => p.slice()), { wash: SET.dark, ink: null }));
  // the floor going back, with the light that spills in through the door
  L.push(mk('inFloor', [[-1.5, 0, GEO.hingeZ], [1.5, 0, GEO.hingeZ], [1.5, 0, -4.6], [-1.5, 0, -4.6]], { wash: SET.darkFloor, ink: null }, 1));
  const op = smoother(seg(t, TIMES.doors[0] + .2, TIMES.doors[1]));
  if (op > .02) L.push(mk('inLight', [[-1.0, 0, GEO.hingeZ], [1.38, 0, GEO.hingeZ], [1.1, 0, -1.6], [-.5, 0, -1.9]], { wash: '#6A4A35', washOp: 150 * op, ink: null }, 1));
  L.push(mk('inBack', [[-1.5, 0, -4.6], [1.5, 0, -4.6], [1.5, 3.2, -4.6], [-1.5, 3.2, -4.6]], { wash: '#261B1C', ink: null }, 1));
  return L;
}

// ---------------------------------------------------------------- the door leaves (hinged at the inner face, swinging in)
function leafShapes(t) {
  const L = [], A = doorAngle(t), d = GEO.doorW / 2, w = GEO.leafW, hz = GEO.hingeZ, H_ = GEO.doorH - .02;
  for (const side of [-1, 1]) {
    const a = side < 0 ? A.L : A.R, hx = side * d, fx = hx - side * w * Math.cos(a), fzz = hz - w * Math.sin(a);
    const at = (u, y) => [lerp(hx, fx, u), y, lerp(hz, fzz, u)];
    const turn = Math.sin(a), lit = side > 0 ? 1 - turn * .6 : 1 - turn;   // turning away from the light, into the dark
    const col = mixCol(mixCol(SET.leaf, SET.leafDk, 1 - lit), SET.dark, shadeAt(fzz) * .9);
    const key = 'leaf' + side, pts = [at(0, .03), at(1, .03), at(1, H_), at(0, H_)];
    L.push(mk(key, pts, { wash: col, ink: PAL.ink, sw: swAt(hz, .8) }, 1));
    // boards, iron straps and studs, the ring pull (all on the face we see)
    const dark = mixCol(col, PAL.ink, .35);
    for (let i = 1; i < 4; i++) { const s = mk(key + 'b' + i, [at(i / 4, .05), at(i / 4, H_ - .02)], { sw: swAt(hz, .35), col: dark, br: 'inkfine', curv: 0 }, .7); s.line = true; L.push(s); }
    for (const y of [.55, 1.6, 2.65]) L.push(mk(key + 's' + y, [at(.02, y - .05), at(.96, y - .05), at(.96, y + .05), at(.02, y + .05)], { wash: mixCol(SET.iron, SET.dark, shadeAt(fzz) * .5), ink: null }, .6));
    if (a < 1.2) L.push(mk(key + 'ring', [at(.86, 1.45), at(.93, 1.45), at(.93, 1.55), at(.86, 1.55)], { wash: SET.iron, ink: PAL.ink, sw: swAt(hz, .4) }, .5));
  }
  return L;
}

// ---------------------------------------------------------------- world shapes (for the pieces that pass through the door)
// The platform and its tableau cross the facade plane, so they are kept as WORLD polygons: painted once in full under
// the facade (the left jamb hides what is still inside), then again over it, clipped to the part in front of the
// facade (z >= FRONT_Z). Their boil is a hash of (key, vertex, boil frame), so a clipped copy lies exactly on the full one.
const FRONT_Z = .06;
const keyHash = key => { let h = 2166136261; for (const c of key) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return (h >>> 0) / 4294967296 * 1000; };
const vj = (key, i, j) => { const b = keyHash(key) + i * 13.17 + BOILN * 91.3; return [(hash(b) - .5) * 2 * j, (hash(b + 4.1) - .5) * 2 * j]; };
const mkW = (key, world, o = {}, j = 1, line = false) => ({ key, world, o, j, line });
function clipFront(P, closed) {   // Sutherland-Hodgman against z >= FRONT_Z; each vertex carries [x, y, z, jx, jy, seam]
  const out = [], N = P.length, inside = p => p[2] >= FRONT_Z, cut = (a, b) => { const u = (FRONT_Z - a[2]) / (b[2] - a[2]); return a.map((v, i) => i < 5 ? lerp(v, b[i], u) : 1); };
  for (let i = 0; i < (closed ? N : N - 1); i++) {
    const a = P[i], b = P[(i + 1) % N];
    if (i === 0 && inside(a)) out.push(a);
    if (inside(a) && inside(b)) out.push(b);
    else if (inside(a) && !inside(b)) out.push(cut(a, b));
    else if (!inside(a) && inside(b)) { out.push(cut(a, b)); out.push(b); }
  }
  if (closed && out.length && out[out.length - 1] === P[0]) out.pop();
  return out;
}
// world shape -> screen shape (null if nothing is left); front = only the part in front of the facade, without ink on the cut
function projW(s, front = false) {
  let P = s.world.map((p, i) => [...p, ...vj(s.key, i, s.j), 0]);
  if (front) { if (P.every(p => p[2] < FRONT_Z)) return null; if (P.some(p => p[2] < FRONT_Z)) P = clipFront(P, !s.line); if (P.length < (s.line ? 2 : 3)) return null; }
  const pts = P.map(p => { const q = proj(p[0], p[1], p[2]); return [q[0] + p[3], q[1] + p[4]]; });
  if (s.line) return { key: s.key, pts, o: s.o, line: true };
  const cutEdge = front && P.some(p => p[5]);
  return { key: s.key, pts, o: cutEdge ? { ...s.o, ink: null } : s.o, rim: cutEdge && s.o.ink !== null ? P.map(p => p[5]) : null };
}
function paintW(list, front = false) {
  for (const s of list) {
    const q = projW(s, front); if (!q) continue;
    boilSeed(s.key + (front ? ' front' : ' paint'));
    if (q.line) { inkLine(q.pts, q.o.sw ?? 1, q.o.col || PAL.ink, q.o.br || 'ink', q.o.curv ?? .3); continue; }
    setPaint(q.pts, q.o);
    if (q.rim) {   // the outline, except along the cut
      const n = q.pts.length; let run = [];
      for (let k = 0; k <= n; k++) { const i = k % n, j2 = (k + 1) % n; if (!(q.rim[i] && q.rim[j2])) { if (!run.length) run.push(q.pts[i]); run.push(q.pts[j2]); } else if (run.length) { inkLine(run, (s.o.sw ?? 1) * .9, s.o.ink || PAL.ink, 'ink', 0); run = []; } }
      if (run.length > 1) inkLine(run, (s.o.sw ?? 1) * .9, s.o.ink || PAL.ink, 'ink', 0);
    }
  }
}

// ---------------------------------------------------------------- the ekkyklema and its tableau
// returns { L: world shapes, zf, zb (the deck's front and back edges), couchTop (world point of the mattress-top centre) }
function platformShapes(t) {
  const L = [], zf = platFront(t), zb = zf - GEO.platD, hw = GEO.platW / 2, y1 = GEO.deckY, y0 = y1 - GEO.deckT, r = GEO.wheelR;
  const zs = (z, c) => sh(c, z), sw = swAt(zf, .85), ang = wheelAngle(t), P = (k, w, o, j = .8) => L.push(mkW(k, w, o, j)), Ln = (k, w, o, j = .5) => L.push(mkW(k, w, o, j, true));
  // the shadow it casts on the ground once it is out in the light (the sun is low, front right)
  const out = clamp(zf / 1.0);
  if (out > 0) P('platShadow', [[-hw - .5, 0, zf - .05], [hw - .2, 0, zf + .08], [hw - .4, 0, Math.max(zb, .1)], [-hw - .9, 0, Math.max(zb, .1)]], { wash: '#5A3E2C', washOp: 70 * out, ink: null }, 1);
  const wheel = (key, x, zc, near) => {
    const pts = []; for (let i = 0; i < 18; i++) { const a = i / 18 * TAU; pts.push([x, r + Math.cos(a) * r, zc + Math.sin(a) * r]); }
    P(key, pts, { wash: zs(zc, near ? SET.wheel : mixCol(SET.wheel, PAL.ink, .3)), ink: zs(zc, PAL.ink), sw: sw * .8 }, .5);
    for (const k of [0, 1]) { const a = ang + k * Math.PI / 2; Ln(key + 'seam' + k, [[x, r + Math.cos(a) * r * .92, zc + Math.sin(a) * r * .92], [x, r - Math.cos(a) * r * .92, zc - Math.sin(a) * r * .92]], { sw: sw * .5, col: zs(zc, '#3E2C22'), br: 'inkfine', curv: 0 }, .3); }
    P(key + 'hub', [[x, r + .03, zc], [x, r, zc + .03], [x, r - .03, zc], [x, r, zc - .03]], { wash: zs(zc, SET.tyre), ink: null }, .3);
    const m = [x, r + Math.cos(ang) * r * .68, zc + Math.sin(ang) * r * .68];   // a paint mark on the rim: the turning reads
    P(key + 'mark', [[m[0], m[1] + .025, m[2]], [m[0], m[1], m[2] + .025], [m[0], m[1] - .025, m[2]], [m[0], m[1], m[2] - .025]], { wash: zs(zc, '#E0BC84'), ink: null }, .2);
  };
  wheel('wheelRB', GEO.wheelX, zb + .25, false); wheel('wheelRF', GEO.wheelX, zf - .25, false);
  P('under', [[-hw + .1, y0, zf - .05], [hw - .1, y0, zf - .05], [hw - .1, .1, zf - .1], [-hw + .1, .1, zf - .1]], { wash: zs(zf, '#2E211C'), ink: null }, .6);
  P('deckSide', [[-hw, y0, zf], [-hw, y0, zb], [-hw, y1, zb], [-hw, y1, zf]], { wash: zs((zf + zb) / 2, SET.deckDk), ink: zs(zf, PAL.ink), sw }, .8);
  wheel('wheelLB', -GEO.wheelX, zb + .25, true); wheel('wheelLF', -GEO.wheelX, zf - .25, true);
  // the deck top in strips, so the part still inside stays dark while the front comes into the light
  const n = 5;
  for (let i = 0; i < n; i++) { const za = lerp(zb, zf, i / n), zz = lerp(zb, zf, (i + 1) / n); P('deck' + i, [[-hw, y1, za], [hw, y1, za], [hw, y1, zz], [-hw, y1, zz]], { wash: zs((za + zz) / 2, SET.deck), ink: null }, .6); }
  for (let i = 1; i < 8; i++) { const x = -hw + i * GEO.platW / 8; Ln('plank' + i, [[x, y1, zb + .02], [x, y1, (zb + zf) / 2], [x, y1, zf - .02]], { sw: sw * .45, col: zs((zf + zb) / 2, '#8A6040'), br: 'inkfine', curv: 0 }, .4); }
  Ln('deckEdgeL', [[-hw, y1, zb], [-hw, y1, zf]], { sw, col: zs(zf, PAL.ink), br: 'ink', curv: 0 }, .6);
  Ln('deckEdgeB', [[-hw, y1, zb], [hw, y1, zb]], { sw, col: zs(zb, PAL.ink), br: 'ink', curv: 0 }, .6);
  Ln('deckEdgeR', [[hw, y1, zb], [hw, y1, zf]], { sw, col: zs(zf, PAL.ink), br: 'ink', curv: 0 }, .6);
  P('deckFront', [[-hw, y0, zf], [hw, y0, zf], [hw, y1, zf], [-hw, y1, zf]], { wash: zs(zf, SET.deckDk), ink: zs(zf, PAL.ink), sw }, .8);
  // the couch (kline): back legs, the raised head end, frame, mattress with a striped cover, a pillow, front legs
  const cz = zf + GEO.couchZ, cd = GEO.couchD / 2, cl = GEO.couchL / 2, cy0 = y1 + .32, cy1 = y1 + GEO.couchH, zc = cz;
  const leg = (key, x, z) => P(key, [[x - .03, y1, z], [x + .03, y1, z], [x + .045, cy0 - .16, z], [x + .055, cy0 - .08, z], [x + .045, cy0, z], [x - .045, cy0, z], [x - .055, cy0 - .08, z], [x - .045, cy0 - .16, z]], { wash: zs(z, SET.couchDk), ink: zs(z, PAL.ink), sw: sw * .7 }, .4);
  leg('legRB', cl - .1, cz - cd + .06); leg('legLB', -cl + .1, cz - cd + .06);
  P('headEnd', [[cl - .12, cy0, cz - cd], [cl + .02, cy0, cz - cd], [cl + .1, cy1 + .32, cz], [cl - .02, cy1 + .26, cz], [cl - .12, cy1, cz]], { wash: zs(zc, SET.couch), ink: zs(zc, PAL.ink), sw: sw * .8, curv: .5 }, .5);
  P('mattTop', [[-cl + .03, cy1, cz - cd + .05], [cl - .08, cy1, cz - cd + .05], [cl - .08, cy1, cz + cd - .02], [-cl + .03, cy1, cz + cd - .02]], { wash: zs(zc, SET.linen), ink: null }, .5);
  P('frame', [[-cl, cy0, cz + cd], [cl, cy0, cz + cd], [cl, cy0 + .1, cz + cd], [-cl, cy0 + .1, cz + cd]], { wash: zs(zc, SET.couch), ink: zs(zc, PAL.ink), sw: sw * .8 }, .5);
  P('mattFront', [[-cl + .02, cy0 + .1, cz + cd], [cl - .06, cy0 + .1, cz + cd], [cl - .06, cy1, cz + cd - .02], [-cl + .02, cy1, cz + cd - .02]], { wash: zs(zc, SET.linen), ink: zs(zc, PAL.ink), sw: sw * .6 }, .5);
  for (let i = 0; i < 3; i++) { const yy = cy0 + .113 + i * .012; Ln('stripe' + i, [[-cl + .04, yy, cz + cd + .001], [cl - .08, yy, cz + cd + .001]], { sw: sw * .5, col: zs(zc, i === 1 ? SET.stripe2 : SET.stripe), br: 'inkfine', curv: 0 }, .3); }
  P('pillow', [[cl - .55, cy1, cz + .2], [cl - .1, cy1, cz + .26], [cl - .06, cy1 + .1, cz + .2], [cl - .14, cy1 + .24, cz + .06], [cl - .48, cy1 + .26, cz + .02], [cl - .58, cy1 + .1, cz + .16]], { wash: zs(zc, SET.pillow), ink: zs(zc, PAL.ink), sw: sw * .7, curv: .5 }, .5);
  Ln('pillowStripe', [[cl - .5, cy1 + .14, cz + .2], [cl - .12, cy1 + .16, cz + .22]], { sw: sw * .6, col: zs(zc, '#E8D9B5'), br: 'inkfine', curv: .4 }, .3);
  leg('legRF', cl - .1, cz + cd); leg('legLF', -cl + .1, cz + cd);
  // the stool with the cup, at the front of the deck by the head end
  const sx = .86, sz = zf - .2, st = y1 + .36;
  for (const [k, dx] of [['stoolL', -.13], ['stoolR', .13]]) P(k, [[sx + dx - .02, y1, sz], [sx + dx + .02, y1, sz], [sx + dx * .6 + .02, st, sz], [sx + dx * .6 - .02, st, sz]], { wash: zs(sz, SET.stool), ink: zs(sz, PAL.ink), sw: sw * .6 }, .4);
  P('stoolTop', [[sx - .18, st, sz - .14], [sx + .18, st, sz - .14], [sx + .18, st, sz + .1], [sx - .18, st, sz + .1]], { wash: zs(sz, mixCol(SET.stool, '#C99760', .4)), ink: zs(sz, PAL.ink), sw: sw * .6 }, .4);
  P('stoolEdge', [[sx - .18, st - .035, sz + .1], [sx + .18, st - .035, sz + .1], [sx + .18, st, sz + .1], [sx - .18, st, sz + .1]], { wash: zs(sz, SET.stool), ink: zs(sz, PAL.ink), sw: sw * .5 }, .3);
  const cupY = st, cupZ = sz - .02;   // a black-glaze kylix: a shallow bowl on a short stem, two handles
  P('cupFoot', [[sx - .045, cupY, cupZ], [sx + .045, cupY, cupZ], [sx + .015, cupY + .04, cupZ], [sx - .015, cupY + .04, cupZ]], { wash: zs(cupZ, SET.cup), ink: null }, .2);
  P('cupBowl', [[sx - .12, cupY + .09, cupZ], [sx + .12, cupY + .09, cupZ], [sx + .08, cupY + .05, cupZ], [sx, cupY + .038, cupZ], [sx - .08, cupY + .05, cupZ]], { wash: zs(cupZ, SET.cup), ink: zs(cupZ, PAL.ink), sw: sw * .4, curv: .4 }, .2);
  for (const sd of [-1, 1]) Ln('cupHandle' + sd, [[sx + sd * .11, cupY + .08, cupZ], [sx + sd * .155, cupY + .09, cupZ], [sx + sd * .13, cupY + .062, cupZ]], { sw: sw * .45, col: zs(cupZ, SET.cup), br: 'ink', curv: .6 }, .2);
  Ln('cupGlint', [[sx - .07, cupY + .083, cupZ], [sx + .03, cupY + .085, cupZ]], { sw: sw * .4, col: zs(cupZ, '#E2D2B0'), br: 'inkfine', curv: .3 }, .2);
  return { L, zf, zb, couchTop: [0, cy1, cz], stool: [sx, st, sz] };
}

// ---------------------------------------------------------------- occluders for the cast pass
// What hides a character at depth z: the facade around the opening (anything inside the skene), the door leaves (while
// they stand between), and the platform with its tableau (for whatever is behind its back edge: the stagehands).
function occluders(t, z) {
  const O = [], d = GEO.doorW / 2;
  if (z < GEO.hingeZ + .02) O.push({ outside: openingPts() });
  const A = doorAngle(t);
  for (const side of [-1, 1]) { const a = side < 0 ? A.L : A.R, fzz = GEO.hingeZ - GEO.leafW * Math.sin(a); if (z < fzz + .05) O.push({ shape: leafShapes(t).find(s => s.key === 'leaf' + side) }); }
  const P = platformShapes(t);
  if (z < P.zb) for (const s of P.L) if (!s.line && s.key !== 'platShadow' && s.o.wash) O.push({ shape: projW(s) });
  return O;
}
