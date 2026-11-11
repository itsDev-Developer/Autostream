"""Audio: procedural chiptune background music + sound effects, mixed live and fed to ffmpeg.

No downloads and no third-party packages: tracks are synthesised once (then cached on disk) with pure Python.
Drop your own mp3/wav/ogg files into --music-dir to use a playlist instead.
"""
from __future__ import annotations

import array
import glob
import logging
import math
import os
import random
import subprocess

log = logging.getLogger("audio")
SR = 22050                      # mono sample rate fed to ffmpeg (ffmpeg upsamples to 44.1 kHz stereo)
N_TBL = 1024
TRACK_VERSION = 3


def _tables():
    n = N_TBL
    return {
        "sine": [math.sin(2 * math.pi * i / n) for i in range(n)],
        "square": [1.0 if i < n / 2 else -1.0 for i in range(n)],
        "pulse": [1.0 if i < n * 0.25 else -1.0 for i in range(n)],
        "tri": [4 * abs(i / n - 0.5) - 1 for i in range(n)],
        "saw": [2 * i / n - 1 for i in range(n)],
    }


TABLES = _tables()
_ENV = {}


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def envelope(n, kind):
    key = (n, kind)
    if key not in _ENV:
        if kind == "pluck":
            a = max(1, int(0.004 * SR))
            _ENV[key] = [min(1.0, i / a) * math.exp(-3.2 * i / n) for i in range(n)]
        elif kind == "pad":
            a, r = max(1, int(n * 0.25)), max(1, int(n * 0.3))
            _ENV[key] = [min(1.0, i / a, (n - i) / r) for i in range(n)]
        else:  # sustain
            a, r = max(1, int(0.008 * SR)), max(1, int(0.05 * SR))
            _ENV[key] = [min(1.0, i / a, (n - i) / r) for i in range(n)]
    return _ENV[key]


def note(buf, start, dur, freq, wave, vol, kind="pluck"):
    a = int(start * SR)
    n = int(dur * SR)
    if n <= 0 or a >= len(buf):
        return
    n = min(n, len(buf) - a)
    tbl, inc, env = TABLES[wave], freq * N_TBL / SR, envelope(n, kind)
    seg = [tbl[int(i * inc) & 1023] * e * vol for i, e in zip(range(n), env)]
    buf[a:a + n] = [b + s for b, s in zip(buf[a:a + n], seg)]


def add(buf, start, samples, vol=1.0):
    a = int(start * SR)
    n = min(len(samples), len(buf) - a)
    if n > 0:
        buf[a:a + n] = [b + s * vol for b, s in zip(buf[a:a + n], samples)]


def _drums():
    rnd = random.Random(7)
    kick, ph = [], 0.0
    for i in range(int(0.17 * SR)):
        t = i / SR
        ph += 2 * math.pi * (46 + 125 * math.exp(-t * 30)) / SR
        kick.append(math.sin(ph) * math.exp(-t * 13))
    snare = [(rnd.uniform(-1, 1) * 0.8 + math.sin(2 * math.pi * 185 * i / SR) * 0.35) * math.exp(-i / SR * 20)
             for i in range(int(0.14 * SR))]
    noise = [rnd.uniform(-1, 1) for _ in range(int(0.05 * SR) + 1)]
    hat = [(noise[i] - noise[i - 1]) * 0.5 * math.exp(-i / SR * 75) for i in range(1, len(noise))]
    return kick, snare, hat


