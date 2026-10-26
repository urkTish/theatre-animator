"""Ekkyklema claymation sample: build the stop-motion scene from a COPY of the built 3D scene.

    blender -b --factory-startup --python-exit-code 1 -P clay_build.py -- \
        --src  WORK/scene4_copy.blend      (copy of 3d/build/scene4.blend; never the original)
        --figs V3WORK                      (folder with posed.blend + figures_unpacked.blend)
        --backdrop WORK/backdrop.png       (paint_backdrop.py output)
        --out  WORK/claymation.blend
        [--no-figures]                     (set only, for set look-dev)

Normally run through clay_sample.py, which also paints the backdrop, renders and encodes.

What it does (all reconstruction facts kept: facade 12 x 5 m, door 2.8 x 3.2 m with leaves
swinging inward, platform 2.4 x 1.6 m with a 0.30 m deck on 4 wheels, waiting with its front
edge 1.68 m behind the facade and rolling 2.93 m in 4.0 s with a long ease in and out):
  set      strips the landscape, theatron, overlays, mannequins and cameras; re-materials the
           skene and platform as a hand-made miniature (stained balsa, card, wooden craft wheels,
           brass-wire axles, felt cushions, polymer-clay cup), lays a sand-and-glue ground with
           pebbles and static-grass tufts, and hangs a painted canvas backdrop (curved cyc).
  figures  four MakeHuman bodies (CC0) from the v3 test, re-dressed as plasticine puppets:
           clay hands/feet/faces with fingerprints and tool marks, painted-plaster masks with
           sculpted clay hair and beards, puppet-fabric robes; puppet proportions (bigger heads
           and hands) by bone scale; robes and tunics follow the rig by Surface Deform.
  motion   doors, roll-out, gestures, stagehands; on twos (render every other frame) with
           slight hand-animated irregularity; camera on a motion-control push-in with follow focus.
  output   view layers composite / plate / cast (set as holdout) and the compositor that writes
           plate, cast (RGBA) and matte (+ per-slot matte) PNGs beside the composite.
Characters live in one collection per slot: standing_actor, reclining_figure, stagehand_1,
stagehand_2 (all under the collection "CAST"). Swap one by replacing that collection's contents.
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

sys.stdout.reconfigure(line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
FIG_SCRIPT_DIR = os.path.abspath(os.path.join(HERE, "..", "3d", "experiments", "v3_figures"))

FPS = 24
DURATION = 12.0
F_START, F_END = 1, int(DURATION * FPS)          # 1..288


def F(sec):
    return int(round(sec * FPS)) + 1


# ---- timeline (seconds) --------------------------------------------------------------------
T_DOOR = (1.4, 4.0)            # doors swing inward, fully open before the platform moves
T_ROLL = (4.4, 8.4)            # 4.0 s roll, long ease in/out
T_ACTOR_GESTURE = (7.9, 9.4)   # standing actor presents / addresses the reclining figure
T_RECL_ANSWER = (9.3, 10.7)    # reclining figure answers with his raised hand
PLAT_Y0, PLAT_Y1 = -2.48, 0.45  # Platform ctrl y: front edge -1.68 -> +1.25 (deck depth 1.6)

SLOTS = ["standing_actor", "reclining_figure", "stagehand_1", "stagehand_2"]
SRC_NAMES = {"standing_actor": "Standing actor", "reclining_figure": "Reclining actor",
             "stagehand_1": "Stagehand A", "stagehand_2": "Stagehand B"}

BACKDROP_ARC, BACKDROP_H = 64.0, 20.0        # metres covered by the painting (paint_backdrop.py)
BACKDROP_C, BACKDROP_R = Vector((0.0, 7.0, 0.0)), 21.0


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {}
    i = 0
    while i < len(a):
        if a[i].startswith("--"):
            if i + 1 < len(a) and not a[i + 1].startswith("--"):
                o[a[i][2:]] = a[i + 1]
                i += 2
            else:
                o[a[i][2:]] = True
                i += 1
        else:
            i += 1
    return o


def srgb(*c):
    if len(c) == 1 and isinstance(c[0], str):
        h = c[0].lstrip("#")
        c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    out = []
    for v in c:
        v = v / 255.0
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def link_to(ob, c):
    for u in list(ob.users_collection):
        u.objects.unlink(ob)
    c.objects.link(ob)


def mesh_obj(name, bm, c, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


# =============================================================================================
# node helpers
# =============================================================================================
class NT:
    """tiny node-tree builder: n(type, **inputs) creates a node and sets/links inputs"""

    def __init__(self, mat):
        self.t = mat.node_tree
        self.N = self.t.nodes
        self.L = self.t.links

    def n(self, typ, _props=None, **inputs):
        nd = self.N.new(typ)
        for k, v in (_props or {}).items():
            setattr(nd, k, v)
        for k, v in inputs.items():
            self.set(nd, k, v)
        return nd

    def set(self, nd, key, v):
        sock = nd.inputs[key] if isinstance(key, int) else nd.inputs.get(key.replace("_", " ")) or nd.inputs[key]
        if isinstance(v, bpy.types.NodeSocket):
            self.L.new(v, sock)
        elif isinstance(v, bpy.types.Node):
            self.L.new(v.outputs[0], sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, clamp=False):
        nd = self.N.new("ShaderNodeMath")
        nd.operation = op
        nd.use_clamp = clamp
        self.set(nd, 0, a)
        self.set(nd, 1, b)
        return nd.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        nd = self.N.new("ShaderNodeMix")
        nd.data_type = "RGBA"
        nd.blend_type = blend
        self.set(nd, 0, fac)
        self.set(nd, 6, a)
        self.set(nd, 7, b)
        return nd.outputs[2]

    def vmath(self, op, a, b=(0, 0, 0)):
        nd = self.N.new("ShaderNodeVectorMath")
        nd.operation = op
        self.set(nd, 0, a)
        self.set(nd, 1, b)
        return nd.outputs[0] if op not in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else nd.outputs["Value"]

    def ramp(self, fac, stops):
        nd = self.N.new("ShaderNodeValToRGB")
        cr = nd.color_ramp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position = stops[0][0]
        cr.elements[0].color = stops[0][1]
        for p, c in stops[1:]:
            e = cr.elements.new(p)
            e.color = c
        self.set(nd, 0, fac)
        return nd.outputs[0]

    def bsdf(self, _props=None, **kw):
        b = self.N.get("Principled BSDF") or self.N.new("ShaderNodeBsdfPrincipled")
        for k, v in (_props or {}).items():
            setattr(b, k, v)
        for k, v in kw.items():
            self.set(b, k, v)
        return b


def new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, NT(m)


def assign(ob, mat):
    me = ob.data
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0


# ---- a shared "boil" value: changes on every held pose (twos), used by clay and set shaders --
def boil_group():
    """node group 'BOIL' with one output, keyed to a new random value every 2 frames (constant
    interpolation): handled clay and hand-dressed sand shift very slightly between poses."""
    g = bpy.data.node_groups.get("BOIL")
    if g:
        return g
    g = bpy.data.node_groups.new("BOIL", "ShaderNodeTree")
    g.interface.new_socket("Value", in_out="OUTPUT", socket_type="NodeSocketFloat")
    out = g.nodes.new("NodeGroupOutput")
    v = g.nodes.new("ShaderNodeValue")
    v.name = "boil"
    g.links.new(v.outputs[0], out.inputs[0])
    rnd = random.Random(11)
    for f in range(F_START, F_END + 2, 2):
        v.outputs[0].default_value = rnd.uniform(0, 100)
        v.outputs[0].keyframe_insert("default_value", frame=f)
    fc = g.animation_data.action.fcurves[0]
    for k in fc.keyframe_points:
        k.interpolation = "CONSTANT"
    return g


def boil(nt):
    nd = nt.N.new("ShaderNodeGroup")
    nd.node_tree = boil_group()
    return nd.outputs[0]


# =============================================================================================
# set materials: a hand-made miniature
# =============================================================================================
def mat_balsa(name, base, dark, plank_axis="x", grain_axis="z", plank_w=0.24, gap=0.012, rough=0.78,
              stain_var=0.22, wash=0.35, seed=1.0, gap_bump=0.6, pencil=False):
    """stained balsa/basswood strip-wood: planks along plank_axis of width plank_w (m, scene
    units), grain running along grain_axis, per-plank stain variation, dark wash in the gaps,
    dry-brushed lighter edges, soft fibrous bump."""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    sep = t.n("ShaderNodeSeparateXYZ", Vector=tc.outputs["Object"])
    ax = {"x": 0, "y": 1, "z": 2}
    pa = sep.outputs[ax[plank_axis]]
    # plank index and position across the plank
    u = t.math("DIVIDE", pa, plank_w)
    idx = t.math("FLOOR", u)
    fr = t.math("SUBTRACT", u, idx)
    wn = t.n("ShaderNodeTexWhiteNoise", {"noise_dimensions": "1D"}, W=t.math("ADD", idx, seed))
    # grain: stretch noise along the grain axis
    sc = [70.0, 70.0, 70.0]
    sc[ax[grain_axis]] = 3.0
    mp = t.n("ShaderNodeMapping", Vector=tc.outputs["Object"], Scale=sc)
    off = t.n("ShaderNodeCombineXYZ", X=t.math("MULTIPLY", wn.outputs["Value"], 13.0), Y=0.0, Z=0.0)
    mpv = t.vmath("ADD", mp.outputs[0], off.outputs[0])
    grain = t.n("ShaderNodeTexNoise", Vector=mpv, Scale=1.0, Detail=6.0, Roughness=0.62, Distortion=0.4)
    fine = t.n("ShaderNodeTexWave", {"wave_type": "BANDS", "bands_direction": "X" if grain_axis != "x" else "Y"},
               Vector=mpv, Scale=4.0, Distortion=6.0, Detail=4.0)
    # gap mask (0 in the gap)
    g0 = t.math("GREATER_THAN", fr, gap / plank_w)
    g1 = t.math("LESS_THAN", fr, 1.0 - gap / plank_w)
    plankmask = t.math("MULTIPLY", g0, g1)
    edge = t.math("MINIMUM", fr, t.math("SUBTRACT", 1.0, fr))
    edge_hi = t.math("LESS_THAN", edge, 0.09)
    # colour: base stain per plank, darker wash pooling in the grain, dark gaps, dry-brush edges
    c_plank = t.mix(t.math("MULTIPLY", wn.outputs["Value"], stain_var * 2.5), base, dark)
    c_grain = t.mix(t.math("MULTIPLY", grain.outputs["Fac"], wash), c_plank, dark, "MULTIPLY")
    c_fine = t.mix(t.math("MULTIPLY", fine.outputs["Fac"], 0.12), c_grain, dark)
    hi = tuple(min(1.0, c * 1.45) for c in base[:3]) + (1.0,)
    c_edge = t.mix(t.math("MULTIPLY", edge_hi, 0.35), c_fine, hi)
    gapcol = tuple(c * 0.25 for c in dark[:3]) + (1.0,)
    col = t.mix(plankmask, gapcol, c_edge)
    # blotchy wash variation over the whole piece (uneven brushwork)
    blot = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=1.3, Detail=3.0)
    col = t.mix(t.math("MULTIPLY", t.math("SUBTRACT", blot.outputs["Fac"], 0.45), 0.6), col, dark, "MULTIPLY")
    h = t.math("ADD", t.math("MULTIPLY", grain.outputs["Fac"], 0.5), t.math("MULTIPLY", plankmask, 1.0))
    bump = t.n("ShaderNodeBump", Strength=gap_bump, Distance=0.004, Height=h)
    t.bsdf(**{"Base Color": col, "Roughness": rough, "Specular IOR Level": 0.25, "Normal": bump.outputs[0]})
    return m


def mat_strips(name, base, dark, light, grain_axis="z", rough=0.8, seed=0.0):
    """individual stained strip-wood boards (each board has a random 'board_rand' attribute):
    per-board stain, coarse balsa grain (big at puppet scale), wash pooling, dry-brushed light
    flecks, a few pencil-mark lines and glue sheen spots"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    at = t.n("ShaderNodeAttribute", {"attribute_name": "board_rand", "attribute_type": "GEOMETRY"})
    r = at.outputs["Fac"]
    ax = {"x": 0, "y": 1, "z": 2}[grain_axis]
    sc = [130.0, 130.0, 130.0]
    sc[ax] = 3.0
    mp = t.n("ShaderNodeMapping", Vector=tc.outputs["Object"], Scale=sc)
    off = t.n("ShaderNodeCombineXYZ", X=t.math("MULTIPLY", r, 37.0), Y=t.math("MULTIPLY", r, 11.0), Z=seed)
    v = t.vmath("ADD", mp.outputs[0], off.outputs[0])
    grain = t.n("ShaderNodeTexNoise", Vector=v, Scale=1.0, Detail=7.0, Roughness=0.66, Distortion=0.6)
    rings = t.n("ShaderNodeTexWave", {"wave_type": "BANDS", "bands_direction": "X" if grain_axis != "x" else "Y"},
                Vector=v, Scale=2.2, Distortion=9.0, Detail=5.0, Detail_Roughness=0.7)
    # per-board stain: a ramp between light honey, mid and dark walnut
    mid_l = tuple(base[i] * 0.6 + light[i] * 0.4 for i in range(3)) + (1.0,)
    mid_d = tuple(base[i] * 0.7 + dark[i] * 0.3 for i in range(3)) + (1.0,)
    c_board = t.ramp(r, [(0.0, mid_l), (0.5, base), (1.0, mid_d)])
    grey = t.mix(t.math("MULTIPLY", t.math("GREATER_THAN", r, 0.9), 0.3), c_board, srgb(124, 116, 104))
    c = t.mix(t.math("MULTIPLY", grain.outputs["Fac"], 0.55), grey, dark, "MULTIPLY")
    c = t.mix(t.math("MULTIPLY", rings.outputs["Fac"], 0.22), c, dark)
    blot = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=0.9, Detail=3.0)
    c = t.mix(t.math("MULTIPLY", t.math("SUBTRACT", blot.outputs["Fac"], 0.42), 0.8), c, dark, "MULTIPLY")
    # dry-brush flecks of light paint on the raised grain
    fl = t.n("ShaderNodeTexNoise", Vector=v, Scale=3.5, Detail=2.0)
    fleck = t.math("GREATER_THAN", t.math("ADD", fl.outputs["Fac"], t.math("MULTIPLY", grain.outputs["Fac"], 0.4)), 0.86)
    c = t.mix(t.math("MULTIPLY", fleck, 0.5), c, light)
    # vertical dry-brush streaks of a paler wash (brush dragged along the strip)
    sk = [6.0, 6.0, 6.0]
    sk[ax] = 0.35
    mps = t.n("ShaderNodeMapping", Vector=tc.outputs["Object"], Scale=sk)
    streak = t.n("ShaderNodeTexNoise", Vector=t.vmath("ADD", mps.outputs[0], off.outputs[0]), Scale=1.0, Detail=2.0)
    c = t.mix(t.math("MULTIPLY", t.math("GREATER_THAN", streak.outputs["Fac"], 0.6), 0.25), c, light)
    c = t.mix(t.math("MULTIPLY", t.math("LESS_THAN", streak.outputs["Fac"], 0.36), 0.25), c, dark)
    h = t.math("ADD", t.math("MULTIPLY", grain.outputs["Fac"], 0.7), t.math("MULTIPLY", rings.outputs["Fac"], 0.3))
    bump = t.n("ShaderNodeBump", Strength=0.5, Distance=0.004, Height=h)
    rough_n = t.math("ADD", rough, t.math("MULTIPLY", t.math("SUBTRACT", grain.outputs["Fac"], 0.5), 0.25))
    t.bsdf(**{"Base Color": c, "Roughness": rough_n, "Specular IOR Level": 0.3, "Normal": bump.outputs[0]})
    return m


