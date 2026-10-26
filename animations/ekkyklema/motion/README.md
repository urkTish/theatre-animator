# Ekkyklema: motion-design build (three.js)

A code-built explainer scene for chapter **06 / 10 · THE ROLL-OUT**: the ekkyklema rolled out through the central door of the wooden skene, Theatre of Dionysus, c. 425 BC. It replaces the Blender renders. The background, camera and motion are fixed. The characters fill four **slots**, and what fills each slot can be swapped, like a green screen.

- `scene.html`: the page (three.js r170, vendored; Inter and GFS Didot, vendored).
- `js/`: the modules (see *Files* below).
- `cast.json`: **the swap point**. There is one entry per character slot.
- `render.mjs`: the offline renderer (Node + Playwright + ffmpeg).
- `sample/`: the 10 s sample renders (see *Sample* below).
- `examples/`: example swaps (glTF, sprite, video).

## The facts the scene encodes

They are all in `js/timeline.js` (`GEO`, `T`), and nothing else hard-codes them.

| Fact | Value |
|---|---|
| Skene façade | 12 m wide × 5 m high, wooden, 4.7 m deep |
| Central double door | 2.8 m × 3.2 m. The leaves swing **inward** (R6), are fully open at 2.9 s, and are hinged at the wall's inner face |
| Platform | 2.4 m wide × 1.6 m deep, deck top 0.30 m, 4 solid wheels (r = 0.12 m) |
| Roll | The front edge waits 1.68 m behind the façade face, then rolls **2.93 m in 4.0 s** (3.0–7.0 s, a quintic ease with no overshoot) and ends 1.25 m beyond the façade |
| Wheels | angle = distance ÷ radius (`wheelAngle(t)`) |
| Tableau | A couch with a reclining masked figure, and a stool with a black-glaze kylix |
| Stagehands | Two, pushing from behind, then slipping sideways behind the wall (7.15–9.05 s). In the audience camera they are hidden by the door frame, the tableau and the dark interior |
| Ground | A beaten-earth orchestra with no raised stage, and the seating on the hillside |
| Light | Late-afternoon sun from the audience's front-right, with a cool sky fill |

