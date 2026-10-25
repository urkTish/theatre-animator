"""Ekkyklema 3D -- COMPARISON TEST ONLY: MakeHuman (MPFB2) figures vs the scene's mannequins.

Not part of the main build: it never touches build_scene.py, render_looktest.py or the
main .blend files. It works on a *copy* of the built scene and writes to its own folder.

    # everything (spawns Blender for the stages, then composes the comparison images):
    python3 makehuman_test.py all --scene COPY.blend --work DIR [--samples 64]
                              [--blender /opt/blender/blender] [--mpfb-resources DIR] [--repo-out DIR]

    # the stages one by one
    BLENDER_USER_RESOURCES=DIR blender -b -P makehuman_test.py -- build   --scene COPY.blend --work DIR
    blender -b COPY.blend -P makehuman_test.py -- render --work DIR [--samples 64] [--only A|B]
    python3 makehuman_test.py compose --work DIR [--repo-out DIR]

build   (needs the MPFB extension, installed in an isolated Blender user folder, see
        MAKEHUMAN_NOTES.md): makes the four MakeHuman figures with MPFB, poses them with
        the MakeHuman "default" rig, drapes chiton / tunics / himation / blanket with
        Blender cloth simulation, models the tragic masks and wigs, freezes everything to
        static meshes and saves DIR/figures.blend. Figures are built in platform-local
        coordinates (platform rig at the origin), like build_scene.py builds the tableau.
render  opens the scene copy, appends the frozen figures, places them where the
        mannequins are, and renders the two look-test frames twice:
        A = the scene as it is (mannequins), B = mannequins hidden, MakeHuman figures shown.
compose side-by-side images with labels, a close crop, and JPG copies for the repo.

Re-runnable: every stage rebuilds its outputs from scratch.
"""
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    import bpy
    import bmesh
    from mathutils import Matrix, Quaternion, Vector, noise
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

FPS = 24


def F(sec):
    return int(round(sec * FPS)) + 1


# look-test stills reproduced here (render_looktest.py STILLS)
SHOTS = {
    "tableau": ("SH07 orbit the tableau", F(52.0)),         # look-test "d_tableau_closeup"
    "cutaway": ("SH04 doors open (cutaway)", F(29.5)),      # look-test "c_cutaway"
}


def get_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    mode = argv[0] if argv else "all"
    opts = {}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opts[a[2:]] = argv[i + 1]
                i += 2
            else:
                opts[a[2:]] = True
                i += 1
        else:
            i += 1
    return mode, opts


# =============================================================================
# reference data from build_scene.py (STORYBOARD R1/R5): platform-local coordinates
# =============================================================================
PLAT_W, PLAT_D, PLAT_H = 2.4, 1.6, 0.30
COUCH_C = (0.04, -0.20)
COUCH_L, COUCH_W = 1.95, 0.82
Z_FRAME = PLAT_H + 0.43
Z_MATT = Z_FRAME + 0.11
REAR = -PLAT_D / 2                      # rear edge of the platform (local y)

CONTEXT_OBJECTS = ["Platform deck", "Platform frame", "Couch (kline)", "Mattress", "Cushion 0", "Cushion 1",
                   "Stool (diphros)", "Folded cloth", "Kylix"]

