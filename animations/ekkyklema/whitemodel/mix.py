"""Sound design for the white-model ekkyklema sample -> mix.wav (no narration, no score: a room, a projector,
the machinery, and mallets/bowed vibraphone for light, after lemo-opuscar's white-model sound palette).

usage: LIB=<lemo-opuscar clone> <LIB>/.venv/bin/python mix.py <events.json> <out.wav>
events.json is window.EV exported by `node render.mjs --events` (every cue at its frame time).
Uses the library's core/audio/sfx.py (procedural foley) and core/audio/sampler.py with VCSL (CC0) samples.
"""
import os, sys, json
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt

LIB = os.environ.get('LIB') or os.path.expanduser('~/lemo-opuscar')
sys.path.insert(0, LIB)
from core.audio import sfx as X
from core.audio import sampler as S

SR = X.SR
EVJ = json.load(open(sys.argv[1]))
OUTF = sys.argv[2]
DUR, EV = EVJ['dur'], EVJ['ev']
E = {e['type']: e for e in EV}
N = int((DUR + 2) * SR)
BED, FX, MUS = (np.zeros((N, 2), np.float32) for _ in range(3))
rng = np.random.default_rng(23)
S.seed(5)


def sos(kind, f, o=2): return butter(o, f, kind, fs=SR, output='sos')
def lpf(x, f, o=2): return sosfilt(sos('low', f, o), x, axis=0)
def hpf(x, f, o=2): return sosfilt(sos('high', f, o), x, axis=0)
def bpf(x, a, b, o=2): return sosfilt(sos('band', [a, b], o), x, axis=0)
def tv(d): return np.arange(int(d * SR)) / SR
def put(buf, x, at, g=1.0, pan=0.0): X.add(buf, np.asarray(x, np.float32), at, g, pan)


# ------------------------------------------------------------------ the room and the projector
def room_tone(d):
    x = lpf(np.cumsum(rng.standard_normal(len(tv(d)))) * .002, 240, 2); x -= lpf(x, 20)
    return x / (np.abs(x).max() + 1e-9)

def fan(d, f0=117):
    t = tv(d)
    hum = sum(np.sin(2 * np.pi * f0 * k * t + k) / k ** 1.5 for k in range(1, 6)) * .22
    air = bpf(rng.standard_normal(len(t)), 300, 2200) * .5
    return hum * .4 + air

def relay(v=1.0):
    a, b = X.clack(.7, v), X.thump(.5 * v, 60)
    y = np.zeros(max(len(a), len(b))); y[:len(a)] += a; y[:len(b)] += b * .7
    return y

def lamp(v=1.0):
    t = tv(1.3)
    zap = hpf(rng.standard_normal(len(t)), 2600) * np.exp(-t / .012) * .55
    whump = np.sin(2 * np.pi * (54 + 30 * np.exp(-t / .05)) * t) * np.exp(-t / .3)
    buzz = np.sin(2 * np.pi * 100 * t) * (1 - np.exp(-t / .08)) * np.exp(-t / .45) * .1
    flick = 1 + .35 * np.sin(2 * np.pi * 15 * t) * np.exp(-t / .2)
    return (zap + whump + buzz) * flick * v

def swell(d, f0, f1, v=1.0, q=.5):
    """the air of a light wash: band noise whose centre slides f0 -> f1"""
    t = tv(d); x = rng.standard_normal(len(t)); out = np.zeros_like(x); blk = 2048
    for i in range(0, len(x), blk):
        fc = f0 * (f1 / f0) ** (i / len(x)); seg = x[max(0, i - 512):i + blk]
        out[i:i + blk] = bpf(seg, fc * (1 - q / 2), fc * (1 + q / 2))[-len(x[i:i + blk]):]
    return out * np.sin(np.pi * np.clip(t / d, 0, 1)) ** 1.5 * v


# ------------------------------------------------------------------ the machinery
def door_creak(d):
    """two heavy leaves turning on their pins: slow, low wooden groans (grains of sfx.creak, pitched down)"""
    out = np.zeros(int((d + .5) * SR))
    t0 = 0.0
    while t0 < d:
        g = X.creak(1.0)
        g = np.interp(np.arange(0, len(g), .62), np.arange(len(g)), g)        # a fifth or so lower, longer
        k = np.sin(np.pi * np.clip(t0 / d, 0, 1))                              # loudest mid-swing
        s = int(t0 * SR); e = min(len(out), s + len(g)); out[s:e] += g[:e - s] * (.35 + .65 * k) * (.7 + .3 * rng.random())
        t0 += .16 + .12 * rng.random()
    return lpf(out, 2600)

