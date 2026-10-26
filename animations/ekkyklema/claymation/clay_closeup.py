"""Close-up still of the puppets (run inside Blender on the built claymation .blend):

    blender -b claymation.blend -P clay_closeup.py -- OUT.png [FRAME=287] [SAMPLES=48]

Uses the camera "CAM clay closeup (still)" at 1920x1080 and renders set and puppets together in
one layer (the plate layer with the CAST collection switched back on). The stagehands are left
out: they are hidden from the audience's view, but this lower camera would see behind the couch.
"""
import sys

import bpy

a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
frame = int(a[1]) if len(a) > 1 else 287
spp = int(a[2]) if len(a) > 2 else 48
sc = bpy.context.scene
sc.camera = bpy.data.objects["CAM clay closeup (still)"]
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
sc.render.film_transparent = False
for vl in sc.view_layers:
    vl.use = vl.name == "plate"
plate = sc.view_layers["plate"]
plate.samples = spp
cast_lc = plate.layer_collection.children["CAST"]
cast_lc.exclude = False
# the stagehands are hidden from the audience but this camera looks behind the couch: leave them out
for slot in ("stagehand_1", "stagehand_2"):
    cast_lc.children[slot].exclude = True
nt = sc.node_tree
for n in nt.nodes:
    if n.type == "OUTPUT_FILE":
        n.mute = True
rl = next(n for n in nt.nodes if n.type == "R_LAYERS" and n.layer == "plate")
comp = next(n for n in nt.nodes if n.type == "COMPOSITE")
nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
sc.frame_set(frame)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("CLOSEUP", out)
