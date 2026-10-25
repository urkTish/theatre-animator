# MakeHuman figures: comparison test (not part of the main build)

A test of whether to replace the scene's jointed mannequins with realistic human figures made with **MakeHuman** through **MPFB2** (MakeHuman's Blender extension). Nothing in the main build was changed: `build_scene.py`, `render_looktest.py`, `SHOTLIST.md`, `ASSETS.md` and the main `.blend` files were only read. All work was done on a copy of the built scene, in a scratch folder.

**Verdict in one line:** MakeHuman works here (downloads, licences and headless MPFB all fine), and the B figures look clearly more real than the mannequins: bodies, hands, poses, the chiton and tunic drapery and the stagehands are a big step up, and the masks read as theatre masks. Weak points that need more work before a switch: the himation, the reclining figure's chiton round the raised arm, the mask paint, and the wigs. It costs roughly 0 to 20 % more render time per frame, plus real extra work to animate the stagehands.

## The images (A = current mannequins, B = MakeHuman + masks)

Same camera, same frame, same settings (1280 × 720, Cycles CPU, 64 samples, OpenImageDenoise) for A and B:

| File | What |
|---|---|
| `compare_tableau.jpg` | look-test still "d_tableau_closeup": camera `SH07 orbit the tableau`, frame 1249 (52.0 s) |
| `compare_cutaway.jpg` | look-test still "c_cutaway": camera `SH04 doors open (cutaway)`, frame 709 (29.5 s) |
| `B_reclining_mask_crop.jpg` | close crop of the masked reclining figure in B: the same camera and frame rendered at 3× resolution with a border crop |
| `compare_tableau_crop.jpg` | the same crop for A and B side by side |

Full-size PNGs (A and B separately) are in the scratch folder `…/scratchpad/3d/mh/work/renders/` and `…/work/compare/`.

## What the test figures are

- **Standing actor**: adult male, 1.75 m (MakeHuman default male height), weight on the right leg, left foot forward, right arm presenting the couch with an open palm, left forearm raised; long chiton of undyed wool to the ankles, belted; a woad-blue himation over the left shoulder and upper arm, hanging front and back; soft leather boots; mask with an attached wig and a beard.
- **Reclining figure**: on the couch on its left side, propped on the left elbow on the cushions, chest to the audience, right hand raised and open in a speaking gesture; saffron chiton; the madder blanket over the legs; mask with an attached wig.
- **Stagehands**: crouched in a staggered stance behind the rear rail (one with the left foot forward, one with the right), hands flat on the rail top, leaning in to push; dark wool knee-length tunics, belted; barefoot; no masks, short dark hair, real eyes and brows.
- **Masks**: moulded on each actor's own posed MakeHuman face with the jaw opened, enlarged 1.16× about the head, smoothed (idealised), with eye and mouth openings cut through, a raised edge, a dark lining behind the openings (so they read as hollow), and painted brows, eye rims, lips and cheeks. Pale paint (the standing actor's slightly darker and warmer). The wig is MakeHuman hair enlarged with the mask so it covers the mask's edge.
- **Clothing**: every garment is a Blender cloth simulation frozen to a mesh. Chiton and tunics are cut for the T-pose, sewn along the shoulder and arm seam, pinned at the girdle, and simulated from the T-pose into the final pose with the body as a collider (76 frames); the himation and blanket are a second pass on the frozen figures. Materials are the scene's own dye materials (rough-linen weave, same colours as the mannequins).
- **Placement**: everything is built in platform-local coordinates. The reclining figure is parented to the platform rig, so it is right at both frames; the standing actor stands where the mannequin stands; the stagehands are where the mannequins push at frame 709. At frame 1249 the mannequin stagehands are hidden behind the façade wall, so in B they are simply switched off for that frame.

## Licences (checked before use)

