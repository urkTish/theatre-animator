"""Ekkyklema 3D -- OPTION FOR REVIEW: "v3 figures" (MakeHuman bodies, period masks and costume).

Not part of the main build: it never touches build_scene.py, render_looktest.py or the main
.blend files. It works on a COPY of the built scene and writes to its own folders.
The research behind every choice is in MASKS_AND_COSTUME.md (same folder).

    # everything (spawns Blender for the stages, then composes the comparison sheets):
    python3 figures_v3.py all --scene COPY.blend --work DIR --mpfb-resources DIR
                              [--assets DIR] [--samples 64] [--repo-out DIR]

    # the stages one by one (each re-runnable; later ones resume from the checkpoints in DIR)
    BLENDER_USER_RESOURCES=DIR blender -b -P figures_v3.py -- build --scene COPY.blend --work DIR [--stage pose|robes]
    BLENDER_USER_RESOURCES=DIR blender -b -P figures_v3.py -- build --scene COPY.blend --work DIR --resume robes|masks
    blender -b COPY.blend -P figures_v3.py -- render --work DIR [--samples 64] [--only AB] [--shots tableau,cutaway,crop]
    python3 figures_v3.py compose --work DIR [--repo-out DIR]

build   needs MPFB 2 (GPL; build time only) in an isolated Blender user folder, see
        ../MAKEHUMAN_NOTES.md. Four all-male MakeHuman bodies (CC0 assets) posed on the
        "default" rig, then:
        robes    long-sleeved patterned robes (actors) and short tunics (stagehands): one closed
                 shell (lofted torso, skirt and sleeves, voxel-remeshed), skinned, belted, and
                 cloth-simulated from the T-pose into the pose with the body as collider; frozen.
        masks    full-head masks moulded on each actor's posed head: idealised face, slightly
                 parted lips, painted eyes, a hand-painted UV texture (tanned male paint), hair and
                 beard as clumped hair curves attached to the mask and kept out of the cloth.
        drapes   the standing actor's himation (wrapped from the left shoulder round the back and
                 hips, end over the left forearm) and the couch blanket, simulated on the frozen
                 figures and frozen.
        Checkpoints: DIR/robes.blend, DIR/masks.blend, DIR/figures.blend (final, packed).
render  opens the scene copy, appends the figures, hides the mannequins, renders the look-test
        frames: A = current mannequins, B = v3 figures (tableau, cutaway, 3x close crop).
compose side-by-side sheets "Current" | "Option: v3 figures", JPG copies for the repo.
"""
import json
import math
import os
import random
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
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

FPS = 24
DEFAULT_ASSETS = "/tmp/claude-0/-home-user/a4092da5-d9e8-554b-87a8-27ec227e9bb1/scratchpad/3d/assets"


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


def srgb(c):
    """sRGB 0-255 triple -> linear 0-1"""
    out = []
    for v in c:
        v = v / 255.0
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return tuple(out)


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

PAT_REP = 0.10                                # pattern repeat width (m)
PAT_H_BODY, PAT_H_SLEEVE = 1.62, 0.80         # pattern image heights (m)

# dyes (sRGB swatches; MASKS_AND_COSTUME.md: plant/insect dyes, scene palette kept)
DYE = {
    "undyed": (214, 202, 178), "cream": (226, 214, 188), "saffron": (205, 150, 50), "saffron_faded": (200, 158, 78),
    "madder": (150, 46, 34), "madder_dark": (104, 30, 26), "woad": (46, 66, 104), "woad_light": (86, 108, 140),
    "dark": (44, 34, 28), "oat": (176, 160, 132), "dun": (118, 98, 76), "leather": (70, 46, 30),
}



# =============================================================================
# painting (plain Python 3: numpy + Pillow; Blender calls these through the system
# python3, because Blender's bundled Python has no Pillow)
# =============================================================================
def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

# ---------------------------------------------------------------------------
# mask painting (numpy + PIL in the cylindrical UV space): flat tanned paint with
# crisp drawn features, like the vase-painters' masks; a dark wig ground under the hair
# ---------------------------------------------------------------------------
def paint_mask_texture(name, ms, land, azgrid_path, path, W=4096, Hh=2048):
    """land: rest landmarks (m); azgrid_path: .npz with the azimuth of the face surface on a
    1 mm (x, z) grid, made in Blender from the mask's rest vertices"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    ez, ex, mz, yc, Z0, Z1 = land["ez"], land["ex"], land["mz"], land["yc"], land["Z0"], land["Z1"]
    G = np.load(azgrid_path)
    gx, gz, gaz = G["xs"], G["zs"], G["az"]

    def az(x, z):
        i = int(np.clip(np.searchsorted(gx, x), 0, len(gx) - 1))
        j = int(np.clip(np.searchsorted(gz, z), 0, len(gz) - 1))
        return float(gaz[j, i])

    def px(x, z):
        a = az(x, z)
        return ((0.5 + a / (2 * math.pi)) * W, (1.0 - (z - Z0) / (Z1 - Z0)) * Hh)
    SS = 1
    base = np.array(srgb(ms["paint"]))
    # base paint with a soft mottle (hand-laid gesso and pigment)
    yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
    rng = np.random.default_rng(ms["seed"])
    n1 = rng.standard_normal((Hh // 32 + 2, W // 32 + 2)).astype(np.float32)
    from PIL import Image as _I
    mott = np.array(_I.fromarray(((n1 - n1.min()) / (np.ptp(n1) + 1e-6) * 255).astype(np.uint8)).resize((W, Hh), _I.BICUBIC)).astype(np.float32) / 255.0 - 0.5
    img = np.ones((Hh, W, 3), np.float32) * base[None, None, :]
    img *= (1.0 + 0.10 * mott[..., None])
    # coordinates of each texel: azimuth (rad), z (m)
    A = (xx / W - 0.5) * 2 * math.pi
    Zt = Z0 + (1.0 - yy / Hh) * (Z1 - Z0)
    R_face = 0.095

    def blob(a0, z0, ra, rz, col, k):
        nonlocal img
        g = np.exp(-(((A - a0) * R_face / ra) ** 2 + ((Zt - z0) / rz) ** 2))
        img = img * (1 - k * g[..., None]) + np.array(srgb(col))[None, None, :] * (k * g[..., None])
    # cheeks: warm flush; temples and jaw a little deeper
    for sx in (1, -1):
        a0 = az(sx * (ex + 0.008), ez - 0.035)
        blob(a0, ez - 0.035, 0.022, 0.018, (176, 92, 64), 0.30)
    blob(0.0, mz - 0.03, 0.03, 0.015, (150, 96, 66), 0.15)              # chin shadow paint
    img = np.clip(img, 0, 1)
    # to 8-bit sRGB for drawing crisp strokes with PIL (supersampled 2x)
    def to_srgb8(a):
        a = np.clip(a, 0, 1)
        s = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)
        return (s * 255 + 0.5).astype(np.uint8)
    im = Image.fromarray(to_srgb8(img)).resize((W * 2, Hh * 2), Image.BICUBIC)
    d = ImageDraw.Draw(im)

    def P2(x, z):
        a, b = px(x, z)
        return (a * 2, b * 2)

    def stroke(points, width_m, col, taper=True):
        """a painted stroke along points [(x, z)], width in metres on the face"""
        k = len(points)
        for i in range(k - 1):
            t = i / max(1, k - 2)
            w = width_m * (math.sin(math.pi * min(1, max(0, t * 0.9 + 0.05))) ** 0.6 if taper else 1.0)
            wp = max(1, int(w / (Z1 - Z0) * Hh * 2))
            d.line([P2(*points[i]), P2(*points[i + 1])], fill=col, width=wp)
            d.ellipse([P2(*points[i + 1])[0] - wp / 2, P2(*points[i + 1])[1] - wp / 2,
                       P2(*points[i + 1])[0] + wp / 2, P2(*points[i + 1])[1] + wp / 2], fill=col)
    brow = tuple(ms["brow"])
    dark = (44, 28, 22)
    old = ms["age"] == "old"
    eyes = land.get("eyes") or []
    mw = land.get("mw", 0.022)
    # brows on their own layer, blurred: painted brows with soft edges, not cartoon outlines
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)

    def stroke_on(dd, points, width_m, col, taper=True):
        k = len(points)
        for i in range(k - 1):
            tt = i / max(1, k - 2)
            w = width_m * (math.sin(math.pi * min(1, max(0, tt * 0.9 + 0.05))) ** 0.6 if taper else 1.0)
            wp = max(1, int(w / (Z1 - Z0) * Hh * 2))
            a, b = P2(*points[i]), P2(*points[i + 1])
            dd.line([a, b], fill=col, width=wp)
            dd.ellipse([b[0] - wp / 2, b[1] - wp / 2, b[0] + wp / 2, b[1] + wp / 2], fill=col)
    for E in eyes:
        cx, cz, w, h = E["cx"], E["cz"], E["w"], E["h"]
        sg = 1.0 if cx > 0 else -1.0
        pts = E["pts"]
        upper = sorted([q for q in pts if q[1] >= cz], key=lambda q: q[0])
        lower = sorted([q for q in pts if q[1] < cz], key=lambda q: q[0])
        # brow: over the orbit, a gentle arc, thickest a third of the way out, tapering outward
        bpts = []
        for i in range(16):
            tt = i / 15
            x = cx + sg * (-0.62 * w + 1.42 * w * tt)
            z = cz + 0.5 * h + 0.0115 + 0.0042 * math.sin(math.pi * min(1.0, tt * 1.1)) - 0.0025 * tt
            bpts.append((x, z))
        col = brow + (215,)
        stroke_on(dl, bpts, 0.0042 if not old else 0.0046, col)
        stroke_on(dl, [(x, z + 0.0012) for x, z in bpts[2:12]], 0.0022, col)
        # upper lid line along the real lid margin (darker and heavier at the outer corner)
        if len(upper) > 2:
            stroke_on(d, [(x, z + 0.0005) for x, z in upper], 0.0015, dark, taper=False)
            outer = max(upper, key=lambda q: sg * q[0])
            stroke_on(d, [(outer[0] - sg * 0.004, outer[1] + 0.0004), (outer[0] + sg * 0.0025, outer[1] - 0.0004)], 0.0016, dark)
        if len(lower) > 2:
            stroke_on(d, [(x, z - 0.0003) for x, z in lower], 0.0007, (104, 66, 48), taper=True)
        # lid crease
        if len(upper) > 3:
            cr = [(x, z + 0.0058 + 0.0012 * math.sin(math.pi * k / max(1, len(upper) - 1))) for k, (x, z) in enumerate(upper)]
            stroke_on(d, cr[1:-1], 0.0008, (122, 80, 58))
        if old:
            for k in range(3):     # crow's feet and the fold under the eye, lightly drawn
                x0 = cx + sg * (0.55 * w + 0.003)
                stroke_on(d, [(x0, cz + 0.002 - 0.0035 * k), (x0 + sg * 0.008, cz + 0.004 - 0.006 * k)], 0.0007, (124, 84, 60))
            stroke_on(d, [(cx - sg * 0.35 * w, cz - 0.5 * h - 0.004), (cx, cz - 0.5 * h - 0.0055), (cx + sg * 0.4 * w, cz - 0.5 * h - 0.0035)], 0.0009, (128, 86, 62))
        # nasolabial fold
        nl = [(sg * (0.016 + 0.011 * i / 8), mz + 0.026 - 0.029 * i / 8) for i in range(9)]
        stroke_on(d, nl, 0.0012 if old else 0.0008, (126, 80, 58))
    from PIL import ImageFilter as _F
    lay = lay.filter(_F.GaussianBlur(2.2))
    im.paste(lay, (0, 0), lay)
    if old:
        ez_ = sum(E["cz"] for E in eyes) / len(eyes) if eyes else ez
        for k, zz in enumerate((ez_ + 0.044, ez_ + 0.054, ez_ + 0.064)):
            ln = [(-0.03 + 0.06 * i / 10, zz + 0.0025 * math.sin(math.pi * i / 10) + 0.0008 * math.sin(7 * i)) for i in range(11)]
            stroke_on(d, ln, 0.0008, (134, 92, 66))
    # lips: muted red-brown, sized on the real lip parting; darker parting line
    lip = tuple(ms["lips"])
    c_ = mw + 0.0025
    poly_u = [(-c_, mz + 0.0004), (-0.66 * c_, mz + 0.0058), (-0.25 * c_, mz + 0.0098), (0.0, mz + 0.0080),
              (0.25 * c_, mz + 0.0098), (0.66 * c_, mz + 0.0058), (c_, mz + 0.0004), (0.0, mz + 0.0012)]
    poly_l = [(-0.92 * c_, mz - 0.0004), (-0.5 * c_, mz - 0.0092), (0.0, mz - 0.0118), (0.5 * c_, mz - 0.0092), (0.92 * c_, mz - 0.0004),
              (0.0, mz - 0.0016)]
    d.polygon([P2(*q) for q in poly_u], fill=lip)
    d.polygon([P2(*q) for q in poly_l], fill=tuple(min(255, int(c * 1.06)) for c in lip))
    stroke_on(d, [(-c_, mz + 0.0002), (-0.4 * c_, mz + 0.0008), (0.0, mz + 0.0005), (0.4 * c_, mz + 0.0008), (c_, mz + 0.0002)], 0.0012, (74, 32, 26), taper=False)
    # wig ground under the hair and the beard (so gaps between strands read as hair, not plaster)
    hair_col = (38, 30, 25) if ms.get("grey", 0) < 0.2 else (88, 82, 76)
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    arr = np.array(im).astype(np.float32) / 255.0
    arr = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    arr = np.array(Image.fromarray(to_srgb8(arr)).resize((W, Hh), Image.LANCZOS)).astype(np.float32) / 255.0
    arr = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    # hair / beard masks in (azimuth, z): computed from the same rules as the hair roots
    hm = np.zeros((Hh, W), np.float32)
    Xs = np.sin(A) * 0.09
    front_ness = np.cos(A)                                  # 1 at the front, -1 at the back
    z_hl = ez + ms["hairline"] + ms["recede"] * (np.abs(A) / 0.6) ** 2
    z_back = Z0 + 0.04
    thr = np.where(front_ness > 0.55, z_hl, np.where(front_ness > 0.1, lerp(z_hl, ez + 0.005, (0.55 - front_ness) / 0.45), z_back))
    hm = (Zt > thr).astype(np.float32)
    bz = beard_top_rule(ms, ez, mz, A)
    bmask = ((Zt < bz) & (np.abs(A) < 1.45)).astype(np.float32)
    lips_zone = (np.abs(A * 0.1) < mw + 0.004) & (np.abs(Zt - mz) < 0.013)
    bmask[lips_zone] = 0
    hm = np.clip(hm + bmask, 0, 1)
    hm = np.array(Image.fromarray((hm * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255.0
    hc_ = np.array(srgb(hair_col))
    arr = arr * (1 - hm[..., None]) + hc_[None, None, :] * hm[..., None]
    out = Image.fromarray(to_srgb8(arr))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)
    print("PAINTED", path)

def beard_top_rule(ms, ez, mz, A):
    """z of the beard's upper edge as a function of azimuth (numpy or float)"""
    import numpy as np
    a = np.abs(A)
    # moustache over the upper lip in the middle, cheek line rising toward the ears
    top = np.where(a < 0.22, mz + 0.020, np.where(a < 0.5, lerp(mz + 0.020, ez - 0.032, (a - 0.22) / 0.28),
                                                   lerp(ez - 0.032, ez - 0.012, np.clip((a - 0.5) / 0.6, 0, 1))))
    return top

