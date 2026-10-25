"""Stack labelled images into one comparison sheet.

    python3 -I compare.py OUT.jpg "TITLE" IMG1 "LABEL1" IMG2 "LABEL2" [...]
"""
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = sys.argv[0].rsplit("/", 1)[0]
INTER = HERE + "/fonts/Inter.ttf"


def font(size, weight):
    f = ImageFont.truetype(INTER, size)
    try:
        f.set_variation_by_axes([min(max(size, 14), 32), weight])
    except Exception:
        pass
    return f


out, title, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
pairs = [(rest[i], rest[i + 1]) for i in range(0, len(rest), 2)]
imgs = [Image.open(p).convert("RGB").resize((1280, 720)) for p, _ in pairs]
bar, head, gap = 44, 64, 16
H = head + sum(bar + im.height + gap for im in imgs)
sheet = Image.new("RGB", (1280 + 2 * gap, H), (244, 239, 230))
d = ImageDraw.Draw(sheet)
d.text((gap, 18), title, font=font(26, 700), fill=(29, 26, 23))
y = head
for (p, label), im in zip(pairs, imgs):
    d.text((gap, y + 10), label, font=font(20, 600), fill=(47, 93, 115) if label.startswith("Option") else (29, 26, 23))
    y += bar
    sheet.paste(im, (gap, y))
    y += im.height + gap
sheet.save(out, quality=88)