if IN_BLENDER:
    # ==========================================================================
    # small helpers
    # ==========================================================================
    def V(*a):
        return Vector(a[0] if len(a) == 1 else a)

    def link_to(ob, coll):
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)

    def get_coll(name, parent=None):
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            (parent or bpy.context.scene.collection).children.link(c)
        return c

    def basis_from(up, front):
        """3x3 rotation taking MakeHuman rest axes (up +Z, front -Y, left +X) to the given world
        up / front directions"""
        up = V(up).normalized()
        fr = V(front)
        fr = (fr - up * fr.dot(up)).normalized()
        left = up.cross(fr)
        # columns: images of +X (left), +Y (= -front), +Z (up)
        return Matrix((left, -fr, up)).transposed()

    def smoothstep(a, b, x):
        t = max(0.0, min(1.0, (x - a) / (b - a)))
        return t * t * (3 - 2 * t)

    # ==========================================================================
    # Poser: pose the MakeHuman default rig by world-space aims, analytic IK and
    # finger curls; computes every bone's armature-space matrix itself, so the
    # result is exact and needs no depsgraph updates while posing.
    # ==========================================================================
    _POSERS_ALIVE = []

    class Poser:
        def __init__(self, rig):
            _POSERS_ALIVE.append(self)
            self.rig = rig
            self.rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
            self.par = {b.name: (b.parent.name if b.parent else None) for b in rig.data.bones}
            self.tail_len = {b.name: b.length for b in rig.data.bones}
            self.basis = {n: Matrix.Identity(4) for n in self.rest}
            self.refresh()

        def refresh(self):
            """call after moving the armature object"""
            self.inv_w = self.rig.matrix_world.inverted()      # world -> armature space
            self.rot_w = self.rig.matrix_world.to_3x3().normalized()

        def reset(self):
            for n in self.basis:
                self.basis[n] = Matrix.Identity(4)

        # armature-space matrices -------------------------------------------
        def chain(self, n):
            """pose matrix of n with its own basis = identity"""
            p = self.par[n]
            if p is None:
                return self.rest[n].copy()
            return self.P(p) @ self.rest[p].inverted() @ self.rest[n]

        def P(self, n):
            return self.chain(n) @ self.basis[n]

        def head(self, n):            # world
            return self.rig.matrix_world @ self.P(n).translation

        def tail(self, n):
            M = self.P(n)
            return self.rig.matrix_world @ (M.translation + M.col[1].xyz.normalized() * self.tail_len[n])

        def wdir(self, v):            # world direction -> armature
            return (self.rot_w.inverted() @ V(v)).normalized()

        # posing ---------------------------------------------------------------
        def aim(self, n, d, v_rest=None, v_target=None, twist=0.0):
            """point bone n's Y axis along world direction d. Optional roll: the vector v_rest
            (armature rest-pose coordinates) is turned as close as possible to world v_target."""
            M0 = self.chain(n)
            C = M0.to_3x3().normalized()
            d = self.wdir(d)
            y0 = C.col[1].normalized()
            R = y0.rotation_difference(d).to_matrix()
            Mr = R @ C
            if v_rest is not None and v_target is not None:
                Rr = self.rest[n].to_3x3().normalized()
                v_loc = Rr.inverted() @ V(v_rest)
                cur = Mr @ v_loc
                want = self.wdir(v_target)
                cur = cur - d * cur.dot(d)
                want = want - d * want.dot(d)
                if cur.length > 1e-6 and want.length > 1e-6:
                    cur.normalize()
                    want.normalize()
                    ang = math.atan2(cur.cross(want).dot(d), cur.dot(want))
                    Mr = Matrix.Rotation(ang, 3, d) @ Mr
            if twist:
                Mr = Matrix.Rotation(math.radians(twist), 3, d) @ Mr
            Md = Matrix.Translation(M0.translation) @ Mr.to_4x4()
            self.basis[n] = M0.inverted() @ Md

        def rot_local(self, n, x=0.0, y=0.0, z=0.0):
            """extra local rotation in degrees (XYZ euler) on top of the current basis"""
            e = Matrix.Rotation(math.radians(x), 4, "X") @ Matrix.Rotation(math.radians(y), 4, "Y") @ Matrix.Rotation(math.radians(z), 4, "Z")
            self.basis[n] = self.basis[n] @ e

        def place_root(self, loc_world, R_world):
            """root bone: world position of its head and world orientation (3x3, relative to rest)"""
            rest = self.rest["root"]
            A = self.inv_w.to_3x3().normalized() @ R_world
            Md = Matrix.Translation(self.inv_w @ V(loc_world)) @ (A @ rest.to_3x3().normalized()).to_4x4()
            self.basis["root"] = rest.inverted() @ Md

        def spine(self, bones, up0, up1, front0, front1):
            """distribute a bend over a chain: directions blend from up0 to up1, fronts likewise"""
            n = len(bones)
            for i, b in enumerate(bones):
                t = (i + 0.5) / n
                u = V(up0).lerp(V(up1), t).normalized()
                f = V(front0).lerp(V(front1), t).normalized()
                self.aim(b, u, (0, -1, 0), f)

        def two_bone(self, b1, b2, end_bone, target, pole, iters=4):
            """analytic two-bone IK over twin-bone segments: b1/b2 are lists of bones aimed as one
            segment (e.g. [upperarm01, upperarm02]); end_bone is the bone whose head must reach
            target (world)."""
            target = V(target)
            pole = V(pole)
            goal = target.copy()
            for _ in range(iters):
                s = self.head(b1[0])
                # current segment lengths (rest)
                l1 = (self.rest[b1[-1]].translation + self.rest[b1[-1]].col[1].xyz.normalized() * self.tail_len[b1[-1]]
                      - self.rest[b1[0]].translation).length
                l2 = (self.rest[end_bone].translation - self.rest[b2[0]].translation).length
                d = goal - s
                dist = max(abs(l1 - l2) + 1e-4, min(l1 + l2 - 1e-4, d.length))
                dn = d.normalized()
                ca = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
                a = math.acos(max(-1.0, min(1.0, ca)))
                pp = pole - dn * pole.dot(dn)
                pp.normalize()
                d1 = dn * math.cos(a) + pp * math.sin(a)
                mid = s + d1 * l1
                d2 = (s + dn * dist - mid).normalized()
                for b in b1:
                    self.aim(b, d1)
                for b in b2:
                    self.aim(b, d2)
                err = target - self.head(end_bone)
                if err.length < 0.002:
                    break
                goal = goal + err
            return (target - self.head(end_bone)).length

        def palm_normal_rest(self, side):
            W = self.rest["wrist." + side].translation
            M = self.rest["finger3-1." + side].translation
            I = self.rest["finger2-1." + side].translation
            L = self.rest["finger5-1." + side].translation
            Fv = (M - W)
            A = (I - L)
            n = Fv.cross(A) if side == "L" else A.cross(Fv)
            return n.normalized()

        def hand(self, side, d, palm, twist_share=(0.25, 0.35)):
            """aim the hand along world d with the palm facing world `palm`; part of the needed roll
            is moved into the forearm twist bones so the wrist does not candy-wrap"""
            n_rest = self.palm_normal_rest(side)
            w = "wrist." + side
            # first solve the wrist alone to find how much roll it needs
            self.aim(w, d, n_rest, palm)
            # roll of the wrist about the forearm axis
            fa = (self.head(w) - self.head("lowerarm01." + side)).normalized()
            Mw = self.P(w).to_3x3()
            M0 = self.chain(w).to_3x3()
            Rr = self.rest[w].to_3x3().normalized()
            nl = Rr.inverted() @ n_rest
            a = M0 @ nl
            b = Mw @ nl
            a = a - fa * a.dot(fa)
            b = b - fa * b.dot(fa)
            if a.length > 1e-6 and b.length > 1e-6:
                ang = math.degrees(math.atan2(a.normalized().cross(b.normalized()).dot(fa), a.normalized().dot(b.normalized())))
                for bn, share in (("lowerarm01." + side, twist_share[0]), ("lowerarm02." + side, twist_share[1])):
                    self.aim(bn, self.tail(bn) - self.head(bn), twist=ang * share)
            self.aim(w, d, n_rest, palm)

        def fingers(self, side, curls, spread=None, thumb=None):
            """curls: {finger index 2..5: (deg joint1, joint2, joint3)}; flexion about local X.
            spread: {finger: deg about local Z}; thumb: ((x,y,z) deg for finger1-1, curl 2, curl 3)"""
            sgn = 1.0
            for f, c in curls.items():
                for j in range(3):
                    self.rot_local("finger%d-%d.%s" % (f, j + 1, side), x=sgn * c[j])
            if spread:
                for f, s in spread.items():
                    self.rot_local("finger%d-1.%s" % (f, side), z=s if side == "L" else -s)
            if thumb:
                (tx, ty, tz), c2, c3 = thumb
                self.rot_local("finger1-1.%s" % side, x=tx, y=ty if side == "L" else -ty, z=tz if side == "L" else -tz)
                self.rot_local("finger1-2.%s" % side, x=c2)
                self.rot_local("finger1-3.%s" % side, x=c3)

        # output ---------------------------------------------------------------
        def snapshot(self):
            return {n: m.copy() for n, m in self.basis.items()}

        def apply(self, basis=None, frame=None):
            basis = basis or self.basis
            for n, m in basis.items():
                pb = self.rig.pose.bones[n]
                pb.rotation_mode = "QUATERNION"
                loc, q, _ = m.decompose()
                pb.rotation_quaternion = q
                pb.location = loc
                if frame is not None:
                    pb.keyframe_insert("rotation_quaternion", frame=frame)
                    pb.keyframe_insert("location", frame=frame)

    def key_pose_sequence(rig, poses):
        """poses: list of (frame, basis dict); keeps quaternions in one hemisphere"""
        prev = {}
        for fr, basis in poses:
            for n, m in basis.items():
                pb = rig.pose.bones[n]
                pb.rotation_mode = "QUATERNION"
                loc, q, _ = m.decompose()
                if n in prev and prev[n].dot(q) < 0:
                    q = -q
                prev[n] = q
                pb.rotation_quaternion = q
                pb.location = loc
                pb.keyframe_insert("rotation_quaternion", frame=fr)
                pb.keyframe_insert("location", frame=fr)
        ad = rig.animation_data
        if ad and ad.action:
            for fc in ad.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.easing = "AUTO"

    # ==========================================================================
    # MPFB access
    # ==========================================================================
    def mpfb():
        try:
            from bl_ext.user_default.mpfb.services.humanservice import HumanService
        except ImportError:
            bpy.ops.preferences.addon_enable(module="bl_ext.user_default.mpfb")
            from bl_ext.user_default.mpfb.services.humanservice import HumanService
        from bl_ext.user_default.mpfb.services.locationservice import LocationService
        from bl_ext.user_default.mpfb.services.targetservice import TargetService
        from bl_ext.user_default.mpfb.services.rigservice import RigService
        return HumanService, LocationService, TargetService, RigService

    # the figures: MakeHuman macro settings (0..1 sliders) and system assets (all CC0)
    FIGURES = {
        "Standing actor": dict(macro=dict(gender=1.0, age=0.62, muscle=0.55, weight=0.5, height=0.5, proportions=0.7),
                               race=dict(caucasian=0.85, african=0.1, asian=0.05), skin="middleage_caucasian_male",
                               tan=(0.42, 0.26, 0.15), hair=None, eyes=False),
        "Reclining actor": dict(macro=dict(gender=0.9, age=0.45, muscle=0.42, weight=0.45, height=0.52, proportions=0.75),
                                race=dict(caucasian=0.9, african=0.05, asian=0.05), skin="young_caucasian_male",
                                tan=(0.46, 0.30, 0.18), hair=None, eyes=False),
        "Stagehand A": dict(macro=dict(gender=1.0, age=0.45, muscle=0.7, weight=0.45, height=0.38, proportions=0.5),
                            race=dict(caucasian=0.75, african=0.2, asian=0.05), skin="young_caucasian_male",
                            tan=(0.36, 0.21, 0.12), hair="short02", eyes=True, brows="eyebrow001"),
        "Stagehand B": dict(macro=dict(gender=1.0, age=0.55, muscle=0.62, weight=0.55, height=0.40, proportions=0.45),
                            race=dict(caucasian=0.8, african=0.15, asian=0.05), skin="middleage_caucasian_male",
                            tan=(0.34, 0.20, 0.115), hair="short04", eyes=True, brows="eyebrow006"),
    }

    def tint_skin(body, tan, strength=0.55):
        for m in body.data.materials:
            if not m or not m.node_tree:
                continue
            for nd in m.node_tree.nodes:
                if nd.type == "GROUP":
                    ins = nd.inputs
                    if "colorMixIn" in ins:
                        ins["colorMixIn"].default_value = (*tan, 1.0)
                        ins["colorMixInStrength"].default_value = strength
                    if "Roughness" in ins:
                        ins["Roughness"].default_value = 0.5

    def make_human(name, spec):
        HS, LS, TS, RS = mpfb()
        macro = TS.get_default_macro_info_dict()
        macro.update(spec["macro"])
        macro["race"] = dict(spec["race"])
        body = HS.create_human(macro_detail_dict=macro)
        rig = HS.add_builtin_rig(body, "default")
        ud = LS.get_user_data()
        HS.set_character_skin(os.path.join(ud, "skins", spec["skin"], spec["skin"] + ".mhmat"), body, skin_type="ENHANCED_SSS")
        assets = []
        if spec.get("eyes"):
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyes/high-poly/high-poly.mhclo"), body, asset_type="Eyes",
                                             subdiv_levels=0, material_type="PROCEDURAL_EYES"))
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyebrows", spec["brows"], spec["brows"] + ".mhclo"), body,
                                             asset_type="Eyebrows", subdiv_levels=0, material_type="MAKESKIN"))
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyelashes/eyelashes02/eyelashes02.mhclo"), body,
                                             asset_type="Eyelashes", subdiv_levels=0, material_type="MAKESKIN"))
        if spec.get("hair"):
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "hair", spec["hair"], spec["hair"] + ".mhclo"), body,
                                             asset_type="Hair", subdiv_levels=0, material_type="MAKESKIN"))
        tint_skin(body, spec["tan"])
        body.name = name + " body"
        rig.name = name + " rig"
        rig.data.name = name + " rig"
        for a in assets:
            if a is not None:
                a.name = name + " " + a.name.split(".")[-1]
        # T-pose becomes the rest pose (arms horizontal, palms down): garments are cut for it
        P = Poser(rig)
        for sd, sx in (("L", 1.0), ("R", -1.0)):
            for b in ("upperarm01.", "upperarm02.", "lowerarm01.", "lowerarm02."):
                P.aim(b + sd, (sx, 0.0, -0.04))
            P.aim("wrist." + sd, (sx, 0.0, -0.06), P.palm_normal_rest(sd), (0, 0, -1))
        P.apply()
        bpy.context.view_layer.update()
        RS.apply_pose_as_rest_pose(rig)
        for pb in rig.pose.bones:
            pb.rotation_mode = "QUATERNION"
        return rig, body, [a for a in assets if a is not None]

    # ==========================================================================
    # context from the scene copy: platform, couch, and the mannequins as reference
    # (converted to static, platform-local positions at the frame each figure is seen)
    # ==========================================================================
    def load_context(scene_path):
        names_ctx = list(CONTEXT_OBJECTS)
        with bpy.data.libraries.load(scene_path, link=False) as (src, dst):
            fig = [n for n in src.objects if n.startswith(("Standing actor", "Reclining actor", "Stagehand"))]
            dst.objects = names_ctx + ["Platform ctrl"] + fig
        sc = bpy.context.scene
        ctrl = bpy.data.objects["Platform ctrl"]
        fc = ctrl.animation_data.action.fcurves.find("location", index=1)
        ctrl_y = {fr: fc.evaluate(fr) for _, fr in SHOTS.values()}
        cc = get_coll("Context")
        mc = get_coll("Mannequins (reference)")
        objs = [o for o in bpy.data.objects if o.name in names_ctx or o.name.startswith(("Standing actor", "Reclining actor", "Stagehand"))]
        for o in objs + [ctrl]:
            sc.collection.objects.link(o) if o.name not in sc.collection.all_objects else None
        # evaluate the mannequins at their frames, then freeze them in platform-local coordinates
        fr_sh, fr_tab = SHOTS["cutaway"][1], SHOTS["tableau"][1]
        world = {}
        for fr in (fr_sh, fr_tab):
            sc.frame_set(fr)
            bpy.context.view_layer.update()
            for o in objs:
                if o.name.startswith("Stagehand") == (fr == fr_sh):
                    world[o.name] = (o.matrix_world.copy(), fr)
        for o in objs:
            o.animation_data_clear()
        for o in objs:
            M, fr = world[o.name]
            o.parent = None
            o.matrix_world = Matrix.Translation((0, -ctrl_y[fr], 0)) @ M
            link_to(o, cc if o.name in names_ctx else mc)
            for md in list(o.modifiers):
                if md.type == "BOOLEAN":
                    o.modifiers.remove(md)
        bpy.data.objects.remove(ctrl)
        bpy.context.view_layer.update()
        ref = {o.name: list(o.matrix_world.translation) for o in objs}
        return ctrl_y, ref

    # ==========================================================================
    # poses (platform-local coordinates: +Y toward the audience, platform rig at origin)
    # ==========================================================================
    class Frame:
        """a body frame: origin, left, front, up (world vectors)"""
        def __init__(self, origin, up, front):
            self.o = V(origin)
            R = basis_from(up, front)
            self.R = R
            self.L, self.Fw, self.U = R.col[0].copy(), -R.col[1], R.col[2].copy()

        def p(self, l, f, u):
            return self.o + self.L * l + self.Fw * f + self.U * u

        def d(self, l, f, u):
            return (self.L * l + self.Fw * f + self.U * u).normalized()

    def place_rig(rig, ground, yaw_front):
        """armature object on the ground, rotated so the MakeHuman front (-Y) points along yaw_front"""
        f = V(yaw_front)
        f.z = 0
        f.normalize()
        yaw = math.atan2(f.x, -f.y)
        rig.matrix_world = Matrix.Translation(V(ground)) @ Matrix.Rotation(yaw, 4, "Z")
        bpy.context.view_layer.update()
        for P in list(_POSERS_ALIVE):
            if P.rig == rig:
                P.refresh()

    def hand_shape(P, side, kind):
        if kind == "present":          # open, relaxed, palm up: addressing / presenting
            P.fingers(side, {2: (6, 8, 4), 3: (10, 10, 6), 4: (14, 14, 8), 5: (20, 16, 10)},
                      spread={2: -4, 3: 0, 4: 4, 5: 9}, thumb=((0, 0, -12), 5, 8))
        elif kind == "relaxed":        # hanging, softly curled
            P.fingers(side, {2: (18, 25, 15), 3: (24, 30, 18), 4: (28, 34, 20), 5: (32, 38, 22)},
                      spread={2: -3, 3: 0, 4: 3, 5: 6}, thumb=((10, 0, 0), 12, 15))
        elif kind == "hold":           # holding a fold of cloth
            P.fingers(side, {2: (40, 55, 35), 3: (48, 60, 38), 4: (52, 62, 40), 5: (55, 64, 42)},
                      spread={2: -2, 3: 0, 4: 2, 5: 4}, thumb=((18, 0, 10), 25, 20))
        elif kind == "speak":          # rhetorical gesture: index + middle up, ring and little folded
            P.fingers(side, {2: (2, 4, 2), 3: (6, 8, 4), 4: (60, 75, 45), 5: (65, 80, 45)},
                      spread={2: -5, 3: 2, 4: 4, 5: 6}, thumb=((5, 0, -20), 10, 10))
        elif kind == "push":           # palm flat on the wood, fingers spread
            P.fingers(side, {2: (-4, 6, 4), 3: (-4, 6, 4), 4: (-2, 8, 5), 5: (0, 8, 6)},
                      spread={2: -6, 3: 0, 4: 5, 5: 11}, thumb=((0, 0, -22), 4, 6))
        elif kind == "rest":           # lying on a cushion
            P.fingers(side, {2: (14, 20, 12), 3: (18, 24, 14), 4: (22, 28, 16), 5: (26, 30, 18)},
                      spread={2: -2, 3: 0, 4: 2, 5: 5}, thumb=((6, 0, 0), 10, 10))

    def pose_standing(P, rig):
        """standing actor: weight on the right leg, left foot forward, right arm presenting the
        couch, left forearm raised under the himation; head turned to the reclining figure"""
        face = V((-0.88, -0.30, 0.0)).normalized()
        g = V((2.03, 0.674, 0.0))                     # between the mannequin's feet
        place_rig(rig, g, face)
        B = Frame(g, (0, 0, 1), face)
        P.reset()
        R = Matrix.Rotation(math.radians(-3.0), 3, B.Fw) @ Matrix.Rotation(math.radians(4.0), 3, V((0, 0, 1))) @ rig.matrix_world.to_3x3()
        P.place_root(B.p(-0.025, 0.0, 0.935), R)
        P.spine(["spine05", "spine04", "spine03", "spine02", "spine01"], B.d(-0.03, 0.0, 1), B.d(0.05, 0.05, 1),
                B.d(0.06, 1, 0), B.d(-0.06, 1, 0))
        for n, u, f in (("neck01", B.d(0.04, 0.12, 1), B.d(-0.1, 1, 0)), ("neck02", B.d(0.03, 0.16, 1), B.d(-0.12, 1, 0)),
                        ("neck03", B.d(0.02, 0.15, 1), B.d(-0.14, 1, 0)), ("head", B.d(-0.06, 0.10, 1), B.d(-0.12, 1, -0.12))):
            P.aim(n, u, (0, -1, 0), f)
        # right arm: forward toward the couch, palm up
        P.aim("clavicle.R", B.d(-1, 0.25, 0.12))
        P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
                   B.p(-0.24, 0.40, 1.30), B.d(-0.6, -0.2, -1))
        P.hand("R", B.d(-0.22, 1, 0.12), B.d(0.35, 0.1, 1))
        hand_shape(P, "R", "present")
        # left arm: elbow at the side, forearm forward under the mantle
        P.two_bone(["upperarm01.L", "upperarm02.L"], ["lowerarm01.L", "lowerarm02.L"], "wrist.L",
                   B.p(0.15, 0.25, 1.00), B.d(0.25, -1, -0.4))
        P.hand("L", B.d(-0.15, 1, -0.25), B.d(-0.6, 0.1, 0.7))
        hand_shape(P, "L", "hold")
        # legs
        P.two_bone(["upperleg01.R", "upperleg02.R"], ["lowerleg01.R", "lowerleg02.R"], "foot.R",
                   B.p(-0.105, -0.01, 0.077), B.d(-0.1, 1, 0))
        P.two_bone(["upperleg01.L", "upperleg02.L"], ["lowerleg01.L", "lowerleg02.L"], "foot.L",
                   B.p(0.13, 0.17, 0.083), B.d(0.3, 1, 0))
        P.aim("foot.R", B.d(-0.18, 0.86, -0.5), (0, 0, -1), (0, 0, -1))
        P.aim("foot.L", B.d(0.42, 0.80, -0.45), (0, 0, -1), (0, 0, -1))
        return B

    def pose_reclining(P, rig, t=1.0):
        """reclining on the couch on the left side, propped on the left elbow on the cushions,
        chest to the audience, right hand raised in a speaking gesture; t=0 gives the start of
        the dressing transition (upright T-pose, raised above the couch)"""
        place_rig(rig, (-0.16, -0.24, 0.0), (0, 1, 0))
        P.reset()
        up_p = V((-0.92, 0.0, 0.40))
        fr_p = V((0.10, 0.90, 0.42))
        R = basis_from(up_p, fr_p)
        root = V((-0.17, -0.25, 1.00))
        P.place_root(root, R)
        B = Frame(root, up_p, fr_p)
        C = Frame(root, (-0.45, 0.06, 0.89), (0.30, 0.95, 0.05))         # chest frame
        P.spine(["spine05", "spine04", "spine03", "spine02", "spine01"], up_p, C.U, B.Fw, C.Fw)
        hfront = V((0.55, 0.82, -0.12))
        for n, u in (("neck01", (-0.30, 0.12, 0.95)), ("neck02", (-0.20, 0.14, 0.97)), ("neck03", (-0.12, 0.14, 0.98)),
                     ("head", (-0.12, 0.10, 0.99))):
            P.aim(n, u, (0, -1, 0), hfront)
        # left arm: upper arm down to the elbow on the cushion, forearm forward on it
        P.two_bone(["upperarm01.L", "upperarm02.L"], ["lowerarm01.L", "lowerarm02.L"], "wrist.L",
                   (-0.47, 0.06, 1.035), V((-0.6, -0.5, -0.4)))
        P.hand("L", (0.45, 0.85, -0.30), (0.1, -0.1, -1))
        hand_shape(P, "L", "rest")
        # right arm: raised, speaking
        P.aim("clavicle.R", C.d(-1, 0.2, 0.18))
        P.two_bone(["upperarm01.R", "upperarm02.R"], ["lowerarm01.R", "lowerarm02.R"], "wrist.R",
                   (-0.26, 0.22, 1.36), V((0.2, -0.3, -1)))
        P.hand("R", (0.35, 0.40, 0.85), (0.55, 0.80, 0.1))
        hand_shape(P, "R", "speak")
        # legs: left (lower) leg along the couch, right knee raised
        P.two_bone(["upperleg01.L", "upperleg02.L"], ["lowerleg01.L", "lowerleg02.L"], "foot.L",
                   (0.66, -0.30, 0.92), V((0.0, 1.0, 0.25)))
        P.two_bone(["upperleg01.R", "upperleg02.R"], ["lowerleg01.R", "lowerleg02.R"], "foot.R",
                   (0.54, -0.14, 0.94), V((0.15, 0.4, 1.0)))
        P.aim("foot.L", (0.6, -0.05, -0.80), (0, 0, -1), (0, 1, 0))
        P.aim("foot.R", (0.55, 0.1, -0.83), (0, 0, -1), (0.2, 1, 0))
        return B

    def pose_stagehand(P, rig, x, lead="L", var=0.0):
        """crouched behind the platform's rear rail, staggered feet, hands flat on the rail top,
        pushing; lead = the foot that is forward"""
        g = V((x, REAR - 0.62, 0.0))
        place_rig(rig, g, (0, 1, 0))
        B = Frame(g, (0, 0, 1), (0, 1, 0))
        P.reset()
        s = 1.0 if lead == "L" else -1.0          # +1: left foot forward
        lean = math.radians(52 + 4 * var)
        up = B.d(0.0, math.sin(lean), math.cos(lean))
        fr = B.d(0.0, math.cos(lean), -math.sin(lean))
        root = B.p(0.0, -0.06, 0.50)
        R = Matrix.Rotation(math.radians(-6 * s), 3, B.U) @ basis_from(up, fr)
        P.place_root(root, R)
        up_c = B.d(0.0, math.sin(lean + 0.18), math.cos(lean + 0.18))
        fr_c = B.d(0.0, math.cos(lean + 0.18), -math.sin(lean + 0.18))
        P.spine(["spine05", "spine04", "spine03", "spine02", "spine01"], up, up_c, fr, fr_c)
        for n, u, f in (("neck01", B.d(0, 0.75, 0.66), B.d(0, 0.6, -0.8)), ("neck02", B.d(0, 0.6, 0.8), B.d(0, 0.75, -0.66)),
                        ("neck03", B.d(0, 0.45, 0.9), B.d(0, 0.85, -0.5)), ("head", B.d(0.03 * s, 0.32, 0.95), B.d(0, 0.92, -0.35))):
            P.aim(n, u, (0, -1, 0), f)
        for sd, sx in (("L", 1.0), ("R", -1.0)):
            P.aim("clavicle." + sd, B.d(sx, 0.35, 0.1))
            P.two_bone(["upperarm01." + sd, "upperarm02." + sd], ["lowerarm01." + sd, "lowerarm02." + sd], "wrist." + sd,
                       (x - sx * 0.19, REAR - 0.085, PLAT_H + 0.035), B.d(sx * 0.9, -0.2, 0.1))
            P.hand(sd, B.d(-sx * 0.15, 0.97, -0.05), (0, 0, -1))
            hand_shape(P, sd, "push")
        fwd, back = ("L", "R") if lead == "L" else ("R", "L")
        sf = 1.0 if fwd == "L" else -1.0
        P.two_bone(["upperleg01." + fwd, "upperleg02." + fwd], ["lowerleg01." + fwd, "lowerleg02." + fwd], "foot." + fwd,
                   B.p(sf * 0.17, 0.20, 0.095), B.d(sf * 0.55, 1, 0.3))
        P.two_bone(["upperleg01." + back, "upperleg02." + back], ["lowerleg01." + back, "lowerleg02." + back], "foot." + back,
                   B.p(-sf * 0.11, -0.46, 0.13), B.d(-sf * 0.2, 1, -0.4))
        P.aim("foot." + fwd, B.d(sf * 0.25, 0.85, -0.48), (0, 0, -1), (0, 0, -1))
        P.aim("foot." + back, B.d(-sf * 0.05, 0.25, -0.97), (0, 0, -1), B.d(0, -1, -0.2))
        for t in ("toe1-1.", "toe2-1.", "toe3-1.", "toe4-1.", "toe5-1."):
            P.aim(t + back, B.d(0, 1, -0.05), (0, 0, -1), (0, 0, -1))
        return B

    POSERS = {
        "Standing actor": lambda P, rig: pose_standing(P, rig),
        "Reclining actor": lambda P, rig: pose_reclining(P, rig),
        "Stagehand A": lambda P, rig: pose_stagehand(P, rig, -0.55, "L", 0.0),
        "Stagehand B": lambda P, rig: pose_stagehand(P, rig, 0.55, "R", 1.0),
    }

    # ==========================================================================
    # quick Workbench previews (pose checks)
    # ==========================================================================
    def preview(path, cam_loc, target, lens=50, res=(640, 640), hide_ref=False):
        sc = bpy.context.scene
        cam = bpy.data.objects.get("PreviewCam")
        if cam is None:
            cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
            sc.collection.objects.link(cam)
        cam.location = V(cam_loc)
        cam.rotation_euler = (V(target) - V(cam_loc)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.clip_start = 0.02
        sc.camera = cam
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        sh.show_cavity = True
        sh.show_shadows = True
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.resolution_percentage = 100
        sc.render.film_transparent = False
        sc.render.filepath = path
        hidden = []
        mc = bpy.data.collections.get("Mannequins (reference)")
        if hide_ref and mc:
            for o in mc.objects:
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        bpy.ops.render.render(write_still=True)
        for o in hidden:
            o.hide_render = False

    def mannequin_display():
        mc = bpy.data.collections.get("Mannequins (reference)")
        if not mc:
            return
        m = bpy.data.materials.new("REF mannequin")
        m.diffuse_color = (0.2, 0.5, 1.0, 1.0)
        for o in mc.objects:
            if o.type == "MESH":
                o.data.materials.clear()
                o.data.materials.append(m)

    PREVIEW_VIEWS = {
        "tableau_cam": ((1.0, 5.95, 1.6), (0.45, 0.0, 1.0), 40, (960, 540)),
        "standing_close": ((0.9, 2.6, 1.45), (2.0, 0.65, 1.15), 45, (640, 800)),
        "standing_hands": ((1.3, 1.7, 1.35), (1.75, 0.65, 1.15), 50, (640, 640)),
        "reclining_close": ((0.2, 1.3, 1.5), (-0.35, -0.1, 1.2), 40, (800, 640)),
        "stagehand_close": ((-1.7, -0.3, 1.0), (-0.55, -1.15, 0.45), 40, (800, 640)),
        "standing_front": ((0.6, 0.9, 1.5), (2.0, 0.65, 1.1), 35, (640, 640)),
        "standing_back": ((3.6, 0.0, 1.6), (2.0, 0.65, 1.0), 35, (640, 640)),
        "reclining_front": ((-0.1, 2.0, 1.45), (-0.2, -0.2, 1.05), 35, (800, 600)),
        "reclining_top": ((-0.1, -0.2, 3.2), (-0.1, -0.2, 0.9), 35, (800, 600)),
        "cutaway_cam": ((-5.62, 0.53, 3.46), (0.32, 0.65, 0.8), 30, (960, 540)),
        "stagehands_side": ((-2.6, -1.3, 0.9), (0.0, -1.2, 0.4), 35, (800, 600)),
        "stagehands_back": ((0.0, -3.6, 1.4), (0.0, -1.0, 0.4), 35, (800, 600)),
    }

    def build(opts):
        t0 = time.time()
        work = os.path.abspath(opts["work"])
        os.makedirs(work, exist_ok=True)
        stage = opts.get("stage", "full")
        bpy.ops.wm.read_homefile(use_empty=True)
        sc = bpy.context.scene
        sc.render.fps = FPS
        ctrl_y, ref = load_context(os.path.abspath(opts["scene"]))
        with open(os.path.join(work, "reference.json"), "w") as f:
            json.dump(dict(ctrl_y={str(k): v for k, v in ctrl_y.items()}, mannequin=ref), f, indent=1)
        mannequin_display()
        figs = {}
        only = opts.get("only")
        for name, spec in FIGURES.items():
            if only and name not in only.split(","):
                continue
            rig, body, assets = make_human(name, spec)
            fc = get_coll("MH " + name)
            for o in [rig, body] + assets:
                link_to(o, fc)
            P = Poser(rig)
            POSERS[name](P, rig)
            P.apply()
            print("POSED", name, {b: tuple(round(c, 3) for c in P.head(b)) for b in ("root", "head", "wrist.L", "wrist.R", "foot.L", "foot.R")})
            figs[name] = dict(rig=rig, body=body, assets=assets, poser=P, final=P.snapshot())
            print("FIGURE", name, "%.1fs" % (time.time() - t0))
        bpy.context.view_layer.update()
        if stage == "pose":
            pdir = os.path.join(work, "preview")
            os.makedirs(pdir, exist_ok=True)
            views = opts.get("views")
            for v, (cl, tg, lens, res) in PREVIEW_VIEWS.items():
                if views and v not in views.split(","):
                    continue
                show_ref = v in ("tableau_cam", "cutaway_cam")
                preview(os.path.join(pdir, v + ".png"), cl, tg, lens, res, hide_ref=not show_ref)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "posed.blend"))
            print("POSE PREVIEWS DONE %.1fs" % (time.time() - t0))
            return


# =============================================================================
# entry point
# =============================================================================
if __name__ == "__main__":
    MODE, OPTS = get_args()
    if IN_BLENDER:
        if MODE == "build":
            build(OPTS)
        elif MODE == "render":
            render(OPTS)
