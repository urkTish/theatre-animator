# Facts on screen, and where each comes from

Every number on screen is computed from the same constants the model is built from (`js/timeline.js` `GEO`, `T`, unchanged from `../motion/`). The evidence tags follow `../SOURCES.md` and `../STORYBOARD.md` (R1–R7).

| On screen | Value / wording | Source or method | Evidence code |
|---|---|---|---|
| Façade (model) | 12 × 5 m | `GEO.SKENE_W`, `GEO.SKENE_H`; STORYBOARD R7 | [R] R7 |
| 01 THE DOOR, "2.8 × 3.2 m", dimension lines "2.8 m", "3.2 m" | 2.8 m wide, 3.2 m high | `GEO.DOOR_W`, `GEO.DOOR_H`; STORYBOARD R2 | [R] R2 |
| "Leaves swing inward" (plan quadrants projected inside) | leaves hinged at the wall's inner face, 0 → 90° inward, fully open at film 5.7 s, before the platform moves at 5.8 s | `doorAngle()`; STORYBOARD R6 | [R] R6 |
| 02 THE ROLL counter, measured line, "Rolled out in 4 seconds" | 0.00 → 2.93 m between film 5.8 and 9.8 s, quintic ease in and out (no overshoot) | `rollDistance()` = 2.93 × smootherstep(3.0, 7.0, scene t); scene t = film t − 2.8 | [I] the action (SOURCES §3.1) |
| Lane on the floor, waiting position, target footprint | front edge waits 1.68 m behind the façade, ends 1.25 m beyond it | `GEO.PLAT_FRONT_IN`, `GEO.ROLL` | [R] R6 |
| "Front edge ends 1.25 m beyond the façade" | −1.68 + 2.93 = 1.25 m | computed | [R] |
| Pin A: *ekkyklein* ἐκκυκλεῖν "to roll out" · Aristophanes, *Acharnians* 408 · attested | Ar. *Ach.* 408 *all' ekkyklēthēt'* ("well, get rolled out!") | Hall & Geldart, PerseusDL `tlg0019.tlg001` (SOURCES §1) | [A] |
| Pin I: Wheels · inferred from the scholia | scholion on *Ach.* 408 (also *Suda*): "a wooden device having wheels" | via Haigh 1907 n. 621 (SOURCES §1, §3.1) | [I] |
| Pin R1: 2.4 × 1.6 m platform · our reconstruction | 2.4 × 1.6 m, deck 0.30 m, 4 solid wheels r = 0.12 m | `GEO.PLAT_*`; STORYBOARD R1 (Dearden ~2.55 × 1.3 m; Haigh ~3 m) | [R] R1 |
| Tableau | couch with a reclining masked figure, stool and cup; a standing masked actor by the door | STORYBOARD R5 | [R] R5 |
| Hidden stagehands | two, pushing from behind, then slipping behind the wall (motion unchanged from ../motion). Hidden as in the motion build: by the door frame, the tableau and the dark interior; they wear near-black (shared/STYLE.md: stagehands in dark tunics). Geometrically they are partly unoccluded between the couch legs from about 4.8 to 9.4 s, so the cast layer, the matte and `tracks.json` (`visible_fraction`) record them there | STORYBOARD R4; *Thesm.* 265 [A] for unseen helpers | [R] R4 |
| "WHITE MODEL 1:20" | the scale at which the film presents the model (a presentation choice; all geometry is in true metres) | — | — |
