"""Ekkyklema, Theatre of Dionysus c. 425-411 BC: build the whole 3D scene from scratch.

Run headless (Blender 4.5 LTS):
    blender -b --factory-startup -P build_scene.py -- --assets DIR --out ekkyklema.blend

--assets  cache made by fetch_assets.py (default: $EKK_ASSETS or ./assets_cache)
--out     .blend to write (default: ./ekkyklema.blend)

The script is deterministic: every random choice uses a fixed seed, and the only
inputs are the CC0 assets listed in ASSETS.md. Re-running it rebuilds the file from
an empty scene.

Units are metres. Axes: +Y points from the skene toward the audience (true bearing
about 345 deg, NNW), +X along the facade toward ENE, +Z up. The facade's outer face
is the plane y = 0, the central door is centred on x = 0, and the orchestra floor is
z = 0. The action (doors, platform, stagehands) is keyframed on one 24 fps timeline
that matches SHOTLIST.md; camera markers switch cameras, so a final render is just
"render frames N-M".
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector, noise

# ----------------------------------------------------------------------------
# arguments
# ----------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


ASSETS = os.path.abspath(_arg("--assets", os.environ.get("EKK_ASSETS", os.path.join(HERE, "assets_cache"))))
OUT = os.path.abspath(_arg("--out", os.path.join(HERE, "ekkyklema.blend")))
LIGHT = "--light" in argv          # skip vegetation scatter (fast test builds)

FPS = 24


def F(sec):
    """seconds on the film timeline -> frame number (frame 1 = 0.0 s)"""
    return int(round(sec * FPS)) + 1


# ----------------------------------------------------------------------------
# reconstruction parameters (STORYBOARD.md R1-R6, layout.svg)
# ----------------------------------------------------------------------------
SKENE_W, SKENE_D, SKENE_H = 12.0, 4.7, 5.0     # facade 12 x 5 m (layout.svg); depth from section
WALL_T = 0.20                                  # boarded wall thickness
DOOR_W, DOOR_H = 2.8, 3.2                      # R2
LEAF_T = 0.065
HINGE_Y = -WALL_T                              # leaves hang at the inner face, swing inward (R6)
PLAT_W, PLAT_D, PLAT_H = 2.4, 1.6, 0.30        # R1
WHEEL_R = 0.12
ROLL = 1.8                                     # travel, metres (storyboard beat 4)
# the leaves (1.4 m) sweep a quarter circle behind the facade; the platform must wait
# clear of that sweep, so its front edge starts 1.68 m behind the facade face.
PLAT_FRONT_IN = -1.68
PLAT_Y_IN = PLAT_FRONT_IN - PLAT_D / 2         # platform centre, rolled in
PLAT_Y_OUT = PLAT_Y_IN + ROLL

# sun: Athens 37.97 N, about 1 April (City Dionysia), 09:00 local solar time
SUN_ALT, SUN_AZ = 37.0, 118.0                  # degrees; azimuth from true north
AXIS_AZ = 345.0                                # true bearing of +Y (theatre axis, approx.)

# action timeline (seconds), see SHOTLIST.md
T = dict(
    cut_in=(17.0, 19.5),        # section cut sweeps through the skene (beat 2)
    doors_open=(31.0, 34.0),    # beat 3
    roll_out=(35.0, 38.7),      # beat 4: 1.8 m in 3.7 s
    roll_in=(58.6, 62.3),       # beat 6
    doors_close=(62.6, 65.2),
    plan_on=66.0,               # beat 7: overhead, roof sectioned away
    roll_out2=(70.4, 74.0),     # beat 7b: windlass comparison
    end_plan=82.0,
    teaser_doors=(87.2, 89.4),  # beat 8: Ajax teaser, doors open again
    end=90.0,
)

rng = random.Random(425)       # 425 BC, Acharnians


# ----------------------------------------------------------------------------
# scene reset and collections
# ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "Ekkyklema"
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = F(T["end"]) - 1
scene.unit_settings.system = "METRIC"

COLL = {}


def coll(name, parent=None):
    if name in COLL:
        return COLL[name]
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    COLL[name] = c
    return c


for _n in ("Landscape", "Theatron", "Skene", "Platform", "Figures", "Vegetation", "Overlays", "Cameras", "Lights", "Library"):
    coll(_n)
COLL["Library"].hide_render = True
COLL["Library"].hide_viewport = True


def link(obj, cname):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    COLL[cname].objects.link(obj)
    return obj


# ----------------------------------------------------------------------------
# mesh helpers
# ----------------------------------------------------------------------------
def mesh_obj(name, verts, faces, cname, smooth=False, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    me.update()
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    ob = bpy.data.objects.new(name, me)
    COLL[cname].objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def box_geom(x0, x1, y0, y1, z0, z1, off=0):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, [tuple(i + off for i in face) for face in f]


class Builder:
    """accumulate many boxes (or other parts) into one mesh"""

    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def box(self, x0, x1, y0, y1, z0, z1, mi=0):
        v, f = box_geom(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1), len(self.v))
        self.v += v
        self.f += f
        self.m += [mi] * len(f)

    def add(self, verts, faces, mi=0):
        off = len(self.v)
        self.v += [tuple(p) for p in verts]
        self.f += [tuple(i + off for i in fc) for fc in faces]
        self.m += [mi] * len(faces)

    def obj(self, name, cname, mats, smooth=False):
        ob = mesh_obj(name, self.v, self.f, cname, smooth=smooth)
        for m in mats:
            ob.data.materials.append(m)
        ob.data.polygons.foreach_set("material_index", self.m)
        ob.data.update()
        return ob


def cylinder_geom(r, z0, z1, n=24, axis="Z", center=(0, 0, 0), r1=None, caps=True):
    r1 = r if r1 is None else r1
    v, f = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        v.append((r * c, r * s, z0))
        v.append((r1 * c, r1 * s, z1))
    for i in range(n):
        j = (i + 1) % n
        f.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    if caps:
        f.append(tuple(2 * i for i in reversed(range(n))))
        f.append(tuple(2 * i + 1 for i in range(n)))
    out = []
    for (x, y, z) in v:
        if axis == "X":
            x, y, z = z, x, y
        elif axis == "Y":
            x, y, z = y, z, x
        out.append((x + center[0], y + center[1], z + center[2]))
    return out, f


def add_bevel(ob, width=0.012, segs=2):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segs
    m.limit_method = "ANGLE"
    m.harden_normals = False
    return m


def add_subsurf(ob, view=1, render=2):
    m = ob.modifiers.new("Subsurf", "SUBSURF")
    m.levels = view
    m.render_levels = render
    return m


def set_smooth(ob, on=True):
    ob.data.polygons.foreach_set("use_smooth", [on] * len(ob.data.polygons))
    ob.data.update()


def empty(name, loc=(0, 0, 0), cname="Platform", size=0.3, kind="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    e.location = loc
    COLL[cname].objects.link(e)
    return e


# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------
IMG_CACHE = {}


def tex_path(tex, kind):
    d = os.path.join(ASSETS, "textures", tex)
    keys = {"diff": ("_diff_", "_col_"), "nor": ("_nor_gl_",), "rough": ("_rough_",)}[kind]
    for fn in sorted(os.listdir(d)):
        if any(k in fn for k in keys):
            return os.path.join(d, fn)
    raise FileNotFoundError(f"{tex} {kind} in {d}: run fetch_assets.py")


def image(path, noncolor=False):
    key = (path, noncolor)
    if key not in IMG_CACHE:
        img = bpy.data.images.load(path, check_existing=True)
        if noncolor:
            img.colorspace_settings.name = "Non-Color"
        IMG_CACHE[key] = img
    return IMG_CACHE[key]


class NT:
    """tiny node-tree helper"""

    def __init__(self, mat):
        self.t = mat.node_tree
        self.t.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        node = self.t.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 200
        for k, v in props.items():
            if k.startswith("in_"):
                key = k[3:].replace("_", " ")
                node.inputs[key].default_value = v
            else:
                setattr(node, k, v)
        return node

    def l(self, a, b):
        self.t.links.new(a, b)


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m


def pbr_tex_nodes(nt, tex, size, coord_out, rot=0.0, offset=(0, 0, 0), blend=0.2, proj="BOX"):
    """returns (color_socket, rough_socket, normal_map_node_color_socket)"""
    mp = nt.n("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
    mp.inputs["Rotation"].default_value = (0, rot, 0) if proj == "BOX" else (0, 0, rot)
    mp.inputs["Location"].default_value = offset
    nt.l(coord_out, mp.inputs["Vector"])
    outs = []
    for kind in ("diff", "rough", "nor"):
        it = nt.n("ShaderNodeTexImage")
        it.image = image(tex_path(tex, kind), noncolor=(kind != "diff"))
        it.projection = proj
        it.projection_blend = blend
        it.interpolation = "Linear"
        nt.l(mp.outputs[0], it.inputs[0])
        outs.append(it.outputs["Color"])
    return outs


def mat_pbr(name, tex, size, hsv=(0.5, 1.0, 1.0), rough=(0.0, 1.0), nstr=1.0, coords="Object",
            grime=0.0, grime_h=0.6, streaks=0.0, rot=0.0, tint=None, tint_fac=0.0, blend=0.2, sss=0.0):
    """image-based PBR material with box projection in object (or world) space.
    grime: darken toward the ground (splash dirt); streaks: vertical rain streaks."""
    m = new_mat(name)
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    co = tc.outputs[coords]
    col, rgh, nor = pbr_tex_nodes(nt, tex, size, co, rot=rot, blend=blend)
    hs = nt.n("ShaderNodeHueSaturation", in_Hue=hsv[0], in_Saturation=hsv[1], in_Value=hsv[2])
    nt.l(col, hs.inputs["Color"])
    col = hs.outputs[0]
    if tint is not None and tint_fac > 0:
        mx = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        mx.inputs["Factor"].default_value = tint_fac
        mx.inputs["B"].default_value = (*tint, 1)
        nt.l(col, mx.inputs["A"])
        col = mx.outputs["Result"]
    if grime > 0 or streaks > 0:
        sep = nt.n("ShaderNodeSeparateXYZ")
        nt.l(tc.outputs["Object"] if coords == "Object" else co, sep.inputs[0])
        fac_socket = None
        if grime > 0:
            # 1 at the ground, 0 above grime_h metres
            mr = nt.n("ShaderNodeMapRange", in_From_Min=0.0, in_From_Max=grime_h, in_To_Min=grime, in_To_Max=0.0)
            nt.l(sep.outputs["Z"], mr.inputs["Value"])
            fac_socket = mr.outputs[0]
        if streaks > 0:
            mp2 = nt.n("ShaderNodeMapping")
            mp2.inputs["Scale"].default_value = (6.0, 6.0, 0.25)
            nt.l(tc.outputs["Object"], mp2.inputs[0])
            nz = nt.n("ShaderNodeTexNoise", in_Scale=1.0, in_Detail=3.0, in_Roughness=0.6)
            nt.l(mp2.outputs[0], nz.inputs[0])
            cr = nt.n("ShaderNodeMapRange", in_From_Min=0.45, in_From_Max=0.75, in_To_Min=0.0, in_To_Max=streaks)
            nt.l(nz.outputs["Fac"], cr.inputs["Value"])
            if fac_socket is not None:
                ad = nt.n("ShaderNodeMath", operation="ADD", use_clamp=True)
                nt.l(fac_socket, ad.inputs[0])
                nt.l(cr.outputs[0], ad.inputs[1])
                fac_socket = ad.outputs[0]
            else:
                fac_socket = cr.outputs[0]
        mx = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        mx.inputs["B"].default_value = (0.42, 0.36, 0.30, 1)
        nt.l(fac_socket, mx.inputs["Factor"])
        nt.l(col, mx.inputs["A"])
        col = mx.outputs["Result"]
    rr = nt.n("ShaderNodeMapRange", in_To_Min=rough[0], in_To_Max=rough[1])
    nt.l(rgh, rr.inputs["Value"])
    nm = nt.n("ShaderNodeNormalMap", in_Strength=nstr)
    nt.l(nor, nm.inputs["Color"])
    bs = nt.n("ShaderNodeBsdfPrincipled")
    bs.inputs["Specular IOR Level"].default_value = 0.35
    nt.l(col, bs.inputs["Base Color"])
    nt.l(rr.outputs[0], bs.inputs["Roughness"])
    nt.l(nm.outputs[0], bs.inputs["Normal"])
    if sss > 0:
        bs.inputs["Subsurface Weight"].default_value = sss
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def mat_plain(name, color, rough=0.6, sss=0.0, sheen=0.0, spec=0.4, bump=0.0, bump_scale=40.0, emission=None):
    m = new_mat(name)
    nt = NT(m)
    bs = nt.n("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Specular IOR Level"].default_value = spec
    if sss:
        bs.inputs["Subsurface Weight"].default_value = sss
        bs.inputs["Subsurface Radius"].default_value = (0.9, 0.45, 0.25)
        bs.inputs["Subsurface Scale"].default_value = 0.01
    if sheen:
        bs.inputs["Sheen Weight"].default_value = sheen
        bs.inputs["Sheen Roughness"].default_value = 0.5
    if bump:
        tc = nt.n("ShaderNodeTexCoord")
        nz = nt.n("ShaderNodeTexNoise", in_Scale=bump_scale, in_Detail=4.0)
        nt.l(tc.outputs["Object"], nz.inputs["Vector"])
        bp = nt.n("ShaderNodeBump", in_Strength=bump, in_Distance=0.002)
        nt.l(nz.outputs["Fac"], bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
    if emission:
        bs.inputs["Emission Color"].default_value = (*emission[0], 1)
        bs.inputs["Emission Strength"].default_value = emission[1]
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def mat_cloth(name, color, rough=0.85, sheen=0.35, nstr=0.6, size=0.27, fold_bump=0.0, sss=0.0):
    """dyed wool/linen: rough_linen weave for the normal/roughness, solid dye colour"""
    m = new_mat(name)
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    col, rgh, nor = pbr_tex_nodes(nt, "rough_linen", size, tc.outputs["Object"], blend=0.3)
    # keep a little of the weave's luminance variation in the dye
    bw = nt.n("ShaderNodeRGBToBW")
    nt.l(col, bw.inputs[0])
    mr = nt.n("ShaderNodeMapRange", in_From_Min=0.2, in_From_Max=0.8, in_To_Min=0.82, in_To_Max=1.08)
    nt.l(bw.outputs[0], mr.inputs["Value"])
    # large-scale tonal variation (sun bleaching, dirt)
    nz = nt.n("ShaderNodeTexNoise", in_Scale=2.5, in_Detail=2.0)
    nt.l(tc.outputs["Object"], nz.inputs[0])
    mr2 = nt.n("ShaderNodeMapRange", in_To_Min=0.9, in_To_Max=1.06)
    nt.l(nz.outputs["Fac"], mr2.inputs["Value"])
    mul = nt.n("ShaderNodeMath", operation="MULTIPLY")
    nt.l(mr.outputs[0], mul.inputs[0])
    nt.l(mr2.outputs[0], mul.inputs[1])
    mx = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    mx.inputs["Factor"].default_value = 1.0
    mx.inputs["A"].default_value = (*color, 1)
    nt.l(mul.outputs[0], mx.inputs["B"])
    bs = nt.n("ShaderNodeBsdfPrincipled")
    nt.l(mx.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Specular IOR Level"].default_value = 0.25
    bs.inputs["Sheen Weight"].default_value = sheen
    bs.inputs["Sheen Roughness"].default_value = 0.6
    if sss:
        bs.inputs["Subsurface Weight"].default_value = sss
        bs.inputs["Subsurface Scale"].default_value = 0.004
    nm = nt.n("ShaderNodeNormalMap", in_Strength=nstr)
    nt.l(nor, nm.inputs["Color"])
    nt.l(nm.outputs[0], bs.inputs["Normal"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def mat_ghost(name, color=(0.478, 0.31, 0.549), alpha=0.28, emit=0.6):
    """evidence-code overlay: soft translucent 'ghost' (accent-2 purple for rival theories)"""
    m = new_mat(name)
    nt = NT(m)
    lw = nt.n("ShaderNodeLayerWeight", in_Blend=0.35)
    mr = nt.n("ShaderNodeMapRange", in_To_Min=alpha, in_To_Max=min(1.0, alpha * 2.4))
    nt.l(lw.outputs["Facing"], mr.inputs["Value"])
    tr = nt.n("ShaderNodeBsdfTransparent")
    em = nt.n("ShaderNodeEmission", in_Strength=emit)
    em.inputs["Color"].default_value = (*color, 1)
    df = nt.n("ShaderNodeBsdfDiffuse")
    df.inputs["Color"].default_value = (*color, 1)
    ad = nt.n("ShaderNodeAddShader")
    nt.l(em.outputs[0], ad.inputs[0])
    nt.l(df.outputs[0], ad.inputs[1])
    # overall opacity is a value node so it can be keyframed (fade in/out)
    val = nt.n("ShaderNodeValue")
    val.name = "Opacity"
    val.outputs[0].default_value = 1.0
    mul = nt.n("ShaderNodeMath", operation="MULTIPLY")
    nt.l(mr.outputs[0], mul.inputs[0])
    nt.l(val.outputs[0], mul.inputs[1])
    mix = nt.n("ShaderNodeMixShader")
    nt.l(mul.outputs[0], mix.inputs["Fac"])
    nt.l(tr.outputs[0], mix.inputs[1])
    nt.l(ad.outputs[0], mix.inputs[2])
    # ghosts cast no shadows and are invisible to everything but the camera
    lp = nt.n("ShaderNodeLightPath")
    mix2 = nt.n("ShaderNodeMixShader")
    tr2 = nt.n("ShaderNodeBsdfTransparent")
    nt.l(lp.outputs["Is Camera Ray"], mix2.inputs["Fac"])
    nt.l(tr2.outputs[0], mix2.inputs[1])
    nt.l(mix.outputs[0], mix2.inputs[2])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(mix2.outputs[0], out.inputs["Surface"])
    m.blend_method = "BLEND" if hasattr(m, "blend_method") else None
    return m


def mat_section():
    """cut faces of the museum-style section: flat warm off-white with fine hatching"""
    m = new_mat("Section cut")
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    # 45-degree hatch in world space (works on every cut plane)
    sep = nt.n("ShaderNodeSeparateXYZ")
    nt.l(tc.outputs["Object"], sep.inputs[0])
    add = nt.n("ShaderNodeMath", operation="ADD")
    nt.l(sep.outputs["Y"], add.inputs[0])
    nt.l(sep.outputs["Z"], add.inputs[1])
    add2 = nt.n("ShaderNodeMath", operation="ADD")
    nt.l(add.outputs[0], add2.inputs[0])
    nt.l(sep.outputs["X"], add2.inputs[1])
    wave = nt.n("ShaderNodeMath", operation="PINGPONG")
    wave.inputs[1].default_value = 0.035
    nt.l(add2.outputs[0], wave.inputs[0])
    st = nt.n("ShaderNodeMath", operation="GREATER_THAN")
    st.inputs[1].default_value = 0.006
    nt.l(wave.outputs[0], st.inputs[0])
    mix = nt.n("ShaderNodeMix", data_type="RGBA")
    mix.inputs["A"].default_value = (0.55, 0.36, 0.22, 1)
    mix.inputs["B"].default_value = (0.86, 0.80, 0.70, 1)
    nt.l(st.outputs[0], mix.inputs["Factor"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.9)
    nt.l(mix.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Emission Color"].default_value = (0.86, 0.80, 0.70, 1)
    bs.inputs["Emission Strength"].default_value = 0.08
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


MAT = {}
MAT["boards"] = mat_pbr("Facade boards (weathered)", "weathered_planks", 2.0, hsv=(0.5, 0.75, 0.95),
                        rough=(0.55, 0.95), nstr=1.2, grime=0.45, grime_h=0.9, streaks=0.35)
MAT["timber"] = mat_pbr("Timber posts", "rough_wood", 0.9, hsv=(0.5, 0.7, 0.85), rough=(0.6, 0.95),
                        nstr=1.4, grime=0.35, grime_h=0.7, streaks=0.2)
MAT["timber_in"] = mat_pbr("Timber interior", "rough_wood", 0.9, hsv=(0.5, 0.85, 0.95), rough=(0.6, 0.95), nstr=1.2)
MAT["boards_in"] = mat_pbr("Boards interior", "weathered_planks", 2.0, hsv=(0.5, 0.9, 1.05), rough=(0.55, 0.95), nstr=1.0)
MAT["deck"] = mat_pbr("Platform deck", "weathered_brown_planks", 1.8, hsv=(0.5, 0.85, 1.05), rough=(0.5, 0.9), nstr=1.0)
MAT["frame"] = mat_pbr("Platform frame", "rough_wood", 0.7, hsv=(0.5, 0.9, 0.75), rough=(0.55, 0.9), nstr=1.2)
MAT["leaf"] = mat_pbr("Door leaves", "weathered_planks", 1.6, hsv=(0.52, 0.8, 0.72), rough=(0.5, 0.9), nstr=1.2,
                      grime=0.4, grime_h=0.8, streaks=0.2)
MAT["couch"] = mat_pbr("Couch wood", "fine_grained_wood", 0.6, hsv=(0.5, 1.0, 1.05), rough=(0.35, 0.7), nstr=0.8)
MAT["section"] = mat_section()
MAT["iron"] = mat_plain("Iron fittings", (0.05, 0.045, 0.04), rough=0.55, spec=0.5)


# ----------------------------------------------------------------------------
# terrain
# ----------------------------------------------------------------------------
ORCH_C = Vector((0.0, 11.0))       # orchestra centre (shape and size debated: never drawn)
TH_R0, TH_R1 = 13.0, 46.0          # first and last bench radius
TH_SLOPE = math.tan(math.radians(25.0))
TH_HALF = math.radians(68.0)       # half-angle of the theatron fan


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------
# geography helpers: true bearing <-> scene coordinates
# ----------------------------------------------------------------------------
_UX = (math.sin(math.radians(AXIS_AZ + 90)), math.cos(math.radians(AXIS_AZ + 90)))   # scene +X in (E, N)
_UY = (math.sin(math.radians(AXIS_AZ)), math.cos(math.radians(AXIS_AZ)))             # scene +Y in (E, N)


def true_to_scene(east, north):
    return east * _UX[0] + north * _UX[1], east * _UY[0] + north * _UY[1]


def scene_to_true(x, y):
    return x * _UX[0] + y * _UY[0], x * _UX[1] + y * _UY[1]


def polar_scene(bearing, dist):
    a = math.radians(bearing)
    return true_to_scene(dist * math.sin(a), dist * math.cos(a))


# distant landmarks (heights relative to the orchestra, about 90 m above sea level)
LANDMARKS = [
    # kind, bearing, distance, height, sigma (m), ridge bearing, ridge half-length
    ("hill", 30.0, 2700.0, 190.0, 260.0, None, 0),       # Lykabettos
    ("hill", 236.0, 950.0, 55.0, 190.0, None, 0),        # Philopappos (Mouseion) hill
    ("hill", 287.0, 820.0, 22.0, 200.0, None, 0),        # Pnyx / Nymphs hill
    ("hill", 312.0, 560.0, 20.0, 120.0, None, 0),        # Areopagus
    ("ridge", 100.0, 7200.0, 930.0, 1900.0, 20.0, 9000.0),   # Hymettus
    ("ridge", 282.0, 9500.0, 380.0, 1600.0, 340.0, 9000.0),  # Aigaleo
    ("ridge", 30.0, 16000.0, 1000.0, 3200.0, 120.0, 5000.0),  # Pentelikon
    ("ridge", 350.0, 23000.0, 1250.0, 4500.0, 80.0, 14000.0),  # Parnes
]
_LM = []
for kind, br, dist, hgt, sig, rb, rl in LANDMARKS:
    cx, cy = polar_scene(br, dist)
    if kind == "hill":
        _LM.append((kind, cx, cy, hgt, sig, None, 0))
    else:
        dx, dy = polar_scene(rb, 1.0)
        _LM.append((kind, cx, cy, hgt, sig, (dx, dy), rl))

ACR_C = Vector((-65.0, 192.0))     # centre of the Acropolis plateau (scene)
ACR_A, ACR_B = 150.0, 78.0         # plateau semi-axes


def acropolis_h(x, y):
    """elliptical rock: plateau ~60 m, a 9 m-wide rock face, then the slope (~22 deg)"""
    dx, dy = x - ACR_C.x, y - ACR_C.y
    rho = math.sqrt((dx / ACR_A) ** 2 + (dy / ACR_B) ** 2) + 1e-9
    r = math.hypot(dx, dy)
    d = r * (1.0 - 1.0 / rho)          # metres outside the plateau edge, along the ray
    if d <= 0:
        return 60.0 + 0.02 * (-d)
    if d < 9.0:
        return 60.0 - 22.0 * smoothstep(0.0, 9.0, d)
    t = (d - 9.0) / 98.0
    return 38.0 * (1.0 - smoothstep(0.0, 1.0, t) * 0.35 - 0.65 * min(t, 1.0)) if t < 1 else 0.0


def far_h(x, y):
    """landscape beyond the local site: plain falling to the sea, hills, mountains"""
    z = 0.0
    e, n = scene_to_true(x, y)
    south = -n
    t = max(0.0, min(1.0, (south - 250.0) / 5300.0))
    z -= 86.0 * t ** 1.15
    coast = -5600.0 + 0.25 * e
    if n < coast:
        z = -96.0
    for kind, cx, cy, hgt, sig, rd, rl in _LM:
        px, py = x - cx, y - cy
        if kind == "hill":
            z += hgt * math.exp(-(px * px + py * py) / (2 * sig * sig))
        else:
            along = px * rd[0] + py * rd[1]
            across = px * -rd[1] + py * rd[0]
            fall = max(0.0, abs(along) - rl)
            z += hgt * math.exp(-(across * across) / (2 * sig * sig)) * math.exp(-(fall * fall) / (2 * (sig * 1.5) ** 2)) \
                * (1.0 + 0.12 * noise.noise(Vector((along * 0.0006, across * 0.0006, 4.2))))
    return z


def hill(x, y):
    """the ground before the theatre is cut into it: Acropolis rock + Athens basin + noise"""
    z = acropolis_h(x, y) + far_h(x, y)
    lat = min(1.0, smoothstep(10, 40, abs(x)) + smoothstep(25, 60, y))
    z += 2.0 * noise.noise(Vector((x * 0.011, y * 0.011, 3.1))) * lat
    z += 0.6 * noise.noise(Vector((x * 0.05, y * 0.05, 7.7))) * lat
    z += 0.08 * noise.noise(Vector((x * 0.3, y * 0.3, 1.7)))
    return z


def theatron_h(x, y):
    p = Vector((x, y)) - ORCH_C
    r = p.length
    return max(0.0, r - (TH_R0 - 0.6)) * TH_SLOPE


def theatron_w(x, y):
    """1 inside the bench fan, 0 outside (soft edges)"""
    p = Vector((x, y)) - ORCH_C
    r = p.length
    ang = abs(math.atan2(p.x, p.y))
    w_ang = 1.0 - smoothstep(TH_HALF + 0.02, TH_HALF + 0.30, ang)
    w_r = 1.0 - smoothstep(TH_R1 + 1.5, TH_R1 + 10.0, r)
    return w_ang * w_r


def flat_w(x, y):
    """1 on the level working area (skene + orchestra), fading out over ~10 m"""
    d = max(abs(x) - 15.0, -15.0 - y, y - 13.0, 0.0)
    return 1.0 - smoothstep(0.0, 11.0, d)


def terrain_h(x, y):
    w = theatron_w(x, y)
    h = hill(x, y) * (1 - w) + theatron_h(x, y) * w
    return h * (1.0 - flat_w(x, y))


def build_terrain():
    # non-uniform grid: fine near the theatre, coarse far away
    def axis_samples(lo, hi, fine_lo, fine_hi, fine, coarse):
        xs, x = [], lo
        while x < hi:
            xs.append(x)
            step = fine if fine_lo <= x <= fine_hi else coarse
            x += step
        xs.append(hi)
        return xs

    xs = axis_samples(-340, 340, -75, 75, 1.0, 5.0)
    ys = axis_samples(-340, 340, -45, 135, 1.0, 5.0)
    verts, cols = [], []
    for y in ys:
        for x in xs:
            verts.append((x, y, terrain_h(x, y)))
    nx = len(xs)
    faces = []
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))
    ob = mesh_obj("Terrain", verts, faces, "Landscape", smooth=True)
    me = ob.data
    # masks as a colour attribute: R = trodden earth, G = grass/scrub, B = rock
    attr = me.color_attributes.new("mask", "FLOAT_COLOR", "POINT")
    vals = []
    for (x, y, z) in verts:
        p = Vector((x, y)) - ORCH_C
        # trodden earth: around skene + orchestra, edges broken by noise (no drawn outline)
        n = noise.noise(Vector((x * 0.15, y * 0.15, 1.3))) * 3.5
        d_or = p.length - 15.0 + n
        d_sk = max(abs(x) - 11.0, -y - 10.0, y - 2.0) + n
        trod = (1.0 - smoothstep(-2.0, 4.0, min(d_or, d_sk))) * (1.0 - theatron_w(x, y) * 0.6)
        # bare rock where the ground is steep (the Acropolis rock face)
        gx = terrain_h(x + 1.0, y) - terrain_h(x - 1.0, y)
        gy = terrain_h(x, y + 1.0) - terrain_h(x, y - 1.0)
        slope = math.hypot(gx, gy) / 2.0
        rock = smoothstep(0.75, 1.3, slope)
        vals += [trod, 1.0 - trod, rock, 1.0]
    attr.data.foreach_set("color", vals)
    ob.data.materials.append(build_terrain_material())
    return ob


def build_terrain_material():
    """cheap on purpose (it covers most pixels): planar XY projection for the soil
    layers, box projection only for rock, no roughness maps, one normal-map node"""
    m = new_mat("Terrain")
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    attr = nt.n("ShaderNodeAttribute", attribute_name="mask")
    sep = nt.n("ShaderNodeSeparateColor")
    nt.l(attr.outputs["Color"], sep.inputs[0])

    def layer(tex, size, hsv, proj="FLAT"):
        mp = nt.n("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
        nt.l(tc.outputs["Object"], mp.inputs["Vector"])
        outs = []
        for kind in ("diff", "nor"):
            it = nt.n("ShaderNodeTexImage")
            it.image = image(tex_path(tex, kind), noncolor=(kind == "nor"))
            it.projection = proj
            it.projection_blend = 0.3
            nt.l(mp.outputs[0], it.inputs[0])
            outs.append(it.outputs["Color"])
        hs = nt.n("ShaderNodeHueSaturation", in_Hue=hsv[0], in_Saturation=hsv[1], in_Value=hsv[2])
        nt.l(outs[0], hs.inputs["Color"])
        return hs.outputs[0], outs[1]

    earth = layer("dirt", 2.0, (0.49, 0.95, 0.95))
    soil = layer("dry_ground_rocks", 4.0, (0.5, 0.9, 1.0))
    grass = layer("sparse_grass", 2.5, (0.47, 0.8, 0.95))
    rock = layer("rock_wall_02", 6.0, (0.5, 0.35, 1.25), proj="BOX")

    nz = nt.n("ShaderNodeTexNoise", in_Scale=0.08, in_Detail=3.0, in_Roughness=0.6)
    nt.l(tc.outputs["Object"], nz.inputs[0])
    gmask = nt.n("ShaderNodeMapRange", in_From_Min=0.4, in_From_Max=0.62)
    nt.l(nz.outputs["Fac"], gmask.inputs["Value"])

    def mix(fac, a, b):
        mx = nt.n("ShaderNodeMix", data_type="RGBA")
        nt.l(fac, mx.inputs["Factor"])
        nt.l(a, mx.inputs["A"])
        nt.l(b, mx.inputs["B"])
        return mx.outputs["Result"]

    c = mix(gmask.outputs[0], soil[0], grass[0])
    n = mix(gmask.outputs[0], soil[1], grass[1])
    c = mix(sep.outputs["Red"], c, earth[0])
    n = mix(sep.outputs["Red"], n, earth[1])
    c = mix(sep.outputs["Blue"], c, rock[0])
    n = mix(sep.outputs["Blue"], n, rock[1])
    nm = nt.n("ShaderNodeNormalMap", in_Strength=1.0)
    nt.l(n, nm.inputs["Color"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.92)
    bs.inputs["Specular IOR Level"].default_value = 0.25
    nt.l(c, bs.inputs["Base Color"])
    nt.l(nm.outputs[0], bs.inputs["Normal"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


# ----------------------------------------------------------------------------
# skene (wooden stage building)
# ----------------------------------------------------------------------------
SKENE_PARTS = []   # architecture objects that the section cutters slice


def build_skene():
    hw, d, h, t = SKENE_W / 2, SKENE_D, SKENE_H, WALL_T
    dx = DOOR_W / 2
    post = 0.26          # post section
    proud = 0.05         # posts and rails stand proud of the boarding

    # --- boarding (facade, sides, back): separate closed boxes per panel
    b = Builder()
    y0, y1 = -t, -proud
    # facade panels between posts / around the door
    xs = [-hw, -4.0, -2.0, -dx, dx, 2.0, 4.0, hw]
    for i in range(len(xs) - 1):
        a, c = xs[i], xs[i + 1]
        if abs(a + dx) < 1e-6 and abs(c - dx) < 1e-6:
            b.box(a, c, y0, y1, DOOR_H, h - 0.02)          # above the door
        else:
            b.box(a, c, y0, y1, 0.0, h - 0.02)
    # side walls and back wall
    b.box(-hw, -hw + t - 0.05, -d, -t, 0, h - 0.02)
    b.box(hw - t + 0.05, hw, -d, -t, 0, h - 0.02)
    b.box(-hw, hw, -d, -d + t - 0.05, 0, h - 0.02)
    boards = b.obj("Skene boarding", "Skene", [MAT["boards"]])
    SKENE_PARTS.append(boards)

    # --- frame: posts, rails, door frame, lintel
    f = Builder()
    for x in (-hw + post / 2, -4.0, -2.0, 2.0, 4.0, hw - post / 2):
        f.box(x - post / 2, x + post / 2, -t - 0.02, 0.0, 0.0, h - 0.25)
    # jamb posts (stouter) and lintel
    jp = 0.24
    for s in (-1, 1):
        f.box(s * dx, s * (dx + jp), -t - 0.02, 0.0, 0.0, DOOR_H + 0.30)
    f.box(-dx - jp - 0.15, dx + jp + 0.15, -t - 0.02, 0.0, DOOR_H, DOOR_H + 0.30)
    # rails: top rail across, bottom rail interrupted by the door
    f.box(-hw, hw, -t - 0.02, 0.01, h - 0.55, h - 0.25)
    for s in (-1, 1):
        a, c = s * (dx + jp), s * hw
        f.box(min(a, c) + (0.0 if s > 0 else 0), max(a, c), -t - 0.02, 0.01, 0.38, 0.62)
    # threshold: a worn sill flush with the ground
    f.box(-dx, dx, -t, 0.0, -0.05, 0.015)
    # corner posts on the back corners
    for x in (-hw + post / 2, hw - post / 2):
        f.box(x - post / 2, x + post / 2, -d, -d + post, 0.0, h - 0.25)
    frame = f.obj("Skene frame", "Skene", [MAT["timber"]])
    add_bevel(frame, 0.015, 2)
    SKENE_PARTS.append(frame)

    # --- roof: plank deck on joists (actors could appear up here)
    r = Builder()
    r.box(-hw - 0.08, hw + 0.08, -d - 0.08, 0.10, h - 0.12, h)
    roof = r.obj("Skene roof", "Skene", [MAT["boards"]])
    SKENE_PARTS.append(roof)
    j = Builder()
    xj = -hw + 0.3
    while xj < hw - 0.2:
        j.box(xj - 0.07, xj + 0.07, -d + 0.05, -0.02, h - 0.34, h - 0.12)
        xj += 0.75
    # two beams under the joists
    j.box(-hw + 0.1, hw - 0.1, -d * 0.5 - 0.12, -d * 0.5 + 0.12, h - 0.58, h - 0.34)
    joists = j.obj("Skene joists", "Skene", [MAT["timber_in"]])
    add_bevel(joists, 0.01, 1)
    SKENE_PARTS.append(joists)
    # interior posts carrying the mid beam
    ip = Builder()
    for x in (-4.0, 4.0):
        ip.box(x - 0.11, x + 0.11, -d * 0.5 - 0.11, -d * 0.5 + 0.11, 0.0, h - 0.58)
    iposts = ip.obj("Skene interior posts", "Skene", [MAT["timber_in"]])
    add_bevel(iposts, 0.01, 1)
    SKENE_PARTS.append(iposts)
    return boards, frame, roof


def build_doors():
    """two leaves, hinged at the inner face of the jambs, opening inward (R6)"""
    hinges = []
    for side in (1, -1):        # +1 = right as seen from inside (x > 0)
        hx = side * DOOR_W / 2
        hinge = empty(f"Door hinge {'E' if side > 0 else 'W'}", (hx, HINGE_Y, 0.0), "Skene", 0.4, "SINGLE_ARROW")
        b = Builder()
        w = DOOR_W / 2 - 0.006
        # boards (vertical) as slightly separate staves for visible joints
        n = 6
        for i in range(n):
            a = -side * (w * i / n + 0.003)
            c = -side * (w * (i + 1) / n - 0.003)
            b.box(a, c, 0.0, LEAF_T, 0.015, DOOR_H - 0.01)
        # ledges and brace on the inner face
        for zc in (0.5, DOOR_H - 0.55):
            b.box(-side * 0.08, -side * (w - 0.08), -0.045, 0.0, zc - 0.09, zc + 0.09, 0)
        leaf = b.obj(f"Door leaf {'E' if side > 0 else 'W'}", "Skene", [MAT["leaf"]])
        add_bevel(leaf, 0.006, 1)
        leaf.parent = hinge
        # iron ring pull on the inner face, near the meeting edge (torus turned upright)
        ring_v, ring_f = torus_geom(0.06, 0.008, 20, 8)
        ring_v = [(vx - side * (w - 0.18), vz - 0.06, vy + 1.15) for (vx, vy, vz) in ring_v]
        ring = mesh_obj(f"Door ring {'E' if side > 0 else 'W'}", ring_v, ring_f, "Skene", smooth=True, mat=MAT["iron"])
        ring.parent = hinge
        hinges.append((side, hinge, leaf))
    return hinges


def torus_geom(R, r, nu=24, nv=12):
    v, f = [], []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        for j in range(nv):
            b = 2 * math.pi * j / nv
            v.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(nu):
        for j in range(nv):
            a = i * nv + j
            bb = ((i + 1) % nu) * nv + j
            c = ((i + 1) % nu) * nv + (j + 1) % nv
            dd = i * nv + (j + 1) % nv
            f.append((a, bb, c, dd))
    return v, f


# ----------------------------------------------------------------------------
# world, sun, render settings
# ----------------------------------------------------------------------------
def scene_dir(az_deg, alt_deg):
    """true azimuth/altitude -> unit vector in scene coordinates"""
    a = math.radians(az_deg - AXIS_AZ)
    e = math.radians(alt_deg)
    return Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))


def build_world():
    w = bpy.data.worlds.new("Attic morning")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = False                     # the sun lamp provides the direct light
    sky.sun_elevation = math.radians(SUN_ALT)
    sky.sun_rotation = math.radians(SUN_AZ - AXIS_AZ)   # compass angle from +Y toward +X
    sky.altitude = 100.0
    sky.air_density = 1.0
    sky.dust_density = 1.6                   # a little spring haze
    sky.ozone_density = 1.0
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.22
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    w.mist_settings.start = 60.0
    w.mist_settings.depth = 2500.0
    w.mist_settings.falloff = "QUADRATIC"

    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 4.2
    sd.angle = math.radians(0.53)
    sd.color = (1.0, 0.955, 0.89)
    sun = bpy.data.objects.new("Sun", sd)
    COLL["Lights"].objects.link(sun)
    d = scene_dir(SUN_AZ, SUN_ALT)
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return sun


def render_settings():
    r = scene.render
    r.engine = "CYCLES"
    c = scene.cycles
    c.device = "CPU"
    c.samples = 96
    c.preview_samples = 16
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.02
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    c.denoising_prefilter = "ACCURATE"
    c.max_bounces = 6
    c.diffuse_bounces = 3
    c.glossy_bounces = 2
    c.transmission_bounces = 4
    c.transparent_max_bounces = 8
    c.volume_bounces = 0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    c.sample_clamp_indirect = 8.0
    c.use_light_tree = True
    r.use_persistent_data = True
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
    r.image_settings.file_format = "PNG"
    r.image_settings.color_depth = "8"
    vs = scene.view_settings
    vs.view_transform = "AgX"
    try:
        vs.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    vs.exposure = 0.0
    scene.display_settings.display_device = "sRGB"
    vl = scene.view_layers[0]
    vl.use_pass_mist = True


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    build_terrain()
    build_skene()
    build_doors()
    build_world()
    render_settings()
    # test camera
    cd = bpy.data.cameras.new("CAM test")
    cd.lens = 35
    cam = bpy.data.objects.new("CAM test", cd)
    COLL["Cameras"].objects.link(cam)
    cam.location = (4.0, 22.0, 4.5)
    cam.rotation_euler = (Vector((0, -1.5, 2.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=False)
    print("SAVED", OUT)


main()
