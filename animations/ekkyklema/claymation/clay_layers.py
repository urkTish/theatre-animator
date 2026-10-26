"""Render layers and compositing for the claymation sample (imported by clay_build.py).

The puppets are kept separable so they can be swapped later without touching set, camera or
motion. A frame is made in two renders and one comp:

  plate   view layer: the set only (CAST excluded). Rendered only while the set or camera
          moves; in the locked-off holds at the start and end the plate is rendered once and
          reused (clay_sample.py fills those frames).
  cast    view layer: the puppets only, on a transparent film. The set is present as linked
          duplicates flagged as SHADOW CATCHERS (collection "SET catcher (cast layer only)"):
          they hide the puppets exactly where door frame, leaves, couch and platform are in
          front, they light and shadow the puppets as the real set does, and the Shadow Catcher
          pass records the puppets' shadows and occlusion on the set.
  comp    scene "COMP (plate + cast)": composite = plate x shadow + cast (alpha over), done in
          scene-linear light from the EXRs, then the same AgX view transform and grade.

Files per held frame (WORK/frames/):
  plate/plate_####.exr   cast/cast_####.exr (RGBA, premultiplied)   shadow/shadow_####.exr
  matte/matte_####.png (white = puppet)   matte_slots/matte_slots_####.png (R standing_actor,
  G reclining_figure, B stagehands) and, from the COMP scene, composite/ and plate_view/ PNGs
  (display-referred, graded) and cast_view/ RGBA PNGs.
"""
import os

import bpy

SLOT_INDEX = {"standing_actor": 1, "reclining_figure": 2, "stagehand_1": 3, "stagehand_2": 4}
CATCH = "SET catcher (cast layer only)"
RIG = "SET rig (empties)"


def _lc(vl, name):
    def walk(lc):
        if lc.collection.name == name:
            return lc
        for ch in lc.children:
            r = walk(ch)
            if r:
                return r
        return None
    return walk(vl.layer_collection)


def _set_flag(lc, attr, val):
    setattr(lc, attr, val)
    for ch in lc.children:
        _set_flag(ch, attr, val)


def make_catchers():
    """empties that drive the set (door hinges, platform control) go to their own collection,
    used by every layer; every set mesh gets a linked duplicate flagged as shadow catcher"""
    sc = bpy.context.scene
    setc = bpy.data.collections["SET (miniature)"]
    rig = bpy.data.collections.get(RIG) or bpy.data.collections.new(RIG)
    if rig.name not in [c.name for c in sc.collection.children]:
        sc.collection.children.link(rig)
    for ob in list(setc.all_objects):
        if ob.type == "EMPTY":
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            rig.objects.link(ob)
    cat = bpy.data.collections.get(CATCH) or bpy.data.collections.new(CATCH)
    if cat.name not in [c.name for c in sc.collection.children]:
        sc.collection.children.link(cat)
    for ob in list(setc.all_objects):
        if ob.type != "MESH":
            continue
        d = ob.copy()                    # shares the mesh; keeps parent, modifiers, drivers
        d.name = ob.name + " [catcher]"
        cat.objects.link(d)
        d.is_shadow_catcher = True
    return cat


def setup(o):
    sc = bpy.context.scene
    sc.render.film_transparent = True
    has_cast = bpy.data.collections.get("CAST") is not None
    base = sc.view_layers[0]
    base.name = "plate"
    for vl in list(sc.view_layers)[1:]:
        if vl.name != "cast":
            sc.view_layers.remove(vl)
    plate = base
    if has_cast:
        make_catchers()
        cast = sc.view_layers.get("cast") or sc.view_layers.new("cast")
        _lc(plate, "CAST").exclude = True
        _lc(plate, CATCH).exclude = True
        _set_flag(_lc(cast, "SET (miniature)"), "exclude", True)
        cast.use_pass_object_index = True
        cast.cycles.use_pass_shadow_catcher = True
        plate.samples = int(o.get("spp_plate", 14))
        cast.samples = int(o.get("spp_cast", 10))
        for slot, idx in SLOT_INDEX.items():
            c = bpy.data.collections.get(slot)
            if c:
                for ob in c.all_objects:
                    ob.pass_index = idx
    build_compositor(o, has_cast)
    if has_cast:
        build_comp_scene(o)


