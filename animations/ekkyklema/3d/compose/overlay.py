"""Composite the 'prompt v2' HUD, evidence gauge, breadcrumb outline, grain and vignette.

    python3 -I overlay.py IN.png OUT.png SPEC [MASK.png]

SPEC is one of the keys in SPECS below.
"""
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = sys.argv[0].rsplit("/", 1)[0]
INTER = HERE + "/fonts/Inter.ttf"
DIDOT = HERE + "/fonts/GFSDidot.ttf"
INK = (29, 26, 23)
SKY = (244, 239, 230)
ACCENT = (47, 93, 115)
CLAY = (200, 116, 60)

SPECS = {
    "rollout": dict(counter="06 / 10", name="THE ROLL-OUT",
                    fact=[("ekkyklein ", "it"), ("ἐκκυκλεῖν", "gr"), ("  “to roll out”", "rg")],
                    sub="“Get rolled out!” cries Dikaiopolis to Euripides",
                    cite="Ar. Acharnians 408 · 425 BC", level=1,
                    note="Word: attested.\nWheels: inferred.", crumb="next: the tableau", box=(530, 400, 780, 480)),
    "tableau": dict(counter="07 / 10", name="THE TABLEAU",
                    fact=[("“No time to come down.”", "rg")],
                    sub="Euripides, rolled out, stays on the platform",
                    cite="Ar. Acharnians 409 · couch and pose: our reconstruction (R5)", level=2,
                    note="Couch and pose:\nour choice (R5).", crumb=None, card_x=470),
}


def font(path, size, weight=None):
    f = ImageFont.truetype(path, size)
    if weight is not None:
        try:
            f.set_variation_by_axes([min(max(size, 14), 32), weight])
        except Exception:
            pass
    return f


