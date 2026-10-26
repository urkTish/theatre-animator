"""Claymation puppets for the ekkyklema sample (imported by clay_build.py).

Raw material: the v3 MakeHuman test (CC0 bodies, posed on MakeHuman's "default" rig; masks,
robes and drapes frozen in the posed state), from the scratch folder given by --figs:
    posed.blend            rigs + skinned bodies (+ the stagehands' eyes and hair cards)
    figures_unpacked.blend masks, linings, painted eyes, hair/beard curves, robes, belts,
                           boots, himation, blanket (frozen meshes, platform-local coordinates)
The v3 build script (../3d/experiments/v3_figures/figures_v3.py) is imported for its Poser
(world-space aims + two-bone IK on the MakeHuman rig) and the four base poses; nothing in it
is changed.

Puppet treatment:
  bodies   plasticine: clay shader (fingerprints, tool drags, pores, crease grime, gentle
           subsurface), a slightly lumpy surface (displace), bigger head and hands by bone
           scale (puppet proportions), masks/hair parented to the head bone
  masks    painted plaster on the v3 hand-painted mask textures, with brush and grit relief
  hair     the v3 hair and beard curves turned into sculpted clay locks (thick strands,
           voxel-fused, smoothed): sculpted, not strands
  robes    painted clay (default): the v3 robes with their finest cloth wrinkles smoothed away,
           the v3 pattern bands as paint on plasticine; or puppet cloth (CLAY_ROBES=0: coarse
           miniature weave, felted fuzz). Robes, belts and boots follow the body by Surface Deform
"""
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

import clay_build as cb

HERE = os.path.dirname(os.path.abspath(__file__))
CLAY_ROBES = os.environ.get("CLAY_ROBES", "1") == "1"

NAMES = {v: k for k, v in cb.SRC_NAMES.items()}          # "Standing actor" -> "standing_actor"
FIGS = list(cb.SRC_NAMES.values())

# puppet proportions (bone scale on top of every pose)
HEAD_SCALE = {"Standing actor": 1.08, "Reclining actor": 1.08, "Stagehand A": 1.14, "Stagehand B": 1.14}
HAND_SCALE = 1.18

CLAY = {  # sRGB
    "Standing actor": (190, 128, 92), "Reclining actor": (196, 140, 106),
    "Stagehand A": (168, 108, 74), "Stagehand B": (150, 96, 66),
}


def fv():
    sys.path.insert(0, cb.FIG_SCRIPT_DIR)
    import figures_v3
    return figures_v3


# =============================================================================================
# appending
# =============================================================================================
def append(path, want):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if want(n)]
    libdir = os.path.dirname(path)
    objs = [o for o in dst.objects if o is not None]
    for im in bpy.data.images:
        if im.packed_file or not im.filepath:
            continue
        fp = bpy.path.abspath(im.filepath)
        if not os.path.exists(fp) and im.filepath.startswith("//"):
            alt = os.path.normpath(os.path.join(libdir, im.filepath[2:]))
            if os.path.exists(alt):
                im.filepath = alt
    return objs


def ctx_override(ob):
    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                     selected_editable_objects=[ob])


def select_only(ob):
    vl = bpy.context.view_layer
    vl.update()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)


# =============================================================================================
# clay materials
# =============================================================================================
def store_clay_co(ob):
    """undeformed vertex positions (metres) as a point attribute: shader texture space that
    sticks to the clay while the rig deforms it"""
    me = ob.data
    if "clay_co" in me.attributes:
        me.attributes.remove(me.attributes["clay_co"])
    a = me.attributes.new("clay_co", "FLOAT_VECTOR", "POINT")
    co = [0.0] * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    a.data.foreach_set("vector", co)


