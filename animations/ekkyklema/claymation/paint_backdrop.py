#!/usr/bin/env python3
"""Paint the scenic backdrop for the claymation set: a stretched-canvas cyclorama with a
late-afternoon sky, the Hymettos ridge, a nearer olive-and-maquis hillside, all in visible
brush strokes (gouache / scene-painter style), so it reads as a painted flat, not a photo.

    python3 paint_backdrop.py OUT.png [--w 4096] [--seed 7]

The image maps onto the curved backdrop in metres (see clay_build.py, BACKDROP_*):
x spans BACKDROP_ARC metres of arc, y spans 0..BACKDROP_H metres from the floor up.
Horizon/hill heights are given in metres so the build and the painting agree.
"""
import math
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ARC_M = 64.0        # metres of arc covered by the image width
H_M = 20.0          # metres covered by the image height (floor = 0)


def srgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def fbm1(x, seed, octaves=5):
    """1-D fractal value noise, x array in metres"""
    rng = np.random.RandomState(seed)
    out = np.zeros_like(x, dtype=float)
    amp, freq = 1.0, 1.0 / 14.0
    for _ in range(octaves):
        n = int(x.max() * freq) + 4
        knots = rng.rand(n)
        xi = x * freq
        i0 = np.floor(xi).astype(int)
        f = xi - i0
        f = f * f * (3 - 2 * f)
        out += amp * (knots[i0] * (1 - f) + knots[i0 + 1] * f)
        amp *= 0.5
        freq *= 2.1
    return out


