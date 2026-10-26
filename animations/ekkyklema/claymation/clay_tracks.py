"""Export tracks.json for the claymation sample (run inside Blender on the built .blend):

    blender -b claymation.blend --python-exit-code 1 -P clay_tracks.py -- OUT/tracks.json

One record per OUTPUT frame (1..288 at 24 fps). The film is on twos, so frames 2k and 2k-1
share a held pose: each record carries "held_frame", the odd frame actually rendered.

Per frame:
  camera  world location, rotation (quaternion wxyz and XYZ euler, radians), 4x4 matrix_world
          (Blender camera looks down its local -Z, +Y up), lens and sensor (mm), intrinsics in
          pixels (fx, fy, cx, cy; origin top-left, y down), focus distance (m) and f-stop
  slots   for standing_actor, reclining_figure, stagehand_1, stagehand_2:
          object     world location / rotation of the slot root (the reclining figure and the
                     stagehands ride the platform)
          root_bone  world location / rotation of the rig's root bone (pelvis)
          points     head, head_top, wrist_l/r, hand_l/r (palm centre), foot_l/r (ankle),
                     toe_l/r: world xyz (m) and screen xy (pixels), depth (m along the view),
                     in_frame (inside the image and in front of the camera). Occlusion by the
                     set is NOT tested: use the matte_slots images for visibility.
L/R are the puppet's own left/right (MakeHuman ".L"/".R").
"""
import json
import math
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

SLOTS = ["standing_actor", "reclining_figure", "stagehand_1", "stagehand_2"]
POINTS = {
    "head": ("head", "mid"), "head_top": ("head", "tail"),
    "wrist_l": ("wrist.L", "head"), "wrist_r": ("wrist.R", "head"),
    "hand_l": (("wrist.L", "finger3-1.L"), "between"), "hand_r": (("wrist.R", "finger3-1.R"), "between"),
    "foot_l": ("foot.L", "head"), "foot_r": ("foot.R", "head"),
    "toe_l": ("foot.L", "tail"), "toe_r": ("foot.R", "tail"),
}


def r(v, n=4):
    return [round(float(x), n) for x in v]


def xform(M):
    loc, q, _ = M.decompose()
    return {"location": r(loc), "rotation_quaternion_wxyz": r(q, 6), "rotation_euler_xyz": r(q.to_euler(), 6)}


def main():
    out = sys.argv[sys.argv.index("--") + 1]
    sc = bpy.context.scene
    W = sc.render.resolution_x * sc.render.resolution_percentage // 100
    H = sc.render.resolution_y * sc.render.resolution_percentage // 100
    cam = sc.camera
    # the file's active view layer is "plate", which excludes the puppets (so they would not be
    # evaluated): include them in memory only, and skip their heavy subdivision while sampling
    for vl in sc.view_layers:
        lc = vl.layer_collection.children.get("CAST")
        if lc:
            lc.exclude = False
    for ob in bpy.data.objects:
        for md in getattr(ob, "modifiers", []):
            if md.type in ("SUBSURF", "DISPLACE", "SMOOTH", "SURFACE_DEFORM", "SOLIDIFY"):
                md.show_viewport = False
    frames = []
    for f in range(sc.frame_start, sc.frame_end + 1):
        held = f if (f - sc.frame_start) % 2 == 0 else f - 1
        sc.frame_set(held)
        cd = cam.data
        Mc = cam.matrix_world
        fx = cd.lens / cd.sensor_width * W           # sensor fit horizontal
        fy = fx
        focus = cd.dof.focus_object
        fd = (-(Mc.inverted() @ focus.matrix_world.translation).z) if focus else cd.dof.focus_distance
        rec = {"frame": f, "time_s": round((f - 1) / sc.render.fps, 4), "held_frame": held,
               "camera": dict(xform(Mc), matrix_world=[r(row, 6) for row in Mc], lens_mm=round(cd.lens, 4),
                              sensor_width_mm=cd.sensor_width, sensor_fit=cd.sensor_fit,
                              intrinsics_px={"fx": round(fx, 3), "fy": round(fy, 3), "cx": W / 2, "cy": H / 2},
                              focus_distance_m=round(fd, 4), fstop=cd.dof.aperture_fstop),
               "slots": {}}
        for slot in SLOTS:
            root = bpy.data.objects.get(slot + " root")
            rig = bpy.data.objects.get(slot + " rig")
            if rig is None:
                continue
            Mr = rig.matrix_world
            pb = rig.pose.bones
            pts = {}
            for key, (bn, where) in POINTS.items():
                if where == "between":
                    a, b = bn
                    if a not in pb or b not in pb:
                        continue
                    p = Mr @ ((pb[a].head + pb[b].head) / 2)
                else:
                    if bn not in pb:
                        continue
                    b = pb[bn]
                    p = Mr @ {"head": b.head, "tail": b.tail, "mid": (b.head + b.tail) / 2}[where]
                v = world_to_camera_view(sc, cam, p)
                inf = 0.0 <= v.x <= 1.0 and 0.0 <= v.y <= 1.0 and v.z > 0
                pts[key] = {"world": r(p), "screen_px": [round(v.x * W, 2), round((1 - v.y) * H, 2)],
                            "depth_m": round(v.z, 4), "in_frame": bool(inf)}
            rb = pb.get("root")
            rec["slots"][slot] = {
                "object": xform(root.matrix_world) if root else None,
                "root_bone": xform(Mr @ rb.matrix) if rb else None,
                "points": pts,
            }
        frames.append(rec)
    data = {
        "about": __doc__.strip().splitlines()[0],
        "fps": sc.render.fps, "on": "twos (every other frame rendered; see held_frame)",
        "resolution": [W, H], "frame_start": sc.frame_start, "frame_end": sc.frame_end,
        "units": "metres (scene units; the set is a miniature of the full-size reconstruction)",
        "screen_origin": "top-left, x right, y down, pixels",
        "camera_name": cam.name, "slots": SLOTS, "frames": frames,
    }
    with open(out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print("TRACKS", out, len(frames), "frames")


if __name__ == "__main__":
    main()
