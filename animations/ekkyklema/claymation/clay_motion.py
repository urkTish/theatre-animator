"""Puppet animation for the claymation sample (imported by clay_figures.py).

Poses are authored with the v3 Poser (world-space aims and two-bone IK on the MakeHuman rig),
in platform-local coordinates before the puppets are parented to their slot roots, then
BAKED ON TWOS: one key per held pose (every odd frame), constant interpolation, with a little
hand-made irregularity (tiny random rotations while a puppet moves, a slow breath in holds).
Masked faces cannot act, so the acting is posture and gesture:

  standing actor   waits (arms down), turns his head to the door as it opens, follows the
                   platform out, then (anticipation, overshoot, settle) raises his right arm,
                   palm up, presenting the reclining man
  reclining figure lies still with his right hand on his hip while the platform rolls, then
                   answers: lifts the open right hand toward the actor and turns his head to him
  stagehands       crouched at the rear rail; while the platform rolls they push it with short
                   stepping feet; when it stops they let go and sit back on their heels, low
                   behind the couch and in the dark of the doorway
"""
import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

import clay_build as cb

JITTER_BONES = ["spine03", "spine01", "neck02", "head", "upperarm01.L", "upperarm01.R",
                "lowerarm01.L", "lowerarm01.R", "clavicle.L", "clavicle.R"]


def reset_fingers(P, side):
    for f in range(1, 6):
        for j in range(1, 4):
            n = "finger%d-%d.%s" % (f, j, side)
            if n in P.basis:
                P.basis[n] = Matrix.Identity(4)


# =============================================================================================
# standing actor
# =============================================================================================
def standing_poses(F, P, rig):
    out = {}
    B = F.POSERS["Standing actor"](P, rig)
    out["present"] = P.snapshot()

    def arm_down(head_front, lean=0.0, wrist=(-0.225, 0.07, 0.88)):
        F.POSERS["Standing actor"](P, rig)
        P.aim("clavicle.R", B.d(-1, 0.02, -0.04))
        P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
                   B.p(*wrist), B.d(-0.25, -1, 0.0))
        P.hand("R", B.d(-0.08, 0.18, -1), B.d(1, 0.15, 0))
        reset_fingers(P, "R")
        F.hand_shape(P, "R", "relaxed")
        for n, u in (("neck02", B.d(0.02, 0.12 + lean, 1)), ("neck03", B.d(0.02, 0.12 + lean, 1)),
                     ("head", B.d(-0.04, 0.08 + lean, 1))):
            P.aim(n, u, (0, -1, 0), head_front)
        return P.snapshot()

    out["wait_front"] = arm_down(B.d(-0.35, 1, -0.02))
    out["wait_door"] = arm_down(B.d(0.28, 1, -0.06), lean=0.06)
    out["wait_follow"] = arm_down(B.d(-0.05, 1, -0.16), lean=0.04)
    # anticipation: the arm draws back a little before it rises
    F.POSERS["Standing actor"](P, rig)
    P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
               B.p(-0.27, -0.03, 0.95), B.d(-0.4, -1, -0.2))
    P.hand("R", B.d(-0.1, 0.4, -0.9), B.d(0.9, 0.2, 0.3))
    reset_fingers(P, "R")
    F.hand_shape(P, "R", "relaxed")
    for n, u in (("neck03", B.d(0.02, 0.18, 1)), ("head", B.d(-0.06, 0.16, 1))):
        P.aim(n, u, (0, -1, 0), B.d(-0.12, 1, -0.2))
    out["antic"] = P.snapshot()
    # overshoot: higher and more open than the final gesture
    F.POSERS["Standing actor"](P, rig)
    P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
               B.p(-0.25, 0.45, 1.38), B.d(-0.6, -0.2, -1))
    P.hand("R", B.d(-0.2, 1, 0.22), B.d(0.35, 0.05, 1))
    reset_fingers(P, "R")
    F.hand_shape(P, "R", "address")
    for n, u in (("neck03", B.d(0.02, 0.14, 1)), ("head", B.d(-0.06, 0.04, 1))):
        P.aim(n, u, (0, -1, 0), B.d(-0.12, 1, -0.06))
    out["over"] = P.snapshot()
    F.POSERS["Standing actor"](P, rig)
    keys = [(0.0, "wait_front"), (0.9, "wait_front"), (1.6, "wait_door"), (4.3, "wait_door"),
            (6.0, "wait_follow"), (7.7, "wait_follow"), (8.25, "antic"), (8.9, "over"), (9.5, "present"),
            (12.0, "present")]
    return [(t, out[k]) for t, k in keys]


