"""Ekkyklema, Theatre of Dionysus c. 425-411 BC: build the whole 3D scene from scratch.

    python3 fetch_assets.py CACHE                     # once: CC0 textures and plants (ASSETS.md)
    blender -b --factory-startup -P build_scene.py -- --assets CACHE --out ekkyklema.blend
    blender -b ekkyklema.blend -a                     # the whole film, frames 1-2160 (or -s N -e M -a)

Options: --assets DIR (default $EKK_ASSETS or ./assets_cache), --out FILE,
--light (skip the vegetation scatter for quick tests). A full build takes about
2.5 minutes on 4 CPU cores, most of it the two cloth simulations.

Deterministic: every random choice uses a fixed seed and the only inputs are the
assets listed in ASSETS.md; re-running rebuilds the file from an empty scene.

Units are metres. Axes: +Y points from the skene toward the audience (true bearing
about 345 deg, NNW), +X along the facade toward ENE, +Z up. The facade's outer face
is the plane y = 0, the central door is centred on x = 0, the orchestra floor is z = 0.

One 24 fps timeline (SHOTLIST.md): the doors, the platform (and its wheels, by
driver), the stagehands' gait, the section cutters, the evidence overlays, per-shot
exposure and the cameras are all keyframed on it, and timeline markers switch the
cameras, so the final render is just "render frames N-M". Captions are composited
afterwards and are not in the scene.
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, noise

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
# the leaves (1.4 m) sweep a quarter circle behind the facade; the platform must wait
# clear of that sweep, so its front edge starts 1.68 m behind the facade face.
PLAT_FRONT_IN = -1.68
# travel: out to the layout.svg OUT position, front edge ~1.25 m beyond the facade face
# and the back edge just inside the doorway (2.93 m in about 4 s)
ROLL = 2.93
PLAT_Y_IN = PLAT_FRONT_IN - PLAT_D / 2         # platform centre, rolled in
PLAT_Y_OUT = PLAT_Y_IN + ROLL

# sun: Athens 37.97 N, about 1 April (City Dionysia), 09:00 local solar time
SUN_ALT, SUN_AZ = 37.0, 118.0                  # degrees; azimuth from true north
AXIS_AZ = 345.0                                # true bearing of +Y (theatre axis, approx.)

# action timeline (seconds), see SHOTLIST.md
T = dict(
    cut_in=(17.0, 19.5),        # section cut sweeps through the skene (beat 2)
    doors_open=(30.9, 33.8),    # beat 3
    roll_out=(34.6, 38.6),      # beat 4: 2.93 m in 4.0 s
    roll_in=(59.6, 63.4),       # beat 6 (the stagehands come back on camera first, 57.5-59.6)
    doors_close=(63.6, 65.9),
    plan_on=66.0,               # beat 7: overhead, roof sectioned away
    roll_out2=(70.4, 74.4),     # beat 7b: windlass comparison
    end_plan=82.0,
    teaser_doors=(87.2, 89.4),  # beat 8: Ajax teaser, doors open again
    end=90.0,
)



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


def mat_cloth(name, color, rough=0.9, sheen=0.7, nstr=1.4, size=0.19, fold_bump=0.0, sss=0.0):
    """dyed wool/linen: rough_linen weave for the normal/roughness, solid dye colour"""
    m = new_mat(name)
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    col, rgh, nor = pbr_tex_nodes(nt, "rough_linen", size, tc.outputs["Object"], blend=0.3)
    # keep a little of the weave's luminance variation in the dye
    bw = nt.n("ShaderNodeRGBToBW")
    nt.l(col, bw.inputs[0])
    mr = nt.n("ShaderNodeMapRange", in_From_Min=0.2, in_From_Max=0.8, in_To_Min=0.70, in_To_Max=1.14)
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
    bs.inputs["Sheen Roughness"].default_value = 0.45
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
    mix.inputs["B"].default_value = (0.62, 0.56, 0.47, 1)
    nt.l(st.outputs[0], mix.inputs["Factor"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.9)
    nt.l(mix.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Emission Color"].default_value = (0.62, 0.56, 0.47, 1)
    bs.inputs["Emission Strength"].default_value = 0.03
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


MAT = {}
WARM = (0.86, 0.66, 0.47)     # sun-bleached pine/oak toward the STYLE.md wood range
MAT["boards"] = mat_pbr("Facade boards (weathered)", "weathered_planks", 2.0, hsv=(0.5, 0.9, 2.3),
                        rough=(0.55, 0.95), nstr=1.2, grime=0.3, grime_h=0.9, streaks=0.25, tint=WARM, tint_fac=0.55)
MAT["timber"] = mat_pbr("Timber posts", "rough_wood", 0.9, hsv=(0.5, 0.9, 1.15), rough=(0.6, 0.95),
                        nstr=1.3, grime=0.25, grime_h=0.7, streaks=0.15, tint=WARM, tint_fac=0.55)
MAT["roof"] = mat_pbr("Roof deck boards", "weathered_planks", 1.2, hsv=(0.5, 0.85, 1.5), rough=(0.55, 0.95), nstr=1.4,
                      streaks=0.3, tint=WARM, tint_fac=0.55)
MAT["timber_in"] = mat_pbr("Timber interior", "rough_wood", 0.9, hsv=(0.5, 0.9, 1.1), rough=(0.6, 0.95), nstr=1.2,
                           tint=WARM, tint_fac=0.55)
MAT["deck"] = mat_pbr("Platform deck", "weathered_brown_planks", 1.8, hsv=(0.5, 0.85, 1.05), rough=(0.5, 0.9), nstr=1.0)
MAT["frame"] = mat_pbr("Platform frame", "rough_wood", 0.7, hsv=(0.5, 0.9, 0.75), rough=(0.55, 0.9), nstr=1.2)
MAT["leaf"] = mat_pbr("Door leaves", "weathered_planks", 1.6, hsv=(0.5, 0.9, 1.8), rough=(0.5, 0.9), nstr=1.2,
                      grime=0.3, grime_h=0.8, streaks=0.2, tint=WARM, tint_fac=0.6)
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
    ang = math.atan2(dy / ACR_B, dx / ACR_A)
    rho *= 1.0 + 0.03 * noise.noise(Vector((math.cos(ang) * 3.0, math.sin(ang) * 3.0, 0.5))) \
        + 0.01 * noise.noise(Vector((math.cos(ang) * 14.0, math.sin(ang) * 14.0, 1.5)))
    r = math.hypot(dx, dy)
    d = r * (1.0 - 1.0 / rho)          # metres outside the plateau edge, along the ray
    nv = noise.noise(Vector((math.cos(ang) * 5.0, math.sin(ang) * 5.0, 7.0)))
    drop = 22.0 * (0.75 + 0.35 * nv)                     # rock face height varies, 14-30 m
    wid = 9.0 * (1.0 + 0.6 * noise.noise(Vector((math.cos(ang) * 8.0, math.sin(ang) * 8.0, 3.0))))
    wid = max(4.0, wid)
    if d <= 0:
        return 60.0 + 0.02 * (-d)
    if d < wid:
        u = d / wid
        step = smoothstep(0.0, 1.0, u) * (0.85 + 0.15 * math.sin(u * 9.0 + nv * 6.0))
        relief = 2.2 * noise.noise(Vector((x * 0.11, y * 0.11, 4.4))) + 0.9 * noise.noise(Vector((x * 0.37, y * 0.37, 8.1)))
        return 60.0 - drop * min(1.0, step) + relief * math.sin(math.pi * u)
    top = 60.0 - drop
    t = (d - wid) / (107.0 - wid)
    return top * (1.0 - smoothstep(0.0, 1.0, t) * 0.35 - 0.65 * min(t, 1.0)) if t < 1 else 0.0


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
    w_ang = 1.0 - smoothstep(TH_HALF + 0.02, TH_HALF + 0.50, ang)
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

    xs = axis_samples(-340, 340, -150, 110, 1.0, 5.0)
    ys = axis_samples(-340, 340, -80, 160, 1.0, 5.0)
    verts = []
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
        n = noise.noise(Vector((x * 0.12, y * 0.12, 1.3))) * 5.0 + noise.noise(Vector((x * 0.5, y * 0.5, 2.3))) * 1.5
        d_or = p.length - 14.0 + n
        d_sk = max(abs(x) - 10.0, -y - 9.0, y - 2.0) + n
        trod = (1.0 - smoothstep(-5.0, 6.0, min(d_or, d_sk))) * (1.0 - theatron_w(x, y) * 0.6)
        # bare rock where the ground is steep (the Acropolis rock face)
        gx = terrain_h(x + 1.0, y) - terrain_h(x - 1.0, y)
        gy = terrain_h(x, y + 1.0) - terrain_h(x, y - 1.0)
        slope = math.hypot(gx, gy) / 2.0
        rock = smoothstep(0.75, 1.3, slope) * smoothstep(18.0, 30.0, acropolis_h(x, y))
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
    soil = layer("dry_ground_rocks", 4.0, (0.5, 0.7, 0.72))
    grass = layer("sparse_grass", 2.5, (0.555, 1.15, 1.25))
    rock = layer("rock_wall_02", 6.0, (0.49, 0.75, 1.05), proj="BOX")

    nz = nt.n("ShaderNodeTexNoise", in_Scale=0.22, in_Detail=4.0, in_Roughness=0.62)
    nt.l(tc.outputs["Object"], nz.inputs[0])
    gmask = nt.n("ShaderNodeMapRange", in_From_Min=0.30, in_From_Max=0.72)
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
    stain = nt.n("ShaderNodeTexNoise", in_Scale=0.06, in_Detail=5.0, in_Roughness=0.7)
    nt.l(tc.outputs["Object"], stain.inputs[0])
    st_ramp = nt.n("ShaderNodeValToRGB")
    st_ramp.color_ramp.elements[0].position = 0.42
    st_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1)
    st_ramp.color_ramp.elements[1].position = 0.68
    st_ramp.color_ramp.elements[1].color = (1.15, 0.78, 0.55, 1)
    nt.l(stain.outputs["Fac"], st_ramp.inputs[0])
    rmul = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    rmul.inputs["Factor"].default_value = 1.0
    nt.l(rock[0], rmul.inputs["A"])
    nt.l(st_ramp.outputs[0], rmul.inputs["B"])
    c = mix(sep.outputs["Blue"], c, rmul.outputs["Result"])
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
# far landscape, sea
# ----------------------------------------------------------------------------
def build_far_land():
    rings = []
    r = 300.0
    while r < 42000.0:
        rings.append(r)
        r *= 1.075
    n = 192
    verts, faces = [], []
    for r in rings:
        for k in range(n):
            a = 2 * math.pi * k / n
            x, y = r * math.sin(a), ORCH_C.y + r * math.cos(a)
            z = terrain_h(x, y)
            # tuck the inner rings under the detailed local terrain
            z -= 2.0 * (1.0 - smoothstep(330.0, 480.0, r))
            verts.append((x, y, z))
    for i in range(len(rings) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            faces.append((a, b, b + n, a + n))
    ob = mesh_obj("Far land", verts, faces, "Landscape", smooth=True)
    m = new_mat("Far land")
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    nz = nt.n("ShaderNodeTexNoise", in_Scale=0.004, in_Detail=6.0, in_Roughness=0.62)
    nt.l(tc.outputs["Object"], nz.inputs[0])
    cr = nt.n("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.38
    cr.color_ramp.elements[0].color = (0.30, 0.25, 0.17, 1)      # dry soil, rock
    cr.color_ramp.elements[1].position = 0.62
    cr.color_ramp.elements[1].color = (0.17, 0.19, 0.10, 1)      # olive groves, maquis
    nt.l(nz.outputs["Fac"], cr.inputs[0])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.95)
    bs.inputs["Specular IOR Level"].default_value = 0.2
    nt.l(cr.outputs[0], bs.inputs["Base Color"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(m)
    ob.visible_shadow = False
    # the Saronic Gulf
    sea = mesh_obj("Sea", [(-60000, -60000, -90), (60000, -60000, -90), (60000, -2500, -90), (-60000, -2500, -90)],
                   [(0, 1, 2, 3)], "Landscape")
    sm = new_mat("Sea")
    nt = NT(sm)
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.12)
    bs.inputs["Base Color"].default_value = (0.02, 0.05, 0.07, 1)
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    sea.data.materials.append(sm)
    return ob


# ----------------------------------------------------------------------------
# theatron: wooden benches (ikria) on the slope, rows following the contour
# ----------------------------------------------------------------------------
def obox(b, c, xdir, sx, sy, sz, mi=0):
    """oriented box centred at c, local X along the horizontal direction xdir"""
    xd = Vector((xdir[0], xdir[1], 0.0)).normalized()
    yd = Vector((-xd.y, xd.x, 0.0))
    zd = Vector((0.0, 0.0, 1.0))
    c = Vector(c)
    verts = []
    for dz in (-0.5, 0.5):
        for (dx, dy) in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
            verts.append(c + xd * (dx * sx) + yd * (dy * sy) + zd * (dz * sz))
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    b.add(verts, faces, mi)


def build_theatron():
    """[R] soft background: straight plank benches set along a gently curved fan.
    The rows are polygonal (straight timbers), which reads as neither a true circle
    nor a strict rectilinear plan: the 5th-century layout is debated."""
    b = Builder()
    rr = random.Random(7)
    aisles = [-TH_HALF + i * (2 * TH_HALF / 6) for i in range(7)]   # 6 wedges
    r = TH_R0
    while r <= TH_R1 + 1e-6:
        rs = r + 0.12
        for w in range(6):
            a0 = aisles[w] + 0.55 / rs
            a1 = aisles[w + 1] - 0.55 / rs
            nseg = max(1, int(round((a1 - a0) * rs / 3.4)))
            for k in range(nseg):
                b0 = a0 + (a1 - a0) * k / nseg
                b1 = a0 + (a1 - a0) * (k + 1) / nseg
                p0 = ORCH_C + Vector((math.sin(b0), math.cos(b0))) * rs
                p1 = ORCH_C + Vector((math.sin(b1), math.cos(b1))) * rs
                mid = (p0 + p1) / 2
                ch = p1 - p0
                L = ch.length - 0.05
                zg = terrain_h(mid.x, mid.y)
                jitter = rr.uniform(-0.012, 0.012)
                obox(b, (mid.x, mid.y, zg + 0.40 + jitter), ch, L, 0.30, 0.05)
                for t in (0.1, 0.5, 0.9):
                    q = p0 + ch * t
                    zq = terrain_h(q.x, q.y)
                    obox(b, (q.x, q.y, zq + 0.19), ch, 0.07, 0.07, 0.40)
                # a low kerb board in front of each row holds the terrace
                inner = ORCH_C + (mid - ORCH_C).normalized() * (r - 0.38)
                zi = terrain_h(inner.x, inner.y)
                obox(b, (inner.x, inner.y, zi + 0.06), ch, L, 0.04, 0.16)
        r += 0.8
    mat = mat_pbr("Bench timber", "rough_wood", 0.8, hsv=(0.5, 0.65, 1.05), rough=(0.6, 0.95), nstr=1.0)
    ob = b.obj("Theatron benches", "Theatron", [mat])
    return ob


# ----------------------------------------------------------------------------
# the Acropolis: south circuit wall and (simplified, distant) Parthenon
# ----------------------------------------------------------------------------
def mat_stone(name, color, block=(1.25, 0.55), mortar=0.012, rough=0.85, bump=0.6):
    m = new_mat(name)
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    sep = nt.n("ShaderNodeSeparateXYZ")
    nt.l(tc.outputs["Object"], sep.inputs[0])
    # run the courses along the wall: u = x + y, v = z
    add = nt.n("ShaderNodeMath", operation="ADD")
    nt.l(sep.outputs["X"], add.inputs[0])
    nt.l(sep.outputs["Y"], add.inputs[1])
    cmb = nt.n("ShaderNodeCombineXYZ")
    nt.l(add.outputs[0], cmb.inputs["X"])
    nt.l(sep.outputs["Z"], cmb.inputs["Y"])
    br = nt.n("ShaderNodeTexBrick", in_Scale=1.0, in_Mortar_Size=mortar, in_Bias=0.0)
    br.inputs["Brick Width"].default_value = block[0]
    br.inputs["Row Height"].default_value = block[1]
    br.inputs["Color1"].default_value = (*color, 1)
    br.inputs["Color2"].default_value = tuple(c * 0.86 for c in color) + (1,)
    br.inputs["Mortar"].default_value = tuple(c * 0.7 for c in color) + (1,)
    nt.l(cmb.outputs[0], br.inputs["Vector"])
    nz = nt.n("ShaderNodeTexNoise", in_Scale=1.6, in_Detail=6.0)
    nt.l(tc.outputs["Object"], nz.inputs[0])
    mix = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="OVERLAY")
    mix.inputs["Factor"].default_value = 0.35
    nt.l(br.outputs["Color"], mix.inputs["A"])
    nt.l(nz.outputs["Color"], mix.inputs["B"])
    bp = nt.n("ShaderNodeBump", in_Strength=bump, in_Distance=0.02)
    nt.l(br.outputs["Fac"], bp.inputs["Height"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=rough)
    nt.l(mix.outputs["Result"], bs.inputs["Base Color"])
    nt.l(bp.outputs[0], bs.inputs["Normal"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def build_acropolis():
    # south (Kimonian) wall following the plateau edge, ~9 m high
    b = Builder()
    pts = []
    for k in range(0, 15):
        phi = math.radians(198 + k * 144 / 14)
        jit = 1.0 + 0.012 * noise.noise(Vector((k * 0.7, 0.3, 0.0)))
        x = ACR_C.x + ACR_A * 0.988 * jit * math.cos(phi)
        y = ACR_C.y + ACR_B * 0.988 * jit * math.sin(phi)
        pts.append(Vector((x, y)))
    th = 3.0
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        d = (p1 - p0)
        nrm = Vector((d.y, -d.x)).normalized()     # outward (south-ish)
        if nrm.dot(p0 - ACR_C) < 0:
            nrm = -nrm
        z0 = min(terrain_h(p0.x, p0.y), terrain_h(p1.x, p1.y)) - 4.0
        top = 64.5 + 1.2 * noise.noise(Vector((p0.x * 0.03, p0.y * 0.03, 2.0)))
        q = [p0 + nrm * 0.0, p1 + nrm * 0.0, p1 - nrm * th, p0 - nrm * th]
        verts = [(v.x, v.y, z0) for v in q] + [(v.x, v.y, top) for v in q]
        b.add(verts, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    wall = b.obj("Acropolis south wall", "Landscape", [mat_stone("Limestone ashlar", (0.56, 0.52, 0.45))])

    # Parthenon (438/432 BC), simplified: stepped krepidoma, 8 x 17 Doric columns on a
    # 69.5 x 30.9 m stylobate, architrave/frieze/cornice, low-pitched roof (~15 deg) with a
    # recessed pediment under raking cornices at each short end
    marble = mat_plain("Pentelic marble", (0.53, 0.48, 0.41), rough=0.5, sss=0.0, bump=0.2, bump_scale=3.0)
    tiles = mat_plain("Marble roof tiles", (0.47, 0.43, 0.37), rough=0.6, bump=0.3, bump_scale=6.0)
    cx, cy = -59.0, 146.0
    z0 = terrain_h(cx, cy) + 0.1
    L, W = 69.5, 30.9
    p = Builder()
    for i, (dl, z1) in enumerate(((1.4, 0.55), (0.7, 1.1), (0.0, 1.65))):     # three steps, 0.55 m each
        p.box(cx - L / 2 - dl, cx + L / 2 + dl, cy - W / 2 - dl, cy + W / 2 + dl, z0 - (2.0 if i == 0 else 0.0) + (z1 - 0.55 if i else 0.0), z0 + z1)
    zs = z0 + 1.65
    col_h = 10.43
    for i in range(17):
        for j in range(8):
            if 0 < i < 16 and 0 < j < 7:
                continue
            x = cx - L / 2 + 1.2 + i * (L - 2.4) / 16
            y = cy - W / 2 + 1.2 + j * (W - 2.4) / 7
            v, f = cylinder_geom(0.95, 0.0, col_h, 16, "Z", (x, y, zs), r1=0.75)
            p.add(v, f)
            p.box(x - 1.0, x + 1.0, y - 1.0, y + 1.0, zs + col_h - 0.35, zs + col_h)   # abacus
    p.box(cx - L / 2 + 5.5, cx + L / 2 - 5.5, cy - W / 2 + 5.0, cy + W / 2 - 5.0, zs, zs + col_h)   # cella
    ze = zs + col_h
    p.box(cx - L / 2 + 0.25, cx + L / 2 - 0.25, cy - W / 2 + 0.25, cy + W / 2 - 0.25, ze, ze + 1.35)  # architrave
    p.box(cx - L / 2 + 0.3, cx + L / 2 - 0.3, cy - W / 2 + 0.3, cy + W / 2 - 0.3, ze + 1.35, ze + 2.7)  # frieze
    p.box(cx - L / 2 - 0.2, cx + L / 2 + 0.2, cy - W / 2 - 0.2, cy + W / 2 + 0.2, ze + 2.7, ze + 3.3)  # cornice
    zc = ze + 3.3
    ridge = 4.1
    # tympanum: triangular prism set back 0.7 m from each end
    x0, x1 = cx - L / 2 + 0.7, cx + L / 2 - 0.7
    hw = W / 2 - 0.1
    v = [(x0, cy - hw, zc), (x0, cy + hw, zc), (x0, cy, zc + ridge - 0.45),
         (x1, cy - hw, zc), (x1, cy + hw, zc), (x1, cy, zc + ridge - 0.45)]
    p.add(v, [(0, 2, 1), (3, 4, 5), (0, 3, 5, 2), (2, 5, 4, 1), (0, 1, 4, 3)])
    parth_roof = Builder()
    # roof slopes as 0.45 m slabs running past the tympanum: their ends are the raking cornices
    for sgn in (-1, 1):
        e_out = (cy + sgn * (W / 2 + 0.35), zc - 0.05)
        top = (cy, zc + ridge)
        xa, xb = cx - L / 2 - 0.25, cx + L / 2 + 0.25
        vv = [(xa, e_out[0], e_out[1]), (xb, e_out[0], e_out[1]), (xb, top[0], top[1]), (xa, top[0], top[1]),
              (xa, e_out[0], e_out[1] - 0.45), (xb, e_out[0], e_out[1] - 0.45), (xb, top[0], top[1] - 0.45), (xa, top[0], top[1] - 0.45)]
        ff = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
        if sgn > 0:
            ff = [tuple(reversed(fc)) for fc in ff]
        parth_roof.add(vv, ff)
    parth_roof.obj("Parthenon roof (simplified)", "Landscape", [tiles])
    parth = p.obj("Parthenon (simplified)", "Landscape", [marble])
    return wall, parth


# ----------------------------------------------------------------------------
# the city: low courtyard houses with tiled roofs (soft background, under haze)
# ----------------------------------------------------------------------------
CITY_C = Vector(true_to_scene(*[600 * math.sin(math.radians(320)), 600 * math.cos(math.radians(320))]))


def in_city(x, y):
    """inside the Themistoclean circuit (approximated by an ellipse round the Agora area)"""
    d = Vector((x, y)) - CITY_C
    return (d.x / 1150.0) ** 2 + (d.y / 950.0) ** 2 < 1.0


def build_city():
    b = Builder()
    cols = []
    rr = random.Random(431)
    cell = 15.0
    xs = range(int(-1500 / cell), int(1500 / cell))
    for i in xs:
        for j in xs:
            x = i * cell + rr.uniform(-3, 3)
            y = j * cell + rr.uniform(-3, 3)
            rr_keep = rr.random()
            r = (Vector((x, y)) - ORCH_C).length
            if r < 95:
                continue
            if acropolis_h(x, y) > 0.5:
                continue
            if abs(x) < 55 and -165 < y < 25:          # sanctuary of Dionysus, theatre
                continue
            if 32 < x < 115 and -20 < y < 75:          # Odeion of Pericles site: left empty (see notes)
                continue
            z = terrain_h(x, y)
            if z < -80:
                continue
            g = abs(terrain_h(x + 4, y) - terrain_h(x - 4, y)) + abs(terrain_h(x, y + 4) - terrain_h(x, y - 4))
            if g > 2.4:
                continue
            city = in_city(x, y)
            if not city and rr_keep > 0.05:
                continue
            if city and rr_keep > 0.62:
                continue
            w, d = rr.uniform(8, 14), rr.uniform(8, 13)
            h = rr.uniform(3.6, 5.8)
            ang = math.radians(rr.uniform(-12, 12)) + (math.radians(15) if rr.random() < 0.3 else 0)
            xd = (math.cos(ang), math.sin(ang))
            c = (x, y, z - 1.0 + (h + 1.0) / 2)
            obox(b, c, xd, w, d, h + 1.0, 0)
            # low gable roof (pitch ~ 15 deg), ridge along the long side
            ex = Vector((xd[0], xd[1], 0))
            ey = Vector((-xd[1], xd[0], 0))
            if d > w:
                ex, ey, w, d = ey, ex, d, w
            zt = z + h
            rh = d / 2 * 0.27
            o = Vector((x, y, zt))
            hw, hd = w / 2 + 0.35, d / 2 + 0.35
            v = [o - ex * hw - ey * hd, o + ex * hw - ey * hd, o + ex * hw + ey * hd, o - ex * hw + ey * hd,
                 o - ex * hw + Vector((0, 0, rh)), o + ex * hw + Vector((0, 0, rh))]
            b.add(v, [(0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5)], 1)
            tone = rr.random()
            cols += [tone] * 6 + [tone] * 4
    ob = b.obj("City houses", "Landscape", [mat_city_wall(), mat_city_roof()])
    attr = ob.data.attributes.new("tone", "FLOAT", "FACE")
    attr.data.foreach_set("value", cols)
    return ob


def _mat_toned(name, c0, c1, rough):
    m = new_mat(name)
    nt = NT(m)
    at = nt.n("ShaderNodeAttribute", attribute_name="tone")
    mix = nt.n("ShaderNodeMix", data_type="RGBA")
    mix.inputs["A"].default_value = (*c0, 1)
    mix.inputs["B"].default_value = (*c1, 1)
    nt.l(at.outputs["Fac"], mix.inputs["Factor"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=rough)
    nt.l(mix.outputs["Result"], bs.inputs["Base Color"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def mat_city_wall():
    return _mat_toned("House walls (plastered mudbrick)", (0.20, 0.17, 0.13), (0.34, 0.30, 0.24), 0.9)


def mat_city_roof():
    return _mat_toned("House roofs (terracotta)", (0.34, 0.15, 0.08), (0.50, 0.26, 0.14), 0.8)


# ----------------------------------------------------------------------------
# vegetation: CC0 Poly Haven plants, scattered with Geometry Nodes instancing
# ----------------------------------------------------------------------------
def import_gltf_variants(mod, olive=False):
    path = os.path.join(ASSETS, "models", mod, mod + "_1k.gltf")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = sorted([o for o in bpy.data.objects if o not in before], key=lambda o: o.name)
    cl = coll("VEG " + mod + (" (olive stand-in)" if olive else ""), COLL["Library"])
    out = []
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
            continue
        for c in o.users_collection:
            c.objects.unlink(o)
        cl.objects.link(o)
        o.location = (0, 0, 0)
        o.rotation_euler = (0, 0, 0)
        out.append(o)
    # leaves/twigs: wire in the separate alpha map (the glTF uses the JPG diffuse, which has
    # no alpha), add a little translucency, and tint: olive stand-ins get the silvery
    # grey-green of olive foliage
    alpha_img = image(os.path.join(ASSETS, "models", mod, "textures", mod + "_alpha_1k.png"), noncolor=True)
    for o in out:
        for m in o.data.materials:
            if m is None or not m.use_nodes or "_tinted" in m.name:
                continue
            nt = m.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None or not bsdf.inputs["Base Color"].links:
                continue
            src = bsdf.inputs["Base Color"].links[0].from_socket
            hs = nt.nodes.new("ShaderNodeHueSaturation")
            card = ("leaves" in m.name) or ("twigs" in m.name)
            if "leaves" in m.name:
                if olive:
                    hs.inputs["Hue"].default_value = 0.52
                    hs.inputs["Saturation"].default_value = 0.45
                    hs.inputs["Value"].default_value = 1.5
                else:
                    hs.inputs["Hue"].default_value = 0.5
                    hs.inputs["Saturation"].default_value = 0.85
                    hs.inputs["Value"].default_value = 1.15
            else:
                hs.inputs["Saturation"].default_value = 0.7
            nt.links.new(src, hs.inputs["Color"])
            nt.links.new(hs.outputs[0], bsdf.inputs["Base Color"])
            if card:
                at = nt.nodes.new("ShaderNodeTexImage")
                at.image = alpha_img
                for l in list(bsdf.inputs["Alpha"].links):
                    nt.links.remove(l)
                nt.links.new(at.outputs["Color"], bsdf.inputs["Alpha"])
            if "leaves" in m.name:
                out_node = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
                tl = nt.nodes.new("ShaderNodeBsdfTranslucent")
                nt.links.new(hs.outputs[0], tl.inputs["Color"])
                mx = nt.nodes.new("ShaderNodeMixShader")
                mx.inputs["Fac"].default_value = 0.25
                nt.links.new(bsdf.outputs[0], mx.inputs[1])
                nt.links.new(tl.outputs[0], mx.inputs[2])
                # translucency must respect the cut-out as well
                tr = nt.nodes.new("ShaderNodeBsdfTransparent")
                mx2 = nt.nodes.new("ShaderNodeMixShader")
                nt.links.new(at.outputs["Color"], mx2.inputs["Fac"])
                nt.links.new(tr.outputs[0], mx2.inputs[1])
                nt.links.new(mx.outputs[0], mx2.inputs[2])
                nt.links.new(mx2.outputs[0], out_node.inputs["Surface"])
            m.name += "_tinted"
    return cl, out


def scatter(name, coll_src, points, cname="Vegetation"):
    """points: list of (x, y, z, rot_z, scale, variant_index)"""
    me = bpy.data.meshes.new(name + " points")
    me.from_pydata([(p[0], p[1], p[2]) for p in points], [], [])
    a_rot = me.attributes.new("rotz", "FLOAT", "POINT")
    a_rot.data.foreach_set("value", [p[3] for p in points])
    a_sc = me.attributes.new("scl", "FLOAT", "POINT")
    a_sc.data.foreach_set("value", [p[4] for p in points])
    a_ix = me.attributes.new("vix", "INT", "POINT")
    a_ix.data.foreach_set("value", [p[5] for p in points])
    ob = bpy.data.objects.new(name, me)
    COLL[cname].objects.link(ob)
    ng = bpy.data.node_groups.new(name + " GN", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    ci = ng.nodes.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = coll_src
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    ci.transform_space = "ORIGINAL"
    iop = ng.nodes.new("GeometryNodeInstanceOnPoints")
    na_r = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na_r.data_type = "FLOAT"
    na_r.inputs["Name"].default_value = "rotz"
    na_s = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na_s.data_type = "FLOAT"
    na_s.inputs["Name"].default_value = "scl"
    na_i = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na_i.data_type = "INT"
    na_i.inputs["Name"].default_value = "vix"
    cmb = ng.nodes.new("ShaderNodeCombineXYZ")
    e2r = ng.nodes.new("FunctionNodeEulerToRotation")
    L = ng.links
    L.new(gi.outputs[0], iop.inputs["Points"])
    L.new(ci.outputs[0], iop.inputs["Instance"])
    iop.inputs["Pick Instance"].default_value = True
    L.new(na_i.outputs["Attribute"], iop.inputs["Instance Index"])
    L.new(na_r.outputs["Attribute"], cmb.inputs["Z"])
    L.new(cmb.outputs[0], e2r.inputs[0])
    L.new(e2r.outputs[0], iop.inputs["Rotation"])
    L.new(na_s.outputs["Attribute"], iop.inputs["Scale"])
    L.new(iop.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("Scatter", "NODES")
    mod.node_group = ng
    return ob


def veg_ok(x, y, z):
    """where plants may grow"""
    if flat_w(x, y) > 0.2:
        return False
    if theatron_w(x, y) > 0.05:
        return False
    if abs(x) < 9 and -8 < y < 2:
        return False
    g = math.hypot(terrain_h(x + 1, y) - terrain_h(x - 1, y), terrain_h(x, y + 1) - terrain_h(x, y - 1)) / 2
    if g > 0.9:
        return False                               # bare rock face
    if acropolis_h(x, y) >= 59.5:
        return False                               # plateau: built over, not modelled
    return True


def build_vegetation():
    shrubs_c, shrubs = import_gltf_variants("searsia_lucida")
    scrub_c, scrub = import_gltf_variants("wild_rooibos_bush")
    olive_c, olives = import_gltf_variants("searsia_burchellii", olive=True)
    rr = random.Random(458)    # 458 BC, Oresteia
    pts_shrub, pts_scrub, pts_olive = [], [], []

    def jitter_grid(x0, x1, y0, y1, cell):
        y = y0
        while y < y1:
            x = x0
            while x < x1:
                yield x + rr.uniform(0, cell), y + rr.uniform(0, cell)
                x += cell
            y += cell

    # maquis on the slopes round the theatre and up to the rock
    for (x, y) in jitter_grid(-170, 170, -60, 135, 2.6):
        z = terrain_h(x, y)
        if not veg_ok(x, y, z):
            continue
        r = (Vector((x, y)) - ORCH_C).length
        dens = 0.55 if r < 120 else 0.28
        if 32 < x < 115 and -20 < y < 75:
            dens *= 0.5
        n = noise.noise(Vector((x * 0.06, y * 0.06, 2.0)))
        if rr.random() > dens * (0.6 + 1.2 * max(0.0, n + 0.3)):
            continue
        if rr.random() < 0.55:
            pts_scrub.append((x, y, z - 0.05, rr.uniform(0, 6.28), rr.uniform(0.9, 1.6), rr.randrange(len(scrub))))
        else:
            pts_shrub.append((x, y, z - 0.08, rr.uniform(0, 6.28), rr.uniform(0.55, 1.1), rr.randrange(len(shrubs))))
    # olive groves: clusters on the lower slopes and in the sanctuary
    centres = [(-48, 8), (-62, -18), (-90, 30), (52, 0), (70, 30), (95, 10), (-30, -60), (28, -75), (-140, 10),
               (130, 40), (-110, -40), (110, -45), (0, -95), (-25, -125), (30, -140), (0, -150), (-40, -95), (40, -110)]
    for (cx, cy) in centres:
        for k in range(rr.randint(6, 14)):
            x, y = cx + rr.gauss(0, 11), cy + rr.gauss(0, 9)
            z = terrain_h(x, y)
            if not veg_ok(x, y, z) and not (abs(x) < 55 and -165 < y < -14):
                continue
            if abs(x) < 16 and y > -20:
                continue
            pts_olive.append((x, y, z - 0.1, rr.uniform(0, 6.28), rr.uniform(1.05, 1.5), rr.randrange(len(olives))))
    # a few trees in the town and beyond the walls (farm groves)
    for (x, y) in jitter_grid(-1200, 1200, -1300, 1100, 26.0):
        r = (Vector((x, y)) - ORCH_C).length
        if r < 140:
            continue
        z = terrain_h(x, y)
        if z < -80 or acropolis_h(x, y) > 0.5:
            continue
        p = 0.16 if in_city(x, y) else 0.22
        if rr.random() < p:
            pts_olive.append((x, y, z - 0.1, rr.uniform(0, 6.28), rr.uniform(1.0, 1.5), rr.randrange(len(olives))))
    scatter("Maquis shrubs", shrubs_c, pts_shrub)
    scatter("Low scrub", scrub_c, pts_scrub)
    scatter("Olive trees (stand-in)", olive_c, pts_olive)
    print("vegetation:", len(pts_shrub), "shrubs,", len(pts_scrub), "scrub,", len(pts_olive), "trees")


# ----------------------------------------------------------------------------
# skene (wooden stage building)
# ----------------------------------------------------------------------------
SKENE_PARTS = []   # architecture objects that the section cutters slice


def build_skene():
    """Wooden skene. Every object is a set of closed boxes that neither touch nor
    overlap (2 mm gaps, hidden behind posts), so the exact boolean section cuts stay clean."""
    hw, d, h, t = SKENE_W / 2, SKENE_D, SKENE_H, WALL_T
    dx = DOOR_W / 2
    post = 0.26          # post section
    proud = 0.05         # posts and rails stand proud of the boarding
    g = 0.002            # gap between neighbouring boxes of one object

    def cut_part(builder, name, mat, bevel=0.0):
        ob = builder.obj(name, "Skene", [mat])
        if bevel:
            add_bevel(ob, bevel, 2)
        SKENE_PARTS.append(ob)
        return ob

    # --- boarding: facade panels, side walls, back wall
    b = Builder()
    y0, y1 = -t, -proud
    xs = [-hw, -4.0, -2.0, -dx, dx, 2.0, 4.0, hw]
    for i in range(len(xs) - 1):
        a, c = xs[i] + g, xs[i + 1] - g
        if abs(xs[i] + dx) < 1e-6:
            b.box(a, c, y0, y1, DOOR_H + g, h - 0.02)          # above the door
        else:
            b.box(a, c, y0, y1, 0.0, h - 0.02)
    b.box(-hw, -hw + t - 0.05, -d + t - 0.05 + g, -t - g, 0, h - 0.02)
    b.box(hw - t + 0.05, hw, -d + t - 0.05 + g, -t - g, 0, h - 0.02)
    b.box(-hw + g, hw - g, -d, -d + t - 0.05, 0, h - 0.02)
    cut_part(b, "Skene boarding", MAT["boards"])

    # --- posts (facade and back corners)
    p = Builder()
    for x in (-hw + post / 2, -4.0, -2.0, 2.0, 4.0, hw - post / 2):
        p.box(x - post / 2, x + post / 2, -t - 0.02, 0.0, 0.0, h - 0.25)
    for x in (-hw + post / 2, hw - post / 2):
        p.box(x - post / 2, x + post / 2, -d - 0.02, -d + post - 0.02, 0.0, h - 0.25)
    cut_part(p, "Skene posts", MAT["timber"], 0.015)

    # --- rails: top rail across, bottom rail either side of the door
    r = Builder()
    jp = 0.24
    r.box(-hw - 0.02, hw + 0.02, -t - 0.04, 0.025, h - 0.55, h - 0.27)
    for sgn in (-1, 1):
        a, c = sgn * (dx + jp + g), sgn * (hw + 0.02)
        r.box(min(a, c), max(a, c), -t - 0.04, 0.025, 0.38, 0.60)
    cut_part(r, "Skene rails", MAT["timber"], 0.012)

    # --- door frame: jambs, lintel, worn threshold
    df = Builder()
    for sgn in (-1, 1):
        df.box(sgn * dx, sgn * (dx + jp), -t - 0.03, 0.01, 0.0, DOOR_H)
    df.box(-dx - jp - 0.15, dx + jp + 0.15, -t - 0.03, 0.035, DOOR_H + g, DOOR_H + 0.32)
    df.box(-dx + g, dx - g, -t, 0.0, -0.05, 0.012)
    cut_part(df, "Skene door frame", MAT["timber"], 0.015)

    # --- roof deck (actors could appear up here), joists, mid beam, interior posts
    rf = Builder()
    rf.box(-hw - 0.08, hw + 0.08, -d - 0.08, 0.10, h - 0.12, h)
    cut_part(rf, "Skene roof", MAT["roof"])
    j = Builder()
    xj = -hw + 0.3
    while xj < hw - 0.2:
        j.box(xj - 0.07, xj + 0.07, -d + 0.05, -0.02, h - 0.34, h - 0.12 - g)
        xj += 0.75
    cut_part(j, "Skene joists", MAT["timber_in"], 0.01)
    bm_ = Builder()
    bm_.box(-hw + 0.1, hw - 0.1, -d * 0.5 - 0.12, -d * 0.5 + 0.12, h - 0.58, h - 0.34 - g)
    cut_part(bm_, "Skene mid beam", MAT["timber_in"], 0.01)
    ip = Builder()
    for x in (-4.0, 4.0):
        ip.box(x - 0.11, x + 0.11, -d * 0.5 - 0.11, -d * 0.5 + 0.11, 0.0, h - 0.58 - g)
    cut_part(ip, "Skene interior posts", MAT["timber_in"], 0.01)


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
            b.box(-side * 0.08, -side * (w - 0.08), -0.045, -0.002, zc - 0.09, zc + 0.09, 0)
        leaf = b.obj(f"Door leaf {'E' if side > 0 else 'W'}", "Skene", [MAT["leaf"]])
        add_bevel(leaf, 0.006, 1)
        leaf.parent = hinge
        # iron ring pull on the inner face, near the meeting edge (torus turned upright)
        ring_v, ring_f = torus_geom(0.06, 0.008, 20, 8)
        ring_v = [(vx - side * (w - 0.18), vz - 0.06, vy + 1.15) for (vx, vy, vz) in ring_v]
        ring = mesh_obj(f"Door ring {'E' if side > 0 else 'W'}", ring_v, ring_f, "Skene", smooth=True, mat=MAT["iron"])
        ring.parent = hinge
        if side < 0:                      # the W leaf lies on the cut-away side
            SKENE_PARTS.extend([leaf, ring])
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
# the ekkyklema: platform, wheels, rig
# ----------------------------------------------------------------------------
PLAT = {}


def build_platform():
    ctrl = empty("Platform ctrl", (0, 0, 0), "Platform", 0.8, "ARROWS")
    PLAT["ctrl"] = ctrl
    hw, hd, H = PLAT_W / 2, PLAT_D / 2, PLAT_H
    bt = 0.055                                   # deck board thickness
    b = Builder()
    nb = 8
    rr = random.Random(96)
    for i in range(nb):
        y0 = -hd + i * PLAT_D / nb + 0.005
        y1 = -hd + (i + 1) * PLAT_D / nb - 0.005
        dz = rr.uniform(-0.003, 0.003)
        b.box(-hw, hw, y0, y1, H - bt + dz, H + dz)
    deck = b.obj("Platform deck", "Platform", [MAT["deck"]])
    add_bevel(deck, 0.006, 2)
    f = Builder()
    for s in (-1, 1):                            # two main runners along the rolling direction
        f.box(s * 0.86, s * 1.02, -hd + 0.03, hd - 0.03, 0.135, H - bt)
    for s in (-1, 1):                            # front and back rails
        f.box(-hw + 0.02, hw - 0.02, s * (hd - 0.075), s * (hd - 0.005), 0.15, H - bt)
    f.box(-0.86, 0.86, -0.06, 0.06, 0.16, H - bt)    # middle cross-member
    for s in (-1, 1):                            # axle blocks
        for ya in (-0.55, 0.55):
            f.box(s * 0.84, s * 1.05, ya - 0.08, ya + 0.08, 0.075, 0.14)
    frame = f.obj("Platform frame", "Platform", [MAT["frame"]])
    add_bevel(frame, 0.008, 2)
    ax = Builder()
    for ya in (-0.55, 0.55):
        v, fc = cylinder_geom(0.022, -1.16, 1.16, 12, "X", (0, ya, WHEEL_R))
        ax.add(v, fc)
    axles = ax.obj("Platform axles", "Platform", [MAT["iron"]])
    set_smooth(axles)
    for o in (deck, frame, axles):
        o.parent = ctrl
    wheels = []
    for s in (-1, 1):
        for ya in (-0.55, 0.55):
            wb = Builder()
            v, fc = cylinder_geom(WHEEL_R, -0.03, 0.03, 36, "X")
            wb.add(v, fc)
            v, fc = cylinder_geom(0.045, -0.045, 0.045, 16, "X")    # hub
            wb.add(v, fc)
            # three-plank solid wheel: two shallow grooves
            w = wb.obj(f"Wheel {'E' if s > 0 else 'W'}{'F' if ya > 0 else 'B'}", "Platform", [MAT["frame"]])
            add_bevel(w, 0.006, 2)
            w.location = (s * 1.115, ya, WHEEL_R)
            w.parent = ctrl
            wheels.append(w)
    PLAT["wheels"] = wheels
    return ctrl


def drive_wheels():
    ctrl = PLAT["ctrl"]
    for w in PLAT["wheels"]:
        fc = w.driver_add("rotation_euler", 0)
        drv = fc.driver
        drv.type = "SCRIPTED"
        var = drv.variables.new()
        var.name = "y"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "OBJECT"
        var.targets[0].id = ctrl
        var.targets[0].data_path = "location[1]"
        drv.expression = f"-(y - ({PLAT_Y_IN:.4f})) / {WHEEL_R}"


# ----------------------------------------------------------------------------
# mannequin figures: smooth segments, hierarchical FK, aim + two-bone IK
# ----------------------------------------------------------------------------
SEG_DEFS = [
    # name, parent, joint position (rest, 1.76 m figure facing +Y, right = +X), rest dir, length
    ("pelvis", None, (0, 0, 0.98), (0, 0, 1), 0.10),
    ("abdomen", "pelvis", (0, 0, 0.98), (0, 0, 1), 0.22),
    ("chest", "abdomen", (0, 0, 1.20), (0, 0, 1), 0.27),
    ("neck", "chest", (0, 0, 1.47), (0, 0, 1), 0.09),
    ("head", "neck", (0, 0, 1.56), (0, 0, 1), 0.21),
    ("upperarm.R", "chest", (0.185, 0, 1.43), (0, 0, -1), 0.29),
    ("forearm.R", "upperarm.R", (0.185, 0, 1.14), (0, 0, -1), 0.255),
    ("hand.R", "forearm.R", (0.185, 0, 0.885), (0, 0, -1), 0.18),
    ("upperarm.L", "chest", (-0.185, 0, 1.43), (0, 0, -1), 0.29),
    ("forearm.L", "upperarm.L", (-0.185, 0, 1.14), (0, 0, -1), 0.255),
    ("hand.L", "forearm.L", (-0.185, 0, 0.885), (0, 0, -1), 0.18),
    ("thigh.R", "pelvis", (0.095, 0, 0.93), (0, 0, -1), 0.43),
    ("shin.R", "thigh.R", (0.095, 0, 0.50), (0, 0, -1), 0.42),
    ("foot.R", "shin.R", (0.095, 0, 0.08), (0, 1, 0), 0.20),
    ("thigh.L", "pelvis", (-0.095, 0, 0.93), (0, 0, -1), 0.43),
    ("shin.L", "thigh.L", (-0.095, 0, 0.50), (0, 0, -1), 0.42),
    ("foot.L", "shin.L", (-0.095, 0, 0.08), (0, 1, 0), 0.20),
]

# radius profiles: (t along the segment 0..1, radius across A, radius across B)
# A/B = X/Y for vertical segments, X/Z for feet. t outside 0..1 is allowed.
SEG_SHAPES = {
    "pelvis": dict(t=(-1.3, 0.7), prof=[(-1.3, 0.13, 0.09), (-0.9, 0.172, 0.118), (-0.3, 0.172, 0.112), (0.3, 0.158, 0.104), (0.7, 0.145, 0.10)], caps=(1, 0)),
    "abdomen": dict(t=(0.0, 1.0), prof=[(0.0, 0.146, 0.101), (0.5, 0.136, 0.100), (1.0, 0.148, 0.106)], caps=(0, 0)),
    "chest": dict(t=(0.0, 1.0), prof=[(0.0, 0.148, 0.106), (0.35, 0.162, 0.118), (0.7, 0.168, 0.112), (0.88, 0.15, 0.095), (1.0, 0.07, 0.06)], caps=(0, 1)),
    "neck": dict(t=(-0.2, 1.0), prof=[(-0.2, 0.056, 0.056), (1.0, 0.05, 0.052)], caps=(0, 0)),
    "head": dict(t=(-0.05, 1.0), prof=[(-0.05, 0.052, 0.06), (0.2, 0.072, 0.088), (0.5, 0.08, 0.098), (0.8, 0.072, 0.09), (1.0, 0.035, 0.045)], caps=(1, 1), off=(0, 0.012, 0)),
    "upperarm": dict(t=(0.0, 1.0), prof=[(0.0, 0.052, 0.054), (0.3, 0.05, 0.05), (1.0, 0.039, 0.04)], caps=(1, 1)),
    "forearm": dict(t=(0.0, 1.0), prof=[(0.0, 0.039, 0.04), (0.25, 0.042, 0.04), (1.0, 0.026, 0.03)], caps=(1, 1)),
    "hand": dict(t=(0.0, 1.0), prof=[(0.0, 0.018, 0.034), (0.4, 0.019, 0.045), (0.8, 0.016, 0.042), (1.0, 0.012, 0.03)], caps=(1, 1)),
    "thigh": dict(t=(0.0, 1.0), prof=[(0.0, 0.082, 0.086), (0.3, 0.078, 0.08), (1.0, 0.052, 0.054)], caps=(1, 1)),
    "shin": dict(t=(0.0, 1.0), prof=[(0.0, 0.052, 0.054), (0.3, 0.054, 0.058), (0.75, 0.04, 0.042), (1.0, 0.032, 0.034)], caps=(1, 1)),
    "foot": dict(t=(-0.3, 1.0), prof=[(-0.3, 0.03, 0.035), (0.0, 0.038, 0.045), (0.5, 0.045, 0.032), (0.85, 0.042, 0.02), (1.0, 0.03, 0.012)], caps=(1, 1), off=(0, 0, -0.045)),
}


def _interp(prof, t):
    if t <= prof[0][0]:
        return prof[0][1], prof[0][2]
    for (t0, a0, b0), (t1, a1, b1) in zip(prof, prof[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)
            return a0 + (a1 - a0) * u, b0 + (b1 - b0) * u
    return prof[-1][1], prof[-1][2]


def lathe_geom(axis, length, shape, s=1.0, n_around=20, n_along=14, fold=None):
    """surface of revolution along `axis` (unit, local), elliptical sections, rounded caps"""
    axis = Vector(axis)
    if abs(axis.z) > 0.5:
        A, B = Vector((1, 0, 0)), Vector((0, 1, 0))
    else:
        A, B = Vector((1, 0, 0)), Vector((0, 0, 1))
    t0, t1 = shape["t"]
    prof = shape["prof"]
    off = Vector(shape.get("off", (0, 0, 0))) * s
    caps = shape.get("caps", (1, 1))
    rings = []
    # bottom cap (at t0, pointing backwards along the axis)
    ra, rb = _interp(prof, t0)
    if caps[0]:
        for k in range(5, 0, -1):
            ph = (math.pi / 2) * k / 5
            rings.append((t0 * length - math.sin(ph) * ra * 0.9, ra * math.cos(ph), rb * math.cos(ph)))
    for i in range(n_along + 1):
        t = t0 + (t1 - t0) * i / n_along
        ra, rb = _interp(prof, t)
        rings.append((t * length, ra, rb))
    ra, rb = _interp(prof, t1)
    if caps[1]:
        for k in range(1, 6):
            ph = (math.pi / 2) * k / 5
            rings.append((t1 * length + math.sin(ph) * ra * 0.9, ra * math.cos(ph), rb * math.cos(ph)))
    verts, faces = [], []
    for (z, ra, rb) in rings:
        for k in range(n_around):
            a = 2 * math.pi * k / n_around
            ca, sa = math.cos(a), math.sin(a)
            rf = 1.0
            if fold:
                rf = fold(a, z)
            p = axis * z * s + (A * (ra * ca) + B * (rb * sa)) * rf * s + off
            verts.append(p)
    nr = len(rings)
    for i in range(nr - 1):
        for k in range(n_around):
            a = i * n_around + k
            b = i * n_around + (k + 1) % n_around
            faces.append((a, b, b + n_around, a + n_around))
    # close the ends
    if True:
        c0 = len(verts)
        verts.append(axis * rings[0][0] * s + off)
        c1 = len(verts)
        verts.append(axis * rings[-1][0] * s + off)
        for k in range(n_around):
            faces.append((c0, (k + 1) % n_around, k))
            last = (nr - 1) * n_around
            faces.append((c1, last + k, last + (k + 1) % n_around))
    # keep normals outward: the (A, B, axis) frame is left-handed for -Z and +Y axes
    if A.cross(B).dot(axis) < 0:
        faces = [tuple(reversed(fc)) for fc in faces]
    return verts, faces


def capsule_geom(p0, p1, r0, r1, n=12, rings=4):
    """capsule between two points (outward normals), for small parts such as thumbs"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    ax = d.normalized()
    tmp = Vector((1, 0, 0)) if abs(ax.x) < 0.9 else Vector((0, 1, 0))
    u = ax.cross(tmp).normalized()
    w = ax.cross(u)
    prof = []
    for k in range(rings, 0, -1):
        ph = (math.pi / 2) * k / rings
        prof.append((-math.sin(ph) * r0, r0 * math.cos(ph)))
    prof += [(0.0, r0), (L, r1)]
    for k in range(1, rings + 1):
        ph = (math.pi / 2) * k / rings
        prof.append((L + math.sin(ph) * r1, r1 * math.cos(ph)))
    verts, faces = [], []
    for (t, r) in prof:
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append(p0 + ax * t + (u * math.cos(a) + w * math.sin(a)) * r)
    for i in range(len(prof) - 1):
        for k in range(n):
            a0, b0 = i * n + k, i * n + (k + 1) % n
            faces.append((a0, b0, b0 + n, a0 + n))
    return verts, faces