def mat_clay(name, color, rough=0.5, sss=0.22, prints=1.0, tool=1.0, image=None, uv=None, grime=0.35,
             seed=0.0, under=None):
    """plasticine: fingerprints (Voronoi rings with an organic warp), tool drags, pores, crease
    grime (pointiness), soft lumps in colour/roughness, gentle subsurface; optional painted image
    as the base colour (clay robes)."""
    m, t = cb.new_mat(name)
    at = t.n("ShaderNodeAttribute", {"attribute_name": "clay_co", "attribute_type": "GEOMETRY"})
    p = t.vmath("ADD", at.outputs["Vector"], (seed, seed * 0.7, seed * 1.3))
    bo = cb.boil(t)
    pb = t.vmath("ADD", p, t.n("ShaderNodeCombineXYZ", X=t.math("MULTIPLY", bo, 0.00002),
                               Y=t.math("MULTIPLY", bo, 0.000013), Z=0.0).outputs[0])
    # lumps (colour + roughness), ~4 cm
    lump = t.n("ShaderNodeTexNoise", Vector=p, Scale=24.0, Detail=3.0, Roughness=0.5)
    # fingerprints: warped Voronoi, rings around each feature point, only in some cells
    warp = t.n("ShaderNodeTexNoise", Vector=p, Scale=40.0, Detail=2.0)
    wv = t.vmath("ADD", p, t.vmath("MULTIPLY", t.vmath("SUBTRACT", warp.outputs["Color"], (0.5, 0.5, 0.5)),
                                   (0.012, 0.012, 0.012)))
    vor = t.n("ShaderNodeTexVoronoi", {"feature": "F1"}, Vector=wv, Scale=9.0, Randomness=1.0)
    d = vor.outputs["Distance"]
    rings = t.math("SINE", t.math("MULTIPLY", d, 2 * math.pi * 21.0))      # ridges ~5 mm apart
    rings = t.math("MULTIPLY", t.math("ADD", rings, 1.0), 0.5)
    inside = t.math("SUBTRACT", 1.0, t.n("ShaderNodeMapRange", Value=d, From_Min=0.18, From_Max=0.42).outputs[0])
    sep = t.n("ShaderNodeSeparateColor", Color=vor.outputs["Color"])
    pick = t.math("GREATER_THAN", sep.outputs[0], 0.45)
    fp = t.math("MULTIPLY", t.math("MULTIPLY", rings, inside), t.math("MULTIPLY", pick, prints))
    # tool drags: long streaks in a direction that wanders over the surface
    dirn = t.n("ShaderNodeTexNoise", Vector=p, Scale=6.0, Detail=1.0)
    rot = t.n("ShaderNodeVectorRotate", {"rotation_type": "Z_AXIS"}, Vector=p,
              Angle=t.math("MULTIPLY", dirn.outputs["Fac"], 5.0))
    rot2 = t.n("ShaderNodeVectorRotate", {"rotation_type": "X_AXIS"}, Vector=rot.outputs[0],
               Angle=t.math("MULTIPLY", dirn.outputs["Fac"], 3.0))
    mp = t.n("ShaderNodeMapping", Vector=rot2.outputs[0], Scale=(240.0, 12.0, 12.0))
    streak = t.n("ShaderNodeTexNoise", Vector=mp.outputs[0], Scale=1.0, Detail=2.0)
    smask = t.n("ShaderNodeTexNoise", Vector=p, Scale=9.0, Detail=1.0)
    st = t.math("MULTIPLY", t.math("MULTIPLY", streak.outputs["Fac"],
                                   t.math("GREATER_THAN", smask.outputs["Fac"], 0.55)), tool)
    pores = t.n("ShaderNodeTexNoise", Vector=pb, Scale=520.0, Detail=1.0)
    h = t.math("ADD", t.math("MULTIPLY", fp, 0.45), t.math("MULTIPLY", st, 0.55))
    h = t.math("ADD", h, t.math("MULTIPLY", pores.outputs["Fac"], 0.25))
    h = t.math("ADD", h, t.math("MULTIPLY", lump.outputs["Fac"], 0.8))
    bump = t.n("ShaderNodeBump", Strength=1.0, Distance=0.0028, Height=h)
    # colour
    if image is not None:
        uvn = t.n("ShaderNodeUVMap", {"uv_map": uv or "UVMap"})
        tex = t.n("ShaderNodeTexImage", Vector=uvn.outputs[0])
        tex.image = image
        base = tex.outputs["Color"]
    else:
        base = color
    if under is not None:
        # the armature's padding under the costume is clay in the robe colour: only where the
        # 'clay_skin' attribute is 1 (hands, head, neck, feet) is it skin-coloured
        sk = t.n("ShaderNodeAttribute", {"attribute_name": "clay_skin", "attribute_type": "GEOMETRY"})
        base = t.mix(sk.outputs["Fac"], under, base)
    dark = t.mix(1.0, base, (0.6, 0.6, 0.6, 1.0), "MULTIPLY")
    col = t.mix(t.math("MULTIPLY", t.math("SUBTRACT", lump.outputs["Fac"], 0.5), 0.45), base, dark)
    # thumb-smudged colour: slight lighter/darker blotches where the clay was handled
    smud = t.n("ShaderNodeTexNoise", Vector=p, Scale=60.0, Detail=2.0)
    col = t.mix(t.math("MULTIPLY", t.math("SUBTRACT", smud.outputs["Fac"], 0.5), 0.35), col,
                t.mix(1.0, base, (1.25, 1.2, 1.15, 1.0), "MULTIPLY"))
    geo = t.n("ShaderNodeNewGeometry")
    crease = t.n("ShaderNodeMapRange", Value=geo.outputs["Pointiness"], From_Min=0.47, From_Max=0.53,
                 To_Min=1.0, To_Max=0.0)
    col = t.mix(t.math("MULTIPLY", crease.outputs[0], grime), col, dark, "MULTIPLY")
    rgh = t.math("ADD", rough, t.math("MULTIPLY", t.math("SUBTRACT", lump.outputs["Fac"], 0.5), 0.3))
    t.bsdf(_props={"subsurface_method": "BURLEY"}, **{"Base Color": col, "Roughness": rgh, "Specular IOR Level": 0.42,
              "Subsurface Weight": sss, "Subsurface Radius": (1.0, 0.5, 0.3), "Subsurface Scale": 0.012,
              "Normal": bump.outputs[0]})
    return m