# =============================================================================================
# reclining figure
# =============================================================================================
def reclining_poses(F, P, rig):
    out = {}
    F.POSERS["Reclining actor"](P, rig)
    out["answer"] = P.snapshot()

    def head(front, ups=((-0.30, 0.12, 0.95), (-0.20, 0.14, 0.97), (-0.12, 0.14, 0.98), (-0.12, 0.10, 0.99))):
        for n, u in zip(("neck01", "neck02", "neck03", "head"), ups):
            P.aim(n, u, (0, -1, 0), front)

    def rest(front):
        F.POSERS["Reclining actor"](P, rig)
        P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
                   (0.02, 0.10, 1.13), Vector((0.0, -0.6, 1.0)))
        P.hand("R", (0.85, 0.15, -0.35), (0.05, 0.25, -1))
        reset_fingers(P, "R")
        F.hand_shape(P, "R", "rest")
        head(Vector(front).normalized())
        return P.snapshot()

    out["rest_out"] = rest((0.25, 0.95, -0.12))      # looking out over the audience
    out["rest_turn"] = rest((0.6, 0.78, -0.12))
    F.POSERS["Reclining actor"](P, rig)
    P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
               (-0.08, 0.20, 1.12), Vector((0.1, -0.5, -1)))
    P.hand("R", (0.8, 0.3, -0.1), (0.1, 0.1, 1))
    reset_fingers(P, "R")
    F.hand_shape(P, "R", "relaxed")
    head(Vector((0.7, 0.68, -0.12)).normalized())
    out["antic"] = P.snapshot()
    F.POSERS["Reclining actor"](P, rig)
    P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
               (-0.12, 0.33, 1.33), Vector((0.1, -0.4, -1)))
    P.hand("R", (0.75, 0.42, 0.42), (0.10, 0.30, 0.95))
    reset_fingers(P, "R")
    F.hand_shape(P, "R", "address")
    head(Vector((0.84, 0.54, -0.06)).normalized())
    out["over"] = P.snapshot()
    F.POSERS["Reclining actor"](P, rig)
    keys = [(0.0, "rest_out"), (8.6, "rest_out"), (9.3, "rest_turn"), (9.65, "antic"), (10.25, "over"),
            (10.8, "answer"), (12.0, "answer")]
    return [(t, out[k]) for t, k in keys]


# =============================================================================================
# stagehands
# =============================================================================================
def stagehand_pose(F, P, rig, x, lead, var, lean_deg=52.0, root_dy=0.0, root_dz=0.0, hands="rail",
                   feet=((0.0, 0.0), (0.0, 0.0)), shift=(0.0, 0.0)):
    """pose_stagehand from figures_v3 with parameters: lean, root offset, hands on the rail or on
    the knees, and per-foot (dy, lift) offsets in the body frame (fwd foot first)"""
    g = Vector((x, F.REAR - 0.70, 0.0))
    F.place_rig(rig, g, (0, 1, 0))
    B = F.Frame(g, (0, 0, 1), (0, 1, 0))
    P.reset()
    s = 1.0 if lead == "L" else -1.0
    lean = math.radians(lean_deg + 4 * var)
    up = B.d(0.0, math.sin(lean), math.cos(lean))
    fr = B.d(0.0, math.cos(lean), -math.sin(lean))
    sh = Vector((shift[0], shift[1], 0.0))          # world offset (platform-local x, y)
    root = B.p(0.0, -0.06 + root_dy, 0.50 + root_dz) + sh
    R = Matrix.Rotation(math.radians(-6 * s), 3, B.U) @ F.basis_from(up, fr)
    P.place_root(root, R)
    up_c = B.d(0.0, math.sin(lean + 0.18), math.cos(lean + 0.18))
    fr_c = B.d(0.0, math.cos(lean + 0.18), -math.sin(lean + 0.18))
    P.spine(["spine05", "spine04", "spine03", "spine02", "spine01"], up, up_c, fr, fr_c)
    for n, u, f in (("neck01", B.d(0, 0.75, 0.66), B.d(0, 0.6, -0.8)), ("neck02", B.d(0, 0.6, 0.8), B.d(0, 0.75, -0.66)),
                    ("neck03", B.d(0, 0.45, 0.9), B.d(0, 0.85, -0.5)), ("head", B.d(0.03 * s, 0.32, 0.95), B.d(0, 0.92, -0.35))):
        P.aim(n, u, (0, -1, 0), f)
    fwd, back = ("L", "R") if lead == "L" else ("R", "L")
    sf = 1.0 if fwd == "L" else -1.0
    (dyf, lf), (dyb, lb) = feet
    for sd, sx in (("L", 1.0), ("R", -1.0)):
        P.aim("clavicle." + sd, B.d(sx, 0.35, 0.1))
        if hands == "rail":
            tgt = Vector((x - sx * 0.19, F.REAR - 0.085, F.PLAT_H + 0.035))
            P.two_bone(["upperarm01." + sd, "upperarm02." + sd], ["lowerarm01." + sd, "lowerarm02." + sd],
                       "wrist." + sd, tgt, B.d(sx * 0.9, -0.2, 0.1))
            P.hand(sd, B.d(-sx * 0.15, 0.97, -0.05), (0, 0, -1))
            F.hand_shape(P, sd, "push")
        else:   # on the knees / thighs
            kn = B.p(sx * 0.15, (0.12 if sd == fwd else -0.12) + root_dy * 0.5, 0.34 + root_dz) + sh
            P.two_bone(["upperarm01." + sd, "upperarm02." + sd], ["lowerarm01." + sd, "lowerarm02." + sd],
                       "wrist." + sd, kn, B.d(sx * 0.9, -0.4, 0.0))
            P.hand(sd, B.d(sx * 0.1, 0.9, -0.45), B.d(0, 0, -1))
            F.hand_shape(P, sd, "relaxed")
    P.two_bone(["upperleg01." + fwd, "upperleg02." + fwd], ["lowerleg01." + fwd, "lowerleg02." + fwd], "foot." + fwd,
               B.p(sf * 0.17, 0.20 + dyf, 0.095 + lf) + sh, B.d(sf * 0.55, 1, 0.3))
    P.two_bone(["upperleg01." + back, "upperleg02." + back], ["lowerleg01." + back, "lowerleg02." + back], "foot." + back,
               B.p(-sf * 0.11, -0.46 + dyb, 0.13 + lb) + sh, B.d(-sf * 0.2, 1, -0.4))
    P.aim("foot." + fwd, B.d(sf * 0.25, 0.85, -0.48), (0, 0, -1), (0, 0, -1))
    P.aim("foot." + back, B.d(-sf * 0.05, 0.25, -0.97), (0, 0, -1), B.d(0, -1, -0.2))
    for t in ("toe1-1.", "toe2-1.", "toe3-1.", "toe4-1.", "toe5-1."):
        P.aim(t + back, B.d(0, 1, -0.05), (0, 0, -1), (0, 0, -1))
    return P.snapshot()


