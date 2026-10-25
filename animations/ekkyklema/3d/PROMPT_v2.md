# Ekkyklema 3D — prompt v2 (proposal, not yet approved)

This rewrites the shot list in the compact style of the "Opus 5.5 Motion Lab" prompt pack (*From a watch to one atom*, R08). The research, the evidence and the reconstruction choices R1–R7 are unchanged. What changes is pacing, the on-screen guide, the camera and the finish.

## What we take from the pack, and why

| Pack rule | Our version |
|---|---|
| **The payoff comes early.** The watch is open by 3 s. | **Cold open:** the doors open and the tableau rolls out by 5 s, seen as the audience saw it. Today our payoff waits until 35 s. |
| **A fast rewind closes the loop.** | **The rewind is the eiskyklema.** Rolling back in is literally the device's second operation (*Thesm.* 265), so we use it twice: a quick rewind after the cold open ("how did that work?"), and the final roll-back, which lands on frame 1, so the film loops seamlessly. |
| **A new level every 2–3 s**, each with a counter, a name and one real fact. | **Chapters 01 / 10**, each with a name and **one fact with its source**. One fact per chapter, short enough to screenshot. |
| **A gauge on the right edge** (a log scale with a live readout) turns the video into a countdown. | **An evidence gauge on the right edge:** three ticks, Attested / Inferred / Reconstruction, with a marker showing how sure we are of what the current chapter shows. Our core rule becomes a visible instrument. |
| **A breadcrumb before every level:** the next target glows 0.8 s before the camera reaches it. | The next subject (door, platform, stagehands, ghost) gets a thin `#2f5d73` outline, composited from an object mask, 0.8 s before the camera moves to it. The accent appears nowhere else. |
| **One camera, no cuts, jumps hidden.** | **Mostly one camera,** with at most 3 cuts. Transitions are hidden behind a door post, the sweeping section plane, or a crane move. |
| **The smallest thing is the stillest.** | **The tableau is the quietest moment:** the camera stops completely for 2.0 s on the revealed interior. |
| **Look:** PBR, bloom, shallow focus, 2% grain, vignette. | We already use AgX Medium High Contrast. Add: Cycles **motion blur** with a 180° shutter (fast door swings and camera moves step without it); **depth of field on every shot** (f/5.6 wide, f/2.8 close); subtle glare (bloom) on sunlit edges; **2% film grain and a soft vignette**; less atmospheric haze, which currently makes the stills look milky. |
| **Contract:** `renderAt(t)`, seeded random, any frame exact. | Already met: `build_scene.py` is deterministic and frame = seconds × 24 + 1. Keep it. |
| **Review after every render, with numeric follow-ups.** | A fixed **five-pass review** (below). |
| **Sound synthesised in code**, each hit 1 frame after its picture, −14 LUFS. | An optional sound pass, synthesised in Python with no samples (below). |

What we don't take: three.js (we chose Blender for realism), 60 fps (it doubles the CPU render time; we use 24 fps with motion blur), and Remotion (not needed for Blender frames).

## The prompt (for the 3D helper)

```
Blender 4.5 Cycles, 1920x1080, 24 fps, 90.0 s = frames 1-2160, seamless loop.
Theatre of Dionysus c. 425 BC; realistic; R1-R7 as in STORYBOARD.md.

Seconds, HUD top left (counter, name, one fact + source in Inter / GFS Didot):
 0.0 01 THE REVEAL: audience eye, doors already parting; platform rolls 2.93 m,
     out by 4.6 s; the tableau in daylight. "Deeds done inside, shown outside."
     Pollux 4.128
 5.5 Hold 0.8 s, then a fast rewind: the platform rolls back in at 3x and the doors
     shut by 7.5 s. Caption: "How?"
 7.5 02 ATHENS: crane up and back to the aerial; theatron on the hillside, the
     Parthenon on the rock. "A wooden stage building, c. 425 BC" [I]
14.0 03 THE PROBLEM: descend to front-row eye height, doors shut. "Violence happens
     inside, offstage."
20.0 04 BEHIND THE DOOR: arc round the skene end; the section plane sweeps in and
     hides the move. The platform waits 1.7 m back; two stagehands crouch.
     "One at each door." Pollux 4.128
30.0 05 THE DOORS: leaves swing inward. dioigō "I open". Soph. Aj. 346
34.6 06 THE ROLL-OUT: camera rides alongside; 2.93 m in 4.0 s. ekkyklein
     "to roll out". Ar. Ach. 408
40.0 07 THE TABLEAU: section closes; audience eye; the camera STOPS, 2.0 s hold,
     then a slow orbit. "No time to come down." Ar. Ach. 409
58.6 08 ROLL BACK IN: section view; the stagehands pull. eiskyklein
     "someone roll me back in". Ar. Thesm. 265
66.0 09 WHAT'S DISPUTED: crane to overhead; purple ghosts one by one: turntable,
     windlass, size range. "Rolled or revolved?"
82.0 10 THE REVEALS: front view; Heracles, Hippolytus, Ajax thumbnails in the
     doorway; "Next: Sophocles' Ajax".
88.8 The doors close and the camera eases onto frame 1's framing; frame 2160
     cuts seamlessly to frame 1.

Mostly one camera, max 3 cuts, jumps hidden. The next subject gets a thin #2f5d73
mask outline 0.8 s before the camera reaches it; no accent anywhere else.
Right edge: the evidence gauge A / I / R, its marker eased between chapters.
Look: AgX Medium High Contrast, motion blur 180°, DOF every shot, subtle glare,
2% grain, vignette, reduced haze. HUD, captions, outlines and gauge are composited
after rendering, never rendered in 3D.
```

## Five-pass review (after each render)

1. **Light and contrast** (stills): no milky haze; the shaded façade and the doorway read clearly.
2. **Materials at scale** (stills): wood, earth, cloth and masks read as real at the distance each shot uses.
3. **Motion in sequence** (a full low-resolution preview at 25%, 16 samples): drift, jolts, things leaving the frame.
4. **Frame-by-frame timing**: eased motion visibly starts several frames after its keyframe, so key captions and breadcrumbs to the **visible** start, not the keyframe.
5. **Final**: motion blur on fast moves, and a fact check of every number and citation on screen against SOURCES.md.

## Optional sound pass

Synthesised in Python (numpy), with no samples or downloads, as a 48 kHz stereo WAV muxed into the MP4 with ffmpeg:
- light wind and distant swallows as a bed;
- a wooden latch, then hinge creaks as the doors swing;
- a low wooden rumble with soft grit for the wheels on beaten earth, its pitch tied to the platform's speed;
- a soft data tick on each chapter label;
- a reversed whoosh for the rewind.

Each sound lands 1 frame after its visual event. Mixed to about −14 LUFS, peak −1 dBTP.

## Optional social cut
A 27 s, 4:5 (1080 × 1350) loop: chapters 01, 06, 07 and 08 only, reusing the same frames re-framed. For posting; it can follow the main film.