def build_boards(c):
    """the facade as hand-cut strip-wood boards glued on a card backing: uneven widths, small
    gaps, slightly out of true, ragged ends; door opening and frame kept clear (R2: 2.8 x 3.2 m)"""
    rnd = random.Random(42)
    bm = bmesh.new()
    lay = bm.faces.layers.float.new("board_rand")
    x = -6.0
    y0, y1 = -0.052, -0.026
    while x < 6.0:
        w = rnd.uniform(0.2, 0.31)
        gap = rnd.uniform(0.006, 0.016)
        x0, x1 = x + gap / 2, min(6.0, x + w - gap / 2)
        x += w
        if x1 - x0 < 0.05:
            continue
        cx = (x0 + x1) / 2
        segs = []
        if x1 > -1.43 and x0 < 1.43:          # over the doorway: only above the frame
            segs.append((3.5 + rnd.uniform(-0.01, 0.01), 4.96 + rnd.uniform(-0.03, 0.01)))
        else:
            segs.append((0.012 + rnd.uniform(0, 0.025), 4.96 + rnd.uniform(-0.035, 0.01)))
        r = rnd.random()
        for z0, z1 in segs:
            g = bmesh.ops.create_cube(bm, size=1.0)
            vs = g["verts"]
            tilt = math.radians(rnd.gauss(0, 0.35))
            twist = math.radians(rnd.gauss(0, 0.4))
            dy = rnd.uniform(-0.004, 0.004)
            for v in vs:
                lx = v.co.x * (x1 - x0)
                lz = (v.co.z + 0.5) * (z1 - z0) + z0
                ly = (v.co.y + 0.5) * (y1 - y0) + y0 + dy
                # out of true: rotate about the board's foot (in the facade plane) and twist
                px = cx + lx * math.cos(tilt) + (lz - z0) * math.sin(tilt)
                pz = lz
                py = ly + lx * math.sin(twist)
                v.co = Vector((px, py, pz))
            for f in {f for v in vs for f in v.link_faces}:
                f[lay] = r
    ob = mesh_obj("MIN facade strip-wood boards", bm, c)
    md = ob.modifiers.new("soft edges", "BEVEL")
    md.width = 0.006
    md.segments = 2
    md.limit_method = "ANGLE"
    return ob


