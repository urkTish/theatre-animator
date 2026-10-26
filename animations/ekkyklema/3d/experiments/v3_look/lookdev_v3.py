#!/usr/bin/env python3
"""Ekkyklema 3D, "v3 look": a look-development pass over a COPY of the built scene.

    python3 lookdev_v3.py                      # copy the built .blend, fetch assets, render both stills
    python3 lookdev_v3.py --res 960x540 --spp 24 --shots audience
    python3 lookdev_v3.py --sun-study          # print the sun table and the facade shadow check only

Run with plain python3: the driver copies the built scene into the working folder
(never touching the original), links its relative ../assets folder, downloads the
extra CC0 assets listed in NOTES.md (MD5-checked), then runs Blender 4.5 headless on
the copy with this same file as the -P script, and finally writes the JPG copies and
the comparison sheets with Pillow. Re-running is safe: every step starts again from
the untouched copy of the built .blend.

Inside Blender (blender -b COPY.blend -P lookdev_v3.py -- ARGS) it changes only:
light (late-afternoon sun + HDRI sky), the skene facade at three scales of detail,
the orchestra ground, atmosphere, compositing, the two cameras, the town houses and
the vegetation tint. Reconstruction facts (R1-R7 sizes, platform travel, timing)
and the figures are left exactly as built.

Options: --src BLEND  --work DIR  --out DIR  --shots audience,establishing
         --res WxH  --spp N  --save-blend  --sun-study  --no-volume  --quick
"""
import hashlib
import math
import os
import random
import shutil
import subprocess
import sys
import time

try:
    import bpy  # noqa: F401  (inside Blender)
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DEFAULT = os.environ.get(
    "EKK_SRC_BLEND", "/tmp/claude-0/-home-user/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/3d/build/scene4.blend")
WORK_DEFAULT = os.environ.get(
    "EKK_V3_WORK", "/tmp/claude-0/-home-user-theatre-animator/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/v3_look")
BLENDER = os.environ.get("BLENDER", "/opt/blender/blender")
REPO_3D = os.path.abspath(os.path.join(HERE, "..", ".."))           # animations/ekkyklema/3d

# extra CC0 assets for this pass (Poly Haven, https://polyhaven.com/license), MD5 from api.polyhaven.com
PH = "https://dl.polyhaven.org/file/ph-assets"
EXTRA_ASSETS = [
    ("hdri/hilly_terrain_01_puresky_4k.hdr", PH + "/HDRIs/hdr/4k/hilly_terrain_01_puresky_4k.hdr",
     "7187d4e09c18d940747b5ad6c808dfcb"),
    ("textures/dirt_floor/dirt_floor_diff_2k.jpg", PH + "/Textures/jpg/2k/dirt_floor/dirt_floor_diff_2k.jpg",
     "dace6e0d469e7b99f0794b941f06bab8"),
    ("textures/dirt_floor/dirt_floor_nor_gl_2k.jpg", PH + "/Textures/jpg/2k/dirt_floor/dirt_floor_nor_gl_2k.jpg",
     "f47bd35ce5a09771aba4ce85e22d5e36"),
    ("textures/dirt_floor/dirt_floor_rough_2k.jpg", PH + "/Textures/jpg/2k/dirt_floor/dirt_floor_rough_2k.jpg",
     "c987eada3ef1492be2843f974e2d9a84"),
    ("textures/dirt_floor/dirt_floor_disp_2k.jpg", PH + "/Textures/jpg/2k/dirt_floor/dirt_floor_disp_2k.jpg",
     "52f507cdfeb132c6dc7753b276c27401"),
    ("textures/brown_mud_dry/brown_mud_dry_diff_2k.jpg", PH + "/Textures/jpg/2k/brown_mud_dry/brown_mud_dry_diff_2k.jpg",
     "7c062619553df423ce2085c48b2ef3c8"),
    ("textures/brown_mud_dry/brown_mud_dry_nor_gl_2k.jpg", PH + "/Textures/jpg/2k/brown_mud_dry/brown_mud_dry_nor_gl_2k.jpg",
     "28547e43fce21a7ac1e71231bb84f433"),
    ("textures/brown_mud_dry/brown_mud_dry_rough_2k.jpg", PH + "/Textures/jpg/2k/brown_mud_dry/brown_mud_dry_rough_2k.jpg",
     "29c7d9215dae069ecf9b294fe444d0e5"),
]


def parse_args(argv):
    a = dict(src=SRC_DEFAULT, work=WORK_DEFAULT, out=HERE, shots="audience,establishing", res="1920x1080",
             spp=64, save_blend=False, sun_study=False, volume=True, quick=False, lst="16.67", est_cam="")
    i = 0
    while i < len(argv):
        k = argv[i]
        if k in ("--src", "--work", "--out", "--shots", "--res", "--lst", "--est-cam"):
            a[k[2:].replace("-", "_")] = argv[i + 1]
            i += 2
            continue
        if k == "--spp":
            a["spp"] = int(argv[i + 1])
            i += 2
            continue
        if k == "--save-blend":
            a["save_blend"] = True
        elif k == "--sun-study":
            a["sun_study"] = True
        elif k == "--no-volume":
            a["volume"] = False
        elif k == "--quick":
            a["quick"] = True
        i += 1
    return a


# =============================================================================
# driver (plain python3)
# =============================================================================
def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_assets(root):
    for rel, url, want in EXTRA_ASSETS:
        dst = os.path.join(root, rel)
        if os.path.exists(dst) and md5(dst) == want:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        print("fetch", url)
        subprocess.run(["curl", "-sS", "--fail", "-o", dst + ".part", url], check=True)
        got = md5(dst + ".part")
        if got != want:
            raise SystemExit(f"MD5 mismatch for {url}: {got} != {want}")
        os.replace(dst + ".part", dst)


def driver(args):
    work = os.path.abspath(args["work"])
    src = os.path.abspath(args["src"])
    build = os.path.join(work, "build")
    os.makedirs(build, exist_ok=True)
    copy = os.path.join(build, "scene_src_copy.blend")
    if not os.path.exists(copy) or md5(copy) != md5(src):
        shutil.copy2(src, copy)                       # the original is only ever read
    # the built file points its textures at //../assets: give the copy the same neighbour
    link = os.path.join(work, "assets")
    target = os.path.abspath(os.path.join(os.path.dirname(src), "..", "assets"))
    if not os.path.islink(link):
        os.symlink(target, link)
    fetch_assets(os.path.join(work, "assets_v3"))
    os.makedirs(os.path.join(work, "renders"), exist_ok=True)
    cmd = [BLENDER, "-b", copy, "--python-exit-code", "1", "-P", os.path.abspath(__file__), "--"]
    for k in ("work", "out", "shots", "res", "lst"):
        cmd += ["--" + k, str(args[k])]
    if args["est_cam"]:
        cmd += ["--est-cam", args["est_cam"]]
    cmd += ["--spp", str(args["spp"])]
    for flag, key in (("--save-blend", "save_blend"), ("--sun-study", "sun_study"), ("--quick", "quick")):
        if args[key]:
            cmd.append(flag)
    if not args["volume"]:
        cmd.append("--no-volume")
    print(" ".join(cmd))
    t0 = time.time()
    r = subprocess.run(cmd)
    if r.returncode:
        raise SystemExit(r.returncode)
    print("blender finished in %.0f s" % (time.time() - t0))
    if not args["sun_study"]:
        make_sheets(args)


