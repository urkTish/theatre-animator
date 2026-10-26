"""Contact sheet for the sample: key frames of the composite, the layers (plate / cast / matte) and look B.
usage: python tools/sheet.py <out folder (holds white/ and clay_stills/)> <contact_sheet.jpg>"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

OUT, DST = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(HERE, 'fonts', 'Inter.ttf')
f_t = ImageFont.truetype(FONT, 26); f_l = ImageFont.truetype(FONT, 17)
TW, TH, PAD, LAB = 384, 216, 8, 26
FPS = 24

def frame(layer, t):
    return os.path.join(OUT, 'white', layer, f'{round(t * FPS):04d}.png')

def tile(path, checker=False):
    im = Image.open(path)
    if im.mode == 'RGBA':
        bg = Image.new('RGBA', im.size, (0, 0, 0, 255)); d = ImageDraw.Draw(bg)
        s = 40
        for y in range(0, im.size[1], s):
            for x in range(0, im.size[0], s):
                if (x // s + y // s) % 2: d.rectangle([x, y, x + s - 1, y + s - 1], fill=(70, 70, 76, 255))
                else: d.rectangle([x, y, x + s - 1, y + s - 1], fill=(40, 40, 44, 255))
        bg.alpha_composite(im); im = bg
    return im.convert('RGB').resize((TW, TH), Image.LANCZOS)

rows = [
    ('Composite (look A: white maquettes)', [(frame('composite', t), f't = {t:.1f} s', False) for t in (0.5, 2.0, 3.6, 5.0, 6.6)]),
    ('', [(frame('composite', t), f't = {t:.1f} s', False) for t in (8.2, 9.8, 10.8, 12.0, 14.9)]),
    ('Layers at the same instants: plate / cast (alpha, over a checker) / matte', [
        (frame('plate', 8.2), 'plate  t = 8.2 s', False), (frame('cast_rgba', 8.2), 'cast  t = 8.2 s', True),
        (frame('plate', 14.9), 'plate  t = 14.9 s', False), (frame('cast_rgba', 14.9), 'cast  t = 14.9 s', True),
        (None, 'matte  t = 14.9 s', False)]),
    ('Look B: same cast file with clay stand-ins (examples/cast.clay.json), same plate and tracks', [
        (os.path.join(OUT, 'clay_stills', 'stills', f'composite_{t:.2f}.png'), f'look B  t = {t:.1f} s', False) for t in (3.5, 8.0, 11.5, 14.5)]),
]
W = 5 * TW + 6 * PAD
H = 60 + sum((34 if r[0] else 0) + TH + LAB + PAD for r in rows) + 10
S = Image.new('RGB', (W, H), (18, 19, 22)); d = ImageDraw.Draw(S)
d.text((PAD, 16), 'Ekkyklema · Projection on White Model · 15 s sample · key frames, layers and the look swap', font=f_t, fill=(236, 238, 242))
y = 60
for title, items in rows:
    if title:
        d.text((PAD, y + 6), title, font=f_l, fill=(170, 200, 220)); y += 34
    for i, (p, lab, chk) in enumerate(items):
        x = PAD + i * (TW + PAD)
        if p is None:   # matte: the cast alpha of the last cast frame
            a = Image.open(frame('cast_rgba', 14.9)).split()[-1].convert('RGB').resize((TW, TH), Image.LANCZOS); S.paste(a, (x, y))
        elif os.path.exists(p): S.paste(tile(p, chk), (x, y))
        d.text((x + 2, y + TH + 4), lab, font=f_l, fill=(220, 222, 226))
    y += TH + LAB + PAD
S.save(DST, quality=88)
print(DST, S.size)