def mat_plaster(name, img, base_rough=0.62):
    """painted plaster/gesso mask: the v3 hand-painted texture, matte mineral paint, brush
    strokes and grit in the relief, a few hairline cracks"""
    m, t = cb.new_mat(name)
    uvn = t.n("ShaderNodeUVMap", {"uv_map": "UVMap"})
    tex = t.n("ShaderNodeTexImage", Vector=uvn.outputs[0])
    tex.image = img
    at = t.n("ShaderNodeAttribute", {"attribute_name": "clay_co", "attribute_type": "GEOMETRY"})
    p = at.outputs["Vector"]
    dirn = t.n("ShaderNodeTexNoise", Vector=p, Scale=14.0, Detail=1.0)
    rot = t.n("ShaderNodeVectorRotate", {"rotation_type": "Y_AXIS"}, Vector=p,
              Angle=t.math("MULTIPLY", dirn.outputs["Fac"], 4.0))
    mp = t.n("ShaderNodeMapping", Vector=rot.outputs[0], Scale=(22.0, 22.0, 260.0))
    brush = t.n("ShaderNodeTexNoise", Vector=mp.outputs[0], Scale=1.0, Detail=3.0)
    grit = t.n("ShaderNodeTexNoise", Vector=p, Scale=700.0, Detail=1.0)
    crk = t.n("ShaderNodeTexVoronoi", {"feature": "DISTANCE_TO_EDGE"}, Vector=p, Scale=60.0)
    crack = t.math("LESS_THAN", crk.outputs["Distance"], 0.012)
    cmask = t.n("ShaderNodeTexNoise", Vector=p, Scale=10.0)
    crack = t.math("MULTIPLY", crack, t.math("GREATER_THAN", cmask.outputs["Fac"], 0.62))
    h = t.math("ADD", t.math("MULTIPLY", brush.outputs["Fac"], 0.6), t.math("MULTIPLY", grit.outputs["Fac"], 0.25))
    h = t.math("SUBTRACT", h, t.math("MULTIPLY", crack, 0.5))
    bump = t.n("ShaderNodeBump", Strength=0.85, Distance=0.0026, Height=h)
    col = t.mix(t.math("MULTIPLY", crack, 0.5), tex.outputs["Color"], cb.srgb(70, 52, 40))
    col = t.mix(t.math("MULTIPLY", t.math("SUBTRACT", brush.outputs["Fac"], 0.5), 0.18), col, cb.srgb(40, 30, 24))
    t.bsdf(**{"Base Color": col, "Roughness": base_rough, "Specular IOR Level": 0.35,
              "Subsurface Weight": 0.04, "Subsurface Radius": (1.0, 0.6, 0.4), "Subsurface Scale": 0.005,
              "Normal": bump.outputs[0]})
    return m