def mat_card(name, color, rough=0.85, fibres=0.25):
    """painted card / mount board: flat paint over a faint fibrous paper bump"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=60.0, Detail=8.0, Roughness=0.7)
    blot = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=2.0, Detail=2.0)
    col = t.mix(t.math("MULTIPLY", blot.outputs["Fac"], 0.25), color, (0.0, 0.0, 0.0, 1.0))
    bump = t.n("ShaderNodeBump", Strength=fibres, Distance=0.003, Height=nz.outputs["Fac"])
    t.bsdf(**{"Base Color": col, "Roughness": rough, "Specular IOR Level": 0.2, "Normal": bump.outputs[0]})
    return m


def mat_sand(name):
    """fine sand sprinkled on PVA over a painted board: grains are big at puppet scale"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    p = tc.outputs["Object"]
    v1 = t.n("ShaderNodeTexVoronoi", {"feature": "F1"}, Vector=p, Scale=150.0, Randomness=1.0)
    v2 = t.n("ShaderNodeTexVoronoi", {"feature": "F1"}, Vector=p, Scale=34.0, Randomness=1.0)
    big = t.n("ShaderNodeTexNoise", Vector=p, Scale=0.55, Detail=4.0, Roughness=0.6)
    mid = t.n("ShaderNodeTexNoise", Vector=p, Scale=4.0, Detail=5.0)
    c_base = t.ramp(big.outputs["Fac"], [(0.3, srgb(176, 142, 102)), (0.5, srgb(196, 166, 124)), (0.7, srgb(166, 128, 90))])
    c = t.mix(t.math("MULTIPLY", mid.outputs["Fac"], 0.35), c_base, srgb(126, 98, 70))
    # individual grains: random tint per cell
    c = t.mix(0.35, c, v1.outputs["Color"], "OVERLAY")
    c = t.mix(t.math("MULTIPLY", t.math("GREATER_THAN", v2.outputs["Color"], 0.93), 0.6), c, srgb(222, 206, 178))
    gr = t.math("POWER", t.math("SUBTRACT", 1.0, t.math("MINIMUM", t.math("MULTIPLY", v1.outputs["Distance"], 1.6), 1.0)), 0.6)
    peb = t.math("POWER", t.math("SUBTRACT", 1.0, t.math("MINIMUM", t.math("MULTIPLY", v2.outputs["Distance"], 2.2), 1.0)), 1.5)
    h = t.math("ADD", t.math("MULTIPLY", gr, 0.5), t.math("MULTIPLY", peb, 0.35))
    h = t.math("ADD", h, t.math("MULTIPLY", mid.outputs["Fac"], 0.4))
    bump = t.n("ShaderNodeBump", Strength=0.9, Distance=0.012, Height=h)
    t.bsdf(**{"Base Color": c, "Roughness": 0.93, "Specular IOR Level": 0.2, "Normal": bump.outputs[0]})
    return m


