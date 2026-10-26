# Ekkyklema: claymation sample (12 s, stop-motion look)

The ekkyklema rolled out through the central door of the wooden skene (Theatre of Dionysus,
c. 425 BC), shot as if it were a hand-made tabletop miniature with plasticine puppets
(Aardman/Laika register). It is one of three look samples; `../painted/` and `../whitemodel/` are
the others.

| File | What |
|---|---|
| `sample/composite.mp4` | the shot: 1280×720, 24 fps **on twos** (each pose held 2 frames), H.264 yuv420p |
| `sample/plate.mp4` | the set alone (no puppets, no puppet shadows), same camera |
| `sample/matte.mp4` | white = puppets (all slots), black = everything else |
| `sample/tracks.json` | per output frame: camera, and for every slot its world transform and screen-space head, hands and feet |
| `sample/contact_sheet.jpg` | 12 frames across the shot |
| `sample/closeup_figures.jpg` | close-up still of the puppets (1920×1080, last frame) |

## Beats (timeline seconds; frame = s × 24 + 1)

| Time | Beat |
|---|---|
| 0–1.4 | Doors shut. The masked actor waits beside the door; locked-off wide that shows the whole miniature (painted cyc above the roof) |
| 1.4–4.0 | The leaves swing **inward** (fully open at 4.0 s). The actor turns his head to the door. The camera starts a slow motion-control push-in |
| 4.4–8.4 | The platform rolls **2.93 m in 4.0 s**, long ease in and out: front edge from 1.68 m behind the façade to 1.25 m in front. Two stagehands push it, crouched behind the couch and out of sight, stepping as they go; at the stop they let go and sink back on their heels |
| 7.9–9.5 | The actor's gesture: anticipation, a slight overshoot, then settle: right arm out, palm up, presenting the reclining man |
| 9.3–10.8 | The reclining, older bearded man answers: turns his head to the actor and lifts his open right hand |
| 8.4–12 | Locked-off hold on the tableau (moving hold: slow breath, tiny hand-made jitter) |

Facts kept from the reconstruction (`../3d/SHOTLIST.md`): façade 12 × 5 m; door 2.8 × 3.2 m with
inward leaves; platform 2.4 × 1.6 m, deck 0.30 m, four wheels (turning by driver); the travel and
timing above. Scene units are the full-size metres of the reconstruction; the "miniature" is
in the materials, light and lens (a ~1:10 set shot at about f/5, i.e. f/0.5 in scene units).

## The look

- **Puppets**: the four posed MakeHuman bodies (CC0) from the v3 test, turned into plasticine:
  fingerprints, tool drags, pores and crease grime in the shader (fixed to the clay, so they do
  not swim as the puppet moves); slightly lumpy surfaces; chunky simplified hands; heads ×1.08
  (actors) / ×1.14 (stagehands) and hands ×1.18 for puppet proportions. Robes are **painted
  clay**: the v3 cloth with its fine wrinkles smoothed into sculpted folds, the v3 patterned
  borders painted on. Masks are **painted plaster** (the v3 hand-painted mask textures with brush
  relief, grit and hairline cracks); hair and beards are **sculpted clay locks** made from the v3
  hair curves. Masked faces cannot act, so the acting is posture and gesture. Between poses the
  clay "boils" very slightly, as handled clay does.
- **Set**: the reconstruction's skene and platform, re-made as a miniature: the façade as
  hand-cut strip-wood boards (uneven widths, small gaps, a little out of true) stained and
  dry-brushed; balsa posts, rails and leaves; a card roof; stained craft wheels on brass-wire axles;
  felt mattress and cushions; a gloss polymer-clay cup; a sand-on-board ground with grit and
  static-grass tufts; a painted canvas cyc (`paint_backdrop.py`: hillside, Hymettos ridge and
  sky in visible brush strokes).
- **Light**: a practical miniature rig: a warm low "sun" fresnel from the west with a leaf
  cucoloris (soft dapple on the upper façade), a white bounce card from camera right, a warm
  kicker over the roof, floods on the cyc and a dim practical inside the skene.
- **Camera**: a locked-off wide, a motion-control push-in (1.4–8.4 s) with follow focus, then a
  locked-off medium on the tableau. Shallow depth of field sells the scale.
- **Motion on twos**: one key per held pose (every odd frame), constant interpolation, with
  slightly uneven hand-moved spacing on doors, platform and camera. Only odd frames are rendered;
  the encode shows each twice.

## How to render

Everything is re-runnable from the copied scene (the original `.blend` is only read):

```bash
cd animations/ekkyklema/claymation
python3 clay_sample.py all            # prep, build, render, tracks, closeup, encode
# or stage by stage:
python3 clay_sample.py prep           # copy 3d/build/scene4.blend to WORK, paint the backdrop
python3 clay_sample.py build          # -> WORK/claymation.blend (about 2.5 min)
python3 clay_sample.py render [--pct 100] [--spp 16] [--frames 1-288]
python3 clay_sample.py tracks         # -> sample/tracks.json
python3 clay_sample.py closeup        # -> sample/closeup_figures.jpg
python3 clay_sample.py encode         # -> sample/*.mp4, contact_sheet.jpg
```

