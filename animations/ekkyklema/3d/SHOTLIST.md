# Ekkyklema 3D: shot list (Phase 1, for approval)

A camera-driven rewrite of the nine storyboard beats (`../STORYBOARD.md`) for the rendered 3D film.
**Length 90.0 s at 24 fps = frames 1–2160.** There is one timeline. The action (doors, platform, wheels, stagehands), the section cuts, the evidence overlays and per-shot exposure are keyframed on it once, and timeline markers switch cameras, so the final render is literally `blender -b ekkyklema.blend -s N -e M -a`.
Captions and citations are composited afterwards (ffmpeg/Pillow); nothing is lettered in 3D. Caption text is the storyboard's (as already worded in the 2D build).

Frame = seconds × 24 + 1. Camera names are the object names in the .blend.

## Fixed action (timeline seconds)

| Event | Time | Notes |
|---|---|---|
| Section cut sweeps through the skene | 17.0–19.5 | museum cutaway; see below |
| Doors swing open, inward (R6) | 31.0–34.0 | 3 s, eased |
| Platform rolls out 1.8 m (R1, R4) | 35.0–38.7 | 3.7 s, long ease in and out, no overshoot; the wheels turn by driver (distance ÷ radius) |
| Stagehands sink into a low crouch | 38.7–39.5 | keeps their heads below the audience's sight line while the tableau is shown |
| Platform rolls back in (stagehands pull) | 58.6–62.3 | |
| Doors close | 62.6–65.2 | |
| Plan view: doors open, platform in | 66.0 | state change hidden by the cut |
| Platform rolls out again (windlass comparison) | 70.4–74.0 | |
| Reset at the cut to the front view | 82.0 | doors shut, platform in |
| Doors open on darkness (*Ajax* teaser) | 87.2–89.4 | |

Beat boundaries move by up to about 1 s against the storyboard: the doors open late in beat 3 and the roll starts at 35 s, so that one 8 s shot can hold both the doors opening and the platform moving. Caption timings move with them.

## Shots