def platform_travel(f):
    fc = bpy.data.objects["Platform ctrl"].animation_data.action.fcurves.find("location", index=1)
    return fc.evaluate(f) - cb.PLAT_Y0


def stagehand_poses(F, P, rig, x, lead, var, phase):
    """dense keys (every odd frame) through the push: feet step to keep up with the platform"""
    total = cb.PLAT_Y1 - cb.PLAT_Y0
    L = total / 5.0                      # step length (m)
    keys = []
    r0, r1 = cb.F(cb.T_ROLL[0]), cb.F(cb.T_ROLL[1])
    keys.append((0.0, stagehand_pose(F, P, rig, x, lead, var, lean_deg=46.0)))
    keys.append(((r0 - 9) / cb.FPS, stagehand_pose(F, P, rig, x, lead, var, lean_deg=46.0)))
    keys.append(((r0 - 1) / cb.FPS, stagehand_pose(F, P, rig, x, lead, var, lean_deg=54.0)))
    for f in range(r0 + 1, r1 + 1, 2):
        D = platform_travel(f)
        env = min(1.0, D / 0.25, (total - D) / 0.25) if 0 < D < total else 0.0
        env = max(0.0, env)

        def foot(ph):
            u = (D / L + ph) % 2.0
            if u < 1.0:
                dy, lift = L / 2 - u * L, 0.0
            else:
                v = u - 1.0
                dy, lift = -L / 2 + v * L, math.sin(math.pi * v) * 0.07
            return dy * env, lift * env

        bob = 0.015 * math.sin(2 * math.pi * D / L) * env
        p = stagehand_pose(F, P, rig, x, lead, var, lean_deg=55.0, root_dz=bob,
                           feet=(foot(0.5 + phase), foot(1.5 + phase)))
        keys.append(((f - 1) / cb.FPS, p))
    t_end = (r1 - 1) / cb.FPS
    # let go, shuffle back and toward the middle, and sink low behind the couch (out of sight)
    sh = (0.05, -0.18) if x < 0 else (-0.3, -0.22)
    half = (sh[0] * 0.5, sh[1] * 0.5)
    keys.append((t_end + 0.35, stagehand_pose(F, P, rig, x, lead, var, lean_deg=40.0, root_dy=-0.04)))
    keys.append((t_end + 0.8, stagehand_pose(F, P, rig, x, lead, var, lean_deg=30.0, root_dy=-0.1,
                                              root_dz=-0.08, hands="knees", shift=half,
                                              feet=((-0.04, 0.05), (0.0, 0.0)))))
    keys.append((t_end + 1.25, stagehand_pose(F, P, rig, x, lead, var, lean_deg=22.0, root_dy=-0.16,
                                               root_dz=-0.17, hands="knees", shift=sh)))
    keys.append((cb.DURATION, stagehand_pose(F, P, rig, x, lead, var, lean_deg=20.0, root_dy=-0.17,
                                              root_dz=-0.18, hands="knees", shift=sh)))
    return keys