def wheel_roll(ev):
    """2.93 m in 4 s: a low rumble that follows the platform's speed (quintic ease, so it swells and dies away
    with no bump), and one soft knock each time a plank seam of the solid wheels meets the ground"""
    d, dist, r = ev['dur'], ev['dist'], ev['wheel_r']
    t = tv(d + .3); u = np.clip(t / d, 0, 1)
    speed = 30 * u ** 2 * (1 - u) ** 2                                         # d/du of the quintic, peak 1.875
    sp = speed / speed.max()
    rum = lpf(np.cumsum(rng.standard_normal(len(t))) * .01, 220, 2); rum -= lpf(rum, 25, 2)
    rum = rum / (np.abs(rum).max() + 1e-9)
    grit = bpf(rng.standard_normal(len(t)), 500, 1800) * .12
    body = (rum + grit) * sp ** 1.2
    out = np.zeros(len(t) + SR)
    out[:len(t)] += body
    # seams: 3 planks -> 6 seam crossings per revolution (each seam meets the ground once per turn, both ends)
    s_of_u = lambda x: x ** 3 * (x * (x * 6 - 15) + 10)
    per = 2 * np.pi * r / 6
    n = int(dist / per)
    for k in range(1, n + 1):
        target = k * per / dist
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if s_of_u(mid) < target else (lo, mid)
        tk = lo * d; v = .25 + .75 * np.interp(lo, u, sp)
        kn = X.thump(1.0, 95 + 20 * rng.random())[:int(.12 * SR)] * .5
        s = int(tk * SR); out[s:s + len(kn)] += kn * v * .5
    return out

def tick(p=1.0, v=1.0):
    t = tv(.07)
    return (np.sin(2 * np.pi * 2300 * p * t) * np.exp(-t / .007) + hpf(rng.standard_normal(len(t)), 3000) * np.exp(-t / .003) * .3) * v


def lufs(x):
    import subprocess, tempfile, re
    f = os.path.join(tempfile.mkdtemp(), 'm.wav'); sf.write(f, x.astype(np.float32), SR)
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', f, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', out)[-1])


