# Compositing prototype

The prompt-v2 overlays are added to the rendered frames after rendering, never in 3D:
- `overlay.py`: the chapter card, evidence gauge, breadcrumb outline (from a platform mask render), finishing pass (haze lift, grain, vignette) and citation.
- `compare.py`: builds labelled comparison sheets.

Both expect a `fonts/` folder next to them with:
- `Inter.ttf`: https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf
- `GFSDidot.ttf`: https://raw.githubusercontent.com/google/fonts/main/ofl/gfsdidot/GFSDidot-Regular.ttf

Both fonts are under the SIL Open Font License.