def mat_felt(name, color, fuzz=0.6):
    """felt / wool puppet fabric: soft sheen, fuzzy fibre bump"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=180.0, Detail=10.0, Roughness=0.8)
    nz2 = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=8.0, Detail=3.0)
    col = t.mix(t.math("MULTIPLY", nz2.outputs["Fac"], 0.25), color, (0, 0, 0, 1))
    bump = t.n("ShaderNodeBump", Strength=0.35, Distance=0.004, Height=nz.outputs["Fac"])
    t.bsdf(**{"Base Color": col, "Roughness": 0.95, "Sheen Weight": fuzz, "Sheen Roughness": 0.6,
              "Specular IOR Level": 0.15, "Normal": bump.outputs[0]})
    return m


def mat_painted(name, color, rough=0.45, spec=0.5, bump=0.15, scale=40.0):
    """enamel / acrylic paint on a small prop (brush texture)"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=scale, Detail=4.0)
    b = t.n("ShaderNodeBump", Strength=bump, Distance=0.003, Height=nz.outputs["Fac"])
    t.bsdf(**{"Base Color": color, "Roughness": rough, "Specular IOR Level": spec, "Normal": b.outputs[0]})
    return m


def mat_brass(name):
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=30.0, Detail=3.0)
    col = t.mix(t.math("MULTIPLY", nz.outputs["Fac"], 0.6), srgb(176, 140, 76), srgb(90, 70, 44))
    t.bsdf(**{"Base Color": col, "Metallic": 1.0, "Roughness": 0.42})
    return m