def vignette(img, strength=0.36):
    w, h = img.size
    mw, mh = w // 8, h // 8
    m = Image.new("L", (mw, mh), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((-0.03 * mw, -0.06 * mh, 1.03 * mw, 1.06 * mh), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(mw // 7)).resize((w, h), Image.BICUBIC)
    dark = Image.eval(img, lambda v: int(v * (1 - strength)))
    return Image.composite(img, dark, m)


def grain(img, amount=0.02, seed=7):
    w, h = img.size
    rnd = random.Random(seed)
    n = Image.frombytes("L", (w, h), bytes(rnd.randint(0, 255) for _ in range(w * h)))
    n = n.filter(ImageFilter.GaussianBlur(0.6))
    n = Image.merge("RGB", (n, n, n))
    a = int(255 * amount * 2.2)
    return ImageChops.add(ImageChops.subtract(img, Image.new("RGB", img.size, (a // 2,) * 3)),
                          Image.eval(n, lambda v: v * a // 255))


def outline(img, mask_path, box, color=ACCENT):
    m = Image.open(mask_path).convert("RGBA").split()[-1].resize(img.size)
    m = m.point(lambda v: 255 if v > 90 else 0)
    keep = Image.new("L", img.size, 0)
    ImageDraw.Draw(keep).rectangle(box, fill=255)
    m = ImageChops.multiply(m, keep)            # the platform only (the mask also caught scattered shrubs)
    edge = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m)
    glow = edge.filter(ImageFilter.GaussianBlur(2.5))
    img = Image.composite(Image.new("RGB", img.size, color), img, glow.point(lambda v: min(255, v * 2) * 0.55))
    return Image.composite(Image.new("RGB", img.size, color), img, edge.point(lambda v: int(v * 0.9))), m


def hud(img, s):
    w, h = img.size
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    f_cnt, f_name = font(INTER, 15, 600), font(INTER, 34, 750)
    f_fact, f_it, f_gr = font(INTER, 21, 500), font(DIDOT, 23), font(DIDOT, 23)
    f_sub, f_cite, f_g = font(INTER, 15, 450), font(INTER, 13, 500), font(INTER, 11, 650)
    f_note = font(INTER, 11, 450)
    # chapter card, top left
    x0, y0 = s.get("card_x", 36), 30
    widths = []
    for txt, kind in s["fact"]:
        ff = f_it if kind in ("it", "gr") else f_fact
        widths.append(d.textlength(txt, font=ff))
    card_w = max(sum(widths), d.textlength(s["name"], font=f_name), d.textlength(s["sub"], font=f_sub)) + 40
    d.rounded_rectangle((x0, y0, x0 + card_w, y0 + 142), 10, fill=SKY + (215,))
    d.text((x0 + 20, y0 + 16), s["counter"], font=f_cnt, fill=CLAY)
    d.text((x0 + 20, y0 + 36), s["name"], font=f_name, fill=INK)
    x = x0 + 20
    for (txt, kind), tw in zip(s["fact"], widths):
        ff = f_it if kind in ("it", "gr") else f_fact
        d.text((x, y0 + 84 - (3 if ff is not f_fact else 0)), txt, font=ff, fill=INK)
        x += tw
    d.text((x0 + 20, y0 + 114), s["sub"], font=f_sub, fill=(74, 67, 60))
    # citation, bottom left
    d.rounded_rectangle((x0, h - 52, x0 + d.textlength(s["cite"], font=f_cite) + 24, h - 24), 7, fill=SKY + (190,))
    d.text((x0 + 12, h - 46), s["cite"], font=f_cite, fill=INK)
    # evidence gauge, right edge
    gx, gy0, gy1 = w - 44, 236, 436
    d.rounded_rectangle((gx - 112, gy0 - 42, w - 16, gy1 + 66), 9, fill=SKY + (175,))
    d.text((gx - 100, gy0 - 32), "HOW SURE?", font=f_g, fill=(74, 67, 60))
    d.line((gx, gy0, gx, gy1), fill=INK + (255,), width=2)
    labels = [("ATTESTED", "ancient text"), ("INFERRED", "scholars"), ("OUR CHOICE", "reconstruction")]
    for i, (lab, sub) in enumerate(labels):
        y = gy0 + i * (gy1 - gy0) // 2
        d.line((gx - 8, y, gx + 8, y), fill=INK + (255,), width=2)
        tw = d.textlength(lab, font=f_g)
        d.text((gx - 16 - tw, y - 15), lab, font=f_g, fill=INK)
        tw2 = d.textlength(sub, font=f_note)
        d.text((gx - 16 - tw2, y + 1), sub, font=f_note, fill=(110, 100, 90))
    my = gy0 + s["level"] * (gy1 - gy0) // 2
    d.polygon([(gx + 6, my), (gx + 22, my - 9), (gx + 22, my + 9)], fill=CLAY + (255,))
    d.ellipse((gx - 6, my - 6, gx + 6, my + 6), fill=CLAY + (255,))
    ny = gy1 + 20
    for line in s["note"].split("\n"):
        d.text((gx - 100, ny), line, font=f_note, fill=INK)
        ny += 14
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def main():
    src, dst, key = sys.argv[1], sys.argv[2], sys.argv[3]
    s = SPECS[key]
    img = Image.open(src).convert("RGB")
    if len(sys.argv) > 4 and s["crumb"]:
        img, m = outline(img, sys.argv[4], s["box"])
        bbox = m.getbbox()
        if bbox:
            d = ImageDraw.Draw(img)
            f = font(INTER, 14, 600)
            tw = d.textlength(s["crumb"], font=f)
            cx = (bbox[0] + bbox[2]) // 2
            d.rounded_rectangle((cx - tw / 2 - 8, bbox[3] + 10, cx + tw / 2 + 8, bbox[3] + 34), 6, fill=ACCENT)
            d.text((cx - tw / 2, bbox[3] + 14), s["crumb"], font=f, fill=SKY)
    # finish: lift the milky haze a little (deeper blacks, a touch more contrast and colour)
    img = img.point(lambda v: max(0, min(255, int((v - 10) * 1.06))))
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.08)
    img = vignette(img)
    img = grain(img)
    img = hud(img, s)
    img.save(dst, quality=90)


main()