| Shot | Time | Beat | Camera | Action | Caption (composited) | Citation |
|---|---|---|---|---|---|---|
| SH01 establishing | 0–5 s | 0 | Aerial from the south-west, drifting in and down: the theatre cut into the hillside, the Acropolis rock seen obliquely above, the town and Lykabettos in the haze. Morning sun from the right | Still. Doors shut | **ekkyklēma** ἐκκύκλημα, "the roll-out" · Theatre of Dionysus, late 5th c. BC | — |
| SH02 descent | 5–15 s | 1 | From high above the top of the theatron, looking down the slope to the skene; descends over the empty benches and settles at front-row eye height facing the closed doors | An actor waits by the closed door | "Greek plays happen outdoors. Violence happens *inside*, offstage." … "How do you show its aftermath?" | cf. Pollux, *Onom.* 4.128 |
| SH03 into the cutaway | 15–28 s | 2 | From audience eye level the camera arcs west round the end of the skene and rises; a section plane sweeps through the building from the west end to the door axis, and the near half is cut away. Ends looking down into the section | Backstage: the platform waits behind the door with its tableau set; two stagehands crouch behind it. Faint dashed outlines tag the platform (R1) and doorway (R2) while the labels are up (21.5–27.4 s) | "A cut through the central door." · "Backstage, the platform waits with its tableau set. Two stagehands crouch behind it." Labels: skene (wooden stage building) [I], door [R2], platform [R1], wheels [I], stagehands [R4] | Pollux, *Onom.* 4.128 · scholion on Ar. *Ach.* 408 |
| SH04 doors open | 28–35 s | 3 | Section view, slow push in | The leaves swing inward. The west leaf is cut away with the wall, so the east leaf is seen face-on | "The doors open…" · *dioigō* "I open", Sophocles, *Ajax* 346 | Soph. *Aj.* 346 |
| SH05 tracking | 35–40 s | 4 | A low camera rides alongside the platform on the cut-away side, with the platform's own easing | The stagehands push; the platform rolls 1.8 m | **ekkyklein** "to roll out" · *Acharnians* 408: *ekkyklēthēti* "get rolled out!" | Ar. *Ach.* 408 |
| SH06 audience eye | 40–46 s | 4 | Back to the audience's view (section closed), slow push toward the door | The tableau stands in the doorway; the stagehands are invisible in the dark interior | (beat 4 caption continues) | Ar. *Ach.* 408 |
| SH07 orbit | 46–58 s | 5 | Slow orbit in front of the doorway, about 3.3 m from the tableau, from the actor's side across to the head of the couch. Exposure opened up for the doorway's shade | The standing actor addresses the reclining figure, who gestures back and stays on the platform | "An interior shown outside." · "In *Acharnians* (425 BC) Euripides, rolled out, has 'no time to come down' (409)." | Ar. *Ach.* 409 · *Ach.* 399 · *Thesm.* 261 · Pollux 4.128 |
| SH08 rolling back in | 58–62.6 s | 6 | Section view again (cut on at the cut) | The stagehands pull it back in, walking backward | **eiskyklein** "to roll in" · *Thesmophoriazusae* 265: "someone roll me back in, quickly!" Pollux (4.128) calls the device for this the *eiskyklēma* | Ar. *Thesm.* 265 · Pollux, *Onom.* 4.128 |
| SH09 doors shut | 62.6–66 s | 6 | Front, medium | The doors close | (beat 6 caption continues) | |
| SH10 overhead | 66–82 s | 7 | Straight down from about 15 m, with a plan section (roof and upper walls cut at 3.1 m, cut faces hatched); very slow rotation | (a) 66–70: purple ghost of a **turntable** in the doorway, rotating its door-wall and couch outward (Exon 1900; Flickinger 1918). (b) 70–74: ghost **windlass and pulley** (Casanova 2017): the drum turns and the rope shortens as the real platform rolls out. (c) 74–78: ghost outlines of the **size range** (Dearden ~2.55 × 1.3 m; Haigh ~3 m wide). (d) 78–82: hold; the timeline strip is a 2D overlay | "What's disputed" · "Rolled or revolved?" → "How big?" → "Since Aeschylus, or later?" with the storyboard's detail lines | Exon 1900 · Flickinger 1918, pp. 284–289 · Casanova, *Prometheus* 43 (2017) 3–42 · Dearden 1976, pp. 50–54 · Haigh 1907, pp. 201–207 · Ar. *Ach.* 408 · *Thesm.* 96, 265 · Taplin 1977 · Hammond 1972 |
| SH11 reveals, *Ajax* teaser | 82–90 s | 8 | Front, slow push toward the door | 82–87: doorway-sized thumbnails composited over the closed doors (*Heracles*, *Hippolytus*, *Ajax*). 87.2–89.4: the doors open on darkness while the *Ajax* thumbnail lingers | "Reveals most scholars accept" · "The usual use: the result of an indoor event, usually bodies or a disturbed hero, shown as a tableau." → "Next: Sophocles' *Ajax*" | Eur. *Her.* 1028 · Eur. *Hipp.* 808 · Soph. *Aj.* 346 |

Extra camera, not in the edit: **LT clip** (30.8–38.8 s), a low front three-quarter view from the west that dollies in as the doors open and the platform rolls out. It is an alternative coverage of SH04–SH06; if it replaces them, the section cut must stay off for that stretch (`render_looktest.py clip` does this).

## Seeing behind the façade: a section cut, not a camera inside

Chosen: a **clean section cut through the skene on the door axis**, as in a museum cutaway. It is stepped: the walls are cut on the door axis and the roof is opened 2.5 m further, so daylight reaches the backstage floor. The cut sweeps in over 2.5 s while the camera swings round. The cut faces are a flat warm grey with fine hatching, so they read as a drawing rather than a broken building. Architecture is cut; people, props and the platform never are (the usual convention). The west door leaf is cut with the wall.

