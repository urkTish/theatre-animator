# Ekkyklema, hand-painted sample: storyboard

**Logline.** A masked actor knocks at the house door in the wooden skene; the doors swing inward onto darkness, and the ekkyklema rolls out with Euripides reclining on his couch. The actor beckons him down, and Euripides answers with a wave from the couch, because he has "no time to come down" (Ar. *Acharnians* 409).

**World.** The Theatre of Dionysus, Athens, c. 425 BC, seen from the audience's side (from the left of the door axis, so the platform's left side and its wheels show). A weathered timber skene in warm late-afternoon light, low sun from the right. Palette: weathered pine and ochre wood, a gold-to-pale-blue sky, beaten-earth orchestra, deep warm brown-black inside the door. Characters in madder, saffron, woad and undyed cream (look A).
**Colour arc.** Warm daylight outside → a cold dark doorway → the tableau slides from darkness into the warm light (the reveal is a change of light).
**Motif.** The door. It opens on the knock, frames the tableau, and closes over it at the end as a door-shaped iris (the ending rhymes with the shut door of the opening).
**Masks are fixed.** All acting is posture, head tilt, hands and timing.

**Facts kept exact** (from `../STORYBOARD.md`, `../3d/SHOTLIST.md`, `../motion/README.md`):
- Central double door 2.8 m wide × 3.2 m high; the leaves are hinged at the inner face and swing **inward** (R6).
- Platform 2.4 m wide × 1.6 m deep, deck top 0.30 m, **4 wheels** (r = 0.12 m). It waits with its front edge 1.68 m behind the façade (clear of the leaves' swing), rolls **2.93 m in 4.0 s** (slow in, slow out, no overshoot), and stops with its front edge 1.25 m beyond the façade and its back edge just inside the doorway. The wheels turn by distance ÷ radius.
- Two stagehands push from behind, unseen: the door frame and the dark interior hide them. They let go at 8.1 s, while the platform coasts its last 0.7 m, and slip sideways behind the jambs and the open leaf (from the audience's left, the doorway shows deep into the right side of the skene, so they have to go further than the jambs to be out of sight).
- On the platform: a couch with a reclining masked figure (an older man with grizzled hair and a full grey beard: Euripides, *Ach.* 399–409, *Thesm.* 190) and a small stool with a black-glaze cup. He stays on the couch.
- Masks: whole-head, naturalistic, calm, painted eyes with a small dark pupil opening, small parted lips, attached hair and beard (Pronomos Vase, c. 400 BC; no Hellenistic gape). Male masks in a tanned ochre. Actors: long-sleeved, ankle-length robes in horizontal pattern bands, belted, a mantle over the left shoulder, soft low-soled boots. Stagehands: plain short belted tunics, barefoot.
- Small additions, for clarity [R]: the actor knocks before the doors open (Dikaiopolis knocks at Euripides' door, *Ach.* 395); Euripides holds a wax tablet and stylus ("writing a tragedy with his feet up", *Ach.* 398–399).

**Arc (body language only).** Actor: patient → impatient (knocks) → steps back, watching → beckons "come down" → exasperated. Euripides: absorbed in writing → looks up → palm out, "no time" → back to his tablet.

## Shot (one continuous shot, 15.0 s, 24 fps)

```
A  0.0–15.0  [transition in: brush wipe drags off, in the façade's ochre and madder]
   The façade, the shut door and the waiting actor; the doors open; the platform rolls out; the exchange.
   Camera: audience eye, from the left of the door axis (one-point perspective, verticals vertical).
           Wide on the façade, then a slow dolly-in through the roll-out, settling on the tableau and the actor.

   reads:  0.4–2.1   the façade, the shut double door, a masked actor waiting beside it (he shifts his weight,
                     glances at the door). The eye: centre-right, on the actor (he is the only thing moving).
           2.1–2.9   he knocks twice (fist on the right leaf; the leaf jolts). Eye already on him; the knock
                     leads it to the door.
           2.9–3.3   he steps back from the door, turning to watch it (lead the eye).
           3.3–5.4   the leaves swing INWARD, heavy and slow (2.1 s): darkness inside, and in it a dim couch, a
                     figure, a glint of the cup. A beat to peer in (5.0–5.5).
           5.5–9.5   the platform rolls out: 2.93 m in 4.0 s, slow to start and slow to stop, wheels turning.
                     The tableau slides from the dark into the warm light. The actor watches it come, head
                     following, half a step back. The stagehands are hidden by the frame and the dark;
                     they let go at 8.1 s (it coasts the last 0.7 m) and sneak off sideways.
                     Camera dollies in with it.
           9.5–10.3  it settles; the actor turns square to the figure (the platform is "parked": hold).
           10.3–11.6 the actor beckons: arm out, palm up, two beckons, then points at the ground
                     ("come down"). Euripides keeps writing until the second beckon.
           11.6–13.1 Euripides looks up, turns his head to him, raises a palm ("no"), waggles it, then flicks
                     his hand back at his tablet and settles back to writing. He never gets off the couch.
           13.1–13.9 the actor throws up both hands, exasperated, and lets them drop.
           13.9–15.0 the iris narrows to the two men, holds, then closes, door-shaped, on Euripides.
   [transition out: a door-shaped iris (the doorway's proportions) closes to the tableau]
```

Checks: an event in every stretch (knock → doors → roll → beckon → refusal → reaction); every read has its own time and no two important reads overlap (Euripides only reacts after the beckon); transitions in and out; no text anywhere; the ending (a closing door shape) rhymes with the opening (the shut door).

## Layers (the green-screen contract)
The set (sky, landscape, ground, façade, door leaves, interior, platform, couch, stool, cup) is the **plate**. The four characters are the **cast**, drawn by the slots in `cast/cast.js` and held out by whatever set piece is in front of them (the façade around the doorway, the leaves, the platform and its tableau for the stagehands). `composite = cast over plate`, exactly, frame for frame.