class Seg:
    pass


def ik2(p0, pt, l1, l2, pole):
    """two-bone IK: directions of bone 1 and bone 2 from p0 toward target pt, bending toward pole"""
    d = pt - p0
    dist = max(abs(l1 - l2) + 1e-4, min(l1 + l2 - 1e-4, d.length))
    dn = d.normalized()
    ca = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    a = math.acos(max(-1.0, min(1.0, ca)))
    pp = pole - dn * pole.dot(dn)
    if pp.length < 1e-6:
        pp = Vector((0, 1, 0)) - dn * dn.y
    pp.normalize()
    d1 = dn * math.cos(a) + pp * math.sin(a)
    mid = p0 + d1 * l1
    d2 = (p0 + dn * dist - mid).normalized()
    return d1, d2


class Figure:
    """jointed mannequin: one smooth mesh per segment, parented in a hierarchy, posed
    by giving world-space directions for segments (FK aim) and solving limbs with ik2."""

    def __init__(self, name, height=1.76, skin=None, parts=None, cname="Figures", head_mesh=True):
        self.name = name
        self.s = height / 1.76
        self.seg = {}
        self.order = []
        self.local = {}
        skin = skin or MAT["skin"]
        for (sn, parent, joint, rdir, length) in SEG_DEFS:
            sg = Seg()
            sg.name, sg.parent = sn, parent
            sg.joint = Vector(joint) * self.s
            sg.rest_dir = Vector(rdir)
            sg.front = Vector((0, 0, 1)) if sn.startswith("foot") else Vector((0, 1, 0))
            sg.length = length * self.s
            base = sn.split(".")[0]
            shape = SEG_SHAPES[base]
            if sn == "head" and not head_mesh:
                verts, faces = [], []
            else:
                verts, faces = lathe_geom(sg.rest_dir, length, shape, self.s)
            if base == "hand":
                # a thumb on the front edge of the hand, angled across the palm
                sg_x = 1.0 if sn.endswith(".R") else -1.0
                p0 = Vector((-0.004 * sg_x, 0.030, -0.030)) * self.s
                p1 = p0 + Vector((-0.012 * sg_x, 0.022, -0.050)) * self.s
                tv, tf = capsule_geom(p0, p1, 0.0125 * self.s, 0.0095 * self.s, 10, 3)
                off = len(verts)
                verts = list(verts) + tv
                faces = list(faces) + [tuple(i + off for i in fc) for fc in tf]
            ob = mesh_obj(f"{name} {sn}", verts, faces, cname, smooth=True, mat=skin)
            if verts:
                add_subsurf(ob, 1, 1)
            ob.rotation_mode = "QUATERNION"
            sg.obj = ob
            self.seg[sn] = sg
            self.order.append(sn)
        for sn in self.order:
            sg = self.seg[sn]
            if sg.parent:
                p = self.seg[sg.parent]
                sg.offset = sg.joint - p.joint
                sg.obj.parent = p.obj
                sg.obj.matrix_parent_inverse = Matrix.Identity(4)
                sg.obj.location = sg.offset
            else:
                sg.offset = Vector((0, 0, 0))
                sg.obj.location = sg.joint
        self.root = self.seg["pelvis"].obj
        self.root_loc = self.seg["pelvis"].joint.copy()
        self.root_q = Quaternion()

    # --- posing -------------------------------------------------------------
    def solve(self, root_loc, root_q, dirs, fronts=None):
        fronts = fronts or {}
        W, P = {}, {}
        for sn in self.order:
            sg = self.seg[sn]
            if sg.parent is None:
                W[sn], P[sn] = root_q, Vector(root_loc)
                continue
            pq = W[sg.parent]
            P[sn] = P[sg.parent] + pq @ sg.offset
            q = Quaternion()
            if sn in dirs:
                dl = (pq.inverted() @ Vector(dirs[sn])).normalized()
                q = sg.rest_dir.rotation_difference(dl)
                if sn in fronts:
                    fw = Vector(fronts[sn])
                    dw = (pq @ dl).normalized()
                    cur = (pq @ q) @ sg.front
                    cur = (cur - dw * cur.dot(dw))
                    want = (fw - dw * fw.dot(dw))
                    if cur.length > 1e-6 and want.length > 1e-6:
                        cur.normalize()
                        want.normalize()
                        ang = math.atan2(cur.cross(want).dot(dw), cur.dot(want))
                        q = Quaternion(dl, ang) @ q
            self.local[sn] = q
            W[sn] = pq @ q
        self.root_loc, self.root_q = Vector(root_loc), root_q
        self.W, self.P = W, P
        return W, P

    def joint(self, sn):
        return self.P[sn]

    def apply(self, frame=None):
        self.root.location = self.root_loc
        self.root.rotation_quaternion = self.root_q
        if frame is not None:
            self.root.keyframe_insert("location", frame=frame)
            self.root.keyframe_insert("rotation_quaternion", frame=frame)
        for sn in self.order:
            if sn == "pelvis":
                continue
            ob = self.seg[sn].obj
            ob.rotation_quaternion = self.local.get(sn, Quaternion())
            if frame is not None:
                ob.keyframe_insert("rotation_quaternion", frame=frame)

    def pose(self, root_loc, up, front, dirs=None, fronts=None, arms=None, legs=None, frame=None):
        """up/front: pelvis orientation. arms/legs: {side: (target, pole)} solved with IK
        (target = wrist / ankle position). dirs/fronts: extra FK aims."""
        dirs = dict(dirs or {})
        fronts = dict(fronts or {})
        rq = basis_quat(up, front)
        self.solve(root_loc, rq, dirs, fronts)
        for side, (tgt, pole) in (arms or {}).items():
            a, b = self.seg["upperarm." + side], self.seg["forearm." + side]
            d1, d2 = ik2(self.P["upperarm." + side], Vector(tgt), a.length, b.length, Vector(pole))
            dirs["upperarm." + side], dirs["forearm." + side] = d1, d2
        for side, (tgt, pole) in (legs or {}).items():
            a, b = self.seg["thigh." + side], self.seg["shin." + side]
            d1, d2 = ik2(self.P["thigh." + side], Vector(tgt), a.length, b.length, Vector(pole))
            dirs["thigh." + side], dirs["shin." + side] = d1, d2
        if arms or legs:
            self.solve(root_loc, rq, dirs, fronts)
        self.apply(frame)

    def objects(self):
        return [self.seg[s].obj for s in self.order]


