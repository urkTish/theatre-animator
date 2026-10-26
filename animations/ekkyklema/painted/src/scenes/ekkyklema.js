// ekkyklema.js: the sample. One continuous shot, 15 s (see STORYBOARD.md): the actor knocks, the doors swing inward,
// the platform rolls out with Euripides on his couch, the actor beckons, Euripides waves him off, the actor gives up.
// The set is painted in the plate pass, the characters in the cast pass (src/layers.js); trackAt(t) gives tracks.json.
(() => {
  const DOORS_OPEN = TIMES.doors[1] + .05;   // after this the open leaves lie beside the platform, not in front of it
  const spaceZ = (space, t) => space === 'platform' ? platFront(t) : 0;
  // a slot at time t: its rig, its place in the world and on screen, its light
  function slotAt(name, t) {
    const S = CAST.slots[name], ev = evalTrack(S.motion, t, spaceZ), R = rigPerson(S.body, ev.P);
    let [x, , z] = ev.root, y = 0;
    if (S.body.body === 'recliner') y = GEO.deckY + GEO.couchH;
    const [sx, sy, k] = proj(x, y, z);
    return { name, S, R, x, y, z, sx, sy, k, env: { shade: shadeFig(z), key: name } };
  }
  const NAMES = ['standing_actor', 'reclining_figure', 'stagehand_1', 'stagehand_2'];
  // ---------------------------------------------------------------- plate: the set, in depth order
  function paintPlate(t) {
    const X = window.EXP || {};
    if (!X.noBg) paintShapes(backdropShapes(t));
    if (!X.noGlow) { boilSeed('sun'); const sp = proj(30, 6, -60); glow(sp[0], sp[1], 520, '#FFC77A', .55); }
    if (!X.noGround) paintShapes(groundShapes(t));
    const F = facadeShapes(t), P = platformShapes(t);
    if (!X.noInt) paintShapes(interiorShapes(t, F.OP));
    if (!X.noPlat) { if (t < DOORS_OPEN) { paintW(P.L); paintShapes(leafShapes(t)); } else { paintShapes(leafShapes(t)); paintW(P.L); } }
    if (!X.noFacade) paintFacade(F);
    if (!X.noPlat) paintW(P.L, true);   // the part of the platform and tableau that is out in front of the facade
    knockMarks(t);
  }
  // the knock, as painted marks on the door where the knuckles land (placed from the rig, so the same for every look)
  function knockMarks(t) {
    for (const tk of TIMES.knock) {
      const a = t - tk; if (a < 0 || a > .2) continue;
      const s = slotAt('standing_actor', tk), h = s.R.flip ? s.R.anchors.hand_r : s.R.anchors.hand_r, p = [s.sx + (s.R.flip ? -1 : 1) * h[0] * s.k, s.sy - h[1] * s.k];
      const k = 1 - a / .2, r0 = 22 + 60 * a, r1 = r0 + 26 * k;
      boilSeed('knock' + tk);
      for (const ang of [-2.5, -3.1, 2.6]) inkLine([[p[0] + Math.cos(ang) * r0, p[1] + Math.sin(ang) * r0], [p[0] + Math.cos(ang) * r1, p[1] + Math.sin(ang) * r1]], 1.1 * k + .2, PAL.ink, 'ink', 0);
    }
  }
  // ---------------------------------------------------------------- cast: the characters, back to front, held out
  function paintCast(t) {
    const L = NAMES.map(n => slotAt(n, t)).sort((a, b) => a.z - b.z);
    for (const s of L) {
      paintPerson(s.R, lookFor(s.name), s.env, s.sx, s.sy, s.k);
      holdOut(occluders(t, s.z));
    }
  }
  // ---------------------------------------------------------------- transitions
  const WIPE = [SET.frame, '#C98A3A'];
  function wipePolys(p) {   // the kit's brush wipe (timeline.js), as polygons, so the cast can be held out by it
    const out = []; if (p <= 0 || p >= 1) return out;
    const n = 5, bh = (H + 420) / n + 40, rot = -.1, c = Math.cos(rot), s = Math.sin(rot), R = ([x, y]) => [W / 2 + (x - W / 2) * c - (y - H / 2) * s, H / 2 + (x - W / 2) * s + (y - H / 2) * c];
    for (let i = 0; i < n; i++) {
      boilSeed('wipe' + i);
      const y0 = -230 + i * (H + 420) / n, d = [0, .14, .06, .18, .1][i];
      const q = p < .5 ? easeOut(clamp((p * 2 - d) / (1 - d))) : ease(clamp(((p - .5) * 2 - d) / (1 - d)));
      const x0 = p < .5 ? -300 : lerp(-300, W + 400, q), x1 = p < .5 ? lerp(-300, W + 400, q) : W + 400;
      if (x1 - x0 < 30) continue;
      const pts = [], rag = k => 40 + 50 * hash(i * 31 + k) + jit(12);
      for (let k = 0; k <= 8; k++) pts.push([lerp(x0, x1, k / 8), y0 + Math.sin(k * .9 + i) * 14 + jit(5)]);
      for (let k = 1; k < 9; k++) pts.push([x1 + rag(k) - 40, y0 + bh * k / 9]);
      for (let k = 8; k >= 0; k--) pts.push([lerp(x0, x1, k / 8), y0 + bh + Math.sin(k * .8 + i * 2) * 14 + jit(5)]);
      if (p >= .5) for (let k = 8; k > 0; k--) pts.push([x0 - rag(k + 20) + 40, y0 + bh * k / 9]);
      out.push({ key: 'wipe' + i, pts: pts.map(R), i });
    }
    return out;
  }
  // the door-shaped iris that closes over the tableau (the ending rhymes with the shut door of the opening)
  const IRIS = { t0: 13.95, hold: 14.45, t1: 14.96 };
  function headOn(name, t) { const s = slotAt(name, t), h = s.R.anchors.head; return [s.sx + (s.R.flip ? -1 : 1) * h[0] * s.k, s.sy - h[1] * s.k]; }
  function irisPts(t) {
    const he = headOn('reclining_figure', t), ha = headOn('standing_actor', t), u = ease(seg(t, IRIS.hold, IRIS.t1));   // holds on both, then closes onto Euripides
    const c = [lerp((he[0] + ha[0]) / 2, he[0], u), lerp((he[1] + ha[1]) / 2 + 120, he[1] + 40, u)], hh = t < IRIS.hold ? lerp(1500, 650, easeOut(seg(t, IRIS.t0, IRIS.hold))) : lerp(650, 0, easeIn(seg(t, IRIS.hold + .05, IRIS.t1))), hw = hh * GEO.doorW / GEO.doorH;
    boilSeed('iris');
    return [[c[0] - hw, c[1] + hh], [c[0] - hw, c[1] - hh], [c[0] + hw, c[1] - hh], [c[0] + hw, c[1] + hh]].map(([x, y]) => [x + jit(2), y + jit(2)]);
  }
  function transitions(t) {
    const wp = t < .62 ? .5 + t / 1.24 : 0, W_ = wipePolys(wp), iris = t > IRIS.t0;
    if (PASS === 'cast') { if (W_.length) holdOut(W_.map(w => ({ shape: { pts: w.pts, o: { ink: null } } }))); if (iris) { const ip = irisPts(t); if (Math.abs(ip[0][1] - ip[1][1]) < 4) holdOut([{ outside: [[0, 0], [1, 0], [1, 1]] }]); else holdOut([{ outside: dilate(ip, 2) }]); } return; }
    // (the kit's wipe adds a watercolour fill and charcoal hatching; in software GL that costs ~30 s a frame, so the
    // strokes are flat paint with a few dry-brush streaks of the other colour)
    for (const w of W_) {
      boilSeed('wipe paint' + w.i); setPaint(w.pts, { wash: w.i % 2 ? WIPE[0] : WIPE[1], ink: null });
      const ys = w.pts.map(p => p[1]), xs = w.pts.map(p => p[0]), y0 = Math.min(...ys), y1 = Math.max(...ys), x0 = Math.max(-50, Math.min(...xs)), x1 = Math.min(W + 50, Math.max(...xs));
      if (x1 - x0 > 80) for (let k = 0; k < 3; k++) { const y = lerp(y0, y1, .25 + k * .25) + jit(6); inkLine([[x0 + 30, y], [(x0 + x1) / 2, y + jit(8)], [x1 - 30, y + jit(6)]], 2.2, w.i % 2 ? WIPE[1] : WIPE[0], 'dry', .4); }
    }
    if (iris) { const ip = irisPts(t); boilSeed('iris paint'); if (Math.abs(ip[0][1] - ip[1][1]) < 4) paint(rectPts(-60, -60, W + 120, H + 120), { wash: '#2A1E1A', ink: null }); else irisShape(ip, '#2A1E1A'); }
  }
  // ---------------------------------------------------------------- the shot
  function shot(t, lt, dur) {
    if (PASS === 'all') return;   // frames are always painted as plate + cast (renderLayers); p5's own first draw is skipped
    CAMS = camAt(t);
    if (PASS !== 'cast') paintPlate(t);
    if (PASS !== 'plate') paintCast(t);
    transitions(t);
  }
  shots([[0, shot]]);

  // ---------------------------------------------------------------- tracks.json: per frame, per slot (from the rig only)
  const r4 = v => Math.round(v * 1e4) / 1e4, r1 = v => Math.round(v * 10) / 10;
  const occl = (O, p) => O.some(o => { const poly = o.outside || (o.shape && o.shape.pts); if (!poly) return false; const inside = pip(p, poly); return o.outside ? !inside : inside; });
  function pip([x, y], P) { let c = false; for (let i = 0, j = P.length - 1; i < P.length; j = i++) { const [xi, yi] = P[i], [xj, yj] = P[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; }
  window.trackAt = t => {
    CAMS = camAt(t); BOILN = Math.floor(t * BOIL);
    const out = { t: r4(t), frame: Math.round(t * CAST.fps), camera: { ...Object.fromEntries(Object.entries(CAMS).map(([k, v]) => [k, r4(v)])), model: 'pinhole, axis along -z, lens-shifted: X = Xp + (x - cx)*F/(cz - z), Y = Yh - (y - cy)*F/(cz - z)' },
      props: { door_angle_deg: r1(doorAngle(t).R * 180 / Math.PI), platform_front_z: r4(platFront(t)), roll_distance: r4(rollDist(t)), wheel_angle_rad: r4(wheelAngle(t)) }, slots: {} };
    for (const n of NAMES) {
      const s = slotAt(n, t), R = s.R, fl = R.flip ? -1 : 1, O = occluders(t, s.z);
      const scr = ([lx, ly]) => [r1(s.sx + fl * lx * s.k), r1(s.sy - ly * s.k)];
      const A = R.anchors, swap = R.flip;   // anatomy: a mirrored drawing swaps which hand is which
      const anchors = { head: A.head, pelvis: A.pelvis, hand_r: swap ? A.hand_l : A.hand_r, hand_l: swap ? A.hand_r : A.hand_l, foot_r: swap ? A.foot_l : A.foot_r, foot_l: swap ? A.foot_r : A.foot_l };
      const scrA = {}; for (const k in anchors) { const p = scr(anchors[k]); scrA[k] = { x: p[0], y: p[1], occluded: occl(O, p) }; }
      out.slots[n] = { world: { x: r4(s.x), y: r4(s.y), z: r4(s.z) }, screen: { x: r1(s.sx), y: r1(s.sy) }, scale_px_per_m: r4(s.k),
        facing: { heading: r4(R.P.heading ?? 0), view: R.view, flip: !!R.flip, head_heading: r4(R.P.headHeading ?? R.P.heading ?? 0), head_view: R.hview, head_flip: !!R.hflip },
        light: { shade: r4(s.env.shade) }, anchors: scrA };
    }
    return out;
  };
})();
