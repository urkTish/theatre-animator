# Designing people: Hugging Face survey and proposed pipeline

Surveyed 2026-10-26 with the Hugging Face API (models and Spaces sorted by likes) and checked licences on each model page.

## Why
Script-built figures (mannequins, and MakeHuman bodies with hand-made clothes) look like toys or horror at the distances our shots need. The Blender skill we installed says so plainly: characters are "out of scope for procedural scripting"; import real models instead.

## Proposed pipeline
1. **Design each person as an image.**
   - Models: **FLUX.1-schnell** (Apache-2.0) or **Qwen-Image** / **Qwen-Image-Edit-2509** (Apache-2.0). The Space `tori29umai/Qwen-Image-2509-CharacterSheet` makes multi-view character sheets.
   - The image: full body, front view, arms slightly out, plain background, even light. Costume and mask follow our research (5th-century naturalistic masks; long-sleeved patterned robes as on the Pronomos Vase).
2. **Image → textured 3D mesh (GLB).**
   - **TRELLIS.2-4B**, Microsoft, MIT: the most-liked image-to-3D on the Hub. Space `microsoft/TRELLIS.2` exposes `/image_to_3d` at 512/1024/1536.
   - **Hunyuan3D-2.1**, Tencent: high quality, but under the Tencent community licence, which has territorial limits. Check before use.
   - Human-specific options:
     - **PSHuman**, CC-BY-4.0: clothed human from a single image; Space `fffiloni/PSHuman`.
     - **LHM**, Apache-2.0: animatable human, but its output is Gaussian splats, which suit Blender less well.
     - **StdGEN** (Apache-2.0) and **CharacterGen** (Apache-2.0): both lean towards stylised characters.
3. **Auto-rig.**
   - **UniRig**, VAST-AI, MIT; Space `MohamedRashad/UniRig`.
   - **Make-It-Animatable**, Apache-2.0.
   - **Puppeteer**, Seed3D, Apache-2.0.
   - Any of these, then import into Blender, pose, and keep our own cloth tweaks where needed.
4. **Motion** for the stagehands walking and pushing:
   - **HY-Motion-1.0**, Tencent, text-to-motion; licence "other", check it. Space `tencent/HY-Motion-1.0`.
   - Or hand-keyed poses on the rig.
5. **Reference only:** **SAM 3D Body** (Meta; gated, licence "other") recovers a 3D body and pose from a photo. It could help match poses to vase paintings. A CPU ONNX port exists (`AmmarkoV/SAM3DBody-cpp-onnx-models`).

## What it needs
- These models need a GPU. This machine has none, so we call the Hugging Face Spaces remotely (ZeroGPU).
- Anonymous calls from this machine are refused: "You have exceeded your ZeroGPU quota (… 0s left)".
- **We need a Hugging Face token** in the environment as `HF_TOKEN`.
- Quota per the HF docs (https://huggingface.co/docs/hub/spaces-zerogpu): free accounts get about 3.5 GPU-minutes a day (a forum post mentions a cap of 3 runs a day); PRO gets about 25 minutes a day.
- One figure costs roughly one image generation plus one 3D generation, so PRO is the practical option for a cast of four or more.

## Licences of outputs
FLUX.1-schnell, Qwen-Image and TRELLIS.2 are permissive (Apache-2.0 / MIT). Record each generated asset (model, Space, seed, prompt) in the animation's `3d/ASSETS.md`.