def mat_puppet_cloth(name, src_mat, weave_mult=0.3, fuzz=0.7):
    """real fabric cut for a puppet: the v3 cloth material with its weave scaled up ~3x (threads
    read at puppet scale), more felted fuzz (sheen) and a softer specular"""
    m = src_mat.copy()
    m.name = name
    nt = m.node_tree
    for n in nt.nodes:
        if n.type == "MAPPING":
            n.inputs["Scale"].default_value = tuple(v * weave_mult for v in n.inputs["Scale"].default_value)
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Sheen Weight"].default_value = fuzz
            n.inputs["Sheen Roughness"].default_value = 0.55
            n.inputs["Specular IOR Level"].default_value = 0.2
        if n.type == "NORMAL_MAP":
            n.inputs["Strength"].default_value = min(1.6, n.inputs["Strength"].default_value * 1.8)
    return m


def mat_bead_eye(name, img=None):
    m, t = cb.new_mat(name)
    if img is not None:
        uvn = t.n("ShaderNodeUVMap", {"uv_map": "UVMap"})
        tex = t.n("ShaderNodeTexImage", Vector=uvn.outputs[0])
        tex.image = img
        col = t.mix(0.25, tex.outputs["Color"], cb.srgb(240, 236, 226))
    else:
        col = cb.srgb(236, 230, 216)
    t.bsdf(**{"Base Color": col, "Roughness": 0.12, "Specular IOR Level": 0.6, "Coat Weight": 0.6,
              "Coat Roughness": 0.05})
    return m