def basis_quat(up, front):
    up = Vector(up).normalized()
    fr = Vector(front)
    fr = (fr - up * fr.dot(up)).normalized()
    right = fr.cross(up)
    m = Matrix((right, fr, up)).transposed()
    return m.to_quaternion()


# ----------------------------------------------------------------------------
# garments and masks
# ----------------------------------------------------------------------------
def folds(n_main=9, amp=0.06, seed=0, z0=0.0, z1=-1.0, grow=True):
    rr = random.Random(seed)
    ph = [rr.uniform(0, 6.28) for _ in range(4)]
    ks = [n_main, n_main * 2 + 1, 5, 3]

    def f(a, z):
        u = (z - z0) / (z1 - z0) if z1 != z0 else 0.0
        u = max(0.0, min(1.0, u))
        g = (0.25 + 0.75 * u) if grow else 1.0
        w = math.sin(ks[0] * a + ph[0] + 0.6 * math.sin(3 * a + ph[1] + 2 * u))
        w2 = math.sin(ks[1] * a + ph[2])
        w3 = math.sin(ks[2] * a + ph[3] + 1.5 * u)
        return 1.0 + amp * g * (0.6 * w + 0.2 * w2 + 0.25 * w3)
    return f


def garment(fig, parent, name, shape, axis=(0, 0, 1), mat=None, fold=None, solid=0.008, n_around=40, n_along=24,
            open_ends=(False, False)):
    s = fig.s
    length = 1.0
    verts, faces = lathe_geom(Vector(axis), length, shape, s, n_around=n_around, n_along=n_along, fold=fold)
    # optionally drop the end fans so a skirt is open at the hem
    nfan = 2 * n_around
    if open_ends[0] or open_ends[1]:
        body, fans = faces[:-nfan], faces[-nfan:]
        keep = [fans[i] for i in range(len(fans)) if not ((i % 2 == 0 and open_ends[0]) or (i % 2 == 1 and open_ends[1]))]
        faces = body + keep
    ob = mesh_obj(f"{fig.name} {name}", verts, faces, "Figures", smooth=True, mat=mat)
    p = fig.seg[parent].obj
    ob.parent = p
    ob.matrix_parent_inverse = Matrix.Identity(4)
    if solid:
        m = ob.modifiers.new("Solidify", "SOLIDIFY")
        m.thickness = solid
        m.offset = 1.0
    add_subsurf(ob, 1, 1)
    return ob


