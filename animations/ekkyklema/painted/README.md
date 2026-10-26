# Ekkyklema: hand-painted sample (p5.brush)

A 15-second hand-painted animation of the **ekkyklema**, the wheeled platform rolled out through the central door of the
wooden skene in the Theatre of Dionysus, Athens, c. 425 BC. A masked actor knocks; the door leaves swing inward onto
darkness; the platform rolls 2.93 m out in 4 s with Euripides on his couch; the actor beckons him down, and Euripides
waves him off from the couch ("no time to come down", Ar. *Acharnians* 409).

> **Credit.** Built on **[ClaudeAnimationBase](https://github.com/JohnHeibel/ClaudeAnimationBase)** by John Heibel
> (MIT, see `LICENSE`). The kit's own README is kept as `KIT_README.md` and its guide as `ANIMATION_GUIDE.md`.

The set and the characters are rendered as **separate layers**, so the characters can be re-cast later without
touching the background, the camera or the motion: `composite = cast over plate`, frame for frame.

## Deliverables (`sample/`)

| file | what it is |
|---|---|
| `composite.mp4` | the finished 15 s, 1920×1080, 24 fps, H.264 yuv420p |
| `plate.mp4` | the same with no characters (set, machinery, transitions) |
| `matte.mp4` | the characters' alpha (white on black), = the cast layer's alpha |
| `cast_*.png` | a few frames of the cast layer: RGBA, straight alpha |
| `tracks.json` | per frame: the camera, the machinery, and per slot the root, scale, facing, light and screen anchors |
| `composite_lookB.mp4` | the same film re-cast with look set B (the swap) |
| `model_sheet.jpg` | the characters' model sheets, look A and look B |
| `contact_sheet.jpg` | key frames of the film |
| `SWAP_PROOF.txt` | the plate and tracks rendered twice, with looks A and B: identical |

The full cast PNG sequence and the ProRes 4444 `.mov` (with alpha) are too big for the repo; `render.mjs` writes them
(see below).

## Files

| path | what it is |
|---|---|
| `STORYBOARD.md` | logline, reads and timing, the facts kept exact, the layer contract |
| `cast/cast.js` | **the swap point**: the four slots, each with its body, motion track and look |
| `src/looks.js` | the looks (colours, masks, costume patterns): look set A and look set B |
| `src/people.js` | the characters: a look-independent **rig** and a look-dependent **painter** |
| `src/motion.js` | evaluates a motion track at time t (eased keys, overlapping action, idle life, stepping) |
| `src/stage.js` | the set, the camera and the machinery (doors, roll, wheels), and what hides whom |
| `src/layers.js` | the layered renderer: plate pass, cast pass, composite, hashes |
| `src/scenes/ekkyklema.js` | the shot, the transitions, `trackAt(t)` |
| `src/modelsheet.js` | the model sheets (`--loop=model_actor`, `model_euripides`, `model_stagehands`) |
| `src/core.js`, `src/timeline.js`, `src/clawd.js`, `src/sheets.js`, `src/scenes/demo.js`, `render.mjs`, `studio.html` | the kit (`core.js`, `render.mjs` and `studio.html` have small, commented additions) |

## Rendering

You need Node.js, ffmpeg and Chrome or Chromium (`--chrome=` or `CHROME_PATH`; here Playwright's
`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`). Without a GPU add `--soft-gl`.

```bash
npm install
export CHROME_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome

# the film, as layers (parallel, resumable): OUT/composite/*.jpg, OUT/plate/*.jpg, OUT/cast/*.png, OUT/meta/*.json
node render.mjs --soft-gl --layers --workers=2 --out=out/A
# encode: composite.mp4, plate.mp4, matte.mp4, cast_prores4444.mov, tracks.json, frame_hashes.json, render_stats.json
node render.mjs --encode-layers --out=out/A --crf=23 --prores

# the same film re-cast with look set B
node render.mjs --soft-gl --layers --workers=2 --looks=B --out=out/B && node render.mjs --encode-layers --out=out/B --crf=23

# checks while working (the kit's review loop; frames go through the same layered renderer)
node render.mjs --soft-gl --sheet=1,4.2,7,10.6,12.6,13.4 --cols=3 --w=640 --out=out/check/sheet.jpg
node render.mjs --soft-gl --strip=10:11.5 --cols=6 --w=320 --out=out/check/strip.jpg
node render.mjs --soft-gl --loop=model_actor --looks=B --sheet=0.3 --cols=1 --w=1920 --out=out/check/actor_B.jpg
```

Open `studio.html` in Chrome to scrub the film (`?t=10.5`, `?looks=B`, `?loop=model_euripides`).

## The layers

- **plate**: everything that is not a character, painted on an opaque canvas: sky, hills, trees, beaten earth, the
  facade, the door frame and leaves, the dark interior, the ekkyklema with its couch, pillow, stool and cup, the knock
  marks on the door, the brush wipe and the door-shaped iris.
- **cast**: the four characters on a transparent canvas, each **held out** by the set pieces in front of it: anything
  inside the skene is cut to the doorway (so the door frame hides it), the leaves cut whatever is behind them, and the
  platform with its tableau cuts the stagehands behind it. The holdouts are rebuilt from the same seeded shapes the
  plate paints, so the cut lies exactly on the painted edge. Contact shadows belong to the cast (they go with the
  character); the darkness of the interior is a light value (`light.shade` in the tracks) that sinks a figure's colours
  into the dark, and a re-cast figure should take it too.
- **composite** = cast over plate. The paper grain and vignette are multiplied into both layers; because that is a
  per-pixel scale, compositing the layers gives exactly the finished frame.
- **matte** = the cast's alpha.
- **The boil stays in sync.** Every mark is seeded by its own stable key and the boil frame (12 drawings a second), never
  by what was painted before it, so the plate's door frame and the cast's cut along it boil together, and every frame
  renders the same in any order, on any worker (`frame_hashes.json`).

How a transparent canvas works with p5.brush: its compositing shader always writes alpha = 1 and mixes onto white. The
cast pass swaps in a copy of that shader that un-premultiplies the canvas, mixes the pigment with the right weight and
writes premultiplied colour and alpha, under p5's `REPLACE` blend (`src/layers.js`).

### `tracks.json`

One entry per frame (`frames_data[i]`):

```jsonc
{ "t": 10.5, "frame": 252,
  "camera": { "cx": -5, "cy": 2.8, "cz": 8.0, "F": 2100, "Xp": -840, "Yh": 168, "model": "X = Xp + (x - cx)*F/(cz - z), Y = Yh - (y - cy)*F/(cz - z)" },
  "props": { "door_angle_deg": 90, "platform_front_z": 1.25, "roll_distance": 2.93, "wheel_angle_rad": 24.4 },
  "slots": { "standing_actor": {
      "world": { "x": 2.4, "y": 0, "z": 1.08 },            // metres: x along the facade, z toward the audience
      "screen": { "x": 1390, "y": 1015 },                   // the root (between the feet; for Euripides, the couch top)
      "scale_px_per_m": 274.6,
      "facing": { "heading": -0.125, "view": "q", "flip": true, "head_heading": -0.125, "head_view": "q", "head_flip": true },
      "light": { "shade": 0 },                              // 0 = in the light, ~0.97 = deep in the skene's dark
      "anchors": { "head": { "x": 1381, "y": 563, "occluded": false }, "pelvis": {...}, "hand_r": {...}, "hand_l": {...}, "foot_r": {...}, "foot_l": {...} } } } }
```

Headings are in turns (0 = facing the audience, ±0.125 = three-quarter, ±0.25 = profile; negative = facing screen-left).
Hands are named by anatomy (a figure facing left is a mirrored drawing). `occluded` says whether that anchor falls under
a holdout. The tracks come from the rig and the motion only, so they are identical whatever look fills a slot.

## Swapping characters

`cast/cast.js` has one entry per slot: `standing_actor`, `reclining_figure`, `stagehand_1`, `stagehand_2`. Each has a
`body` (rig and proportions), a `motion` track and a `look`.

- **Re-colour or re-costume a slot:** change its `look` to another name in `src/looks.js`, or add a look there (mask
  skin, hair, beard, iris, fillet, robe colour and pattern bands, mantle, boots). `LOOK_SETS` names whole re-castings;
  `--looks=B` (or `studio.html?looks=B`) renders set B.
- **Re-draw a character entirely:** write a new painter for the same rig (`paintPerson` in `src/people.js` gets the
  rig's joints, view and pose); the rig, motion, tracks and plate do not change.
- **Replace it with other footage:** render the plate (`plate.mp4`), put your character over it at the `tracks.json`
  anchors, scale and facing, and apply the holdouts (cut it with the cast alpha, or with your own matte for the door
  frame), then multiply by the paper grain if you want it to sit in the paint.
- **Proof:** `sample/SWAP_PROOF.txt`. The film was rendered with look set A and with look set B: every plate frame is
  bit-identical (pixel hashes), `tracks.json` and `plate.mp4` are byte-identical, and the cast differs in every frame
  with a character on screen (351 of 360; the other 9 are the opening wipe and the closed iris).
  `sample/composite_lookB.mp4` is that look-B film.

## Render speed

Measured on this machine: 4 CPU cores, no GPU, Chromium with SwiftShader (`--soft-gl`), 1920×1080.

| what | time |
|---|---|
| one layered frame, one worker (plate + cast + composite + PNG/JPEG encode) | **about 5 s** (3.5–7 s; render_stats.json: 5.7 s per frame per worker with 2 workers running) |
| of which: the plate | about 3 s (the set, the platform and its tableau painted twice where they cross the facade) |
| of which: the cast | about 1.5–2 s (the four characters, all p5.brush, plus their holdouts) |
| the whole film, 360 frames, `--workers=2` | **2.9 s per frame effective, about 17.5 min**; more workers barely help, SwiftShader already uses every core |
| encoding (`--encode-layers`, with ProRes) | about 3 min |
| a model sheet (8 figures) | 0.5–1.7 s |
| the first frame of a page | +3–50 s (shader compilation) |

Before the speed work the same frame took 70–90 s here (the kit's own demo: about 40 s a frame), almost all of it in
p5.brush's compositing pass: in software GL every colour change runs a spectral-mixing shader over the mark's bounding
box. What changed is listed below. On a machine with a GPU the same page should render in well under a second a frame.

## How the kit was used, and where this departs from it

- **Workflow** as in `ANIMATION_GUIDE.md`: storyboard with timed reads first (`STORYBOARD.md`), then the characters on
  model sheets (three rounds each before any animation), then the shot, checked with contact sheets, strips and crops.
- **Characters** are the kit's medium (flat wash, ink outline, boiling linework, drawn key views: front, 3/4, profile,
  mirrored for the other side; turns snap through them). All acting is body language because the masks are fixed:
  posture, lean, head tilt and turn, hands (relaxed, fist, beckon, point, open palm, flat, holding the stylus).
  Overlapping action is built into the motion evaluator (the head leads, the body follows, arms and hands trail).
- **The set uses one-point perspective** (the audience's eye left of the door axis, verticals kept vertical), because
  the facts are spatial: the leaves swing inward, the platform travels 2.93 m toward the audience and its wheels turn.
  The facade is never foreshortened; only the depth faces (the jamb, the platform's side, the wheels) are drawn in
  perspective. The guide asks for no projected 3D; this is the one place the brief needed it.
- **Speed measures for software GL** (no GPU here): the set's flat washes are laid down as plain jittered polygons
  (a wash at full opacity is a flat colour, so it looks the same) and its long hairlines (plank seams, the eave, the hill
  ridge) are thin tapered polygons; every outline, the door frame, the leaves, the platform and **all of the characters**
  are painted with p5.brush. The brush's compositing shader is replaced by an equivalent that skips the spectral mix
  where the pigment covers a pixel completely and computes the edge "pooling" without screen-space derivatives; marks
  entirely off the canvas are skipped (p5.brush composited the whole frame for them). Watercolour `fill`s are not used
  in the film. `render.mjs` starts Chromium with `--disable-accelerated-2d-canvas` under `--soft-gl` (p5.brush's 2D
  fill mask otherwise stalls on every upload).
- **A p5.brush quirk:** the first wash a page paints can be lost; `render.mjs` paints one throwaway frame first.
- **No text** in the film. The knock is shown with painted impact marks.
