# Theatre Animator — shared style guide

This is a draft for the user's approval. It applies to every animation in `animations/`.

## Format (proposed)
- **Medium:** SVG animated with JavaScript, delivered as one self-contained HTML page. It can be played, paused and scrubbed, and exported to MP4 later if needed.
- **Frame:** 16:9, designed at 1600 × 900 user units, and it must still read on a phone.
- **Length:** 60–120 s per animation, built from short scenes ("beats") that the viewer can step through.
- **Views:** two standard views, which can be shown alone or side by side:
  - **Front elevation:** the audience's view of the skene façade.
  - **Cutaway side section:** the skene sliced through the central door, showing backstage and the machinery.
  - A plan view (from above) is used only when layout is the point.

## The evidence code (the core rule)
Each drawn element shows how sure we are of it. The tags match SOURCES.md.

| Tag | Meaning | How it is drawn |
|---|---|---|
| **[A] Attested** | An ancient text says it | Solid ink outline with a full fill |
| **[I] Inferred** | A scholarly inference | Solid outline with a lighter fill and a small "I" marker on first appearance |
| **[R] Reconstruction** | Our own choice, weakly supported | Dashed outline and a hatched or pale fill |
| **Alternative theory** | A competing reconstruction, shown for comparison | A dotted ghost outline in the accent-2 colour, never filled |

A legend with these four swatches appears in the corner whenever more than one level is on screen.

## Palette
Earth tones taken from Attic pottery, plus wood.

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#1d1a17` | Outlines, text (the black of black-figure ware) |
| `--clay` | `#c8743c` | Main fill, figures (the orange of red-figure ware) |
| `--clay-light` | `#e9b48a` | Inferred fills |
| `--wood` | `#8a5a34` | Skene timber, the platform |
| `--wood-light` | `#c49a6c` | The platform deck |
| `--stone` | `#d9d2c3` | Orchestra floor, later stone parts |
| `--sky` | `#f4efe6` | Background |
| `--accent` | `#2f5d73` | Labels and arrows showing movement |
| `--accent-2` | `#7a4f8c` | Alternative theories (the ghost outlines) |
| `--blood` | `#8e1f1f` | Used sparingly, e.g. in the *Ajax* tableau |

A dark mode swaps `--sky` to `#1a1714`, swaps `--ink` to `#efe6d8`, and keeps the clay tones.

## Figures
- Simplified silhouettes inspired by red-figure ware: clay-coloured bodies with ink detail lines and no faces beyond profile.
- Actors wear masks, drawn as a slightly oversized head with an open mouth.
- Stagehands are plain dark silhouettes, so they read as "not part of the fiction".

## Typography
- Labels: **Inter**, 500 weight, sentence case.
- Greek terms: **GFS Didot**, set in italic transliteration first, with the Greek beside it, e.g. *ekkyklēma* ἐκκύκλημα.
- Citations sit at the bottom left in small type, e.g. "Ar. *Ach.* 408–9".

## Motion
- Movement is mechanical and weighty. Ease in and out, with no bounce. The platform takes about 3–4 s to roll out.
- Arrows in `--accent` show the direction of force: who pushes and where.
- Doors swing open first; then the platform moves.

## Files
- `shared/STYLE.md`: this guide.
- `shared/assets/`: reusable SVG parts (skene façade, door, platform, figures), extracted once Animation 1 is approved.
- Each animation folder holds `NOTES.md`, `SOURCES.md`, `STORYBOARD.md`, `layout.svg` and the build files.
