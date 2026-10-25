# Ekkyklema 3D: third-party assets

Every external asset is **CC0 1.0** (public domain dedication) from Poly Haven. Nothing with an unclear licence is used.
Licence: https://polyhaven.com/license (CC0: no attribution required; credited here anyway).

The files are not in git. `fetch_assets.py` downloads exactly this list into a local cache (about 110 MB) and checks each file's MD5 against the Poly Haven API. `build_scene.py --assets DIR` reads from that cache.

## Textures (2k JPG: diffuse, OpenGL normal, roughness)

| Asset | URL | Authors | Used for |
|---|---|---|---|
| Weathered Planks | https://polyhaven.com/a/weathered_planks | Dario Barresi, Dimitrios Savva | skene boarding, roof deck, door leaves |
| Rough Wood | https://polyhaven.com/a/rough_wood | Rob Tuytel | posts, rails, door frame, joists, benches, platform frame, wheels |
| Weathered Brown Planks | https://polyhaven.com/a/weathered_brown_planks | Dimitrios Savva, Rico Cilliers | platform deck boards |
| Fine Grained Wood | https://polyhaven.com/a/fine_grained_wood | Rob Tuytel | couch (kline), stool |
| Dirt | https://polyhaven.com/a/dirt | Charlotte Baglioni | beaten-earth orchestra and working area |
| Dry Ground Rocks | https://polyhaven.com/a/dry_ground_rocks | Rob Tuytel | hillside soil |
| Sparse Grass | https://polyhaven.com/a/sparse_grass | Amal Kumar | spring grass on the slopes |
| Rock Wall 02 | https://polyhaven.com/a/rock_wall_02 | Rob Tuytel | Acropolis rock face |
| Rough Linen | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | weave (normal/roughness) for every garment, mattress and cushion; the dye colours are set in the shader |

## Models (glTF, 1k textures, plus each model's 1k alpha map PNG)

| Asset | URL | Authors | Used for |
|---|---|---|---|
| Searsia lucida | https://polyhaven.com/a/searsia_lucida | James Ray Cock, Jenelle van Heerden | maquis shrubs on the slopes |
| Wild Rooibos Bush | https://polyhaven.com/a/wild_rooibos_bush | James Ray Cock, Jenelle van Heerden | low scrub |
| Searsia burchellii | https://polyhaven.com/a/searsia_burchellii | James Ray Cock, Jenelle van Heerden | **stand-in for olive trees**, leaves re-tinted silvery grey-green |

Botanical honesty: these are South African (fynbos) species, used only as distant background vegetation of the right size and habit. They are not olives or Attic maquis. If olive trees ever come close to camera, they should be replaced by a proper CC0 olive model or a procedural one.

The glTF versions are used rather than `.blend`, because glTF is pure data and cannot carry scripts. Poly Haven's glTF files point the leaf alpha at the JPG diffuse (which has no alpha channel), so `fetch_assets.py` also downloads each model's separate alpha map (`<id>_alpha_1k.png`, same CC0 licence) and `build_scene.py` wires it in.

## Made in `build_scene.py` (no external files)

- Terrain, Acropolis rock, Athens basin, distant hills (Hymettus, Lykabettos, Philopappos, Aigaleo, Pentelikon, Parnes) and the sea: height functions.
- Skene, doors, platform, wheels, couch, cushions, stool, kylix, benches, city houses, Acropolis wall, simplified Parthenon: generated meshes.
- Figures: jointed mannequins built from lathed segments; tragic masks and wigs from deformed spheres; garments as lathed shells; both himatia by Blender cloth simulation, frozen to static meshes.
- Sky: Blender's physical Nishita sky (no HDRI), with a sun lamp at the computed solar position.
- Materials for stone, marble, skin, hair, black-glaze pottery, section cut faces and the evidence overlays: procedural shaders.

## Software

- Blender 4.5.15 LTS, official Linux build from https://download.blender.org/release/Blender4.5/ (SHA-256 checked), installed in `/opt/blender`. GPL; the renders and scripts are not affected by that licence.
- ffmpeg 6.1 for encoding.