# ---------------------------------------------------------------------------
# woven / painted pattern bands (PIL, supersampled): the tragic poikilon after the
# Pronomos Vase -- horizontal bands of meander, running spiral, dots, palmettes,
# triangles and crenellation in madder, woad and dark on the ground colour [R]
# ---------------------------------------------------------------------------
PPM, PSS = 1600, 3            # pixels per metre, supersampling

def _pat_canvas(width_m, height_m, ground):
    from PIL import Image, ImageDraw
    W, H = int(round(width_m * PPM * PSS)), int(round(height_m * PPM * PSS))
    im = Image.new("RGB", (W, H), ground)
    return im, ImageDraw.Draw(im), W, H

def _y(H, s):
    return H - s * PPM * PSS

def _motif(d, W, H, kind, s0, s1, fg, bg=None, units=None, lw=0.11):
    """paint one band between heights s0 < s1 (m) across the full repeat width W"""
    top, bot = _y(H, s1), _y(H, s0)
    h = bot - top
    if bg is not None:
        d.rectangle([0, top, W, bot], fill=bg)
    if kind == "solid":
        d.rectangle([0, top, W, bot], fill=fg)
        return
    n = units or max(1, int(round(W / h)))
    uw = W / n
    lwp = max(2, int(h * lw))

    def P(i, x, y):
        return (i * uw + x * uw, top + y * h)
    if kind == "meander":
        m = 0.16
        for i in range(-1, n + 1):
            pts = [P(i, 0.0, 1 - m), P(i, 1.0, 1 - m)]
            d.line(pts, fill=fg, width=lwp)
            key = [(0.72, 1 - m), (0.72, m), (0.14, m), (0.14, 0.62), (0.50, 0.62), (0.50, 0.40), (0.33, 0.40)]
            d.line([P(i, x, y) for x, y in key], fill=fg, width=lwp, joint="curve")
        d.line([(0, top + lwp * 0.5), (W, top + lwp * 0.5)], fill=fg, width=max(2, lwp // 2))
    elif kind == "wave":
        for i in range(-1, n + 1):
            cx, cy, R0 = 0.60, 0.46, 0.30
            pts = []
            for k in range(12):                       # lead-in rising from the base line
                t = k / 11
                a = (0.0, 0.94)
                c = (cx - R0, 0.94)
                b = (cx - R0, cy)
                x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0]
                y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]
                pts.append(P(i, x, y))
            for k in range(1, 40):                    # the curl
                t = k / 39
                th = math.pi + t * 2.15 * math.pi
                R = R0 * (1 - 0.78 * t)
                pts.append(P(i, cx + R * math.cos(th), cy + R * math.sin(th)))
            d.line(pts, fill=fg, width=lwp, joint="curve")
        d.line([(0, bot - lwp * 0.5), (W, bot - lwp * 0.5)], fill=fg, width=lwp)
    elif kind == "dots":
        for i in range(-1, n + 1):
            x, y = P(i, 0.5, 0.5)
            r = h * 0.32
            d.ellipse([x - r, y - r, x + r, y + r], fill=fg)
    elif kind == "triangles":
        for i in range(-1, n + 1):
            d.polygon([P(i, 0.06, 1.0), P(i, 0.5, 0.05), P(i, 0.94, 1.0)], fill=fg)
    elif kind == "crenel":
        for i in range(-1, n + 1):
            d.rectangle([*P(i, 0.0, 0.5), *P(i, 0.5, 1.0)], fill=fg)
            d.rectangle([*P(i, 0.5, 0.0), *P(i, 1.0, 0.5)], fill=fg)
    elif kind == "palmette":
        fg2 = bg if isinstance(fg, tuple) and False else fg
        for i in range(-1, n + 1):
            bx, by = P(i, 0.5, 0.92)
            for k in range(7):                        # fan of rounded petals
                ang = math.radians(-63 + 21 * k)
                L = h * (0.80 - 0.07 * abs(k - 3))
                wdt = h * 0.085
                ca, sa = math.cos(ang), math.sin(ang)
                poly = []
                for q in range(17):
                    u = q / 16
                    r = wdt * math.sin(math.pi * u) ** 0.7 * (0.55 + 0.45 * u)
                    poly.append((bx + sa * (0.12 + 0.88 * u) * L + ca * r, by - ca * (0.12 + 0.88 * u) * L + sa * r))
                for q in range(16, -1, -1):
                    u = q / 16
                    r = wdt * math.sin(math.pi * u) ** 0.7 * (0.55 + 0.45 * u)
                    poly.append((bx + sa * (0.12 + 0.88 * u) * L - ca * r, by - ca * (0.12 + 0.88 * u) * L - sa * r))
                d.polygon(poly, fill=fg2)
            r = h * 0.09
            d.ellipse([bx - r, by - r, bx + r, by + r], fill=fg2)
            # lotus bud between palmettes
            qx, qy = P(i, 0.0, 0.95)
            d.polygon([(qx - h * 0.08, qy), (qx, qy - h * 0.45), (qx + h * 0.08, qy)], fill=fg2)

