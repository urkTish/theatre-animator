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
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
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
                               tan=(0.42, 0.26, 0.15), hair="long01", eyes=False, hair_col=(0.55, 0.52, 0.5)),
        "Reclining actor": dict(macro=dict(gender=0.9, age=0.45, muscle=0.42, weight=0.45, height=0.52, proportions=0.75),
                                race=dict(caucasian=0.9, african=0.05, asian=0.05), skin="young_caucasian_male",
                                tan=(0.46, 0.30, 0.18), hair="long01", eyes=False, hair_col=(1.0, 0.8, 0.62)),
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


    # ==========================================================================
    # our own shaders on the CC0 MakeHuman textures (MPFB's node groups are not used,
    # so no GPL-covered node data ends up in the scene)
    # ==========================================================================
    def mhmat_texture(mhmat):
        with open(mhmat) as f:
            for line in f:
                if line.startswith("diffuseTexture"):
                    return os.path.join(os.path.dirname(mhmat), line.split(None, 1)[1].strip())
        return None

    def mat_textured(name, tex, tint=(1, 1, 1), tint_fac=0.0, rough=0.5, alpha=False, sss=0.0, spec=0.4, bump=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bs = nt.nodes["Principled BSDF"]
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = bpy.data.images.load(tex, check_existing=True)
        col = it.outputs["Color"]
        if tint_fac > 0:
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs["Factor"].default_value = tint_fac
            mx.inputs[7].default_value = (*tint, 1.0)
            nt.links.new(col, mx.inputs[6])
            col = mx.outputs[2]
        nt.links.new(col, bs.inputs["Base Color"])
        if alpha:
            nt.links.new(it.outputs["Alpha"], bs.inputs["Alpha"])
        bs.inputs["Roughness"].default_value = rough
        bs.inputs["Specular IOR Level"].default_value = spec
        if sss:
            bs.inputs["Subsurface Weight"].default_value = sss
            bs.inputs["Subsurface Radius"].default_value = (1.0, 0.4, 0.22)
            bs.inputs["Subsurface Scale"].default_value = 0.006
            nt.links.new(col, bs.inputs["Base Color"])
        if bump:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 900.0
            nz.inputs["Detail"].default_value = 3.0
            nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            bp.inputs["Distance"].default_value = 0.0005
            nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
            nt.links.new(bp.outputs["Normal"], bs.inputs["Normal"])
        return m

    def set_only_material(ob, m):
        me = ob.data
        me.materials.clear()
        me.materials.append(m)
        for p in me.polygons:
            p.material_index = 0

    def own_materials(name, spec, body, assets, ud):
        skin = mat_textured(name + " skin", mhmat_texture(os.path.join(ud, "skins", spec["skin"], spec["skin"] + ".mhmat")),
                            tint=spec["tan"], tint_fac=0.55, rough=0.48, sss=0.12, spec=0.4, bump=0.08)
        set_only_material(body, skin)
        for a in assets:
            src = a.name.split(".")[-1].lower()
            if "eye" in src and "brow" not in src.lower() and "lash" not in src.lower():
                set_only_material(a, mat_textured(name + " eyes", os.path.join(ud, "eyes/materials/brown_eye.png"), rough=0.12, spec=0.6))
            else:
                folder = next((d for d in ("hair", "eyebrows", "eyelashes") if os.path.exists(os.path.join(ud, d, src, src + ".mhmat"))), None)
                if folder:
                    tex = mhmat_texture(os.path.join(ud, folder, src, src + ".mhmat"))
                    col = spec.get("hair_col", (0.5, 0.42, 0.36))
                    set_only_material(a, mat_textured(name + " " + src, tex, tint=col, tint_fac=1.0, rough=0.42, alpha=True, spec=0.5))

    def make_human(name, spec):
        HS, LS, TS, RS = mpfb()
        macro = TS.get_default_macro_info_dict()
        macro.update(spec["macro"])
        macro["race"] = dict(spec["race"])
        body = HS.create_human(macro_detail_dict=macro)
        rig = HS.add_builtin_rig(body, "default")
        ud = LS.get_user_data()
        assets = []
        if spec.get("eyes"):
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyes/high-poly/high-poly.mhclo"), body, asset_type="Eyes",
                                             subdiv_levels=0, material_type="MAKESKIN"))
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyebrows", spec["brows"], spec["brows"] + ".mhclo"), body,
                                             asset_type="Eyebrows", subdiv_levels=0, material_type="MAKESKIN"))
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "eyelashes/eyelashes02/eyelashes02.mhclo"), body,
                                             asset_type="Eyelashes", subdiv_levels=0, material_type="MAKESKIN"))
        if spec.get("hair"):
            assets.append(HS.add_mhclo_asset(os.path.join(ud, "hair", spec["hair"], spec["hair"] + ".mhclo"), body,
                                             asset_type="Hair", subdiv_levels=0, material_type="MAKESKIN"))
        assets = [a for a in assets if a is not None]
        for a in assets:
            a["mh_source"] = a.name.split(".")[-1].lower()
        own_materials(name, spec, body, assets, ud)
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
            P.fingers(side, {2: (0, 3, 2), 3: (8, 12, 6), 4: (26, 34, 18), 5: (36, 44, 24)},
                      spread={2: -6, 3: 0, 4: 5, 5: 10}, thumb=((0, 0, -18), 6, 8))
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
        g = V((x, REAR - 0.70, 0.0))
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


    # ==========================================================================
    # garments: cut for the T-pose rest (arms horizontal), pinned along the
    # shoulder/arm seam and at the girdle, then simulated from the T-pose into
    # the final pose with the body as a collider, and frozen
    # ==========================================================================
    def body_rest_points(body):
        """rest-pose coordinates of the real body vertices (not the MakeHuman helper geometry)"""
        gi = body.vertex_groups["body"].index
        pts = []
        for v in body.data.vertices:
            for g in v.groups:
                if g.group == gi and g.weight > 0.5:
                    pts.append(v.co.copy())
                    break
        return pts

    def slice_extent(pts, z0, z1, xlim=0.25):
        xs = [p.x for p in pts if z0 <= p.z <= z1 and abs(p.x) < xlim]
        ys = [p.y for p in pts if z0 <= p.z <= z1 and abs(p.x) < xlim]
        return min(xs), max(xs), min(ys), max(ys)

    def store_rest_coords(body):
        at = body.data.attributes.get("rest_co") or body.data.attributes.new("rest_co", "FLOAT_VECTOR", "POINT")
        at.data.foreach_set("vector", [c for v in body.data.vertices for c in v.co])

    def copy_weights(garment, body, pts_idx=None, k=4):
        """nearest-body-vertex weights (inverse-distance blend of k neighbours)"""
        from mathutils.kdtree import KDTree
        gi = body.vertex_groups["body"].index
        bverts = [v for v in body.data.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)]
        kd = KDTree(len(bverts))
        for i, v in enumerate(bverts):
            kd.insert(v.co, i)
        kd.balance()
        bone_names = set(b.name for b in body.parent.data.bones)
        gname = {g.index: g.name for g in body.vertex_groups if g.name in bone_names}
        acc = {}
        for gv in garment.data.vertices:
            res = kd.find_n(gv.co, k)
            tot = 0.0
            w = {}
            for co, i, d in res:
                f = 1.0 / max(d, 1e-4) ** 2
                tot += f
                for g in bverts[i].groups:
                    if g.group in gname:
                        w[gname[g.group]] = w.get(gname[g.group], 0.0) + f * g.weight
            for n, val in w.items():
                acc.setdefault(n, []).append((gv.index, val / tot))
        for n, lst in acc.items():
            vg = garment.vertex_groups.get(n) or garment.vertex_groups.new(name=n)
            for idx, val in lst:
                if val > 0.01:
                    vg.add([idx], val, "REPLACE")

    def make_garment(name, rig, body, mat_name, xw, z_hem, res=0.024, margin=0.055, neck_hw=0.095,
                     waist=True, sleeve_drop=0.0):
        pts = body_rest_points(body)
        rb = {b.name: b for b in rig.data.bones}
        sh_L = rb["upperarm01.L"].head_local
        z_arm_top = max(p.z for p in pts if 0.22 < p.x < 0.30)            # top of the upper arm
        z_top = z_arm_top + 0.018
        y_sh = sh_L.y
        z_armpit = min(p.z for p in pts if 0.17 < p.x < 0.21 and p.z > 1.0 and abs(p.y - y_sh) < 0.05) - 0.02
        z_armpit = max(z_armpit, z_top - 0.17)            # keep the arm opening modest
        x0, x1, ch_f, ch_b = slice_extent(pts, 1.20, 1.42, 0.17)
        _, _, hp_f, hp_b = slice_extent(pts, 0.80, 0.98, 0.20)
        yf = min(ch_f, hp_f) - margin
        yb = max(ch_b, hp_b) + margin
        yc = 0.5 * (yf + yb)
        z_waist = rb["spine04"].head_local.z + 0.01
        wx0, wx1, wy0, wy1 = slice_extent(pts, z_waist - 0.015, z_waist + 0.015, 0.2)
        wa, wb, wyc = (wx1 - wx0) / 2 + 0.012, (wy1 - wy0) / 2 + 0.012, (wy0 + wy1) / 2
        depth = yb - yf
        nf = max(8, int(round(2 * xw / res)))
        ns = max(4, int(round(depth / res)))
        loop = []                                            # (x, y, kind)  kind: F front, S side, B back
        for i in range(nf):
            loop.append((xw - 2 * xw * i / nf, yf, "F"))
        for i in range(ns):
            loop.append((-xw, yf + depth * i / ns, "S"))
        for i in range(nf):
            loop.append((-xw + 2 * xw * i / nf, yb, "B"))
        for i in range(ns):
            loop.append((xw, yb - depth * i / ns, "S"))
        nc = len(loop)
        nr = max(8, int(round((z_top - z_hem) / res)))
        h_yoke = 0.20
        verts, rest, pin, kinds = [], [], [], []
        for r in range(nr + 1):
            z = z_top - (z_top - z_hem) * r / nr
            for (x, y, kd) in loop:
                yy = y
                if z > z_top - h_yoke and kd != "S":
                    prof = 0.5 - 0.5 * math.cos(math.pi * (z - (z_top - h_yoke)) / h_yoke)
                    c = smoothstep(neck_hw, neck_hw + 0.07, abs(x))
                    yy = y + (y_sh - y) * c * prof ** 1.6
                p_rest = V((x, yy, z))
                p = p_rest.copy()
                wpin = 0.0
                if waist and abs(z - z_waist) < 0.13:
                    th = math.atan2(yy - yc, x)
                    ell = V((wa * math.cos(th), wyc + wb * math.sin(th), z))
                    wgt = 1.0 - smoothstep(0.012, 0.13, abs(z - z_waist))
                    p = p_rest.lerp(ell, wgt)
                    if abs(z - z_waist) < 0.013:
                        wpin = 1.0
                if r == 0 and kd != "S" and smoothstep(neck_hw, neck_hw + 0.07, abs(x)) > 0.98:
                    wpin = 1.0
                verts.append(p)
                rest.append(p_rest)
                pin.append(wpin)
                kinds.append(kd)
        faces = []
        for r in range(nr):
            z = z_top - (z_top - z_hem) * (r + 0.5) / nr
            for c in range(nc):
                a, b = r * nc + c, r * nc + (c + 1) % nc
                side = kinds[a] == "S" or kinds[b] == "S"
                if side and z > z_armpit:
                    # open side seam above the armpit (both edges of a side column)
                    if kinds[a] == "S" or (kinds[b] == "S"):
                        continue
                faces.append((a, b, b + nc, a + nc))
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        # rest shape key and pins, then sew the shoulder seam (front/back top rows coincide)
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="rest")
        for i, p in enumerate(rest):
            sk.data[i].co = p
        vg = ob.vertex_groups.new(name="pin")
        for i, w in enumerate(pin):
            if w > 0:
                vg.add([i], w, "REPLACE")
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        top = [bm.verts[i] for i in range(nc) if kinds[i] != "S"]
        bmesh.ops.remove_doubles(bm, verts=top, dist=0.004)
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(me)
        bm.free()
        ob.parent = rig
        ob.matrix_parent_inverse = Matrix.Identity(4)
        me.materials.append(bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name))
        for poly in me.polygons:
            poly.use_smooth = True
        copy_weights(ob, body)
        am = ob.modifiers.new("Armature", "ARMATURE")
        am.object = rig
        info = dict(z_top=z_top, z_waist=z_waist, z_armpit=z_armpit, yf=yf, yb=yb, nverts=len(me.vertices))
        print("GARMENT", name, {k: round(v, 3) if isinstance(v, float) else v for k, v in info.items()})
        return ob, info

    def add_cloth(ob, colliders_coll, frames, pin="pin", mass=0.25, tension=15.0, bend=0.5, shear=5.0,
                  quality=6, self_coll=True, air=1.5, rest_key="rest"):
        md = ob.modifiers.new("Cloth", "CLOTH")
        st = md.settings
        st.quality = quality
        st.mass = mass
        st.tension_stiffness = tension
        st.compression_stiffness = tension
        st.shear_stiffness = shear
        st.bending_stiffness = bend
        st.air_damping = air
        st.tension_damping = 5.0
        st.compression_damping = 5.0
        st.shear_damping = 5.0
        if pin:
            st.vertex_group_mass = pin
            st.pin_stiffness = 1.0
        if rest_key and ob.data.shape_keys and rest_key in ob.data.shape_keys.key_blocks:
            st.rest_shape_key = ob.data.shape_keys.key_blocks[rest_key]
        cs = md.collision_settings
        cs.collision_quality = 3
        cs.distance_min = 0.005
        cs.use_self_collision = self_coll
        cs.self_distance_min = 0.004
        cs.self_friction = 3.0
        cs.collection = colliders_coll
        md.point_cache.frame_start = 1
        md.point_cache.frame_end = frames
        return md

    def make_collider(ob, thick=0.007, friction=5.0):
        if not any(m.type == "COLLISION" for m in ob.modifiers):
            ob.modifiers.new("Collision", "COLLISION")
        ob.collision.thickness_outer = thick
        ob.collision.thickness_inner = 0.02
        ob.collision.cloth_friction = friction
        ob.collision.damping = 0.5

    def freeze(ob, keep_mats=True):
        """replace an object's data by its evaluated mesh (current frame) and drop its modifiers"""
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        mw = ob.matrix_world.copy()
        old = ob.data
        ob.modifiers.clear()
        if ob.data.shape_keys:
            ob.shape_key_clear()
        ob.data = me
        if keep_mats:
            me.materials.clear()
            for m in old.materials:
                me.materials.append(m)
        ob.parent = None
        ob.matrix_world = mw
        ob.vertex_groups.clear()
        return ob


    GARMENTS = {
        # figure: (garment name, material, half-width (sleeve reach) m, hem height m, cloth params)
        "Standing actor": ("chiton", "Chiton undyed wool", 0.44, 0.035, dict(mass=0.22, bend=0.35, tension=14.0)),
        "Reclining actor": ("chiton", "Chiton saffron", 0.30, 0.05, dict(mass=0.22, bend=0.35, tension=14.0)),
        "Stagehand A": ("tunic", "Stagehand tunic (dark wool)", 0.25, 0.50, dict(mass=0.3, bend=1.5, tension=18.0)),
        "Stagehand B": ("tunic", "Stagehand tunic (dark wool)", 0.25, 0.49, dict(mass=0.3, bend=1.5, tension=18.0)),
    }
    T_SETTLE, T_MOVE, T_END = 12, 52, 76          # cloth timeline (frames)

    def transition_keys(name, fig):
        """keyframe the rig: rest (T-pose) -> final pose; the reclining figure starts upright
        above the couch and lies down late, so the cloth never meets the couch from inside"""
        rig, P, final = fig["rig"], fig["poser"], fig["final"]
        start = {n: Matrix.Identity(4) for n in final}
        seq = [(1, start), (T_SETTLE, start)]
        if name == "Reclining actor":
            to_root = P.rest["root"].to_3x3().normalized().inverted() @ P.inv_w.to_3x3().normalized()
            lift = Matrix.Translation(to_root @ V((0, 0, 1.15)))
            start = {n: Matrix.Identity(4) for n in final}
            start["root"] = lift
            seq = [(1, start), (T_SETTLE, start)]
            mid = {}
            for n, m in final.items():
                loc, q, _ = m.decompose()
                mid[n] = Matrix.Translation(loc * 0.85) @ Quaternion().slerp(q, 0.85).to_matrix().to_4x4()
            # root: rotated 85 %, still lifted 0.35 m above its final place
            loc, q, _ = final["root"].decompose()
            lift2 = to_root @ V((0, 0, 0.35))
            mid["root"] = Matrix.Translation(loc * 0.85 + lift2) @ Quaternion().slerp(q, 0.85).to_matrix().to_4x4()
            seq += [(T_MOVE - 10, mid), (T_MOVE, final), (T_END, final)]
        else:
            seq += [(T_MOVE, final), (T_END, final)]
        key_pose_sequence(rig, seq)

    def simulate_garments(figs, ctx_colliders):
        sc = bpy.context.scene
        sc.frame_start, sc.frame_end = 1, T_END
        cloths = []
        for name, fig in figs.items():
            gname, mat, xw, hem, prm = GARMENTS[name]
            rig, body = fig["rig"], fig["body"]
            P = fig["poser"]
            # jaw open for the masked actors (the mask is moulded on the open mouth)
            if name in ("Standing actor", "Reclining actor"):
                fig["final"]["jaw"] = Matrix.Rotation(math.radians(14), 4, "X")
            # garments are cut in rest (T-pose): show the rest pose while building them
            rig.data.pose_position = "REST"
            bpy.context.view_layer.update()
            store_rest_coords(body)
            g, info = make_garment(f"{name} {gname}", rig, body, mat, xw, hem,
                                   neck_hw=0.07 if gname == "tunic" else 0.075, margin=0.04 if gname == "tunic" else 0.055)
            fig["garment"], fig["ginfo"] = g, info
            rig.data.pose_position = "POSE"
            transition_keys(name, fig)
            cc = get_coll(f"COL {name}")
            cc.hide_render = True
            make_collider(body, thick=0.006)
            if body.name not in cc.objects:
                cc.objects.link(body)
            for o in ctx_colliders.get(name, []):
                make_collider(o, thick=0.006)
                if o.name not in cc.objects:
                    cc.objects.link(o)
            add_cloth(g, cc, T_END, **prm)
            cloths.append(g)
        t0 = time.time()
        for f in range(1, T_END + 1):
            sc.frame_set(f)
            if f % 10 == 0:
                print("  cloth frame", f, "%.1fs" % (time.time() - t0))
        print("CLOTH SIM %.1fs" % (time.time() - t0))
        return cloths


    # ==========================================================================
    # tragic masks: moulded on the posed MakeHuman face (mouth open), enlarged and
    # idealised, with eye and mouth openings, painted features, a dark lining, and
    # an attached wig (MakeHuman CC0 hair, enlarged with the mask)
    # ==========================================================================
    def mat_simple(name, color, rough=0.6, spec=0.3, bump=0.0, bump_scale=60.0, attr=None):
        m = bpy.data.materials.get(name)
        if m:
            return m
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bs = nt.nodes["Principled BSDF"]
        bs.inputs["Base Color"].default_value = (*color, 1)
        bs.inputs["Roughness"].default_value = rough
        bs.inputs["Specular IOR Level"].default_value = spec
        if attr:
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_name = attr
            nt.links.new(at.outputs["Color"], bs.inputs["Base Color"])
        if bump:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = bump_scale
            nz.inputs["Detail"].default_value = 6.0
            nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            bp.inputs["Distance"].default_value = 0.001
            nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
            nt.links.new(bp.outputs["Normal"], bs.inputs["Normal"])
        return m

    def head_refs(rig):
        rb = rig.data.bones
        eL, eR = rb["eye.L"].head_local, rb["eye.R"].head_local
        return dict(eL=eL.copy(), eR=eR.copy(), ez=0.5 * (eL.z + eR.z), ey=0.5 * (eL.y + eR.y),
                    hz=rb["head"].head_local.z)

    def build_mask(name, fig, paint, hair_col, scale=1.16, beard=False, trim_wig=False):
        """fig['body'] must already be frozen in the final pose (it carries 'rest_co')"""
        body, rig, P = fig["body"], fig["rig"], fig["poser"]
        H = head_refs(rig)
        ez, ey, ex = H["ez"], H["ey"], abs(H["eL"].x)
        mz = ez - 0.068                     # mouth line (rest)
        me = body.data
        rest = [V(d.vector) for d in me.attributes["rest_co"].data]
        # posed head frame: centre of scaling
        Mh = rig.matrix_world @ P.P("head")
        hc = Mh @ V((0.0, 0.02, 0.0))       # a little up the head bone from its head
        hc = Mh.translation + (Mh.to_3x3().normalized() @ V((0, 1, 0))) * 0.045

        def in_face(p):
            return (p.x / 0.088) ** 2 + ((p.z - (ez - 0.008)) / 0.132) ** 2 < 1.0 and p.y < ey + 0.075

        def eye_hole(p):
            return any(((p.x - sx * ex) / 0.0165) ** 2 + ((p.z - ez) / 0.0105) ** 2 < 1.0 for sx in (1, -1)) or \
                (any(((p.x - sx * ex) / 0.021) ** 2 + ((p.z - ez) / 0.014) ** 2 < 1.0 for sx in (1, -1)) and p.y > ey + 0.004)

        def mouth_hole(p):
            return ((p.x / 0.024) ** 2 + ((p.z - mz) / 0.013) ** 2 < 1.0) or \
                (abs(p.x) < 0.03 and mz - 0.035 < p.z < mz + 0.02 and p.y > ey + 0.012)

        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(body.matrix_world)
        bm.verts.ensure_lookup_table()
        keep = set()
        for f in bm.faces:
            if all(in_face(rest[v.index]) for v in f.verts):
                keep.add(f.index)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        # keep the largest connected piece only
        bm.faces.ensure_lookup_table()
        rest_l = bm.verts.layers.float_vector.get("rest_co")
        def rco(v):
            return V(v[rest_l]) if rest_l else rest[v.index]
        # enlarge about the head centre, push out a little, smooth (idealise)
        for v in bm.verts:
            v.co = hc + (v.co - hc) * scale
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * 0.004
        for _ in range(4):
            bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                                  use_axis_x=True, use_axis_y=True, use_axis_z=True)
        # lining (no openings) slightly inside: seen through the eye and mouth holes as darkness
        lining = bm.copy()
        for v in lining.verts:
            v.co = hc + (v.co - hc) * 0.955
        # openings
        holes = [f for f in bm.faces if any(eye_hole(rco(v)) or mouth_hole(rco(v)) for v in f.verts)]
        bmesh.ops.delete(bm, geom=holes, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        # painted features as a colour attribute
        base = V(paint)
        col_l = bm.verts.layers.float_color.new("paint")
        for v in bm.verts:
            p = rco(v)
            c = base.copy()
            dx = min(abs(p.x - ex), abs(p.x + ex))
            # cheeks: faint warm flush
            ck = math.exp(-((dx - 0.012) / 0.02) ** 2 - ((p.z - (ez - 0.035)) / 0.018) ** 2)
            c = c.lerp(V((0.66, 0.36, 0.28)), 0.35 * ck)
            # brows: dark arcs
            bz = ez + 0.031 - 0.25 * (abs(p.x) - ex) ** 2 / 0.02
            br = math.exp(-((p.z - bz) / 0.0085) ** 2) * (1.0 - smoothstep(0.028, 0.044, dx)) * (1 if abs(p.x) > 0.008 else 0)
            c = c.lerp(V((0.05, 0.035, 0.025)), min(1.0, 1.7 * br))
            # dark rims round the eye holes
            er = math.exp(-(((dx) / 0.030) ** 2 + ((p.z - ez) / 0.020) ** 2) * 1.2)
            c = c.lerp(V((0.10, 0.07, 0.05)), 0.85 * er)
            # red-ochre lips round the open mouth
            lp = math.exp(-((p.x / 0.045) ** 2 + ((p.z - mz) / 0.030) ** 2) * 1.0)
            c = c.lerp(V((0.45, 0.12, 0.08)), min(1.0, 1.3 * lp))
            v[col_l] = (*c, 1.0)
        mm = bpy.data.meshes.new(name + " mask")
        bm.to_mesh(mm)
        bm.free()
        mask = bpy.data.objects.new(name + " mask", mm)
        mm.materials.append(mat_simple("MH mask paint (gesso)", paint, rough=0.55, spec=0.35, bump=0.15, bump_scale=90.0, attr="paint"))
        for poly in mm.polygons:
            poly.use_smooth = True
        sd = mask.modifiers.new("Solidify", "SOLIDIFY")
        sd.thickness = 0.005
        sd.offset = -1.0
        sd.use_rim = True
        ss = mask.modifiers.new("Subsurf", "SUBSURF")
        ss.levels, ss.render_levels = 1, 2
        ml = bpy.data.meshes.new(name + " mask lining")
        lining.to_mesh(ml)
        lining.free()
        lin = bpy.data.objects.new(name + " mask lining", ml)
        ml.materials.append(mat_simple("MH mask lining (dark)", (0.006, 0.005, 0.004), rough=0.95, spec=0.05))
        out = [mask, lin]
        # wig: the MakeHuman hair, frozen in the pose and enlarged with the mask
        for a in fig["assets"]:
            if a.name.endswith(("long01", "bob01", "bob02", "short01", "short02", "short03", "short04", "ponytail01", "braid01", "afro01")):
                for v in a.data.vertices:
                    w = a.matrix_world @ v.co
                    v.co = a.matrix_world.inverted() @ (hc + (w - hc) * (scale + 0.02))
                if trim_wig:
                    # trim the long hair to the shoulders (a mature man's tragic wig)
                    zcut = (rig.matrix_world @ P.P("neck01")).translation.z - 0.06
                    bmw = bmesh.new()
                    bmw.from_mesh(a.data)
                    mwa = a.matrix_world
                    bmesh.ops.delete(bmw, geom=[v for v in bmw.verts if (mwa @ v.co).z < zcut], context="VERTS")
                    bmw.to_mesh(a.data)
                    bmw.free()
                a.name = name + " wig"
        if beard:
            out.append(build_beard(name, mask, H, hair_col))
        return out

    def tint_hair(ob, col):
        for m in ob.data.materials:
            if not m or not m.node_tree:
                continue
            nt = m.node_tree
            bs = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not bs:
                continue
            lk = bs.inputs["Base Color"].links
            if lk:
                src = lk[0].from_socket
                mx = nt.nodes.new("ShaderNodeMix")
                mx.data_type = "RGBA"
                mx.blend_type = "MULTIPLY"
                mx.inputs["Factor"].default_value = 1.0
                mx.inputs[7].default_value = (*col, 1.0)
                nt.links.new(src, mx.inputs[6])
                nt.links.new(mx.outputs[2], bs.inputs["Base Color"])
            else:
                bs.inputs["Base Color"].default_value = (*col, 1.0)
            bs.inputs["Roughness"].default_value = 0.6

    def build_beard(name, mask, H, col, n=2600, seed=7):
        """a full wig-maker's beard and moustache attached to the lower mask: hair curves rooted on
        the mask's jaw, chin and upper lip, falling down and a little forward, with curl"""
        import random as _r
        rr = _r.Random(seed)
        me = mask.data
        mw = mask.matrix_world
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(mw)
        bm.normal_update()
        zs = [v.co.z for v in bm.verts]
        z0, z1 = min(zs), max(zs)
        zc = z0 + 0.40 * (z1 - z0)
        tris = []
        for f in bm.faces:
            c = f.calc_center_median()
            if c.z < zc:
                tris.append((f, f.calc_area()))
        tot = sum(a for _, a in tris)
        down = V((0, 0, -1))
        curves = bpy.data.hair_curves.new(name + " beard")
        K = 6
        curves.add_curves([K] * n)
        pos, rad = [], []
        for i in range(n):
            x = rr.random() * tot
            for f, a in tris:
                x -= a
                if x <= 0:
                    break
            vs = [v.co for v in f.verts]
            u, w = rr.random(), rr.random()
            if u + w > 1:
                u, w = 1 - u, 1 - w
            root = vs[0] + (vs[1] - vs[0]) * u + (vs[-1] - vs[0]) * w
            nrm = f.normal.copy()
            L = 0.045 + 0.035 * rr.random() * (1.0 - (root.z - z0) / max(1e-6, zc - z0)) + 0.01
            d = (nrm * 0.55 + down * 1.0).normalized()
            p = root.copy()
            ph = rr.random() * 6.28
            for k in range(K):
                t = k / (K - 1)
                curl = V((math.cos(ph + t * 9), math.sin(ph + t * 9), 0)) * 0.004 * t
                pos.append(p + curl)
                rad.append(0.0007 * (1.0 - 0.7 * t))
                dd = (d + down * 0.35 * t).normalized()
                p = p + dd * (L / (K - 1))
        curves.attributes["position"].data.foreach_set("vector", [c for v in pos for c in v])
        ra = curves.attributes.get("radius") or curves.attributes.new("radius", "FLOAT", "POINT")
        ra.data.foreach_set("value", rad)
        bm.free()
        ob = bpy.data.objects.new(name + " beard", curves)
        curves.materials.append(mat_hair_bsdf(name + " beard hair", col))
        return ob

    def mat_hair_bsdf(name, col):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
        hb.parametrization = "COLOR"
        hb.inputs["Color"].default_value = (*col, 1.0)
        hb.inputs["Roughness"].default_value = 0.35
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(hb.outputs[0], out.inputs["Surface"])
        return m

    # ==========================================================================
    # soft boots for the standing actor: a leather shell over the posed feet and ankles
    # ==========================================================================
    def build_boots(name, body):
        me = body.data
        rest = [V(d.vector) for d in me.attributes["rest_co"].data]
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(body.matrix_world)
        dele = [f for f in bm.faces if not all(rest[v.index].z < 0.20 for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * 0.0035
        mb = bpy.data.meshes.new(name + " boots")
        bm.to_mesh(mb)
        bm.free()
        ob = bpy.data.objects.new(name + " boots", mb)
        mb.materials.append(bpy.data.materials.get("Soft leather boots") or mat_simple("Soft leather boots", (0.09, 0.06, 0.045), rough=0.6, bump=0.2, bump_scale=80))
        for poly in mb.polygons:
            poly.use_smooth = True
        sd = ob.modifiers.new("Solidify", "SOLIDIFY")
        sd.thickness = 0.002
        ss = ob.modifiers.new("Subsurf", "SUBSURF")
        ss.levels, ss.render_levels = 1, 1
        return ob


    # ==========================================================================
    # second cloth pass on the frozen figures: the standing actor's himation (wrapped
    # over the left shoulder, across the back, round the right hip, held in the left
    # hand) and the blanket over the reclining figure
    # ==========================================================================
    def bvh_of(objs):
        from mathutils.bvhtree import BVHTree
        verts, polys = [], []
        dg = bpy.context.evaluated_depsgraph_get()
        for o in objs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            off = len(verts)
            mw = o.matrix_world
            verts += [mw @ v.co for v in me.vertices]
            polys += [[off + i for i in p.vertices] for p in me.polygons]
            ev.to_mesh_clear()
        return BVHTree.FromPolygons(verts, polys)

    def catmull(pts, t):
        n = len(pts) - 1
        x = max(0.0, min(n - 1e-6, t * n))
        i = int(x)
        u = x - i
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n)]
        return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)

    HIMATION = [
        # (mode, a, b, width dir (l, f, u), half-width). side: a = angle from the front toward
        # the left (deg), b = height; top: a, b = (left, front) over the shoulder, cast down.
        # A mantle over the left shoulder and upper arm: the front part falls over the raised
        # left forearm, the back part hangs down the back to the calves.
        ("side", 34, 0.50, (1, 0.15, 0), 0.31),
        ("side", 40, 1.05, (1, 0.15, 0), 0.31),
        ("side", 46, 1.38, (1, 0.1, 0), 0.25),
        ("top", 0.20, 0.05, (1, 0, -0.25), 0.20),
        ("top", 0.20, -0.07, (1, 0, -0.25), 0.20),
        ("side", 150, 1.35, (1, 0, 0), 0.31),
        ("side", 162, 0.98, (1, 0, -0.1), 0.35),
        ("side", 170, 0.45, (1, 0, -0.1), 0.38),
    ]

    def build_himation(name, fig, colliders, W=0.70, res=0.022):
        B = fig["frame"]
        P = fig["poser"]
        bvh = bvh_of(colliders)
        axis_o = P.head("root")
        cs, ws, hws = [], [], []
        for mode, a, b, w, hw in HIMATION:
            if mode == "side":
                phi = math.radians(a)
                d = (B.Fw * math.cos(phi) + B.L * math.sin(phi)).normalized()
                o = V((axis_o.x, axis_o.y, b)) + d * 1.2
                hit = bvh.ray_cast(o, -d, 2.0)
                p = hit[0] if hit[0] is not None else V((axis_o.x, axis_o.y, b)) + d * 0.25
                c = p + d * 0.03
            elif mode == "top":
                o = B.p(a, b, 2.2)
                o = V((o.x, o.y, 2.2))
                hit = bvh.ray_cast(o, V((0, 0, -1)), 2.0)
                c = (hit[0] if hit[0] is not None else B.p(a, b, 1.5)) + V((0, 0, 0.025))
            else:
                c = P.head("wrist.L") + B.U * 0.06 + B.Fw * 0.01
            cs.append(c)
            ws.append(B.d(*w))
            hws.append(hw)
        # resample along the path by arc length
        dense = [catmull(cs, i / 400.0) for i in range(401)]
        L = [0.0]
        for i in range(1, len(dense)):
            L.append(L[-1] + (dense[i] - dense[i - 1]).length)
        total = L[-1]
        nrows = int(total / res)
        nw = int(W / res) + 1
        verts, rest_co, pinw = [], [], []
        k = 0
        for r in range(nrows + 1):
            s = total * r / nrows
            while k < len(L) - 2 and L[k + 1] < s:
                k += 1
            t = (k + (s - L[k]) / max(1e-9, L[k + 1] - L[k])) / 400.0
            c = catmull(cs, t)
            c2 = catmull(cs, min(1.0, t + 0.002))
            c1 = catmull(cs, max(0.0, t - 0.002))
            tan = (c2 - c1).normalized()
            x = t * (len(cs) - 1)
            i0 = min(int(x), len(cs) - 2)
            u = x - i0
            w = ws[i0].lerp(ws[i0 + 1], u)
            w = (w - tan * w.dot(tan)).normalized()
            hw = hws[i0] + (hws[i0 + 1] - hws[i0]) * u
            nrm = tan.cross(w).normalized()
            radial = c - V((axis_o.x, axis_o.y, c.z))
            if nrm.dot(radial) < 0 and c.z < 1.45:
                nrm = -nrm
            elif c.z >= 1.45 and nrm.z < 0:
                nrm = -nrm
            amp = 0.0
            for j in range(nw):
                tt = -1.0 + 2.0 * j / (nw - 1)
                zig = (0.5 * amp) * (1 if j % 2 else -1) if amp > 0.002 else 0.0
                verts.append(c + w * (tt * hw) + nrm * (zig + 0.5 * amp))
                rest_co.append(V((tt * hw, s, 0.0)))
                pin = 0.0
                if abs(t - 3.5 / (len(cs) - 1)) < 0.4 / (len(cs) - 1) and abs(tt) < 0.3:
                    pin = 1.0                      # on top of the shoulder
                pinw.append(pin)
        faces = [(r * nw + j, r * nw + j + 1, (r + 1) * nw + j + 1, (r + 1) * nw + j) for r in range(nrows) for j in range(nw - 1)]
        me = bpy.data.meshes.new(name + " himation")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ob = bpy.data.objects.new(name + " himation", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="rest")
        for i, p in enumerate(rest_co):
            sk.data[i].co = p
        vg = ob.vertex_groups.new(name="pin")
        for i, wgt in enumerate(pinw):
            if wgt > 0:
                vg.add([i], wgt, "REPLACE")
        for poly in me.polygons:
            poly.use_smooth = True
        me.materials.append(bpy.data.materials.get("Himation woad") or bpy.data.materials.new("Himation woad"))
        print("HIMATION rows %d x %d, path %.2f m" % (nrows + 1, nw, total))
        return ob

    def build_blanket(name, fig, colliders):
        bvh = bvh_of(colliders[:2])
        ztop = Z_MATT
        for x in [i * 0.05 - 0.2 for i in range(20)]:
            for y in [j * 0.05 - 0.6 for j in range(16)]:
                hit = bvh.ray_cast(V((x, y, 2.5)), V((0, 0, -1)), 3.0)
                if hit[0] is not None:
                    ztop = max(ztop, hit[0].z)
        nx, ny = 52, 70
        w, h = 1.30, 1.75
        verts = []
        rot = Matrix.Rotation(math.radians(6), 3, "Z")
        for j in range(ny + 1):
            for i in range(nx + 1):
                x, y = -w / 2 + w * i / nx, -h / 2 + h * j / ny
                p = rot @ V((x, y, 0.0)) + V((0.42, -0.08, ztop + 0.04 + 0.015 * math.sin(x * 9) * math.cos(y * 7)))
                verts.append(p)
        faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i) for j in range(ny) for i in range(nx)]
        me = bpy.data.meshes.new(name + " blanket")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ob = bpy.data.objects.new(name + " blanket", me)
        bpy.context.scene.collection.objects.link(ob)
        for poly in me.polygons:
            poly.use_smooth = True
        me.materials.append(bpy.data.materials.get("Himation madder") or bpy.data.materials.new("Himation madder"))
        return ob


    # ==========================================================================
    # render stage (runs inside the scene copy)
    # ==========================================================================
    MANNEQUIN_PREFIXES = ("Standing actor", "Reclining actor", "Stagehand A", "Stagehand B")

    def mannequin_objects():
        figc = bpy.data.collections.get("Figures")
        objs = list(figc.all_objects) if figc else []
        return [o for o in objs if o.name.startswith(MANNEQUIN_PREFIXES)]

    def append_figures(path):
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.collections = [c for c in src.collections if c == "MH figures" or c.endswith("(frozen)")]
        top = bpy.data.collections["MH figures"]
        bpy.context.scene.collection.children.link(top)
        # use the scene's own dye and leather materials (same colours as the mannequins wear)
        for c in top.children:
            for o in c.objects:
                if o.type != "MESH":
                    continue
                for slot in o.material_slots:
                    m = slot.material
                    if m is None:
                        continue
                    base = m.name.split(".")[0] if m.name[-4:-3] == "." else m.name
                    sm = bpy.data.materials.get(base)
                    if sm is not None and sm != m and sm.users > 0 and base in (
                            "Chiton undyed wool", "Chiton saffron", "Himation woad", "Himation madder",
                            "Stagehand tunic (dark wool)", "Soft leather boots"):
                        slot.material = sm
        return top

    def place_figures(top, ctrl_y):
        ctrl = bpy.data.objects["Platform ctrl"]
        groups = {}
        for c in top.children:
            name = c.name.replace("MH ", "").replace(" (frozen)", "")
            groups[name] = list(c.objects)
            for o in c.objects:
                mb = o.matrix_basis.copy()         # (unparented: basis = world, platform-local)
                if name == "Reclining actor":
                    o.parent = ctrl
                    o.matrix_parent_inverse = Matrix.Identity(4)
                    o.matrix_basis = mb            # platform-local = local to the platform rig
                elif name == "Standing actor":
                    o.matrix_basis = Matrix.Translation((0, ctrl_y[SHOTS["tableau"][1]], 0)) @ mb
                else:
                    o.matrix_basis = Matrix.Translation((0, ctrl_y[SHOTS["cutaway"][1]], 0)) @ mb
        return groups

    def render(opts):
        work = os.path.abspath(opts["work"])
        outdir = os.path.join(work, opts.get("outname", "renders"))
        os.makedirs(outdir, exist_ok=True)
        spp = int(opts.get("samples", 64))
        only = opts.get("only", "AB")
        sc = bpy.context.scene
        r = sc.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = 1280, 720, 100
        r.use_overwrite, r.use_placeholder = True, False
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGB"
        r.use_border = False
        sc.cycles.samples = spp
        sc.cycles.use_denoising = True
        for m in sc.timeline_markers:
            m.camera = None
        ctrl = bpy.data.objects["Platform ctrl"]
        fc = ctrl.animation_data.action.fcurves.find("location", index=1)
        ctrl_y = {fr: fc.evaluate(fr) for _, fr in SHOTS.values()}
        timing = []

        def shot(tag, label, crop=None, scale=1):
            cam, fr = SHOTS[tag]
            sc.camera = bpy.data.objects[cam]
            sc.frame_set(fr)
            r.resolution_x, r.resolution_y = 1280 * scale, 720 * scale
            if crop:
                r.use_border, r.use_crop_to_border = True, True
                r.border_min_x, r.border_max_x, r.border_min_y, r.border_max_y = crop
            else:
                r.use_border = False
            path = os.path.join(outdir, "%s_%s.png" % (label, tag if not crop else tag + "_crop"))
            r.filepath = path
            t = time.time()
            bpy.ops.render.render(write_still=True)
            dt = time.time() - t
            timing.append(dict(shot=tag, version=label, seconds=round(dt, 1), samples=sc.cycles.samples,
                               res="%dx%d" % (r.resolution_x, r.resolution_y), crop=bool(crop)))
            print("RENDER %s %s %.1fs" % (label, tag, dt))
            with open(os.path.join(outdir, "timing_%s.json" % only), "w") as f:
                json.dump(timing, f, indent=1)

        # warm-up: kernels, images, BVH (not timed in the table)
        sc.cycles.samples = 1
        r.resolution_percentage = 10
        sc.camera = bpy.data.objects[SHOTS["tableau"][0]]
        sc.frame_set(SHOTS["tableau"][1])
        r.filepath = os.path.join(outdir, "warmup.png")
        bpy.ops.render.render(write_still=True)
        r.resolution_percentage = 100
        sc.cycles.samples = spp
        crop = None
        if "A" in only:
            for tag in ("tableau", "cutaway"):
                shot(tag, "A")
        if "B" in only or "C" in only:
            top = append_figures(os.path.join(work, "figures.blend"))
            groups = place_figures(top, ctrl_y)
            for o in mannequin_objects():
                o.hide_render = True
            bpy.context.view_layer.update()
            # crop window round the reclining figure's mask in the tableau camera
            from bpy_extras.object_utils import world_to_camera_view
            sc.frame_set(SHOTS["tableau"][1])
            cam = bpy.data.objects[SHOTS["tableau"][0]]
            mask = next(o for o in groups["Reclining actor"] if "mask" in o.name and "mask lining" not in o.name)
            pc = world_to_camera_view(sc, cam, mask.matrix_world @ (sum((V(b) for b in mask.bound_box), Vector()) / 8))
            cw, ch = 0.26, 0.46
            crop = (max(0, pc.x - cw * 0.55), min(1, pc.x + cw * 0.45), max(0, pc.y - ch * 0.62), min(1, pc.y + ch * 0.38))
            with open(os.path.join(outdir, "crop.json"), "w") as f:
                json.dump(crop, f)
            for tag in ("tableau", "cutaway"):
                for o in groups.get("Stagehand A", []) + groups.get("Stagehand B", []):
                    # at the tableau frame the mannequin stagehands are hidden behind the facade wall
                    o.hide_render = (tag == "tableau")
                if "B" in only:
                    shot(tag, "B")
            for o in groups.get("Stagehand A", []) + groups.get("Stagehand B", []):
                o.hide_render = True
            if "C" in only:
                shot("tableau", "B", crop=crop, scale=3)
                for o in mannequin_objects():
                    o.hide_render = False
                for c in top.children:
                    c.hide_render = True
                shot("tableau", "A", crop=crop, scale=3)
        print("RENDER STAGE DONE")

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
        "standing_backleft": ((1.3, 2.6, 1.5), (2.0, 0.7, 1.05), 40, (640, 800)),
        "masks_close": ((1.0, 1.3, 1.62), (1.95, 0.64, 1.62), 60, (640, 640)),
        "reclining_mask": ((-0.15, 0.8, 1.55), (-0.52, -0.12, 1.5), 55, (640, 640)),
        "stagehands_side": ((-2.6, -1.3, 0.9), (0.0, -1.2, 0.4), 35, (800, 600)),
        "stagehands_back": ((0.0, -3.6, 1.4), (0.0, -1.0, 0.4), 35, (800, 600)),
    }

    def build(opts):
        t0 = time.time()
        work = os.path.abspath(opts["work"])
        os.makedirs(work, exist_ok=True)
        stage = opts.get("stage", "full")
        if opts.get("resume") == "cloth":
            return resume_from_cloth(work, t0)
        if stage == "figpreview":
            # look at the finished figures.blend with the platform and couch for context
            bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "figures.blend"))
            with bpy.data.libraries.load(os.path.abspath(opts["scene"]), link=False) as (src, dst):
                dst.objects = list(CONTEXT_OBJECTS)
            for o in dst.objects:
                bpy.context.scene.collection.objects.link(o)
                mb = o.matrix_basis.copy()
                o.parent = None
                o.matrix_world = mb
            pdir = os.path.join(work, "preview")
            os.makedirs(pdir, exist_ok=True)
            for v, (cl, tg, lens, res) in PREVIEW_VIEWS.items():
                if opts.get("views") and v not in opts["views"].split(","):
                    continue
                preview(os.path.join(pdir, "fig_" + v + ".png"), cl, tg, lens, res)
            return
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
            frame = POSERS[name](P, rig)
            P.apply()
            print("POSED", name, {b: tuple(round(c, 3) for c in P.head(b)) for b in ("root", "head", "wrist.L", "wrist.R", "foot.L", "foot.R")})
            figs[name] = dict(rig=rig, body=body, assets=assets, poser=P, final=P.snapshot(), frame=frame)
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
        # ---- cloth: chiton / tunics ------------------------------------------------
        gp = bpy.data.meshes.new("Ground (collider)")
        gp.from_pydata([(-8, -8, 0), (8, -8, 0), (8, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
        ground = bpy.data.objects.new("Ground (collider)", gp)
        get_coll("Context").objects.link(ground)
        ground.hide_render = True
        couch = [bpy.data.objects[n] for n in ("Mattress", "Cushion 0", "Cushion 1", "Couch (kline)")]
        ctx_col = {"Standing actor": [ground], "Reclining actor": couch,
                   "Stagehand A": [ground], "Stagehand B": [ground]}
        simulate_garments(figs, ctx_col)
        sc.frame_set(T_END)
        for fig in figs.values():
            freeze(fig["garment"])
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "cloth.blend"))
        if stage == "cloth":
            pdir = os.path.join(work, "preview")
            os.makedirs(pdir, exist_ok=True)
            for v, (cl, tg, lens, res) in PREVIEW_VIEWS.items():
                if opts.get("views") and v not in opts["views"].split(","):
                    continue
                preview(os.path.join(pdir, "cloth_" + v + ".png"), cl, tg, lens, res, hide_ref=True)
            print("CLOTH STAGE DONE %.1fs" % (time.time() - t0))
            return
        finish_build(figs, work, couch, t0)

    def resume_from_cloth(work, t0):
        """continue from DIR/cloth.blend (garments simulated and frozen, bodies still rigged)"""
        bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "cloth.blend"))
        figs = {}
        for name in FIGURES:
            rig = bpy.data.objects.get(name + " rig")
            if rig is None:
                continue
            gname = GARMENTS[name][0]
            body = bpy.data.objects[name + " body"]
            garment = bpy.data.objects[f"{name} {gname}"]
            coll = bpy.data.collections["MH " + name]
            assets = [o for o in coll.objects if o not in (rig, body, garment) and o.type == "MESH"]
            P = Poser(rig)
            frame = POSERS[name](P, rig)
            figs[name] = dict(rig=rig, body=body, assets=assets, poser=P, final=P.snapshot(), frame=frame, garment=garment)
        couch = [bpy.data.objects[n] for n in ("Mattress", "Cushion 0", "Cushion 1", "Couch (kline)")]
        finish_build(figs, work, couch, t0)

    MASKS = {"Standing actor": dict(paint=(0.60, 0.52, 0.41), hair=(0.035, 0.028, 0.022), beard=True),
             "Reclining actor": dict(paint=(0.60, 0.53, 0.42), hair=(0.075, 0.048, 0.03), beard=False)}

    def finish_build(figs, work, couch, t0):
        sc = bpy.context.scene
        sc.frame_set(T_END)
        bpy.context.view_layer.update()
        for name, fig in figs.items():
            for o in [fig["body"]] + fig["assets"]:
                freeze(o)
        out = {n: [f["body"], f["garment"]] + f["assets"] for n, f in figs.items()}
        # masks, wigs, beard; boots
        for name, mp in MASKS.items():
            if name in figs:
                out[name] += build_mask(name, figs[name], mp["paint"], mp["hair"], beard=mp["beard"], trim_wig=mp["beard"])
        if "Standing actor" in figs:
            out["Standing actor"].append(build_boots("Standing actor", figs["Standing actor"]["body"]))
        print("MASKS %.1fs" % (time.time() - t0))
        # second cloth pass: himation and blanket on the frozen figures
        drapes = []
        if "Standing actor" in figs:
            f = figs["Standing actor"]
            cols = [f["body"], f["garment"]]
            cc = get_coll("COL2 Standing")
            for o in cols:
                make_collider(o, thick=0.008, friction=40.0)
                cc.objects.link(o)
            him = build_himation("Standing actor", f, cols)
            add_cloth(him, cc, 90, mass=0.3, bend=0.6, tension=15.0, quality=7, air=2.0)
            drapes.append(("Standing actor", him))
        if "Reclining actor" in figs:
            f = figs["Reclining actor"]
            cols = [f["body"], f["garment"]] + couch + [bpy.data.objects["Platform deck"]]
            cc = get_coll("COL2 Reclining")
            for o in cols:
                make_collider(o, thick=0.007, friction=10.0)
                if o.name not in cc.objects:
                    cc.objects.link(o)
            bl = build_blanket("Reclining actor", f, cols)
            add_cloth(bl, cc, 90, pin=None, mass=0.4, bend=2.0, tension=15.0, quality=6, rest_key=None)
            drapes.append(("Reclining actor", bl))
        for o in bpy.data.objects:
            if o.animation_data:
                o.animation_data_clear()
        sc.frame_start, sc.frame_end = 1, 90
        t1 = time.time()
        for fr in range(1, 91):
            sc.frame_set(fr)
        print("DRAPE SIM %.1fs" % (time.time() - t1))
        for name, o in drapes:
            freeze(o)
            out[name].append(o)
        # render dressing: thickness and smoothing; bodies subdivided once
        for name, objs in out.items():
            for o in objs:
                for md in list(o.modifiers):
                    if md.type == "COLLISION":
                        o.modifiers.remove(md)
                if o.type != "MESH":
                    continue
                if o == figs[name]["body"]:
                    ss = o.modifiers.new("Subsurf", "SUBSURF")
                    ss.levels, ss.render_levels = 1, 1
                elif o in (figs[name]["garment"],) or o.name.endswith(("himation", "blanket")):
                    sd = o.modifiers.new("Solidify", "SOLIDIFY")
                    sd.thickness = 0.003
                    sd.offset = 0.0
                    ss = o.modifiers.new("Subsurf", "SUBSURF")
                    ss.levels, ss.render_levels = 1, 1
        # collect into one collection per figure, drop everything else
        top = get_coll("MH figures")
        keep = set()
        for name, objs in out.items():
            c = get_coll("MH " + name + " (frozen)", top)
            for o in objs:
                link_to(o, c)
                if not o.name.startswith("MH "):
                    o.name = "MH " + o.name          # no clashes with the mannequins' names
                keep.add(o.name)
        for o in list(bpy.data.objects):
            if o.name not in keep:
                bpy.data.objects.remove(o)
        for c in list(bpy.data.collections):
            if c != top and not c.name.endswith("(frozen)"):
                bpy.data.collections.remove(c)
        bpy.ops.outliner.orphans_purge(do_recursive=True)
        try:
            bpy.ops.file.pack_all()
        except Exception as e:
            print("pack failed", e)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "figures.blend"), compress=True)
        print("FIGURES SAVED %.1fs" % (time.time() - t0))