SPECS = {
    # bpm, chord roots (midi), chord kinds, melody scale, melody wave, arp wave, bass style
    "flappy": dict(bpm=126, roots=[60, 57, 53, 55], kinds="MmMM", scale=[0, 2, 4, 7, 9], lead="pulse", arp="tri",
                   bass="tri", style="bounce", key=72),
    "racing": dict(bpm=152, roots=[57, 53, 60, 55], kinds="mMMM", scale=[0, 3, 5, 7, 10], lead="saw", arp="pulse",
                   bass="saw", style="drive", key=69),
    "blocks": dict(bpm=112, roots=[62, 58, 65, 60], kinds="mMMM", scale=[0, 2, 3, 5, 7, 8, 10], lead="square",
                   arp="pulse", bass="saw", style="synth", key=74),
    "fight": dict(bpm=144, roots=[57, 57, 53, 55], kinds="mmMM", scale=[0, 3, 5, 7, 10], lead="saw", arp="pulse",
                  bass="saw", style="drive", key=69),
}
RHYTHMS = [[(0, 2), (2, 1), (3, 1), (4, 2), (6, 2)], [(0, 1), (1, 1), (2, 2), (4, 1), (5, 1), (6, 2)],
           [(0, 3), (3, 1), (4, 2), (6, 2)], [(0, 2), (2, 2), (4, 4)], [(0, 1), (2, 1), (3, 1), (4, 1), (6, 1), (7, 1)]]