def _save_pat(im, path, fade=0.0, seed=0):
    from PIL import Image, ImageFilter
    import numpy as np
    W, H = im.size
    im = im.resize((W // PSS, H // PSS), Image.LANCZOS)
    if fade:
        a = np.asarray(im).astype(np.float32) / 255.0
        rng = np.random.default_rng(seed)
        # periodic (tileable) low-frequency noise: white noise low-passed in Fourier space
        wn = rng.standard_normal(a.shape[:2])
        fy = np.fft.fftfreq(a.shape[0])[:, None]
        fx = np.fft.rfftfreq(a.shape[1])[None, :]
        n = np.fft.irfft2(np.fft.rfft2(wn) * np.exp(-(fx ** 2 + fy ** 2) * (2 * math.pi * 16) ** 2 / 2), s=a.shape[:2])
        n = (n - n.mean()) / (n.std() + 1e-6)
        grey = a.mean(axis=2, keepdims=True)
        a = a * (1 - fade) + (grey * 0.35 + a * 0.65) * fade          # sun-faded dye
        a = a * (1.0 + 0.02 * np.clip(n[..., None], -2.5, 2.5))      # uneven wear
        im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    im.save(path)
    return path

def paint_patterns(texdir):
    os.makedirs(texdir, exist_ok=True)
    C = {k: v for k, v in DYE.items()}
    out = {}
    # --- standing actor: cream poikilon, banded all over (after the Pronomos king) ---
    im, d, W, H = _pat_canvas(PAT_REP, PAT_H_BODY, C["cream"])
    bands = [("meander", 0.040, 0.125, C["cream"], C["madder"], 2), ("solid", 0.130, 0.137, C["dark"], None, None),
             ("wave", 0.160, 0.205, C["woad"], None, 2), ("dots", 0.232, 0.250, C["madder"], None, 4),
             ("palmette", 0.300, 0.375, C["woad"], None, 2), ("solid", 0.392, 0.399, C["madder"], None, None),
             ("triangles", 0.45, 0.49, C["dark"], None, 4), ("solid", 0.53, 0.536, C["woad"], None, None),
             ("wave", 0.58, 0.625, C["madder"], None, 2), ("dots", 0.668, 0.684, C["woad"], None, 4),
             ("crenel", 0.73, 0.76, C["woad"], None, 3), ("solid", 0.80, 0.806, C["madder"], None, None),
             ("palmette", 0.85, 0.915, C["madder"], None, 2),
             ("wave", 1.12, 1.16, C["woad"], None, 2), ("dots", 1.20, 1.216, C["madder"], None, 4),
             ("crenel", 1.27, 1.295, C["madder"], None, 3),
             ("solid", 1.37, 1.376, C["dark"], None, None), ("solid", 1.385, 1.62, C["madder"], None, None),
             ("meander", 1.385, 1.44, C["cream"], C["madder"], 2)]
    for kind, s0, s1, fg, bg, n in bands:
        _motif(d, W, H, kind, s0, s1, fg, bg, n)
    body = _save_pat(im, os.path.join(texdir, "poikilon_body.png"))
    im, d, W, H = _pat_canvas(PAT_REP, PAT_H_SLEEVE, C["cream"])
    for kind, s0, s1, fg, bg, n in [("wave", 0.03, 0.07, C["woad"], None, 2), ("dots", 0.11, 0.126, C["madder"], None, 4),
                                    ("wave", 0.17, 0.21, C["woad"], None, 2), ("dots", 0.25, 0.266, C["madder"], None, 4),
                                    ("wave", 0.31, 0.35, C["woad"], None, 2), ("dots", 0.39, 0.406, C["madder"], None, 4),
                                    ("solid", 0.455, 0.462, C["dark"], None, None),
                                    ("solid", 0.47, 0.80, C["madder"], None, None),
                                    ("meander", 0.475, 0.535, C["cream"], C["madder"], 2)]:
        _motif(d, W, H, kind, s0, s1, fg, bg, n)
    sleeve = _save_pat(im, os.path.join(texdir, "poikilon_sleeve.png"))
    out["poikilon"] = (body, sleeve)
    # --- Euripides: "rags from tragedy" (Ach. 412): faded saffron, plainer borders ---
    im, d, W, H = _pat_canvas(PAT_REP, PAT_H_BODY, C["saffron"])
    for kind, s0, s1, fg, bg, n in [("meander", 0.040, 0.13, C["saffron"], C["madder"], 2), ("solid", 0.135, 0.142, C["dark"], None, None),
                                    ("dots", 0.165, 0.18, C["madder"], None, 4), ("solid", 0.48, 0.486, C["madder"], None, None),
                                    ("solid", 0.80, 0.806, C["madder"], None, None),
                                    ("wave", 1.20, 1.24, C["madder_dark"], None, 2),
                                    ("solid", 1.37, 1.377, C["dark"], None, None), ("solid", 1.385, 1.62, C["madder"], None, None),
                                    ("dots", 1.40, 1.415, C["saffron"], None, 4)]:
        _motif(d, W, H, kind, s0, s1, fg, bg, n)
    body = _save_pat(im, os.path.join(texdir, "rags_body.png"), fade=0.35, seed=4)
    im, d, W, H = _pat_canvas(PAT_REP, PAT_H_SLEEVE, C["saffron"])
    for kind, s0, s1, fg, bg, n in [("solid", 0.06, 0.068, C["madder"], None, None), ("solid", 0.455, 0.462, C["dark"], None, None),
                                    ("solid", 0.47, 0.80, C["madder"], None, None), ("dots", 0.49, 0.505, C["saffron"], None, 4)]:
        _motif(d, W, H, kind, s0, s1, fg, bg, n)
    sleeve = _save_pat(im, os.path.join(texdir, "rags_sleeve.png"), fade=0.35, seed=5)
    out["rags"] = (body, sleeve)
    # --- stagehands: plain undyed / dun wool with a self-coloured woven stripe at the hem ---
    for key, ground, stripe in (("tunic_oat", C["oat"], C["dun"]), ("tunic_dun", C["dun"], C["dark"])):
        im, d, W, H = _pat_canvas(PAT_REP, PAT_H_BODY, ground)
        _motif(d, W, H, "solid", 0.53, 0.538, stripe)
        body = _save_pat(im, os.path.join(texdir, key + "_body.png"), fade=0.2, seed=7)
        im, d, W, H = _pat_canvas(PAT_REP, PAT_H_SLEEVE, ground)
        sleeve = _save_pat(im, os.path.join(texdir, key + "_sleeve.png"), fade=0.2, seed=8)
        out[key] = (body, sleeve)
    # --- himation: woad wool, madder and dark border stripes along both long edges ---
    from PIL import Image, ImageDraw
    Wd, Hd = 600, 2400
    him = Image.new("RGB", (Wd, Hd), C["woad"])
    dd = ImageDraw.Draw(him)
    for u0, u1, col in ((0.0, 0.012, C["dark"]), (0.02, 0.055, C["madder"]), (0.062, 0.068, C["dark"])):
        for a, b in ((u0, u1), (1 - u1, 1 - u0)):
            dd.rectangle([a * Wd, 0, b * Wd, Hd], fill=col)
    _save_pat(him.resize((Wd * PSS, Hd * PSS)), os.path.join(texdir, "himation.png"), fade=0.08, seed=9)
    # --- blanket: madder wool with a dark and woad border on all four sides ---
    Wb = 1200
    bl = Image.new("RGB", (Wb, Wb), C["madder"])
    db = ImageDraw.Draw(bl)
    for u0, u1, col in ((0.0, 0.015, C["madder_dark"]), (0.03, 0.05, C["dark"]), (0.058, 0.066, C["woad"]), (0.074, 0.08, C["dark"])):
        db.rectangle([u0 * Wb, 0, u1 * Wb, Wb], fill=col)
        db.rectangle([(1 - u1) * Wb, 0, (1 - u0) * Wb, Wb], fill=col)
        db.rectangle([0, u0 * Wb, Wb, u1 * Wb], fill=col)
        db.rectangle([0, (1 - u1) * Wb, Wb, (1 - u0) * Wb], fill=col)
    _save_pat(bl.resize((Wb * PSS, Wb * PSS)), os.path.join(texdir, "blanket.png"), fade=0.1, seed=10)
    return out


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
        return Matrix((left, -fr, up)).transposed()

    # ==========================================================================
    # Poser (from makehuman_test.py): poses the MakeHuman default rig by world-space
    # aims, analytic two-bone IK and finger curls
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
    # MPFB access (build time only)
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

    # the figures: all male; MakeHuman macro sliders (0..1). height 0.50 = 1.72 m, +0.1 = +0.13 m
    FIGURES = {
        "Standing actor": dict(macro=dict(gender=1.0, age=0.60, muscle=0.58, weight=0.52, height=0.53, proportions=0.65),
                               race=dict(caucasian=0.8, african=0.12, asian=0.08), skin="middleage_caucasian_male",
                               tan=(0.40, 0.25, 0.15)),
        "Reclining actor": dict(macro=dict(gender=1.0, age=0.70, muscle=0.50, weight=0.56, height=0.50, proportions=0.6),
                                race=dict(caucasian=0.82, african=0.1, asian=0.08), skin="middleage_caucasian_male",
                                tan=(0.42, 0.27, 0.16)),
        "Stagehand A": dict(macro=dict(gender=1.0, age=0.47, muscle=0.70, weight=0.45, height=0.47, proportions=0.5),
                            race=dict(caucasian=0.7, african=0.25, asian=0.05), skin="young_caucasian_male",
                            tan=(0.34, 0.20, 0.115), hair="short02", eyes=True, brows="eyebrow001",
                            hair_col=(0.03, 0.022, 0.016)),
        "Stagehand B": dict(macro=dict(gender=1.0, age=0.56, muscle=0.62, weight=0.55, height=0.48, proportions=0.45),
                            race=dict(caucasian=0.8, african=0.15, asian=0.05), skin="middleage_caucasian_male",
                            tan=(0.33, 0.195, 0.11), hair="short04", eyes=True, brows="eyebrow006",
                            hair_col=(0.04, 0.03, 0.022)),
    }
    ACTORS = ("Standing actor", "Reclining actor")

    # ==========================================================================
    # our own shaders on the CC0 MakeHuman textures (MPFB's GPL node groups are not used)
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
            if "eye" in src and "brow" not in src and "lash" not in src:
                set_only_material(a, mat_textured(name + " eyes", os.path.join(ud, "eyes/materials/brown_eye.png"), rough=0.12, spec=0.6))
            else:
                folder = next((d for d in ("hair", "eyebrows", "eyelashes") if os.path.exists(os.path.join(ud, d, src, src + ".mhmat"))), None)
                if folder:
                    tex = mhmat_texture(os.path.join(ud, folder, src, src + ".mhmat"))
                    col = spec.get("hair_col", (0.05, 0.04, 0.03))
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
        own_materials(name, spec, body, assets, ud)
        body.name = name + " body"
        rig.name = name + " rig"
        rig.data.name = name + " rig"
        for a in assets:
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
        return rig, body, assets

    # ==========================================================================
    # context from the scene copy: platform and couch, and the mannequins as reference
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
        elif kind == "address":        # open hand, fingers gently graded (index straightest)
            P.fingers(side, {2: (5, 9, 5), 3: (9, 13, 7), 4: (15, 19, 11), 5: (21, 25, 14)},
                      spread={2: -4, 3: 0, 4: 4, 5: 9}, thumb=((4, 0, -10), 8, 8))
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
        hfront = V((0.80, 0.58, -0.10))                  # toward the standing actor
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
                   (-0.13, 0.30, 1.27), V((0.1, -0.4, -1)))
        P.hand("R", (0.78, 0.45, 0.30), (0.10, 0.32, 0.94))     # open hand, palm up, offered
        hand_shape(P, "R", "address")
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
    # garments: ONE closed shell per garment (lofted torso + flared skirt + sleeve tubes,
    # union by voxel remesh), cut open at neck, cuffs and hem; cut for the T-pose rest,
    # belted (waist ring pinned, gathered), pinned along the shoulders and cuffs, then
    # cloth-simulated from the T-pose into the pose with the body as a collider.
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

    GARMENTS = {
        # long-sleeved, ankle-length patterned robes for the actors (Pronomos Vase, c. 400 BC);
        # knee-length short-sleeved tunics for the stagehands [R]
        "Standing actor": dict(kind="robe", z_hem=0.045, hem_r=(0.31, 0.26), m_torso=(0.034, 0.036),
                               m_sleeve=(0.021, 0.015), sleeve="long", pattern="poikilon", vox=0.0135,
                               cloth=dict(mass=0.3, bend=0.9, tension=15.0, shear=5.0)),
        "Reclining actor": dict(kind="robe", z_hem=0.05, hem_r=(0.29, 0.25), m_torso=(0.034, 0.036),
                                m_sleeve=(0.021, 0.015), sleeve="long", pattern="rags", vox=0.0135,
                                cloth=dict(mass=0.3, bend=0.9, tension=15.0, shear=5.0)),
        "Stagehand A": dict(kind="tunic", z_hem=0.46, hem_r=(0.28, 0.23), m_torso=(0.03, 0.032),
                            m_sleeve=(0.03, 0.03), sleeve="short", pattern="tunic_oat", vox=0.014,
                            cloth=dict(mass=0.3, bend=1.2, tension=16.0, shear=5.0)),
        "Stagehand B": dict(kind="tunic", z_hem=0.47, hem_r=(0.26, 0.21), m_torso=(0.03, 0.032),
                            m_sleeve=(0.03, 0.03), sleeve="short", pattern="tunic_dun", vox=0.014,
                            cloth=dict(mass=0.3, bend=1.2, tension=16.0, shear=5.0)),
    }
    T_SETTLE, T_MOVE, T_END = 10, 50, 92          # cloth timeline (frames)

    def loft(loops, caps=True):
        verts, faces = [], []
        n = len(loops[0])
        for L in loops:
            verts += [tuple(p) for p in L]
        for r in range(len(loops) - 1):
            for c in range(n):
                a, b = r * n + c, r * n + (c + 1) % n
                faces.append((a, b, b + n, a + n))
        if caps:
            faces.append(tuple(reversed(range(n))))
            faces.append(tuple(range((len(loops) - 1) * n, len(loops) * n)))
        return verts, faces

    def garment_geometry(rig, body, spec):
        """measure the rest (T-pose) body and return the shell's lofts and the key levels"""
        pts = body_rest_points(body)
        rb = rig.data.bones
        sh = rb["upperarm01.L"].head_local
        wr = rb["wrist.L"].head_local
        nk = rb["neck01"].head_local
        x_sh = sh.x
        z_sh_top = max(p.z for p in pts if abs(p.x - x_sh) < 0.02 and p.z > sh.z - 0.1)
        z_armpit = min(p.z for p in pts if 0.15 < abs(p.x) < 0.19 and p.z > sh.z - 0.2) - 0.005
        z_waist = rb["spine04"].head_local.z + 0.01

        def tslice(z, xlim):
            sel = [p for p in pts if abs(p.z - z) < 0.011 and abs(p.x) < xlim]
            xs = [p.x for p in sel]
            ys = [p.y for p in sel]
            return min(xs), max(xs), min(ys), max(ys)

        # hips: widest torso slice between 0.78 and 1.05 m
        best = (0, 0.9)
        for i in range(28):
            z = 0.78 + i * 0.01
            x0, x1, _, _ = tslice(z, 0.26)
            if x1 - x0 > best[0]:
                best = (x1 - x0, z)
        z_hip = best[1]
        mx, my = spec["m_torso"]
        N = 56
        loops, radii = [], []

        def ell(cx, cy, rx, ry, z, ex=2.4):
            L = []
            for k in range(N):
                a = 2 * math.pi * k / N
                c, s = math.cos(a), math.sin(a)
                # superellipse: a little boxier than an ellipse, like a body in cloth
                cx_ = math.copysign(abs(c) ** (2 / ex), c)
                sy_ = math.copysign(abs(s) ** (2 / ex), s)
                L.append(V((cx + rx * cx_, cy + ry * sy_, z)))
            return L
        x0, x1, y0, y1 = tslice(z_hip, 0.26)
        hip = (0.0, (y0 + y1) / 2, (x1 - x0) / 2 + mx, (y1 - y0) / 2 + my)
        z_hem = spec["z_hem"]
        hx, hy = spec["hem_r"]
        # skirt: from below the hem up to the hips, flaring toward the hem
        zb = z_hem - 0.04
        nsk = max(4, int((z_hip - zb) / 0.05))
        for i in range(nsk):
            z = zb + (z_hip - zb) * i / nsk
            t = (z - zb) / (z_hip - zb)
            t = t ** 0.85
            rx, ry = lerp(hx, hip[2], t), lerp(hy, hip[3], t)
            loops.append(ell(0.0, hip[1] + 0.012 * (1 - t), rx, ry, z))
            radii.append((z, rx, ry))
        # torso: body slices + margin, arms excluded above the armpit
        z = z_hip
        while z < z_sh_top - 0.03:
            xlim = 0.26 if z < z_armpit - 0.02 else 0.175
            x0, x1, y0, y1 = tslice(z, xlim)
            rx, ry = max((x1 - x0) / 2 + mx, 0.12), (y1 - y0) / 2 + my
            if z > z_armpit - 0.02:
                rx = max(rx, x_sh + 0.01)
            loops.append(ell(0.0, (y0 + y1) / 2, rx, ry, z))
            radii.append((z, rx, ry))
            z += 0.04
        # shoulders and the slope to the neck
        x0, x1, y0, y1 = tslice(z_sh_top - 0.03, 0.17)
        cy_sh = (y0 + y1) / 2
        ry_sh = (y1 - y0) / 2 + my
        z_top = max(z_sh_top, nk.z) + 0.035
        for (zz, rx, ry, cy) in ((z_sh_top - 0.01, x_sh + 0.035, ry_sh, cy_sh),
                                  (z_sh_top + 0.012, x_sh - 0.01, ry_sh * 0.92, cy_sh),
                                  (z_sh_top + 0.026, 0.13, ry_sh * 0.8, lerp(cy_sh, nk.y, 0.5)),
                                  (z_top, 0.085, 0.075, nk.y)):
            loops.append(ell(0.0, cy, rx, ry, zz, ex=2.0))
            radii.append((zz, rx, ry))
        shells = [loft(loops)]
        # sleeves: circle loops round the T-pose arm, from inside the torso to the cuff
        if spec["sleeve"] == "long":
            x_cuff = wr.x + 0.012
        else:
            x_cuff = x_sh + 0.115
        ms0, ms1 = spec["m_sleeve"]
        arm = []
        x = x_sh + 0.04
        while x < wr.x + 0.001:
            sel = [p for p in pts if abs(p.x - x) < 0.01 and p.z > sh.z - 0.14 and p.z < sh.z + 0.12]
            ys = [p.y for p in sel]
            zs = [p.z for p in sel]
            arm.append((x, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2, max(max(ys) - min(ys), max(zs) - min(zs)) / 2))
            x += 0.02

        def arm_at(x):
            if x <= arm[0][0]:
                return arm[0][1:]
            for a, b in zip(arm, arm[1:]):
                if a[0] <= x <= b[0]:
                    t = (x - a[0]) / (b[0] - a[0])
                    return tuple(lerp(a[k], b[k], t) for k in (1, 2, 3))
            return arm[-1][1:]
        sleeve_r = {}
        xs = [0.10]
        while xs[-1] < x_cuff:
            xs.append(min(x_cuff, xs[-1] + 0.025))
        NS = 28
        for sx in (1.0, -1.0):
            sl = []
            for x in xs:
                cy, cz, r = arm_at(max(x, x_sh + 0.04))
                t = smoothstep(x_sh, wr.x, x)
                rr = r + lerp(ms0, ms1, t)
                if x < x_sh + 0.04:                      # inside the torso: keep the armhole full
                    rr = max(rr, 0.075)
                sleeve_r[round(x, 4)] = (cy, cz, rr)
                L = [V((sx * x, cy + rr * math.sin(2 * math.pi * k / NS), cz + rr * math.cos(2 * math.pi * k / NS))) for k in range(NS)]
                sl.append(L)
            shells.append(loft(sl))
        return dict(shells=shells, z_hem=z_hem, z_top=z_top, z_sh_top=z_sh_top, z_armpit=z_armpit, z_waist=z_waist,
                    x_sh=x_sh, x_cuff=x_cuff, wr_x=wr.x, nk=nk.copy(), radii=radii, arm=arm, sleeve_r=sleeve_r,
                    cy_hip=hip[1], hip=hip)

    def build_garment(name, rig, body, spec, mat_name):
        G = garment_geometry(rig, body, spec)
        verts, faces = [], []
        for vs, fs in G["shells"]:
            off = len(verts)
            verts += vs
            faces += [tuple(i + off for i in f) for f in fs]
        me = bpy.data.meshes.new(name + " shell")
        me.from_pydata(verts, [], faces)
        tmp = bpy.data.objects.new(name + " shell", me)
        bpy.context.scene.collection.objects.link(tmp)
        rm = tmp.modifiers.new("Remesh", "REMESH")
        rm.mode = "VOXEL"
        rm.voxel_size = spec["vox"]
        rm.adaptivity = 0.0
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg), depsgraph=dg)
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        bm = bmesh.new()
        bm.from_mesh(me2)
        nk = G["nk"]
        z_top = G["z_top"]

        def neck_cut(c):
            dz = 0.05 + 0.025 * smoothstep(0.0, 0.08, nk.y - c.y)        # neckline dips in front
            return c.z > z_top - dz and math.hypot(c.x, (c.y - nk.y) * 1.1) < 0.125
        dele = []
        for f in bm.faces:
            c = f.calc_center_median()
            if c.z < G["z_hem"] or abs(c.x) > G["x_cuff"] - 0.004 or neck_cut(c):
                dele.append(f)
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        # keep the largest piece; smooth the voxel steps
        bm.faces.ensure_lookup_table()
        seen, best = set(), []
        for f in bm.faces:
            if f.index in seen:
                continue
            comp, stack = [], [f]
            seen.add(f.index)
            while stack:
                g = stack.pop()
                comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in seen:
                            seen.add(h.index)
                            stack.append(h)
            if len(comp) > len(best):
                best = comp
        keep = set(f.index for f in best)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        for _ in range(3):
            bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                                  use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.to_mesh(me2)
        bm.free()
        me2.name = name
        ob = bpy.data.objects.new(name, me2)
        bpy.context.scene.collection.objects.link(ob)
        for p in me2.polygons:
            p.use_smooth = True
        # rest shape (no waist) and the belted shape (waist ring pulled onto the body)
        pts = body_rest_points(body)
        zw = G["z_waist"]
        sel = [p for p in pts if abs(p.z - zw) < 0.015 and abs(p.x) < 0.2]
        wx0, wx1 = min(p.x for p in sel), max(p.x for p in sel)
        wy0, wy1 = min(p.y for p in sel), max(p.y for p in sel)
        wa, wb, wyc = (wx1 - wx0) / 2 + 0.013, (wy1 - wy0) / 2 + 0.013, (wy0 + wy1) / 2
        rest = [v.co.copy() for v in me2.vertices]
        pin = [0.0] * len(rest)
        belt_ring = []
        for i, p in enumerate(rest):
            is_sleeve = abs(p.x) > G["x_sh"] + 0.03 and p.z > G["z_armpit"] - 0.06
            if not is_sleeve and abs(p.z - zw) < 0.13:
                th = math.atan2(p.y - wyc, p.x)
                e = V((wa * math.cos(th), wyc + wb * math.sin(th), p.z))
                w = 1.0 - smoothstep(0.012, 0.13, abs(p.z - zw))
                me2.vertices[i].co = p.lerp(e, w)
                if abs(p.z - zw) < 0.013:
                    pin[i] = 1.0
                    belt_ring.append(i)
            if is_sleeve:
                pin[i] = max(pin[i], 0.12 + 0.88 * smoothstep(G["x_cuff"] - 0.05, G["x_cuff"] - 0.02, abs(p.x)))
            elif p.z > G["z_sh_top"] - 0.012 and abs(p.x) < G["x_sh"] + 0.05:
                pin[i] = 1.0                                    # shoulder seam / yoke
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="rest")
        for i, p in enumerate(rest):
            sk.data[i].co = p
        vg = ob.vertex_groups.new(name="pin")
        for i, w in enumerate(pin):
            if w > 0:
                vg.add([i], w, "REPLACE")
        garment_uvs(ob, rest, G)
        ob.parent = rig
        ob.matrix_parent_inverse = Matrix.Identity(4)
        m = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
        me2.materials.append(m)
        sm = bpy.data.materials.get(mat_name + " sleeves") or bpy.data.materials.new(mat_name + " sleeves")
        me2.materials.append(sm)
        copy_weights(ob, body)
        am = ob.modifiers.new("Armature", "ARMATURE")
        am.object = rig
        ob["belt_ring"] = belt_ring
        print("GARMENT", name, "verts", len(me2.vertices), "z_waist %.3f z_hem %.3f x_cuff %.3f" % (zw, G["z_hem"], G["x_cuff"]))
        return ob, G

    def garment_uvs(ob, rest, G):
        """two UV maps from the rest (T-pose) coordinates: 'pattern' (repeat units across, height
        up: the band layout is painted in an image that tiles across) and 'weave' (metres)"""
        me = ob.data
        radii = G["radii"]

        def r_at(z):
            if z <= radii[0][0]:
                z = radii[0][0]
            for a, b in zip(radii, radii[1:]):
                if a[0] <= z <= b[0]:
                    t = (z - a[0]) / max(1e-6, b[0] - a[0])
                    rx, ry = lerp(a[1], b[1], t), lerp(a[2], b[2], t)
                    return math.sqrt((rx * rx + ry * ry) / 2)
            return math.sqrt((radii[-1][1] ** 2 + radii[-1][2] ** 2) / 2)
        sk = sorted(G["sleeve_r"].items())

        def sleeve_at(x):
            for (xa, a), (xb, b) in zip(sk, sk[1:]):
                if xa <= x <= xb:
                    t = (x - xa) / max(1e-6, xb - xa)
                    return tuple(lerp(a[k], b[k], t) for k in range(3))
            return sk[-1][1] if x > sk[-1][0] else sk[0][1]
        yc = G["cy_hip"]
        vinfo = []
        for p in rest:
            sleeve = abs(p.x) > G["x_sh"] + 0.02 and p.z > G["z_armpit"] - 0.05
            if sleeve:
                cy, cz, rr = sleeve_at(abs(p.x))
                ang = math.atan2(p.y - cy, p.z - cz)            # 0 on top of the arm, +-pi underneath (seam)
                vinfo.append((1, ang, rr, abs(p.x) - G["x_sh"]))
            else:
                ang = math.atan2(p.x, -(p.y - yc))              # 0 at the front, +-pi at the back (seam)
                vinfo.append((0, ang, r_at(p.z), p.z))
        uvp = me.uv_layers.new(name="pattern")
        uvw = me.uv_layers.new(name="weave")
        sleeve_attr = me.attributes.new("sleeve", "INT", "FACE")
        for poly in me.polygons:
            cls = [vinfo[v][0] for v in poly.vertices]
            is_sl = 1 if sum(cls) * 2 > len(cls) else 0
            sleeve_attr.data[poly.index].value = is_sl
            poly.material_index = is_sl
            angs = []
            for li, v in zip(poly.loop_indices, poly.vertices):
                c, a, r, s = vinfo[v]
                angs.append(a)
            wrap = max(angs) - min(angs) > math.pi
            for li, v in zip(poly.loop_indices, poly.vertices):
                c, a, r, s = vinfo[v]
                if c != is_sl:          # boundary face between body and sleeve: use this face's class
                    p = rest[v]
                    if is_sl:
                        cy, cz, rr = sleeve_at(abs(p.x))
                        a, r, s = math.atan2(p.y - cy, p.z - cz), rr, abs(p.x) - G["x_sh"]
                    else:
                        a, r, s = math.atan2(p.x, -(p.y - yc)), r_at(p.z), p.z
                if wrap and a < 0:
                    a += 2 * math.pi
                t = a * r
                Hh = PAT_H_SLEEVE if is_sl else PAT_H_BODY
                uvp.data[li].uv = (t / PAT_REP, s / Hh)
                uvw.data[li].uv = (t, s)
        me.uv_layers.active = uvp

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
            spec = GARMENTS[name]
            rig, body = fig["rig"], fig["body"]
            if name in ACTORS:
                fig["final"]["jaw"] = Matrix.Rotation(math.radians(4.5), 4, "X")     # lips slightly parted
            rig.data.pose_position = "REST"
            bpy.context.view_layer.update()
            store_rest_coords(body)
            g, G = build_garment(f"{name} {spec['kind']}", rig, body, spec, "V3 " + spec["pattern"])
            fig["garment"], fig["G"] = g, G
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
            add_cloth(g, cc, T_END, quality=7, **spec["cloth"])
            g.modifiers["Cloth"].collision_settings.collision_quality = 4
            cloths.append(g)
        t0 = time.time()
        for f in range(1, T_END + 1):
            sc.frame_set(f)
            if f % 10 == 0:
                print("  cloth frame", f, "%.1fs" % (time.time() - t0))
        print("CLOTH SIM %.1fs" % (time.time() - t0))
        return cloths

    def relax_cloth(garment, body, iters=2, factor=0.45, gap=0.004):
        """after freezing: smooth the solver's high-frequency crinkle (keeps the folds), then
        push any vertex that ended up in or too near the body back out along the body normal"""
        bvh = bvh_of([body])
        me = garment.data
        bm = bmesh.new()
        bm.from_mesh(me)
        for _ in range(iters):
            bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=factor,
                                  use_axis_x=True, use_axis_y=True, use_axis_z=True)
        mw = garment.matrix_world
        mi = mw.inverted()
        moved = 0
        for v in bm.verts:
            p = mw @ v.co
            loc, n, i, d = bvh.find_nearest(p)
            if loc is None or d > 0.03:
                continue
            s = (p - loc).dot(n)
            if s < gap:
                v.co = mi @ (p + n * (gap - s))
                moved += 1
        bm.to_mesh(me)
        bm.free()
        print("RELAX", garment.name, "pushed out", moved)

    def smooth_boundaries(ob, iters=14, factor=0.5):
        """the voxel-cut neckline, cuffs and hem as clean curves (smoothing along each open edge)"""
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bverts = [v for v in bm.verts if v.is_boundary]
        nbr = {}
        for v in bverts:
            ns = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(ns) == 2:
                nbr[v] = ns
        for _ in range(iters):
            new = {v: v.co + ((ns[0].co + ns[1].co) * 0.5 - v.co) * factor for v, ns in nbr.items()}
            for v, c in new.items():
                v.co = c
        bm.to_mesh(ob.data)
        bm.free()

    def merge_robes(work):
        """robes.blend from the per-figure files (robes_<names>.blend): for each figure, its
        'MH <name>' collection comes from the newest file that contains it"""
        import glob
        parts = [p for p in glob.glob(os.path.join(work, "robes_*.blend"))]
        if not parts:
            return
        newest = {}
        for p in sorted(parts, key=os.path.getmtime):
            names = os.path.basename(p)[len("robes_"):-len(".blend")].split("+")
            for n in names:
                newest[n.replace("_", " ")] = p
        files = sorted(set(newest.values()), key=os.path.getmtime)
        bpy.ops.wm.open_mainfile(filepath=files[-1])
        have = set(c.name for c in bpy.data.collections)
        for name, p in newest.items():
            if p == files[-1]:
                continue
            old = bpy.data.collections.get("MH " + name)
            if old is not None:
                for o in list(old.objects):
                    bpy.data.objects.remove(o)
                bpy.data.collections.remove(old)
            gname = "%s %s" % (name, GARMENTS[name]["kind"])
            with bpy.data.libraries.load(p, link=False) as (src, dst):
                dst.collections = ["MH " + name]
                dst.objects = [gname] if gname in src.objects else []
            for c in dst.collections:
                if c is not None:
                    bpy.context.scene.collection.children.link(c)
            for o in dst.objects:
                if o is not None and not o.users_collection:
                    bpy.data.collections["MH " + name].objects.link(o)
        for name in newest:
            g = bpy.data.objects.get("%s %s" % (name, GARMENTS[name]["kind"]))
            c = bpy.data.collections.get("MH " + name)
            if g is not None and c is not None and g.name not in c.objects:
                link_to(g, c)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "robes.blend"))
        print("MERGED", {n: os.path.basename(p) for n, p in newest.items()})

    def build_belt(name, garment, ring, width=0.032, thick=0.005, mat="V3 belt"):
        """a girdle round the frozen robe's pinned waist ring"""
        mw = garment.matrix_world
        pts = [mw @ garment.data.vertices[i].co for i in ring]
        c = sum(pts, Vector()) / len(pts)
        pts.sort(key=lambda p: math.atan2(p.y - c.y, p.x - c.x))
        # thin the ring to an even loop of ~64 points
        n = 64
        loop = [pts[int(i * len(pts) / n)] for i in range(n)]
        zc = sum(p.z for p in loop) / n
        verts, faces = [], []
        for p in loop:
            d = V((p.x - c.x, p.y - c.y, 0)).normalized()
            q = V((p.x, p.y, zc)) + d * 0.004
            for dz, dd in ((-width / 2, 0), (width / 2, 0), (width / 2, thick), (-width / 2, thick)):
                verts.append(tuple(q + V((0, 0, dz)) + d * dd))
        for i in range(n):
            j = (i + 1) % n
            for k in range(4):
                a, b = i * 4 + k, i * 4 + (k + 1) % 4
                faces.append((a, b, j * 4 + (k + 1) % 4, j * 4 + k))
        me = bpy.data.meshes.new(name + " belt")
        me.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new(name + " belt", me)
        bpy.context.scene.collection.objects.link(ob)
        me.materials.append(bpy.data.materials.get(mat) or bpy.data.materials.new(mat))
        for p in me.polygons:
            p.use_smooth = True
        return ob

    def build_boots(name, body):
        """soft, low-soled calf-high leather boots (cf. the Pronomos actors' laced boots)"""
        me = body.data
        rest = [V(d.vector) for d in me.attributes["rest_co"].data]
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(body.matrix_world)
        dele = [f for f in bm.faces if not all(rest[v.index].z < 0.30 for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * 0.0035
        mb = bpy.data.meshes.new(name + " boots")
        bm.to_mesh(mb)
        bm.free()
        ob = bpy.data.objects.new(name + " boots", mb)
        mb.materials.append(bpy.data.materials.get("V3 boots") or bpy.data.materials.new("V3 boots"))
        for poly in mb.polygons:
            poly.use_smooth = True
        sd = ob.modifiers.new("Solidify", "SOLIDIFY")
        sd.thickness = 0.002
        return ob

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

    # ==========================================================================
    # masks: full-head, moulded on the actor's posed head (MASKS_AND_COSTUME.md §1):
    # naturalistic, idealised, lips slightly parted, painted eyes, tanned male paint,
    # hair and beard attached (hair curves rooted on the mask)
    # ==========================================================================
    MASKS = {
        # hair_len: (front, back) m; mel: hair melanin (0 white .. 1 black), rnd: per-strand melanin
        # variation (grizzled), hairline: front hairline above the eyes (m), recede: temple recession
        # grey: share of white strands (salt-and-pepper); mel/red: the dark strands' melanin
        "Standing actor": dict(scale=1.085, paint=(160, 112, 78), brow=(46, 32, 24), lips=(134, 66, 54),
                               hair_len=(0.04, 0.065), beard_len=(0.032, 0.055), mel=0.9, red=0.1, rnd=0.05, grey=0.0,
                               hairline=0.058, recede=0.008, curl=0.0042, beard_curl=0.0048, n_hair=13000, n_beard=7000,
                               age="prime", seed=3),
        "Reclining actor": dict(scale=1.085, paint=(156, 110, 78), brow=(96, 88, 80), lips=(128, 68, 56),
                                hair_len=(0.045, 0.08), beard_len=(0.05, 0.085), mel=0.85, red=0.1, rnd=0.1, grey=0.55,
                                hairline=0.07, recede=0.025, curl=0.0042, beard_curl=0.005, n_hair=12000, n_beard=8000,
                                age="old", seed=11),
    }

    def head_frame(fig):
        """rest landmarks and the rest->world transform of the posed head"""
        rig, P = fig["rig"], fig["poser"]
        rb = rig.data.bones
        eL, eR = rb["eye.L"].head_local.copy(), rb["eye.R"].head_local.copy()
        ez, ey, ex = 0.5 * (eL.z + eR.z), 0.5 * (eL.y + eR.y), abs(eL.x)
        Mh = rig.matrix_world @ P.P("head") @ P.rest["head"].inverted()     # rest point -> posed world
        return dict(ez=ez, ey=ey, ex=ex, M=Mh, R=Mh.to_3x3().normalized())

    def build_mask(name, fig, ms, colliders, texdir):
        body, rig = fig["body"], fig["rig"]
        H = head_frame(fig)
        ez, ey, ex, M, R = H["ez"], H["ey"], H["ex"], H["M"], H["R"]
        me = body.data
        rest = [V(d.vector) for d in me.attributes["rest_co"].data]
        # head axis (rest): centre of the head between face and back at eye level
        ring = [p for p in rest if abs(p.z - ez) < 0.01 and abs(p.x) < 0.02]
        y_front = min(p.y for p in ring)
        y_back = max(p.y for p in ring)
        yc = 0.5 * (y_front + y_back)
        mz = ez - 0.068                                      # mouth line (MakeHuman male)
        z_chin_cut, z_nape_cut = ez - 0.132, ez - 0.088

        def zcut(p):
            return lerp(z_chin_cut, z_nape_cut, smoothstep(y_front + 0.05, yc + 0.03, p.y))

        def in_head(p):
            return abs(p.x) < 0.115 and p.z > zcut(p) and p.z > ez - 0.16

        def mouth_gap(p):                                   # inside the parted lips (rest)
            return abs(p.x) < 0.021 * (1 - ((p.z - mz) / 0.02) ** 2) ** 0.5 if abs(p.z - mz) < 0.02 else False
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(body.matrix_world)
        rl = bm.verts.layers.float_vector.get("rest_co")

        def rco(v):
            return V(v[rl])
        dele = [f for f in bm.faces if not all(in_head(rco(v)) for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        # the mouth: remove the inner mouth surfaces behind the parted lips (a small dark parting)
        lipv = [rco(v) for v in bm.verts if abs(rco(v).x) < 0.005 and abs(rco(v).z - mz) < 0.015]
        y_lip = min(p.y for p in lipv) if lipv else y_front

        def inner_mouth(p):
            return abs(p.x) < 0.022 and abs(p.z - mz) < 0.014 and p.y > y_lip + 0.009 + 0.25 * abs(p.x)
        dele = [f for f in bm.faces if all(inner_mouth(rco(v)) for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        # largest piece
        bm.faces.ensure_lookup_table()
        seen, best = set(), []
        for f in bm.faces:
            if f.index in seen:
                continue
            comp, stack = [], [f]
            seen.add(f.index)
            while stack:
                g = stack.pop()
                comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in seen:
                            seen.add(h.index)
                            stack.append(h)
            if len(comp) > len(best):
                best = comp
        keep = set(f.index for f in best)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        # enlarge about the head centre (a mask is a little larger than life), push out, idealise
        hc = M @ V((0.0, yc, ez))
        S = ms["scale"]
        for v in bm.verts:
            v.co = hc + (v.co - hc) * S
        bm.normal_update()
        rb = fig["rig"].data.bones
        ecs = [rb["eye.L"].head_local.copy(), rb["eye.R"].head_local.copy()]
        for v in bm.verts:
            p = rco(v)
            de = min((p - e).length for e in ecs)
            dl = math.hypot(p.x / 1.4, p.z - mz) if p.y < yc - 0.05 else 1.0
            v.co += v.normal * 0.003 * smoothstep(0.016, 0.03, de) * smoothstep(0.018, 0.032, dl)
        # eye sockets: remove the faces inside the eyeball (the painted eye ball shows in the opening)
        dele = [f for f in bm.faces if all(min((rco(v) - e).length for e in ecs) < 0.0112 for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")

        def keep_detail(p):
            near_eye = min((p - e).length for e in ecs) < 0.026
            near_lips = abs(p.x) < 0.032 and abs(p.z - mz) < 0.022 and p.y < yc - 0.05
            return near_eye or near_lips
        # idealise: smooth the skin detail but keep the big forms and the lids and lips
        for it in range(2):
            vs = [v for v in bm.verts if not v.is_boundary and not keep_detail(rco(v))]
            bmesh.ops.smooth_vert(bm, verts=vs, factor=0.35, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        # landmarks from the mesh itself (rest coordinates): the eye openings and the lip parting
        # are boundary loops; the paint follows them exactly
        def loop_pts(pred):
            pts = []
            for e in bm.edges:
                if e.is_boundary:
                    a, b = rco(e.verts[0]), rco(e.verts[1])
                    if pred(a) and pred(b):
                        pts.append((a + b) / 2)
            return pts
        eye_open = []
        for e in ecs:
            pts = loop_pts(lambda q, e=e: (q - e).length < 0.03 and q.y < e.y)
            if len(pts) < 6:
                pts = [V((e.x + 0.013 * math.cos(a), e.y - 0.01, e.z + 0.005 * math.sin(a))) for a in [k * 0.4 for k in range(16)]]
            cx = sum(q.x for q in pts) / len(pts)
            cz = sum(q.z for q in pts) / len(pts)
            pts.sort(key=lambda q: math.atan2(q.z - cz, q.x - cx))
            eye_open.append(dict(cx=cx, cz=cz, pts=[(q.x, q.z) for q in pts],
                                 w=max(q.x for q in pts) - min(q.x for q in pts), h=max(q.z for q in pts) - min(q.z for q in pts)))
        mpts = loop_pts(lambda q: abs(q.x) < 0.035 and abs(q.z - mz) < 0.025 and q.y < yc - 0.04)
        if len(mpts) >= 6:
            mz_m = sum(q.z for q in mpts) / len(mpts)
            mw = max(abs(q.x) for q in mpts)
        else:
            mz_m, mw = mz, 0.022
        print("LANDMARKS", name, "eyes", [(round(o["cx"], 4), round(o["cz"], 4), round(o["w"], 4), round(o["h"], 4)) for o in eye_open],
              "mouth z %.4f half-width %.4f" % (mz_m, mw), "ez %.4f mz %.4f" % (ez, mz))
        # cylindrical UVs from the rest coordinates (front of the face at u = 0.5); the body's
        # own UV layers are dropped so the paint layer is the only one
        Z0, Z1 = ez - 0.175, ez + 0.155
        for l in list(bm.loops.layers.uv):
            bm.loops.layers.uv.remove(l)
        uvl = bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            angs = [math.atan2(rco(l.vert).x, -(rco(l.vert).y - yc)) for l in f.loops]
            wrap = max(angs) - min(angs) > math.pi
            for l, a in zip(f.loops, angs):
                if wrap and a < 0:
                    a += 2 * math.pi
                p = rco(l.vert)
                l[uvl].uv = (0.5 + a / (2 * math.pi), (p.z - Z0) / (Z1 - Z0))
        mm = bpy.data.meshes.new(name + " mask")
        bm.to_mesh(mm)
        # rest coordinates of the mask verts (for hair roots and painting)
        mrest = [V(d.vector) for d in mm.attributes["rest_co"].data]
        mask = bpy.data.objects.new(name + " v3mask", mm)
        bpy.context.scene.collection.objects.link(mask)
        for poly in mm.polygons:
            poly.use_smooth = True
        mm.materials.append(bpy.data.materials.get(name + " mask paint") or bpy.data.materials.new(name + " mask paint"))
        # lining: a dark inner copy, seen only through the parted lips and the rim
        lining_me = mm.copy()
        lining_me.name = name + " mask lining"
        lin = bpy.data.objects.new(name + " v3mask lining", lining_me)
        bpy.context.scene.collection.objects.link(lin)
        for v in lining_me.vertices:
            v.co = hc + (v.co - hc) * 0.955
        lining_me.materials.clear()
        lining_me.materials.append(bpy.data.materials.get("V3 mask lining") or bpy.data.materials.new("V3 mask lining"))
        sd = mask.modifiers.new("Solidify", "SOLIDIFY")
        sd.thickness = 0.004
        sd.offset = -1.0
        sd.use_rim = True
        sd.use_rim_only = False
        ss = mask.modifiers.new("Subsurf", "SUBSURF")
        ss.levels, ss.render_levels = 1, 2
        bm.free()
        # painted eyes: ivory eyeballs with an iris and a dark pupil opening
        eyes = []
        for k, side in enumerate(("L", "R")):
            eb = ecs[k]
            c_rest = V((eye_open[k]["cx"], eb.y, eye_open[k]["cz"]))
            c = hc + (M @ c_rest - hc) * S
            em = bpy.data.meshes.new(name + " eye " + side)
            bme = bmesh.new()
            bmesh.ops.create_uvsphere(bme, u_segments=32, v_segments=20, radius=0.0122 * S)
            bme.to_mesh(em)
            bme.free()
            eo = bpy.data.objects.new(name + " v3eye " + side, em)
            bpy.context.scene.collection.objects.link(eo)
            # local -Y = the head's forward direction
            fw = (R @ V((0, -1, 0))).normalized()
            up = (R @ V((0, 0, 1))).normalized()
            eo.matrix_world = Matrix.Translation(c - fw * 0.0025) @ basis_from(up, fw).to_4x4()
            for p in em.polygons:
                p.use_smooth = True
            em.materials.append(bpy.data.materials.get(name + " eye paint") or bpy.data.materials.new(name + " eye paint"))
            eyes.append(eo)
        # landmarks for painting and for the hair: rest -> (azimuth, z)
        land = dict(ez=ez, ex=ex, mz=mz_m, mw=mw, yc=yc, y_front=y_front, Z0=Z0, Z1=Z1,
                    eyes=[dict(cx=o["cx"], cz=o["cz"], w=o["w"], h=o["h"], pts=o["pts"]) for o in eye_open])
        # azimuth of the front face surface on a 1 mm (x, z) grid (rest coordinates)
        import numpy as np
        front = [p for p in mrest if p.y < yc - 0.02]
        kd = KDTree(len(front))
        for i, p in enumerate(front):
            kd.insert(V((p.x, p.z, 0.0)), i)
        kd.balance()
        gx = np.arange(-0.10, 0.1001, 0.001)
        gz = np.arange(Z0, Z1 + 0.0001, 0.001)
        gaz = np.zeros((len(gz), len(gx)), np.float32)
        for j, z in enumerate(gz):
            for i, x in enumerate(gx):
                co, k, dd = kd.find(V((float(x), float(z), 0.0)))
                gaz[j, i] = math.atan2(float(x), -(front[k].y - yc))
        os.makedirs(texdir, exist_ok=True)
        stem = os.path.join(texdir, name.replace(" ", "_"))
        np.savez(stem + "_azgrid.npz", xs=gx, zs=gz, az=gaz)
        with open(stem + "_mask.json", "w") as f:
            json.dump(dict(name=name, ms=ms, land=land), f)
        paint_subprocess(["paint-mask", "--params", stem + "_mask.json"])
        print("MASK", name, "verts", len(mm.vertices))
        hair = build_mask_hair(name, ms, mask, mrest, land, H, colliders)
        return [mask, lin] + eyes + hair

    # ---------------------------------------------------------------------------
    # hair and beard: clumped, curling hair curves rooted on the mask, combed down and
    # back, kept outside the mask and outside the actor's clothes and couch
    # ---------------------------------------------------------------------------
    def build_mask_hair(name, ms, mask, mrest, land, H, colliders):
        import numpy as np
        rr = random.Random(ms["seed"])
        ez, mz, yc = land["ez"], land["mz"], land["yc"]
        R = H["R"]
        up_w = (R @ V((0, 0, 1))).normalized()
        back_w = (R @ V((0, 1, 0))).normalized()
        left_w = (R @ V((1, 0, 0))).normalized()
        down_g = V((0, 0, -1))
        dg = bpy.context.evaluated_depsgraph_get()
        mw = mask.matrix_world
        me = mask.data
        mverts = [mw @ v.co for v in me.vertices]
        mnorm = [(mw.to_3x3() @ v.normal).normalized() for v in me.vertices]
        bvh_mask = BVHTree.FromPolygons(mverts, [list(p.vertices) for p in me.polygons])
        # colliders: body (closed, normals out) + garments (open: decided relative to the body)
        body = colliders["body"]
        bvh_body = bvh_of([body])
        bvh_cloth = bvh_of(colliders["cloth"]) if colliders.get("cloth") else None
        bvh_solid = bvh_of(colliders["solid"]) if colliders.get("solid") else None

        def azimuth(p):
            return math.atan2(p.x, -(p.y - yc))

        def is_scalp(p):
            a = azimuth(p)
            fn = math.cos(a)
            z_hl = ez + ms["hairline"] + ms["recede"] * (abs(a) / 0.6) ** 2
            if fn > 0.55:
                thr = z_hl
            elif fn > 0.1:
                thr = lerp(z_hl, ez + 0.005, (0.55 - fn) / 0.45)
            else:
                thr = land["Z0"] + 0.045
            return p.z > thr

        def is_beard(p):
            a = azimuth(p)
            if abs(a) > 1.45 or math.cos(a) < 0.0:
                return False
            if abs(math.sin(a) * 0.1) < land.get("mw", 0.022) + 0.004 and abs(p.z - mz) < 0.0135:
                return False                                   # the lips stay bare
            return p.z < float(beard_top_rule(ms, ez, mz, a))

        # sample roots on the mask faces by area
        polys = list(me.polygons)

        def sample(pred, n):
            tris = []
            for p in polys:
                c = sum((mrest[i] for i in p.vertices), Vector()) / len(p.vertices)
                if pred(c):
                    tris.append((p, p.area))
            tot = sum(a for _, a in tris)
            cum, acc = [], 0.0
            for _, a in tris:
                acc += a
                cum.append(acc)
            import bisect
            out = []
            for _ in range(n):
                x = rr.random() * tot
                p = tris[min(len(tris) - 1, bisect.bisect_left(cum, x))][0]
                vs = list(p.vertices)
                k = rr.randrange(len(vs) - 2) if len(vs) > 3 else 0
                a, b, c = vs[0], vs[k + 1], vs[k + 2]
                u, w = rr.random(), rr.random()
                if u + w > 1:
                    u, w = 1 - u, 1 - w
                pos = mverts[a] + (mverts[b] - mverts[a]) * u + (mverts[c] - mverts[a]) * w
                rest_p = mrest[a] + (mrest[b] - mrest[a]) * u + (mrest[c] - mrest[a]) * w
                nrm = (mnorm[a] + mnorm[b] + mnorm[c]).normalized()
                out.append((pos, nrm, rest_p))
            return out

        def keep_out(p, layer, hug=False):
            """outside the mask by 'layer' (and, for the wig, not far from it: a dressed wig lies
            on the head). Returns (point, contact): contact = the point met the actor's clothes,
            body or the couch, where a real strand would come to rest (the strand stops there)."""
            loc, n, i, dist = bvh_mask.find_nearest(p)
            if loc is not None:
                s = (p - loc).dot(n)
                if s < layer:
                    p = p + n * (layer - s)
                elif hug and s > layer + 0.011 and dist < 0.035:
                    p = p - n * (s - layer - 0.011) * 0.7
            contact = False
            loc, nb, i, dist = bvh_body.find_nearest(p)
            if loc is not None and dist < 0.15:
                depth = (p - loc).dot(nb)
                if depth < 0.006:
                    p = p + nb * (0.006 - depth)
                    contact = True
                elif bvh_cloth is not None:
                    # is there cloth between the point and the body? then the point is outside it
                    between = bvh_cloth.ray_cast(p, -nb, depth)
                    if between[0] is None:
                        above = bvh_cloth.ray_cast(p, nb, 0.06)
                        if above[0] is not None:          # under the cloth: bring it out on top
                            p = above[0] + nb * 0.006
                            contact = True
                    elif (p - between[0]).length < 0.005:
                        p = between[0] + nb * 0.006
                        contact = True
            if bvh_solid is not None:
                sl, sn, si, sd = bvh_solid.find_nearest(p)
                if sl is not None and (p - sl).dot(sn) < 0.005:
                    p = sl + sn * 0.005
                    contact = True
            return p, contact

        def grow(root, nrm, rest_p, length, kind, K, phase, curl_amp, curl_per):
            pts = [root.copy()]
            if kind == "scalp":
                a = azimuth(rest_p)
                fn = math.cos(a)
                # combed: from the front hairline back over the crown, elsewhere down and out
                comb = (back_w * (0.9 if fn > 0.5 else 0.25) - up_w * (0.25 if fn > 0.5 else 1.0))
            elif rest_p.z > land["mz"] + 0.004:
                # moustache: swept down and out toward the corners of the mouth
                comb = -up_w * 0.55 + left_w * (1.0 if rest_p.x > 0 else -1.0)
            else:
                comb = (-up_w * 1.0 + nrm * 0.15)
            comb = (comb - nrm * comb.dot(nrm)).normalized() if (comb - nrm * comb.dot(nrm)).length > 1e-6 else -up_w
            d = (comb * 0.9 + nrm * (0.15 if kind == "scalp" else 0.3)).normalized()
            step = length / (K - 1)
            p = root.copy()
            side = comb.cross(nrm).normalized()
            for k in range(1, K):
                t = k / (K - 1)
                # gravity takes over toward the tip; a little lift keeps volume
                g = down_g * (0.25 + 0.75 * t) * (1.0 if kind == "scalp" else 0.6)
                d = (d + g * 0.35).normalized()
                p = p + d * step
                c = (side * math.cos(phase + t * curl_per) + nrm * math.sin(phase + t * curl_per)) * curl_amp * min(1.0, t * 2.5)
                q, hit = keep_out(p + c, 0.0022 + 0.006 * t if kind == "scalp" else 0.002 + 0.007 * t, hug=kind == "scalp")
                p = q - c
                pts.append(q)
                if hit:                                   # rests on the cloth: the strand ends here
                    while len(pts) < K:
                        pts.append(pts[-1] + d * 0.0004)
                    break
            return pts
        objs = []
        for kind, n, nguide, (L0, L1), curl in (("scalp", ms["n_hair"], 380, ms["hair_len"], ms["curl"]),
                                                ("beard", ms["n_beard"], 220, ms["beard_len"], ms["beard_curl"])):
            pred = is_scalp if kind == "scalp" else is_beard
            K = 12 if kind == "scalp" else 9
            guides_r = sample(pred, nguide)
            guides = []
            for (pos, nrm, rp) in guides_r:
                a = azimuth(rp)
                if kind == "scalp":
                    # front short, back long; the nape longest
                    L = lerp(L0, L1, smoothstep(0.6, -0.6, math.cos(a))) * rr.uniform(0.85, 1.12)
                else:
                    # chin longest, moustache and cheeks short
                    L = lerp(L1, L0 * 0.55, smoothstep(0.15, 0.9, abs(a))) * (0.6 if rp.z > mz + 0.005 else 1.0) * rr.uniform(0.85, 1.12)
                ph = rr.random() * 6.283
                guides.append(grow(pos, nrm, rp, L, kind, K, ph, curl * rr.uniform(0.7, 1.3), rr.uniform(7.0, 11.0)))
            kd = KDTree(len(guides))
            for i, g in enumerate(guides):
                kd.insert(g[0], i)
            kd.balance()
            roots = sample(pred, n)
            pos_all, rad_all = [], []
            for (pos, nrm, rp) in roots:
                co, gi, dist = kd.find(pos)
                g = guides[gi]
                off = pos - g[0]
                jitter = V((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-1, 1))) * 0.0015
                lscale = rr.uniform(0.82, 1.08)
                pts = []
                stop = None
                for k, q in enumerate(g):
                    t = k / (K - 1)
                    if stop is not None:
                        pts.append(pts[-1] + stop * 0.0004)
                        continue
                    clump = 0.88 * smoothstep(0.1, 0.8, t)        # strands gather into locks toward the tips
                    pk = g[0] + (q - g[0]) * lscale + off * (1 - clump) + jitter * t
                    if k > 0:
                        pk, hit = keep_out(pk, 0.0018 + 0.005 * t, hug=kind == "scalp")
                        if hit:
                            stop = (pk - pts[-1]).normalized() if (pk - pts[-1]).length > 1e-6 else V((0, 0, -1))
                    pts.append(pk)
                pos_all += pts
                base_r = 0.00027 if kind == "scalp" else 0.0003
                rad_all += [base_r * (1.0 - 0.75 * (k / (K - 1))) for k in range(K)]
            cv = bpy.data.hair_curves.new(name + " " + kind)
            cv.add_curves([K] * len(roots))
            cv.attributes["position"].data.foreach_set("vector", [c for v in pos_all for c in v])
            ra = cv.attributes.get("radius") or cv.attributes.new("radius", "FLOAT", "POINT")
            ra.data.foreach_set("value", rad_all)
            ob = bpy.data.objects.new(name + " " + ("v3hair" if kind == "scalp" else "v3beard"), cv)
            bpy.context.scene.collection.objects.link(ob)
            cv.materials.append(bpy.data.materials.get(name + " mask hair") or bpy.data.materials.new(name + " mask hair"))
            objs.append(ob)
            print("HAIR", name, kind, len(roots), "strands")
        return objs

    # ==========================================================================
    # second cloth pass on the frozen figures: himation (standing) and blanket (couch)
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

    HIMATION_PATH = [
        # (mode, a, b, width dir (l, f, u), half-width, offset)  side: a = angle from the front
        # toward the figure's left (deg), b = height (m); top: (left, front) over the shoulder.
        # The classic wrap: one end hangs down the front from the left shoulder -> over the
        # shoulder -> diagonally down the back -> under the right arm round the right hip ->
        # across the front OVER the first end (larger offset) -> the end over the left forearm
        ("side", 38, 0.60, (1, 0.1, 0), 0.29, 0.035),
        ("side", 40, 1.10, (1, 0.1, 0), 0.29, 0.035),
        ("side", 44, 1.37, (1, 0.05, 0.2), 0.27, 0.035),
        ("top", 0.17, 0.02, (0.2, 1, 0), 0.25, 0.03),
        ("side", 150, 1.34, (0.6, 0, 1), 0.29, 0.035),
        ("side", 205, 1.04, (0.15, 0, 1), 0.34, 0.035),
        ("side", 262, 0.80, (0, 0, 1), 0.36, 0.04),
        ("side", 318, 0.78, (0, 0, 1), 0.36, 0.075),
        ("side", 12, 0.84, (0, 0, 1), 0.34, 0.085),
        ("arm", 0, 0, (0, 0, 1), 0.30, 0.0),
    ]

    def build_himation(name, fig, colliders, res=0.02):
        B = fig["frame"]
        P = fig["poser"]
        bvh = bvh_of(colliders)
        axis_o = P.head("root")
        cs, ws, hws, pins = [], [], [], []
        for mode, a, b, w, hw, off in HIMATION_PATH:
            if mode == "side":
                phi = math.radians(a)
                d = (B.Fw * math.cos(phi) + B.L * math.sin(phi)).normalized()
                o = V((axis_o.x, axis_o.y, b)) + d * 1.2
                hit = bvh.ray_cast(o, -d, 2.0)
                p = hit[0] if hit[0] is not None else V((axis_o.x, axis_o.y, b)) + d * 0.25
                c = p + d * off
            elif mode == "top":
                o = B.p(a, b, 2.2)
                o = V((o.x, o.y, 2.2))
                hit = bvh.ray_cast(o, V((0, 0, -1)), 2.0)
                c = (hit[0] if hit[0] is not None else B.p(a, b, 1.5)) + V((0, 0, off))
            else:
                c = 0.5 * (P.head("wrist.L") + P.head("lowerarm02.L")) + B.U * 0.07
            cs.append(c)
            ws.append(B.d(*w))
            hws.append(hw)
        dense = [catmull(cs, i / 600.0) for i in range(601)]
        L = [0.0]
        for i in range(1, len(dense)):
            L.append(L[-1] + (dense[i] - dense[i - 1]).length)
        total = L[-1] + 0.35                                 # the end hangs on past the forearm
        nrows = int(total / res)
        nw = int(2 * max(hws) / res) + 1
        verts, pinw = [], []
        k = 0
        last_c, last_tan = cs[-1], (cs[-1] - cs[-2]).normalized()
        for r in range(nrows + 1):
            s = total * r / nrows
            if s <= L[-1]:
                while k < len(L) - 2 and L[k + 1] < s:
                    k += 1
                t = (k + (s - L[k]) / max(1e-9, L[k + 1] - L[k])) / 600.0
                c = catmull(cs, t)
                c2 = catmull(cs, min(1.0, t + 0.002))
                c1 = catmull(cs, max(0.0, t - 0.002))
                tan = (c2 - c1).normalized()
                x = t * (len(cs) - 1)
                i0 = min(int(x), len(cs) - 2)
                u = x - i0
                w = ws[i0].lerp(ws[i0 + 1], u)
                hw = hws[i0] + (hws[i0 + 1] - hws[i0]) * u
            else:
                # past the forearm: hang straight down
                c = last_c + V((0, 0, -(s - L[-1])))
                tan = V((0, 0, -1))
                w, hw = ws[-1], hws[-1]
                t = 1.0
            w = (w - tan * w.dot(tan))
            w = w.normalized() if w.length > 1e-6 else B.L
            for j in range(nw):
                tt = -1.0 + 2.0 * j / (nw - 1)
                verts.append(c + w * (tt * hw))
                pin = 0.0
                if abs(t - 3.0 / (len(cs) - 1)) < 0.25 / (len(cs) - 1) and abs(tt) < 0.35:
                    pin = 1.0                      # on top of the left shoulder
                if abs(t - 1.0) < 0.0001 and s <= L[-1] + 0.06 and abs(tt) < 0.5:
                    pin = 0.7                      # over the left forearm
                pinw.append(pin)
        faces = [(r * nw + j, r * nw + j + 1, (r + 1) * nw + j + 1, (r + 1) * nw + j) for r in range(nrows) for j in range(nw - 1)]
        me = bpy.data.meshes.new(name + " himation")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ob = bpy.data.objects.new(name + " himation", me)
        bpy.context.scene.collection.objects.link(ob)
        uv = me.uv_layers.new(name="pattern")
        uvw = me.uv_layers.new(name="weave")
        for poly in me.polygons:
            poly.use_smooth = True
            for li, vi in zip(poly.loop_indices, poly.vertices):
                r, j = divmod(vi, nw)
                uv.data[li].uv = (j / (nw - 1), r / nrows)
                uvw.data[li].uv = (j * res, r * res)
        vg = ob.vertex_groups.new(name="pin")
        for i, wgt in enumerate(pinw):
            if wgt > 0:
                vg.add([i], wgt, "REPLACE")
        me.materials.append(bpy.data.materials.get("V3 himation") or bpy.data.materials.new("V3 himation"))
        ob["size"] = (2 * max(hws), total)
        print("HIMATION rows %d x %d, %.2f x %.2f m" % (nrows + 1, nw, 2 * max(hws), total))
        return ob

    def build_blanket(name, colliders, res=0.016):
        """a wool blanket dropped over the reclining figure's legs and the couch edge"""
        bvh = bvh_of(colliders)
        w, h = 1.16, 1.30
        cx, cy, rot = 0.47, -0.17, math.radians(-5)
        nx, ny = int(w / res), int(h / res)
        R = Matrix.Rotation(rot, 3, "Z")
        verts = []
        for j in range(ny + 1):
            for i in range(nx + 1):
                x, y = -w / 2 + w * i / nx, -h / 2 + h * j / ny
                p = R @ V((x, y, 0.0)) + V((cx, cy, 0.0))
                hit = bvh.ray_cast(V((p.x, p.y, 2.5)), V((0, 0, -1)), 3.0)
                ztop = hit[0].z if hit[0] is not None else Z_MATT
                verts.append(V((p.x, p.y, 0.0)))
                verts[-1].z = ztop
        # start as a smooth sheet a few cm over the highest point below each region
        zs = [v.z for v in verts]
        zmax = max(zs)
        for v in verts:
            v.z = max(v.z + 0.05, lerp(v.z + 0.05, zmax + 0.03, 0.6))
        faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i) for j in range(ny) for i in range(nx)]
        me = bpy.data.meshes.new(name + " blanket")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        ob = bpy.data.objects.new(name + " blanket", me)
        bpy.context.scene.collection.objects.link(ob)
        uv = me.uv_layers.new(name="pattern")
        uvw = me.uv_layers.new(name="weave")
        for poly in me.polygons:
            poly.use_smooth = True
            for li, vi in zip(poly.loop_indices, poly.vertices):
                j, i = divmod(vi, nx + 1)
                uv.data[li].uv = (i / nx, j / ny)
                uvw.data[li].uv = (i * res, j * res)
        me.materials.append(bpy.data.materials.get("V3 blanket") or bpy.data.materials.new("V3 blanket"))
        print("BLANKET %d x %d verts" % (nx + 1, ny + 1))
        return ob

    # ==========================================================================
    # materials (built into figures.blend; images packed)
    # ==========================================================================
    def linen_images(assets):
        d = os.path.join(assets, "textures", "rough_linen")
        out = {}
        for k, fn, cs in (("diff", "rough_linen_diff_2k.jpg", "sRGB"), ("rough", "rough_linen_rough_2k.jpg", "Non-Color"),
                          ("nor", "rough_linen_nor_gl_2k.jpg", "Non-Color")):
            im = bpy.data.images.load(os.path.join(d, fn), check_existing=True)
            im.colorspace_settings.name = cs
            out[k] = im
        return out

    def mat_cloth(name, lin, pattern_img=None, color=None, sheen=0.6, rough=0.88, weave_scale=5.26, normal=0.55):
        """wool/linen cloth: base colour from a pattern image (UV 'pattern') or a flat dye,
        modulated by the CC0 rough_linen weave (UV 'weave', metres)"""
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bs.outputs[0], out.inputs["Surface"])
        uvw = nt.nodes.new("ShaderNodeUVMap")
        uvw.uv_map = "weave"
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (weave_scale, weave_scale, weave_scale)
        nt.links.new(uvw.outputs["UV"], mp.inputs["Vector"])
        td = nt.nodes.new("ShaderNodeTexImage")
        td.image = lin["diff"]
        tr = nt.nodes.new("ShaderNodeTexImage")
        tr.image = lin["rough"]
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = lin["nor"]
        for t in (td, tr, tn):
            nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        # weave luminance -> +-12 % brightness variation of the dye
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(td.outputs["Color"], bw.inputs["Color"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.2
        mr.inputs["From Max"].default_value = 0.8
        mr.inputs["To Min"].default_value = 0.86
        mr.inputs["To Max"].default_value = 1.10
        nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
        if pattern_img is not None:
            uvp = nt.nodes.new("ShaderNodeUVMap")
            uvp.uv_map = "pattern"
            tp = nt.nodes.new("ShaderNodeTexImage")
            tp.image = pattern_img
            tp.interpolation = "Cubic"
            tp.extension = "REPEAT"
            nt.links.new(uvp.outputs["UV"], tp.inputs["Vector"])
            col = tp.outputs["Color"]
        else:
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = (*color, 1.0)
            col = rgb.outputs[0]
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mx.inputs[6])
        nt.links.new(mr.outputs["Result"], mx.inputs[7])
        nt.links.new(mx.outputs[2], bs.inputs["Base Color"])
        rmr = nt.nodes.new("ShaderNodeMapRange")
        rmr.inputs["To Min"].default_value = rough - 0.08
        rmr.inputs["To Max"].default_value = min(1.0, rough + 0.08)
        nt.links.new(tr.outputs["Color"], rmr.inputs["Value"])
        nt.links.new(rmr.outputs["Result"], bs.inputs["Roughness"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "weave"
        nm.inputs["Strength"].default_value = normal
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
        bs.inputs["Sheen Weight"].default_value = sheen
        bs.inputs["Sheen Roughness"].default_value = 0.6
        bs.inputs["Sheen Tint"].default_value = (1, 1, 1, 1)
        bs.inputs["Specular IOR Level"].default_value = 0.25
        return m

    def mat_mask_paint(name, img, lin):
        """gesso-and-pigment paint on stiffened linen: matt, slightly waxy, faint linen texture"""
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bs.outputs[0], out.inputs["Surface"])
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = img
        ti.interpolation = "Cubic"
        nt.links.new(uv.outputs["UV"], ti.inputs["Vector"])
        nt.links.new(ti.outputs["Color"], bs.inputs["Base Color"])
        bs.inputs["Roughness"].default_value = 0.62
        bs.inputs["Specular IOR Level"].default_value = 0.3
        # brush and linen relief, very faint
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 180.0
        nz.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (22.0, 22.0, 22.0)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        tl = nt.nodes.new("ShaderNodeTexImage")
        tl.image = lin["diff"]
        tl.projection = "BOX"
        tl.projection_blend = 0.3
        nt.links.new(mp.outputs["Vector"], tl.inputs["Vector"])
        bwl = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(tl.outputs["Color"], bwl.inputs["Color"])
        add = nt.nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        nt.links.new(nz.outputs["Fac"], add.inputs[0])
        nt.links.new(bwl.outputs["Val"], add.inputs[1])
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = 0.22
        bp.inputs["Distance"].default_value = 0.0004
        nt.links.new(add.outputs[0], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bs.inputs["Normal"])
        return m

    def mat_eye_paint(name):
        """painted eye on the ball: ivory white, brown iris ring, dark pupil (the sight hole)"""
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bs.outputs[0], out.inputs["Surface"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
        # radial distance from the forward (-Y) axis in the XZ plane, normalised by the radius
        r2 = nt.nodes.new("ShaderNodeVectorMath")
        r2.operation = "LENGTH"
        cmb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(sep.outputs["X"], cmb.inputs["X"])
        nt.links.new(sep.outputs["Z"], cmb.inputs["Y"])
        nt.links.new(cmb.outputs["Vector"], r2.inputs[0])
        front = nt.nodes.new("ShaderNodeMath")
        front.operation = "LESS_THAN"
        nt.links.new(sep.outputs["Y"], front.inputs[0])
        front.inputs[1].default_value = 0.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "LINEAR"
        cr.elements[0].position = 0.0
        cr.elements[0].color = (0.006, 0.004, 0.003, 1)
        cr.elements[1].position = 1.0
        cr.elements[1].color = (*srgb((214, 204, 184)), 1)
        for pos, col in ((0.0026, (8, 6, 5)), (0.0031, (62, 38, 22)), (0.0052, (92, 58, 32)), (0.0060, (40, 26, 18)), (0.0066, (205, 194, 172))):
            e = cr.elements.new(pos / 0.02)
            e.color = (*srgb(col), 1)
        scale = nt.nodes.new("ShaderNodeMath")
        scale.operation = "DIVIDE"
        nt.links.new(r2.outputs["Value"], scale.inputs[0])
        scale.inputs[1].default_value = 0.02
        nt.links.new(scale.outputs[0], ramp.inputs["Fac"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(front.outputs[0], mix.inputs["Factor"])
        mix.inputs[6].default_value = (*srgb((214, 204, 184)), 1)
        nt.links.new(ramp.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bs.inputs["Base Color"])
        bs.inputs["Roughness"].default_value = 0.42
        bs.inputs["Coat Weight"].default_value = 0.15
        return m

    def mat_hair(name, mel, red, rnd, grey=0.0, rough=0.42):
        """wig hair: dark strands (melanin), and for a grizzled wig a share of white strands
        chosen per strand (salt and pepper)"""
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")

        def hair(mel_, red_, rnd_):
            hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
            hb.parametrization = "MELANIN"
            hb.inputs["Melanin"].default_value = mel_
            hb.inputs["Melanin Redness"].default_value = red_
            hb.inputs["Random Color"].default_value = rnd_
            hb.inputs["Roughness"].default_value = rough
            hb.inputs["Random Roughness"].default_value = 0.2
            hb.inputs["Coat"].default_value = 0.05
            return hb
        dark = hair(mel, red, rnd)
        if grey <= 0:
            nt.links.new(dark.outputs[0], out.inputs["Surface"])
            return m
        white = hair(0.08, 0.05, 0.3)
        hi = nt.nodes.new("ShaderNodeHairInfo")
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        lt.inputs[1].default_value = grey
        nt.links.new(hi.outputs["Random"], lt.inputs[0])
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lt.outputs[0], mx.inputs["Fac"])
        nt.links.new(dark.outputs[0], mx.inputs[1])
        nt.links.new(white.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
        return m

    def mat_plain(name, color, rough=0.6, spec=0.3, bump=0.0, bump_scale=80.0):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bs = nt.nodes.get("Principled BSDF")
        bs.inputs["Base Color"].default_value = (*color, 1)
        bs.inputs["Roughness"].default_value = rough
        bs.inputs["Specular IOR Level"].default_value = spec
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

    def paint_subprocess(args):
        """run this file's painting modes in the system python3 (numpy + Pillow)"""
        py = os.environ.get("V3_PYTHON", "/usr/bin/python3")
        subprocess.run([py, "-I", os.path.abspath(__file__)] + args, check=True)

    def make_materials(work, assets):
        lin = linen_images(assets)
        texdir = os.path.join(work, "textures")
        paint_subprocess(["paint-patterns", "--texdir", texdir])
        with open(os.path.join(texdir, "patterns.json")) as f:
            imgs = json.load(f)
        for key, (img_body, img_sleeve) in imgs.items():
            mat_cloth("V3 " + key, lin, bpy.data.images.load(img_body, check_existing=True),
                      sheen=0.55 if key != "rags" else 0.5, rough=0.86)
            mat_cloth("V3 " + key + " sleeves", lin, bpy.data.images.load(img_sleeve, check_existing=True),
                      sheen=0.55, rough=0.86)
        mat_cloth("V3 himation", lin, bpy.data.images.load(os.path.join(texdir, "himation.png"), check_existing=True), sheen=0.5, rough=0.88)
        mat_cloth("V3 blanket", lin, bpy.data.images.load(os.path.join(texdir, "blanket.png"), check_existing=True), sheen=0.65, rough=0.9, normal=0.7)
        mat_plain("V3 belt", srgb((58, 38, 26)), rough=0.55, spec=0.35, bump=0.15)
        mat_plain("V3 boots", srgb(DYE["leather"]), rough=0.55, spec=0.35, bump=0.2)
        mat_plain("V3 mask lining", (0.006, 0.005, 0.004), rough=0.95, spec=0.05)
        for name, ms in MASKS.items():
            p = os.path.join(texdir, name.replace(" ", "_") + "_mask.png")
            if os.path.exists(p):
                mat_mask_paint(name + " mask paint", bpy.data.images.load(p, check_existing=True), lin)
            mat_eye_paint(name + " eye paint")
            mat_hair(name + " mask hair", ms["mel"], ms["red"], ms["rnd"], ms.get("grey", 0.0))

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
            dst.collections = [c for c in src.collections if c == "V3 figures" or c.endswith("(v3)")]
        top = bpy.data.collections["V3 figures"]
        bpy.context.scene.collection.children.link(top)
        return top

    def place_figures(top, ctrl_y):
        ctrl = bpy.data.objects["Platform ctrl"]
        groups = {}
        for c in top.children:
            name = c.name.replace("V3 ", "").replace(" (v3)", "")
            groups[name] = list(c.objects)
            for o in c.objects:
                if o.parent is not None:
                    continue
                mb = o.matrix_basis.copy()         # (unparented: basis = world, platform-local)
                if name == "Reclining actor":
                    o.parent = ctrl
                    o.matrix_parent_inverse = Matrix.Identity(4)
                    o.matrix_basis = mb
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
        only = opts.get("only", "B")
        shots = opts.get("shots", "tableau,cutaway,crop").split(",")
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
        tpath = os.path.join(outdir, "timing_%s.json" % only)

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
            path = os.path.join(outdir, "%s_%s.png" % (label, tag if not crop else "crop"))
            r.filepath = path
            t = time.time()
            bpy.ops.render.render(write_still=True)
            dt = time.time() - t
            timing.append(dict(shot=tag if not crop else "crop", version=label, seconds=round(dt, 1), samples=sc.cycles.samples,
                               res="%dx%d" % (r.resolution_x, r.resolution_y), crop=bool(crop)))
            print("RENDER %s %s %.1fs" % (label, tag, dt))
            with open(tpath, "w") as f:
                json.dump(timing, f, indent=1)

        # warm-up: kernels, images, BVH (not timed)
        sc.cycles.samples = 1
        r.resolution_percentage = 10
        sc.camera = bpy.data.objects[SHOTS["tableau"][0]]
        sc.frame_set(SHOTS["tableau"][1])
        r.filepath = os.path.join(outdir, "warmup.png")
        bpy.ops.render.render(write_still=True)
        r.resolution_percentage = 100
        sc.cycles.samples = spp
        top = append_figures(os.path.join(work, "figures.blend"))
        groups = place_figures(top, ctrl_y)
        bpy.context.view_layer.update()
        # crop window: the reclining figure's masked head and both hands, in the tableau camera
        from bpy_extras.object_utils import world_to_camera_view
        sc.frame_set(SHOTS["tableau"][1])
        cam = bpy.data.objects[SHOTS["tableau"][0]]
        pts = []
        for o in groups["Reclining actor"]:
            if o.name.endswith("v3mask"):
                pts += [o.matrix_world @ V(b) for b in o.bound_box]
        hb = bpy.data.objects.get("V3 Reclining actor hands")
        if hb:
            pts += [hb.matrix_world @ V(b) for b in hb.bound_box]
        cp = [world_to_camera_view(sc, cam, p) for p in pts]
        x0, x1 = min(p.x for p in cp), max(p.x for p in cp)
        y0, y1 = min(p.y for p in cp), max(p.y for p in cp)
        # pad and fix the aspect to 1:1 in pixels (crop of a 16:9 frame)
        cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
        half_w = max((x1 - x0) / 2 * 1.25, (y1 - y0) / 2 * 1.25 * 9 / 16)
        half_h = half_w * 16 / 9
        crop = (max(0, cxm - half_w), min(1, cxm + half_w), max(0, cym - half_h), min(1, cym + half_h))
        with open(os.path.join(outdir, "crop.json"), "w") as f:
            json.dump(crop, f)
        figs_b = [o for c in top.children for o in c.all_objects]
        for o in figs_b:
            o.hide_render = True
        mann = mannequin_objects()

        def show(version, tag):
            for o in mann:
                o.hide_render = version != "A"
            for name, objs in groups.items():
                for o in objs:
                    vis = version == "B"
                    if name.startswith("Stagehand") and tag != "cutaway":
                        vis = False       # at the tableau frame they wait hidden behind the facade wall
                    o.hide_render = not vis
        for version in only:
            for tag in shots:
                show(version, tag if tag != "crop" else "tableau")
                if tag == "crop":
                    shot("tableau", version, crop=crop, scale=3)
                else:
                    shot(tag, version)
        print("RENDER STAGE DONE")

    POSERS = {
        "Standing actor": lambda P, rig: pose_standing(P, rig),
        "Reclining actor": lambda P, rig: pose_reclining(P, rig),
        "Stagehand A": lambda P, rig: pose_stagehand(P, rig, -0.55, "L", 0.0),
        "Stagehand B": lambda P, rig: pose_stagehand(P, rig, 0.55, "R", 1.0),
    }

    # ==========================================================================
    # quick Workbench previews (pose / cloth / mask checks)
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
        "standing_back": ((3.6, 0.0, 1.6), (2.0, 0.65, 1.0), 35, (640, 800)),
        "standing_backleft": ((3.4, 2.2, 1.5), (2.0, 0.7, 1.0), 38, (640, 800)),
        "standing_front": ((0.5, 0.2, 1.5), (2.0, 0.65, 1.05), 35, (640, 800)),
        "reclining_close": ((0.2, 1.3, 1.5), (-0.35, -0.1, 1.2), 40, (800, 640)),
        "reclining_front": ((-0.1, 2.0, 1.45), (-0.2, -0.2, 1.05), 35, (800, 600)),
        "reclining_top": ((-0.1, -0.2, 3.2), (-0.1, -0.2, 0.9), 35, (800, 600)),
        "reclining_mask": ((0.05, 0.75, 1.5), (-0.45, -0.15, 1.38), 60, (640, 640)),
        "standing_mask": ((1.2, 1.2, 1.7), (2.0, 0.65, 1.62), 60, (640, 640)),
        "cutaway_cam": ((-5.62, 0.53, 3.46), (0.32, 0.65, 0.8), 30, (960, 540)),
        "stagehands_side": ((-2.6, -1.3, 0.9), (0.0, -1.2, 0.4), 35, (800, 600)),
        "stagehands_back": ((0.0, -3.6, 1.4), (0.0, -1.0, 0.4), 35, (800, 600)),
    }

    def previews(work, prefix, views=None, hide_ref=True):
        pdir = os.path.join(work, "preview")
        os.makedirs(pdir, exist_ok=True)
        for v, (cl, tg, lens, res) in PREVIEW_VIEWS.items():
            if views and v not in views:
                continue
            preview(os.path.join(pdir, prefix + v + ".png"), cl, tg, lens, res, hide_ref=hide_ref and v not in ("tableau_cam", "cutaway_cam"))

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

    # ==========================================================================
    # build
    # ==========================================================================
    def build(opts):
        t0 = time.time()
        work = os.path.abspath(opts["work"])
        os.makedirs(work, exist_ok=True)
        stage = opts.get("stage", "full")
        views = opts["views"].split(",") if opts.get("views") else None
        if opts.get("resume") in ("robes", "masks"):
            return resume(opts, work, t0)
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
            figs[name] = dict(rig=rig, body=body, assets=assets, poser=P, final=P.snapshot(), frame=frame)
            print("FIGURE", name, "%.1fs" % (time.time() - t0))
        bpy.context.view_layer.update()
        if stage == "pose":
            previews(work, "pose_", views)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "posed.blend"))
            print("POSE PREVIEWS DONE %.1fs" % (time.time() - t0))
            return
        # ---- robes and tunics ---------------------------------------------------------
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
        bpy.context.view_layer.update()
        for name, fig in figs.items():
            freeze(fig["garment"])
            link_to(fig["garment"], get_coll("MH " + name))
            for o in [fig["body"]] + fig["assets"]:
                freeze(o)
            fig["garment"]["belt_ring"] = list(fig["garment"].get("belt_ring", []))
        for o in bpy.data.objects:
            if o.type == "ARMATURE":
                o.animation_data_clear()
        for name, fig in figs.items():
            relax_cloth(fig["garment"], fig["body"])
        fname = "robes.blend" if not only else "robes_%s.blend" % "+".join(n.replace(" ", "_") for n in figs)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, fname))
        previews(work, "robes_" if not only else "robes_%s_" % "+".join(n.split()[-1] for n in figs), views)
        print("ROBES STAGE DONE %.1fs" % (time.time() - t0))
        if only:
            return
        if stage == "robes":
            return
        opts = dict(opts)
        opts["resume"] = "robes"
        resume(opts, work, t0)

    def figs_from_file(names):
        figs = {}
        for name in names:
            rig = bpy.data.objects.get(name + " rig")
            if rig is None:
                continue
            body = bpy.data.objects[name + " body"]
            kind = GARMENTS[name]["kind"]
            garment = bpy.data.objects[f"{name} {kind}"]
            coll = bpy.data.collections["MH " + name]
            assets = [o for o in coll.objects if o not in (rig, body, garment) and o.type == "MESH" and not o.name.startswith(name + " belt")]
            P = Poser(rig)
            frame = POSERS[name](P, rig)
            figs[name] = dict(rig=rig, body=body, assets=assets, poser=P, final=P.snapshot(), frame=frame, garment=garment)
        return figs

    def resume(opts, work, t0):
        stage = opts.get("stage", "full")
        views = opts["views"].split(",") if opts.get("views") else None
        assets_dir = opts.get("assets", DEFAULT_ASSETS)
        texdir = os.path.join(work, "textures")
        if opts["resume"] == "robes":
            if opts.get("merge"):
                merge_robes(work)
            bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "robes.blend"))
            figs = figs_from_file(FIGURES)
            out = {n: [f["body"], f["garment"]] + f["assets"] for n, f in figs.items()}
            for n, f in figs.items():
                smooth_boundaries(f["garment"])
            for n, f in figs.items():
                belt = build_belt(n, f["garment"], list(f["garment"]["belt_ring"]))
                link_to(belt, bpy.data.collections["MH " + n])
            for name, ms in MASKS.items():
                if name not in figs:
                    continue
                f = figs[name]
                cols = dict(body=f["body"], cloth=[f["garment"]],
                            solid=[bpy.data.objects[n] for n in ("Mattress", "Cushion 0", "Cushion 1")] if name == "Reclining actor" else [])
                objs = build_mask(name, f, ms, cols, texdir)
                for o in objs:
                    link_to(o, bpy.data.collections["MH " + name])
            if "Standing actor" in figs:
                link_to(build_boots("Standing actor", figs["Standing actor"]["body"]), bpy.data.collections["MH Standing actor"])
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "masks.blend"))
            make_materials(work, assets_dir)
            previews(work, "masks_", views)
            print("MASKS STAGE DONE %.1fs" % (time.time() - t0))
            if stage == "masks":
                return
        else:
            bpy.ops.wm.open_mainfile(filepath=os.path.join(work, "masks.blend"))
            figs = figs_from_file(FIGURES)
        finish_drapes(figs, work, assets_dir, t0, views)

    def finish_drapes(figs, work, assets_dir, t0, views):
        sc = bpy.context.scene
        drapes = []
        couch = [bpy.data.objects[n] for n in ("Mattress", "Cushion 0", "Cushion 1", "Couch (kline)")]
        if "Standing actor" in figs:
            f = figs["Standing actor"]
            cols = [f["body"], f["garment"]]
            cc = get_coll("COL2 Standing")
            for o in cols:
                make_collider(o, thick=0.008, friction=60.0)
                if o.name not in cc.objects:
                    cc.objects.link(o)
            him = build_himation("Standing actor", f, cols)
            add_cloth(him, cc, 110, mass=0.32, bend=0.08, tension=14.0, shear=4.0, quality=8, air=1.5)
            him.modifiers["Cloth"].collision_settings.collision_quality = 4
            drapes.append(("Standing actor", him))
        if "Reclining actor" in figs:
            f = figs["Reclining actor"]
            cols = [f["body"], f["garment"]] + couch + [bpy.data.objects["Platform deck"]]
            cc = get_coll("COL2 Reclining")
            for o in cols:
                make_collider(o, thick=0.006, friction=12.0)
                if o.name not in cc.objects:
                    cc.objects.link(o)
            bl = build_blanket("Reclining actor", cols)
            add_cloth(bl, cc, 110, pin=None, mass=0.38, bend=0.15, tension=15.0, shear=4.0, quality=8, air=1.0, rest_key=None)
            bl.modifiers["Cloth"].collision_settings.collision_quality = 4
            drapes.append(("Reclining actor", bl))
        for o in bpy.data.objects:
            if o.animation_data:
                o.animation_data_clear()
        sc.frame_start, sc.frame_end = 1, 110
        t1 = time.time()
        for fr in range(1, 111):
            sc.frame_set(fr)
            if fr % 10 == 0:
                print("  drape frame", fr, "%.1fs" % (time.time() - t1))
        print("DRAPE SIM %.1fs" % (time.time() - t1))
        for name, o in drapes:
            freeze(o)
            link_to(o, bpy.data.collections["MH " + name])
        finalize(figs, work, assets_dir, t0, views)

    def finalize(figs, work, assets_dir, t0, views):
        make_materials(work, assets_dir)
        top = get_coll("V3 figures")
        keep = set()
        for name in figs:
            src = bpy.data.collections["MH " + name]
            c = get_coll("V3 " + name + " (v3)", top)
            rig = figs[name]["rig"]
            for o in list(src.objects):
                if o == rig:
                    continue
                for md in list(o.modifiers):
                    if md.type in ("COLLISION", "CLOTH", "ARMATURE"):
                        o.modifiers.remove(md)
                if o.type == "MESH":
                    if o == figs[name]["body"]:
                        ss = o.modifiers.new("Subsurf", "SUBSURF")
                        ss.levels, ss.render_levels = 1, 1
                    elif o == figs[name]["garment"] or o.name.endswith(("himation", "blanket")):
                        sd = o.modifiers.new("Solidify", "SOLIDIFY")
                        sd.thickness = 0.0028
                        sd.offset = 0.0
                        ss = o.modifiers.new("Subsurf", "SUBSURF")
                        ss.levels, ss.render_levels = 1, 1
                link_to(o, c)
                o.name = "V3 " + o.name if not o.name.startswith("V3 ") else o.name
                keep.add(o.name)
        # an empty that bounds the reclining figure's hands (for the close crop)
        if "Reclining actor" in figs:
            P = figs["Reclining actor"]["poser"]
            pts = []
            for side in ("L", "R"):
                for b in ("wrist.", "finger3-3.", "finger1-3.", "finger5-3."):
                    pts.append(P.head(b + side))
                    pts.append(P.tail(b + side))
            lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            hm = bpy.data.meshes.new("V3 Reclining actor hands")
            hm.from_pydata([(x, y, z) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)], [], [])
            hob = bpy.data.objects.new("V3 Reclining actor hands", hm)
            hob.hide_render = True
            get_coll("V3 Reclining actor (v3)", top).objects.link(hob)
            keep.add(hob.name)
        for o in list(bpy.data.objects):
            if o.name not in keep:
                bpy.data.objects.remove(o)
        for c in list(bpy.data.collections):
            if c != top and not c.name.endswith("(v3)"):
                bpy.data.collections.remove(c)
        bpy.data.orphans_purge(do_recursive=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "figures_unpacked.blend"))
        try:
            bpy.ops.file.pack_all()
        except Exception as e:
            print("pack failed", e)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "figures.blend"), compress=True)
        print("FIGURES SAVED %.1fs" % (time.time() - t0))
        # previews of the final figures with the couch for context
        with bpy.data.libraries.load(os.path.join(work, "scene_ctx.blend") if os.path.exists(os.path.join(work, "scene_ctx.blend")) else os.path.join(work, "robes.blend"), link=False) as (src, dst):
            dst.objects = [n for n in CONTEXT_OBJECTS if n in src.objects]
        for o in dst.objects:
            if o is not None:
                bpy.context.scene.collection.objects.link(o)
        previews(work, "final_", views, hide_ref=False)


