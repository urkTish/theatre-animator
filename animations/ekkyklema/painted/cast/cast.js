// cast/cast.js: THE SWAP POINT. One entry per character slot.
//   body    the rig and its proportions (part of the motion, not of the look: tracks.json depends on it)
//   motion  the motion track, on the shared timeline (src/motion.js explains the format)
//   look    the name of a look in src/looks.js: what fills the slot. Change only this to re-cast a slot.
// LOOK_SETS name whole re-castings; render one with ?looks=B (render.mjs --looks=B). The background, camera, motion and
// tracks never read the look, so they come out identical (see sample/SWAP_PROOF.txt).
//
// Positions are metres: x along the facade (+ = the audience's right), z toward the audience (facade face = 0).
// 'platform' root keys are relative to the ekkyklema's deck front edge (they ride out with it); for the reclining
// figure the root is the middle of the couch's mattress top.
// Arms: in the 3/4 and side views 'r' is the near arm (drawn in front), 'l' the far one; tracks.json reports hands by
// anatomy (hand_r / hand_l), mirrored when a figure faces left.
const WRITE = { hand: [.17, .33], bend: -1, w: -.4, h: 'hold', stylus: true };
const CAST = {
  fps: 24, duration: 15,
  slots: {
    // ---------------------------------------------------------------- the masked actor who waits at the door
    standing_actor: {
      label: 'Standing masked actor (Dikaiopolis, Ar. Ach. 395-409): knocks, steps back, beckons, gives up',
      body: { body: 'actor', height: 1.78 },
      look: 'dikaiopolis',
      motion: {
        space: 'world', steps: true, idle: { breath: 1, sway: .8, seed: .3 },
        root: [[0, 1.6, .42], [2.75, 2.36, 1.02, .85], [7.4, 2.5, 1.14, .75], [9.95, 2.4, 1.08, .6]],
        keys: [
          [0, { heading: -.125, headHeading: -.125, lean: 0, hip: 0, crouch: 0, headTilt: 0, headDx: 0, headDy: 0,
                r: { a: .12, e: .35, w: 0, h: 'relax', palm: false }, l: { a: .1, e: .3, w: 0, h: 'relax' } }],
          [.85, { headHeading: 0, headTilt: -.05 }, .25],                    // an impatient glance at the audience...
          [1.4, { headHeading: -.125, headTilt: .02, hip: .02 }, .3],        // ...and back to the door
          [1.68, { lean: -.05, headHeading: -.25, r: { a: 1.25, e: 1.45, w: .25, h: 'fist' } }, .32, 'easeOut'],   // wind-up: fist back by the shoulder
          [2.03, { lean: .06, r: { a: 1.4, e: .2, w: .1 } }, .08, 'easeIn'],  // knock
          [2.13, { r: { a: 1.3, e: 1.2, w: .25 } }, .13, 'easeOut'],
          [2.33, { r: { a: 1.4, e: .2, w: .1 } }, .08, 'easeIn'],             // knock
          [2.43, { r: { a: 1.3, e: 1.1, w: .2 }, lean: 0 }, .14, 'easeOut'],
          [2.68, { r: { a: .3, e: .6, h: 'relax' }, lean: -.04, headHeading: -.125 }, .4],   // steps back to watch
          [3.25, { lean: 0, l: { a: .25, e: .5 } }, .5],
          [4.3, { lean: .07, headTilt: .08, headDy: -.01 }, .9],             // peers into the dark
          [5.6, { lean: -.05, headTilt: -.03, r: { a: .55, e: .8 }, l: { a: .45, e: .9 } }, .6],   // it's coming: leans back
          [8.5, { lean: 0, headTilt: .04, r: { a: .3, e: .5 }, l: { a: .25, e: .6 } }, .8],
          [9.95, { lean: .06, headTilt: .06 }, .4],                          // squares up to him
          [10.3, { lean: .09, r: { a: 1.35, e: .35, w: .45, h: 'beckon', palm: true } }, .3, 'backOut'],   // beckons
          [11.2, { lean: .12, headTilt: .14, r: { a: .75, e: .25, w: .2, h: 'point', palm: false } }, .25, 'backOut'],   // "come down!"
          [11.75, { lean: .04, headTilt: .06, r: { a: .4, e: .5, w: 0, h: 'relax' } }, .5],
          [12.0, { lean: -.03, headTilt: -.02 }, .35],                       // rebuffed
          [13.05, { heading: 0, headHeading: 0, lean: -.04, headTilt: -.14, r: { a: 2.5, e: .35, w: .1, h: 'open' }, l: { a: 2.4, e: .45, w: .1, h: 'open' } }, .3, 'backOut'],   // gives up, to the audience
          [13.75, { lean: .02, headTilt: .06, r: { a: .12, e: .15, w: 0, h: 'relax' }, l: { a: .12, e: .15, w: 0, h: 'relax' } }, .45],
          [14.3, { headTilt: -.03 }, .5],
        ],
        add: [[10.6, 11.15, 'r.w', .5, 2.6], [11.35, 11.62, 'r.a', .08, 4], [13.35, 13.75, 'r.w', .15, 5], [13.35, 13.75, 'l.w', .15, 5, 1.5]],
      },
    },
    // ---------------------------------------------------------------- Euripides on the couch, rolled out
    reclining_figure: {
      label: 'Reclining masked figure (Euripides, Ach. 399-409): writes, looks up, "no time to come down", writes on',
      body: { body: 'recliner', height: 1.74 },
      look: 'euripides',
      motion: {
        space: 'platform', idle: { breath: .8, sway: .4, seed: 1.3 },
        root: [[0, 0, GEO.couchZ, .6, 'platform']],
        keys: [
          [0, { headHeading: 0, headTilt: .22, headDy: -.02, headDx: 0, lean: 0, hip: 0, kneeUp: 0, r: { ...WRITE }, l: { hand: [.22, .3], bend: 1, w: 0, h: 'hold' } }],
          [5.5, { lean: .035 }, .3, 'easeOut'], [5.85, { lean: 0 }, .8],     // the jolt as it starts...
          [9.35, { lean: -.03 }, .25, 'easeOut'], [9.65, { lean: 0 }, .6],   // ...and as it stops
          [10.95, { r: { w: -.15 } }, .2],                                   // stops writing
          [11.12, { headTilt: -.04, headDy: 0 }, .3],                        // looks up
          [11.32, { headHeading: .125 }, .25],                               // turns to him
          [11.6, { lean: .03, r: { hand: [-.22, .8], bend: 1, w: .15, h: 'open', stylus: false } }, .35, 'backOut'],   // "no"
          [12.45, { r: { hand: [.52, .42], bend: -1, w: .25, h: 'flat' } }, .22, 'easeOut'],   // waves it off
          [12.72, { lean: 0, r: { ...WRITE } }, .4],                         // back to the tablet
          [12.8, { headHeading: 0, headTilt: .22, headDy: -.02 }, .45],
        ],
        add: [[0, 10.95, 'r.hand[0]', .012, 2.2], [0, 10.95, 'r.hand[1]', .006, 4.4, 1], [0, 10.95, 'headTilt', .02, .7],
              [11.95, 12.42, 'r.w', .3, 3.6], [13.1, 15, 'r.hand[0]', .012, 2.2], [13.1, 15, 'r.hand[1]', .006, 4.4, 1]],
      },
    },
    // ---------------------------------------------------------------- the stagehands: push from behind, unseen
    stagehand_1: {
      label: 'Stagehand (audience-left): pushes from behind, lets go at 8.1 s while the platform coasts its last 0.7 m, and slips sideways behind the left jamb and wall; never seen by the audience',
      body: { body: 'stagehand', height: 1.72 },
      look: 'stagehand_a',
      motion: {
        space: 'platform', steps: true, idle: { breath: 1.2, sway: .5, seed: 2.1 },
        root: [[0, -.55, -1.98, .6, 'platform'], [8.1, -.55, -1.42, .5], [8.5, -1.8, -1.5, .85], [9.6, -2.9, -1.6, 1.2]],
        keys: [
          [0, { heading: 0, headHeading: 0, crouch: .32, lean: 0, headDy: 0, headDown: false, r: { a: .5, e: .6, w: 0, h: 'relax' }, l: { a: .4, e: .8, w: 0, h: 'relax' } }],
          [5.1, { crouch: .46, headDy: -.07, headDown: true, r: { a: .35, e: -.9, h: 'flat' }, l: { a: .35, e: -.9, h: 'flat' } }, .35],   // braces, pushes
          [8.1, { crouch: .3, headDy: -.03, headDown: false, r: { a: .3, e: .4, h: 'relax' }, l: { a: .25, e: .5, h: 'relax' } }, .3],   // lets go, stays low
          [8.42, { heading: -.25, headHeading: -.25, crouch: .3, lean: .2 }, .15],   // turns, sneaks behind the left jamb
          [9.7, { crouch: .05, lean: .06 }, .5],
        ],
        add: [[5.5, 8.1, 'bob', .012, 1.6], [8.5, 10.8, 'r.a', .35, 1.6], [8.5, 10.8, 'l.a', .35, 1.6, Math.PI]],
      },
    },
    stagehand_2: {
      label: 'Stagehand (audience-right): pushes from behind, lets go at 8.18 s, backs past the open leaf\'s end and slips behind it and the wall; never seen by the audience',
      body: { body: 'stagehand', height: 1.75 },
      look: 'stagehand_b',
      motion: {
        space: 'platform', steps: true, idle: { breath: 1.1, sway: .6, seed: 3.4 },
        root: [[0, .6, -1.98, .6, 'platform'], [8.18, .6, -1.38, .5], [8.6, .7, -1.72, .5], [9.12, 3.1, -1.78, 1.25], [10.4, 3.9, -1.85, .8]],
        keys: [
          [0, { heading: 0, headHeading: 0, crouch: .3, lean: 0, headDy: 0, headDown: false, r: { a: .45, e: .7, w: 0, h: 'relax' }, l: { a: .5, e: .6, w: 0, h: 'relax' } }],
          [5.2, { crouch: .44, headDy: -.07, headDown: true, r: { a: .33, e: -.85, h: 'flat' }, l: { a: .37, e: -.9, h: 'flat' } }, .3],
          [8.18, { crouch: .3, headDy: -.03, headDown: false, r: { a: .3, e: .45, h: 'relax' }, l: { a: .3, e: .4, h: 'relax' } }, .3],
          [8.98, { heading: .25, headHeading: .25, crouch: .3, lean: .2 }, .15],   // backs past the leaf's end, sneaks away right
          [10.2, { crouch: .04, lean: .06 }, .5],
        ],
        add: [[5.5, 8.18, 'bob', .012, 1.7, 1], [9.1, 11.2, 'r.a', .35, 1.6], [9.1, 11.2, 'l.a', .35, 1.6, Math.PI]],
      },
    },
  },
};
const LOOK_SETS = {
  A: { standing_actor: 'dikaiopolis', reclining_figure: 'euripides', stagehand_1: 'stagehand_a', stagehand_2: 'stagehand_b' },
  B: { standing_actor: 'dikaiopolis_B', reclining_figure: 'euripides_B', stagehand_1: 'stagehand_a_B', stagehand_2: 'stagehand_b_B' },
};
// the look that fills a slot (the URL's ?looks= picks a set; otherwise the slot's own look)
const lookFor = name => LOOKS[(window.LOOKSET && LOOK_SETS[window.LOOKSET] && LOOK_SETS[window.LOOKSET][name]) || CAST.slots[name].look];