def make_sheets(args):
    from PIL import Image, ImageDraw, ImageFont
    out = os.path.abspath(args["out"])
    w, h = (int(v) for v in args["res"].split("x"))
    pairs = {"audience": ("looktest/b_audience_eye.jpg", "v3_audience_eye"),
             "establishing": ("looktest/a_establishing.jpg", "v3_establishing")}
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    for shot in args["shots"].split(","):
        cur, tag = pairs[shot]
        png = os.path.join(out, tag + ".png")
        if not os.path.exists(png):
            continue
        im = Image.open(png).convert("RGB")
        im.save(os.path.join(out, tag + ".jpg"), quality=90, optimize=True)
        if (w, h) != (1920, 1080):
            continue
        cw = 1600
        ch = int(cw * 9 / 16)
        bar = 64
        sheet = Image.new("RGB", (cw, 2 * (ch + bar)), (244, 239, 230))
        d = ImageDraw.Draw(sheet)
        before = Image.open(os.path.join(REPO_3D, cur)).convert("RGB").resize((cw, ch), Image.LANCZOS)
        sheet.paste(before, (0, bar))
        sheet.paste(im.resize((cw, ch), Image.LANCZOS), (0, 2 * bar + ch))
        d.text((24, 14), "Current", fill=(29, 26, 23), font=font)
        d.text((24, ch + bar + 14), "Option: v3 look", fill=(47, 93, 115), font=font)
        q = 88
        while True:
            p = os.path.join(out, f"compare_{shot}.jpg")
            sheet.save(p, quality=q, optimize=True)
            if os.path.getsize(p) < 1.45e6 or q <= 60:
                break
            q -= 4
        print("sheet", p, os.path.getsize(p) // 1024, "KB")


# =============================================================================
# inside Blender
# =============================================================================
if IN_BLENDER:
    import bmesh
    from mathutils import Matrix, Vector, noise

    # ------------------------------------------------------------- reconstruction facts (from build_scene.py)
    FPS = 24
    SKENE_W, SKENE_D, SKENE_H = 12.0, 4.7, 5.0
    WALL_T = 0.20
    DOOR_W, DOOR_H = 2.8, 3.2
    LEAF_T = 0.065
    PLAT_W, PLAT_D, PLAT_H = 2.4, 1.6, 0.30
    AXIS_AZ = 345.0                 # true bearing of scene +Y (the facade normal)
    ORCH_C = Vector((0.0, 11.0))
    TH_R0, TH_ROW = 13.0, 0.8
    LAT = 37.97                     # Athens

    def F(sec):
        return int(round(sec * FPS)) + 1

    FRAME_AUDIENCE = F(45.0)        # tableau rolled out, stagehands hidden (= look test b)
    FRAME_ESTABLISHING = F(2.5)     # = look test a

    sc = bpy.context.scene
    ARGS = parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    WORK = os.path.abspath(ARGS["work"])
    V3A = os.path.join(WORK, "assets_v3")
    RNG = random.Random(425)        # 425 BC, Acharnians

    def log(*a):
        print("[v3]", *a, flush=True)

    # ------------------------------------------------------------- sun position
    def declination(solar_longitude_deg, obliquity_deg=23.73):
        """obliquity for c. 425 BC (23.73 deg; 23.44 today makes < 0.1 deg difference here)"""
        return math.degrees(math.asin(math.sin(math.radians(obliquity_deg)) * math.sin(math.radians(solar_longitude_deg))))

    def sun_position(lat, dec, lst_hours):
        """altitude, azimuth (deg, from true north, clockwise) for local apparent solar time"""
        H = math.radians(15.0 * (lst_hours - 12.0))
        p, d = math.radians(lat), math.radians(dec)
        s_alt = math.sin(p) * math.sin(d) + math.cos(p) * math.cos(d) * math.cos(H)
        alt = math.asin(s_alt)
        cos_az = (math.sin(d) - s_alt * math.sin(p)) / (math.cos(alt) * math.cos(p))
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        return math.degrees(alt), (360.0 - az if H > 0 else az)

    def scene_dir(az_deg, alt_deg):
        """true azimuth/altitude -> unit vector in scene coordinates (as build_scene.py)"""
        a = math.radians(az_deg - AXIS_AZ)
        e = math.radians(alt_deg)
        return Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))

    # about 1 April (City Dionysia, Elaphebolion): ~11 deg of solar longitude past the equinox
    DEC = declination(11.0)
    SUN_LST = float(ARGS["lst"])
    SUN_ALT, SUN_AZ = sun_position(LAT, DEC, SUN_LST)

    def sun_study():
        """facade (normal = scene +Y) lit or not, checked by ray casts against the built geometry"""
        sc.frame_set(FRAME_AUDIENCE)
        hidden = []
        for o in sc.objects:
            cn = o.users_collection[0].name if o.users_collection else ""
            if cn in ("Overlays", "Cameras", "Figures", "Platform") or o.name.startswith("Section"):
                if not o.hide_viewport:
                    o.hide_viewport = True
                    hidden.append(o)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        pts = [Vector((x, 0.06, z)) for x in [-5.6 + 0.8 * i for i in range(15)] for z in (0.3, 1.5, 2.7, 3.9)
               if not (abs(x) < 1.6 and z < 3.3)]
        rows = []
        log("declination %.2f deg (solar longitude 11 deg, obliquity 23.73 deg)" % DEC)
        log(" LST    alt    az   az-axis  cos(i) facade  sin(alt) ground  facade/ground  facade pts in sun")
        for lst in (15.0, 15.5, 16.0, 16.25, 16.5, 16.75, 17.0, 17.25, 17.5, 17.75, 18.0):
            alt, az = sun_position(LAT, DEC, lst)
            d = scene_dir(az, alt)
            lit = sum(1 for p in pts if not sc.ray_cast(dg, p, d, distance=30000.0)[0])
            rows.append((lst, alt, az, d.y, d.z, lit))
            log("%5.2f  %5.1f  %6.1f  %6.1f   %6.3f        %5.3f          %5.2f         %2d/%d"
                % (lst, alt, az, az - AXIS_AZ, d.y, d.z, d.y / max(d.z, 1e-6), lit, len(pts)))
        for o in hidden:
            o.hide_viewport = False
        return rows

    # ------------------------------------------------------------- small helpers
    class NT:
        def __init__(self, tree, clear=True):
            self.t = tree
            if clear:
                tree.nodes.clear()
            self.x = 0

        def n(self, kind, **props):
            node = self.t.nodes.new(kind)
            node.location = (self.x, 0)
            self.x += 180
            for k, v in props.items():
                if k.startswith("in_"):
                    node.inputs[k[3:].replace("_", " ")].default_value = v
                else:
                    setattr(node, k, v)
            return node

        def l(self, a, b):
            self.t.links.new(a, b)

    def new_mat(name):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        return m

    def coll(name):
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            sc.collection.children.link(c)
        return c

    def mesh_object(name, verts, faces, cname, mats=(), mat_idx=None, smooth=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        me.validate()
        for m in mats:
            me.materials.append(m)
        if mat_idx is not None:
            me.polygons.foreach_set("material_index", mat_idx)
        if smooth:
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.update()
        ob = bpy.data.objects.new(name, me)
        coll(cname).objects.link(ob)
        return ob

    class Builder:
        """many closed parts merged into one mesh (one island per part); optional per-corner UVs"""

        def __init__(self):
            self.v, self.f, self.m, self.uv = [], [], [], []

        def add(self, verts, faces, mi=0, uvs=None):
            o = len(self.v)
            self.v += [tuple(p) for p in verts]
            self.f += [tuple(i + o for i in fc) for fc in faces]
            self.m += [mi] * len(faces) if isinstance(mi, int) else list(mi)
            if uvs is None:
                uvs = [[(0.0, 0.0)] * len(fc) for fc in faces]
            self.uv += uvs

        def timber(self, lo, hi, grain, mi=0, mi_end=None, off=(0.0, 0.0), segs=1, jitter=0.0, rng=None, tex=1.0):
            """a squared timber from corner lo to hi, grain along axis `grain` (0/1/2), UVs along the grain,
            end grain on its own material slot; segs/jitter: hand-hewn waviness of the long edges"""
            lo, hi = Vector(lo), Vector(hi)
            a1, a2 = [k for k in range(3) if k != grain]
            rng = rng or RNG
            n = max(1, segs)
            rings = []
            for s in range(n + 1):
                t = lo[grain] + (hi[grain] - lo[grain]) * s / n
                ring = []
                for (c1, c2) in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    p = Vector((0.0, 0.0, 0.0))
                    p[grain] = t
                    p[a1] = (hi[a1] if c1 else lo[a1]) + (rng.uniform(-jitter, jitter) if jitter else 0.0)
                    p[a2] = (hi[a2] if c2 else lo[a2]) + (rng.uniform(-jitter, jitter) if jitter else 0.0)
                    ring.append(p)
                rings.append(ring)
            verts = [p for ring in rings for p in ring]
            faces, mis, uvs = [], [], []
            for s in range(n):
                for k in range(4):
                    a, b = s * 4 + k, s * 4 + (k + 1) % 4
                    fc = (a, b, b + 4, a + 4)
                    faces.append(fc)
                    mis.append(mi)
                    # u around the perimeter, v along the grain
                    us = []
                    for vi in fc:
                        p = verts[vi]
                        u = p[a1] if k % 2 == 0 else p[a2]
                        us.append(((u + off[0]) / tex, (p[grain] + off[1]) / tex))
                    uvs.append(us)
            end0 = (3, 2, 1, 0)
            end1 = tuple(n * 4 + i for i in range(4))
            for fc in (end0, end1):
                faces.append(fc)
                mis.append(mi if mi_end is None else mi_end)
                uvs.append([((verts[vi][a1] + off[0]) / 0.3, (verts[vi][a2] + off[1]) / 0.3) for vi in fc])
            # orientation: make the first side face point away from the axis
            c = (lo + hi) / 2
            f0 = faces[0]
            nrm = (verts[f0[1]] - verts[f0[0]]).cross(verts[f0[3]] - verts[f0[0]])
            mid = sum((verts[i] for i in f0), Vector()) / 4
            ctr = Vector(c)
            ctr[grain] = mid[grain]
            if nrm.dot(mid - ctr) < 0:
                faces = [tuple(reversed(fc)) for fc in faces]
                uvs = [list(reversed(u)) for u in uvs]
            self.add(verts, faces, mis, uvs)

        def box(self, x0, x1, y0, y1, z0, z1, mi=0):
            x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
            v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
            self.add(v, f, mi)

        def obox(self, c, xdir, sx, sy, sz, mi=0, zdir=(0, 0, 1)):
            xd = Vector(xdir).normalized()
            zd = Vector(zdir).normalized()
            yd = zd.cross(xd).normalized()
            zd = xd.cross(yd).normalized()
            c = Vector(c)
            v = []
            for dz in (-0.5, 0.5):
                for (dx, dy) in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
                    v.append(c + xd * (dx * sx) + yd * (dy * sy) + zd * (dz * sz))
            self.add(v, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], mi)

        def cyl(self, p0, p1, r, n=10, mi=0, r1=None):
            p0, p1 = Vector(p0), Vector(p1)
            ax = (p1 - p0).normalized()
            ref = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0))
            u = ax.cross(ref).normalized()
            w = ax.cross(u).normalized()
            r1 = r if r1 is None else r1
            v = []
            for i in range(n):
                a = 2 * math.pi * i / n
                d = u * math.cos(a) + w * math.sin(a)
                v.append(p0 + d * r)
                v.append(p1 + d * r1)
            f = [(2 * i, 2 * ((i + 1) % n), 2 * ((i + 1) % n) + 1, 2 * i + 1) for i in range(n)]
            f.append(tuple(2 * i for i in reversed(range(n))))
            f.append(tuple(2 * i + 1 for i in range(n)))
            self.add(v, f, mi)

        def obj(self, name, cname, mats, smooth=False):
            ob = mesh_object(name, self.v, self.f, cname, mats, self.m, smooth)
            me = ob.data
            if len(me.polygons) == len(self.f):
                uvl = me.uv_layers.new(name="UVMap")
                flat = [c for face in self.uv for uv in face for c in uv]
                if len(flat) == 2 * len(me.loops):
                    uvl.data.foreach_set("uv", flat)
            return ob

    def add_bevel(ob, width, segs=1, angle=60):
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = width
        m.segments = segs
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angle)
        return m

    def add_section_cuts(ob):
        """the museum section cutters (build_scene.py) must slice new architecture too"""
        for cname, nm in (("Section cutter (vertical)", "Cut vertical"), ("Section cutter (plan)", "Cut plan")):
            cutter = bpy.data.objects.get(cname)
            if cutter is None:
                continue
            md = ob.modifiers.new(nm, "BOOLEAN")
            md.operation = "DIFFERENCE"
            md.solver = "EXACT"
            md.object = cutter
            md.material_mode = "TRANSFER"
            md.use_self = False

    def img(path, noncolor=False):
        im = bpy.data.images.load(path, check_existing=True)
        if noncolor:
            im.colorspace_settings.name = "Non-Color"
        return im

    def asset_tex(name, kind):
        """kind: diff / nor_gl / rough / disp -- from the built asset cache or this pass's downloads"""
        for root in (os.path.join(WORK, "assets", "textures", name), os.path.join(V3A, "textures", name)):
            if os.path.isdir(root):
                for fn in sorted(os.listdir(root)):
                    if f"_{kind}_" in fn:
                        return os.path.join(root, fn)
        raise FileNotFoundError(name + " " + kind)

    def srgb(h):
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

    # ------------------------------------------------------------- 1. light: HDRI sky + matched sun lamp
    HDRI = os.path.join(V3A, "hdri", "hilly_terrain_01_puresky_4k.hdr")
    HDRI_SUN_U = 0.6000          # measured: brightest pixel of the HDRI (u), at 11.4 deg elevation
    HDRI_STRENGTH = 0.30
    SUN_STRENGTH = 5.2           # W/m^2 at normal incidence
    SUN_KELVIN = 4300            # direct beam at ~15 deg altitude (air mass ~3.9)

    def build_light():
        w = bpy.data.worlds.new("Attic late afternoon (v3)")
        sc.world = w
        w.use_nodes = True
        nt = NT(w.node_tree)
        d = scene_dir(SUN_AZ, SUN_ALT)
        # Blender's equirect lookup: u = 0.5 - atan2(y, x) / 2pi. Rotate the HDRI about Z so its
        # sun lies at our sun's azimuth (elevation differs by ~3 deg; the disc itself is clamped out)
        hdri_angle = (0.5 - HDRI_SUN_U) * 2 * math.pi
        rot = hdri_angle - math.atan2(d.y, d.x)
        _HDRI_PX["rot"] = rot
        tc = nt.n("ShaderNodeTexCoord")
        mp = nt.n("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0.0, 0.0, rot)
        nt.l(tc.outputs["Generated"], mp.inputs["Vector"])
        env = nt.n("ShaderNodeTexEnvironment")
        env.image = img(HDRI)
        env.interpolation = "Cubic"
        nt.l(mp.outputs[0], env.inputs["Vector"])
        # remove the photographed sun (the lamp is the sun): clamp radiance per channel
        dk = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="DARKEN")
        dk.inputs["Factor"].default_value = 1.0
        dk.inputs["B"].default_value = (14.0, 14.0, 14.0, 1)
        nt.l(env.outputs["Color"], dk.inputs["A"])
        # Attic spring sky: a touch less saturated than the high-veld original
        hs = nt.n("ShaderNodeHueSaturation", in_Hue=0.5, in_Saturation=0.88, in_Value=1.0)
        nt.l(dk.outputs["Result"], hs.inputs["Color"])
        bg = nt.n("ShaderNodeBackground", in_Strength=HDRI_STRENGTH)
        nt.l(hs.outputs[0], bg.inputs["Color"])
        out = nt.n("ShaderNodeOutputWorld")
        nt.l(bg.outputs[0], out.inputs["Surface"])
        w.mist_settings.start = 40.0
        w.mist_settings.depth = 9000.0
        w.mist_settings.falloff = "LINEAR"
        # the lamp
        sun = bpy.data.objects.get("Sun")
        ld = sun.data
        ld.energy = SUN_STRENGTH
        ld.angle = math.radians(0.55)
        ld.use_temperature = True
        ld.temperature = SUN_KELVIN
        ld.color = (1.0, 1.0, 1.0)
        sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        log("sun: LST %.2f  alt %.1f  az %.1f  scene dir %s  hdri rot %.1f deg"
            % (SUN_LST, SUN_ALT, SUN_AZ, tuple(round(c, 3) for c in d), math.degrees(rot)))

    # ------------------------------------------------------------- 2. materials: weathered timber, end grain, iron
    def smooth_range(nt, sock, a, b, lo=0.0, hi=1.0):
        mr = nt.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        mr.inputs["From Min"].default_value = a
        mr.inputs["From Max"].default_value = b
        mr.inputs["To Min"].default_value = lo
        mr.inputs["To Max"].default_value = hi
        nt.l(sock, mr.inputs["Value"])
        return mr.outputs[0]

    def mix_col(nt, fac, a, b, blend="MIX"):
        mx = nt.n("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        if isinstance(fac, float):
            mx.inputs["Factor"].default_value = fac
        else:
            nt.l(fac, mx.inputs["Factor"])
        for sock, val in (("A", a), ("B", b)):
            if isinstance(val, tuple):
                mx.inputs[sock].default_value = (*val, 1.0) if len(val) == 3 else val
            else:
                nt.l(val, mx.inputs[sock])
        return mx.outputs["Result"]

    def mth(nt, op, a, b=None, clamp=False):
        m = nt.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                nt.l(v, m.inputs[i])
        return m.outputs[0]

    def nz_tex(nt, vec, scale, detail=3.0, rough=0.55, stretch=None):
        if stretch:
            mp = nt.n("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = stretch
            nt.l(vec, mp.inputs["Vector"])
            vec = mp.outputs[0]
        nz = nt.n("ShaderNodeTexNoise", in_Scale=scale, in_Detail=detail, in_Roughness=rough)
        nt.l(vec, nz.inputs["Vector"])
        return nz.outputs["Fac"]

    def mat_timber_v3(name, bleach=0.6, grime=0.8, warm=0.35, tone=1.0, rough_bias=0.0):
        """Weathered softwood/oak boards and timbers, grain from rough_wood (CC0) along the UVs.
        Three scales: per-board tone (random per island), sun bleaching toward the top, splash grime,
        dust and a dust skin on upward faces at the base, rain streaks; plus the texture's own checks."""
        m = new_mat(name)
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        geo = nt.n("ShaderNodeNewGeometry")
        sep = nt.n("ShaderNodeSeparateXYZ")
        nt.l(tc.outputs["Object"], sep.inputs[0])
        z = sep.outputs["Z"]
        rnd = geo.outputs["Random Per Island"]
        # per-board offset into the texture on top of the UV offsets
        off = nt.n("ShaderNodeCombineXYZ")
        nt.l(mth(nt, "MULTIPLY", rnd, 3.7), off.inputs["X"])
        nt.l(mth(nt, "MULTIPLY", rnd, 1.3), off.inputs["Y"])
        uv = nt.n("ShaderNodeVectorMath", operation="ADD")
        nt.l(tc.outputs["UV"], uv.inputs[0])
        nt.l(off.outputs[0], uv.inputs[1])
        outs = {}
        for kind in ("diff", "rough", "nor_gl"):
            it = nt.n("ShaderNodeTexImage")
            it.image = img(asset_tex("rough_wood", kind), noncolor=(kind != "diff"))
            it.interpolation = "Cubic" if kind == "nor_gl" else "Linear"
            nt.l(uv.outputs[0], it.inputs["Vector"])
            outs[kind] = it.outputs["Color"]
        # per-board tone, hue and saturation
        hue = nt.n("ShaderNodeMapRange", in_To_Min=0.485, in_To_Max=0.515)
        nt.l(rnd, hue.inputs["Value"])
        val = nt.n("ShaderNodeMapRange", in_To_Min=0.80 * tone, in_To_Max=1.12 * tone)
        nt.l(mth(nt, "FRACT", mth(nt, "MULTIPLY", rnd, 7.13)), val.inputs["Value"])
        hs = nt.n("ShaderNodeHueSaturation", in_Saturation=1.0)
        nt.l(outs["diff"], hs.inputs["Color"])
        nt.l(hue.outputs[0], hs.inputs["Hue"])
        nt.l(val.outputs[0], hs.inputs["Value"])
        col = hs.outputs[0]
        # the texture is already grey: warm the lower, less exposed boards toward the brown of old oak/pine
        lowwarm = smooth_range(nt, z, 3.6, 0.6, 0.0, warm)
        col = mix_col(nt, lowwarm, col, mix_col(nt, 1.0, col, (1.0, 0.80, 0.60), "MULTIPLY"))
        # sun bleaching: silvery toward the top, broken by long vertical noise
        bn = nz_tex(nt, tc.outputs["Object"], 1.6, 3.0, 0.5, stretch=(3.0, 3.0, 0.35))
        bfac = mth(nt, "MULTIPLY", smooth_range(nt, z, 1.2, 4.6, 0.0, bleach), smooth_range(nt, bn, 0.3, 0.7, 0.55, 1.0))
        bl = nt.n("ShaderNodeHueSaturation", in_Saturation=0.35, in_Value=1.42)
        nt.l(col, bl.inputs["Color"])
        col = mix_col(nt, bfac, col, mix_col(nt, 0.35, bl.outputs[0], (0.60, 0.58, 0.54)))
        # rain streaks
        st = nz_tex(nt, tc.outputs["Object"], 2.2, 4.0, 0.6, stretch=(9.0, 9.0, 0.18))
        sfac = smooth_range(nt, st, 0.55, 0.78, 0.0, 0.22)
        col = mix_col(nt, sfac, col, mix_col(nt, 1.0, col, (0.55, 0.50, 0.45), "MULTIPLY"))
        # splash grime at the base, broken by fine noise
        sp = nz_tex(nt, tc.outputs["Object"], 24.0, 2.0, 0.7)
        gfac = mth(nt, "MULTIPLY", smooth_range(nt, z, 0.65, 0.0, 0.0, grime), smooth_range(nt, sp, 0.35, 0.65, 0.45, 1.0))
        col = mix_col(nt, gfac, col, (0.20, 0.155, 0.11))
        # pale dust skin right at the ground and on upward faces near it
        dfac = smooth_range(nt, z, 0.22, 0.0, 0.0, 0.55)
        nz_up = nt.n("ShaderNodeSeparateXYZ")
        nt.l(geo.outputs["Normal"], nz_up.inputs[0])
        up = mth(nt, "MULTIPLY", smooth_range(nt, nz_up.outputs["Z"], 0.6, 0.95, 0.0, 0.55), smooth_range(nt, z, 1.4, 0.2, 0.25, 1.0))
        dfac = mth(nt, "MAXIMUM", dfac, up)
        col = mix_col(nt, dfac, col, (0.44, 0.37, 0.28))
        bs = nt.n("ShaderNodeBsdfPrincipled")
        bs.inputs["Specular IOR Level"].default_value = 0.32
        nt.l(col, bs.inputs["Base Color"])
        rr = nt.n("ShaderNodeMapRange", in_To_Min=0.62 + rough_bias, in_To_Max=0.95)
        nt.l(outs["rough"], rr.inputs["Value"])
        nt.l(mth(nt, "MAXIMUM", rr.outputs[0], dfac), bs.inputs["Roughness"])
        nm = nt.n("ShaderNodeNormalMap", in_Strength=1.35)
        nt.l(outs["nor_gl"], nm.inputs["Color"])
        nt.l(nm.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def mat_end_grain(name="End grain v3"):
        """sawn or split ends: darker, growth rings, radial checks"""
        m = new_mat(name)
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        geo = nt.n("ShaderNodeNewGeometry")
        rings = nt.n("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL", wave_profile="SIN")
        rings.inputs["Scale"].default_value = 9.0
        rings.inputs["Distortion"].default_value = 3.0
        rings.inputs["Detail"].default_value = 3.0
        mp = nt.n("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0, 1.0, 0.2)
        nt.l(tc.outputs["UV"], mp.inputs["Vector"])
        loc = nt.n("ShaderNodeVectorMath", operation="ADD")
        nt.l(mp.outputs[0], loc.inputs[0])
        rr = nt.n("ShaderNodeCombineXYZ")
        nt.l(mth(nt, "MULTIPLY", geo.outputs["Random Per Island"], 5.0), rr.inputs["X"])
        nt.l(rr.outputs[0], loc.inputs[1])
        nt.l(loc.outputs[0], rings.inputs["Vector"])
        vor = nt.n("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", in_Scale=7.0)
        nt.l(loc.outputs[0], vor.inputs["Vector"])
        crack = smooth_range(nt, vor.outputs["Distance"], 0.0, 0.035, 1.0, 0.0)
        col = mix_col(nt, rings.outputs["Fac"], (0.20, 0.165, 0.13), (0.30, 0.255, 0.20))
        col = mix_col(nt, mth(nt, "MULTIPLY", crack, 0.9), col, (0.04, 0.035, 0.03))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.92)
        nt.l(col, bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.6, in_Distance=0.004)
        nt.l(mth(nt, "SUBTRACT", rings.outputs["Fac"], crack), bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def mat_iron_v3(name="Forged iron v3"):
        m = new_mat(name)
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        nz = nz_tex(nt, tc.outputs["Object"], 45.0, 4.0, 0.6)
        rust = smooth_range(nt, nz, 0.45, 0.62, 0.0, 1.0)
        col = mix_col(nt, rust, (0.030, 0.027, 0.025), (0.16, 0.065, 0.025))
        bs = nt.n("ShaderNodeBsdfPrincipled")
        nt.l(col, bs.inputs["Base Color"])
        nt.l(smooth_range(nt, rust, 0.0, 1.0, 0.55, 0.9), bs.inputs["Roughness"])
        nt.l(smooth_range(nt, rust, 0.0, 1.0, 0.55, 0.05), bs.inputs["Metallic"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.5, in_Distance=0.001)
        nt.l(nz, bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    MAT = {}

    def build_materials():
        MAT["boards"] = mat_timber_v3("Facade boards v3", bleach=0.62, grime=0.85, warm=0.40)
        MAT["timber"] = mat_timber_v3("Facade timbers v3", bleach=0.45, grime=0.8, warm=0.55, tone=0.92)
        MAT["leaf"] = mat_timber_v3("Door boards v3", bleach=0.25, grime=0.9, warm=0.65, tone=0.9)
        MAT["end"] = mat_end_grain()
        MAT["iron"] = mat_iron_v3()

    # ------------------------------------------------------------- 3. the skene facade at three scales
    def delete_islands(ob, keep):
        """delete the connected parts of a mesh for which keep(bbox_min, bbox_max) is False"""
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        seen, doomed = set(), []
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, part = [v], []
            seen.add(v.index)
            while stack:
                a = stack.pop()
                part.append(a)
                for e in a.link_edges:
                    b = e.other_vert(a)
                    if b.index not in seen:
                        seen.add(b.index)
                        stack.append(b)
            lo = Vector((min(p.co.x for p in part), min(p.co.y for p in part), min(p.co.z for p in part)))
            hi = Vector((max(p.co.x for p in part), max(p.co.y for p in part), max(p.co.z for p in part)))
            if not keep(lo, hi):
                doomed += part
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()

    def remove_object(name):
        ob = bpy.data.objects.get(name)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)

    def board(b, x0, w, z0, z1, rng, y_front=-0.056, thick=0.032, rows_z=None, mi=0, mi_end=1):
        """one vertical board with real cupping, bowing between its fixings, a slight lean and twist,
        weathered (rounded) arrises; UVs along the grain with a random offset into the texture"""
        cup = rng.uniform(0.0015, 0.0042)
        bow1, bow2 = rng.uniform(-0.004, 0.006), rng.uniform(-0.004, 0.006)
        flare = rng.uniform(0.0, 0.007)
        twist = rng.uniform(-0.003, 0.003)
        lean = rng.uniform(-0.0035, 0.0035)
        yf = y_front + rng.uniform(-0.004, 0.004)
        ou, ov = rng.uniform(0, 8), rng.uniform(0, 8)
        fr = [0.0, 0.10, 0.5, 0.90, 1.0]
        zs = sorted(set([z0, z1] + [z for z in (rows_z or []) if z0 < z < z1]
                        + [z0 + (z1 - z0) * k / 14 for k in range(1, 14)]))

        def bow(z):
            if z < 0.49:
                return flare * (0.49 - z) / 0.49
            if z < 2.52:
                return bow1 * math.sin(math.pi * (z - 0.49) / 2.03)
            if z < 4.59:
                return bow2 * math.sin(math.pi * (z - 2.52) / 2.07)
            return 0.0

        F_, B_ = [], []
        verts, faces, uvs = [], [], []
        for z in zs:
            dx = lean * (z - z0) / max(0.1, z1 - z0)
            rowf, rowb = [], []
            for i, f in enumerate(fr):
                x = x0 + w * f + dx
                cupd = -cup * (1.0 - (2 * f - 1) ** 2)
                arr = -0.0018 if i in (0, 4) else 0.0
                y = yf + bow(z) + cupd + arr + twist * (f - 0.5) * (z - z0) / 5.0
                rowf.append(len(verts))
                verts.append((x, y, z))
                rowb.append(len(verts))
                verts.append((x, yf - thick + bow(z) * 0.5, z))
            F_.append(rowf)
            B_.append(rowb)

        def uvp(vi, side=False):
            x, y, z = verts[vi]
            return (((y if side else x - x0) + ou), (z + ov))

        nz, nf = len(zs), len(fr)
        for j in range(nz - 1):
            for i in range(nf - 1):
                fc = (F_[j][i], F_[j + 1][i], F_[j + 1][i + 1], F_[j][i + 1])
                faces.append(fc)
                uvs.append([uvp(v) for v in fc])
                fc = (B_[j][i], B_[j][i + 1], B_[j + 1][i + 1], B_[j + 1][i])
                faces.append(fc)
                uvs.append([uvp(v) for v in fc])
            for (col, rev) in ((0, False), (nf - 1, True)):
                fc = (F_[j][col], B_[j][col], B_[j + 1][col], F_[j + 1][col])
                if rev:
                    fc = tuple(reversed(fc))
                faces.append(fc)
                uvs.append([uvp(v, True) for v in fc])
        mis = [mi] * len(faces)
        for (row, rev) in ((0, False), (nz - 1, True)):
            for i in range(nf - 1):
                fc = (F_[row][i], F_[row][i + 1], B_[row][i + 1], B_[row][i])
                if rev:
                    fc = tuple(reversed(fc))
                faces.append(fc)
                uvs.append([((verts[v][0] - x0) / 0.3 + ou, verts[v][1] / 0.3) for v in fc])
                mis.append(mi_end)
        b.add(verts, faces, mis, uvs)
        return yf

    def prism_xz(b, poly, y0, y1, mi, mi_end, off):
        """a timber with an arbitrary (CCW in x-z) outline extruded along y: grain along x"""
        n = len(poly)
        verts = [(x, y1, z) for (x, z) in poly] + [(x, y0, z) for (x, z) in poly]
        faces, mis, uvs = [], [], []
        front = tuple(range(n))                       # seen from +y the x-z outline is clockwise ...
        back = tuple(n + i for i in reversed(range(n)))
        # CCW in (x, z) viewed from -y; from +y it is CW, so reverse the front cap
        faces.append(tuple(reversed(front)))
        faces.append(tuple(reversed(back)))
        for fc in faces:
            uvs.append([((verts[v][2] + off[0]), (verts[v][0] + off[1])) for v in fc])
            mis.append(mi)
        for i in range(n):
            j = (i + 1) % n
            fc = (i, j, n + j, n + i)
            faces.append(fc)
            vertical = abs(poly[i][0] - poly[j][0]) < 1e-6
            mis.append(mi_end if vertical else mi)
            uvs.append([((verts[v][1] + off[0]) / (0.3 if vertical else 1.0),
                         ((verts[v][2] if vertical else verts[v][0]) + off[1]) / (0.3 if vertical else 1.0)) for v in fc])
        b.add(verts, faces, mis, uvs)

    def board_run(rng, xa, xb):
        """board widths filling [xa, xb]: hand-sawn, 0.17-0.34 m, gaps 4-11 mm"""
        out, x = [], xa
        while x < xb - 0.05:
            w = min(rng.choice((rng.uniform(0.19, 0.27), rng.uniform(0.17, 0.34))), xb - x)
            if xb - (x + w) < 0.12:
                w = xb - x
            out.append((x, w))
            x += w + rng.uniform(0.004, 0.011)
        return out

    FAC = {}

    def build_facade():
        rng = random.Random(4250)
        hw = SKENE_W / 2
        dx = DOOR_W / 2
        jp = 0.24
        # --- strip the old facade parts (the side and back walls stay)
        delete_islands(bpy.data.objects["Skene boarding"], lambda lo, hi: hi.y < -0.06)
        delete_islands(bpy.data.objects["Skene posts"], lambda lo, hi: hi.y < -0.3)
        for n in ("Skene rails", "Skene door frame", "Door leaf E", "Door leaf W"):
            remove_object(n)
        roof = bpy.data.objects["Skene roof"]
        for v in roof.data.vertices:
            if v.co.y > 0.05:
                v.co.y = -0.06
        roof.data.update()
        mats = [MAT["boards"], MAT["end"]]
        tm = [MAT["timber"], MAT["end"]]
        rows = [0.38, 0.6, 2.42, 2.62, 3.2, 3.52, 4.45, 4.73]
        # --- boards (secondary scale): varied widths, real gaps, cupped and bowed, raised off the ground
        b = Builder()
        runs = []
        for (xa, xb) in ((-hw + 0.04, -dx - jp + 0.02), (dx + jp - 0.02, hw - 0.04)):
            runs += [(x, w, False) for (x, w) in board_run(rng, xa, xb)]
        runs += [(x, w, True) for (x, w) in board_run(rng, -dx - jp + 0.03, dx + jp - 0.03)]
        fronts = []
        for (x, w, over_door) in runs:
            z0 = 3.53 if over_door else (rng.uniform(0.05, 0.09) if rng.random() < 0.12 else rng.uniform(0.012, 0.035))
            fronts.append(board(b, x, w, z0, 4.865, rng, rows_z=rows))
        FAC["boards"] = [(x, w, ov) for (x, w, ov) in runs]
        boards = b.obj("Facade boards v3", "Skene", mats)
        # --- hidden inner girt that the mid-height nails go into (visible only in the cutaway)
        g = Builder()
        for (xa, xb) in ((-hw + 0.26, -dx - jp), (dx + jp, hw - 0.26)):
            g.timber((xa, -0.20, 2.42), (xb, -0.095, 2.62), 0, 0, 1, off=(rng.uniform(0, 5), rng.uniform(0, 5)))
        girt = g.obj("Facade inner girt v3", "Skene", tm)
        # --- posts and rails (primary/secondary): hewn, with stepped scarf joints in the long top rail
        p = Builder()
        post_x = (-hw + 0.13, -4.0, -2.0, 2.0, 4.0, hw - 0.13)
        for x in post_x:
            p.timber((x - 0.13, -0.22, -0.12), (x + 0.13, 0.0, 4.86), 2, 0, 1, off=(rng.uniform(0, 5), rng.uniform(0, 5)),
                     segs=7, jitter=0.004, rng=rng)
        posts = p.obj("Facade posts v3", "Skene", tm)
        r = Builder()
        zt0, zt1, zm = 4.45, 4.73, 4.59
        joints = (-2.0, 2.0)
        lap = 0.11
        ends = [-hw - 0.02] + list(joints) + [hw + 0.02]
        for k in range(3):
            xa, xb = ends[k], ends[k + 1]
            o = (rng.uniform(0, 5), rng.uniform(0, 5))
            # stepped (halved) scarf over the posts at x = +-2: the left piece's lower half runs on past
            # the joint, the right piece's upper half laps back over it; 2 mm open seams
            la = xa + (lap + 0.002 if k > 0 else 0.0)
            ua = xa - (lap - 0.002 if k > 0 else 0.0)
            lb = xb + (lap if k < 2 else 0.0)
            ub = xb - (lap if k < 2 else 0.0)
            outline = [(la, zt0), (lb, zt0), (lb, zm), (ub, zm), (ub, zt1), (ua, zt1), (ua, zm), (la, zm)]
            clean = []
            for pt in outline:
                if not clean or (abs(pt[0] - clean[-1][0]) > 1e-6 or abs(pt[1] - clean[-1][1]) > 1e-6):
                    clean.append(pt)
            if abs(clean[0][0] - clean[-1][0]) < 1e-6 and abs(clean[0][1] - clean[-1][1]) < 1e-6:
                clean.pop()
            # drop collinear points (a straight end)
            pts = [clean[i] for i in range(len(clean))
                   if abs((clean[i][0] - clean[i - 1][0]) * (clean[(i + 1) % len(clean)][1] - clean[i][1])
                          - (clean[i][1] - clean[i - 1][1]) * (clean[(i + 1) % len(clean)][0] - clean[i][0])) > 1e-9]
            prism_xz(r, pts, -0.24, 0.025 + rng.uniform(-0.002, 0.002), 0, 1, o)
        for sgn in (-1, 1):
            a, c = sgn * (dx + jp + 0.002), sgn * (hw + 0.02)
            r.timber((min(a, c), -0.24, 0.38), (max(a, c), 0.025, 0.60), 0, 0, 1,
                     off=(rng.uniform(0, 5), rng.uniform(0, 5)), segs=8, jitter=0.003, rng=rng)
        rails = r.obj("Facade rails v3", "Skene", tm)
        # --- door frame: jambs, pegged lintel, a worn threshold
        d = Builder()
        for sgn in (-1, 1):
            d.timber((min(sgn * dx, sgn * (dx + jp)), -0.23, -0.12), (max(sgn * dx, sgn * (dx + jp)), 0.01, DOOR_H), 2, 0, 1,
                     off=(rng.uniform(0, 5), rng.uniform(0, 5)), segs=6, jitter=0.003, rng=rng)
        d.timber((-dx - jp - 0.15, -0.23, DOOR_H + 0.002), (dx + jp + 0.15, 0.035, DOOR_H + 0.32), 0, 0, 1,
                 off=(rng.uniform(0, 5), rng.uniform(0, 5)), segs=6, jitter=0.003, rng=rng)
        # threshold: dished by feet and wheels in the middle
        tv, tf, tu = [], [], []
        nxs = 15
        for i in range(nxs + 1):
            x = -dx + 0.002 + (DOOR_W - 0.004) * i / nxs
            dip = 0.007 * math.cos(math.pi * x / DOOR_W) ** 2
            for (y, z) in ((-0.2, -0.05), (0.0, -0.05), (0.0, 0.006 - dip * 0.4), (-0.2, 0.012 - dip)):
                tv.append((x, y, z))
        for i in range(nxs):
            for k in range(4):
                a, c = i * 4 + k, i * 4 + (k + 1) % 4
                tf.append((a, c, c + 4, a + 4))
        tf.append((3, 2, 1, 0))
        tf.append(tuple(nxs * 4 + k for k in range(4)))
        tu = [[(tv[v][0] + 1.3, tv[v][1] + tv[v][2]) for v in fc] for fc in tf]
        d.add(tv, tf, [0] * (len(tf) - 2) + [1, 1], tu)
        frame = d.obj("Facade door frame v3", "Skene", tm)
        # --- tertiary: pegs at every joint, hand-forged nail heads where boards meet rails and the girt
        pg = Builder()

        def peg(x, z, y0, depth=0.013, r_=0.016):
            pg.cyl((x, y0 - 0.02, z), (x, y0 + depth + rng.uniform(-0.004, 0.004), z), r_ * rng.uniform(0.9, 1.1), 8)

        for x in post_x:
            for zc, y0 in ((4.59, 0.025),) + (((0.49, 0.025),) if abs(x) > 1.9 else ()):
                for sx in (-0.058, 0.058):
                    peg(x + sx, zc + rng.uniform(-0.01, 0.01), y0)
        for xj in joints:
            for (sx, zz) in ((-0.09, 4.52), (0.09, 4.66)):
                peg(xj + sx, zz, 0.025)
        for sgn in (-1, 1):
            for zz in (3.29, 3.43):
                peg(sgn * (dx + jp / 2), zz, 0.035)
        pegs = pg.obj("Facade pegs v3", "Skene", [MAT["end"]])
        nl = Builder()

        def nail(x, z, y):
            a = rng.uniform(-0.45, 0.45)
            s = rng.uniform(0.011, 0.015)
            nl.obox((x, y + 0.001, z), (math.cos(a), 0, math.sin(a)), s, s, 0.008, zdir=(0, 1, 0))

        for (x, w, ov), yf in zip(runs, fronts):
            cx = x + w / 2
            spots = [(cx, 4.59, 0.025)]
            if not ov:
                spots += [(cx, 0.49, 0.025), (cx, 2.52, yf)]
            for (sx, sz, sy) in spots:
                if not ov and abs(sx) < dx + jp + 0.02 and sz < 3:
                    continue
                if w < 0.21:
                    pts = ((sx, sz + 0.055), (sx, sz - 0.055))
                else:
                    pts = ((sx - 0.26 * w, sz + 0.05), (sx + 0.26 * w, sz - 0.05))
                for (px, pz) in pts:
                    if rng.random() < 0.06:
                        continue          # a lost nail
                    nail(px + rng.uniform(-0.01, 0.01), pz + rng.uniform(-0.008, 0.008), sy)
        nails = nl.obj("Facade nails v3", "Skene", [MAT["iron"]])
        # --- roof edge: a wall plate and the ends of the roof boards, uneven
        re = Builder()
        re.timber((-hw - 0.08, -0.06, 4.875), (hw + 0.08, 0.075, 4.95), 0, 0, 1, segs=8, jitter=0.002, rng=rng)
        x = -hw - 0.08
        while x < hw + 0.08:
            w = min(rng.uniform(0.17, 0.30), hw + 0.08 - x)
            re.timber((x, -0.06, 4.951 + rng.uniform(-0.002, 0.003)), (x + w - 0.006, 0.09 + rng.uniform(0, 0.035), 5.0),
                      1, 0, 1, off=(rng.uniform(0, 5), rng.uniform(0, 5)))
            x += w
        roof_edge = re.obj("Roof edge v3", "Skene", tm)
        for ob, bev in ((boards, 0.0), (girt, 0.006), (posts, 0.012), (rails, 0.01), (frame, 0.01), (roof_edge, 0.006)):
            if bev:
                add_bevel(ob, bev, 1, 50)
            add_section_cuts(ob)
        for ob in (pegs, nails):
            add_section_cuts(ob)
        log("facade: %d boards, %d nails, %d pegs" % (len(runs), len(nails.data.polygons) // 6, len(pegs.data.polygons) // 10))

    def build_doors():
        """new leaves on the same hinges (R6: same size, same swing): staves of varied width, ledges,
        clench-nail rows on the outer face, iron strap hinges inside, an iron ring pull outside"""
        rng = random.Random(346)
        w = DOOR_W / 2 - 0.006
        for side in (1, -1):
            tag = "E" if side > 0 else "W"
            hinge = bpy.data.objects[f"Door hinge {tag}"]
            b = Builder()
            n = 6
            widths = [rng.uniform(0.85, 1.15) for _ in range(n)]
            s = sum(widths)
            x = 0.0
            for i in range(n):
                ww = w * widths[i] / s
                a, c = x + 0.002, x + ww - 0.002
                x += ww
                lo = (min(-side * a, -side * c), 0.0, 0.015)
                hi = (max(-side * a, -side * c), LEAF_T, DOOR_H - 0.01)
                b.timber(lo, hi, 2, 0, 1, off=(rng.uniform(0, 6), rng.uniform(0, 6)), segs=5, jitter=0.0015, rng=rng)
            for zc in (0.5, DOOR_H - 0.55):
                b.timber((min(-side * 0.08, -side * (w - 0.08)), -0.045, zc - 0.09),
                         (max(-side * 0.08, -side * (w - 0.08)), -0.002, zc + 0.09), 0, 0, 1,
                         off=(rng.uniform(0, 6), rng.uniform(0, 6)))
            leaf = b.obj(f"Door leaf {tag} v3", "Skene", [MAT["leaf"], MAT["end"]])
            add_bevel(leaf, 0.004, 1, 50)
            leaf.parent = hinge
            ir = Builder()
            # clench nails through the staves into the ledges: rows of heads on the outer face
            for zc in (0.5, DOOR_H - 0.55):
                xx = 0.0
                for i in range(n):
                    ww = w * widths[i] / s
                    for (fx, dz) in ((0.3, 0.05), (0.7, -0.05)):
                        px = -side * (xx + ww * fx)
                        aa = rng.uniform(-0.4, 0.4)
                        ir.obox((px, LEAF_T + 0.002, zc + dz), (math.cos(aa), 0, math.sin(aa)), 0.014, 0.014, 0.006, zdir=(0, 1, 0))
                    xx += ww
                # strap hinge on the inner face over the ledge, with an eye round the hinge pin
                ir.box(min(0.0, -side * 0.95), max(0.0, -side * 0.95), -0.052, -0.045, zc - 0.028, zc + 0.028)
                ir.cyl((0.0, -0.03, zc - 0.035), (0.0, -0.03, zc + 0.035), 0.022, 10)
                for k in range(5):
                    px = -side * (0.12 + k * 0.19)
                    ir.obox((px, -0.054, zc), (1, 0, 0), 0.012, 0.012, 0.005, zdir=(0, -1, 0))
            # ring pull outside, near the meeting edge (rosette, staple, hanging ring)
            rx = -side * (w - 0.17)
            ir.cyl((rx, LEAF_T, 1.12), (rx, LEAF_T + 0.004, 1.12), 0.055, 16)
            ir.cyl((rx, LEAF_T + 0.004, 1.12), (rx, LEAF_T + 0.026, 1.12), 0.008, 8)
            R, rr = 0.062, 0.0085
            nu, nv = 20, 8
            tv, tf = [], []
            for i in range(nu):
                a = 2 * math.pi * i / nu
                for j in range(nv):
                    bb = 2 * math.pi * j / nv
                    tv.append((rx + (R + rr * math.cos(bb)) * math.sin(a), LEAF_T + 0.03 + rr * math.sin(bb),
                               1.12 - R + (R + rr * math.cos(bb)) * math.cos(a) - 0.005))
            for i in range(nu):
                for j in range(nv):
                    a0, b0 = i * nv + j, ((i + 1) % nu) * nv + j
                    tf.append((a0, b0, ((i + 1) % nu) * nv + (j + 1) % nv, i * nv + (j + 1) % nv))
            ir.add(tv, tf)
            irons = ir.obj(f"Door irons {tag} v3", "Skene", [MAT["iron"]])
            irons.parent = hinge
            if side < 0:
                for ob in (leaf, irons):
                    add_section_cuts(ob)
        for tag in ("E", "W"):
            ring = bpy.data.objects.get(f"Door ring {tag}")
            if ring:
                ring.data.materials.clear()
                ring.data.materials.append(MAT["iron"])

    # ------------------------------------------------------------- 3b. the orchestra ground
    GX0, GX1, GY0, GY1 = -12.0, 12.0, -6.0, 23.0     # detailed beaten-earth patch (metres)
    GRES = 0.025                                      # mesh spacing
    HRES = 0.0125                                     # height/mask image spacing

    def value_noise(np, shape, cell_px, rng, octaves=3, gain=0.5):
        """fractal value noise on a pixel grid (smooth bilinear interpolation of random lattices)"""
        h, w = shape
        out = np.zeros(shape, np.float32)
        amp, tot = 1.0, 0.0
        for o in range(octaves):
            c = max(2.0, cell_px / (2 ** o))
            gh, gw = int(h / c) + 3, int(w / c) + 3
            g = rng.random((gh, gw)).astype(np.float32)
            ys = np.arange(h) / c
            xs = np.arange(w) / c
            y0 = ys.astype(int)
            x0 = xs.astype(int)
            fy = ys - y0
            fx = xs - x0
            fy = fy * fy * (3 - 2 * fy)
            fx = fx * fx * (3 - 2 * fx)
            a = g[y0][:, x0]
            b = g[y0][:, x0 + 1]
            cc = g[y0 + 1][:, x0]
            d = g[y0 + 1][:, x0 + 1]
            top = a + (b - a) * fx[None, :]
            bot = cc + (d - cc) * fx[None, :]
            out += amp * (top + (bot - top) * fy[:, None])
            tot += amp
            amp *= gain
        return out / tot

    def ground_fields():
        """height (m) and masks on the HRES grid: undulation, lumps, trodden areas, a dust berm along
        the facade, two faint wheel ruts out of the door, footprints along walking lines, scuffs"""
        import numpy as np
        rng = np.random.default_rng(408)
        pr = random.Random(409)
        nx = int(round((GX1 - GX0) / HRES)) + 1
        ny = int(round((GY1 - GY0) / HRES)) + 1
        X = (GX0 + np.arange(nx) * HRES)[None, :].astype(np.float32)
        Y = (GY0 + np.arange(ny) * HRES)[:, None].astype(np.float32)
        H = np.zeros((ny, nx), np.float32)
        px = 1.0 / HRES
        und = value_noise(np, (ny, nx), 3.0 * px, rng, 3) - 0.5
        lump = value_noise(np, (ny, nx), 0.35 * px, rng, 3) - 0.5
        grit = value_noise(np, (ny, nx), 0.06 * px, rng, 2) - 0.5
        # trodden: in front of the door, along the facade, the path to the orchestra centre and the side entrances
        T = np.exp(-((X / 3.4) ** 2 + ((Y - 1.8) / 2.3) ** 2))
        T = np.maximum(T, np.exp(-((Y - 0.9) / 0.9) ** 2) * np.exp(-(np.maximum(np.abs(X) - 4.5, 0) / 1.5) ** 2) * 0.8)
        T = np.maximum(T, np.exp(-((X - 0.25 * (Y - 2)) / 1.6) ** 2) * (Y > 2) * np.exp(-np.maximum(Y - 12, 0) / 3) * 0.7)
        for sx in (-1, 1):
            T = np.maximum(T, np.exp(-((Y - 5.5 - 0.12 * (np.abs(X) - 3)) / 1.3) ** 2) * (sx * X > 3) * 0.55)
        T = np.clip(T + (value_noise(np, (ny, nx), 1.2 * px, rng, 2) - 0.5) * 0.35, 0, 1)
        loose = np.clip(1.0 - T * 1.2, 0, 1)
        H += 0.012 * und + 0.0045 * lump * (0.35 + 0.65 * loose) + 0.0012 * grit - 0.005 * T
        # dust berm against the wall (not across the doorway)
        door = np.clip((np.abs(X) - 1.35) / 0.25, 0, 1)
        berm = np.clip(1 - (Y + 0.02) / 0.32, 0, 1) ** 1.5 * (0.6 + 0.8 * (value_noise(np, (ny, nx), 0.4 * px, rng, 2) - 0.2))
        berm = berm * (0.25 + 0.75 * door) * np.clip((6.4 - np.abs(X)) / 0.3, 0, 1) * (Y > -0.25)
        H += 0.03 * berm
        D = np.clip(berm * 1.3, 0, 1)                    # loose pale dust
        K = np.zeros((ny, nx), np.float32)               # darkening of pressed soil (prints, ruts)
        # wheel ruts: the front wheels reach y = 0.45 + 0.55 + 0.12; back wheels stop inside the door
        for xw in (-1.115, 1.115):
            u = np.abs(X - xw)
            prof = np.exp(-(u / 0.03) ** 2) - 0.25 * np.exp(-((u - 0.055) / 0.015) ** 2)
            ext = np.clip((1.25 - Y) / 0.35, 0, 1) * (Y > -0.6)
            H -= 0.0045 * prof * ext
            K = np.maximum(K, np.clip(prof, 0, 1) * ext * 0.6)

        def stamp(cx, cy, ang, left, depth, scale=1.0):
            """one bare-foot / soft-boot print: heel + ball ellipses, with a pressed rim"""
            L = 0.26 * scale
            r = int(0.22 / HRES)
            ix, iy = int((cx - GX0) / HRES), int((cy - GY0) / HRES)
            if ix < r or iy < r or ix >= nx - r or iy >= ny - r:
                return
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32) * HRES
            ca, sa = math.cos(ang), math.sin(ang)
            u = xx * ca + yy * sa
            v = -xx * sa + yy * ca
            v = v * (1 if left else -1)
            heel = ((u + 0.32 * L) / (0.20 * L)) ** 2 + ((v - 0.004) / (0.125 * L)) ** 2
            ball = ((u - 0.17 * L) / (0.33 * L)) ** 2 + ((v + 0.012) / (0.19 * L)) ** 2
            arch = ((u + 0.02 * L) / (0.30 * L)) ** 2 + ((v + 0.035) / (0.10 * L)) ** 2
            d = np.minimum(np.minimum(heel, ball), arch)
            inside = np.clip(1.15 - d, 0, 1) ** 0.6
            rim = np.exp(-((d - 1.25) / 0.25) ** 2)
            sl = (slice(iy - r, iy + r + 1), slice(ix - r, ix + r + 1))
            H[sl] += -depth * inside + 0.25 * depth * rim
            K[sl] = np.maximum(K[sl], inside * 0.8)

        def walk(p0, p1, n_side=None, stride=0.68, depth=(0.002, 0.005), scale=1.0, wobble=0.1):
            p0, p1 = Vector(p0), Vector(p1)
            dist = (p1 - p0).length
            steps = int(dist / stride)
            d = (p1 - p0).normalized()
            nrm = Vector((-d.y, d.x))
            ang = math.atan2(d.y, d.x)
            for k in range(steps):
                left = (k % 2 == 0)
                c = p0 + d * (k * stride + pr.uniform(-0.05, 0.05)) + nrm * ((0.085 if left else -0.085) + pr.uniform(-0.03, 0.03))
                c = c + nrm * math.sin(k * 0.7) * wobble
                if pr.random() < 0.12:
                    continue
                stamp(c.x, c.y, ang + pr.uniform(-0.25, 0.25), left, pr.uniform(*depth), scale * pr.uniform(0.93, 1.07))

        # actors in and out of the door, along the facade, to the side entrances (eisodoi), the standing actor's spot
        walk((0.9, 0.35), (4.5, 8.5))
        walk((4.4, 8.0), (0.6, 0.6))
        walk((-0.7, 0.5), (-3.5, 9.0))
        walk((-6.0, 1.1), (6.2, 0.9), wobble=0.15)
        walk((6.5, 1.6), (-5.0, 1.4), wobble=0.2)
        walk((2.6, 1.3), (11.5, 6.5))
        walk((-11.5, 6.0), (-1.5, 1.6))
        walk((1.0, 4.0), (9.0, 12.0))
        walk((-2.0, 10.5), (2.5, 2.0))
        for k in range(26):
            a = pr.uniform(0, 2 * math.pi)
            stamp(2.25 + pr.gauss(0, 0.35), 0.95 + pr.gauss(0, 0.3), a, k % 2 == 0, pr.uniform(0.002, 0.004))
        for k in range(30):
            stamp(pr.uniform(-1.6, 1.6), pr.uniform(0.15, 2.2), pr.uniform(0, 6.28), k % 2 == 0, pr.uniform(0.0015, 0.0035))
        # scuffs and drag marks near the door
        for k in range(40):
            cx, cy = pr.gauss(0, 1.6), abs(pr.gauss(1.4, 1.1))
            ang = pr.uniform(0, math.pi)
            ln = pr.uniform(0.15, 0.6)
            r = int(0.4 / HRES)
            ix, iy = int((cx - GX0) / HRES), int((cy - GY0) / HRES)
            if ix < r or iy < r or ix >= nx - r or iy >= ny - r:
                continue
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32) * HRES
            u = xx * math.cos(ang) + yy * math.sin(ang)
            v = -xx * math.sin(ang) + yy * math.cos(ang)
            m = np.exp(-(v / pr.uniform(0.02, 0.05)) ** 2) * np.clip(1 - np.abs(u) / (ln / 2), 0, 1)
            sl = (slice(iy - r, iy + r + 1), slice(ix - r, ix + r + 1))
            H[sl] -= 0.0012 * m
            K[sl] = np.maximum(K[sl], m * 0.4)
        # fade every detail out toward the patch edge (except along the facade, where the wall hides it)
        ex = np.clip(np.minimum(X - GX0, GX1 - X) / 1.5, 0, 1)
        ey = np.clip(np.minimum(GY1 - Y, Y - GY0) / 1.5, 0, 1)
        E = (ex * ey).astype(np.float32)
        E = E * E * (3 - 2 * E)
        H *= E
        T *= E
        D *= E
        K *= E
        return X, Y, H, T, D, K, loose * E

    def save_float_image(np, name, rgb, path):
        h, w = rgb.shape[:2]
        im = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
        a = np.ones((h, w, 4), np.float32)
        a[..., :rgb.shape[2]] = rgb
        im.pixels.foreach_set(a.ravel())
        im.filepath_raw = path
        im.file_format = "OPEN_EXR"
        im.save()
        im.colorspace_settings.name = "Non-Color"
        return im

    def terrain_grid():
        """the built terrain is a regular grid near the theatre: bilinear lookup of its heights"""
        import numpy as np
        me = bpy.data.objects["Terrain"].data
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        xs = np.unique(np.round(co[:, 0], 3))
        ys = np.unique(np.round(co[:, 1], 3))
        Z = co[:, 2].reshape(len(ys), len(xs))
        return xs, ys, Z

    def terrain_z(np, grid, X, Y):
        xs, ys, Z = grid
        ix = np.clip(np.searchsorted(xs, X) - 1, 0, len(xs) - 2)
        iy = np.clip(np.searchsorted(ys, Y) - 1, 0, len(ys) - 2)
        fx = (X - xs[ix]) / (xs[ix + 1] - xs[ix])
        fy = (Y - ys[iy]) / (ys[iy + 1] - ys[iy])
        return (Z[iy, ix] * (1 - fx) * (1 - fy) + Z[iy, ix + 1] * fx * (1 - fy)
                + Z[iy + 1, ix] * (1 - fx) * fy + Z[iy + 1, ix + 1] * fx * fy)

    def mat_ground_v3(height_img, mask_img):
        """beaten earth: dirt_floor (CC0) as the base with brown_mud_dry breaking the repeat, large tonal
        drift, compacted (darker, smoother) traffic areas, pale loose dust, and the fine relief of prints
        and ruts as bump from the height image"""
        m = new_mat("Orchestra earth v3")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        tex = {}
        for name, size, rot in (("dirt_floor", 2.07, 0.0), ("brown_mud_dry", 1.3, 0.7)):
            mp = nt.n("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
            mp.inputs["Rotation"].default_value = (0, 0, rot)
            nt.l(tc.outputs["Object"], mp.inputs["Vector"])
            for kind in ("diff", "nor_gl", "rough"):
                it = nt.n("ShaderNodeTexImage")
                it.image = img(asset_tex(name, kind), noncolor=(kind != "diff"))
                it.projection = "FLAT"
                nt.l(mp.outputs[0], it.inputs["Vector"])
                tex[(name, kind)] = it.outputs["Color"]
        mk = nt.n("ShaderNodeTexImage")
        mk.image = mask_img
        mk.interpolation = "Linear"
        mk.extension = "EXTEND"
        nt.l(tc.outputs["UV"], mk.inputs["Vector"])
        sep = nt.n("ShaderNodeSeparateColor")
        nt.l(mk.outputs["Color"], sep.inputs[0])
        T, D, K = sep.outputs["Red"], sep.outputs["Green"], sep.outputs["Blue"]
        hm = nt.n("ShaderNodeTexImage")
        hm.image = height_img
        hm.interpolation = "Cubic"
        hm.extension = "EXTEND"
        nt.l(tc.outputs["UV"], hm.inputs["Vector"])
        hsep = nt.n("ShaderNodeSeparateColor")
        nt.l(hm.outputs["Color"], hsep.inputs[0])
        # base: the two textures mixed by a large soft mask
        big = nz_tex(nt, tc.outputs["Object"], 0.22, 3.0, 0.55)
        mfac = smooth_range(nt, big, 0.42, 0.62, 0.0, 0.55)
        col = mix_col(nt, mfac, tex[("dirt_floor", "diff")], tex[("brown_mud_dry", "diff")])
        hs = nt.n("ShaderNodeHueSaturation", in_Hue=0.497, in_Saturation=0.66, in_Value=0.94)
        nt.l(col, hs.inputs["Color"])
        col = hs.outputs[0]
        drift = nz_tex(nt, tc.outputs["Object"], 0.09, 2.0, 0.5)
        col = mix_col(nt, smooth_range(nt, drift, 0.35, 0.65, 0.0, 0.35), col,
                      mix_col(nt, 1.0, col, (1.08, 0.92, 0.80), "MULTIPLY"))
        col = mix_col(nt, mth(nt, "MULTIPLY", T, 0.6), col, mix_col(nt, 1.0, col, (0.74, 0.70, 0.66), "MULTIPLY"))
        col = mix_col(nt, mth(nt, "MULTIPLY", K, 0.55), col, mix_col(nt, 1.0, col, (0.70, 0.64, 0.58), "MULTIPLY"))
        col = mix_col(nt, mth(nt, "MULTIPLY", D, 0.6), col, (0.46, 0.40, 0.32))
        # pale, loose, sun-dried crust where nobody walks (from the patch's own looseness via the dust mask's inverse)
        crust = nz_tex(nt, tc.outputs["Object"], 0.6, 3.0, 0.55)
        cfac = mth(nt, "MULTIPLY", smooth_range(nt, crust, 0.5, 0.75, 0.0, 0.3), mth(nt, "SUBTRACT", 1.0, T))
        col = mix_col(nt, cfac, col, mix_col(nt, 1.0, col, (1.12, 1.08, 1.02), "MULTIPLY"))
        bs = nt.n("ShaderNodeBsdfPrincipled")
        bs.inputs["Specular IOR Level"].default_value = 0.3
        nt.l(col, bs.inputs["Base Color"])
        rgh = mix_col(nt, mfac, tex[("dirt_floor", "rough")], tex[("brown_mud_dry", "rough")])
        rr = nt.n("ShaderNodeMapRange", in_To_Min=0.72, in_To_Max=1.0)
        nt.l(rgh, rr.inputs["Value"])
        rough = mth(nt, "SUBTRACT", rr.outputs[0], mth(nt, "MULTIPLY", T, 0.12))
        nt.l(mth(nt, "MAXIMUM", rough, D), bs.inputs["Roughness"])
        nm1 = nt.n("ShaderNodeNormalMap", in_Strength=0.9)
        nt.l(mix_col(nt, mfac, tex[("dirt_floor", "nor_gl")], tex[("brown_mud_dry", "nor_gl")]), nm1.inputs["Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=1.0, in_Distance=1.0)
        nt.l(hsep.outputs["Red"], bp.inputs["Height"])
        nt.l(nm1.outputs[0], bp.inputs["Normal"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def retune_terrain_earth():
        """make the terrain's trodden-earth layer the same dirt_floor texture, so the patch edge vanishes"""
        m = bpy.data.materials.get("Terrain")
        if not m:
            return
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and n.image.name.startswith("dirt_"):
                kind = "nor_gl" if "nor_gl" in n.image.name else "diff"
                n.image = img(asset_tex("dirt_floor", kind), noncolor=(kind != "diff"))
                for l in n.inputs["Vector"].links:
                    mp = l.from_node
                    if mp.type == "MAPPING":
                        mp.inputs["Scale"].default_value = (1 / 2.07, 1 / 2.07, 1 / 2.07)
                for l in n.outputs["Color"].links:
                    hs = l.to_node
                    if hs.type == "HUE_SAT":
                        hs.inputs["Hue"].default_value = 0.497
                        hs.inputs["Saturation"].default_value = 0.66
                        hs.inputs["Value"].default_value = 0.94

    def build_ground():
        import numpy as np
        t0 = time.time()
        X, Y, H, T, D, K, loose = ground_fields()
        grid = terrain_grid()
        # height image holds only the fine relief (the mesh carries the rest): H minus a 7x7 box blur
        pad = np.pad(H, 3, mode="edge")
        cs = pad.cumsum(0).cumsum(1)
        cs = np.pad(cs, ((1, 0), (1, 0)))
        k = 7
        blur = (cs[k:, k:] - cs[:-k, k:] - cs[k:, :-k] + cs[:-k, :-k]) / (k * k)
        fine = (H - blur[:H.shape[0], :H.shape[1]]).astype(np.float32)
        build = os.path.join(WORK, "build")
        h_img = save_float_image(np, "Orchestra fine relief v3", fine[..., None].repeat(3, 2), os.path.join(build, "ground_relief_v3.exr"))
        m_img = save_float_image(np, "Orchestra masks v3", np.stack([T, D, K], -1), os.path.join(build, "ground_masks_v3.exr"))
        # mesh at GRES, heights sampled from H (every other image pixel) on top of the built terrain
        step = int(round(GRES / HRES))
        Hs = H[::step, ::step]
        Xs = np.broadcast_to(X[:, ::step], Hs.shape)
        Ys = np.broadcast_to(Y[::step, :], Hs.shape)
        Zt = terrain_z(np, grid, Xs, Ys)
        Z = Zt + 0.003 + Hs
        ny, nx = Hs.shape
        co = np.stack([Xs, Ys, Z], -1).reshape(-1, 3).astype(np.float32)
        ii = np.arange(ny * nx).reshape(ny, nx)
        a = ii[:-1, :-1].ravel()
        quads = np.stack([a, a + 1, a + nx + 1, a + nx], -1)
        me = bpy.data.meshes.new("Orchestra ground v3")
        me.vertices.add(len(co))
        me.vertices.foreach_set("co", co.ravel())
        me.loops.add(quads.size)
        me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
        me.polygons.add(len(quads))
        me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
        me.update(calc_edges=True)
        uvl = me.uv_layers.new(name="UVMap")
        u = ((co[:, 0] - GX0) / (GX1 - GX0))
        v = ((co[:, 1] - GY0) / (GY1 - GY0))
        uv = np.stack([u, v], -1)[quads.ravel()]
        uvl.data.foreach_set("uv", uv.ravel())
        me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
        me.materials.append(mat_ground_v3(h_img, m_img))
        ob = bpy.data.objects.new("Orchestra ground v3", me)
        coll("Landscape").objects.link(ob)
        # sink the built terrain a little under the patch (more than 1 m inside its edge) so it never pokes through
        tm = bpy.data.objects["Terrain"].data
        tco = np.empty(len(tm.vertices) * 3, np.float32)
        tm.vertices.foreach_get("co", tco)
        tco = tco.reshape(-1, 3)
        inside = (tco[:, 0] > GX0 + 1.01) & (tco[:, 0] < GX1 - 1.01) & (tco[:, 1] > GY0 + 0.3) & (tco[:, 1] < GY1 - 1.01)
        tco[inside, 2] -= 0.05
        tm.vertices.foreach_set("co", tco.ravel())
        # widen the terrain's own trodden-earth mask round the patch so the colours meet without a seam
        ca = tm.color_attributes.get("mask")
        if ca is not None:
            cv = np.empty(len(ca.data) * 4, np.float32)
            ca.data.foreach_get("color", cv)
            cv = cv.reshape(-1, 4)
            dd = np.maximum.reduce([np.abs(tco[:, 0]) - (GX1 - 0.5), (GY0 + 0.5) - tco[:, 1], tco[:, 1] - (GY1 - 0.5),
                                    np.zeros(len(tco), np.float32)])
            w = 1.0 - np.clip(dd / 4.0, 0, 1)
            w = w * w * (3 - 2 * w)
            cv[:, 0] = np.maximum(cv[:, 0], w)
            cv[:, 1] = 1.0 - cv[:, 0]
            ca.data.foreach_set("color", cv.ravel())
        tm.update()
        retune_terrain_earth()
        log("ground: %d x %d verts, %.1f s" % (nx, ny, time.time() - t0))
        return X, Y, H, T, D, loose, grid

    # --- pebbles, grit and dry tufts
    def pebble_mesh(name, seed):
        rng = random.Random(seed)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        off = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
        sx, sy, sz = rng.uniform(0.8, 1.2), rng.uniform(0.6, 1.0), rng.uniform(0.45, 0.75)
        for v in bm.verts:
            p = v.co.copy()
            d = 1.0 + 0.28 * noise.noise(p * 1.1 + off) + 0.08 * noise.noise(p * 3.7 + off)
            v.co = Vector((p.x * d * sx, p.y * d * sy, p.z * d * sz))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        return me

    def mat_pebble():
        m = new_mat("Limestone pebbles v3")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        oi = nt.n("ShaderNodeObjectInfo")
        nz = nz_tex(nt, tc.outputs["Object"], 3.0, 6.0, 0.6)
        base = nt.n("ShaderNodeValToRGB")
        cr = base.color_ramp
        cr.elements[0].position, cr.elements[0].color = 0.0, (0.20, 0.17, 0.13, 1)
        cr.elements[1].position, cr.elements[1].color = 1.0, (0.44, 0.40, 0.34, 1)
        e = cr.elements.new(0.55)
        e.color = (0.33, 0.25, 0.18, 1)
        nt.l(oi.outputs["Random"], base.inputs["Fac"])
        col = mix_col(nt, smooth_range(nt, nz, 0.3, 0.7, 0.0, 0.35), base.outputs["Color"], (0.25, 0.22, 0.18))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.82)
        nt.l(col, bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.4, in_Distance=0.002)
        nt.l(nz, bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def tuft_mesh(name, seed, n_blades):
        rng = random.Random(seed)
        b = Builder()
        for k in range(n_blades):
            a = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(0, 0.03)
            base = Vector((r0 * math.cos(a), r0 * math.sin(a), -0.01))
            L = rng.uniform(0.06, 0.20)
            lean = rng.uniform(0.15, 0.9)
            dirn = Vector((math.cos(a), math.sin(a), 0))
            side = Vector((-dirn.y, dirn.x, 0))
            w0 = rng.uniform(0.0025, 0.0045)
            pts = []
            for s in range(4):
                t = s / 3
                p = base + Vector((0, 0, L * t)) + dirn * (lean * L * t * t)
                if rng.random() < 0.15 and s == 3:
                    p.z -= L * 0.25                      # a broken, drooping tip
                pts.append((p, w0 * (1 - t * 0.9)))
            verts, faces, uvs = [], [], []
            for (p, w) in pts:
                verts += [p - side * w, p + side * w]
            for s in range(3):
                faces.append((2 * s, 2 * s + 1, 2 * s + 3, 2 * s + 2))
                uvs.append([(0, s / 3), (1, s / 3), (1, (s + 1) / 3), (0, (s + 1) / 3)])
            b.add(verts, faces, 0, uvs)
        ob = b.obj(name, "V3 library", [mat_tuft()])
        return ob

    def mat_tuft():
        m = bpy.data.materials.get("Dry grass tufts v3")
        if m:
            return m
        m = new_mat("Dry grass tufts v3")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        geo = nt.n("ShaderNodeNewGeometry")
        sep = nt.n("ShaderNodeSeparateXYZ")
        nt.l(tc.outputs["UV"], sep.inputs[0])
        oi = nt.n("ShaderNodeObjectInfo")
        greenness = smooth_range(nt, mth(nt, "ADD", mth(nt, "MULTIPLY", geo.outputs["Random Per Island"], 0.6),
                                         mth(nt, "MULTIPLY", oi.outputs["Random"], 0.6)), 0.55, 1.0, 0.0, 1.0)
        straw = mix_col(nt, sep.outputs["Y"], (0.36, 0.29, 0.15), (0.55, 0.47, 0.30))
        col = mix_col(nt, mth(nt, "MULTIPLY", greenness, mth(nt, "SUBTRACT", 1.0, sep.outputs["Y"])), straw, (0.13, 0.14, 0.05))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.7)
        nt.l(col, bs.inputs["Base Color"])
        tl = nt.n("ShaderNodeBsdfTranslucent")
        nt.l(col, tl.inputs["Color"])
        mx = nt.n("ShaderNodeMixShader", in_Fac=0.3)
        nt.l(bs.outputs[0], mx.inputs[1])
        nt.l(tl.outputs[0], mx.inputs[2])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(mx.outputs[0], out.inputs["Surface"])
        return m

    def scatter_points(name, source_coll, pts, cname="Landscape"):
        """pts: (x, y, z, rot_z, scale, variant, tilt_x, tilt_y) -> GN instances of the collection's children"""
        me = bpy.data.meshes.new(name + " points")
        me.from_pydata([(p[0], p[1], p[2]) for p in pts], [], [])
        for key, i, kind in (("rx", 6, "FLOAT"), ("ry", 7, "FLOAT"), ("rz", 3, "FLOAT"), ("scl", 4, "FLOAT"), ("vix", 5, "INT")):
            a = me.attributes.new(key, kind, "POINT")
            a.data.foreach_set("value", [p[i] for p in pts])
        ob = bpy.data.objects.new(name, me)
        coll(cname).objects.link(ob)
        ng = bpy.data.node_groups.new(name + " GN", "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        N = ng.nodes
        L = ng.links
        gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
        ci = N.new("GeometryNodeCollectionInfo")
        ci.inputs["Collection"].default_value = source_coll
        ci.inputs["Separate Children"].default_value = True
        ci.inputs["Reset Children"].default_value = True
        ci.transform_space = "ORIGINAL"
        iop = N.new("GeometryNodeInstanceOnPoints")
        iop.inputs["Pick Instance"].default_value = True
        cmb = N.new("ShaderNodeCombineXYZ")
        e2r = N.new("FunctionNodeEulerToRotation")
        reads = {}
        for key, dt in (("rx", "FLOAT"), ("ry", "FLOAT"), ("rz", "FLOAT"), ("scl", "FLOAT"), ("vix", "INT")):
            na = N.new("GeometryNodeInputNamedAttribute")
            na.data_type = dt
            na.inputs["Name"].default_value = key
            reads[key] = na.outputs["Attribute"]
        L.new(gi.outputs[0], iop.inputs["Points"])
        L.new(ci.outputs[0], iop.inputs["Instance"])
        L.new(reads["vix"], iop.inputs["Instance Index"])
        L.new(reads["rx"], cmb.inputs["X"])
        L.new(reads["ry"], cmb.inputs["Y"])
        L.new(reads["rz"], cmb.inputs["Z"])
        L.new(cmb.outputs[0], e2r.inputs[0])
        L.new(e2r.outputs[0], iop.inputs["Rotation"])
        L.new(reads["scl"], iop.inputs["Scale"])
        L.new(iop.outputs[0], go.inputs[0])
        mod = ob.modifiers.new("Scatter", "NODES")
        mod.node_group = ng
        return ob

    def library_collection(name):
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            lib = bpy.data.collections.get("Library")
            (lib or sc.collection).children.link(c)
        return c

    def build_ground_scatter(fields):
        import numpy as np
        X, Y, H, T, D, loose, grid = fields
        lib = library_collection("V3 library")
        COLL_PEB = library_collection("V3 pebbles")
        pm = mat_pebble()
        for k in range(7):
            me = pebble_mesh(f"Pebble v3 {k}", 30 + k)
            me.materials.append(pm)
            o = bpy.data.objects.new(f"Pebble v3 {k}", me)
            COLL_PEB.objects.link(o)
        COLL_TUFT = library_collection("V3 tufts")
        for k in range(4):
            o = tuft_mesh(f"Tuft v3 {k}", 70 + k, 22 + 9 * k)
            for c in o.users_collection:
                c.objects.unlink(o)
            COLL_TUFT.objects.link(o)
        rng = random.Random(1201)

        def sample(x, y):
            ix = int(round((x - GX0) / HRES))
            iy = int(round((y - GY0) / HRES))
            ix = min(max(ix, 0), X.shape[1] - 1)
            iy = min(max(iy, 0), Y.shape[0] - 1)
            return float(H[iy, ix]), float(T[iy, ix]), float(D[iy, ix]), float(loose[iy, ix])

        def ground_at(x, y, h):
            return float(terrain_z(np, grid, np.array([x]), np.array([y]))[0]) + 0.003 + h

        pts = []
        tries = 0
        while len(pts) < 7000 and tries < 60000:
            tries += 1
            x, y = rng.uniform(GX0 + 0.2, GX1 - 0.2), rng.uniform(GY0 + 0.3, GY1 - 0.4)
            if y < -0.05 and abs(x) < 6.15:
                continue                               # inside the skene
            if y < -0.05 and rng.random() < 0.5:
                continue
            h, t, d, lo = sample(x, y)
            dens = 0.25 + 0.75 * lo + 0.8 * d
            if (Vector((x, y)) - ORCH_C).length > 10.5:
                dens += 0.6
            if rng.random() > dens / 2.2:
                continue
            size = math.exp(rng.uniform(math.log(0.005), math.log(0.04)))
            if size > 0.02 and rng.random() < 0.7:
                size *= 0.45
            z = ground_at(x, y, h) - size * rng.uniform(0.15, 0.45)
            pts.append((x, y, z, rng.uniform(0, 6.28), size, rng.randrange(7), rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)))
        scatter_points("Pebbles and grit v3", COLL_PEB, pts)
        tp = []
        # sparse dry tufts where feet do not go: along the wall base away from the door, at the corners,
        # toward the benches and the side edges
        for k in range(400):
            zone = rng.random()
            if zone < 0.35:
                x = rng.choice((-1, 1)) * rng.uniform(2.6, 6.6)
                y = rng.uniform(0.02, 0.3)
            elif zone < 0.6:
                a = rng.uniform(-1.2, 1.2)
                r = rng.uniform(10.6, 12.3)
                x, y = ORCH_C.x + r * math.sin(a), ORCH_C.y + r * math.cos(a)
            else:
                x, y = rng.choice((-1, 1)) * rng.uniform(8.0, 11.6), rng.uniform(0.2, 15.0)
            if not (GX0 + 0.3 < x < GX1 - 0.3 and -0.2 < y < GY1 - 0.3):
                continue
            h, t, d, lo = sample(x, y)
            if t > 0.45 or rng.random() > 0.55:
                continue
            tp.append((x, y, ground_at(x, y, h), rng.uniform(0, 6.28), rng.uniform(0.6, 1.5), rng.randrange(4), 0.0, 0.0))
        scatter_points("Dry tufts v3", COLL_TUFT, tp)
        log("scatter: %d pebbles, %d tufts" % (len(pts), len(tp)))

    # ------------------------------------------------------------- 3c. the town: courtyard houses on the built sites
    def mat_town_walls():
        """mud-brick or rubble walls under clay or lime plaster: per-house tone, darker stone socle and
        splash at the foot, patchy plaster, faint rain streaks"""
        m = new_mat("Town walls v3 (plastered mud brick)")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        tone = nt.n("ShaderNodeAttribute", attribute_name="tone", attribute_type="GEOMETRY")
        hz = nt.n("ShaderNodeAttribute", attribute_name="hz", attribute_type="GEOMETRY")
        ramp = nt.n("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "CONSTANT"
        stops = [(0.0, (0.42, 0.33, 0.24)), (0.22, (0.56, 0.47, 0.36)), (0.45, (0.58, 0.54, 0.47)),
                 (0.62, (0.50, 0.37, 0.24)), (0.80, (0.54, 0.50, 0.43)), (0.92, (0.45, 0.41, 0.36))]
        cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
        cr.elements[1].position, cr.elements[1].color = stops[1][0], (*stops[1][1], 1)
        for pos, c in stops[2:]:
            e = cr.elements.new(pos)
            e.color = (*c, 1)
        nt.l(tone.outputs["Fac"], ramp.inputs["Fac"])
        col = ramp.outputs["Color"]
        patch = nz_tex(nt, tc.outputs["Object"], 0.9, 3.0, 0.6)
        col = mix_col(nt, smooth_range(nt, patch, 0.35, 0.7, 0.0, 0.3), col, mix_col(nt, 1.0, col, (0.85, 0.80, 0.74), "MULTIPLY"))
        st = nz_tex(nt, tc.outputs["Object"], 1.5, 3.0, 0.6, stretch=(4.0, 4.0, 0.3))
        col = mix_col(nt, smooth_range(nt, st, 0.55, 0.75, 0.0, 0.25), col, mix_col(nt, 1.0, col, (0.7, 0.66, 0.62), "MULTIPLY"))
        socle = smooth_range(nt, hz.outputs["Fac"], 0.75, 0.55, 0.0, 1.0)
        col = mix_col(nt, socle, col, (0.30, 0.27, 0.23))
        splash = smooth_range(nt, hz.outputs["Fac"], 0.5, 0.0, 0.0, 0.5)
        col = mix_col(nt, splash, col, (0.26, 0.20, 0.14))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.95)
        bs.inputs["Specular IOR Level"].default_value = 0.25
        nt.l(col, bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.25, in_Distance=0.02)
        nt.l(nz_tex(nt, tc.outputs["Object"], 6.0, 4.0, 0.6), bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def mat_town_roofs():
        """terracotta pan-and-cover tiles: ripples along the eave from the UVs, courses up the slope,
        per-roof firing colour, per-tile mottling, a little lichen and dust"""
        m = new_mat("Town roofs v3 (terracotta tiles)")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        tone = nt.n("ShaderNodeAttribute", attribute_name="tone", attribute_type="GEOMETRY")
        sep = nt.n("ShaderNodeSeparateXYZ")
        nt.l(tc.outputs["UV"], sep.inputs[0])
        rows = nt.n("ShaderNodeMath", operation="SINE")
        nt.l(mth(nt, "MULTIPLY", sep.outputs["X"], 2 * math.pi / 0.34), rows.inputs[0])
        ridge = mth(nt, "POWER", mth(nt, "ABSOLUTE", rows.outputs[0]), 0.6)
        course = mth(nt, "FRACT", mth(nt, "DIVIDE", sep.outputs["Y"], 0.46))
        lap = smooth_range(nt, course, 0.80, 1.0, 0.0, 1.0)
        ramp = nt.n("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.elements[0].position, cr.elements[0].color = 0.0, (0.28, 0.11, 0.06, 1)
        cr.elements[1].position, cr.elements[1].color = 1.0, (0.52, 0.30, 0.17, 1)
        e = cr.elements.new(0.5)
        e.color = (0.43, 0.17, 0.08, 1)
        tile_id = nt.n("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
        cmb = nt.n("ShaderNodeCombineXYZ")
        nt.l(mth(nt, "FLOOR", mth(nt, "DIVIDE", sep.outputs["X"], 0.34)), cmb.inputs["X"])
        nt.l(mth(nt, "FLOOR", mth(nt, "DIVIDE", sep.outputs["Y"], 0.46)), cmb.inputs["Y"])
        nt.l(cmb.outputs[0], tile_id.inputs["Vector"])
        fac = mth(nt, "ADD", mth(nt, "MULTIPLY", tone.outputs["Fac"], 0.75), mth(nt, "MULTIPLY", tile_id.outputs["Value"], 0.25))
        nt.l(fac, ramp.inputs["Fac"])
        col = ramp.outputs["Color"]
        col = mix_col(nt, mth(nt, "MULTIPLY", lap, 0.35), col, mix_col(nt, 1.0, col, (0.55, 0.5, 0.48), "MULTIPLY"))
        lich = nz_tex(nt, tc.outputs["Object"], 0.35, 4.0, 0.65)
        col = mix_col(nt, smooth_range(nt, lich, 0.62, 0.78, 0.0, 0.35), col, (0.42, 0.40, 0.33))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.8)
        nt.l(col, bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.9, in_Distance=0.06)
        nt.l(mth(nt, "SUBTRACT", ridge, mth(nt, "MULTIPLY", lap, 0.4)), bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def build_town():
        """Replace the box-and-gable houses with courtyard houses on the same sites (the town's extent
        and density stay as built): rooms on two to four sides of an open court, a court wall where
        there are no rooms, mono-pitch tiled roofs falling to the court (sometimes a gable, sometimes an
        upper room), walls of varied plaster; sizes vary, so no two blocks repeat."""
        import numpy as np
        old = bpy.data.objects.get("City houses")
        if old is None:
            return
        me = old.data
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 14, 3)
        rng = random.Random(4311)
        V, Fc, MI, UV, TONE, HZ = [], [], [], [], [], []

        def add_box(c0, ex, ey, x0, x1, y0, y1, z0, z1, g, tone):
            """axis-aligned in the house frame (ex, ey), walls material"""
            base = len(V)
            for (u, v, w) in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                              (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)):
                p = c0 + ex * u + ey * v
                V.append((p.x, p.y, w))
                HZ.append(w - g)
            for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
                Fc.append(tuple(base + i for i in f))
                MI.append(0)
                UV.append([(0, 0)] * 4)
                TONE.append(tone)

        def add_roof(c0, ex, ey, x0, x1, y0, y1, z_lo, z_hi, low_side, g, tone, gable=False):
            """tiled slab: mono-pitch falling toward low_side ('y0' or 'y1') or a gable along x"""
            th = 0.12
            base = len(V)
            if gable:
                ym = (y0 + y1) / 2
                pts = [(x0, y0, z_lo), (x1, y0, z_lo), (x1, ym, z_hi), (x0, ym, z_hi), (x1, y1, z_lo), (x0, y1, z_lo)]
                for (u, v, w) in pts:
                    p = c0 + ex * u + ey * v
                    V.append((p.x, p.y, w))
                    HZ.append(w - g)
                for (u, v, w) in pts:
                    p = c0 + ex * u + ey * v
                    V.append((p.x, p.y, w - th))
                    HZ.append(w - th - g)
                faces = [((0, 1, 2, 3), True, abs(ym - y0)), ((3, 2, 4, 5), True, abs(ym - y0)),
                         ((6, 9, 8, 7), False, 0), ((9, 11, 10, 8), False, 0),
                         ((0, 6, 7, 1), False, 0), ((5, 4, 10, 11), False, 0),
                         ((0, 3, 9, 6), False, 0), ((3, 5, 11, 9), False, 0), ((1, 7, 8, 2), False, 0), ((2, 8, 10, 4), False, 0)]
                slope_len = math.hypot(abs(ym - y0), z_hi - z_lo)
                # gable-end wall triangles under the roof (wall material)
                for xg in (x0 + 0.25, x1 - 0.25):
                    tb = len(V)
                    for (v_, w_) in ((y0 + 0.3, z_lo - th), (ym, z_hi - th), (y1 - 0.3, z_lo - th)):
                        p = c0 + ex * xg + ey * v_
                        V.append((p.x, p.y, w_))
                        HZ.append(w_ - g)
                    Fc.append((tb, tb + 1, tb + 2))
                    MI.append(0)
                    UV.append([(0, 0)] * 3)
                    TONE.append(tone_w_cur[0])
                for k, (f, top, _) in enumerate(faces):
                    Fc.append(tuple(base + i for i in f))
                    MI.append(1)
                    if top:
                        if k == 0:
                            UV.append([(0, 0), (x1 - x0, 0), (x1 - x0, slope_len), (0, slope_len)])
                        else:
                            UV.append([(0, slope_len), (x1 - x0, slope_len), (x1 - x0, 0), (0, 0)])
                    else:
                        UV.append([(0, 0)] * 4)
                    TONE.append(tone)
                return
            if low_side == "y1":
                za0, za1 = z_hi, z_lo
            else:
                za0, za1 = z_lo, z_hi
            pts = [(x0, y0, za0), (x1, y0, za0), (x1, y1, za1), (x0, y1, za1)]
            for (u, v, w) in pts:
                p = c0 + ex * u + ey * v
                V.append((p.x, p.y, w))
                HZ.append(w - g)
            for (u, v, w) in pts:
                p = c0 + ex * u + ey * v
                V.append((p.x, p.y, w - th))
                HZ.append(w - th - g)
            L = math.hypot(y1 - y0, z_hi - z_lo)
            vlo = 0.0 if low_side == "y0" else L
            vhi = L - vlo
            for k, f in enumerate(((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))):
                Fc.append(tuple(base + i for i in f))
                MI.append(1)
                if k == 0:
                    UV.append([(0, vlo), (x1 - x0, vlo), (x1 - x0, vhi), (0, vhi)])
                else:
                    UV.append([(0, 0)] * 4)
                TONE.append(tone)

        n_houses = 0
        tone_w_cur = [0.5]
        for h in co:
            bot = h[:4]
            c0 = Vector(bot.mean(axis=0))
            g = float(bot[0, 2]) + 1.0
            exv = Vector(bot[1] - bot[0])
            eyv = Vector(bot[3] - bot[0])
            w0, d0 = exv.length, eyv.length
            ex = Vector((exv.x, exv.y, 0)).normalized()
            ey = Vector((eyv.x, eyv.y, 0)).normalized()
            if ex.cross(ey).z < 0:
                ey = -ey
            c0 = Vector((c0.x, c0.y, 0.0))
            W = w0 * rng.uniform(0.95, 1.25)
            D = d0 * rng.uniform(0.95, 1.25)
            hx, hy = W / 2, D / 2
            wall_t = 0.45
            tone_w = rng.random()
            tone_r = rng.random()
            tone_w_cur[0] = tone_w
            rd = min(rng.uniform(3.4, 4.8), 0.42 * min(W, D))
            # which sides get rooms: the side facing most nearly north always (scene +y is close to north)
            sides = {"y1": ey.y, "y0": -ey.y, "x1": ex.y, "x0": -ex.y}
            north = max(sides, key=sides.get)
            plan = rng.choices(("L", "U", "I", "O"), (0.4, 0.3, 0.2, 0.1))[0]
            order = [north] + [s for s in ("x0", "x1", "y0", "y1") if s != north]
            rng.shuffle(order[1:])
            opp = {"y1": "y0", "y0": "y1", "x1": "x0", "x0": "x1"}
            if plan == "I":
                rooms = [north]
            elif plan == "L":
                rooms = [north, rng.choice([s for s in order[1:] if s != opp[north]])]
            elif plan == "U":
                rooms = [north] + [s for s in order[1:] if s != opp[north]]
            else:
                rooms = ["x0", "x1", "y0", "y1"]
            zb = g - 1.0
            for s in ("x0", "x1", "y0", "y1"):
                if s in rooms:
                    hw = rng.uniform(3.0, 3.8)
                    if s == north and rng.random() < 0.28:
                        hw = rng.uniform(5.4, 6.3)            # an upper room
                    if s in ("y0", "y1"):
                        ya, yb = (-hy, -hy + rd) if s == "y0" else (hy - rd, hy)
                        xa, xb = -hx, hx
                        add_box(c0, ex, ey, xa, xb, ya, yb, zb, g + hw, g, tone_w)
                        rise = rd * math.tan(math.radians(rng.uniform(12, 18)))
                        gable = rng.random() < 0.22
                        if gable:
                            add_roof(c0, ex, ey, xa - 0.25, xb + 0.25, ya - 0.3, yb + 0.3, g + hw, g + hw + rise * 1.1, None, g, tone_r, gable=True)
                        else:
                            inner = "y1" if s == "y0" else "y0"
                            yy0, yy1 = (ya - 0.15, yb + 0.35) if s == "y0" else (ya - 0.35, yb + 0.15)
                            add_roof(c0, ex, ey, xa - 0.2, xb + 0.2, yy0, yy1, g + hw - 0.15, g + hw + rise, inner, g, tone_r)
                    else:
                        xa, xb = (-hx, -hx + rd) if s == "x0" else (hx - rd, hx)
                        ya, yb = -hy, hy
                        # x-wings: the roof is built in a frame along the wing (right-handed, +y' toward the court)
                        cx = c0 + ex * ((xa + xb) / 2)
                        add_box(c0, ex, ey, xa, xb, ya, yb, zb, g + hw, g, tone_w)
                        rise = rd * math.tan(math.radians(rng.uniform(12, 18)))
                        half = (xb - xa) / 2
                        if s == "x1":
                            fx, fy = ey, -ex                 # local y' = -ex: outer (+ex) is y' = -half
                            add_roof(cx, fx, fy, -hy - 0.2, hy + 0.2, -half - 0.15, half + 0.35, g + hw - 0.15, g + hw + rise, "y1", g, tone_r)
                        else:
                            fx, fy = -ey, ex                 # local y' = +ex: outer (-ex) is y' = -half
                            add_roof(cx, fx, fy, -hy - 0.2, hy + 0.2, -half - 0.15, half + 0.35, g + hw - 0.15, g + hw + rise, "y1", g, tone_r)
                else:
                    # court wall on this side (with a gap for the street door on one of them)
                    hcw = rng.uniform(2.3, 2.9)
                    if s in ("y0", "y1"):
                        ya, yb = (-hy, -hy + wall_t) if s == "y0" else (hy - wall_t, hy)
                        add_box(c0, ex, ey, -hx, hx, ya, yb, zb, g + hcw, g, tone_w)
                    else:
                        xa, xb = (-hx, -hx + wall_t) if s == "x0" else (hx - wall_t, hx)
                        add_box(c0, ex, ey, xa, xb, -hy, hy, zb, g + hcw, g, tone_w)
            n_houses += 1
        town = mesh_object("Town houses v3", V, Fc, "Landscape", [mat_town_walls(), mat_town_roofs()], MI)
        tm = town.data
        if len(tm.polygons) == len(Fc):
            uvl = tm.uv_layers.new(name="UVMap")
            uvl.data.foreach_set("uv", [c for f in UV for uv in f for c in uv])
            at = tm.attributes.new("tone", "FLOAT", "FACE")
            at.data.foreach_set("value", TONE)
        if len(tm.vertices) == len(HZ):
            ah = tm.attributes.new("hz", "FLOAT", "POINT")
            ah.data.foreach_set("value", HZ)
        old.hide_render = True
        old.hide_viewport = True
        log("town: %d courtyard houses, %d faces" % (n_houses, len(tm.polygons)))

    # ------------------------------------------------------------- 3d. slopes: Mediterranean planting, rock, tints
    def retint_vegetation():
        """olive stand-ins toward the silver grey-green of olive leaves; maquis darker and glossier
        (lentisk, kermes oak); low scrub grey-green (sage, phlomis); spring grass less lawn-green"""
        tints = {"searsia_burchellii_leaves_tinted": (0.49, 0.40, 1.30),
                 "searsia_lucida_leaves_tinted": (0.485, 0.95, 0.80),
                 "wild_rooibos_bush_leaves_tinted": (0.50, 0.55, 1.05)}
        for mn, (hh, ss, vv) in tints.items():
            m = bpy.data.materials.get(mn)
            if not m:
                continue
            for n in m.node_tree.nodes:
                if n.type == "HUE_SAT":
                    n.inputs["Hue"].default_value = hh
                    n.inputs["Saturation"].default_value = ss
                    n.inputs["Value"].default_value = vv
            bs = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bs and "burchellii" in mn:
                bs.inputs["Sheen Weight"].default_value = 0.6       # the silvery underside
                bs.inputs["Sheen Tint"].default_value = (0.75, 0.80, 0.70, 1)
        m = bpy.data.materials.get("Terrain")
        if m:
            hs = [n for n in m.node_tree.nodes if n.type == "HUE_SAT"]
            for n in hs:
                img_in = n.inputs["Color"].links[0].from_node if n.inputs["Color"].links else None
                name = img_in.image.name if img_in is not None and getattr(img_in, "image", None) else ""
                if name.startswith("sparse_grass"):
                    n.inputs["Hue"].default_value = 0.545
                    n.inputs["Saturation"].default_value = 1.0
                    n.inputs["Value"].default_value = 1.15
            for n in m.node_tree.nodes:
                if n.type == "TEX_NOISE" and abs(n.inputs["Scale"].default_value - 0.22) < 1e-3:
                    n.inputs["Scale"].default_value = 0.14
                    n.inputs["Detail"].default_value = 6.0

    def retune_far_land():
        """the distant hills were one smooth two-colour noise: add field-scale tonal breakup and relief shading"""
        m = bpy.data.materials.get("Far land")
        if not m:
            return
        t = m.node_tree
        ramp = next((n for n in t.nodes if n.type == "VALTORGB"), None)
        bs = next((n for n in t.nodes if n.type == "BSDF_PRINCIPLED"), None)
        tc = next((n for n in t.nodes if n.type == "TEX_COORD"), None)
        if not (ramp and bs and tc):
            return
        nt = NT(t, clear=False)
        nt.x = 600
        n1 = nz_tex(nt, tc.outputs["Object"], 0.02, 5.0, 0.6)
        n2 = nz_tex(nt, tc.outputs["Object"], 0.15, 3.0, 0.6)
        v = mth(nt, "MULTIPLY", smooth_range(nt, n1, 0.3, 0.7, 0.72, 1.18), smooth_range(nt, n2, 0.3, 0.7, 0.9, 1.08))
        mul = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        mul.inputs["Factor"].default_value = 1.0
        nt.l(ramp.outputs["Color"], mul.inputs["A"])
        cmb = nt.n("ShaderNodeCombineColor")
        for i in range(3):
            nt.l(v, cmb.inputs[i])
        nt.l(cmb.outputs[0], mul.inputs["B"])
        nt.l(mul.outputs["Result"], bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.35, in_Distance=4.0)
        nt.l(n1, bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])

    def mat_outcrop():
        m = new_mat("Limestone outcrops v3")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        oi = nt.n("ShaderNodeObjectInfo")
        nz = nz_tex(nt, tc.outputs["Object"], 2.5, 8.0, 0.65)
        base = mix_col(nt, oi.outputs["Random"], (0.26, 0.24, 0.21), (0.38, 0.35, 0.30))
        col = mix_col(nt, smooth_range(nt, nz, 0.35, 0.65, 0.0, 0.5), base, (0.15, 0.14, 0.12))
        li = nz_tex(nt, tc.outputs["Object"], 9.0, 3.0, 0.6)
        col = mix_col(nt, smooth_range(nt, li, 0.62, 0.72, 0.0, 0.5), col, (0.55, 0.53, 0.40))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.85)
        nt.l(col, bs.inputs["Base Color"])
        bp = nt.n("ShaderNodeBump", in_Strength=0.6, in_Distance=0.05)
        nt.l(nz, bp.inputs["Height"])
        nt.l(bp.outputs[0], bs.inputs["Normal"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def cypress_mesh(name, seed, H):
        """Cupressus sempervirens: a narrow spindle of clumped foliage"""
        rng = random.Random(seed)
        seg, rings = 14, 28
        R = H * rng.uniform(0.075, 0.095)
        off = Vector((rng.uniform(0, 40), rng.uniform(0, 40), 0))
        verts, faces = [], []
        for j in range(rings + 1):
            t = j / rings
            r = R * (math.sin(math.pi * min(1.0, t * 1.05) ** 0.75) ** 0.9) if t < 0.99 else 0.0
            for i in range(seg):
                a = 2 * math.pi * i / seg
                p = Vector((math.cos(a), math.sin(a), 0.0))
                d = 1.0 + 0.28 * noise.noise(p * 2.0 + Vector((0, 0, t * 9.0)) + off)
                verts.append((p.x * r * d, p.y * r * d, t * H))
        for j in range(rings):
            for i in range(seg):
                a0, a1 = j * seg + i, j * seg + (i + 1) % seg
                faces.append((a0, a1, a1 + seg, a0 + seg))
        b = Builder()
        b.add(verts, faces)
        b.cyl((0, 0, -0.5), (0, 0, 1.0), 0.12, 6, 1)
        m = bpy.data.materials.get("Cypress foliage v3")
        if m is None:
            m = new_mat("Cypress foliage v3")
            nt = NT(m.node_tree)
            tc = nt.n("ShaderNodeTexCoord")
            vor = nt.n("ShaderNodeTexVoronoi", in_Scale=7.0)
            nt.l(tc.outputs["Object"], vor.inputs["Vector"])
            col = mix_col(nt, smooth_range(nt, vor.outputs["Distance"], 0.1, 0.5, 0.0, 1.0), (0.035, 0.055, 0.025), (0.01, 0.018, 0.008))
            bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.75)
            nt.l(col, bs.inputs["Base Color"])
            bp = nt.n("ShaderNodeBump", in_Strength=0.9, in_Distance=0.25)
            nt.l(vor.outputs["Distance"], bp.inputs["Height"])
            nt.l(bp.outputs[0], bs.inputs["Normal"])
            out = nt.n("ShaderNodeOutputMaterial")
            nt.l(bs.outputs[0], out.inputs["Surface"])
        bark = bpy.data.materials.get("Timber interior") or m
        ob = b.obj(name, "V3 library", [m, bark], smooth=True)
        return ob

    def build_slope_dressing(grid):
        """olive groves on the lower slopes west and south-west of the theatre, maquis clumps and limestone
        outcrops up toward the rock, a few cypresses by the sanctuary and in the town ([R]: planting is generic)"""
        import numpy as np
        from mathutils import kdtree
        xs, ys, Z = grid
        houses = bpy.data.objects.get("City houses")
        hc = []
        if houses:
            co = np.empty(len(houses.data.vertices) * 3, np.float32)
            houses.data.vertices.foreach_get("co", co)
            hc = co.reshape(-1, 14, 3)[:, :4].mean(axis=1)
        kd = kdtree.KDTree(len(hc))
        for i, p in enumerate(hc):
            kd.insert((float(p[0]), float(p[1]), 0.0), i)
        kd.balance()
        rng = random.Random(4320)

        def zat(x, y):
            return float(terrain_z(np, grid, np.array([x]), np.array([y]))[0])

        def slope(x, y):
            return math.hypot(zat(x + 1, y) - zat(x - 1, y), zat(x, y + 1) - zat(x, y - 1)) / 2

        def free(x, y, clear=9.0):
            if len(hc) and kd.find((x, y, 0.0))[2] < clear:
                return False
            r = (Vector((x, y)) - ORCH_C).length
            if r < 54.0 or (abs(x) < 16 and -9 < y < 14):
                return False                      # theatron, orchestra, skene
            if (Vector((x, y)) - Vector((-65.0, 192.0))).length < 75:
                return False                      # the plateau
            return True

        olive_c = bpy.data.collections.get("VEG searsia_burchellii (olive stand-in)")
        shrub_c = bpy.data.collections.get("VEG searsia_lucida")
        scrub_c = bpy.data.collections.get("VEG wild_rooibos_bush")
        n_ol = len(olive_c.objects) if olive_c else 0
        olives, shrubs, scrubs, rocks = [], [], [], []
        # groves: rows 8.5 m apart along the contour, 7 m in the row, patchy
        ang = math.radians(-20)
        ca, sa = math.cos(ang), math.sin(ang)
        rej = {"region": 0, "noise": 0, "free": 0, "slope": 0}
        for i in range(-24, 25):
            for j in range(-26, 26):
                u, v = i * 7.0, j * 8.5
                x = -95 + u * ca - v * sa + rng.uniform(-1.2, 1.2)
                y = 10 + u * sa + v * ca + rng.uniform(-1.2, 1.2)
                if not (-200 < x < -30 and -110 < y < 110):
                    rej["region"] += 1
                    continue
                if noise.noise(Vector((x * 0.012, y * 0.012, 3.3))) < -0.25 or rng.random() < 0.12:
                    rej["noise"] += 1
                    continue
                if not free(x, y, 6.0):
                    rej["free"] += 1
                    continue
                if slope(x, y) > 0.6:
                    rej["slope"] += 1
                    continue
                olives.append((x, y, zat(x, y) - 0.15, rng.uniform(0, 6.28), rng.uniform(1.0, 1.45), rng.randrange(max(1, n_ol)), 0.0, 0.0))
        # maquis clumps and grey scrub on the rougher ground, outcrops of the Acropolis limestone
        for k in range(9000):
            x, y = rng.uniform(-230, 60), rng.uniform(-90, 150)
            if not free(x, y, 6.0):
                continue
            sl = slope(x, y)
            if sl > 1.1:
                continue
            n = noise.noise(Vector((x * 0.03, y * 0.03, 8.1)))
            up = min(1.0, max(0.0, (zat(x, y) - 5.0) / 30.0))
            if rng.random() < 0.35 * (0.5 + n) + 0.25 * up:
                if rng.random() < 0.55:
                    shrubs.append((x, y, zat(x, y) - 0.1, rng.uniform(0, 6.28), rng.uniform(1.3, 2.4),
                                   rng.randrange(len(shrub_c.objects) if shrub_c else 1), 0.0, 0.0))
                else:
                    scrubs.append((x, y, zat(x, y) - 0.05, rng.uniform(0, 6.28), rng.uniform(1.2, 2.2),
                                   rng.randrange(len(scrub_c.objects) if scrub_c else 1), 0.0, 0.0))
            if rng.random() < 0.012 + 0.10 * up * (sl > 0.35):
                s = rng.uniform(0.3, 1.1) * (1.5 if sl > 0.5 else 1.0)
                rocks.append((x, y, zat(x, y) - s * rng.uniform(0.45, 0.7), rng.uniform(0, 6.28), s, rng.randrange(7),
                              rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)))
        if olive_c:
            scatter_points("Olive groves v3", olive_c, olives, "Vegetation")
        if shrub_c:
            scatter_points("Maquis v3", shrub_c, shrubs, "Vegetation")
        if scrub_c:
            scatter_points("Grey scrub v3", scrub_c, scrubs, "Vegetation")
        # limestone outcrops reuse the pebble shapes with a rock material
        oc = library_collection("V3 outcrops")
        om = mat_outcrop()
        for k in range(7):
            src = bpy.data.objects.get(f"Pebble v3 {k}")
            if src:
                o = bpy.data.objects.new(f"Outcrop v3 {k}", src.data.copy())
                o.data.materials.clear()
                o.data.materials.append(om)
                oc.objects.link(o)
        scatter_points("Limestone outcrops v3", oc, rocks, "Landscape")
        # cypresses
        cc = library_collection("V3 cypresses")
        for k in range(3):
            o = cypress_mesh(f"Cypress v3 {k}", 90 + k, (10.5, 13.0, 15.5)[k])
            for c in o.users_collection:
                c.objects.unlink(o)
            cc.objects.link(o)
        cyp = []
        spots = [(-38, -46), (-30, -40), (35, -50), (44, -58), (-60, -78), (-20, -112), (22, -95), (-52, 40),
                 (-120, -12), (-138, 30), (90, 20)]
        for (x, y) in spots:
            x += rng.uniform(-3, 3)
            y += rng.uniform(-3, 3)
            if len(hc) and kd.find((x, y, 0.0))[2] < 6:
                continue
            cyp.append((x, y, zat(x, y) - 0.3, rng.uniform(0, 6.28), rng.uniform(0.85, 1.1), rng.randrange(3), 0.0, 0.0))
        scatter_points("Cypresses v3", cc, cyp, "Vegetation")
        log("olive rejections", rej)
        log("slopes: %d olives, %d maquis, %d scrub, %d outcrops, %d cypresses" % (len(olives), len(shrubs), len(scrubs), len(rocks), len(cyp)))

    # ------------------------------------------------------------- 3e. air: a thin layer of dust over the orchestra
    def build_air():
        """homogeneous dust/haze in a box round the stage and the front rows, a little denser near the ground:
        it lifts the shadows slightly toward the sky colour and makes the low sun visible in the air"""
        b = Builder()
        b.box(-45.0, 45.0, -25.0, 48.0, -1.0, 28.0)
        ob = b.obj("Stage air v3", "Landscape", [])
        m = new_mat("Dust haze v3")
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        sep = nt.n("ShaderNodeSeparateXYZ")
        nt.l(tc.outputs["Object"], sep.inputs[0])
        # density: 0.0016 / m aloft rising to ~0.006 / m in the first metres above the ground, slightly patchy
        low = smooth_range(nt, sep.outputs["Z"], 4.0, 0.0, 0.0, 1.0)
        patch = nz_tex(nt, tc.outputs["Object"], 0.12, 2.0, 0.5)
        dens = mth(nt, "ADD", 0.0006, mth(nt, "MULTIPLY", mth(nt, "MULTIPLY", low, 0.0022), smooth_range(nt, patch, 0.3, 0.7, 0.5, 1.2)))
        vol = nt.n("ShaderNodeVolumePrincipled", in_Anisotropy=0.35)
        vol.inputs["Color"].default_value = (0.92, 0.86, 0.78, 1)
        nt.l(dens, vol.inputs["Density"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(vol.outputs[0], out.inputs["Volume"])
        ob.data.materials.append(m)
        ob.visible_shadow = False
        sc.cycles.volume_step_rate = 4.0
        sc.cycles.volume_max_steps = 256
        return ob

    # ------------------------------------------------------------- 4. compositor: haze, bloom, vignette
    _HDRI_PX = {}

    def hdri_horizon(theta, half_width=0.6, el0=0.5, el1=5.0):
        """mean sky radiance just above the horizon around scene direction angle theta (rad), as the world
        shader shows it: the colour that distant land should fade to (aerial perspective)"""
        import numpy as np
        if "px" not in _HDRI_PX:
            im = bpy.data.images.load(HDRI, check_existing=True)
            w, h = im.size
            a = np.empty(w * h * 4, np.float32)
            im.pixels.foreach_get(a)
            _HDRI_PX["px"] = a.reshape(h, w, 4)[..., :3]
        px = _HDRI_PX["px"]
        h, w = px.shape[:2]
        rot = _HDRI_PX.get("rot", 0.0)
        r0, r1 = int((0.5 + el0 / 180) * h), int((0.5 + el1 / 180) * h)
        cols = []
        for k in range(-6, 7):
            t = theta + half_width * k / 6
            u = (0.5 - (t + rot) / (2 * math.pi)) % 1.0
            cols.append(px[r0:r1, int(u * w) % w].mean(axis=0))
        c = np.minimum(np.mean(cols, axis=0), 14.0) * HDRI_STRENGTH
        lum = float(c @ np.array([0.2126, 0.7152, 0.0722]))
        c = lum + (c - lum) * 0.88
        return tuple(float(x) for x in c)

    HAZE = (0.50, 0.53, 0.58)

    def build_compositor(shot):
        cam = sc.camera
        fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
        haze_col = hdri_horizon(math.atan2(fwd.y, fwd.x))
        log("haze colour", tuple(round(c, 3) for c in haze_col))
        sc.use_nodes = True
        sc.render.film_transparent = True
        vl = sc.view_layers[0]
        vl.use_pass_mist = True
        vl.use_pass_environment = True
        nt = NT(sc.node_tree)
        rl = nt.n("CompositorNodeRLayers")
        # aerial perspective from the mist pass (linear 40 m .. 9 km), toward a pale late-afternoon haze
        mul = nt.n("CompositorNodeMath", operation="MULTIPLY")
        mul.inputs[1].default_value = 0.85 if shot == "establishing" else 0.78
        nt.l(rl.outputs["Mist"], mul.inputs[0])
        pw = nt.n("CompositorNodeMath", operation="POWER")
        pw.inputs[1].default_value = 0.85
        nt.l(mul.outputs[0], pw.inputs[0])
        haze = nt.n("CompositorNodeRGB")
        haze.outputs[0].default_value = (*haze_col, 1.0)
        sa = nt.n("CompositorNodeSetAlpha", mode="APPLY")
        nt.l(haze.outputs[0], sa.inputs["Image"])
        nt.l(rl.outputs["Alpha"], sa.inputs["Alpha"])
        mix = nt.n("CompositorNodeMixRGB", blend_type="MIX")
        nt.l(pw.outputs[0], mix.inputs[0])
        nt.l(rl.outputs["Image"], mix.inputs[1])
        nt.l(sa.outputs[0], mix.inputs[2])
        keep = nt.n("CompositorNodeSetAlpha", mode="REPLACE_ALPHA")
        nt.l(mix.outputs[0], keep.inputs["Image"])
        nt.l(rl.outputs["Alpha"], keep.inputs["Alpha"])
        over = nt.n("CompositorNodeAlphaOver")
        nt.l(rl.outputs["Env"], over.inputs[1])
        nt.l(keep.outputs[0], over.inputs[2])
        # subtle bloom on the sunlit highlights (scene-linear threshold, before the view transform)
        gl = nt.n("CompositorNodeGlare", glare_type="BLOOM", quality="HIGH")
        gl.inputs["Threshold"].default_value = 1.6
        gl.inputs["Strength"].default_value = 0.22
        gl.inputs["Size"].default_value = 0.55
        gl.inputs["Saturation"].default_value = 1.0
        nt.l(over.outputs[0], gl.inputs["Image"])
        # soft vignette
        el = nt.n("CompositorNodeEllipseMask")
        el.inputs["Size"].default_value = (1.15, 1.05)
        bl = nt.n("CompositorNodeBlur", filter_type="FAST_GAUSS", use_relative=True)
        bl.factor_x = bl.factor_y = 0.32
        nt.l(el.outputs["Mask"], bl.inputs["Image"])
        mr = nt.n("CompositorNodeMapRange")
        mr.inputs["To Min"].default_value = 0.88
        mr.inputs["To Max"].default_value = 1.0
        nt.l(bl.outputs[0], mr.inputs["Value"])
        vg = nt.n("CompositorNodeMixRGB", blend_type="MULTIPLY")
        nt.l(gl.outputs[0], vg.inputs[1])
        nt.l(mr.outputs[0], vg.inputs[2])
        comp = nt.n("CompositorNodeComposite", use_alpha=False)
        nt.l(vg.outputs[0], comp.inputs["Image"])

    # ------------------------------------------------------------- 5. cameras
    def theatron_seat_z(x, y):
        """top of the bench at (x, y): ray down onto the built benches"""
        dg = bpy.context.evaluated_depsgraph_get()
        ob = bpy.data.objects["Theatron benches"]
        hit, loc, nor, idx, o, m = sc.ray_cast(dg, Vector((x, y, 30.0)), Vector((0, 0, -1)))
        if hit and o.name == ob.name:
            return loc.z
        return None

    def bench_point(row, ang_deg, back=0.0):
        """a point on bench `row` (0 = front) at angle `ang_deg` from the theatre axis (+ = east, +X)"""
        rs = TH_R0 + TH_ROW * row + 0.12 + back
        a = math.radians(ang_deg)
        return Vector((ORCH_C.x + rs * math.sin(a), ORCH_C.y + rs * math.cos(a)))

    def make_camera(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36.0
        cd.clip_start = 0.05
        cd.clip_end = 60000.0
        cam = bpy.data.objects.new(name, cd)
        coll("Cameras").objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus if focus else (Vector(target) - Vector(loc)).length
            cd.dof.aperture_blades = 7
            cd.dof.aperture_rotation = math.radians(12)
        return cam

    AUD_ROW, AUD_ANG = 1, -4.0             # second bench, just west of the central aisle
    AUD_LENS = 45.0
    AUD_EYE = 0.70                         # seated eye height above the plank (m)
    AUD_TOP_MARGIN = 1.3                   # degrees of sky kept above the skene roof

    def seat_on_bench(row, ang):
        """nearest point on a bench plank (the rows are straight chords, with small gaps between them)"""
        for k in range(0, 40):
            for s in (1, -1):
                a = ang + s * 0.25 * k
                p = bench_point(row, a, back=-0.04)
                z = theatron_seat_z(p.x, p.y)
                if z is not None:
                    return p, z, a
        p = bench_point(row, ang)
        return p, 0.4, ang

    def build_audience_camera():
        p, z, a = seat_on_bench(AUD_ROW, AUD_ANG)
        eye = Vector((p.x, p.y, z + AUD_EYE))
        to = Vector((0.1, 0.3, 1.0)) - eye
        horiz = Vector((to.x, to.y, 0.0)).length
        # pitch: the skene's roof edge sits just under the top of the frame, so the frame reaches down to the
        # heads of the front row (16:9 on a 36 mm wide sensor: the vertical sensor is 20.25 mm)
        half_v = math.atan(36.0 * 9 / 16 / 2 / AUD_LENS)
        roof = math.atan2(5.0 - eye.z, eye.y - 0.1)
        pitch = roof + math.radians(AUD_TOP_MARGIN) - half_v
        tgt = eye + Vector((to.x, to.y, 0.0)).normalized() * horiz + Vector((0, 0, horiz * math.tan(pitch)))
        focus = (Vector((0.05, 0.45, 0.9)) - eye).length
        cam = make_camera("V3 audience eye", eye, tgt, AUD_LENS, fstop=2.8, focus=focus)
        log("audience camera", tuple(round(c, 2) for c in eye), "bench angle %.2f, seat z %.2f, focus %.1f m" % (a, z, focus))
        return cam

    # --- the audience in front of the camera: simple seated figures seen from behind (they are out of focus)
    def mat_wool(name, color, sheen=0.6):
        m = new_mat(name)
        nt = NT(m.node_tree)
        tc = nt.n("ShaderNodeTexCoord")
        nz = nz_tex(nt, tc.outputs["Object"], 18.0, 3.0, 0.6)
        col = mix_col(nt, smooth_range(nt, nz, 0.3, 0.7, 0.0, 0.25), color, tuple(c * 0.7 for c in color))
        bs = nt.n("ShaderNodeBsdfPrincipled", in_Roughness=0.92)
        bs.inputs["Sheen Weight"].default_value = sheen
        nt.l(col, bs.inputs["Base Color"])
        out = nt.n("ShaderNodeOutputMaterial")
        nt.l(bs.outputs[0], out.inputs["Surface"])
        return m

    def ellipsoid(b, c, r, mi, seg=16, rings=10, folds=0.0, seed=0):
        rng = random.Random(seed)
        ph = rng.uniform(0, 6.28)
        verts, faces = [], []
        for j in range(rings + 1):
            t = math.pi * j / rings
            for i in range(seg):
                a = 2 * math.pi * i / seg
                f = 1.0 + folds * (0.6 * math.sin(7 * a + ph) + 0.4 * math.sin(13 * a + 2 * ph)) * math.sin(t) ** 2
                verts.append((c[0] + r[0] * f * math.sin(t) * math.cos(a), c[1] + r[1] * f * math.sin(t) * math.sin(a),
                              c[2] + r[2] * math.cos(t)))
        for j in range(rings):
            for i in range(seg):
                a0, a1 = j * seg + i, j * seg + (i + 1) % seg
                faces.append((a0, a1, a1 + seg, a0 + seg))
        b.add(verts, faces, mi)

    def spectator(name, seat, face_to, z, cloth, seed, cover_head=False):
        """seated, facing the stage: draped torso and shoulders, neck, an ovoid head with ears and curly
        hair, or a fold of the himation drawn up over the head"""
        rng = random.Random(seed)
        b = Builder()
        lean = rng.uniform(-0.02, 0.04)
        sh = rng.uniform(1.0, 1.06)
        tilt = rng.uniform(-0.03, 0.03)
        ellipsoid(b, (0.0, 0.02, z + 0.30 * sh), (0.21 * sh, 0.15, 0.34 * sh), 0, 22, 12, folds=0.07, seed=seed)
        ellipsoid(b, (0.0, lean, z + 0.565 * sh), (0.235 * sh, 0.135, 0.09), 0, 22, 8, folds=0.04, seed=seed + 1)
        hz = z + 0.80 * sh
        hx = tilt * 0.6
        b.cyl((hx * 0.5, lean, z + 0.58 * sh), (hx, lean + 0.012, hz - 0.06), 0.056, 12, 1)
        ellipsoid(b, (hx, lean + 0.012, hz), (0.076, 0.096, 0.114), 1, 18, 12)
        for sx in (-1, 1):
            ellipsoid(b, (hx + sx * 0.077, lean + 0.018, hz - 0.012), (0.013, 0.026, 0.034), 1, 10, 6)
        if cover_head:
            # himation pulled over the head: a hood that falls to the shoulders
            ellipsoid(b, (hx, lean - 0.006, hz + 0.012), (0.098, 0.112, 0.128), 0, 20, 12, folds=0.05, seed=seed + 2)
            ellipsoid(b, (hx * 0.5, lean - 0.02, hz - 0.13), (0.13, 0.11, 0.12), 0, 20, 10, folds=0.08, seed=seed + 4)
        else:
            ellipsoid(b, (hx, lean - 0.014, hz + 0.024), (0.084, 0.099, 0.1), 2, 22, 12, folds=0.09, seed=seed + 3)
            ellipsoid(b, (hx, lean - 0.05, hz - 0.03), (0.07, 0.05, 0.07), 2, 14, 8, folds=0.12, seed=seed + 5)
        hair = mat_wool("Spectator hair v3", (0.035, 0.026, 0.02), sheen=0.5)
        skin = bpy.data.materials.get("Skin (sun-tanned)") or mat_wool("Spectator skin v3", (0.42, 0.26, 0.17), 0.1)
        ob = b.obj(name, "V3 spectators", [cloth, skin, hair], smooth=True)
        d = Vector((face_to[0] - seat.x, face_to[1] - seat.y))
        ob.rotation_euler = (0.0, 0.0, math.atan2(d.y, d.x) - math.pi / 2)
        ob.location = (seat.x, seat.y, 0.0)
        return ob

    SPECTATORS = [   # (row, angle from the axis, cloth colour, hooded)
        (0, -5.35, (0.30, 0.26, 0.21), False),
        (0, -2.75, (0.16, 0.11, 0.08), True),
    ]

    def build_spectators():
        for k, (row, ang, colr, hood) in enumerate(SPECTATORS):
            p, z, a = seat_on_bench(row, ang)
            cloth = mat_wool(f"Spectator wool {k} v3", colr)
            spectator(f"Spectator {k} v3", p, (0.0, 2.0), z, cloth, 50 + k, hood)

    # from the south-west, about 190 m from the theatre: west of the Parthenon's west front (so its pediment
    # shows, in the low sun), close enough that the theatre is the subject, the town off to the right
    EST = dict(loc=(-152.0, -92.0, 58.0), tgt=(-33.0, 68.0, 31.0), lens=35.0)

    def build_establishing_camera():
        e = dict(EST)
        if ARGS["est_cam"]:
            v = [float(t) for t in ARGS["est_cam"].split(",")]
            e = dict(loc=tuple(v[0:3]), tgt=tuple(v[3:6]), lens=v[6])
        return make_camera("V3 establishing", Vector(e["loc"]), Vector(e["tgt"]), e["lens"])

    # ------------------------------------------------------------- render
    def clear_exposure_animation():
        ad = sc.animation_data
        if ad and ad.action:
            for fc in list(ad.action.fcurves):
                if fc.data_path.startswith("view_settings"):
                    ad.action.fcurves.remove(fc)

    def render_settings(w, h, spp):
        r = sc.render
        r.engine = "CYCLES"
        c = sc.cycles
        c.device = "CPU"
        c.samples = spp
        c.use_denoising = True
        c.denoiser = "OPENIMAGEDENOISE"
        c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        c.denoising_prefilter = "ACCURATE"
        c.denoising_quality = "HIGH"
        c.use_adaptive_sampling = False
        c.max_bounces = 8
        c.diffuse_bounces = 3
        c.glossy_bounces = 2
        c.transparent_max_bounces = 8
        c.volume_bounces = 0
        c.sample_clamp_indirect = 6.0
        r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
        r.use_overwrite = True
        r.use_placeholder = False
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGB"
        r.image_settings.color_depth = "8"
        vs = sc.view_settings
        vs.view_transform = "AgX"
        vs.look = "AgX - Medium High Contrast"

    def verify_render(path):
        """after boilerplate.verify_render (skill): mean luminance, clipping, flatness"""
        import numpy as np
        im = bpy.data.images.load(path, check_existing=False)
        w, h = im.size
        px = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        bpy.data.images.remove(im)
        px = px.reshape(h, w, 4)
        lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        res = {"mean_luminance": round(float(lum.mean()), 3), "clipped_white_%": round(float((lum > 0.98).mean() * 100), 2),
               "near_black_%": round(float((lum < 0.02).mean() * 100), 2), "contrast_std": round(float(lum.std()), 3)}
        warn = []
        if res["mean_luminance"] < 0.05:
            warn.append("nearly black")
        if res["clipped_white_%"] > 5:
            warn.append("blown out")
        if res["contrast_std"] < 0.02:
            warn.append("flat")
        res["warnings"] = warn
        log("RENDER QA", os.path.basename(path), res)
        return res

    SHOTS = {
        "audience": dict(frame=FRAME_AUDIENCE, cam="V3 audience eye", exposure=0.55, tag="v3_audience_eye"),
        "establishing": dict(frame=FRAME_ESTABLISHING, cam="V3 establishing", exposure=0.25, tag="v3_establishing"),
    }

    AIR = [None]

    def render_shot(shot, w, h, spp, outdir):
        s = SHOTS[shot]
        if AIR[0] is not None:
            AIR[0].hide_render = (shot != "audience")
        for m in sc.timeline_markers:
            m.camera = None
        sc.camera = bpy.data.objects[s["cam"]]
        sc.frame_set(s["frame"])
        build_compositor(shot)
        sc.view_settings.exposure = s["exposure"]
        render_settings(w, h, spp)
        path = os.path.join(outdir, s["tag"] + ".png")
        sc.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t
        log("RENDER %s %dx%d %d spp: %.1f s" % (shot, w, h, spp, dt))
        verify_render(path)
        with open(os.path.join(outdir, "render_times.txt"), "a") as f:
            f.write("%s\t%s\t%dx%d\t%d spp\t%.1f s\n" % (time.strftime("%Y-%m-%d %H:%M"), shot, w, h, spp, dt))
        return dt

    def main():
        t0 = time.time()
        if ARGS["sun_study"]:
            sun_study()
            return
        clear_exposure_animation()
        build_light()
        build_materials()
        build_facade()
        build_doors()
        fields = build_ground()
        build_ground_scatter(fields)
        build_spectators()
        build_town()
        retint_vegetation()
        retune_far_land()
        build_slope_dressing(fields[6])
        build_audience_camera()            # (before the air box: seat heights are found by ray casts)
        build_establishing_camera()
        AIR[0] = build_air() if ARGS["volume"] else None
        log("look pass built in %.1f s" % (time.time() - t0))
        w, h = (int(v) for v in ARGS["res"].split("x"))
        outdir = os.path.abspath(ARGS["out"])
        os.makedirs(outdir, exist_ok=True)
        if ARGS["save_blend"]:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WORK, "build", "scene_v3.blend"), compress=True)
        for shot in ARGS["shots"].split(","):
            render_shot(shot, w, h, ARGS["spp"], outdir)


if __name__ == "__main__":
    if IN_BLENDER:
        main()
    else:
        driver(parse_args(sys.argv[1:]))