def mat_backdrop(name, img_path):
    """painted canvas flat: image + canvas weave bump, lit by its own floods"""
    m, t = new_mat(name)
    tc = t.n("ShaderNodeTexCoord")
    tex = t.n("ShaderNodeTexImage", Vector=tc.outputs["UV"])
    tex.image = bpy.data.images.load(img_path, check_existing=True)
    tex.extension = "EXTEND"
    weave = t.n("ShaderNodeTexWave", {"wave_type": "BANDS", "bands_direction": "X"}, Vector=tc.outputs["UV"], Scale=900.0)
    weave2 = t.n("ShaderNodeTexWave", {"wave_type": "BANDS", "bands_direction": "Y"}, Vector=tc.outputs["UV"], Scale=300.0)
    h = t.math("ADD", weave.outputs["Fac"], weave2.outputs["Fac"])
    b = t.n("ShaderNodeBump", Strength=0.15, Distance=0.01, Height=h)
    t.bsdf(**{"Base Color": tex.outputs["Color"], "Roughness": 0.92, "Specular IOR Level": 0.1, "Normal": b.outputs[0],
              "Emission Color": tex.outputs["Color"], "Emission Strength": 0.55})
    return m


# =============================================================================================
# set
# =============================================================================================
def strip_scene():
    sc = bpy.context.scene
    keep_colls = {"Skene", "Platform"}
    for o in list(bpy.data.objects):
        for md in list(getattr(o, "modifiers", [])):
            if md.type == "BOOLEAN" and md.object and md.object.name.startswith("Section cutter"):
                o.modifiers.remove(md)
    for cname in ["Landscape", "Theatron", "Vegetation", "Overlays", "Cameras", "Figures", "Lights", "Library"]:
        c = bpy.data.collections.get(cname)
        if not c:
            continue
        for ch in list(c.children_recursive):
            for o in list(ch.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(ch)
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)
    for o in list(sc.objects):
        if not any(c.name in keep_colls for c in o.users_collection):
            bpy.data.objects.remove(o, do_unlink=True)
    sc.timeline_markers.clear()
    bpy.data.orphans_purge(do_recursive=True)


def remap_images(assets_dir):
    for im in bpy.data.images:
        if im.packed_file or not im.filepath:
            continue                      # packed images keep their data (and alpha)
        fp = im.filepath
        if fp.startswith("//../assets/"):
            im.filepath = os.path.join(assets_dir, fp[len("//../assets/"):])


def restyle_set():
    O = bpy.data.objects
    façade = mat_balsa("MIN balsa facade boards", srgb(150, 108, 72), srgb(84, 58, 40), plank_axis="x",
                       grain_axis="z", plank_w=0.26, gap=0.014, seed=3.0)
    posts = mat_balsa("MIN balsa posts", srgb(122, 86, 58), srgb(66, 46, 32), plank_axis="x", grain_axis="z",
                      plank_w=5.0, gap=0.0, seed=7.0, gap_bump=0.3)
    rails = mat_balsa("MIN balsa rails", srgb(122, 86, 58), srgb(66, 46, 32), plank_axis="z", grain_axis="x",
                      plank_w=5.0, gap=0.0, seed=9.0, gap_bump=0.3)
    leaves = mat_balsa("MIN balsa door leaves", srgb(142, 94, 62), srgb(78, 50, 34), plank_axis="x",
                       grain_axis="z", plank_w=0.235, gap=0.012, seed=5.0)
    interior = mat_balsa("MIN balsa interior (unpainted back)", srgb(96, 74, 54), srgb(46, 34, 24), plank_axis="x",
                         grain_axis="z", plank_w=0.3, gap=0.01, seed=11.0)
    roof = mat_card("MIN card roof", srgb(112, 90, 70))
    deck = mat_balsa("MIN balsa platform deck", srgb(170, 132, 92), srgb(98, 72, 50), plank_axis="y",
                     grain_axis="x", plank_w=0.2, gap=0.012, seed=13.0)
    frame = mat_balsa("MIN balsa platform frame", srgb(118, 84, 58), srgb(62, 44, 30), plank_axis="z",
                      grain_axis="x", plank_w=5.0, gap=0.0, seed=17.0, gap_bump=0.3)
    wheels = mat_painted("MIN craft wheel (stained)", srgb(112, 74, 46), rough=0.6, spec=0.3, bump=0.25, scale=25.0)
    couch = mat_painted("MIN couch (painted balsa)", srgb(112, 70, 44), rough=0.55, spec=0.35, bump=0.25, scale=30.0)
    brass = mat_brass("MIN brass wire")
    iron = mat_painted("MIN iron (painted wire)", srgb(40, 36, 34), rough=0.5, spec=0.4)
    mattress = mat_felt("MIN felt mattress", srgb(222, 210, 182))
    cush_r = mat_felt("MIN felt cushion madder", srgb(160, 52, 38))
    cush_b = mat_felt("MIN felt cushion woad", srgb(52, 74, 116))
    cloth = mat_felt("MIN felt folded cloth", srgb(60, 82, 124))
    kylix = mat_painted("MIN polymer-clay kylix (gloss black)", srgb(22, 18, 16), rough=0.18, spec=0.7, bump=0.05)
    table = {
        "Skene boarding": façade, "Skene posts": posts, "Skene rails": rails, "Skene door frame": posts,
        "Skene roof": roof, "Skene joists": interior, "Skene mid beam": interior, "Skene interior posts": interior,
        "Door leaf E": leaves, "Door leaf W": leaves, "Door ring E": iron, "Door ring W": iron,
        "Platform deck": deck, "Platform frame": frame, "Platform axles": brass,
        "Wheel WB": wheels, "Wheel WF": wheels, "Wheel EB": wheels, "Wheel EF": wheels,
        "Couch (kline)": couch, "Stool (diphros)": couch, "Mattress": mattress, "Cushion 0": cush_r,
        "Cushion 1": cush_b, "Folded cloth": cloth, "Kylix": kylix,
    }
    for n, m in table.items():
        ob = O.get(n)
        if ob:
            assign(ob, m)
            for md in ob.modifiers:
                if md.type == "BEVEL":
                    md.width = max(md.width, 0.012)          # soft, sanded balsa edges
                    md.segments = max(md.segments, 2)
    boards = build_boards(bpy.data.collections["Skene"])
    assign(boards, mat_strips("MIN strip-wood boards (stained)", srgb(138, 104, 76), srgb(70, 50, 38),
                              srgb(188, 158, 124), "z"))
    # the boarding's back face is the interior: give inward faces the darker unpainted balsa
    b = O["Skene boarding"]
    b.data.materials.append(interior)
    for p in b.data.polygons:
        if p.normal.y < -0.5 or (p.center.y < -0.3 and abs(p.normal.y) < 0.5 and abs(p.center.x) < 5.9):
            p.material_index = 1