# =============================================================================================
# clay hair: curves -> thick strands -> fused, smoothed sculpted locks
# =============================================================================================
def gn_strands(keep, radius, seed):
    g = bpy.data.node_groups.new("CLAY strands", "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = g.nodes, g.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    rv = N.new("FunctionNodeRandomValue")
    rv.data_type = "BOOLEAN"
    rv.inputs["Probability"].default_value = 1.0 - keep
    rv.inputs["Seed"].default_value = seed
    dl = N.new("GeometryNodeDeleteGeometry")
    dl.domain = "CURVE"
    L.new(gi.outputs[0], dl.inputs["Geometry"])
    L.new(rv.outputs[3], dl.inputs["Selection"])
    sr = N.new("GeometryNodeSetCurveRadius")
    sr.inputs["Radius"].default_value = 1.0
    L.new(dl.outputs[0], sr.inputs["Curve"])
    cc = N.new("GeometryNodeCurvePrimitiveCircle")
    cc.inputs["Resolution"].default_value = 6
    cc.inputs["Radius"].default_value = radius
    cm = N.new("GeometryNodeCurveToMesh")
    cm.inputs["Fill Caps"].default_value = True
    L.new(sr.outputs[0], cm.inputs["Curve"])
    L.new(cc.outputs[0], cm.inputs["Profile Curve"])
    L.new(cm.outputs[0], go.inputs[0])
    return g


def clay_locks(curves_ob, name, keep, radius, voxel, smooth_iters=6, seed=1):
    md = curves_ob.modifiers.new("strands", "NODES")
    md.node_group = gn_strands(keep, radius, seed)
    select_only(curves_ob)
    with ctx_override(curves_ob):
        bpy.ops.object.convert(target="MESH")
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.remesh_voxel_size = voxel
    ob.data.remesh_voxel_adaptivity = 0.0
    select_only(ob)
    with ctx_override(ob):
        bpy.ops.object.voxel_remesh()
    sm = ob.modifiers.new("soften", "SMOOTH")
    sm.factor = 0.6
    sm.iterations = smooth_iters
    with ctx_override(ob):
        bpy.ops.object.modifier_apply(modifier=sm.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def hair_cap_from_cards(cards, name, thick=0.012, voxel=0.007):
    """MakeHuman hair cards (posed) -> solid sculpted clay cap"""
    select_only(cards)
    with ctx_override(cards):
        bpy.ops.object.convert(target="MESH")          # bakes the posed armature deform
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.vertex_groups.clear()
    so = ob.modifiers.new("thick", "SOLIDIFY")
    so.thickness = thick
    so.offset = 0.0
    with ctx_override(ob):
        bpy.ops.object.modifier_apply(modifier=so.name)
    ob.data.remesh_voxel_size = voxel
    with ctx_override(ob):
        bpy.ops.object.voxel_remesh()
    sm = ob.modifiers.new("soften", "SMOOTH")
    sm.factor = 0.7
    sm.iterations = 8
    with ctx_override(ob):
        bpy.ops.object.modifier_apply(modifier=sm.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# =============================================================================================
# binding helpers
# =============================================================================================
def bone_parent(ob, rig, bone):
    M = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = M


def deform_proxy(body):
    """hidden triangulated twin of the body (same armature + mask): Surface Deform refuses the
    MakeHuman quads once posed (concave polygons), triangles are always fine"""
    px = bpy.data.objects.get(body.name + " (deform proxy)")
    if px:
        return px
    px = body.copy()
    px.data = body.data.copy()
    px.name = body.name + " (deform proxy)"
    for c in body.users_collection:
        c.objects.link(px)
    for md in list(px.modifiers):
        if md.type not in ("ARMATURE", "MASK"):
            px.modifiers.remove(md)
    tri = px.modifiers.new("tri", "TRIANGULATE")
    tri.quad_method = "FIXED"
    px.hide_render = True
    px.display_type = "WIRE"
    px.data.materials.clear()
    return px


def surface_bind(ob, target):
    for md in list(ob.modifiers):
        if md.type == "SUBSURF":
            ob.modifiers.remove(md)
    md = ob.modifiers.new("follow body", "SURFACE_DEFORM")
    md.target = target
    md.falloff = 4.0
    # keep modifier order: surface deform first, then solidify/subsurf
    while ob.modifiers[0] != md:
        with ctx_override(ob):
            bpy.ops.object.modifier_move_up(modifier=md.name)
    select_only(ob)
    with ctx_override(ob):
        bpy.ops.object.surfacedeform_bind(modifier=md.name)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ob.evaluated_get(dg)
    if not md.is_bound:
        print("WARNING: surface deform not bound", ob.name)
    return md


# =============================================================================================
# build
# =============================================================================================
def build_all(o):
    F = fv()
    figdir = os.path.abspath(o.get("figs", "/tmp/claude-0/-home-user-theatre-animator/"
                                           "a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/v3_figures/work"))
    sc = bpy.context.scene
    sc.frame_set(1)
    tmp = cb.coll("TMP figures")
    rigs_objs = append(os.path.join(figdir, "posed.blend"),
                       lambda n: n.startswith(tuple(FIGS)) and not n.endswith(("eyebrow001", "eyebrow006",
                                                                                 "eyelashes02")))
    acc_objs = append(os.path.join(figdir, "figures_unpacked.blend"),
                      lambda n: n.startswith("V3 ") and not n.endswith((" body", " hands", "eyebrow001",
                                                                         "eyebrow006", "eyelashes02",
                                                                         " high-poly", " short02", " short04")))
    for ob in rigs_objs + acc_objs:
        tmp.objects.link(ob)
    bpy.context.view_layer.update()
    figs = {}
    for name in FIGS:
        rig = bpy.data.objects[name + " rig"]
        body = bpy.data.objects[name + " body"]
        P = F.Poser(rig)
        frame = F.POSERS[name](P, rig)
        base = P.snapshot()
        P.apply(base)
        figs[name] = dict(rig=rig, body=body, P=P, base=base, frame=frame)
    bpy.context.view_layer.update()

    # ---- clay bodies -------------------------------------------------------------------------
    for name, fg in figs.items():
        body = fg["body"]
        store_clay_co(body)
        sk = body.data.attributes.new("clay_skin", "FLOAT", "POINT")
        skin_idx = {g.index for g in body.vertex_groups if g.name.startswith(
            ("finger", "metacarpal", "wrist", "head", "neck", "jaw", "eye", "foot", "toe", "tongue", "teeth",
             "special", "levator", "oris", "orbicularis", "temporalis", "risorius", "lowerlid", "upperlid"))}
        if name.startswith("Stagehand"):
            skin_idx |= {g.index for g in body.vertex_groups if g.name.startswith(("lowerarm", "lowerleg", "upperarm"))}
        vals = []
        for v in body.data.vertices:
            vals.append(min(1.0, sum(g.weight for g in v.groups if g.group in skin_idx)))
        sk.data.foreach_set("value", vals)
        under = {"Standing actor": cb.srgb(222, 210, 186), "Reclining actor": cb.srgb(206, 160, 84)}.get(
            name, cb.srgb(150, 128, 98))
        assign_clay = mat_clay("CLAY skin " + name, cb.srgb(*CLAY[name]), seed=len(name) * 0.37, under=under)
        cb.assign(body, assign_clay)
        sub = body.modifiers.new("smooth clay", "SUBSURF")
        sub.levels, sub.render_levels = 0, 1
        tx = bpy.data.textures.new("CLAY lumps " + name, "CLOUDS")
        tx.noise_scale = 0.02
        tx.noise_depth = 1
        dp = body.modifiers.new("hand-pressed lumps", "DISPLACE")
        dp.texture = tx
        dp.texture_coords = "UV"
        dp.strength = 0.006
        dp.mid_level = 0.5
        # puppet hands: fingers and palm pushed out along the normal (chunky, simplified)
        vg = body.vertex_groups.new(name="clay_fat_hands")
        idx = {g.index for g in body.vertex_groups if g.name.startswith(("finger", "metacarpal", "wrist"))}
        for v in body.data.vertices:
            w = sum(g.weight for g in v.groups if g.group in idx)
            if w > 0.01:
                vg.add([v.index], min(1.0, w), "REPLACE")
        fat = body.modifiers.new("chunky clay hands", "DISPLACE")
        fat.direction = "NORMAL"
        fat.strength = 0.0045
        fat.mid_level = 0.0
        fat.vertex_group = vg.name
        # (deform order: armature -> mask -> fat -> subsurf -> lumps)
        with ctx_override(body):
            while body.modifiers.find(fat.name) > body.modifiers.find("smooth clay"):
                bpy.ops.object.modifier_move_up(modifier=fat.name)
        for p in body.data.polygons:
            p.use_smooth = True

    # ---- accessories ---------------------------------------------------------------------------
    def acc(name, suffix):
        return bpy.data.objects.get("V3 %s %s" % (name, suffix))

    for name in ("Standing actor", "Reclining actor"):
        fg = figs[name]
        rig = fg["rig"]
        mask = acc(name, "v3mask")
        mimg = next(n.image for n in mask.active_material.node_tree.nodes if n.type == "TEX_IMAGE"
                    and n.image and n.image.name.endswith("_mask.png"))
        store_clay_co(mask)
        cb.assign(mask, mat_plaster("PLASTER mask " + name, mimg))
        lining = acc(name, "v3mask lining")
        for eye in (acc(name, "v3eye L"), acc(name, "v3eye R")):
            em = eye.active_material
            for n in em.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Roughness"].default_value = 0.25
                    n.inputs["Coat Weight"].default_value = 0.4
            bone_parent(eye, rig, "head")
        hair_col = cb.srgb(54, 40, 32) if name == "Standing actor" else cb.srgb(150, 144, 136)
        hair_m = mat_clay("CLAY hair " + name, hair_col, rough=0.55, sss=0.08, prints=0.5, tool=1.6, grime=0.6)
        locks = []
        for part, keep, rad in (("v3hair", 0.16, 0.0042), ("v3beard", 0.2, 0.0038)):
            cv = acc(name, part)
            lk = clay_locks(cv, "CLAY %s %s" % (name, part[2:]), keep, rad, voxel=0.0032)
            store_clay_co(lk)
            cb.assign(lk, hair_m)
            locks.append(lk)
        for ob in [mask, lining] + locks:
            bone_parent(ob, rig, "head")
        fg["head_objs"] = [mask, lining] + locks
    for name in ("Stagehand A", "Stagehand B"):
        fg = figs[name]
        rig = fg["rig"]
        cards = next(o for o in bpy.data.objects if o.name.startswith(name + " short"))
        cap = hair_cap_from_cards(cards, "CLAY %s hair" % name)
        store_clay_co(cap)
        cb.assign(cap, mat_clay("CLAY hair " + name, cb.srgb(40, 30, 24), rough=0.55, sss=0.06, tool=1.6,
                                grime=0.6))
        bone_parent(cap, rig, "head")
        eyes = bpy.data.objects.get(name + " high-poly")
        if eyes:
            img = next((n.image for n in eyes.active_material.node_tree.nodes if n.type == "TEX_IMAGE"), None)
            cb.assign(eyes, mat_bead_eye("BEAD eyes " + name, img))
        fg["head_objs"] = [cap]

    # ---- robes, belts, boots, drapes ----------------------------------------------------------
    for name, fg in figs.items():
        body = fg["body"]
        kind = "tunic" if name.startswith("Stagehand") else "robe"
        robe = acc(name, kind)
        # (the v3 himation is left out: its frozen drape stands off the shoulder like a board)
        parts = [robe, acc(name, "belt") if name != "Reclining actor" else None, acc(name, "boots")]
        parts = [p for p in parts if p is not None]
        for p in parts:
            store_clay_co(p)
            if p is robe:
                mats = [s.material for s in p.material_slots]
                for i, mm in enumerate(mats):
                    if CLAY_ROBES and i == 0:
                        sm = p.modifiers.new("sculpted folds (smooth fine wrinkles)", "SMOOTH")
                        sm.factor = 0.7
                        sm.iterations = 12
                    if CLAY_ROBES:
                        img = next((n.image for n in mm.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and
                                    not n.image.name.startswith("rough_linen")), None)
                        p.material_slots[i].material = mat_clay("CLAY robe %s %d" % (name, i), cb.srgb(200, 170, 120),
                                                                rough=0.62, sss=0.1, image=img, uv="pattern",
                                                                prints=0.7, tool=1.3, seed=i * 3.1)
                    else:
                        p.material_slots[i].material = mat_puppet_cloth("CLOTH %s %s" % (name, mm.name), mm)
            elif "himation" in p.name:
                p.material_slots[0].material = mat_puppet_cloth("CLOTH himation", p.material_slots[0].material)
            elif "belt" in p.name:
                cb.assign(p, mat_clay("CLAY belt " + name, cb.srgb(92, 62, 40), rough=0.55, sss=0.05))
            elif "boots" in p.name:
                cb.assign(p, mat_clay("CLAY boots", cb.srgb(86, 56, 36), rough=0.5, sss=0.05))
            surface_bind(p, deform_proxy(body))
        fg["dressed"] = parts + [deform_proxy(body)]
    for extra in (acc("Reclining actor", "belt"),):
        if extra:
            bpy.data.objects.remove(extra, do_unlink=True)
    him = acc("Standing actor", "himation.001")
    if him:
        bpy.data.objects.remove(him, do_unlink=True)
    blanket = acc("Reclining actor", "blanket")
    if blanket:
        blanket.material_slots[0].material = mat_puppet_cloth("CLOTH blanket", blanket.material_slots[0].material)
        figs["Reclining actor"]["static"] = [blanket]

    # ---- poses for the animation (computed in platform-local space, before parenting) ----------
    import clay_motion
    keys = clay_motion.author_poses(F, figs)

    # ---- slots: CAST/<slot>, roots ---------------------------------------------------------------
    cast = cb.coll("CAST")
    for name, fg in figs.items():
        slot = NAMES[name]
        sc_coll = cb.coll(slot, cast)
        root = bpy.data.objects.new(slot + " root", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.3
        sc_coll.objects.link(root)
        if name == "Standing actor":
            root.location = (0.0, cb.PLAT_Y1, 0.0)
        else:
            root.parent = bpy.data.objects["Platform ctrl"]
        members = [fg["rig"], fg["body"]] + fg.get("head_objs", []) + fg.get("dressed", []) + fg.get("static", [])
        members += [o for o in bpy.data.objects if o.parent == fg["rig"] and o not in members]
        if name.startswith("Stagehand"):
            eyes = bpy.data.objects.get(name + " high-poly")
            if eyes:
                members.append(eyes)
        for ob in members:
            cb.link_to(ob, sc_coll)
        for ob in (fg["rig"], *fg.get("dressed", []), *fg.get("static", [])):
            if ob.parent is None:
                ob.parent = root
                ob.matrix_parent_inverse = Matrix.Identity(4)
        fg["root"] = root
        fg["slot"] = slot
        fg["rig"].name = slot + " rig"
    bpy.data.collections.remove(tmp)
    bpy.context.view_layer.update()
    clay_motion.bake(figs, keys)
    bpy.data.orphans_purge(do_recursive=True)