| What | Licence | Statement, and where it is stated |
|---|---|---|
| **MPFB 2.0.18** (the extension's code) | **GPL-3.0-or-later** | Extensions platform listing <https://extensions.blender.org/add-ons/mpfb/> and the API record: `"license": ["SPDX:GPL-3.0-or-later"]`; the same in the archive's `blender_manifest.toml`. MakeHuman's licence page: "The source code of MPFB is shared under GPL and the source code of MakeHuman is shared under AGPL." |
| **MakeHuman core assets** (base mesh, targets, skins, eyes, eyebrows, eyelashes, hair, rigs and weights) | **CC0** | <https://static.makehumancommunity.org/about/license.html>: "All core assets are shared under Creative Commons, CC0. The effective consequence of this is that you are free to do as you see fit with the asset or derivates of the assets. You do not need to pay anything, include any copyright notices nor give attribution." <https://static.makehumancommunity.org/mpfb/faq/is_it_really_free.html>: "all core asset such as the base mesh, targets and skins are shared under CC0". |
| Per-file confirmation | CC0 | The base mesh `data/3dobjs/base.obj` (shipped inside MPFB) and every `.mhclo` / `.mhmat` file in the system-asset pack (140 files) carry the header: "This asset was explicitly released as CC0 in september 2020." The pack manifest `packs/makehuman_system_assets.json` gives `"license": "CC0"` for every asset, and the pack page <https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html> lists every asset as CC0. The rig weights file `weights.default.json` says `"license": "CC0"`. |
| Not confirmed file-by-file | (CC0 by the general statement) | `rig.default.json` (bone layout) and the `.target.gz` shape targets have no licence field of their own; they are MakeHuman core assets and the targets are named explicitly in the FAQ quote above. I treated them as covered. |

How the GPL is kept away from the scene: `makehuman_test.py` *calls* MPFB at build time (MPFB is installed in an isolated Blender user folder, not in the repo, and no MPFB code is copied). MPFB's own material node groups (its "enhanced skin", "MakeSkin" and procedural-eye node trees are data that ships with the GPL add-on) are **not** used: the script builds its own simple shaders on the CC0 textures, so the figures in the `.blend` contain only CC0 MakeHuman data plus our own geometry and shaders. Renders are not affected by either licence.

## Assets used (all CC0)

Downloads (checked by SHA-256):
- MPFB 2.0.18: <https://extensions.blender.org/download/sha256:c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad/add-on-mpfb-v2.0.18.zip> (sha256 `c075b3e9…2dad`, 46 MB). Contains the base mesh `hm08`, the shape targets, and the `default` rig with its weights.
- MakeHuman system assets: <https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip> (sha256 `b542127a…0107`, 281 MB).

| Asset (MakeHuman name) | From | Used for |
|---|---|---|
| Base mesh `hm08` + macro targets (gender, age, muscle, weight, height, proportions, ethnic mix) | MPFB 2.0.18 `data/` | all four bodies |
| Rig `default` (163 bones, fingers, toes, face) + `weights.default.json` | MPFB 2.0.18 `data/rigs/standard/` | posing |
| Skins `middleage_caucasian_male`, `young_caucasian_male` (diffuse textures only, re-tinted to a sun-tanned tone in our shader) | system assets | skin |
| Hair `bob01` (standing actor's wig), `long01` (reclining actor's wig), `short02`, `short04` (stagehands) | system assets | wigs / hair |
| Eyes `high-poly` with `brown` texture, eyebrows `eyebrow001`, `eyebrow006`, eyelashes `eyelashes02` | system assets | stagehands' faces |

Made by the script (no external files): the T-pose garments (chiton, tunics), the himation and blanket (Blender cloth simulation, frozen), the tragic masks and their dark linings, the beard (hair curves), the boots, all shaders. Cloth weave: the scene's existing CC0 Poly Haven `rough_linen` materials (same dye colours as the mannequins).

## Render time (measured on this 4-core CPU, no other Blender job running)

Single renders in one Blender session, after a warm-up render (kernels, images); 1280 × 720, OpenImageDenoise:

| Shot | Samples | A (mannequins) | B (MakeHuman) | Difference |
|---|---|---|---|---|
| tableau (SH07, frame 1249) | 64 | 85.4 s | 87.0 s | +1.6 s (+2 %) |
| cutaway (SH04, frame 709) | 64 | 92.3 s | 92.4 s | +0.1 s (0 %) |
| 3× crop of the reclining figure | 64 | 87.3 s | 88.2 s | +0.9 s (+1 %) |
| tableau | 16 (the planned final setting) | 24.9 s | 30.2 s | +5.3 s (+21 %) |
| cutaway | 16 | 27.5 s | 31.6 s | +4.1 s (+15 %) |

Reading: the extra cost is mostly a fixed per-frame cost (syncing about 0.9 million more triangles, alpha-textured hair cards and the beard curves), not per-sample shading, so it shows at 16 samples and nearly vanishes in the noise at 64. These are single measurements: a repeat run of B (after the last mask tweak) gave 86.0 s and 96.9 s at 64 samples, so the noise is about ±5 s.

**Estimate for the final ~90 s film** (SHOTLIST.md: 1280 × 720, 16 samples, about 24.5 s per frame, about 14.7 h for 2160 frames): figures are on screen from about 5 s to 82 s (about 1,850 frames). At +4 to +5 s per frame that is about **+2.1 to +2.6 h, i.e. about 17 h instead of 14.7 h (+15 to 18 %)**. Persistent data (already on in the .blend) should claw back part of that for the two actors, who do not deform. One-off costs: building the four figures takes about 1.5 min (cloth 45 s, masks and second cloth pass 40 s); simulating the stagehands' tunics over the whole film, if they are animated (see below), would add very roughly 15–30 min once.

## Problems found, and what would take more work in the real build

1. **Himation.** The classic wrap (over the left shoulder, across the back, round the right hip, the end held in the left hand) was tried twice and failed: the cloth slid down the back and crumpled round the hips. The test shows a simpler mantle over the left shoulder and upper arm, hanging front and back; its top outer corner still stands out stiffly. A proper wrap needs a guided simulation (wrap it in stages, or hold it with temporary pins/colliders that are then released): about half a day.
2. **Reclining chiton.** Moving from the T-pose to the reclined pose drags the right sleeve: there is a loose flap at the raised right arm, and the neckline slides off the shoulder (reads a little like a modern off-shoulder blouse). Fix: real Ionic-chiton pins at intervals along the arms, a finer cloth (2.4 cm grid now), a longer settle.
3. **Cloth intersections.** The MakeHuman hair is not a collider, so wig strands pass through the himation and chitons at the shoulders. Some cloth sinks slightly into the cushions. The blanket's front hangs as a rather flat sheet.
4. **Mask paint.** The features are vertex colours on a ~5 mm mesh, so brows and lips are soft, and at SH07's exposure the paint reads nearly white (as the mannequin's does). The mask shape, edge, eye holes and open mouth read well. A UV-unwrapped mask with a painted texture would fix the paint. The mask/wig join is simple (enlarged MakeHuman hair over the mask's edge).
5. **Wigs.** MakeHuman's CC0 hair cards (`long01`, trimmed to the shoulders for the standing actor). Fine at these distances; for close-ups, curve hair and a historically checked style. The beard is script-generated hair curves (2,600 strands).
6. **Rig limits.** MPFB's `default` rig (163 bones, full fingers) has no IK controls and no corrective shapes, so the script poses it with its own aim and two-bone IK solver and moves part of the wrist roll into the forearm twist bones. Deep bends (the stagehands' knees, the reclining figure's shoulders) lose a little volume. For animation, use MPFB's rig helpers or Rigify, and add corrective shapes for knees and shoulders.
7. **Animation.** In this test every figure is frozen at one frame. In the film the stagehands crouch, push, walk back and hide behind the façade (keyed per frame in `build_scene.py`). Switching means porting that gait (planted feet, stepping) to the MakeHuman rig and either simulating the tunics over the whole timeline or skinning them to the rig. The actors can stay frozen unless SH07 should show the gesture moving.
8. **Real faces.** The stagehands have real MakeHuman faces (the actors' are covered by the masks). At the cutaway's distance they look fine; in close shots they risk the uncanny. Keep them small in frame, or turned away.
9. **Skin.** Our own simple shader (CC0 diffuse texture, tinted to a sun-tanned tone, a little subsurface scattering); no normal or specular maps.
10. **Scene versions.** The figures were built with the platform and couch from the first copy (`scene.blend`, 18:16); the comparison renders use a copy of the newer `scene4.blend` (19:32), so A shows the current mannequins. Mannequin positions, the platform animation and both cameras are identical in the two files (checked).

## How to reproduce

1. Install MPFB into an isolated Blender user folder (so the main build's Blender is untouched):
   `BLENDER_USER_RESOURCES=DIR blender -b --factory-startup --command extension install-file -r user_default -e add-on-mpfb-v2.0.18.zip`
2. Unzip `makehuman_system_assets_cc0.zip` into `DIR/extensions/.user/user_default/mpfb/data/`.
3. `python3 makehuman_test.py all --scene COPY.blend --work WORKDIR --mpfb-resources DIR --repo-out .`
   (or the three stages `build`, `render`, `compose` separately; see the script's docstring). `build --resume cloth` redoes only the masks and the second cloth pass from the checkpoint.