def build_ground(c):
    m = mat_sand("MIN sand ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    for v in bm.verts:
        v.co.x *= 36.0
        v.co.y = v.co.y * 24.0 - 2.0
    ob = mesh_obj("MIN ground (sand on board)", bm, c, m)
    return ob


def build_backdrop(c, img):
    """curved painted canvas (a cyc) behind the skene; UVs in painting metres"""
    m = mat_backdrop("MIN painted backdrop", img)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    nseg = 64
    ang = BACKDROP_ARC / BACKDROP_R
    rows = []
    for j, z in enumerate((0.0, BACKDROP_H)):
        row = []
        for i in range(nseg + 1):
            a = -ang / 2 + ang * i / nseg
            p = BACKDROP_C + Vector((math.sin(a) * BACKDROP_R, -math.cos(a) * BACKDROP_R, z))
            row.append(bm.verts.new(p))
        rows.append(row)
    for i in range(nseg):
        f = bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
        for lp in f.loops:
            k = rows[0].index(lp.vert) if lp.vert in rows[0] else rows[1].index(lp.vert)
            lp[uvl].uv = (k / nseg, 0.0 if lp.vert in rows[0] else 1.0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = mesh_obj("MIN painted backdrop (canvas cyc)", bm, c, m)
    # normals must face the stage (+y side at the centre)
    me = ob.data
    if me.polygons[nseg // 2].normal.y < 0:
        for p in me.polygons:
            p.flip()
    ob.visible_shadow = False
    return ob


def scatter_dressing(c, seed=5):
    """pebbles and static-grass tufts glued on the sand, kept clear of the platform's path,
    the doorway and the actor's spot"""
    rnd = random.Random(seed)
    peb_m = mat_painted("MIN pebble (grit)", srgb(150, 132, 112), rough=0.85, spec=0.2, bump=0.4, scale=60.0)
    tuft_m, t = new_mat("MIN static grass tuft")
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=3.0)
    col = t.ramp(nz.outputs["Fac"], [(0.35, srgb(150, 140, 78)), (0.65, srgb(118, 112, 60))])
    t.bsdf(**{"Base Color": col, "Roughness": 0.7, "Specular IOR Level": 0.3,
              "Subsurface Weight": 0.2, "Subsurface Radius": (0.4, 0.5, 0.2), "Subsurface Scale": 0.01})

    def clear(x, y):
        if -1.55 < x < 1.55 and -0.4 < y < 1.75:     # platform path out + its stop position
            return False
        if 1.45 < x < 2.65 and 0.5 < y < 1.8:          # standing actor
            return False
        if -1.7 < x < 1.7 and -0.25 < y < 0.25:        # threshold
            return False
        if y < 0.05 and -6.2 < x < 6.2:                # under the skene
            return False
        return True

    bm = bmesh.new()
    n = 0
    while n < 260:
        x, y = rnd.uniform(-9, 9), rnd.uniform(-0.1, 9)
        if not clear(x, y):
            continue
        r = rnd.uniform(0.015, 0.05) * (2.2 if rnd.random() < 0.08 else 1.0)
        geom = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
        vs = geom["verts"]
        for v in vs:
            v.co = Vector((v.co.x * rnd.uniform(0.8, 1.3), v.co.y * rnd.uniform(0.8, 1.3), v.co.z * 0.55))
            v.co += Vector((x, y, r * 0.15))
        n += 1
    peb = mesh_obj("MIN pebbles", bm, c, peb_m)
    for p in peb.data.polygons:
        p.use_smooth = True
    # tufts: clusters of thin tapered blades (static grass), denser along the facade foot
    bm = bmesh.new()
    nt_ = 0
    while nt_ < 70:
        if rnd.random() < 0.6:
            x, y = rnd.uniform(-6.3, 6.3), rnd.uniform(0.08, 0.5)
        else:
            x, y = rnd.uniform(-8, 8), rnd.uniform(0.3, 7)
        if not clear(x, y):
            continue
        nt_ += 1
        hgt = rnd.uniform(0.07, 0.18)
        for k in range(rnd.randint(14, 26)):
            a = rnd.uniform(0, 2 * math.pi)
            rr = rnd.uniform(0, 0.05)
            bx, by = x + math.cos(a) * rr, y + math.sin(a) * rr
            lean = Vector((math.cos(a), math.sin(a), 0)) * rnd.uniform(0.2, 0.7)
            top = Vector((bx, by, 0)) + (Vector((0, 0, 1)) + lean).normalized() * hgt * rnd.uniform(0.6, 1.1)
            w = 0.006
            side = Vector((-math.sin(a), math.cos(a), 0)) * w
            v0 = bm.verts.new(Vector((bx, by, 0)) - side)
            v1 = bm.verts.new(Vector((bx, by, 0)) + side)
            v2 = bm.verts.new(top)
            bm.faces.new((v0, v1, v2))
    tufts = mesh_obj("MIN static-grass tufts", bm, c, tuft_m)
    return peb, tufts


# =============================================================================================
# lights: a practical miniature rig (warm fresnel key, white bounce card, cyc floods, a kicker)
# =============================================================================================
def aim(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def add_light(c, name, typ, loc, target, energy, color, **kw):
    ld = bpy.data.lights.new(name, typ)
    ld.energy = energy
    ld.color = color[:3]
    for k, v in kw.items():
        setattr(ld, k, v)
    ob = bpy.data.objects.new(name, ld)
    c.objects.link(ob)
    ob.location = loc
    aim(ob, target)
    return ob


def build_lights(c):
    L = {}
    L["key"] = add_light(c, "LGT key fresnel (warm, low sun from the west)", "SPOT", (-9.5, 5.0, 6.2),
                         (0.6, 0.4, 0.9), 6500.0, (1.0, 0.77, 0.54), spot_size=math.radians(64), spot_blend=0.8,
                         shadow_soft_size=0.25)
    L["fill"] = add_light(c, "LGT bounce card (white, camera right)", "AREA", (8.0, 12.0, 2.5), (0.5, 0.0, 1.4),
                          650.0, (0.86, 0.92, 1.0), shape="RECTANGLE", size=5.0, size_y=3.0)
    L["fill"].data.use_shadow = True
    L["kick"] = add_light(c, "LGT kicker (warm, behind right, over the roof)", "SPOT", (5.0, -1.2, 10.0),
                          (1.0, 1.0, 1.0), 2800.0, (1.0, 0.86, 0.7), spot_size=math.radians(35), spot_blend=0.7,
                          shadow_soft_size=0.3)
    L["cyc1"] = add_light(c, "LGT cyc flood L", "AREA", (-8.0, -6.0, 13.0), (-8.0, -13.0, 7.0), 1200.0,
                          (0.95, 0.96, 1.0), shape="RECTANGLE", size=10.0, size_y=2.0)
    L["cyc2"] = add_light(c, "LGT cyc flood R", "AREA", (8.0, -6.0, 13.0), (8.0, -13.0, 7.0), 1200.0,
                          (0.95, 0.96, 1.0), shape="RECTANGLE", size=10.0, size_y=2.0)
    L["inside"] = add_light(c, "LGT practical inside the skene (dim)", "AREA", (0.0, -3.0, 4.3), (0.0, -2.0, 0.0),
                            60.0, (1.0, 0.85, 0.7), shape="DISK", size=1.5)
    return L


def build_cookie(c, key, dist=3.2, up=1.0, size=(4.5, 3.0)):
    """a leaf cookie (cucoloris) in the upper part of the key's beam: soft dapple, as if the low
    sun came through an olive branch, on the upper facade only (the tableau stays clean)"""
    d = (Vector((0.6, 0.4, 0.9)) - key.location).normalized()
    side = d.cross(Vector((0, 0, 1))).normalized()
    upv = side.cross(d).normalized()
    if upv.z < 0:
        upv = -upv
    ctr = key.location + d * dist + upv * up
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0] * 2, v.co.y * size[1] * 2, 0))
    m, t = new_mat("MIN cookie (leaf cutout card)")
    tc = t.n("ShaderNodeTexCoord")
    nz = t.n("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=4.2, Detail=6.0, Roughness=0.65, Distortion=0.4)
    leaf = t.math("GREATER_THAN", nz.outputs["Fac"], 0.585)
    tr = t.n("ShaderNodeBsdfTransparent")
    df = t.n("ShaderNodeBsdfDiffuse", Color=(0.02, 0.02, 0.02, 1))
    mx = t.n("ShaderNodeMixShader", Fac=leaf)
    t.L.new(tr.outputs[0], mx.inputs[1])
    t.L.new(df.outputs[0], mx.inputs[2])
    out = t.N.get("Material Output")
    t.L.new(mx.outputs[0], out.inputs["Surface"])
    ob = mesh_obj("LGT cookie (leaf cucoloris)", bm, c, m)
    ob.location = ctr
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    for a in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(ob, a, False)
    return ob


def set_world():
    w = bpy.data.worlds.get("MIN studio") or bpy.data.worlds.new("MIN studio")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = srgb(70, 66, 62)
    bg.inputs["Strength"].default_value = 0.12
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])
    bpy.context.scene.world = w