# =============================================================================
# compose (plain Python 3 with Pillow): side-by-side sheets with labels
# =============================================================================
LABEL_A = "Current"
LABEL_B = "Option: v3 figures"
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
    for tag in ("tableau", "cutaway", "crop"):
        pa, pb = os.path.join(rd, "A_%s.png" % tag), os.path.join(rd, "B_%s.png" % tag)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            continue
        a, b = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
        size = 26 if a.width <= 1400 else int(26 * a.width / 1280 * 0.8)
        _label(a, LABEL_A, size)
        _label(b, LABEL_B, size)
        gap = 8
        im = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height)), (255, 255, 255))
        im.paste(a, (0, 0))
        im.paste(b, (a.width + gap, 0))
        name = "compare_%s" % tag
        im.save(os.path.join(cd, name + ".png"))
        outs.append((name, im))
        bb = Image.open(pb).convert("RGB")
        _label(bb, LABEL_B, size)
        outs.append(("v3_%s" % tag, bb))
    repo = opts.get("repo-out")
    if repo:
        os.makedirs(repo, exist_ok=True)
        for name, im in outs:
            path = os.path.join(repo, name + ".jpg")
            q = 93
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
    extra = ["--assets", opts["assets"]] if opts.get("assets") else []
    subprocess.run([blender, "-b", "--python-exit-code", "1", "-P", me, "--", "build", "--scene", scene, "--work", work] + extra,
                   env=env, check=True)
    subprocess.run([blender, "-b", scene, "--python-exit-code", "1", "-P", me, "--", "render", "--work", work,
                    "--samples", str(opts.get("samples", 64)), "--only", "AB"], check=True)
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
    elif MODE == "paint-patterns":
        out = paint_patterns(OPTS["texdir"])
        with open(os.path.join(OPTS["texdir"], "patterns.json"), "w") as f:
            json.dump(out, f, indent=1)
    elif MODE == "paint-mask":
        with open(OPTS["params"]) as f:
            prm = json.load(f)
        stem = OPTS["params"][:-len("_mask.json")]
        paint_mask_texture(prm["name"], prm["ms"], prm["land"], stem + "_azgrid.npz", stem + "_mask.png")
