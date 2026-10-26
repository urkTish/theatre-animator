#!/usr/bin/env python3
"""Ekkyklema claymation sample: build, render and encode (driver; plain python3).

    python3 clay_sample.py all                 # everything below, in order
    python3 clay_sample.py prep|build|render|tracks|closeup|encode
    options: --work DIR  --pct 100  --spp 32  --frames 1-288  --out DIR (default ./sample)

prep     copy the built 3D scene (never touching the original) and paint the backdrop
build    blender: clay_build.py -> WORK/claymation.blend
render   blender -a on the .blend, every other frame (on twos); resumable (existing frames are
         skipped). Layers plate + cast where the set/camera moves, cast only in the locked holds
         (the plate is rendered once there and reused); then the COMP scene makes composite =
         plate x shadow + cast. Frames: WORK/frames/{plate,cast,shadow (EXR), matte,
         matte_slots, composite, plate_view, cast_view (PNG)}/. Writes WORK/render_timing.json
tracks   blender: clay_tracks.py -> OUT/tracks.json
closeup  a close-up still of the puppets (camera "CAM clay closeup (still)", last frame)
encode   ffmpeg: OUT/composite.mp4, plate.mp4, matte.mp4 (each held frame shown twice, 24 fps,
         H.264 yuv420p), OUT/contact_sheet.jpg
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("BLENDER", "/opt/blender/blender")
SRC = os.environ.get("EKK_SRC_BLEND",
                     "/tmp/claude-0/-home-user/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/3d/build/scene4.blend")
FIGS = os.environ.get("EKK_V3_FIGS",
                      "/tmp/claude-0/-home-user-theatre-animator/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/v3_figures/work")
WORK_DEFAULT = "/tmp/claude-0/-home-user-theatre-animator/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/claymation/work"
FPS = 24
VIGNETTE = "vignette=angle=0.55:mode=forward"


def opts():
    a = sys.argv[1:]
    stage = a[0] if a and not a[0].startswith("--") else "all"
    o = {"work": WORK_DEFAULT, "pct": "100", "spp": "16", "frames": "1-288", "out": os.path.join(HERE, "sample")}
    for i, x in enumerate(a):
        if x.startswith("--") and i + 1 < len(a):
            o[x[2:]] = a[i + 1]
    return stage, o


def run(cmd, log=None):
    print("+", " ".join(cmd[:6]), "..." if len(cmd) > 6 else "")
    if log:
        with open(log, "w") as fh:
            r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    else:
        r = subprocess.run(cmd)
    if r.returncode:
        raise SystemExit("failed (%d): %s%s" % (r.returncode, " ".join(cmd[:4]), (" -- see " + log) if log else ""))


def prep(o):
    w = o["work"]
    os.makedirs(w, exist_ok=True)
    dst = os.path.join(w, "scene4_copy.blend")
    if not os.path.exists(dst):
        shutil.copy2(SRC, dst)                       # the original is only read
    run([sys.executable, "-I", os.path.join(HERE, "paint_backdrop.py"), os.path.join(w, "backdrop.png")])


def build(o):
    w = o["work"]
    run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(HERE, "clay_build.py"), "--",
         "--src", os.path.join(w, "scene4_copy.blend"), "--figs", FIGS, "--backdrop", os.path.join(w, "backdrop.png"),
         "--out", os.path.join(w, "claymation.blend"), "--frames", os.path.join(w, "frames")],
        log=os.path.join(w, "build.log"))


# the plate only changes while the camera, doors or platform move (clay_build.CAM_LOCK = 1.4..8.4 s);
# in the locked holds it is rendered once (frames 1 and 203) and reused
PLATE_MOVING = (37, 203)
PLATE_REUSE = [((3, 35), 1), ((205, 287), 203)]


def _blender_render(o, f0, f1, plate=True, tag=""):
    w = o["work"]
    expr = ("import bpy; s=bpy.context.scene; s.render.resolution_percentage=%d; "
            "s.render.use_overwrite=False; s.render.use_placeholder=True" % int(o["pct"]))
    if o.get("spp") and int(o["spp"]) != 16:          # scale the per-layer samples (14/10 at --spp 16)
        expr += "; k=%d/16.0; [setattr(v,'samples',max(4,int(round(v.samples*k)))) for v in s.view_layers]" % int(o["spp"])
    if not plate:
        expr += ("; s.view_layers['plate'].use=False; "
                 "[setattr(n,'mute',True) for n in s.node_tree.nodes if n.name=='FO plate']")
    run([BLENDER, "-b", os.path.join(w, "claymation.blend"), "--python-expr", expr, "-s", str(f0), "-e", str(f1),
         "-j", "2", "-a"], log=os.path.join(w, "render_%s%d_%d.log" % (tag, f0, f1)))


def render(o):
    w = o["work"]
    f0, f1 = (int(x) for x in o["frames"].split("-"))
    before = set(glob.glob(os.path.join(w, "frames", "_raw", "*.png")))
    t = time.time()
    # plate + cast where the plate changes; cast only in the locked holds
    for (a, b), plate in [((1, 1), True), (PLATE_MOVING, True)] + [(r, False) for r, _ in PLATE_REUSE]:
        a, b = max(a, f0), min(b, f1)
        if a > b:
            continue
        if (a - 1) % 2:
            a += 1
        _blender_render(o, a, b, plate=plate, tag="p" if plate else "c")
    dt = time.time() - t
    fill_plates(o)
    new = set(glob.glob(os.path.join(w, "frames", "_raw", "*.png"))) - before
    rec = {"frames_rendered": len(new), "seconds": round(dt, 1),
           "seconds_per_rendered_frame": round(dt / max(1, len(new)), 1),
           "settings": {"resolution_pct": int(o["pct"]), "spp": o.get("spp")}}
    path = os.path.join(w, "render_timing.json")
    hist = json.load(open(path)) if os.path.exists(path) else []
    hist.append(rec)
    json.dump(hist, open(path, "w"), indent=1)
    print("RENDER", rec)
    comp(o)


def fill_plates(o):
    d = os.path.join(o["work"], "frames", "plate")
    for (a, b), src in PLATE_REUSE:
        sp = os.path.join(d, "plate_%04d.exr" % src)
        if not os.path.exists(sp):
            continue
        for f in range(a, b + 1, 2):
            dp = os.path.join(d, "plate_%04d.exr" % f)
            if not os.path.exists(dp):
                os.symlink(os.path.basename(sp), dp)


def comp(o):
    """composite = plate x shadow + cast, in the compositing-only scene (fast, no path tracing)"""
    w = o["work"]
    run([BLENDER, "-b", os.path.join(w, "claymation.blend"), "-S", "COMP (plate + cast)", "--python-expr",
         "import bpy; bpy.context.scene.render.resolution_percentage=%d" % int(o["pct"]), "-a"],
        log=os.path.join(w, "comp.log"))


def tracks(o):
    os.makedirs(o["out"], exist_ok=True)
    run([BLENDER, "-b", os.path.join(o["work"], "claymation.blend"), "--python-exit-code", "1", "-P",
         os.path.join(HERE, "clay_tracks.py"), "--", os.path.join(o["out"], "tracks.json")],
        log=os.path.join(o["work"], "tracks.log"))


def closeup(o):
    os.makedirs(o["out"], exist_ok=True)
    png = os.path.join(o["work"], "closeup.png")
    run([BLENDER, "-b", os.path.join(o["work"], "claymation.blend"), "--python-exit-code", "1", "-P",
         os.path.join(HERE, "clay_closeup.py"), "--", png, "287", str(max(48, int(o.get("spp") or 16) * 3))],
        log=os.path.join(o["work"], "closeup.log"))
    from PIL import Image
    Image.open(png).convert("RGB").save(os.path.join(o["out"], "closeup_figures.jpg"), quality=92)


def _twos_sequence(src_dir, prefix, tmp, f0=1, f1=288):
    """symlink each held (odd) frame twice: 1,1,3,3,5,5... -> 0001..0288"""
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for f in range(f0, f1 + 1):
        held = f if (f - f0) % 2 == 0 else f - 1
        os.symlink(os.path.join(src_dir, "%s%04d.png" % (prefix, held)), os.path.join(tmp, "%04d.png" % f))
    return os.path.join(tmp, "%04d.png")


def encode(o):
    w, out = o["work"], o["out"]
    os.makedirs(out, exist_ok=True)
    fr = os.path.join(w, "frames")
    jobs = [("composite", "composite", "composite_", VIGNETTE, 20), ("plate", "plate_view", "plate_view_", VIGNETTE, 21),
            ("matte", "matte", "matte_", None, 24)]
    for name, sub, prefix, vf, crf in jobs:
        pat = _twos_sequence(os.path.join(fr, sub), prefix, os.path.join(w, "seq_" + name))
        filt = ["scale=1280:720:flags=lanczos"] + (["format=gray"] if name == "matte" else [])
        if vf:
            filt.append(vf)
        filt.append("format=yuv420p")
        run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", pat, "-vf", ",".join(filt),
             "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             os.path.join(out, name + ".mp4")])
    contact_sheet(o)
    for n in ("composite", "plate", "matte"):
        p = os.path.join(out, n + ".mp4")
        print(n, "%.2f MB" % (os.path.getsize(p) / 1e6))


def contact_sheet(o):
    from PIL import Image, ImageDraw, ImageFont
    fr = os.path.join(o["work"], "frames", "composite")
    picks = [1, 25, 41, 61, 81, 109, 133, 161, 193, 213, 233, 287]
    ims = [Image.open(os.path.join(fr, "composite_%04d.png" % f)).convert("RGB") for f in picks]
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * 4 + 50, th * 3 + 40 + 60), (24, 22, 20))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        font = big = ImageFont.load_default()
    d.text((12, 14), "Ekkyklema, claymation sample: 12 s, 24 fps on twos (frame / seconds)", fill=(240, 232, 220), font=big)
    for i, (f, im) in enumerate(zip(picks, ims)):
        x, y = 10 + (i % 4) * (tw + 10), 50 + (i // 4) * (th + 10)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        d.rectangle([x, y + th - 24, x + 120, y + th], fill=(0, 0, 0))
        d.text((x + 6, y + th - 22), "f%03d  %.1f s" % (f, (f - 1) / FPS), fill=(255, 255, 255), font=font)
    sheet.save(os.path.join(o["out"], "contact_sheet.jpg"), quality=88)


def main():
    stage, o = opts()
    steps = {"prep": prep, "build": build, "render": render, "tracks": tracks, "closeup": closeup, "encode": encode}
    for s in (["prep", "build", "render", "tracks", "closeup", "encode"] if stage == "all" else [stage]):
        t = time.time()
        steps[s](o)
        print("STAGE %s %.0fs" % (s, time.time() - t))


if __name__ == "__main__":
    main()