def build_mask(fig, skin_col, hair_col, beard=False, female=False, name="mask"):
    """tragic mask: a pale painted face standing proud of the head with a raised rim where it
    meets the wig/hood, deep dark eye holes and a wide open mouth"""
    s = fig.s
    head = fig.seg["head"].obj
    a, bz, c = 0.098 * s, 0.128 * s, 0.118 * s
    cz, cy = 0.105 * s, 0.014 * s
    R, S = 120, 160

    def face_e(ux, uz):
        return (ux / 0.80) ** 2 + ((uz + 0.10) / 0.82) ** 2

    verts, faces, mats = [], [], []
    uv = []
    for i in range(R + 1):
        th = math.pi * i / R
        for j in range(S):
            ph = 2 * math.pi * j / S
            ux, uy, uz = math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph), math.cos(th)
            k = 1.0
            e = face_e(ux, uz)
            if uy > 0.08 and e < 1.0:
                k += 0.035 + 0.03 * math.exp(-((e - 0.93) / 0.04) ** 2)       # mask proud of the head, raised rim
            x, y, z = a * ux * k, c * uy * k, bz * uz * k
            fr = max(0.0, uy)
            y -= c * 0.10 * fr ** 4                                         # flatter face
            y += c * 0.08 * math.exp(-((uz - 0.30) / 0.08) ** 2) * fr ** 2 * max(0.0, 1 - ux * ux * 1.6)   # brow ridge
            for ex in (-0.34, 0.34):                                       # deep eye sockets
                y -= c * 0.20 * math.exp(-(((ux - ex) / 0.16) ** 2 + ((uz - 0.13) / 0.10) ** 2)) * fr
            nose = math.exp(-(ux / 0.085) ** 2) * smoothstep(-0.27, -0.12, uz) * (1 - smoothstep(0.12, 0.3, uz))
            y += c * 0.22 * nose * fr
            y -= c * 0.17 * math.exp(-((ux / 0.28) ** 2 + ((uz + 0.42) / 0.13) ** 2)) * fr          # open mouth
            y += c * 0.05 * math.exp(-((ux / 0.3) ** 2 + ((uz + 0.70) / 0.12) ** 2)) * fr          # chin
            x *= 1.0 + 0.05 * math.exp(-((uz + 0.1) / 0.25) ** 2)                             # cheeks
            verts.append((x, y + cy, z + cz))
            uv.append((ux, uy, uz))
    for i in range(R):
        for j in range(S):
            a0 = i * S + j
            b0 = i * S + (j + 1) % S
            faces.append((a0, b0, b0 + S, a0 + S))
            th = math.pi * (i + 0.5) / R
            ph = 2 * math.pi * (j + 0.5) / S
            ux, uy, uz = math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph), math.cos(th)
            m = 4                                              # hood under the wig
            if uy > 0.08 and face_e(ux, uz) < 1.0:
                m = 0                                          # painted mask surface
                for ex in (-0.34, 0.34):
                    if ((ux - ex) / 0.165) ** 2 + ((uz - 0.13) / 0.095) ** 2 < 1.0:
                        m = 1                                  # eye holes
                if (ux / 0.24) ** 2 + ((uz + 0.42) / 0.11) ** 2 < 1.0:
                    m = 1                                      # mouth opening
                if m == 0:
                    if 0.24 < uz < 0.31 and 0.13 < abs(ux) < 0.56:
                        m = 2                                  # painted brows
                    elif (ux / 0.29) ** 2 + ((uz + 0.42) / 0.15) ** 2 < 1.0:
                        m = 3                                  # painted lips round the opening
            mats.append(m)
    m_skin = mat_plain(f"{fig.name} mask paint", skin_col, rough=0.55, bump=0.25, bump_scale=45, spec=0.4)
    m_hole = mat_plain("Mask openings", (0.004, 0.003, 0.003), rough=0.95, spec=0.1)
    m_brow = mat_plain("Mask paint dark", (0.04, 0.03, 0.022), rough=0.6)
    m_lip = mat_plain("Mask paint red", (0.45, 0.20, 0.14), rough=0.55)
    m_hood = mat_hair(f"{fig.name} hood", hair_col)
    ob = mesh_obj(f"{fig.name} {name}", verts, faces, "Figures", smooth=True)
    for mm in (m_skin, m_hole, m_brow, m_lip, m_hood):
        ob.data.materials.append(mm)
    ob.data.polygons.foreach_set("material_index", mats)
    ob.parent = head
    ob.matrix_parent_inverse = Matrix.Identity(4)
    add_subsurf(ob, 1, 1)
    # wig: a lumpy shell over the crown, sides and back, falling to the nape
    hv, hf = [], []
    R2, S2 = 24, 40
    for i in range(R2 + 1):
        th = math.pi * i / R2
        for j in range(S2):
            ph = 2 * math.pi * j / S2
            ux, uy, uz = math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph), math.cos(th)
            k = 1.07 + 0.035 * noise.noise(Vector((ux * 3, uy * 3, uz * 3 + 5.0)))
            k += 0.03 * math.sin(ph * 14 + uz * 6)
            x, y, z = a * ux * k * 1.03, c * uy * k, bz * uz * k
            if uy < 0.2 and uz < 0.1:          # hair falls lower at the back
                z -= bz * 0.25 * (0.1 - uz) * (0.2 - uy)
            hv.append((x, y + cy - 0.006 * s, z + cz + 0.008 * s))
    for i in range(R2):
        for j in range(S2):
            a0 = i * S2 + j
            b0 = i * S2 + (j + 1) % S2
            th = math.pi * (i + 0.5) / R2
            ph = 2 * math.pi * (j + 0.5) / S2
            ux, uy, uz = math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph), math.cos(th)
            face_zone = uy > 0.02 and (ux / 0.86) ** 2 + ((uz + 0.10) / 0.88) ** 2 < 1.0
            low_front = uz < -0.35 and uy > -0.3
            if face_zone or low_front or uz < -0.75:
                continue
            hf.append((a0, b0, b0 + S2, a0 + S2))
    m_hair = mat_hair(f"{fig.name} wig", hair_col)
    wig = mesh_obj(f"{fig.name} wig", hv, hf, "Figures", smooth=True, mat=m_hair)
    wig.parent = head
    wig.matrix_parent_inverse = Matrix.Identity(4)
    sm = wig.modifiers.new("Solidify", "SOLIDIFY")
    sm.thickness = 0.012 * s
    add_subsurf(wig, 1, 1)
    out = [ob, wig]
    if beard:
        bv, bf = [], []
        R3, S3 = 14, 24
        for i in range(R3 + 1):
            th = math.pi * i / R3
            for j in range(S3):
                ph = 2 * math.pi * j / S3
                ux, uy, uz = math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph), math.cos(th)
                k = 1.0 + 0.08 * noise.noise(Vector((ux * 4, uy * 4, uz * 4 + 9.0)))
                bv.append((0.075 * s * ux * k, 0.06 * s * uy * k + c * 0.62 + cy, 0.075 * s * uz * k + cz - bz * 0.62))
        for i in range(R3):
            for j in range(S3):
                a0 = i * S3 + j
                b0 = i * S3 + (j + 1) % S3
                bf.append((a0, b0, b0 + S3, a0 + S3))
        bd = mesh_obj(f"{fig.name} beard", bv, bf, "Figures", smooth=True, mat=m_hair)
        bd.parent = head
        bd.matrix_parent_inverse = Matrix.Identity(4)
        add_subsurf(bd, 1, 1)
        out.append(bd)
    return out