# =============================================================================================
# animation of the set: doors, roll-out; on twos with a hand-moved irregularity
# =============================================================================================
def ease_in_out(t, p=2.6):
    """long, symmetric ease (no overshoot); p > 2 = longer ease than smoothstep"""
    t = min(1.0, max(0.0, t))
    return t ** p / (t ** p + (1 - t) ** p)


def key_values(ob, path, index, frames_vals):
    ob.animation_data_create()
    for f, v in frames_vals:
        arr = getattr(ob, path)
        arr[index] = v
        ob.keyframe_insert(path, index=index, frame=f)
    fc = ob.animation_data.action.fcurves.find(path, index=index)
    for k in fc.keyframe_points:
        k.interpolation = "LINEAR"


def animate_set():
    O = bpy.data.objects
    rnd = random.Random(3)
    for n in ("Door hinge E", "Door hinge W", "Platform ctrl"):
        O[n].animation_data_clear()
    # doors: keyed on every held pose (odd frames) with a slightly uneven hand-moved spacing
    f0, f1 = F(T_DOOR[0]), F(T_DOOR[1])
    vals_e, vals_w = [], []
    for f in range(F_START, F_END + 1, 2):
        t = (f - f0) / (f1 - f0)
        e = ease_in_out(t, 2.2)
        if 0.02 < e < 0.98:
            e += rnd.uniform(-0.006, 0.006)
        e2 = ease_in_out((f - f0 - 1.0) / (f1 - f0), 2.2)       # the west leaf a hair behind
        vals_e.append((f, math.radians(90) * e))
        vals_w.append((f, -math.radians(90) * e2))
    key_values(O["Door hinge E"], "rotation_euler", 2, vals_e)
    key_values(O["Door hinge W"], "rotation_euler", 2, vals_w)
    # platform: 2.93 m in 4.0 s
    r0, r1 = F(T_ROLL[0]), F(T_ROLL[1])
    vals = []
    for f in range(F_START, F_END + 1, 2):
        e = ease_in_out((f - r0) / (r1 - r0), 2.6)
        if 0.01 < e < 0.99:
            e += rnd.uniform(-0.002, 0.002)
        vals.append((f, PLAT_Y0 + (PLAT_Y1 - PLAT_Y0) * e))
    vals[-1] = (vals[-1][0], PLAT_Y1)
    key_values(O["Platform ctrl"], "location", 1, vals)


