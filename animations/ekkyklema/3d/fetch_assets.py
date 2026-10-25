#!/usr/bin/env python3
"""Download the CC0 assets used by build_scene.py into a local cache.

Every asset comes from Poly Haven (https://polyhaven.com), licence CC0 1.0.
The list here must match ASSETS.md. Files are checked against the MD5 sums
published by the Poly Haven API, and existing good files are not re-fetched.

Usage:
    python3 fetch_assets.py [CACHE_DIR]

CACHE_DIR defaults to $EKK_ASSETS, or ./assets_cache next to this script.
Keep the cache out of git: it is about 120 MB.
"""
import hashlib
import json
import os
import sys
import urllib.request

API = "https://api.polyhaven.com/files/"
UA = {"User-Agent": "theatre-animator-fetch/1.0 (CC0 asset cache)"}

# texture id -> maps to fetch (Poly Haven map keys), all 2k JPG
TEXTURES = {
    "weathered_planks":       ["Diffuse", "nor_gl", "Rough"],   # facade boards, roof, door leaves
    "rough_wood":             ["Diffuse", "nor_gl", "Rough"],   # posts, beams, platform frame, wheels
    "weathered_brown_planks": ["Diffuse", "nor_gl", "Rough"],   # platform deck
    "fine_grained_wood":      ["Diffuse", "nor_gl", "Rough"],   # couch, stool
    "dirt":                   ["Diffuse", "nor_gl", "Rough"],   # beaten-earth orchestra
    "dry_ground_rocks":       ["Diffuse", "nor_gl", "Rough"],   # hillside soil
    "sparse_grass":           ["Diffuse", "nor_gl", "Rough"],   # spring grass on the slopes
    "rock_wall_02":           ["Diffuse", "nor_gl", "Rough"],   # Acropolis rock, outcrops
    "rough_linen":            ["Diffuse", "nor_gl", "Rough"],   # cloth weave (tinted per garment)
}
# model id -> glTF at 1k (glTF rather than .blend: pure data, no embedded scripts)
MODELS = ["wild_rooibos_bush", "searsia_lucida", "searsia_burchellii"]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest, want_md5=None):
    if os.path.exists(dest) and (want_md5 is None or md5(dest) == want_md5):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    if want_md5 and md5(tmp) != want_md5:
        os.remove(tmp)
        raise RuntimeError(f"MD5 mismatch for {url}")
    os.replace(tmp, dest)
    return True


def api(asset):
    with urllib.request.urlopen(urllib.request.Request(API + asset, headers=UA)) as r:
        return json.load(r)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cache = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EKK_ASSETS", os.path.join(here, "assets_cache"))
    n = 0
    for tex, maps in TEXTURES.items():
        files = api(tex)
        for m in maps:
            info = files[m]["2k"]["jpg"]
            dest = os.path.join(cache, "textures", tex, os.path.basename(info["url"]))
            n += fetch(info["url"], dest, info.get("md5"))
    for mod in MODELS:
        files = api(mod)
        g = files["gltf"]["1k"]["gltf"]
        root = os.path.join(cache, "models", mod)
        n += fetch(g["url"], os.path.join(root, os.path.basename(g["url"])), g.get("md5"))
        for rel, inc in g.get("include", {}).items():
            n += fetch(inc["url"], os.path.join(root, rel), inc.get("md5"))
        # the glTF points its alpha at the JPG diffuse (no alpha channel): fetch the alpha map
        a = files["Alpha"]["1k"]["png"]
        n += fetch(a["url"], os.path.join(root, "textures", os.path.basename(a["url"])), a.get("md5"))
    print(f"assets ready in {cache} ({n} files downloaded)")


if __name__ == "__main__":
    main()