def mat_hair(name, color):
    m = new_mat(name)
    nt = NT(m)
    tc = nt.n("ShaderNodeTexCoord")
    wv = nt.n("ShaderNodeTexWave", in_Scale=60.0, in_Distortion=6.0, in_Detail=3.0)
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    nt.l(tc.outputs["Object"], wv.inputs[0])
    bp = nt.n("ShaderNodeBump", in_Strength=0.5, in_Distance=0.002)
    nt.l(wv.outputs["Fac"], bp.inputs["Height"])
    bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.7)
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Specular IOR Level"].default_value = 0.3
    nt.l(bp.outputs[0], bs.inputs["Normal"])
    out = nt.n("ShaderNodeOutputMaterial")
    nt.l(bs.outputs[0], out.inputs["Surface"])
    return m


def cloth_sim_freeze(cloth_ob, colliders, frames=60, pin_group=None, mass=0.35, bend=0.6, tension=12.0, shrink=0.0):
    """drop a cloth onto collision objects and freeze the result as a static mesh"""
    for c in colliders:
        if not any(md.type == "COLLISION" for md in c.modifiers):
            md = c.modifiers.new("Collision", "COLLISION")
            c.collision.thickness_outer = 0.006
            c.collision.cloth_friction = 8.0
    md = cloth_ob.modifiers.new("Cloth", "CLOTH")
    st = md.settings
    st.quality = 7
    st.mass = mass
    st.tension_stiffness = tension
    st.compression_stiffness = tension
    st.shear_stiffness = 5.0
    st.bending_stiffness = bend
    st.air_damping = 4.0
    st.shrink_min = shrink
    if pin_group:
        st.vertex_group_mass = pin_group
    cs = md.collision_settings
    cs.distance_min = 0.006
    cs.collision_quality = 3
    cs.use_self_collision = False
    md.point_cache.frame_start = 1
    md.point_cache.frame_end = frames
    for f in range(1, frames + 1):
        scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = cloth_ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = cloth_ob.data
    cloth_ob.modifiers.clear()
    cloth_ob.data = me
    me.materials.clear()
    for m in old.materials:
        me.materials.append(m)
    scene.frame_set(1)
    for c in colliders:
        for mdc in list(c.modifiers):
            if mdc.type == "COLLISION":
                c.modifiers.remove(mdc)
    return cloth_ob


def grid_geom(w, h, nx, ny):
    verts = [(-w / 2 + w * i / nx, -h / 2 + h * j / ny, 0.0) for j in range(ny + 1) for i in range(nx + 1)]
    faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i)
             for j in range(ny) for i in range(nx)]
    return verts, faces


# ----------------------------------------------------------------------------
# figure materials
# ----------------------------------------------------------------------------
MAT["skin"] = mat_plain("Skin (sun-tanned)", (0.40, 0.26, 0.16), rough=0.55, sss=0.08, spec=0.35)
MAT["skin_sh"] = mat_plain("Skin stagehand", (0.36, 0.22, 0.14), rough=0.6, sss=0.1, spec=0.3)
MAT["boot"] = mat_plain("Soft leather boots", (0.09, 0.06, 0.045), rough=0.6, spec=0.4, bump=0.2, bump_scale=80)
MAT["tunic"] = mat_cloth("Stagehand tunic (dark wool)", (0.055, 0.05, 0.045), rough=0.95, sheen=0.5)
MAT["chiton_y"] = mat_cloth("Chiton saffron", (0.62, 0.40, 0.11))
MAT["himation_r"] = mat_cloth("Himation madder", (0.40, 0.085, 0.05), sheen=0.45)
MAT["chiton_w"] = mat_cloth("Chiton undyed wool", (0.66, 0.60, 0.48))
MAT["himation_b"] = mat_cloth("Himation woad", (0.12, 0.17, 0.30), sheen=0.45)
MAT["mattress"] = mat_cloth("Mattress cover", (0.50, 0.44, 0.33), rough=0.9)
MAT["cushion_r"] = mat_cloth("Cushion red", (0.42, 0.10, 0.06))
MAT["cushion_b"] = mat_cloth("Cushion blue", (0.10, 0.14, 0.26))
MAT["glaze"] = mat_plain("Black-glaze pottery", (0.015, 0.013, 0.012), rough=0.22, spec=0.6)


# ----------------------------------------------------------------------------
# tableau (R5): couch, cushions, stool, cup, and a masked figure reclining
# built in platform coordinates with the platform rig at the origin
# ----------------------------------------------------------------------------
COUCH_C = Vector((0.04, -0.20))     # couch centre on the deck (x along the couch)
COUCH_L, COUCH_W = 1.95, 0.82
Z_FRAME = PLAT_H + 0.43             # top of the couch frame
Z_MATT = Z_FRAME + 0.11             # top of the mattress


