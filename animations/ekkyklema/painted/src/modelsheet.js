// modelsheet.js: the characters' model sheets, as standalone loops (labels are fine here: reference, not the film).
//   node render.mjs --soft-gl --loop=model_actor --sheet=0.3 --cols=1 --w=1920 --out=...
// ?looks=B swaps every slot to its B look (the same rigs and poses).
(() => {
  // prime p5.brush's composite before the first real mark (otherwise the first wash of a sheet can come out white)
  const prime = () => { boilSeed('prime'); for (const c of ['#7A4B2C', '#A9432F']) paint([[2, 2], [8, 2], [8, 8], [2, 8]], { wash: c, ink: null }); flushBrush(); image(paperG, 0, 0); };
  const label = (txt, x, y, size = 22) => letter(txt, x, y, size, PAL.ink, { ink: false, alpha: .75, font: `${size}px Georgia, serif` });
  const floor = (y, x0 = 60, x1 = W - 60) => { boilSeed('floor' + y); inkLine([[x0, y + 4], [(x0 + x1) / 2, y + 2], [x1, y + 5]], .6, mixCol(PAL.paper, PAL.ink, .35), 'inkfine', .5); };
  const look = name => LOOKS[(window.LOOKSET === 'B' && LOOKS[name + '_B']) ? name + '_B' : name];
  const person = (slot, lookName, P, x, y, k, key) => { const R = rigPerson(slot, P); paintPerson(R, look(lookName), { key }, x, y, k); return R; };
  const ACT = { body: 'actor', height: 1.78 }, EUR = { body: 'recliner', height: 1.74 }, SH = { body: 'stagehand', height: 1.72 };
  // a plain couch to lie on (the real one is part of the set)
  function couch(x, y, k, key) {
    boilSeed(key);
    const P = pts => pts.map(([a, b]) => [x + a * k + jit(1), y - b * k + jit(1)]);
    for (const lx of [-1.0, .95]) paint(P([[lx - .045, -.45], [lx + .045, -.45], [lx + .055, -.1], [lx - .055, -.1]]), { wash: '#7A4B2C', ink: PAL.ink, sw: .7 });
    paint(P([[-1.1, -.13], [1.1, -.13], [1.1, -.03], [-1.1, -.03]]), { wash: '#8A5A34', ink: PAL.ink, sw: .7 });
    paint(P([[-1.06, -.03], [1.06, -.03], [1.04, .0], [-1.04, .0]]), { wash: '#E8D9B5', ink: PAL.ink, sw: .6 });
    paint(P([[.3, .0], [.82, .0], [.86, .1], [.8, .24], [.5, .27], [.34, .2]]), { wash: '#A9432F', ink: PAL.ink, sw: .6, curv: .5 });
  }
  LOOPS.model_actor = t => {
    prime();
    const k = 300, gy = 900, poses = [
      ['front', { heading: 0 }], ['3/4', { heading: .125 }], ['side', { heading: .25 }],
      ['waits (3/4 left)', { heading: -.125, headHeading: -.125, hip: -.02, r: { a: .35, e: .9, h: 'relax' }, l: { a: .3, e: 1.0, h: 'relax' } }],
      ['knocks', { heading: -.125, headHeading: -.25, lean: .06, r: { a: 1.45, e: .5, w: .2, h: 'fist' }, l: { a: .12, e: .15 } }],
      ['beckons', { heading: -.125, lean: .08, headTilt: .08, r: { a: 1.35, e: .35, w: .5, h: 'beckon', palm: true }, l: { a: .15, e: .2 } }],
      ['"come down!"', { heading: -.125, lean: .1, headTilt: .14, r: { a: .7, e: .25, w: .2, h: 'point' }, l: { a: .2, e: .3 } }],
      ['exasperated', { heading: 0, headHeading: 0, lean: -.03, headTilt: -.12, r: { a: 2.5, e: .35, w: .1, h: 'open' }, l: { a: 2.4, e: .45, w: .1, h: 'open' } }],
    ];
    poses.forEach(([name, P], i) => { const x = 140 + i * 235; person(ACT, 'dikaiopolis', P, x, gy, k, 'ma' + i); label(name, x, gy + 50); });
    floor(gy);
  };
  LOOPS.model_actor.len = 1;
  LOOPS.model_euripides = t => {
    prime();
    const k = 330, W_ = { hand: [.17, .33], h: 'hold', stylus: true, w: -.4 }, poses = [
      ['writing', { headHeading: 0, headTilt: .24, headDy: -.025, r: W_ }],
      ['looks up', { headHeading: .125, headTilt: -.05, r: W_ }],
      ['"no time"', { headHeading: .125, headTilt: -.1, lean: .03, r: { hand: [-.22, .8], bend: 1, h: 'open', w: .15 } }],
      ['waves it off', { headHeading: .125, headTilt: .05, r: { hand: [.52, .42], bend: -1, h: 'flat', w: .25 } }],
    ];
    poses.forEach(([name, P], i) => {
      const x = 560 + (i % 2) * 820, y = 400 + Math.floor(i / 2) * 470;
      couch(x, y, k, 'couch' + i); person(EUR, 'euripides', P, x, y, k, 'me' + i); label(name, x, y + 200);
    });
  };
  LOOPS.model_euripides.len = 1;
  LOOPS.model_stagehands = t => {
    prime();
    const k = 300, gy = 900, poses = [
      ['front', 'stagehand_a', { heading: 0 }], ['3/4', 'stagehand_a', { heading: .125 }], ['side', 'stagehand_a', { heading: .25 }],
      ['pushing', 'stagehand_a', { heading: 0, crouch: .45, headDown: true, headDy: -.07, r: { a: .35, e: -.9, h: 'flat' }, l: { a: .35, e: -.9, h: 'flat' }, feet: { r: { dx: -.06 }, l: { dx: .06 } } }],
      ['pushing (3/4)', 'stagehand_b', { heading: .125, crouch: .45, lean: .55, r: { a: 1.25, e: .15, h: 'flat' }, l: { a: 1.15, e: .2, h: 'flat' }, feet: { r: { dx: -.25 }, l: { dx: .12 } } }],
      ['slips away', 'stagehand_b', { heading: -.25, lean: .08, r: { a: .35 }, l: { a: -.3 }, feet: { r: { dx: .16 }, l: { dx: -.14, dy: .03 } } }],
      ['waits, crouched', 'stagehand_b', { heading: -.125, crouch: .35, lean: .15, r: { a: .5, e: .6 }, l: { a: .4, e: .8 } }],
    ];
    poses.forEach(([name, lk, P], i) => { const x = 160 + i * 265; person(SH, lk, P, x, gy, k, 'ms' + i); label(name, x, gy + 50); });
    floor(gy);
  };
  LOOPS.model_stagehands.len = 1;
})();