# =============================================================================
# compose (plain Python 3 with Pillow): side-by-side images with labels
# =============================================================================
LABEL_A = "Current: mannequins"
LABEL_B = "Option: MakeHuman + masks"
FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"


def _label(im, text, size=26):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(FONT, size)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(im, "RGBA")
    pad = int(size * 0.45)
    x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
    w, h = x1 - x0, y1 - y0
    d.rectangle((16, 16, 16 + w + 2 * pad, 16 + h + 2 * pad), fill=(20, 20, 20, 170))
    d.text((16 + pad - x0, 16 + pad - y0), text, font=font, fill=(245, 242, 235, 255))


def compose(opts):
    from PIL import Image
    work = os.path.abspath(opts["work"])
    rd = os.path.join(work, "renders")
    cd = os.path.join(work, "compare")
    os.makedirs(cd, exist_ok=True)
    outs = []
    for tag in ("tableau", "cutaway", "tableau_crop"):
        pa, pb = os.path.join(rd, "A_%s.png" % tag), os.path.join(rd, "B_%s.png" % tag)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            continue
        a, b = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
        size = 26 if a.width <= 1400 else int(26 * a.width / 1280 * 0.75)
        _label(a, LABEL_A, size)
        _label(b, LABEL_B, size)
        gap = 8
        im = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height)), (255, 255, 255))
        im.paste(a, (0, 0))
        im.paste(b, (a.width + gap, 0))
        name = "compare_%s" % tag
        im.save(os.path.join(cd, name + ".png"))
        outs.append((name, im))
        if tag == "tableau_crop":
            bb = Image.open(pb).convert("RGB")
            _label(bb, LABEL_B + " (close crop, same camera)", size)
            bb.save(os.path.join(cd, "B_reclining_mask_crop.png"))
            outs.append(("B_reclining_mask_crop", bb))
    repo = opts.get("repo-out")
    if repo:
        os.makedirs(repo, exist_ok=True)
        for name, im in outs:
            path = os.path.join(repo, name + ".jpg")
            q = 95
            while True:
                im.save(path, quality=q, optimize=True, progressive=True)
                if os.path.getsize(path) < 1.9e6 or q <= 60:
                    break
                q -= 5
            print("JPG", path, "%.2f MB" % (os.path.getsize(path) / 1e6), "q", q)


def run_all(opts):
    blender = opts.get("blender", "/opt/blender/blender")
    work = os.path.abspath(opts["work"])
    scene = os.path.abspath(opts["scene"])
    env = dict(os.environ)
    if opts.get("mpfb-resources"):
        env["BLENDER_USER_RESOURCES"] = os.path.abspath(opts["mpfb-resources"])
    me = os.path.abspath(__file__)
    subprocess.run([blender, "-b", "-P", me, "--", "build", "--scene", scene, "--work", work], env=env, check=True)
    subprocess.run([blender, "-b", scene, "-P", me, "--", "render", "--work", work,
                    "--samples", str(opts.get("samples", 64)), "--only", "ABC"], check=True)
    compose(dict(work=work, **{"repo-out": opts.get("repo-out", HERE)}))


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
    elif MODE == "compose":
        compose(OPTS)
    elif MODE == "all":
        run_all(OPTS)