# =============================================================================================
def author_poses(F, figs):
    keys = {}
    for name, fg in figs.items():
        P, rig = fg["P"], fg["rig"]
        if name == "Standing actor":
            keys[name] = standing_poses(F, P, rig)
        elif name == "Reclining actor":
            keys[name] = reclining_poses(F, P, rig)
        else:
            x, lead, var, ph = (-0.55, "L", 0.0, 0.0) if name == "Stagehand A" else (0.55, "R", 1.0, 0.5)
            keys[name] = stagehand_poses(F, P, rig, x, lead, var, ph)
        # leave the rig at its base pose (bindings were made there)
        P.apply(fg["base"])
        F.place_rig(rig, *_rig_place(F, name))
    bpy.context.view_layer.update()
    return keys


def _rig_place(F, name):
    if name == "Standing actor":
        face = Vector((-0.88, -0.30, 0.0)).normalized()
        return Vector((2.03, 0.674, 0.0)), face
    if name == "Reclining actor":
        return Vector((-0.16, -0.24, 0.0)), (0, 1, 0)
    x = -0.55 if name == "Stagehand A" else 0.55
    return Vector((x, F.REAR - 0.70, 0.0)), (0, 1, 0)


# =============================================================================================
# baking on twos
# =============================================================================================
def _dec(m):
    loc, q, s = m.decompose()
    return loc, q, s


def _blend(a, b, t):
    la, qa, sa = _dec(a)
    lb, qb, sb = _dec(b)
    if qa.dot(qb) < 0:
        qb = -qb
    return la.lerp(lb, t), qa.slerp(qb, t), sa.lerp(sb, t)


def bake(figs, keys):
    from clay_figures import HEAD_SCALE, HAND_SCALE
    rnd = random.Random(7)
    for name, fg in figs.items():
        rig = fg["rig"]
        K = sorted(keys[name], key=lambda k: k[0])
        dense = name.startswith("Stagehand")
        # bones that move at all (plus scale and jitter bones)
        moving = set()
        for (_, a), (_, b) in zip(K, K[1:]):
            for n in a:
                if any(abs(v) > 1e-6 for row in (a[n] - b[n]) for v in row):
                    moving.add(n)
        keyed = moving | {"head", "wrist.L", "wrist.R"} | set(JITTER_BONES) | {"spine01", "spine03"}
        keyed = [n for n in keyed if n in rig.pose.bones]
        prev = {}
        ad = rig.animation_data_create()
        for f in range(cb.F_START, cb.F_END + 1, 2):
            s = (f - 1) / cb.FPS
            i = max(0, max(j for j, k in enumerate(K) if k[0] <= s + 1e-6))
            a = K[i]
            b = K[min(i + 1, len(K) - 1)]
            if b[0] > a[0]:
                t = (s - a[0]) / (b[0] - a[0])
                t = t if dense else cb.ease_in_out(t, 2.0)
            else:
                t = 0.0
            moving_now = a[1] is not b[1] and 0.0 < t < 1.0
            amp = 0.35 if moving_now else 0.08
            for n in keyed:
                loc, q, sc = _blend(a[1][n], b[1][n], t)
                if n in JITTER_BONES:
                    e = Vector((rnd.gauss(0, amp), rnd.gauss(0, amp), rnd.gauss(0, amp)))
                    q = q @ Quaternion(e.normalized() if e.length else Vector((1, 0, 0)), math.radians(e.length))
                if n in ("spine01", "spine03") and not dense:       # breathing in the holds
                    q = q @ Quaternion((1, 0, 0), math.radians(0.5 * math.sin(2 * math.pi * s / 3.2)))
                if n == "head":
                    sc = Vector((1, 1, 1)) * HEAD_SCALE[name]
                if n in ("wrist.L", "wrist.R"):
                    sc = Vector((1, 1, 1)) * HAND_SCALE
                if n in prev and prev[n].dot(q) < 0:
                    q = -q
                prev[n] = q
                pb = rig.pose.bones[n]
                pb.rotation_mode = "QUATERNION"
                pb.location = loc
                pb.rotation_quaternion = q
                pb.scale = sc
                pb.keyframe_insert("location", frame=f)
                pb.keyframe_insert("rotation_quaternion", frame=f)
                pb.keyframe_insert("scale", frame=f)
        for fc in ad.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"
        print("BAKED", name, len(keyed), "bones")