def paint(out, W=4096, seed=7):
    random.seed(seed)
    np.random.seed(seed)
    H = int(W * H_M / ARC_M)
    ppm = W / ARC_M                         # pixels per metre
    xs = np.arange(W) / ppm                 # metres

    def Y(z_m):                             # metres above floor -> image row
        return H - 1 - z_m * ppm

    # ---- profiles (metres above the floor) -------------------------------------------------
    # far ridge (Hymettos-like, long and flat-topped), mid hills, near hillside
    far = 6.3 + 2.4 * fbm1(xs + 3.0, seed + 1, 4) - 0.8 * np.cos((xs - ARC_M * 0.62) / ARC_M * 2 * math.pi)
    mid = 4.6 + 1.5 * fbm1(xs + 40.0, seed + 2, 5)
    near = 2.6 + 1.8 * fbm1(xs + 90.0, seed + 3, 5)

    sky_top, sky_mid, sky_hor = srgb("#5f90c0"), srgb("#93b6d3"), srgb("#eccb9e")
    far_col, far_lit = srgb("#8f8fae"), srgb("#b7a9b3")
    mid_col, mid_lit = srgb("#7f8a7a"), srgb("#a9a58a")
    near_col, near_lit = srgb("#7d7347"), srgb("#bb9e66")

    img = np.zeros((H, W, 3), float)
    rows = np.arange(H)[:, None]
    z = (H - 1 - rows) / ppm                # metres per row
    # sky gradient
    t = np.clip((z - 5.0) / (H_M - 5.0), 0, 1) ** 0.65
    sky = np.where(t < 0.45, 0, 1)
    c1 = np.array(sky_hor)[None, None] * (1 - np.clip(t / 0.45, 0, 1))[..., None] + np.array(sky_mid)[None, None] * np.clip(t / 0.45, 0, 1)[..., None]
    c2 = np.array(sky_mid)[None, None] * (1 - np.clip((t - 0.45) / 0.55, 0, 1))[..., None] + np.array(sky_top)[None, None] * np.clip((t - 0.45) / 0.55, 0, 1)[..., None]
    img[:] = np.where(sky[..., None] == 0, c1, c2) * np.ones((1, W, 1))

    def band(profile, base, lit, below=None):
        zz = z * np.ones((1, W))
        m = zz < profile[None, :]
        # lit on the upper part of each hill, darker toward the base: aerial shading
        depth = np.clip((profile[None, :] - zz) / 2.5, 0, 1)
        col = np.array(lit)[None, None] * (1 - depth[..., None]) + np.array(base)[None, None] * depth[..., None]
        img[m] = col[m]

    band(far, far_col, far_lit)
    band(mid, mid_col, mid_lit)
    band(near, near_col, near_lit)

    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(ppm * 0.25))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")

    def stroke(x, y, length, width, ang, col, alpha):
        dx, dy = math.cos(ang) * length / 2, math.sin(ang) * length / 2
        d.line([(x - dx, y - dy), (x + dx, y + dy)], fill=(*[int(max(0, min(255, c))) for c in col], int(alpha)),
               width=max(1, int(width)))
        r = width / 2
        for ex, ey in ((x - dx, y - dy), (x + dx, y + dy)):
            d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=(*[int(max(0, min(255, c))) for c in col], int(alpha)))

    base = np.asarray(canvas).astype(float)

    def sample(x, y):
        xi = int(min(W - 1, max(0, x)))
        yi = int(min(H - 1, max(0, y)))
        return base[yi, xi]

    # ---- sky: long, slightly diagonal scumbled strokes -------------------------------------
    for _ in range(int(9000 * W / 4096)):
        x = random.uniform(0, W)
        y = random.uniform(0, Y(6.5))
        c = sample(x, y) + np.random.normal(0, 7, 3) + (6, 4, -2)
        stroke(x, y, ppm * random.uniform(0.6, 1.8), ppm * random.uniform(0.12, 0.28),
               random.gauss(0.0, 0.12), c, random.uniform(70, 150))
    # clouds: soft warm-white dabs in a few drifting clusters
    for cx_m, cz_m, sx, sz in ((9, 15.5, 7, 1.4), (24, 17.5, 9, 1.2), (41, 14.5, 6, 1.1), (55, 16.8, 8, 1.3), (33, 12.6, 4, 0.7)):
        for _ in range(int(450 * sx / 7)):
            u = random.gauss(0, 0.45)
            v = random.gauss(0, 0.35)
            x = (cx_m + u * sx) * ppm
            zz = cz_m + v * sz + 0.6 * sz * (1 - min(1, abs(u)))
            y = Y(zz)
            lit = 1.0 if v > -0.2 else 0.85
            c = np.array(srgb("#fbf1e2")) * lit + np.random.normal(0, 5, 3)
            if v < -0.35:
                c = lerp(c, srgb("#b9b4c4"), 0.5)
            stroke(x, y, ppm * random.uniform(0.25, 0.6), ppm * random.uniform(0.25, 0.45),
                   random.gauss(0.0, 0.35), c, random.uniform(60, 130))
    # ---- hills: strokes follow the slope ---------------------------------------------------
    def hill_strokes(profile, n, lo, jitter, tint, wmin, wmax):
        for _ in range(n):
            xi = random.randrange(W)
            top = profile[xi]
            zz = random.uniform(lo, top)
            x, y = xi, Y(zz)
            i0, i1 = max(0, xi - 20), min(W - 1, xi + 20)
            slope = math.atan2(-(profile[i1] - profile[i0]) * ppm, i1 - i0)
            c = sample(x, y) + np.random.normal(0, jitter, 3) + tint
            stroke(x, y, ppm * random.uniform(0.5, 1.3), ppm * random.uniform(wmin, wmax),
                   slope + random.gauss(0, 0.25), c, random.uniform(90, 170))

    hill_strokes(far, int(7000 * W / 4096), 4.0, 6, (2, 0, 4), 0.12, 0.26)
    hill_strokes(mid, int(7000 * W / 4096), 2.5, 9, (0, 2, 0), 0.14, 0.3)
    hill_strokes(near, int(9000 * W / 4096), 0.0, 12, (2, 1, -2), 0.16, 0.34)
    # ---- olive trees and maquis: dark green dabs with a warm lit edge -----------------------
    for prof, n, sc, dark in ((mid, 70, 0.45, srgb("#56604a")), (near, 120, 0.8, srgb("#46502f"))):
        for _ in range(n):
            xi = random.randrange(W)
            zz = random.uniform(max(0.3, prof[xi] - 2.6), prof[xi] - 0.15)
            cx, cy = xi, Y(zz)
            r = ppm * sc * random.uniform(0.35, 0.8)
            for k in range(9):
                ox, oy = random.gauss(0, r * 0.5), random.gauss(0, r * 0.35)
                c = np.array(dark) + np.random.normal(0, 6, 3)
                stroke(cx + ox, cy + oy, r * 0.7, r * 0.5, random.uniform(0, math.pi), c, 190)
            for k in range(3):  # light from the left (the key light side)
                ox, oy = -r * 0.35 + random.gauss(0, r * 0.15), -r * 0.25 + random.gauss(0, r * 0.15)
                c = np.array(srgb("#93975f")) + np.random.normal(0, 6, 3)
                stroke(cx + ox, cy + oy, r * 0.45, r * 0.3, random.uniform(0, math.pi), c, 150)
    # a few pale rock / earth scrapes on the near hill
    for _ in range(220):
        xi = random.randrange(W)
        zz = random.uniform(0.2, near[xi] - 0.3)
        c = np.array(srgb("#c9ad80")) + np.random.normal(0, 10, 3)
        stroke(xi, Y(zz), ppm * random.uniform(0.25, 0.5), ppm * random.uniform(0.14, 0.24),
               random.gauss(0, 0.3), c, 120)

    canvas = Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")
    # slight paint grain
    arr = np.asarray(canvas).astype(float)
    arr += np.random.normal(0, 2.0, arr.shape)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(out, quality=95)
    print("backdrop", out, W, H)


if __name__ == "__main__":
    a = sys.argv[1:]
    out = a[0]
    W = int(a[a.index("--w") + 1]) if "--w" in a else 4096
    seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 7
    paint(out, W, seed)
