# Ekkyklema: white-model build (Projection on White Model)

A 15 s sample of chapter 06 (the roll-out) in the **Projection on White Model** style of the [lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) toolkit: our reconstruction of the skene and the ekkyklema shown as a clean white museum model on a dark plinth, with light, labels and evidence projected onto it, and the people as deliberate white maquettes. It reuses the geometry, timeline, cast slots and layer system of `../motion/` (which is not modified).

- `scene.html`, `js/`: the page (three.js 0.170, vendored).
- `cast.json`: **the swap point**, one entry per character slot (white maquettes). `examples/cast.clay.json` and `examples/cast.vase.json` are the same file with other looks.
- `render.mjs`: the offline renderer (Node + Playwright + ffmpeg), with layers `all` / `plate` / `cast` / `matte`.
- `build.sh`: one command for the whole sample (render → encode → sound → mux → swap proof → contact sheet).
- `mix.py`: the sound design. `TREATMENT.md`: the plan. `FACTS.md`: every on-screen claim and its source. `CREDITS`.
- `sample/`: the deliverables (below).

## The film (15.0 s, 1920×1080, 24 fps)

One continuous take, with light changes as the transitions (the style's grammar):

| Film time | Picture |
|---|---|
| 0–1.45 s | The white model on its plinth under house light; a high wide crane down. Identity label top-left. |
| 1.45 s | Relay: the house light cuts. 1.8 s: the lamp strikes (flicker), the projector's black level and a 1 m grid appear on the base. |
| 2.05–5.7 s | **01 THE DOOR**: a cool wash and outline on the doorway, dimension lines grow (2.8 m, 3.2 m), readout "2.8 × 3.2 m". The leaves swing **inward** (3.8–5.7 s) while the projector traces their sweep as plan-drawing quadrants on the floor inside. The waiting platform is picked out in the dark. |
| 5.35–9.8 s | **02 THE ROLL**: the lane, the target footprint, the façade line and a 0.5 m ruler are projected on the floor; the platform rolls **2.93 m in 4.0 s** (5.8–9.8 s, quintic ease, no overshoot), its front edge carrying the light front; a counter and a measured line (dashed while behind the façade) run 0.00 → 2.93 m. |
| 10.25–15 s | **03 HOW SURE?**: the evidence code of `shared/STYLE.md`, in the style's language (one warm layer palette, three treatments): **[A]** a solid amber arrow on the floor, "ekkyklein ἐκκυκλεῖν 'to roll out', Aristophanes, *Acharnians* 408"; **[I]** a lighter glow on the wheels, "inferred from the scholia"; **[R1]** a hatched deck with a dashed edge, "2.4 × 1.6 m platform, our reconstruction". At 12.9 s the house light comes back (1 s) and the evidence layer stays on alone; the camera settles at audience eye height on the tableau. |

**The hidden stagehands.** The couch is an open frame, so from eye level you look between its legs into the skene, where the two stagehands crouch behind the platform; no camera angle avoids that. As in the motion build they are hidden by the dark interior: in the white look they are near-black maquettes (shared/STYLE.md: stagehands in plain dark tunics, "not part of the fiction"). The cast layer and the matte show them faintly where they are geometrically unoccluded (about 4.8–9.4 s), and `tracks.json` gives their `visible_fraction`, so a compositor can see exactly where they are.

The facts are exactly those of `../motion`: façade 12 × 5 m; door 2.8 × 3.2 m, leaves inward, fully open at 5.7 s before the platform moves at 5.8 s; platform 2.4 × 1.6 m, deck 0.30 m, 4 wheels; front edge waits 1.68 m behind the façade, rolls 2.93 m in 4 s, ends 1.25 m beyond it; two hidden stagehands push; couch, reclining masked figure, stool and cup; a standing masked actor by the door.

**How the timeline is reused.** `js/timeline.js` is copied unchanged (facts, door, roll, wheels). `js/film.js` adds a 2.8 s lead-in: the scene runs on scene time `ts = t − 2.8`, so every cast keyframe in `cast.json` and every prop function is the motion build's own. `tracks.json` gives both `t` (film) and `scene_t`.

## Deliverables (`sample/`)

| File | What |
|---|---|
| `composite.mp4` | the film with sound: 1920×1080, 24 fps, H.264 High yuv420p, AAC 48 kHz, −14 LUFS |
| `plate.mp4` | the set and the projection, no characters (no overlays, no vignette) |
| `matte.mp4` | the character silhouettes, white on black, occluded by the set (= the cast layer's alpha) |
| `tracks.json` | one entry per frame: camera (position, quaternion, fov, focus), props (door angle, roll distance, platform z, wheel angle), and per slot the root transform, pose, screen anchors (head, pelvis, feet) with visibility, boxes and all 21 joints |
| `contact_sheet.jpg` | key frames of the composite, the layers, and look B |
| `SWAP_PROOF.txt` | look A vs look B: plate frame hashes and `tracks.json` identical |

The RGBA cast layer (PNG sequence and ProRes 4444 `.mov`) is produced by `build.sh` in `out/` (not committed: too large).

## Render

```sh
cd animations/ekkyklema/whitemodel
LIB=/path/to/lemo-opuscar sh build.sh                       # everything, ~1 h 40 min on this machine (see below)
STAGE=render sh build.sh                                    # just the PNG sequences (all, plate, cast) with 3 workers
node render.mjs --stills 3.6,9.8,14.9 --layers all,plate,cast,matte --out /tmp/x   # single frames
node render.mjs --w 960 --h 540 --stills 0.5,5,10,14.9 --out /tmp/x                # quick preview stills
node render.mjs --readcheck                                 # every on-screen text stays long enough to read
node render.mjs --serve                                     # live preview at http://127.0.0.1:8123/scene.html
```

`LIB` is a clone of lemo-opuscar with its core tier installed (`sh plugin/skills/lemo-opuscar/scripts/setup.sh deps`, i.e. a `.venv` with numpy, scipy, soundfile, soxr, pillow) and the VCSL samples (`sh tools/fetch.sh instruments vcsl`, 284 MB, CC0). The picture needs only Node, Playwright's Chromium and ffmpeg.

`render.mjs` options are those of `../motion/render.mjs` plus `--png` (write every layer as a PNG sequence, for parallel workers), `--events` (export the sound cues, `window.EV`) and `--readcheck`. The page also exposes the lemo-opuscar page contract (`window.DUR`, `render(t)`, `READY`, `EV`, `TEXTS(t)`).

## Swap the characters

Edit only `representation` in `cast.json` (the `motion` blocks are tied to the shared timeline). Every type of `../motion` works: `standin` (styles `white`, `clay`, `vase`), `gltf`, `sprite`, `video` (see `../motion/README.md`). To render another look:

```sh
node render.mjs --cast examples/cast.clay.json --layers all --out /tmp/clay      # a whole other cast file
node render.mjs --style vase --stills 12 --out /tmp/vase                         # or override every stand-in's style
```

**Proof that only the characters change** (`sample/SWAP_PROOF.txt`): the full 360-frame plate and the tracks were rendered with look A (`cast.json`, white maquettes) and look B (`examples/cast.clay.json`, the clay stand-ins). Every plate frame has the same MD5 and the two `tracks.json` are byte-identical. It holds because the plate hides every slot and its shadows, the projector puts data colours only on the model (figures receive only its neutral black level), and the tracks come from the canonical skeleton and simple set occluders, never from the mesh in a slot.

## Render speed

RENDER_SPEED_PLACEHOLDER

## What was taken from lemo-opuscar (with credit)

[lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) by LemoLab: code MIT (Copyright (c) 2026 LemoLab), content CC BY 4.0. Nothing in this folder carries a LemoLab sign-off; the film is ours.

- **Style** (`styles/white-model/STYLE.md`): the white model (matte ≈ #F3F3F1) on a dark plinth in a dark room; data drawn as projected light, never paint; layers one at a time, each with its own gesture of light; house light → relay → lamp strike with a flicker → layers → house light back; at most two layer palettes on screen (here cool for measurement, warm for evidence); readouts in the left third (index, name, one figure, one label, one source line, a legend), pins on dark plates with a hairline, a quiet identity label top-left; Inter Tight 200 for figures and IBM Plex Mono for numbers; camera grammar (crane down, side-on track along the measured line, a settling push), no cuts.
- **Code, adapted**: the projection term `colour × (0.42 + 0.58·max(N·toProjector, 0)) × throw mask` injected into `MeshStandardMaterial` (after `demo/studio.js` `projLight`), here rewritten as `js/lighting.js` `PROJ_GLSL` with this film's layers (door wash and outline, swing quadrants, lane, ruler, target footprint, evidence arrow / wheel glow / hatch); the 2D overlay grammar `readout` / `pin` / range line (after `demo/overlay.js`), rewritten in `js/overlay.js`; the room background gradient; the anti-aliased line helper.
- **Tools used as they are**: `core/audio/sfx.py` (clack, thump, creak, mix helpers), `core/audio/sampler.py` (VCSL samples, `room` reverb), `core/render/mux.sh` (two-pass loudnorm to −14 LUFS, true peak −1.2 dB, light grain in ffmpeg), `core/render/sheet.py` (review sheets); the reading-time rule of `core/render/readcheck.mjs` is reimplemented in `render.mjs --readcheck` because our page renders asynchronously and a full WebGL frame per 0.04 s step would take 25 min in software.
- **Direction** (`DIRECTOR.md`, `TECHNIQUE.md`): a treatment with three candidate structures before reading the demo, a benchmark, a cue sheet, one timeline driving picture and sound (`window.EV` → `mix.py`), frame-by-frame deterministic rendering, a review loop on contact sheets (four rounds), the reading-time check, "not the demo again" (structure, opening, signature shot, camera path, score and ending differ from the Rotterdam demo).
- **Not used**: narration (the film is captioned and readable muted, as `shared/STYLE.md` asks; Kokoro would have been reachable), a score (sound design with sampled mallets and bowed vibraphone instead), GTAO/bloom from `core/three/post.js` (too slow in software WebGL; the motion build's half-resolution SSAO and depth of field are kept).

## Files

| File | Role |
|---|---|
| `js/film.js` | the film's timeline (lead-in offset, cue sheet), light state per layer, camera path |
| `js/lighting.js` | house key, neutral studio ambient, interior visibility, **the projector** (`PROJ_GLSL`), room background |
| `js/set.js` | the white model: the motion build's skene, doors, platform, wheels and tableau, with white materials, on a base plate and plinth |
| `js/overlay.js` | identity label, readouts, dimension lines, measured line, evidence pins |
| `js/main.js` | page entry, layers, `trackAt`, sound events |
| `js/standin.js` | the stand-ins, with the new `white` maquette style (plaster masks) next to `clay` and `vase` |
| `js/timeline.js`, `cast.js`, `skeleton.js`, `sdf.js`, `geom.js`, `pipeline.js`, `util.js` | from `../motion` (pipeline: neutral grade; grain moved to ffmpeg) |
| `tools/swapproof.mjs`, `tools/sheet.py` | the swap proof and the contact sheet |