Axes: x runs along the façade (+x is the audience's right), y is up, and z points toward the audience. The façade face is the plane z = 0.

## The contract (in the page)

```js
await window.ready;                                  // assets, fonts and shaders are ready
await window.renderAt(t, { layer, contactShadows }); // draws exactly frame t (seconds)
window.trackAt(t);                                    // JSON: camera + slots (below)
```

- **Deterministic.** Every state is a pure function of `t`. The code reads no clock, the randomness is seeded, CSS has no transitions, and grain is seeded by the frame number. The page runs `requestAnimationFrame` only in the interactive preview (no `?t=` and no `?render`).
- **URL parameters:** `?t=4.5` renders one frame, `&layer=`, `&style=clay|vase` overrides the style of every stand-in, `&cast=path.json` sets the cast file, and `&w=&h=` set the size (1920×1080 by default).

### Layers

| `layer` | What it contains |
|---|---|
| `all` | The final composite: set, characters, the HTML overlays (chapter card, "How sure?" gauge, breadcrumb), depth of field, a soft vignette and 2% grain. |
| `plate` | The background only. Every character slot is hidden. With `contactShadows: true`, the characters still cast their shadows into the plate, so they would no longer be representation-independent. They are off by default, so the plate is identical whatever fills the slots. No overlays, grain or vignette (finishing comes after compositing). |
| `cast` | The characters only, on a fully transparent background. The set is drawn **depth-only** first, so the door frame, the leaves, the couch and the platform occlude the characters exactly as in `all`. The characters keep the scene lighting, including the set's shadows and the dark interior. The WebGL buffer is premultiplied. PNG stores straight alpha by definition, so `cast_rgba/*.png` is straight (un-premultiplied) RGBA, and the ProRes 4444 `.mov` is the same. |
| `matte` | The character silhouettes in white on black, with the same occlusion. It is the `cast` alpha exactly. |

The depth of field is applied to every layer (it is a property of the camera). Grain and vignette appear only in `all`.

### `trackAt(t)` and `tracks.json`

There is one entry per frame:

```json
{ "t": 8.5, "frame": 204,
  "camera": { "position": [x,y,z], "quaternion": [x,y,z,w], "fov_deg": 31, "aspect": 1.7778, "near": 0.1, "far": 1500,
              "focus_distance": 8.9, "aperture": 1 },
  "props":  { "door_angle_deg": 90, "platform_center_z": 0.45, "roll_distance": 2.93, "platform_front_edge_z": 1.25, "wheel_angle_rad": 24.42 },
  "slots": { "standing_actor": {
      "world": { "position": [...], "quaternion": [...], "yaw_deg": -64 },
      "pose": { "pose": "gesture", "from": "stand_wait", "w": 1 },
      "anchors": { "head": { "world": [...], "screen": [x,y], "visible": true }, "pelvis": {...}, "foot_l": {...}, "foot_r": {...} },
      "bbox": [x0,y0,x1,y1], "bbox_unoccluded": [...], "visible_fraction": 1,
      "joints": { "pelvis": [x,y,z], ... } } } }
```

Screen coordinates are pixels with the origin at the top-left. The anchors and boxes come from the **canonical skeleton**, not from the mesh that fills the slot. Visibility is ray-tested against simple occluder boxes of the set (the façade, door leaves, platform, couch and stool). As a result `tracks.json` is identical for every representation, and you can use it to place 2D footage or to stabilise a replacement.

## Swapping characters (`cast.json`)

Each slot has a **`motion`** (tied to the shared timeline) and a **`representation`** (what you see). Edit only `representation` to swap. Motion drives a canonical 21-joint skeleton (`js/skeleton.js`), and every representation follows that skeleton. Neither the camera nor the set ever reads the representation.

Slots: `standing_actor`, `reclining_figure`, `stagehand_1`, `stagehand_2`.

```jsonc
"motion": {
  "root":  [ { "t": 0, "pos": [x,y,z], "yaw": deg, "space": "world" | "platform", "ease": "inout" } ],  // keyframes
  "poses": [ { "t": 0, "pose": "stand_wait" }, { "t": 7.25, "pose": "gesture", "blend": 1.0 } ],      // named poses
  "breath": 1, "sway": 0.6, "gait": { "stride": 0.62 }     // optional procedural layers (functions of t)
}
```

`"space": "platform"` keys ride on the ekkyklema, so the reclining figure and the pushing stagehands move with it. The named poses are in `js/skeleton.js` (`POSES`). They are FK angles plus two-bone IK targets for hands and feet, and a head look-at.

The representation types:

| `representation` | Notes |
|---|---|
| `{ "type": "standin", "style": "clay" \| "vase", "costume": "actor" \| "reclining" \| "stagehand" }` | The built-in stand-ins. They are meshed every frame from signed-distance primitives on the skeleton, so the joints and drapery blend like a maquette. **clay**: matte figures with painted theatre masks and draped robes. **vase**: Athenian red-figure, with terracotta bodies, a black ink contour, black hair, and dilute-glaze drapery lines with a hem band. Options: `palette` (6 hex colours), `resolution` (metres), `mask` (bool). |
| `{ "type": "gltf", "src": "x.glb", "scale": 1, "offset": [x,y,z], "rotation": [deg,deg,deg] }` | Loaded and placed on the slot root, and lit and occluded like everything else. The materials are patched so they get the same interior darkness. Optional `bones: { "<canonical joint>": "<bone name>" }` drives those bones with the solved skeleton's local rotations (rest-relative, so the axes must match). Optional `clip`, `clipStart`, `clipSpeed` and `clipLoop` sample an animation clip at the shared time. |
| `{ "type": "sprite", "src": "x.png" \| "seq_%04d.png", "frames": N, "fps": 24, "start": 0, "anchor": [u,v], "height": m, "lit": false }` | A camera-facing card, upright, turning only about the vertical axis. `anchor` is the image point that sits on the slot root (feet). `lit: true` lets the scene light it (useful in the dark interior). Image sequences are indexed by `t`. |
| `{ "type": "video", "src": "x.webm", "start": 0, "speed": 1, ... }` | The same card with an HTML video, seeked to `t` before every frame (deterministic). VP9 WebM with alpha works in Chromium. |

```sh
node render.mjs --cast examples/cast.gltf-example.json --stills 8.5 --out /tmp/x
```

Three examples, each identical to `cast.json` except for the standing actor's `representation`: `cast.gltf-example.json` (`actor_clay.glb`, a static export of the clay stand-in, so it has root motion only), `cast.sprite-example.json` (`sprite_actor.png`) and `cast.video-example.json` (`sprite_actor.webm`, VP9 with alpha). All three were rendered as test stills. The sprite and the video are crude placeholder drawings, made only to exercise the plumbing.

**Proof that only the characters change.** The sample was rendered twice, with `--style clay` and with `--style vase`. All 240 `plate` frames have identical MD5s, and `tracks.json` and even `plate.mp4` are byte-identical between the two. See `sample/SWAP_PROOF.txt`; the hashes refer to the full-quality scratch renders.

## Sample (`sample/`)

- `composite_clay.mp4` and `composite_vase.mp4`: the same 10 s, with the two stand-in styles.
- `plate.mp4` and `matte.mp4`: the plate and the matte.
- `tracks.json`: compact, one entry per frame.
- `cast_rgba_{0,3,5,8}s.png`: frames from the RGBA cast layer.
- `contact_sheet.jpg`: key frames, clay above vase.
- `SWAP_PROOF.txt`: the swap proof.

The MP4s here were re-encoded at CRF 23 to stay under about 10 MB each. The renders came out at CRF 18. The full PNG sequence and the ProRes 4444 `.mov` stay outside the repo.

## Rendering

```sh
cd animations/ekkyklema/motion
node render.mjs --out OUT --layers all,plate,cast,matte --tracks --prores        # the full 10 s at 1920x1080, 24 fps
node render.mjs --out OUT --style vase --layers all,plate --tracks               # same shot, vase stand-ins
node render.mjs --out OUT --stills 0,3,5,8 --layers all,cast                     # single frames as PNG
node render.mjs --out OUT --w 960 --h 540                                        # quick preview
node render.mjs --serve                                                          # http://127.0.0.1:8123/scene.html (live preview)
```

Options: `--start/--end` (seconds), `--fps`, `--crf` (18), `--contact-shadows` (plate), `--cast`, and `--style`. The outputs are `composite.mp4` (H.264 yuv420p), `plate.mp4`, `matte.mp4`, `cast_rgba/NNNN.png` (+ `cast_rgba.mov` ProRes 4444 with `--prores`), `tracks.json`, `frame_hashes.json` and `render_stats.json`. When both `cast` and `matte` are requested, the matte is extracted from the cast alpha (`alphaextract`) rather than rendered twice.

**Render speed.** This machine has 4 CPU cores and no GPU, so Chromium runs WebGL in software (SwiftShader). Measured on it at 1920×1080 (`render_stats.json`) while the clay and vase renders ran **in parallel**, so each process had about half the machine:

| Layer | s/frame (render) | of which posing and meshing (CPU) | capture |
|---|---|---|---|
| `all` (clay) | 7.2 | 1.6 | 0.36 |
| `all` (vase) | 7.9 | 1.6 | 0.32 |
| `plate` | 5.2–5.6 | 0 | 0.22 |
| `cast` | 2.8 | 0 (reuses the frame's meshes) | 0.14 |
| `matte` | free (taken from the cast alpha) | | |

Wall clock: the clay pass (all + plate + cast + matte + tracks + ProRes) took 65 min, and the vase pass (all + plate + tracks), run at the same time, took 57 min. A single process on its own measured about 6 s per `all` frame on the hold and about 11 s on the wide establishing frames. A 960×540 preview of `all` runs at 2.8 s per frame (11 min for the 10 s).

What costs the time: the scene pass with 4× MSAA and PCF shadows, about 3 s per frame; depth of field, about 0.8 s on the hold; and re-meshing the four SDF stand-ins on the CPU, about 1.5 s. A glTF or sprite cast skips the meshing. On a machine with a GPU the same page renders in real time (`--serve`). Ambient light is a spherical-harmonics probe of the sky, because a prefiltered environment map cost about 2 s per frame in software.

## Files

| File | Role |
|---|---|
| `js/timeline.js` | The facts, the machinery motion (doors, roll, wheels) and the camera path (C1 Hermite) |
| `js/set.js`, `js/geom.js`, `js/textures.js` | The skene (planks, posts, rails, door frame, roof eave, ledged leaves with iron straps), the platform and its wheels, the couch, stool and kylix, the ground, the seating wing with retaining walls, trees and hills. The textures are procedural and seeded |
| `js/lighting.js` | Sun, sky, SH ambient, and the analytic sky-visibility term (dark skene interior, the platform's footprint) that patches every lit material, the swapped-in ones included |
| `js/pipeline.js` | The layers: depth-only occlusion, half-resolution SSAO, depth of field, AgX tone mapping and grade, vignette and grain |
| `js/skeleton.js`, `js/cast.js` | The canonical skeleton (FK + IK + look-at), the poses, slot motion, representations, and tracking |
| `js/sdf.js`, `js/standin.js` | The signed-distance figure modeller with surface-nets meshing, and the clay and vase stand-ins with their masks |
| `js/overlay.js` | The chapter card, the gauge and the breadcrumb, all set from `t` |
| `vendor/three/` | three.js **0.170.0** (`build/three.module.js` plus the few addons used), MIT licence |
| `fonts/` | Inter and GFS Didot (both SIL Open Font Licence) |