def render_track(name, seed=1):
    sp, rng = SPECS[name], random.Random(seed)
    kick, snare, hat = _drums()
    step = 60.0 / sp["bpm"] / 2
    bars = 16
    loop_n = int(bars * 8 * step * SR)
    buf = [0.0] * (loop_n + int(1.2 * SR))
    style = sp["style"]
    for bar in range(bars):
        root, kind = sp["roots"][bar % 4], sp["kinds"][bar % 4]
        triad = [0, 3, 7] if kind == "m" else [0, 4, 7]
        for st in range(8):
            t = (bar * 8 + st) * step
            # drums
            if st in (0, 4) or (style == "drive" and st in (2, 6)):
                add(buf, t, kick, 0.6)
            if st in (2, 6):
                add(buf, t, snare, 0.26)
            add(buf, t, hat, 0.10 if st % 2 else 0.06)
            # bass
            if style == "bounce" and st in (0, 3, 4, 6):
                note(buf, t, step * 1.7, midi(root - 12 + (7 if st == 6 else 0)), sp["bass"], 0.30, "sustain")
            elif style == "drive":
                note(buf, t, step * 0.9, midi(root - 12 + (12 if st % 4 == 3 else 0)), sp["bass"], 0.24, "pluck")
            elif style == "synth" and st == 0:
                note(buf, t, step * 7.6, midi(root - 12), sp["bass"], 0.17, "pad")
                for iv in triad:
                    note(buf, t, step * 7.6, midi(root + iv), "tri", 0.05, "pad")
            # arpeggio
            if style == "synth" or st % 2 == 0 or style == "drive":
                idx = [0, 1, 2, 1][st % 4] if style != "synth" else [0, 1, 2, 1, 0, 2, 1, 2][st]
                note(buf, t, step * 0.9, midi(root + 12 + triad[idx]), sp["arp"], 0.10 if style != "synth" else 0.12, "pluck")
        # melody
        deg = rng.randrange(len(sp["scale"]))
        for off, ln in rng.choice(RHYTHMS):
            if rng.random() < 0.14:
                continue
            deg = max(0, min(len(sp["scale"]) * 2 - 1, deg + rng.choice([-2, -1, -1, 0, 1, 1, 2])))
            n = sp["key"] + sp["scale"][deg % len(sp["scale"])] + 12 * (deg // len(sp["scale"])) - 12 + (12 if bar >= 8 and rng.random() < 0.3 else 0)
            note(buf, (bar * 8 + off) * step, step * ln * 0.95, midi(n), sp["lead"], 0.17, "pluck" if ln < 3 else "sustain")
    for i in range(loop_n, len(buf)):          # wrap the reverb-ish tail so the loop is seamless
        buf[i - loop_n] += buf[i]
    buf = buf[:loop_n]
    peak = max(1e-6, max(abs(x) for x in buf))
    k = 0.85 * 32767 / peak
    return array.array("h", [int(x * k) for x in buf])


# ----------------------------------------------------------------------------- sound effects
def _tone(f0, f1, dur, wave="sine", vol=1.0, decay=4.0):
    n, ph, out, tbl = int(dur * SR), 0.0, [], TABLES[wave]
    for i in range(n):
        t = i / n
        ph += (f0 + (f1 - f0) * t) * N_TBL / SR
        out.append(tbl[int(ph) & 1023] * vol * math.exp(-decay * t) * min(1.0, i / 40))
    return out


def _seq(notes, wave="tri", vol=0.8, gap=0.07, ln=0.14):
    out = []
    for i, f in enumerate(notes):
        out += [0.0] * (int(gap * SR) if i else 0) + _tone(f, f, ln, wave, vol, 3.0)
    return out


def _noise_hit(rnd, dur, decay):
    return [rnd.uniform(-1, 1) * math.exp(-i / SR * decay) * 0.7 for i in range(int(dur * SR))]


def build_sfx():
    rnd = random.Random(3)
    c5, e5, g5, c6 = 523.25, 659.25, 783.99, 1046.5
    crash = [rnd.uniform(-1, 1) * math.exp(-i / SR * 7) * 0.7 for i in range(int(0.55 * SR))]
    low = _tone(180, 40, 0.55, "sine", 0.9, 3.0)
    crash = [a + b for a, b in zip(crash, low)]
    whoosh = [x * (math.sin(math.pi * i / (0.8 * SR)) ** 1.5) for i, x in enumerate(_tone(180, 1900, 0.8, "saw", 0.35, 0.0))]
    return {
        "flap": _tone(340, 640, 0.09, "square", 0.22, 5.0),
        "point": _seq([880, 1320], "tri", 0.5, 0.0, 0.06),
        "tick": _tone(740, 740, 0.04, "sine", 0.25, 6.0),
        "crash": crash,
        "lock": _tone(130, 80, 0.07, "sine", 0.6, 6.0),
        "clear1": _seq([c5, e5], "pulse", 0.30), "clear2": _seq([c5, e5, g5], "pulse", 0.30),
        "clear3": _seq([c5, e5, g5, c6], "pulse", 0.30), "clear4": _seq([c5, e5, g5, c6, e5 * 2, g5 * 2], "pulse", 0.32, 0.06),
        "levelup": _seq([g5, c6, 1318.5], "tri", 0.5, 0.06, 0.12),
        "record": _seq([c5, e5, g5, c6, g5, c6], "pulse", 0.30, 0.06, 0.12),
        "goal": _seq([c5, e5, g5, c6, g5, c6, e5 * 2, g5 * 2, c6 * 2], "pulse", 0.32, 0.09, 0.2),
        "whoosh": whoosh,
        "hit": [a + b for a, b in zip(_noise_hit(rnd, 0.09, 30), _tone(220, 90, 0.09, "square", 0.45, 6.0))],
        "heavy": [a + b for a, b in zip(_noise_hit(rnd, 0.2, 14), _tone(150, 45, 0.2, "sine", 0.9, 4.0))],
        "block": _tone(900, 600, 0.06, "square", 0.25, 7.0),
        "whiff": whoosh[: int(0.12 * SR)],
        "ko": [a + b for a, b in zip(_noise_hit(rnd, 0.8, 5), _tone(260, 35, 0.8, "saw", 0.5, 3.5))],
        "bell": _seq([1318.5, 1318.5], "sine", 0.6, 0.12, 0.35),
        "super": _tone(200, 1600, 0.6, "saw", 0.4, 1.5),
        "wave": _tone(500, 160, 0.3, "saw", 0.3, 3.0),
    }


# ----------------------------------------------------------------------------- mixer
class Audio:
    def __init__(self, cfg, games):
        self.cfg, self.enabled = cfg, True
        self.tracks, self.sfx_bank = {}, {}
        self.cur, self.prev = None, None
        self.pos = self.prev_pos = 0
        self.fade = 1.0                       # crossfade progress 0..1
        self.gain = 0.0
        self.duck = 1.0
        self.active = []
        if cfg.music:
            self._load_music(games)
        if cfg.sfx:
            peak = 32767 * 0.6
            self.sfx_bank = {k: array.array("h", [int(max(-1, min(1, x)) * peak) for x in v]) for k, v in build_sfx().items()}

    # ---- music loading
    def _load_music(self, games):
        files = []
        if self.cfg.music_dir:
            for ext in ("mp3", "wav", "ogg", "flac", "m4a", "aac"):
                files += glob.glob(os.path.join(self.cfg.music_dir, f"*.{ext}"))
            files.sort()
        if files:
            arr = array.array("h")
            for f in files:
                log.info("decoding %s", os.path.basename(f))
                r = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                                   capture_output=True)
                if r.returncode == 0 and r.stdout:
                    arr.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
            if len(arr):
                for g in games:
                    self.tracks[g] = arr
                self.tracks["_playlist"] = arr
                return
            log.warning("no usable audio in %s - using built-in music", self.cfg.music_dir)
        os.makedirs(self.cfg.cache_dir, exist_ok=True)
        for g in games:
            path = os.path.join(self.cfg.cache_dir, f"{g}-v{TRACK_VERSION}.pcm")
            arr = array.array("h")
            try:
                with open(path, "rb") as f:
                    arr.frombytes(f.read())
            except OSError:
                log.info("composing '%s' music (first run only, can take a minute on a phone)...", g)
                arr = render_track(g)
                try:
                    with open(path, "wb") as f:
                        f.write(arr.tobytes())
                except OSError:
                    pass
            self.tracks[g] = arr

    # ---- control
    def play(self, name):
        """Switch background music (crossfade). Same track object -> no restart (playlists keep playing)."""
        tr = self.tracks.get(name)
        if tr is None or (self.cur is not None and self.tracks.get(self.cur) is tr):
            self.cur = name if self.cur is None else self.cur
            return
        self.prev, self.prev_pos = self.cur, self.pos
        self.cur, self.pos, self.fade = name, 0, 0.0

    def sfx(self, name, vol=1.0):
        if name in self.sfx_bank and len(self.active) < 12:
            self.active.append([self.sfx_bank[name], 0, vol])

    def set_duck(self, f):
        self.duck = f

    def _read(self, tr, pos, n):
        L = len(tr)
        p = pos % L
        seg = tr[p:p + n]
        if len(seg) < n:
            seg = seg + tr[: n - len(seg)]
        return seg

    def chunk(self, n) -> bytes:
        out = [0] * n
        tr = self.tracks.get(self.cur) if self.cfg.music else None
        if tr is not None and len(tr):
            target = self.cfg.volume * self.duck
            self.gain += (target - self.gain) * 0.08
            seg = self._read(tr, self.pos, n)
            self.pos = (self.pos + n) % len(tr)
            if self.fade < 1.0:
                step = n / (1.6 * SR)
                f0, f1 = self.fade, min(1.0, self.fade + step)
                self.fade = f1
                pt = self.tracks.get(self.prev)
                if pt is not None and len(pt):
                    pseg = self._read(pt, self.prev_pos, n)
                    self.prev_pos = (self.prev_pos + n) % len(pt)
                    g = self.gain
                    out = [int((a * (f0 + (f1 - f0) * i / n) + b * (1 - (f0 + (f1 - f0) * i / n))) * g)
                           for i, (a, b) in enumerate(zip(seg, pseg))]
                else:
                    g = self.gain * f1
                    out = [int(a * g) for a in seg]
            else:
                g = self.gain
                out = [int(a * g) for a in seg]
        if self.active:
            alive = []
            for item in self.active:
                data, p, v = item
                m = min(n, len(data) - p)
                for i in range(m):
                    out[i] += int(data[p + i] * v)
                item[1] = p + m
                if item[1] < len(data):
                    alive.append(item)
            self.active = alive
            out = [32767 if x > 32767 else (-32768 if x < -32768 else x) for x in out]
        return array.array("h", out).tobytes()
