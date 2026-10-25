"""Render the Phase-1 look test and the timing probes from ekkyklema.blend.

    blender -b ekkyklema.blend -P render_looktest.py -- stills  OUTDIR [SAMPLES] [TAG ...]
    blender -b ekkyklema.blend -P render_looktest.py -- clip    OUTDIR [SAMPLES] [PERCENT] [FIRST LAST]
    blender -b ekkyklema.blend -P render_looktest.py -- timing  OUTDIR

stills: the four 1920x1080 look-test frames (a)-(d), plus timing per frame.
clip:   frames of the "LT clip" camera (doors open, then the roll-out), PNG sequence;
        encode with ffmpeg afterwards (see SHOTLIST.md, "Look test").
timing: one representative frame per shot type at 1920x1080 and 1280x720 and at
        several sample counts; writes timing.csv in OUTDIR.
"""
import csv
import os
import sys
import time

import bpy

FPS = 24


def F(sec):
    return int(round(sec * FPS)) + 1


argv = sys.argv[sys.argv.index("--") + 1:]
mode, outdir = argv[0], os.path.abspath(argv[1])
os.makedirs(outdir, exist_ok=True)
sc = bpy.context.scene

STILLS = [
    ("a_establishing", "SH01 establishing", F(2.5)),
    ("b_audience_eye", "LT b audience eye", F(45.0)),
    ("c_cutaway", "SH04 doors open (cutaway)", F(29.5)),
    ("d_tableau_closeup", "SH07 orbit the tableau", F(52.0)),
]
PROBES = [   # representative frames for the timing table: (label, camera, frame)
    ("aerial", "SH01 establishing", F(2.5)),
    ("audience", "SH06 audience eye", F(44.0)),
    ("cutaway", "SH05 tracking the roll-out", F(37.0)),
    ("closeup", "SH07 orbit the tableau", F(51.0)),
    ("overhead", "SH10 overhead: what is disputed", F(72.0)),
]


def use_camera(name):
    for m in sc.timeline_markers:
        m.camera = None
    sc.camera = bpy.data.objects[name]


def render(path, cam, frame, w, h, spp):
    use_camera(cam)
    sc.frame_set(frame)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.cycles.samples = spp
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - t


if mode == "stills":
    spp = int(argv[2]) if len(argv) > 2 else 64
    only = set(argv[3:])                       # optional: render only these still tags
    rows = []
    for tag, cam, fr in STILLS:
        if only and tag not in only:
            continue
        dt = render(os.path.join(outdir, tag + ".png"), cam, fr, 1920, 1080, spp)
        rows.append((tag, cam, fr, 1920, 1080, spp, round(dt, 1)))
        print("STILL %s %.1fs" % (tag, dt))
    with open(os.path.join(outdir, "stills_timing.csv"), "w", newline="") as f:
        csv.writer(f).writerows([("still", "camera", "frame", "w", "h", "samples", "seconds")] + rows)

elif mode == "clip":
    spp = int(argv[2]) if len(argv) > 2 else 32
    pct = int(argv[3]) if len(argv) > 3 else 100
    use_camera("LT clip")
    # the clip is front coverage of a stretch the edit shows in section (SH04/SH05):
    # switch the section cut off for it
    vc = bpy.data.objects["Section cutter (vertical)"]
    if vc.animation_data and vc.animation_data.action:
        for fc in vc.animation_data.action.fcurves:
            fc.mute = True
    vc.location.x = -80.0
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, pct
    sc.cycles.samples = spp
    f0, f1 = F(30.8), F(38.8) - 1
    if len(argv) > 5:                          # optional sub-range (re-render part of the clip)
        f0, f1 = int(argv[4]), int(argv[5])
    t0 = time.time()
    for fr in range(f0, f1 + 1):
        sc.frame_set(fr)
        sc.render.filepath = os.path.join(outdir, "clip_%04d.png" % fr)
        bpy.ops.render.render(write_still=True)
    dt = time.time() - t0
    n = f1 - f0 + 1
    print("CLIP %d frames %.1fs  %.1fs/frame" % (n, dt, dt / n))
    with open(os.path.join(outdir, "clip_timing.txt"), "w") as f:
        f.write("frames %d-%d (%d) at 1280x720 x %d%%, %d samples: %.1f s total, %.1f s/frame\n" % (f0, f1, n, pct, spp, dt, dt / n))

elif mode == "timing":
    configs = [(1920, 1080, 64), (1920, 1080, 32), (1280, 720, 64), (1280, 720, 32), (1280, 720, 16)]
    if len(argv) > 2:
        configs = [tuple(int(v) for v in c.split("x")) for c in argv[2:]]
    rows = []
    # warm-up: the first render of a session pays for loading images and building the BVH
    render(os.path.join(outdir, "warmup.png"), PROBES[0][1], PROBES[0][2], 320, 180, 1)
    for (w, h, spp) in configs:
        for label, cam, fr in PROBES:
            path = os.path.join(outdir, "t_%s_%dp_%d.png" % (label, h, spp))
            dt = render(path, cam, fr, w, h, spp)
            rows.append((label, cam, fr, w, h, spp, round(dt, 1)))
            print("TIMING %s %dx%d %dspp %.1fs" % (label, w, h, spp, dt))
            with open(os.path.join(outdir, "timing.csv"), "w", newline="") as f:
                csv.writer(f).writerows([("probe", "camera", "frame", "w", "h", "samples", "seconds")] + rows)