def build_tableau():
    ctrl = PLAT["ctrl"]
    cx, cy = COUCH_C
    hl, hw = COUCH_L / 2, COUCH_W / 2
    b = Builder()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * (hl - 0.06), cy + sy * (hw - 0.06)
            b.box(x - 0.04, x + 0.04, y - 0.04, y + 0.04, PLAT_H, Z_FRAME - 0.02)
            # incised leg: a narrower neck under the rail
            b.box(x - 0.05, x + 0.05, y - 0.05, y + 0.05, Z_FRAME - 0.17, Z_FRAME - 0.11)
    for sy in (-1, 1):
        b.box(cx - hl, cx + hl, cy + sy * hw - 0.03, cy + sy * hw + 0.03, Z_FRAME - 0.11, Z_FRAME)
    for sx in (-1, 1):
        b.box(cx + sx * hl - 0.03, cx + sx * hl + 0.03, cy - hw, cy + hw, Z_FRAME - 0.11, Z_FRAME)
    # headrest at the -X end, inclined
    x0 = cx - hl
    b.add([(x0 - 0.02, cy - hw, Z_FRAME - 0.02), (x0 + 0.05, cy - hw, Z_FRAME - 0.02), (x0 + 0.05, cy + hw, Z_FRAME - 0.02),
           (x0 - 0.02, cy + hw, Z_FRAME - 0.02), (x0 - 0.09, cy - hw, Z_FRAME + 0.30), (x0 - 0.03, cy - hw, Z_FRAME + 0.30),
           (x0 - 0.03, cy + hw, Z_FRAME + 0.30), (x0 - 0.09, cy + hw, Z_FRAME + 0.30)],
          [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    couch = b.obj("Couch (kline)", "Platform", [MAT["couch"]])
    add_bevel(couch, 0.008, 2)
    couch.parent = ctrl
    # mattress
    v, f = box_geom(cx - hl + 0.03, cx + hl - 0.03, cy - hw + 0.03, cy + hw - 0.03, Z_FRAME - 0.005, Z_MATT)
    matt = mesh_obj("Mattress", v, f, "Platform", mat=MAT["mattress"])
    add_bevel(matt, 0.04, 3)
    add_subsurf(matt, 1, 2)
    set_smooth(matt)
    matt.parent = ctrl
    # cushions against the headrest
    cush = []
    for i, (dx, dy, dz, mat, sc) in enumerate(((0.16, -0.05, 0.12, MAT["cushion_r"], (0.17, 0.33, 0.12)),
                                                (0.30, 0.05, 0.07, MAT["cushion_b"], (0.16, 0.30, 0.09)))):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=1.0)
        for vtx in bm.verts:
            vtx.co.x *= sc[0]
            vtx.co.y *= sc[1]
            vtx.co.z *= sc[2] * (1.0 - 0.25 * max(0.0, -vtx.co.z))
        me = bpy.data.meshes.new(f"Cushion {i}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"Cushion {i}", me)
        COLL["Platform"].objects.link(ob)
        me.materials.append(mat)
        set_smooth(ob)
        ob.location = (x0 + dx, cy + dy, Z_MATT + dz)
        ob.rotation_euler = (0, math.radians(-28 + 10 * i), 0)
        ob.parent = ctrl
        cush.append(ob)
    # stool (diphros) with a folded cloth and a black-glaze kylix
    sx0, sy0 = 0.78, 0.42
    sb = Builder()
    for ex in (-1, 1):
        for ey in (-1, 1):
            x, y = sx0 + ex * 0.16, sy0 + ey * 0.13
            sb.box(x - 0.02, x + 0.02, y - 0.02, y + 0.02, PLAT_H, PLAT_H + 0.36)
    sb.box(sx0 - 0.21, sx0 + 0.21, sy0 - 0.17, sy0 + 0.17, PLAT_H + 0.36, PLAT_H + 0.40)
    for ey in (-1, 1):
        sb.box(sx0 - 0.17, sx0 + 0.17, sy0 + ey * 0.13 - 0.012, sy0 + ey * 0.13 + 0.012, PLAT_H + 0.12, PLAT_H + 0.145)
    stool = sb.obj("Stool (diphros)", "Platform", [MAT["couch"]])
    add_bevel(stool, 0.004, 1)
    stool.parent = ctrl
    v, f = box_geom(sx0 - 0.16, sx0 + 0.10, sy0 - 0.13, sy0 + 0.12, PLAT_H + 0.40, PLAT_H + 0.445)
    fold = mesh_obj("Folded cloth", v, f, "Platform", mat=MAT["himation_b"])
    add_bevel(fold, 0.015, 3)
    add_subsurf(fold, 1, 2)
    set_smooth(fold)
    fold.parent = ctrl
    # kylix: shallow cup on a stem (lathe), two handles
    prof = [(0.0, 0.035), (0.006, 0.036), (0.012, 0.012), (0.04, 0.009), (0.05, 0.03), (0.062, 0.075), (0.075, 0.098),
            (0.079, 0.1), (0.078, 0.094), (0.068, 0.07), (0.058, 0.0)]
    kv, kf = [], []
    n = 32
    for (z, r) in prof:
        for k in range(n):
            a = 2 * math.pi * k / n
            kv.append((r * math.cos(a), r * math.sin(a), z))
    for i in range(len(prof) - 1):
        for k in range(n):
            a0 = i * n + k
            b0 = i * n + (k + 1) % n
            kf.append((a0, b0, b0 + n, a0 + n))
    for s in (-1, 1):
        tv, tf = torus_geom(0.022, 0.0045, 16, 6)
        off = len(kv)
        kv += [(x + s * 0.112, z, y + 0.07) for (x, y, z) in tv]
        kf += [tuple(i + off for i in fc) for fc in tf]
    kyl = mesh_obj("Kylix", kv, kf, "Platform", smooth=True, mat=MAT["glaze"])
    kyl.location = (sx0 + 0.03, sy0 + 0.0, PLAT_H + 0.40)
    kyl.parent = ctrl
    return couch, matt, cush


def build_reclining_actor():
    """the demo tableau figure (R5): masked, reclining on the left elbow on the cushions,
    torso turned to the audience, legs along the couch toward +X"""
    fig = Figure("Reclining actor", 1.76, skin=MAT["skin"], head_mesh=False)
    cy = COUCH_C.y
    root = (-0.24, cy - 0.04, Z_MATT + 0.17)
    dirs = {
        "abdomen": (-0.80, 0.06, 0.60), "chest": (-0.60, 0.14, 0.79), "neck": (-0.35, 0.25, 0.90),
        "head": (-0.10, 0.25, 0.96),
        "hand.L": (0.30, 0.80, -0.52), "hand.R": (0.35, 0.55, 0.76),
        "foot.L": (0.55, 0.05, -0.83), "foot.R": (0.55, -0.15, -0.82),
    }
    fronts = {"abdomen": (0, 1, 0), "chest": (0.15, 1, 0), "head": (0.45, 1, -0.05),
              "hand.L": (0, 0, 1), "hand.R": (0.3, 1, 0), "foot.L": (1, 0.2, 0.3), "foot.R": (1, 0.2, 0.3)}
    arms = {"L": ((-0.50, cy + 0.30, Z_MATT + 0.19), (-0.15, -0.35, -1.0)),
            "R": ((-0.20, cy + 0.42, Z_MATT + 0.46), (0.35, -0.3, -1.0))}
    legs = {"L": ((0.52, cy - 0.12, Z_MATT + 0.07), (0.2, 1.0, 0.0)),
            "R": ((0.40, cy + 0.04, Z_MATT + 0.12), (0.1, 0.55, 0.8))}
    fig.pose(root, up=(-0.97, 0.0, 0.25), front=(0, 1, 0), dirs=dirs, fronts=fronts, arms=arms, legs=legs)
    # garments: chiton (torso shell + short sleeves); himation by cloth simulation
    yel = MAT["chiton_y"]
    garment(fig, "chest", "chiton top", dict(t=(-0.05, 0.30), prof=[(-0.05, 0.158, 0.116), (0.12, 0.178, 0.13), (0.2, 0.183, 0.124), (0.24, 0.165, 0.105), (0.30, 0.08, 0.07)], caps=(0, 1)),
            mat=yel, fold=folds(7, 0.05, 1, -0.05, 0.3, grow=False), open_ends=(True, False))
    garment(fig, "abdomen", "chiton waist", dict(t=(-0.02, 0.24), prof=[(-0.02, 0.172, 0.124), (0.1, 0.162, 0.12), (0.24, 0.168, 0.122)], caps=(0, 0)),
            mat=yel, fold=folds(9, 0.06, 2, -0.02, 0.24, grow=False), open_ends=(True, True))
    garment(fig, "pelvis", "chiton hips", dict(t=(-0.08, 0.22), prof=[(-0.08, 0.18, 0.13), (0.1, 0.205, 0.15), (0.22, 0.215, 0.165)], caps=(0, 0)),
            axis=(0, 0, -1), mat=yel, fold=folds(10, 0.07, 4, -0.08, 0.22), open_ends=(True, True))
    for side in ("L", "R"):
        garment(fig, "upperarm." + side, "sleeve " + side, dict(t=(-0.05, 0.27), prof=[(-0.05, 0.07, 0.072), (0.12, 0.078, 0.08), (0.27, 0.085, 0.07)], caps=(1, 0)),
                axis=(0, 0, -1), mat=yel, fold=folds(6, 0.12, 3, -0.05, 0.27), open_ends=(False, True))
    build_mask(fig, (0.80, 0.74, 0.63), (0.07, 0.045, 0.03), beard=False)
    for ob in fig.objects():
        if ob.parent is None:
            ob.parent = PLAT["ctrl"]
    return fig


def drape_himation_reclining(fig, couch, matt, cushions):
    colliders = [fig.seg[s].obj for s in ("pelvis", "abdomen", "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R",
                                          "forearm.R")]
    colliders += [o for o in bpy.data.objects if o.name.startswith("Reclining actor chiton hips")]
    colliders += [couch, matt]
    bpy.context.view_layer.update()
    ztop = Z_MATT
    for o in colliders[:9]:
        for vv in o.data.vertices:
            p = o.matrix_world @ vv.co
            if p.x > -0.12:
                ztop = max(ztop, p.z)
    v, f = grid_geom(1.62, 1.80, 46, 50)
    cx = 0.43
    cy = COUCH_C.y + 0.18
    v = [(x + cx, y + cy, ztop + 0.035 + 0.02 * math.sin(x * 9) * math.cos(y * 7)) for (x, y, z) in v]
    cl = mesh_obj("Reclining actor himation", v, f, "Figures", smooth=True, mat=MAT["himation_r"])
    cloth_sim_freeze(cl, colliders, frames=60, mass=0.35, bend=1.0, tension=14.0)
    sm = cl.modifiers.new("Solidify", "SOLIDIFY")
    sm.thickness = 0.005
    add_subsurf(cl, 1, 1)
    cl.parent = PLAT["ctrl"]
    return cl


def build_standing_actor():
    """an actor on the orchestra ground addressing the figure on the platform (beat 5)"""
    fig = Figure("Standing actor", 1.78, skin=MAT["skin"], head_mesh=False)
    s = fig.s
    pos = Vector((2.05, 1.10, 0.0))
    face = Vector((-0.88, -0.30, 0.0)).normalized()       # toward the doorway, 3/4 to the audience
    side = Vector((-face.y, face.x, 0))                    # figure's left
    right = -side
    root = pos + Vector((0, 0, 0.965 * s)) + right * 0.025
    up = Vector((0.02, 0.0, 1.0))
    dirs = {"abdomen": (0.0, 0.0, 1.0), "chest": tuple(Vector((0, 0, 1)) + face * 0.06), "neck": tuple(Vector((0, 0, 1)) + face * 0.18),
            "head": tuple(Vector((0, 0, 1)) + face * 0.08 - Vector((0, 0, 0.0))),
            "hand.R": tuple(face * 0.9 + Vector((0, 0, 0.35)) + right * 0.1), "hand.L": (0, 0, -1)}
    fronts = {"abdomen": tuple(face), "chest": tuple(face), "head": tuple(face + Vector((0.1, 0.25, 0))),
              "foot.L": (0, 0, 1), "foot.R": (0, 0, 1), "hand.R": (0, 0, 1)}
    # feet: weight on the right leg, left foot forward and turned out
    rfoot = pos + right * 0.11 + Vector((0, 0, 0.075 * s))
    lfoot = pos + side * 0.10 + face * 0.17 + Vector((0, 0, 0.075 * s))
    dirs["foot.R"] = tuple(face + right * 0.2)
    dirs["foot.L"] = tuple(face + side * 0.35)
    shoulder_R = root + Vector((0, 0, 0.47 * s)) + right * 0.18 * s
    arms = {"R": (shoulder_R + face * 0.36 + Vector((0, 0, -0.08)) + right * 0.12, Vector((0, 0, -1)) + right * 0.6),
            "L": (root + Vector((0, 0, 0.08)) + side * 0.24 + face * 0.12, -face + side * 0.5)}
    legs = {"R": (rfoot, face), "L": (lfoot, face + Vector((0, 0, 0.1)))}
    fig.pose(root, up=up, front=face, dirs=dirs, fronts=fronts, arms=arms, legs=legs)
    wht = MAT["chiton_w"]
    STANDING_CHITON.clear()
    STANDING_CHITON.extend([
        ("chest", dict(t=(-0.05, 0.30), prof=[(-0.05, 0.16, 0.118), (0.12, 0.18, 0.132), (0.2, 0.185, 0.126), (0.24, 0.166, 0.106), (0.30, 0.08, 0.07)], caps=(0, 1)), (0, 0, 1)),
        ("abdomen", dict(t=(-0.06, 0.25), prof=[(-0.06, 0.17, 0.125), (0.1, 0.158, 0.118), (0.25, 0.168, 0.124)], caps=(0, 0)), (0, 0, 1)),
        ("pelvis", dict(t=(-0.06, 0.93), prof=[(-0.06, 0.172, 0.128), (0.12, 0.2, 0.15), (0.5, 0.235, 0.19), (0.93, 0.28, 0.235)], caps=(0, 0)), (0, 0, -1)),
    ])
    garment(fig, "chest", "chiton top", STANDING_CHITON[0][1],
            mat=wht, fold=folds(7, 0.045, 11, -0.05, 0.3, grow=False), open_ends=(True, False))
    garment(fig, "abdomen", "chiton waist", STANDING_CHITON[1][1],
            mat=wht, fold=folds(9, 0.05, 12, -0.06, 0.25, grow=False), open_ends=(True, True))
    garment(fig, "pelvis", "chiton skirt", STANDING_CHITON[2][1],
            axis=(0, 0, -1), mat=wht, fold=folds(11, 0.09, 13, -0.06, 0.93), open_ends=(True, True), n_around=64, n_along=36)
    for sd in ("L", "R"):
        garment(fig, "upperarm." + sd, "sleeve " + sd, dict(t=(-0.04, 0.30), prof=[(-0.04, 0.064, 0.066), (0.30, 0.052, 0.054)], caps=(1, 0)),
                axis=(0, 0, -1), mat=wht, fold=folds(6, 0.07, 14, -0.04, 0.3), open_ends=(False, True))
        garment(fig, "forearm." + sd, "cuff " + sd, dict(t=(-0.02, 0.22), prof=[(-0.02, 0.052, 0.054), (0.22, 0.042, 0.044)], caps=(0, 0)),
                axis=(0, 0, -1), mat=wht, fold=folds(5, 0.06, 15, -0.02, 0.22), open_ends=(True, True))
        garment(fig, "shin." + sd, "boot " + sd, dict(t=(0.24, 0.43), prof=[(0.24, 0.05, 0.052), (0.43, 0.04, 0.042)], caps=(0, 0)),
                       axis=(0, 0, -1), mat=MAT["boot"], fold=folds(4, 0.03, 16, 0.24, 0.43), open_ends=(True, True), solid=0.004)
        fig.seg["foot." + sd].obj.data.materials[0] = MAT["boot"]
    build_mask(fig, (0.74, 0.67, 0.55), (0.03, 0.025, 0.02), beard=True)
    return fig


STANDING_CHITON = []


def drape_himation_standing(fig):
    """a woad-blue mantle over the left shoulder, front and back, pinned at the shoulder"""
    P = fig.P
    W = fig.W
    shL = P["upperarm.L"]
    chest_q = W["chest"]
    up = chest_q @ Vector((0, 0, 1))
    fr = chest_q @ Vector((0, 1, 0))
    rt = fr.cross(up)
    # strip: 0.95 wide (across the shoulder), runs front-to-back over the shoulder
    nx, ny = 24, 56
    width, length = 1.25, 2.3
    verts, faces = [], []
    pin = []
    for j in range(ny + 1):
        u = -length / 2 + length * j / ny          # along the strip; 0 = on the shoulder
        for i in range(nx + 1):
            w = -width / 2 + width * i / nx
            # arc over the shoulder (radius 0.11) then hang vertically front and back
            if abs(u) < 0.36:
                ang = u / 0.36 * (math.pi / 2)
                off = fr * (math.sin(ang) * 0.30) + up * (math.cos(ang) * 0.17)
            else:
                sgn = 1 if u > 0 else -1
                off = fr * (0.30 * sgn) + up * (0.0 - (abs(u) - 0.36))
            p = shL + up * 0.02 + off + (-rt) * (w * 0.55 + 0.03)
            verts.append(tuple(p))
            pin.append(1.0 if abs(u) < 0.08 and abs(w) < 0.22 else 0.0)
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    cl = mesh_obj("Standing actor himation", verts, faces, "Figures", smooth=True, mat=MAT["himation_b"])
    vg = cl.vertex_groups.new(name="pin")
    for k, wgt in enumerate(pin):
        if wgt > 0:
            vg.add([k], wgt, "REPLACE")
    colliders = [fig.seg[n].obj for n in ("chest", "abdomen", "pelvis", "upperarm.L", "forearm.L", "thigh.L", "thigh.R", "neck")]
    # thin solidified garments collide badly: use closed, slightly inflated proxies of the chiton
    proxies = []
    for (seg, shape, axis) in STANDING_CHITON:
        pr = garment(fig, seg, "collision proxy", shape, axis=axis, mat=None, fold=None, solid=0.0,
                     n_around=24, n_along=12, open_ends=(False, False))
        pr.modifiers.clear()
        pr.scale = (1.07, 1.07, 1.0)
        pr.hide_render = True
        proxies.append(pr)
    cloth_sim_freeze(cl, colliders + proxies, frames=60, pin_group="pin", mass=0.45, bend=1.0, tension=15.0)
    for pr in proxies:
        bpy.data.objects.remove(pr)
    sm = cl.modifiers.new("Solidify", "SOLIDIFY")
    sm.thickness = 0.005
    add_subsurf(cl, 1, 1)
    return cl


# ----------------------------------------------------------------------------
# stagehands (R4): plain dark tunics, crouched behind the platform, pushing
# ----------------------------------------------------------------------------
def build_stagehand(name):
    fig = Figure(name, 1.70, skin=MAT["skin_sh"])
    tun = MAT["tunic"]
    garment(fig, "chest", "tunic top", dict(t=(-0.04, 0.30), prof=[(-0.04, 0.16, 0.118), (0.12, 0.18, 0.132), (0.2, 0.184, 0.126), (0.24, 0.166, 0.105), (0.30, 0.075, 0.065)], caps=(0, 1)),
            mat=tun, fold=folds(6, 0.04, 21, -0.04, 0.3, grow=False), open_ends=(True, False))
    garment(fig, "abdomen", "tunic waist", dict(t=(-0.08, 0.26), prof=[(-0.08, 0.18, 0.13), (0.1, 0.162, 0.118), (0.26, 0.17, 0.124)], caps=(0, 0)),
            mat=tun, fold=folds(8, 0.05, 22, -0.08, 0.26, grow=False), open_ends=(True, True))
    garment(fig, "pelvis", "tunic skirt", dict(t=(-0.06, 0.20), prof=[(-0.06, 0.175, 0.13), (0.20, 0.205, 0.16)], caps=(0, 0)),
            axis=(0, 0, -1), mat=tun, fold=folds(9, 0.06, 23, -0.06, 0.2), open_ends=(True, True))
    for sd in ("L", "R"):
        garment(fig, "thigh." + sd, "tunic hem " + sd, dict(t=(-0.04, 0.24), prof=[(-0.04, 0.10, 0.104), (0.24, 0.112, 0.116)], caps=(0, 0)),
                axis=(0, 0, -1), mat=tun, fold=folds(6, 0.08, 24 + (sd == "L"), -0.04, 0.24), open_ends=(True, True))
    # short dark hair cap
    head = fig.seg["head"].obj
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=56, v_segments=36, radius=1.0)
    for vtx in bm.verts:
        vtx.co.x *= 0.084 * fig.s
        vtx.co.y *= 0.102 * fig.s
        vtx.co.z *= 0.1 * fig.s
        vtx.co.z += 0.118 * fig.s
        vtx.co.y += 0.006 * fig.s
    for f in list(bm.faces):
        c = f.calc_center_median()
        # hairline: high on the forehead, over the ears at the sides, down to the nape behind
        fy = max(-1.0, min(1.0, c.y / (0.102 * fig.s)))
        hairline = (0.105 + 0.07 * max(0.0, fy) - 0.045 * max(0.0, -fy)) * fig.s
        if c.z < hairline:
            bm.faces.remove(f)
    me = bpy.data.meshes.new(name + " hair")
    bm.to_mesh(me)
    bm.free()
    hair = bpy.data.objects.new(name + " hair", me)
    COLL["Figures"].objects.link(hair)
    me.materials.append(mat_hair(name + " hair", (0.035, 0.028, 0.022)))
    set_smooth(hair)
    hair.parent = head
    sm = hair.modifiers.new("Solidify", "SOLIDIFY")
    sm.thickness = 0.008
    return fig


def _lerpv(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def stagehand_root(x, rear, hide, s=1.0, bob=0.0):
    """pelvis position. push (hide 0): on the ground behind the rear rail. hide 1: out of every
    frontal sight line: back past the ends of the open door leaves, then sideways behind the
    facade wall (path: back first, then sideways), crouched low"""
    sx = 1.0 if x > 0 else -1.0
    p0 = Vector((x, rear - 0.62))
    p1 = Vector((x + sx * 0.25, rear - 1.70))
    p2 = Vector((sx * 1.95, rear - 1.70))
    if hide <= 0.45:
        t = smoothstep(0.0, 1.0, hide / 0.45)
        p = p0.lerp(p1, t)
    else:
        p = p1.lerp(p2, smoothstep(0.0, 1.0, (hide - 0.45) / 0.55))
    crouch = min(1.0, hide / 0.3)
    return Vector((p.x, p.y, (0.52 - 0.12 * crouch) * s + bob))


STAGEHAND_FEET = {"push": {"L": (-0.12, -0.08), "R": (0.12, -0.40)},
                  "hide": {"L": (-0.13, 0.10), "R": (0.13, -0.16)}}


def stagehand_pose(fig, x, rear, feet, frame, lean=0.0, bob=0.0, hide=0.0):
    """push: crouched on the ground behind the platform, arms straight down to the top of the
    rear rail, head well behind the couch. hide (0..1): low crouch, hands on the knees"""
    s = fig.s
    root = stagehand_root(x, rear, hide, s, bob)
    hide = min(1.0, hide / 0.3)          # posture changes early in the retreat
    up = Vector(_lerpv((0, 0.72 + lean, 0.69), (0, 0.88, 0.47), hide)).normalized()
    front = Vector(_lerpv((0, 0.69, -0.72 - lean), (0, 0.47, -0.88), hide))
    dirs = {"abdomen": _lerpv((0, 0.72 + lean, 0.69), (0, 0.88, 0.47), hide),
            "chest": _lerpv((0, 0.80, 0.60), (0, 0.96, 0.28), hide),
            "neck": _lerpv((0, 0.55, 0.83), (0, 0.90, 0.43), hide),
            "head": _lerpv((0, 0.25, 0.97), (0, 0.70, 0.71), hide)}
    fronts = {"abdomen": (0, 0.5, -0.8), "chest": (0, 0.4, -0.9), "head": (0, 1, -0.2),
              "foot.L": (0, 0, 1), "foot.R": (0, 0, 1), "hand.L": (0, 1, 0), "hand.R": (0, 1, 0)}
    hd = _lerpv((0, 0.82, -0.57), (0, 0.5, -0.86), hide)
    dirs["hand.L"] = hd
    dirs["hand.R"] = hd
    arms = {}
    for sd, sg in (("R", 1.0), ("L", -1.0)):
        push = Vector((x + sg * 0.17, rear - 0.06, PLAT_H + 0.09))
        rest = root + Vector((sg * 0.17, 0.42, -0.22))
        arms[sd] = (push.lerp(rest, hide), Vector((sg * 0.5, -0.4, -1)))
    legs = {}
    for sd in ("L", "R"):
        p, lift = feet[sd]
        tgt = Vector((p.x, p.y, 0.072 * s + lift))
        legs[sd] = (tgt, Vector((0.15 if sd == "R" else -0.15, 1.0, 0.35)))
        dirs["foot." + sd] = (0, 1.0, -0.15 - lift * 3)
    fig.pose(root, up=up, front=front, dirs=dirs, fronts=fronts, arms=arms, legs=legs, frame=frame)


def animate_stagehands(figs, xs):
    """per-frame gait: the pelvis follows the platform (and the hide retreat); each foot stays
    planted until it lags its neutral spot by 17 cm, then steps (8 frames, 7 cm lift), one
    foot at a time, so the feet never slide"""
    ctrl = PLAT["ctrl"]
    fc = ctrl.animation_data.action.fcurves.find("location", index=1)
    f_end = scene.frame_end
    # hide weight: 1 while the platform stands rolled out; they retreat over 3 s after it stops
    # and come back over 2.1 s before it moves again (on camera, in the SH08 cutaway). After
    # the second roll-out they stay hidden until the cut at 82 s.
    holds = [(F(T["roll_out"][1]), F(T["roll_in"][0]), int(3.0 * FPS), int(2.1 * FPS)),
             (F(T["roll_out2"][1]), F(T["end_plan"]) - 1, int(3.0 * FPS), 0)]

    def hide_w(f):
        for a, b, r_out, r_back in holds:
            if a <= f <= b:
                w = smoothstep(a, a + r_out, f)
                if r_back:
                    w *= 1.0 - smoothstep(b - r_back, b, f)
                return w
        return 0.0

    def state(x, f):
        rear = fc.evaluate(f) - PLAT_D / 2
        h = hide_w(f)
        return rear, h, stagehand_root(x, rear, h)

    for fig, x in zip(figs, xs):
        planted = {}
        swing = {"L": None, "R": None}
        prev_root = None
        for f in range(1, f_end + 1):
            rear, h, root = state(x, f)
            neutral = {sd: _lerpv(STAGEHAND_FEET["push"][sd] + (0,), STAGEHAND_FEET["hide"][sd] + (0,), h)
                       for sd in ("L", "R")}
            r_prev, r_next = state(x, f - 1)[2], state(x, f + 1)[2]
            moving = (r_next - r_prev).length > 1e-4 or any(swing.values())
            jump = prev_root is not None and (root - prev_root).length > 0.25
            if not planted or jump:
                for sd in ("L", "R"):
                    planted[sd] = Vector((root.x + neutral[sd][0], root.y + neutral[sd][1], 0))
                    swing[sd] = None
            vel = Vector((0, 0, 0)) if prev_root is None else (root - prev_root)
            vel.z = 0
            lead = vel.normalized() * 0.13 if vel.length > 1e-5 else Vector((0, 0, 0))
            feet = {}
            for sd in ("L", "R"):
                other = "R" if sd == "L" else "L"
                want = Vector((root.x + neutral[sd][0], root.y + neutral[sd][1], 0))
                if swing[sd] is None and swing[other] is None and (want - planted[sd]).length > 0.17:
                    swing[sd] = (f, planted[sd].copy(), want + lead)
                if swing[sd] is not None:
                    f0, a, b = swing[sd]
                    u = (f - f0) / 8.0
                    if u >= 1.0:
                        planted[sd] = b
                        swing[sd] = None
                        feet[sd] = (b, 0.0)
                    else:
                        uu = u * u * (3 - 2 * u)
                        feet[sd] = (a.lerp(b, uu), 0.07 * math.sin(math.pi * u))
                else:
                    feet[sd] = (planted[sd], 0.0)
            prev_root = root
            if not moving and not jump and f not in (1, f_end):
                # key a still pose only at the edges of each still period
                r2p, r2n = state(x, f - 2)[2], state(x, f + 2)[2]
                if (r2n - root).length < 1e-4 and (root - r2p).length < 1e-4:
                    continue
            bob = 0.012 * math.sin(f * 0.9) if moving else 0.0
            plat_moving = abs(fc.evaluate(f + 1) - fc.evaluate(f - 1)) > 1e-4
            stagehand_pose(fig, x, rear, feet, f, lean=0.06 if plat_moving else 0.0, bob=bob, hide=h)
        for ob in fig.objects():
            ad = ob.animation_data
            if ad and ad.action:
                for c in ad.action.fcurves:
                    for kp in c.keyframe_points:
                        kp.interpolation = "LINEAR"


# ----------------------------------------------------------------------------
# keyframing helpers
# ----------------------------------------------------------------------------
def key(obj, path, index, frame, value, interp="BEZIER"):
    if index is None:
        setattr(obj, path, value)
    else:
        getattr(obj, path)[index] = value
    obj.keyframe_insert(path, index=-1 if index is None else index, frame=frame)
    fcs = obj.animation_data.action.fcurves
    for fc in fcs:
        if fc.data_path == path and (index is None or fc.array_index == index):
            for kp in fc.keyframe_points:
                if abs(kp.co.x - frame) < 0.5:
                    kp.interpolation = interp


def ease_move(obj, path, index, f0, v0, f1, v1, ease=0.45):
    """heavy move: hold v0 until f0, glide to v1 at f1 with long ease in/out, no overshoot"""
    key(obj, path, index, f0, v0)
    key(obj, path, index, f1, v1)
    fc = obj.animation_data.action.fcurves.find(path, index=index if index is not None else 0)
    for kp in fc.keyframe_points:
        kp.handle_left_type = "FREE"
        kp.handle_right_type = "FREE"
    for kp in fc.keyframe_points:
        x, y = kp.co
        if abs(x - f0) < 0.5 or abs(x - f1) < 0.5:
            span = (f1 - f0) * ease
            kp.handle_left = (x - span, y)
            kp.handle_right = (x + span, y)


def animate_action():
    ctrl = PLAT["ctrl"]
    Y0, Y1 = PLAT_Y_IN, PLAT_Y_OUT
    ctrl.location = (0, Y0, 0)
    key(ctrl, "location", 1, 1, Y0)
    ease_move(ctrl, "location", 1, F(T["roll_out"][0]), Y0, F(T["roll_out"][1]), Y1)
    ease_move(ctrl, "location", 1, F(T["roll_in"][0]), Y1, F(T["roll_in"][1]), Y0)
    ease_move(ctrl, "location", 1, F(T["roll_out2"][0]), Y0, F(T["roll_out2"][1]), Y1)
    key(ctrl, "location", 1, F(T["end_plan"]) - 1, Y1, "CONSTANT")
    key(ctrl, "location", 1, F(T["end_plan"]), Y0, "CONSTANT")
    key(ctrl, "location", 1, scene.frame_end, Y0)
    fc = ctrl.animation_data.action.fcurves.find("location", index=1)
    for kp in fc.keyframe_points:
        if abs(kp.co.x - (F(T["end_plan"]) - 1)) < 0.5:
            kp.interpolation = "CONSTANT"
    drive_wheels()
    # doors (R6): swing inward. E leaf +90 deg, W leaf -90 deg about the hinge
    for side, hinge, leaf in DOORS:
        hinge.rotation_mode = "XYZ"
        op = math.radians(90.0) * side
        key(hinge, "rotation_euler", 2, 1, 0.0)
        ease_move(hinge, "rotation_euler", 2, F(T["doors_open"][0]), 0.0, F(T["doors_open"][1]), op, ease=0.38)
        ease_move(hinge, "rotation_euler", 2, F(T["doors_close"][0]), op, F(T["doors_close"][1]), 0.0, ease=0.38)
        key(hinge, "rotation_euler", 2, F(T["plan_on"]) - 1, 0.0, "CONSTANT")
        key(hinge, "rotation_euler", 2, F(T["plan_on"]), op, "CONSTANT")
        key(hinge, "rotation_euler", 2, F(T["end_plan"]) - 1, op, "CONSTANT")
        key(hinge, "rotation_euler", 2, F(T["end_plan"]), 0.0)
        ease_move(hinge, "rotation_euler", 2, F(T["teaser_doors"][0]), 0.0, F(T["teaser_doors"][1]), op * 0.8, ease=0.4)


DOORS = []


# ----------------------------------------------------------------------------
# section cutters (museum-style cutaway) and evidence-code overlays
# ----------------------------------------------------------------------------
CUT = {}


def build_cutters():
    sec = MAT["section"]
    # vertical section through the door axis: removes x < cut (cut keyed in x)
    # stepped profile in XZ, extruded along Y: walls cut at x = 0, roof opened to x = 2.5
    prof = [(-60.0, -2.0), (0.0, -2.0), (0.0, 4.25), (2.5, 4.25), (2.5, 40.0), (-60.0, 40.0)]
    v = [(x, -30.0, z) for (x, z) in prof] + [(x, 30.0, z) for (x, z) in prof]
    n = len(prof)
    f = [tuple(range(n)), tuple(n + i for i in reversed(range(n)))]
    f += [(i, n + i, n + (i + 1) % n, (i + 1) % n) for i in range(n)]
    vc = mesh_obj("Section cutter (vertical)", v, f, "Overlays", mat=sec)
    vc.hide_render = True
    vc.display_type = "WIRE"
    # plan section: removes everything above z = 3.1 (below the lintel)
    v, f = box_geom(-30.0, 30.0, -30.0, 30.0, 3.1, 40.0)
    pc = mesh_obj("Section cutter (plan)", v, f, "Overlays", mat=sec)
    pc.hide_render = True
    pc.display_type = "WIRE"
    for ob in SKENE_PARTS:
        for cutter, nm in ((vc, "Cut vertical"), (pc, "Cut plan")):
            md = ob.modifiers.new(nm, "BOOLEAN")
            md.operation = "DIFFERENCE"
            md.solver = "EXACT"
            md.object = cutter
            md.material_mode = "TRANSFER"
            md.use_self = False
    # the cut faces get the section material through TRANSFER; make sure it is in each slot list
    CUT["v"], CUT["p"] = vc, pc
    return vc, pc


SHOTS = []      # filled by build_cameras: (name, t0, t1, cut_vertical, cut_plan)


def animate_cutters():
    vc, pc = CUT["v"], CUT["p"]
    OFFV, OFFP = -80.0, 60.0
    key(vc, "location", 0, 1, OFFV, "CONSTANT")
    key(pc, "location", 2, 1, OFFP, "CONSTANT")
    for name, t0, t1, cv, cp in SHOTS:
        f0 = F(t0)
        if cv == "sweep":
            key(vc, "location", 0, f0, -SKENE_W / 2 - 0.6, "LINEAR")
            key(vc, "location", 0, F(T["cut_in"][0]), -SKENE_W / 2 - 0.6, "LINEAR")
            key(vc, "location", 0, F(T["cut_in"][1]), 0.0, "CONSTANT")
        elif cv:
            key(vc, "location", 0, f0, 0.0, "CONSTANT")
        else:
            key(vc, "location", 0, f0, OFFV, "CONSTANT")
        key(pc, "location", 2, f0, 0.0 if cp else OFFP, "CONSTANT")
    for o in [vc, pc]:
        if o.animation_data and o.animation_data.action:
            for c in o.animation_data.action.fcurves:
                for kp in c.keyframe_points:
                    if kp.interpolation != "LINEAR":
                        kp.interpolation = "CONSTANT"


def fade(mat, ob_list, t_in, t_out, ramp=0.6):
    """key the ghost material's Opacity value and the objects' render visibility"""
    val = mat.node_tree.nodes["Opacity"].outputs[0]
    pts = [(1, 0.0), (F(t_in) - 1, 0.0), (F(t_in + ramp), 1.0), (F(t_out - ramp), 1.0), (F(t_out), 0.0)]
    for fr, v in pts:
        val.default_value = v
        val.keyframe_insert("default_value", frame=fr)
    for o in ob_list:
        for fr, hid in ((1, True), (F(t_in) - 1, False), (F(t_out) + 1, True)):
            o.hide_render = hid
            o.keyframe_insert("hide_render", frame=fr)
        for c in o.animation_data.action.fcurves:
            for kp in c.keyframe_points:
                kp.interpolation = "CONSTANT"


def dashed_rect(name, corners, dash=0.12, gap=0.08, w=0.018, mat=None, parent=None):
    """thin dashed outline through the given corner points (closed loop)"""
    b = Builder()
    pts = [Vector(c) for c in corners]
    for i in range(len(pts)):
        a, c = pts[i], pts[(i + 1) % len(pts)]
        d = c - a
        L = d.length
        dn = d.normalized()
        up = Vector((0, 0, 1)) if abs(dn.z) < 0.9 else Vector((1, 0, 0))
        sd = dn.cross(up).normalized()
        up2 = sd.cross(dn).normalized()
        t = 0.0
        while t < L:
            t1 = min(L, t + dash)
            p0, p1 = a + dn * t, a + dn * t1
            vv = []
            for (e1, e2) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                vv.append(p0 + sd * (e1 * w / 2) + up2 * (e2 * w / 2))
            for (e1, e2) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                vv.append(p1 + sd * (e1 * w / 2) + up2 * (e2 * w / 2))
            b.add(vv, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
            t = t1 + gap
    ob = b.obj(name, "Overlays", [mat])
    if parent:
        ob.parent = parent
    return ob


def build_overlays():
    ghost = mat_ghost("Ghost: rival theory (accent-2)")
    recon = mat_ghost("Tag: our reconstruction", color=(0.94, 0.90, 0.82), alpha=0.85, emit=2.5)
    ctrl = PLAT["ctrl"]
    # (a) turntable in the doorway (Exon 1900; Flickinger 1918): disc + rotating door-wall
    tt = empty("Ghost turntable pivot", (0.0, -0.10, 0.0), "Overlays", 0.5)
    v, f = cylinder_geom(1.45, 0.0, 0.10, 48)
    disc = mesh_obj("Ghost turntable disc", v, f, "Overlays", smooth=False, mat=ghost)
    v, f = box_geom(-1.42, 1.42, -0.05, 0.05, 0.10, 3.15)
    wallg = mesh_obj("Ghost turntable wall", v, f, "Overlays", mat=ghost)
    v, f = box_geom(-0.9, 0.9, -1.15, -0.45, 0.10, 0.62)
    couchg = mesh_obj("Ghost turntable couch", v, f, "Overlays", mat=ghost)
    for o in (disc, wallg, couchg):
        o.parent = tt
    tt.rotation_mode = "XYZ"
    key(tt, "rotation_euler", 2, 1, 0.0)
    ease_move(tt, "rotation_euler", 2, F(66.8), 0.0, F(69.6), math.pi, ease=0.4)
    # (b) windlass and pulley (Casanova 2017): drum at the back, pulley out in front
    wl = []
    drum = empty("Ghost windlass drum", (0.0, -4.05, 0.75), "Overlays", 0.3)
    v, f = cylinder_geom(0.16, -0.6, 0.6, 24, "X")
    d1 = mesh_obj("Ghost windlass drum body", v, f, "Overlays", mat=ghost)
    d1.parent = drum
    hb = Builder()
    for s in (-1, 1):
        hb.box(s * 0.62, s * 0.66, -0.02, 0.02, -0.02, 0.38)
        hb.box(s * 0.62, s * 0.80, -0.02, 0.02, 0.34, 0.38)
    cr = hb.obj("Ghost windlass cranks", "Overlays", [ghost])
    cr.parent = drum
    fb = Builder()
    for s in (-1, 1):
        fb.box(s * 0.70, s * 0.78, -4.15, -3.95, 0.0, 0.85)
    frame = fb.obj("Ghost windlass posts", "Overlays", [ghost])
    v, f = cylinder_geom(0.12, -0.05, 0.05, 24, "X", (0.0, 1.95, 0.14))
    pul = mesh_obj("Ghost pulley", v, f, "Overlays", mat=ghost)
    v, f = cylinder_geom(0.012, 0.0, 1.0, 8, "Y")
    rope_fixed = mesh_obj("Ghost rope (return)", [(x, y * (1.95 + 4.05) - 4.05, z) for (x, y, z) in v], f, "Overlays", mat=ghost)
    rope_fixed.location = (0.06, 0.0, 0.0)
    rope_fixed.data.transform(Matrix.Translation((0, 0, 0.05)))
    rope_pull = mesh_obj("Ghost rope (to platform)", [(x, -y, z) for (x, y, z) in v], f, "Overlays", mat=ghost)
    rope_pull.location = (-0.06, 1.95, 0.14)
    # the pulling strand runs from the pulley back to the platform's front edge
    fcd = rope_pull.driver_add("scale", 1).driver
    fcd.type = "SCRIPTED"
    var = fcd.variables.new()
    var.name = "y"
    var.targets[0].id = ctrl
    var.targets[0].data_path = "location[1]"
    fcd.expression = f"max(0.01, 1.95 - (y + {PLAT_D / 2:.3f}))"
    drum.rotation_mode = "XYZ"
    fcd2 = drum.driver_add("rotation_euler", 0).driver
    fcd2.type = "SCRIPTED"
    var = fcd2.variables.new()
    var.name = "y"
    var.targets[0].id = ctrl
    var.targets[0].data_path = "location[1]"
    fcd2.expression = f"(y - ({PLAT_Y_IN:.3f})) / 0.16"
    wl = [d1, cr, frame, pul, rope_fixed, rope_pull]
    # (c) the range of sizes: Dearden ~2.55 x 1.3 m, Haigh ~3 m wide
    sizes = []
    for nm, w, d in (("Dearden 2.55 x 1.30", 2.55, 1.30), ("Haigh ~3.0 wide", 3.0, 1.6)):
        v, f = box_geom(-w / 2, w / 2, -d / 2, d / 2, PLAT_H + 0.01, PLAT_H + 0.03)
        o = mesh_obj(f"Ghost size {nm}", v, f, "Overlays", mat=ghost)
        o.parent = ctrl
        sizes.append(o)
    ghosts_a = [disc, wallg, couchg]
    # one material per ghost group so each fades on its own
    mats = []
    for grp, nm in ((ghosts_a, "turntable"), (wl, "windlass"), (sizes, "sizes")):
        m = ghost.copy()
        m.name = f"Ghost: {nm}"
        for o in grp:
            o.data.materials.clear()
            o.data.materials.append(m)
        mats.append(m)
    fade(mats[0], ghosts_a, 66.3, 70.2)
    fade(mats[1], wl, 70.1, 74.6)
    fade(mats[2], sizes, 74.4, 78.4)
    # [R] tags: faint dashed outlines on the platform (R1) and the doorway (R2), with the labels in beat 2
    hw, hd = PLAT_W / 2 + 0.03, PLAT_D / 2 + 0.03
    r1 = dashed_rect("Tag R1 platform outline", [(-hw, -hd, PLAT_H + 0.02), (hw, -hd, PLAT_H + 0.02), (hw, hd, PLAT_H + 0.02), (-hw, hd, PLAT_H + 0.02)],
                     mat=None, parent=ctrl)
    r2 = dashed_rect("Tag R2 doorway outline", [(-DOOR_W / 2, 0.03, 0.02), (DOOR_W / 2, 0.03, 0.02), (DOOR_W / 2, 0.03, DOOR_H), (-DOOR_W / 2, 0.03, DOOR_H)],
                     mat=None, dash=0.16, gap=0.1)
    m_tag = recon
    for o in (r1, r2):
        o.data.materials.clear()
        o.data.materials.append(m_tag)
    fade(m_tag, [r1, r2], 21.5, 27.4)
    return ghost


# ----------------------------------------------------------------------------
# cameras and the edit (camera markers)
# ----------------------------------------------------------------------------
def make_camera(name, lens=35.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36.0
    cd.clip_start = 0.1
    cd.clip_end = 60000.0
    cam = bpy.data.objects.new(name, cd)
    COLL["Cameras"].objects.link(cam)
    tgt = bpy.data.objects.new(name + " target", None)
    tgt.empty_display_size = 0.3
    COLL["Cameras"].objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam, tgt


def cam_path(cam, tgt, keys, smooth=True):
    """keys: list of (t_seconds, cam_loc, target_loc, lens)"""
    for (t, loc, at, lens) in keys:
        f = F(t)
        cam.location = loc
        cam.keyframe_insert("location", frame=f)
        tgt.location = at
        tgt.keyframe_insert("location", frame=f)
        cam.data.lens = lens
        cam.data.keyframe_insert("lens", frame=f)
    for ob in (cam, tgt, cam.data):
        for c in ob.animation_data.action.fcurves:
            for kp in c.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
            c.update()


def follow_platform(cam, tgt, t0, t1, cam_off, tgt_off, lens):
    """camera rides alongside the platform with the same easing"""
    ctrl = PLAT["ctrl"]
    fc = ctrl.animation_data.action.fcurves.find("location", index=1)
    for f in range(F(t0), F(t1) + 1, 2):
        y = fc.evaluate(f)
        cam.location = (cam_off[0], y + cam_off[1], cam_off[2])
        tgt.location = (tgt_off[0], y + tgt_off[1], tgt_off[2])
        cam.keyframe_insert("location", frame=f)
        tgt.keyframe_insert("location", frame=f)
    cam.data.lens = lens
    cam.data.keyframe_insert("lens", frame=F(t0))


def build_cameras():
    cams = {}

    def shot(name, t0, t1, cv, cp, keys=None, follow=None, desc=""):
        cam, tgt = make_camera(name)
        if keys:
            cam_path(cam, tgt, keys)
        if follow:
            follow_platform(cam, tgt, t0, t1, *follow)
        cam["shot"] = desc
        cams[name] = cam
        SHOTS.append((name, t0, t1, cv, cp))
        m = scene.timeline_markers.new(name, frame=F(t0))
        m.camera = cam
        return cam

    shot("SH01 establishing", 0.0, 5.0, False, False, [
        (0.0, (-262.0, -222.0, 90.0), (-29.0, 65.0, 29.0), 52.0),
        (5.0, (-248.0, -208.0, 83.0), (-31.0, 64.0, 29.0), 54.0)],
        desc="telephoto aerial from the far south-west: the theatre on the hillside; above it the Acropolis "
             "and the Parthenon, its west pediment and roof ridge seen obliquely")
    shot("SH02 descent", 5.0, 15.0, False, False, [
        (5.0, (-9.0, 74.0, 40.0), (0.0, 2.0, 0.0), 30.0),
        (10.0, (-4.0, 42.0, 15.0), (0.0, -1.0, 1.5), 34.0),
        (15.0, (2.6, 25.5, 3.3), (0.0, -1.0, 1.8), 40.0)], desc="descent over the theatron to audience eye-level")
    shot("SH03 into the cutaway", 15.0, 28.0, "sweep", False, [
        (15.0, (2.6, 25.5, 3.3), (0.0, -1.0, 1.8), 40.0),
        (18.5, (-10.0, 12.5, 5.5), (-0.5, -1.4, 1.4), 32.0),
        (22.0, (-9.2, -0.5, 4.8), (0.2, -2.0, 0.8), 30.0),
        (28.0, (-6.4, -4.2, 4.0), (0.2, -2.0, 0.8), 30.0)], desc="arc round to the west side as the section cuts the skene")
    shot("SH04 doors open (cutaway)", 28.0, 34.5, True, False, [
        (28.0, (-5.7, -4.5, 3.5), (0.3, -1.9, 0.8), 30.0),
        (34.5, (-5.1, -4.0, 3.2), (0.4, -1.6, 0.8), 30.0)], desc="section view from behind: the leaves swing inward")
    shot("SH05 tracking the roll-out", 34.5, 40.0, True, False,
         follow=((-3.3, -1.3, 1.2), (0.4, 0.3, 0.7), 28.0), desc="camera rides alongside the platform, a little behind it")
    shot("SH06 audience eye", 40.0, 46.0, False, False, [
        (40.0, (1.6, 25.5, 3.6), (0.0, 0.0, 1.3), 50.0),
        (46.0, (1.1, 20.0, 3.1), (0.0, 0.0, 1.25), 50.0)], desc="what the audience saw: the tableau rolled out of the doorway")
    shot("SH07 orbit the tableau", 46.0, 57.5, False, False, [
        (46.0, (4.3, 5.2, 1.75), (0.5, 0.5, 1.0), 40.0),
        (52.0, (1.0, 6.4, 1.6), (0.45, 0.45, 1.0), 40.0),
        (58.0, (-2.9, 5.2, 1.7), (0.35, 0.45, 1.0), 40.0)], desc="medium orbit: the whole tableau and the actor addressing it")
    c7 = cams["SH07 orbit the tableau"]
    c7.data.dof.use_dof = True
    c7.data.dof.focus_object = bpy.data.objects["SH07 orbit the tableau target"]
    c7.data.dof.aperture_fstop = 2.8
    shot("SH08 rolling back in (cutaway)", 57.5, 63.4, True, False, [
        (57.5, (-5.9, -3.4, 3.7), (0.2, -0.6, 0.8), 30.0),
        (63.4, (-5.6, -4.4, 3.4), (0.2, -1.8, 0.8), 30.0)], desc="section view: the stagehands come back and pull it in")
    shot("SH09 doors shut", 63.4, 66.0, False, False, [
        (63.4, (0.9, 12.5, 2.2), (0.0, -0.3, 1.7), 40.0),
        (66.0, (0.7, 11.5, 2.1), (0.0, -0.3, 1.7), 40.0)], desc="front: the doors close")
    cam = shot("SH10 overhead: what is disputed", 66.0, 82.0, False, True, None, desc="plan view, ghosts of rival theories")
    cam.constraints.clear()
    cam.rotation_mode = "XYZ"
    # rotates until 78.5 s, then a locked hold (nothing moves until the cut: render once, reuse)
    for t, z, rz, lens in ((66.0, 15.5, math.radians(-8), 40.0), (78.5, 14.6, math.radians(5), 40.0),
                           (82.0, 14.6, math.radians(5), 40.0)):
        cam.location = (0.4, -1.3, z)
        cam.keyframe_insert("location", frame=F(t))
        cam.rotation_euler = (0.0, 0.0, rz)
        cam.keyframe_insert("rotation_euler", frame=F(t))
        cam.data.lens = lens
        cam.data.keyframe_insert("lens", frame=F(t))
    # locked off for the composited thumbnails (82-87.2 s: render once, reuse), then a push in
    shot("SH11 reveals and Ajax teaser", 82.0, 90.0, False, False, [
        (82.0, (0.6, 16.0, 2.4), (0.0, -0.4, 1.7), 45.0),
        (87.2, (0.6, 16.0, 2.4), (0.0, -0.4, 1.7), 45.0),
        (90.0, (0.25, 10.0, 2.0), (0.0, -0.8, 1.55), 50.0)], desc="front: thumbnails composited, then the doors open on darkness")
    # look-test cameras (not in the edit)
    cam, tgt = make_camera("LT b audience eye", 45.0)
    cam.location, tgt.location = (1.5, 21.5, 3.25), (0.1, 0.0, 1.3)
    cam, tgt = make_camera("LT clip", 35.0)
    keys = [(30.8, (-4.6, 6.8, 1.7), (0.0, -1.0, 1.3), 35.0), (34.5, (-3.9, 5.8, 1.55), (0.0, -1.2, 1.2), 35.0),
            (38.8, (-3.3, 5.4, 1.4), (0.3, 0.1, 0.95), 35.0)]
    cam_path(cam, tgt, keys)
    scene.camera = cams["SH01 establishing"]
    EXPOSURE.update({"SH01 establishing": 0.0, "SH02 descent": 0.35, "SH03 into the cutaway": 0.3,
                     "SH04 doors open (cutaway)": 0.35, "SH05 tracking the roll-out": 0.35, "SH06 audience eye": 0.75,
                     "SH07 orbit the tableau": 0.8, "SH08 rolling back in (cutaway)": 0.35, "SH09 doors shut": 0.6,
                     "SH10 overhead: what is disputed": 0.15, "SH11 reveals and Ajax teaser": 0.65})
    return cams


EXPOSURE = {}


def key_exposure():
    """per-shot exposure keys (constant), applied after render_settings"""
    vs = scene.view_settings
    for name, t0, t1, cv, cp in SHOTS:
        vs.exposure = 0.15 + EXPOSURE.get(name, 0.0)
        vs.keyframe_insert("exposure", frame=F(t0))
    ad = scene.animation_data
    if ad and ad.action:
        for c in ad.action.fcurves:
            if c.data_path.endswith("exposure"):
                for kp in c.keyframe_points:
                    kp.interpolation = "CONSTANT"


# ----------------------------------------------------------------------------
# compositor: aerial perspective (haze) from the mist pass
# ----------------------------------------------------------------------------
def build_compositor():
    scene.use_nodes = True
    scene.render.film_transparent = True
    vl = scene.view_layers[0]
    vl.use_pass_mist = True
    vl.use_pass_environment = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    mul = nt.nodes.new("CompositorNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.92
    nt.links.new(rl.outputs["Mist"], mul.inputs[0])
    haze = nt.nodes.new("CompositorNodeRGB")
    haze.outputs[0].default_value = (0.56, 0.62, 0.70, 1.0)
    setalpha = nt.nodes.new("CompositorNodeSetAlpha")
    setalpha.mode = "APPLY"
    nt.links.new(haze.outputs[0], setalpha.inputs["Image"])
    nt.links.new(rl.outputs["Alpha"], setalpha.inputs["Alpha"])
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MIX"
    mix.use_alpha = False
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(setalpha.outputs[0], mix.inputs[2])
    keep_a = nt.nodes.new("CompositorNodeSetAlpha")
    keep_a.mode = "REPLACE_ALPHA"
    nt.links.new(mix.outputs[0], keep_a.inputs["Image"])
    nt.links.new(rl.outputs["Alpha"], keep_a.inputs["Alpha"])
    over = nt.nodes.new("CompositorNodeAlphaOver")
    nt.links.new(rl.outputs["Env"], over.inputs[1])
    nt.links.new(keep_a.outputs[0], over.inputs[2])
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.use_alpha = False
    nt.links.new(over.outputs[0], comp.inputs["Image"])


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
    bg.inputs["Strength"].default_value = 0.38
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    w.mist_settings.start = 50.0
    w.mist_settings.depth = 12000.0
    w.mist_settings.falloff = "LINEAR"

    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 4.0
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
    c.samples = 16                       # recommended final: 1280x720, 16 spp + OIDN (see report)
    c.preview_samples = 16
    c.use_adaptive_sampling = False      # measured: slower than fixed samples at <=64 spp here
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    c.denoising_prefilter = "ACCURATE"
    c.max_bounces = 6
    c.diffuse_bounces = 2
    c.glossy_bounces = 2
    c.transmission_bounces = 4
    c.transparent_max_bounces = 6
    c.use_fast_gi = True                 # full GI for the first bounces, AO approximation after
    c.ao_bounces_render = 1
    scene.world.light_settings.distance = 12.0
    c.denoising_quality = "BALANCED"
    c.volume_bounces = 0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    c.sample_clamp_indirect = 8.0
    c.use_light_tree = False             # one sun + sky: the light tree only adds overhead
    r.use_persistent_data = True
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1280, 720, 100
    r.use_overwrite = False              # resumable: re-running skips frames already on disk
    r.use_placeholder = True
    r.filepath = "//frames/ekk_####"
    r.image_settings.file_format = "PNG"
    r.image_settings.color_depth = "8"
    r.image_settings.color_mode = "RGB"
    vs = scene.view_settings
    vs.view_transform = "AgX"
    try:
        vs.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    vs.exposure = 0.15
    scene.display_settings.display_device = "sRGB"
    vl = scene.view_layers[0]
    vl.use_pass_mist = True


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    import time
    t0 = time.time()
    build_terrain()
    build_far_land()
    build_theatron()
    build_acropolis()
    build_city()
    if not LIGHT:
        build_vegetation()
    print("landscape %.1fs" % (time.time() - t0))
    build_skene()
    DOORS.extend(build_doors())
    build_platform()
    couch, matt, cush = build_tableau()
    rec = build_reclining_actor()
    drape_himation_reclining(rec, couch, matt, cush)
    act = build_standing_actor()
    drape_himation_standing(act)
    hands = [build_stagehand("Stagehand A"), build_stagehand("Stagehand B")]
    print("figures %.1fs" % (time.time() - t0))
    build_cutters()
    animate_action()
    build_cameras()
    animate_stagehands(hands, (-0.55, 0.55))
    animate_cutters()
    build_overlays()
    build_world()
    render_settings()
    key_exposure()
    build_compositor()
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    print("SAVED", OUT, "%.1fs" % (time.time() - t0))


main()