Why not move the camera behind the building:
- **Honesty.** The back of the skene is unattested. A camera behind it would have to invent a back wall, openings and a way for light to get in. The section shows only what the reconstruction needs: the door, the platform, the stagehands and the depth behind the façade.
- **Legibility.** A real interior would be dark (the façade faces NNW, so it is in shade all morning), and a camera inside can't see the audience side at the same time. The section shows backstage and the orchestra in one frame, which is the storyboard's "S" view.
- **Convention.** Viewers know cutaways as diagrams, so the cut itself signals "explanatory view, not what the audience saw". That keeps SH02, SH06, SH07, SH09 and SH11 as the only "as seen" views.

## Evidence code in 3D (subtle overlays)

- **Rival theories:** soft purple (accent-2 `#7a4f8c`) translucent ghosts. They are camera-only, so they cast no shadows, and each fades in and out with its caption (SH10).
- **Our reconstructions:** faint dashed light outlines on the platform (R1) and the doorway (R2), shown only while a caption or label discusses them (SH03).
- Everything else is rendered realistically. The [A]/[I]/[R] tags go into the composited labels, and the four-swatch legend is composited bottom-right whenever ghosts or [R] outlines are on screen (SH03, SH10).
- **Force and direction:** a 2D `--accent` arrow is composited in SH05 and SH08 (who pushes, who pulls, which way), as `shared/STYLE.md` asks.

## 3D reconstruction notes (choices within R7 and beyond R1–R7)

| Item | What the scene shows | Status |
|---|---|---|
| Orchestra | Never drawn: a patch of beaten earth with soft, noise-broken edges, framed so no outline is emphasised. The bench fan starts 13 m from a nominal centre 11 m in front of the façade | R7 [R]: the 5th-century shape is debated |
| Theatron | Straight wooden benches on stakes, in rows that follow a gently curved polygonal fan (6 wedges, 0.8 m rows, 25° slope), empty | R7 [R]: rectilinear vs curved is debated; polygonal straight timbers read as neither |
| Skene | 12 × 4.7 × 5 m timber building: posts every 2 m, rails at 0.5 m and 4.5 m (as `layout.svg`), vertical weathered boards, flat plank roof, no decoration | R7: wooden skene [I]; the depth (4.7 m, from the layout's section) and details are [R] |
| Door | 2.8 × 3.2 m opening with a stout frame, two ledged board leaves hung at the inner face, iron ring pulls inside | R2, R6; leaf construction [R] |
| Platform | 2.4 × 1.6 m, deck top 0.30 m, plank deck on two runners, four solid 0.24 m wheels on iron axles, outboard under the deck edge | R1; wheels [I]; construction [R] |
| Light | Sun at the computed position for about 1 April, 09:00 local solar time, at 37.97° N (altitude 37°, azimuth 118°), with a physical sky. The façade faces about NNW and so stands in shade, lit by the sky and the sunlit slope | [I]: geometry and astronomy; the theatre axis is approximate |
| Surroundings | Acropolis rock with the south circuit wall and a simplified Parthenon (complete by 432 BC); low courtyard houses with tiled roofs in the town; olive and maquis on the slopes | generic [R]; the Parthenon's position is approximate |
| Not shown | The Odeion of Pericles (built c. 440s BC, immediately east of the theatre): its site is left as olive grove and kept out of frame. The old temple of Dionysus south of the skene is also omitted | open question |
| Figures | Jointed mannequins with full-head masks (open mouth, eye holes, attached wig). Actors wear long chitons and himatia (saffron/madder; undyed wool/woad); the standing actor wears soft boots. Stagehands wear plain dark tunics | stylised by design; dye colours [R] |

## Look test (Phase 1)

Made by `render_looktest.py` from the built .blend (full settings and timings are in the report):
- Stills at 1920×1080: (a) SH01 at 2.5 s, (b) "LT b audience eye" at 45 s, (c) SH04 at 29.5 s, (d) SH07 at 52 s.
- Clip: "LT clip", 30.8–38.8 s, 192 frames at 1280×720, encoded H.264 yuv420p.