# ------------------------------------------------------------------ build
def main():
    # beds: room tone throughout; projector fan idle, up with the lamp, settling with the lights
    put(BED, room_tone(DUR + 2) * .5, 0, 1.0, -.1); put(BED, room_tone(DUR + 2) * .5, 0, 1.0, .1)
    t = tv(DUR + 2); fa = fan(DUR + 2)
    lamp_t, lights_t = E['lamp']['t'], E['lights']['t']
    lvl = .22 + .78 * np.clip((t - lamp_t) / .4, 0, 1) - .45 * np.clip((t - lights_t) / 1.2, 0, 1)
    put(BED, fa * lvl, 0, .55, -.2)

    m = []   # score-like events for the sampler (VCSL, CC0): mallets and bowed vibraphone for light
    for e in EV:
        ty, t0 = e['type'], e['t']
        if ty == 'relay': put(FX, relay(1.0), t0, .9, -.3)
        elif ty == 'lamp':
            put(FX, lamp(1.0), t0, .85, .15)
            m.append(dict(t=t0 + .25, inst='vibraphone_bowed', pitch='D5', dur=3.4, vel=.32, pan=-.2, attack=.6, release=1.2))
        elif ty == 'wash': put(FX, swell(1.0, 400, 2400, 1.0, .6), t0 - .1, .35, 0)
        elif ty == 'tick': put(FX, tick(1.0, .8), t0, .5, .2)
        elif ty == 'tickEnd':   # each dimension line lands on a glockenspiel note (width A6, height D7)
            n_end = sum(1 for q in m if q.get('tag') == 'dim')
            m.append(dict(t=t0, inst='glockenspiel', pitch=['A6', 'D7'][n_end % 2], dur=.8, vel=.38, pan=.3, tag='dim'))
        elif ty == 'doors':
            put(FX, door_creak(e['dur']), t0 + .05, .5, -.1)
            m.append(dict(t=t0, inst='vibraphone_bowed', pitch='A4', dur=e['dur'] + 1.0, vel=.26, pan=.25, attack=.8, release=1.0))
        elif ty == 'doorStop': put(FX, X.thump(.55, 75), t0, .45, 0)
        elif ty == 'pick': m.append(dict(t=t0, inst='marimba', pitch='D4', dur=.6, vel=.45, pan=-.1))
        elif ty == 'lane':
            put(FX, swell(.9, 900, 3600, 1.0, .5), t0 - .1, .3, .1)
            m.append(dict(t=t0 + .45, inst='glockenspiel', pitch='E6', dur=.8, vel=.3, pan=.2))
        elif ty == 'roll':
            put(FX, wheel_roll(e), t0, .95, 0)
            m.append(dict(t=t0, inst='vibraphone_bowed', pitch='F#4', dur=e['dur'] + .4, vel=.24, pan=-.25, attack=1.2, release=1.2))
            m.append(dict(t=t0 + .6, inst='vibraphone_bowed', pitch='D5', dur=e['dur'] - .2, vel=.2, pan=.25, attack=1.5, release=1.4))
        elif ty == 'land':
            put(FX, X.thump(1.0, 58), t0, 1.1, 0); put(FX, X.thump(.6, 92), t0 + .01, .5, 0)
            m.append(dict(t=t0, inst='tubular_bells', pitch='D5', dur=3.0, vel=.55, pan=0))
        elif ty == 'layer': put(FX, swell(.8, 1200, 4200, 1.0, .5), t0 - .15, .28, -.1)
        elif ty == 'pin':
            p = {'A': 'D6', 'I': 'F#6', 'R': 'A6'}[e['code']]
            m.append(dict(t=t0, inst='vibraphone', pitch=p, dur=1.6, vel=.5, pan={'A': .2, 'I': -.3, 'R': -.1}[e['code']]))
            m.append(dict(t=t0, inst='hand_chimes', pitch=p.replace('6', '5'), dur=1.6, vel=.32, pan=0))
        elif ty == 'lights':
            put(FX, relay(.8), t0, .7, -.4); put(FX, relay(.6), t0 + .13, .5, .4)
            m.append(dict(t=t0 + .2, inst='vibraphone_bowed', pitch='D4', dur=DUR - t0 - .4, vel=.3, pan=-.2, attack=.9, release=1.0))
            m.append(dict(t=t0 + .5, inst='vibraphone_bowed', pitch='A4', dur=DUR - t0 - .7, vel=.26, pan=.2, attack=1.0, release=1.0))
            m.append(dict(t=t0 + .9, inst='vibraphone_bowed', pitch='F#5', dur=DUR - t0 - 1.1, vel=.2, pan=.0, attack=1.2, release=1.0))
    y = S.render(m, dur=N / SR, master=False); MUS[:len(y)] += y[:N]

    mus = S.room(MUS, .55, .24); fx = S.room(FX, .3, .12); bed = BED
    # near-silence before the roll (the first sound after it is the wheels): dip beds and music, 5.55 -> roll start
    r0 = E['roll']['t']
    g = np.ones(N); i0, i1 = int((r0 - .3) * SR), int(r0 * SR); g[i0:i1] = np.linspace(1, .35, i1 - i0); g[i1:i1 + int(.6 * SR)] = np.linspace(.35, 1, int(.6 * SR))
    mix = mus * .55 * g[:, None] + fx * .8 + bed * .3 * (.5 + .5 * g)[:, None]
    mix = hpf(mix, 35, 2)
    mix = mix[:int(DUR * SR)]
    f = int(.6 * SR); mix[-f:] *= np.linspace(1, 0, f)[:, None] ** 1.5
    mix /= np.abs(mix).max() / .7
    # keep the crest (peak vs integrated loudness) small enough that mastering to -14 LUFS stays under -1.2 dBTP:
    # limit the transients (lamp strike, relays, ticks) to 10 dB above the integrated loudness (look-ahead limiter, sfx.py)
    for _ in range(3):
        I = lufs(mix); ceil = 10 ** ((I + 10.0) / 20)
        if np.abs(mix).max() <= ceil: break
        mix = np.stack([X.limit(mix[:, c], ceil, .004) for c in range(2)], 1)
    print(f'integrated {lufs(mix):.1f} LUFS, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS')
    sf.write(OUTF, mix.astype(np.float32), SR)
    print('mix written', OUTF, f'{DUR:.2f} s; instruments:', sorted({e["inst"] for e in m}))
    print('credits:', S.credits(sorted({e['inst'] for e in m})))


if __name__ == '__main__':
    main()