def _exr(fo, half=True):
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "16" if half else "32"
    fo.format.exr_codec = "ZIP"


def build_compositor(o, has_cast):
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    nt.nodes.clear()
    frames = os.path.abspath(o.get("frames", "//frames"))
    sc.render.filepath = os.path.join(frames, "_raw", "raw_")      # the render's own output (a cast preview)

    def rl(name, y):
        n = nt.nodes.new("CompositorNodeRLayers")
        n.layer = name
        n.location = (-700, y)
        return n

    pl = rl("plate", 300)
    fo_p = nt.nodes.new("CompositorNodeOutputFile")
    fo_p.name = fo_p.label = "FO plate"
    fo_p.location = (200, 300)
    fo_p.base_path = frames
    _exr(fo_p)
    fo_p.format.color_mode = "RGB"
    fo_p.file_slots.clear()
    fo_p.file_slots.new("plate/plate_")
    nt.links.new(pl.outputs["Image"], fo_p.inputs[0])
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.location = (200, 600)
    if not has_cast:
        nt.links.new(pl.outputs["Image"], comp.inputs["Image"])
        return
    ca = rl("cast", -200)
    nt.links.new(ca.outputs["Image"], comp.inputs["Image"])
    fo_c = nt.nodes.new("CompositorNodeOutputFile")
    fo_c.name = fo_c.label = "FO cast"
    fo_c.location = (200, -100)
    fo_c.base_path = frames
    _exr(fo_c)
    fo_c.format.color_mode = "RGBA"
    fo_c.file_slots.clear()
    fo_c.file_slots.new("cast/cast_")
    fo_c.file_slots.new("shadow/shadow_")
    nt.links.new(ca.outputs["Image"], fo_c.inputs[0])
    nt.links.new(ca.outputs["Shadow Catcher"], fo_c.inputs[1])
    fo_m = nt.nodes.new("CompositorNodeOutputFile")
    fo_m.name = fo_m.label = "FO mattes"
    fo_m.location = (200, -500)
    fo_m.base_path = frames
    fo_m.format.file_format = "PNG"
    fo_m.format.color_mode = "RGB"
    fo_m.format.color_depth = "8"
    fo_m.file_slots.clear()
    fo_m.file_slots.new("matte/matte_")
    fo_m.file_slots.new("matte_slots/matte_slots_")
    nt.links.new(ca.outputs["Alpha"], fo_m.inputs[0])
    ids = {}
    for k, idx in enumerate((1, 2, 3, 4)):
        idm = nt.nodes.new("CompositorNodeIDMask")
        idm.index = idx
        idm.use_antialiasing = True
        idm.location = (-350, -600 - 120 * k)
        nt.links.new(ca.outputs["IndexOB"], idm.inputs["ID value"])
        ids[idx] = idm.outputs["Alpha"]
    mxb = nt.nodes.new("CompositorNodeMath")
    mxb.operation = "MAXIMUM"
    mxb.location = (-150, -900)
    nt.links.new(ids[3], mxb.inputs[0])
    nt.links.new(ids[4], mxb.inputs[1])
    cmb = nt.nodes.new("CompositorNodeCombineColor")
    cmb.mode = "RGB"
    cmb.location = (0, -700)
    nt.links.new(ids[1], cmb.inputs["Red"])
    nt.links.new(ids[2], cmb.inputs["Green"])
    nt.links.new(mxb.outputs[0], cmb.inputs["Blue"])
    cmb.inputs["Alpha"].default_value = 1.0
    nt.links.new(cmb.outputs["Image"], fo_m.inputs[1])


