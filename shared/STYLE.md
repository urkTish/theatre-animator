# Theatre Animator — shared style guide

Applies to every animation in `animations/`. Updated 2026-10-25, when the medium changed from 2D diagrams to realistic 3D video.

## Format
- **Medium:** realistic 3D, modelled and rendered in Blender (Cycles), delivered as a video. Captions, citations and the evidence legend are composited over the rendered frames afterwards, so text can be corrected without re-rendering.
- **Frame:** 1920 × 1080 at 24 fps, H.264 MP4 (yuv420p). A 1280 × 720 master upscaled to 1080p is acceptable when render time forces it; say so in the animation's notes.
- **Length:** 60–120 s per animation, in short shots. The camera moves: flyovers, tracking, orbits and cuts. Slow and steady, with no handheld shake.
- **Standard shots:** the audience's view of the façade; a cutaway or behind-the-building view of the machinery; an overhead when layout is the point.
- **Sound:** silent by default. The captions carry everything, so the video also works muted or embedded. Sound can be added later.

## The evidence code (the core rule)
Each thing on screen shows how sure we are of it. The tags match each animation's SOURCES.md. In realistic 3D the picture stays realistic; the code appears as overlays when a caption discusses certainty.

| Tag | Meaning | 3D treatment | 2D diagram treatment |
|---|---|---|---|
| **[A] Attested** | An ancient text says it | Rendered normally; the caption cites the text | Solid outline, full fill |
| **[I] Inferred** | A scholarly inference | Rendered normally; a small "I" tag in the caption | Solid outline, lighter fill |
| **[R] Reconstruction** | Our own choice, weakly supported | Rendered normally; when discussed, a thin dashed outline overlay or an "[R1]"-style tag | Dashed outline, hatched or pale fill |
| **Alternative theory** | A competing reconstruction, shown for comparison | Translucent purple ghost geometry (`--accent-2`), never solid | Dotted purple ghost outline, never filled |

A legend with these four swatches appears bottom-right whenever ghosts or [R] overlays are on screen.

## Palette
Earth tones taken from Attic pottery, plus wood. In 3D these are the reference range for the physically based materials (weathered pine and oak, beaten earth, limestone, undyed and dyed wool) and the exact colours for captions and overlays.

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#1d1a17` | Caption text, outlines |
| `--clay` | `#c8743c` | Accent for figures and highlights |
| `--clay-light` | `#e9b48a` | Inferred fills (2D) |
| `--wood` | `#8a5a34` | Skene timber, the platform |
| `--wood-light` | `#c49a6c` | The platform deck |
| `--stone` | `#d9d2c3` | Orchestra floor, later stone parts |
| `--sky` | `#f4efe6` | Caption card background |
| `--accent` | `#2f5d73` | Labels and arrows showing movement |
| `--accent-2` | `#7a4f8c` | Alternative theories (ghosts) |
| `--blood` | `#8e1f1f` | Sparingly, e.g. the *Ajax* tableau |

## Figures
- Realistic proportions, 1.70–1.80 m tall, so the machinery reads at true scale.
- Actors wear masks (slightly oversized, open mouth), a chiton and a himation. Stagehands wear plain dark tunics, so they read as "not part of the fiction".
- Where realistic human models are unavailable, use clean mannequins in draped cloth with masks. Never uncanny half-realistic faces.

## Typography (composited captions)
- Captions: **Inter**, 500 weight, sentence case, on a translucent `--sky` card with `--ink` text.
- Greek terms: **GFS Didot**, italic transliteration first, with the Greek beside it, e.g. *ekkyklēma* ἐκκύκλημα.
- Citations sit bottom-left in small type, e.g. "Ar. *Ach.* 408–9".

## Motion
- Machinery moves heavily. Ease in and out, with no bounce. The platform takes about 3–4 s to roll out.
- Doors open first; then the platform moves.
- When a caption explains force or direction, an arrow overlay in `--accent` shows it.

## Files
- `shared/STYLE.md`: this guide.
- `shared/assets/`: reusable Blender assets (.blend files, textures), with their sources and licences in `shared/assets/ASSETS.md`. Only CC0 or CC-BY material.
- Each animation folder holds `NOTES.md`, `SOURCES.md`, `STORYBOARD.md`, `layout.svg`, a `3d/` folder (`build_scene.py`, `SHOTLIST.md`, `ASSETS.md`, `looktest/`) and the finished video.