# =============================================================================================
# camera: motion-control push-in with follow focus
# =============================================================================================
CAM_LOCK = (1.4, 8.4)   # locked off before and after: the plate is static there (rendered once)
CAM_KEYS = [  # (sec, location, target, lens): motion-control push-in between the locks
    (0.0, (1.6, 15.2, 3.05), (0.45, -0.4, 2.35), 36.0),
    (CAM_LOCK[0], (1.6, 15.2, 3.05), (0.45, -0.4, 2.35), 36.0),
    (CAM_LOCK[1], (1.3, 8.4, 2.0), (0.95, 0.35, 1.1), 40.0),
    (12.0, (1.3, 8.4, 2.0), (0.95, 0.35, 1.1), 40.0),
]
FOCUS_KEYS = [(0.0, (0.3, -0.2, 1.5)), (CAM_LOCK[0], (0.3, -0.2, 1.5)), (4.4, (0.2, -0.6, 1.2)),
              (CAM_LOCK[1], (0.8, 0.95, 1.2)), (12.0, (0.8, 0.95, 1.2))]


def build_camera(c):
    cd = bpy.data.cameras.new("CAM clay main")
    cam = bpy.data.objects.new("CAM clay main", cd)
    c.objects.link(cam)
    tgt = bpy.data.objects.new("CAM clay main target", None)
    foc = bpy.data.objects.new("CAM clay main focus", None)
    for e in (tgt, foc):
        c.objects.link(e)
        e.empty_display_size = 0.2
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    cd.sensor_width = 36.0
    cd.dof.use_dof = True
    cd.dof.focus_object = foc
    cd.dof.aperture_fstop = 0.5          # scene units: like a ~1:10 miniature shot at about f/5
    cd.dof.aperture_blades = 6
    cd.clip_start = 0.1
    cd.clip_end = 200.0
    rnd = random.Random(21)

    def interp(keys, s):
        for (s0, *a), (s1, *b) in zip(keys, keys[1:]):
            if s0 <= s <= s1:
                t = ease_in_out((s - s0) / (s1 - s0), 1.8)
                return [Vector(a[i]).lerp(Vector(b[i]), t) if isinstance(a[i], tuple) else a[i] + (b[i] - a[i]) * t
                        for i in range(len(a))]
        return [Vector(x) if isinstance(x, tuple) else x for x in keys[-1][1:]]

    for f in range(F_START, F_END + 1, 2):
        s = (f - 1) / FPS
        loc, tg, lens = interp(CAM_KEYS, s)
        # moco rig: tiny irregularity of a hand-cranked slider (sub-millimetre at puppet scale)
        if CAM_LOCK[0] < s < CAM_LOCK[1]:
            loc = loc + Vector((rnd.gauss(0, 0.0015), rnd.gauss(0, 0.0015), rnd.gauss(0, 0.001)))
        cam.location = loc
        tgt.location = tg
        cd.lens = lens
        cam.keyframe_insert("location", frame=f)
        tgt.keyframe_insert("location", frame=f)
        cd.keyframe_insert("lens", frame=f)
        (fp,) = interp([(k[0], k[1]) for k in FOCUS_KEYS], s)
        foc.location = fp
        foc.keyframe_insert("location", frame=f)
    for idb in (cam, tgt, foc, cd):
        for fc in idb.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"
    # a second camera for the close-up still of the puppets (not used by the clip)
    cc = bpy.data.cameras.new("CAM clay closeup (still)")
    cl = bpy.data.objects.new("CAM clay closeup (still)", cc)
    c.objects.link(cl)
    cl.location = (1.75, 5.0, 1.6)
    d = Vector((0.75, 0.62, 1.12)) - cl.location
    cl.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cc.lens, cc.sensor_width = 52.0, 36.0
    cc.dof.use_dof = True
    cc.dof.focus_distance = (Vector((0.9, 0.75, 1.25)) - cl.location).length
    cc.dof.aperture_fstop = 1.6
    bpy.context.scene.camera = cam
    return cam


# =============================================================================================
# render settings
# =============================================================================================
def render_settings():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 16                 # per-layer overrides in clay_layers.py
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 1
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.blur_glossy = 1.0
    sc.cycles.sample_clamp_indirect = 8.0
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end, sc.frame_step = F_START, F_END, 2
    sc.render.use_persistent_data = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Base Contrast"
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"


# =============================================================================================
def main():
    o = args()
    src = os.path.abspath(o["src"])
    bpy.ops.wm.open_mainfile(filepath=src)
    assets = o.get("assets", "/tmp/claude-0/-home-user/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/3d/assets")
    remap_images(assets)
    strip_scene()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = F_START, F_END
    setc = coll("SET (miniature)")
    for cn in ("Skene", "Platform"):
        c = bpy.data.collections[cn]
        if c.name not in [x.name for x in setc.children]:
            sc.collection.children.unlink(c)
            setc.children.link(c)
    dress = coll("Set dressing", setc)
    restyle_set()
    build_ground(dress)
    build_backdrop(dress, os.path.abspath(o["backdrop"]))
    scatter_dressing(dress)
    lc = coll("LIGHTS (miniature rig)")
    L = build_lights(lc)
    build_cookie(lc, L["key"])
    set_world()
    animate_set()
    camc = coll("CAMERA")
    build_camera(camc)
    render_settings()
    if not o.get("no-figures"):
        import clay_figures
        clay_figures.build_all(o)
    import clay_layers
    clay_layers.setup(o)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(o["out"]))
    print("SAVED", o["out"])


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