`WORK` defaults to the session scratch folder (`--work DIR` to change; `EKK_SRC_BLEND` and
`EKK_V3_FIGS` point at the source scene and the v3 figure files). The render is resumable:
frames already on disk are skipped.

Inputs it needs: `3d/build/scene4.blend` (+ its `../assets` textures), the v3 figure files
`posed.blend` and `figures_unpacked.blend` (made by `../3d/experiments/v3_figures/figures_v3.py`,
whose Poser and base poses are imported, unchanged) and the v3 texture folder they reference.

| Script | Runs in | Does |
|---|---|---|
| `clay_sample.py` | python3 | the driver above |
| `paint_backdrop.py` | python3 (Pillow, numpy) | paints the cyc |
| `clay_build.py` | Blender 4.5 | set restyle, backdrop, lights, cookie, set animation, camera, render settings |
| `clay_figures.py` | Blender (imported) | puppets: clay/plaster materials, clay hair, robes bound by Surface Deform, slots |
| `clay_motion.py` | Blender (imported) | poses (v3 Poser) and the bake on twos |
| `clay_layers.py` | Blender (imported) | plate / cast layers, shadow-catcher set, compositor, the COMP scene |
| `clay_tracks.py` | Blender | `tracks.json` |
| `clay_closeup.py` | Blender | the close-up still |

### Render time

RENDER_TIME_TABLE

## Layers, and how to swap a character

Each puppet lives in its own collection under `CAST`: **`standing_actor`, `reclining_figure`,
`stagehand_1`, `stagehand_2`**. Each contains `<slot> root` (an empty: the standing actor's
stands on the orchestra, the other three are parented to `Platform ctrl` and ride the
platform), `<slot> rig` (MakeHuman "default" rig, baked on twos) and the meshes.

A frame is made from two renders and a comp (`clay_layers.py`):

- **plate** (view layer): the set only. Rendered only while the set or camera moves; in the two
  locked-off holds it is rendered once (frames 1 and 203) and reused.
- **cast** (view layer): the puppets only, on a transparent film. The set is there as linked
  duplicates flagged *shadow catcher* (collection `SET catcher (cast layer only)`): they hide the
  puppets exactly where door frame, leaves, couch and platform are in front of them, light and
  shadow them as the real set does, and the *Shadow Catcher* pass records the puppets' shadows
  on the set.
- **composite** (scene `COMP (plate + cast)`, compositing only, seconds per frame):
  `plate × shadow + cast` in scene-linear light, then the shared AgX view and grade.
- **matte**: the cast alpha. `matte_slots` (per frame, PNG in `WORK/frames/matte_slots/`) holds
  one slot per channel: R standing_actor, G reclining_figure, B stagehands.

The vignette is added at encode time, to composite and plate alike.

To swap a character **in Blender** (the set, camera, motion and plate stay untouched):

1. Open `WORK/claymation.blend`. Replace the meshes in the slot's collection with the new
   character, or keep the rig and bind the new meshes to it (Armature modifier, or bone-parent
   rigid parts to `head`). If you replace the rig too, parent it to `<slot> root` with an
   identity parent inverse and give it the same motion (or retarget the baked action: one key
   per odd frame, constant interpolation).
2. Set the new objects' **Pass Index** to the slot's number (1 standing_actor, 2
   reclining_figure, 3 stagehand_1, 4 stagehand_2) so `matte_slots` stays right.
3. Re-render the **cast** layer only (disable the `plate` view layer and mute the `FO plate`
   output node: `clay_sample.py` does this for the hold frames), then run the comp
   (`python3 clay_sample.py render` skips finished plates; or
   `blender -b claymation.blend -S "COMP (plate + cast)" -a`) and `encode`.

To swap a character **in 2D** (another renderer, hand-drawn, footage): comp it over
`plate.mp4`/the plate frames, using `tracks.json` for placement. Per frame it gives the camera
(world matrix, lens, pixel intrinsics, focus) and, per slot, the root's and pelvis's world
transform and screen positions of head, head top, wrists, palm centres, ankles and toes.
Occlusion by the set is not in `tracks.json`: take it from `matte_slots`, which already has
the door frame and couch cut out of each puppet. Frames 2k and 2k−1 share a held pose
(`held_frame`).

## Strengths and weaknesses

STRENGTHS_WEAKNESSES

## Credits and licences

MakeHuman bodies, rig and hair cards: CC0 (see `../3d/experiments/MAKEHUMAN_NOTES.md`); MPFB
(GPL) is not needed to rebuild this sample, only to rebuild the v3 figure files. Set textures:
none from outside (all procedural) except what the copied scene already used. Backdrop: painted
by `paint_backdrop.py`. Mask and costume research: `../3d/experiments/v3_figures/MASKS_AND_COSTUME.md`.