def _grade(nt, sock, x, y):
    """a touch of warmth (identical for composite, plate and cast)"""
    cb = nt.nodes.new("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    cb.lift = (1.0, 0.995, 0.985)
    cb.gamma = (1.0, 1.0, 0.99)
    cb.gain = (1.02, 1.0, 0.97)
    cb.location = (x, y)
    nt.links.new(sock, cb.inputs["Image"])
    return cb.outputs["Image"]


def build_comp_scene(o):
    """compositing-only scene: reads the EXR sequences and writes the display-referred frames"""
    src = bpy.context.scene
    frames = os.path.abspath(o.get("frames", "//frames"))
    name = "COMP (plate + cast)"
    old = bpy.data.scenes.get(name)
    if old:
        bpy.data.scenes.remove(old)
    cs = bpy.data.scenes.new(name)
    cs.render.engine = "BLENDER_WORKBENCH"
    cs.render.resolution_x, cs.render.resolution_y = src.render.resolution_x, src.render.resolution_y
    cs.render.resolution_percentage = 100
    cs.render.fps = src.render.fps
    cs.frame_start, cs.frame_end, cs.frame_step = src.frame_start, src.frame_end, 2
    cs.view_settings.view_transform = src.view_settings.view_transform
    cs.view_settings.look = src.view_settings.look
    cs.view_settings.exposure = src.view_settings.exposure
    cs.render.film_transparent = False
    cs.render.image_settings.file_format = "PNG"
    cs.render.image_settings.color_mode = "RGB"
    cs.render.filepath = os.path.join(frames, "composite", "composite_")
    cs.render.use_compositing = True
    cs.use_nodes = True
    nt = cs.node_tree
    nt.nodes.clear()

    def seq(sub, y):
        img = bpy.data.images.new("SEQ " + sub, 8, 8)
        img.source = "SEQUENCE"
        img.filepath = os.path.join(frames, sub, sub + "_0001.exr")
        img.colorspace_settings.name = "Linear Rec.709"
        nd = nt.nodes.new("CompositorNodeImage")
        nd.image = img
        nd.frame_duration = src.frame_end
        nd.frame_start = 1
        nd.frame_offset = 0
        nd.use_auto_refresh = True
        nd.location = (-900, y)
        return nd

    p, s, c = seq("plate", 300), seq("shadow", 0), seq("cast", -300)
    mul = nt.nodes.new("CompositorNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.location = (-600, 200)
    nt.links.new(p.outputs["Image"], mul.inputs[1])
    nt.links.new(s.outputs["Image"], mul.inputs[2])
    ov = nt.nodes.new("CompositorNodeAlphaOver")
    ov.use_premultiply = False             # cast EXR is premultiplied already
    ov.location = (-400, 0)
    nt.links.new(mul.outputs["Image"], ov.inputs[1])
    nt.links.new(c.outputs["Image"], ov.inputs[2])
    g = _grade(nt, ov.outputs["Image"], -200, 0)
    out = nt.nodes.new("CompositorNodeComposite")
    out.location = (100, 0)
    nt.links.new(g, out.inputs["Image"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.location = (100, -300)
    fo.base_path = frames
    fo.format.file_format = "PNG"
    fo.format.color_mode = "RGBA"
    fo.format.color_depth = "8"
    fo.file_slots.clear()
    fo.file_slots.new("plate_view/plate_view_")
    fo.file_slots.new("cast_view/cast_view_")
    nt.links.new(_grade(nt, p.outputs["Image"], -200, -300), fo.inputs[0])
    nt.links.new(_grade(nt, c.outputs["Image"], -200, -500), fo.inputs[1])
    cam = bpy.data.objects.get("COMP camera") or bpy.data.objects.new("COMP camera", bpy.data.cameras.new("COMP camera"))
    if cam.name not in cs.collection.objects:
        cs.collection.objects.link(cam)
    cs.camera = cam
