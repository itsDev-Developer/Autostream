"""Rendering toolkit: supersampled sprites (anti-aliased), gradients, glow, text, panels, particles.

Everything is drawn in a logical 1280x720 space and scaled to the real output size.
Sprites are painted once at 2-4x resolution, downsampled with LANCZOS and cached, so per-frame work is
just fast pastes - this is what makes the graphics smooth while staying light enough for a phone.
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

LW, LH = 1280, 720
LANCZOS = Image.LANCZOS
_T = getattr(Image, "Transpose", Image)

FONT_PATHS = [
    os.environ.get("FONT_PATH", ""),
    "/system/fonts/Roboto-Black.ttf", "/system/fonts/Roboto-Bold.ttf", "/system/fonts/DroidSans-Bold.ttf",
    os.environ.get("PREFIX", "") + "/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


# ----------------------------------------------------------------------------- colour helpers
def col(c, a=255):
    """'#rrggbb' / (r,g,b) / (r,g,b,a) -> (r,g,b,a)."""
    if isinstance(c, str):
        t = ImageColor.getrgb(c)
        return (t[0], t[1], t[2], t[3] if len(t) > 3 else int(a))
    if len(c) == 4:
        return tuple(int(v) for v in c)
    return (int(c[0]), int(c[1]), int(c[2]), int(a))


def mix(c1, c2, t):
    a, b = col(c1), col(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(c, f):
    return mix(c, (255, 255, 255), f)


def darken(c, f):
    return mix(c, (0, 0, 0), f)


def fmt(n):
    return f"{int(n):,}"


def fmt_time(sec):
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def ease_out(t):
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def gradient(w, h, stops, horizontal=False):
    """RGBA gradient image. stops = [(pos 0..1, colour), ...]."""
    n = max(1, w if horizontal else h)
    stops = [(p, col(c)) for p, c in stops]
    strip = Image.new("RGBA", (n, 1))
    px = strip.load()
    for i in range(n):
        t = i / max(1, n - 1)
        for j in range(len(stops) - 1):
            if t <= stops[j + 1][0] or j == len(stops) - 2:
                (p0, c0), (p1, c1) = stops[j], stops[j + 1]
                u = 0.0 if p1 == p0 else min(1.0, max(0.0, (t - p0) / (p1 - p0)))
                px[i, 0] = tuple(int(c0[k] + (c1[k] - c0[k]) * u) for k in range(4))
                break
    if horizontal:
        return strip.resize((w, h), Image.NEAREST)
    return strip.transpose(_T.ROTATE_270).resize((w, h), Image.NEAREST)


# ----------------------------------------------------------------------------- painter
class Painter:
    """Draws with logical coordinates scaled by k onto an image."""

    def __init__(self, im, k, blend=False):
        self.im, self.k = im, k
        self.d = ImageDraw.Draw(im, "RGBA") if (blend and im.mode == "RGB") else ImageDraw.Draw(im)

    @staticmethod
    def _c(c):
        return None if c is None else col(c)

    def _w(self, w):
        return max(1, int(round(w * self.k)))

    def _box(self, x, y, w, h):
        k = self.k
        return [x * k, y * k, max(x * k, (x + w) * k - 1), max(y * k, (y + h) * k - 1)]

    def rect(self, x, y, w, h, fill=None, outline=None, width=1):
        self.d.rectangle(self._box(x, y, w, h), fill=self._c(fill), outline=self._c(outline), width=self._w(width))

    def rrect(self, x, y, w, h, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self._box(x, y, w, h), radius=r * self.k, fill=self._c(fill),
                                 outline=self._c(outline), width=self._w(width))

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, width=1):
        k = self.k
        self.d.ellipse([(cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k], fill=self._c(fill),
                       outline=self._c(outline), width=self._w(width))

    def poly(self, pts, fill=None, outline=None):
        k = self.k
        self.d.polygon([(x * k, y * k) for x, y in pts], fill=self._c(fill), outline=self._c(outline))

    def line(self, x1, y1, x2, y2, fill, width=1):
        k = self.k
        self.d.line([(x1 * k, y1 * k), (x2 * k, y2 * k)], fill=self._c(fill), width=self._w(width))

    # --- gradients (hard binary masks; supersampling makes edges smooth)
    def _paste_grad(self, mask, x, y, w, h, stops, horizontal):
        W, H = mask.size
        self.im.paste(gradient(W, H, stops, horizontal), (int(round(x * self.k)), int(round(y * self.k))), mask)

    def rrect_grad(self, x, y, w, h, r, stops, horizontal=False):
        W, H = max(1, int(round(w * self.k))), max(1, int(round(h * self.k)))
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, W - 1, H - 1], radius=r * self.k, fill=255)
        self._paste_grad(m, x, y, w, h, stops, horizontal)

    def ellipse_grad(self, cx, cy, rx, ry, stops, horizontal=False):
        W, H = max(1, int(round(2 * rx * self.k))), max(1, int(round(2 * ry * self.k)))
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).ellipse([0, 0, W - 1, H - 1], fill=255)
        self._paste_grad(m, cx - rx, cy - ry, 2 * rx, 2 * ry, stops, horizontal)

    # --- translucent layers
    def layer(self):
        return Painter(Image.new("RGBA", self.im.size, (0, 0, 0, 0)), self.k)

    def commit(self, lp):
        self.im.alpha_composite(lp.im)

    def glow(self, cx, cy, r, color, strength=1.0, power=2.0):
        k = self.k
        D = max(2, int(2 * r * k))
        a = Image.radial_gradient("L").resize((D, D), Image.BILINEAR)
        # radial_gradient reaches 255 only at the corners; stretch so alpha hits 0 at the circle edge (no square halo)
        a = a.point(lambda v: int(255 * min(1.0, strength) * max(0.0, 1 - min(1.0, v / 255 * 1.4143)) ** power))
        lay = Image.new("RGBA", (D, D), col(color)[:3] + (0,))
        lay.putalpha(a)
        X, Y = int(cx * k - D / 2), int(cy * k - D / 2)
        full = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        full.paste(lay, (X, Y))
        self.im.alpha_composite(full)


# ----------------------------------------------------------------------------- particles
class Particles:
    def __init__(self, rng, cap=320):
        self.items, self.rng, self.cap = [], rng, cap

    def add(self, x, y, vx, vy, life, size, color, grav=0.1, kind="dot"):
        if len(self.items) >= self.cap:
            self.items.pop(0)
        self.items.append([x, y, vx, vy, life, life, size, col(color), grav, kind, self.rng.random() * 6.28])

    def burst(self, x, y, n, colors, speed=(1, 5), life=(25, 55), size=(2, 5), grav=0.12, up=0.0, kind="dot"):
        r = self.rng
        for _ in range(n):
            a, sp = r.uniform(0, 6.283), r.uniform(*speed)
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp - up, r.randint(*life), r.uniform(*size),
                     r.choice(colors), grav, kind)

    def confetti(self, n, colors):
        r = self.rng
        for _ in range(n):
            self.add(r.uniform(0, LW), r.uniform(-120, -10), r.uniform(-1, 1), r.uniform(1.5, 4), r.randint(160, 280),
                     r.uniform(4, 8), r.choice(colors), 0.02, "conf")

    def update(self):
        for p in self.items:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += p[8]
            p[4] -= 1
            if p[9] == "smoke":
                p[2] *= 0.97
        self.items = [p for p in self.items if p[4] > 0]

    def draw(self, cv):
        s, d = cv.s, cv.d
        for x, y, vx, vy, life, maxlife, size, c, g, kind, rot in self.items:
            t = life / maxlife
            if kind == "conf":
                a, w, h = rot + life * 0.2, size, size * 0.55
                ca, sa = math.cos(a), math.sin(a)
                pts = [((x + ca * dx - sa * dy) * s, (y + sa * dx + ca * dy) * s) for dx, dy in
                       ((-w, -h), (w, -h), (w, h), (-w, h))]
                d.polygon(pts, fill=c[:3] + (int(255 * min(1, t * 3)),))
            elif kind == "spark":
                d.line([(x * s, y * s), ((x - vx * 3) * s, (y - vy * 3) * s)], fill=c[:3] + (int(255 * t),),
                       width=max(1, int(2 * s)))
            else:
                r = size * (0.5 + 0.5 * t) if kind == "dot" else size * (1 + (1 - t) * 2.2)
                alpha = int(255 * t) if kind == "dot" else int(130 * t)
                d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=c[:3] + (alpha,))


# ----------------------------------------------------------------------------- canvas
class Canvas:
    """Frame buffer + sprite cache + text/panel helpers."""

    def __init__(self, w, h, fx=2):
        self.w, self.h, self.fx = w, h, fx
        self.s = w / LW
        self.img = Image.new("RGB", (w, h), (0, 0, 0))
        self.p = Painter(self.img, self.s, blend=True)
        self.d = self.p.d
        self._sp, self._fonts, self._vig = {}, {}, None

    # ---- sprites
    def sprite(self, key, w, h, paint, ss=3, shadow=None, rotate=None, mode="RGBA"):
        """Paint once at ss x resolution, downsample, cache. shadow=(dx,dy,blur,alpha) in logical px."""
        if key in self._sp:
            return self._sp[key]
        k = self.s * ss
        im = Image.new("RGBA", (max(1, round(w * k)), max(1, round(h * k))), (0, 0, 0, 0))
        out = paint(Painter(im, k))
        if isinstance(out, Image.Image):
            im = out
        if rotate:
            im = im.rotate(rotate, resample=Image.BICUBIC)
        im = im.resize((max(1, round(w * self.s)), max(1, round(h * self.s))), LANCZOS)
        if shadow:
            im = self._shadowed(im, *shadow)
        if mode == "RGB":
            im = im.convert("RGB")
        self._sp[key] = im
        return im

    def _shadowed(self, im, dx, dy, blur, alpha):
        s = self.s
        pad = int(math.ceil(blur * s * 2 + max(abs(dx), abs(dy)) * s)) + 1
        W, H = im.width + 2 * pad, im.height + 2 * pad
        base = Image.new("L", (W, H), 0)
        base.paste(im.getchannel("A"), (pad + int(dx * s), pad + int(dy * s)))
        base = base.filter(ImageFilter.GaussianBlur(max(0.1, blur * s))).point(lambda v: int(v * alpha))
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.putalpha(base)
        out.alpha_composite(im, (pad, pad))
        return out

    def blit(self, spr, x, y, anchor="tl"):
        s = self.s
        w, h = spr.size
        fx, fy = {"tl": (0, 0), "c": (.5, .5), "tc": (.5, 0), "bc": (.5, 1), "cl": (0, .5), "cr": (1, .5),
                  "tr": (1, 0), "bl": (0, 1)}[anchor]
        pos = (int(round(x * s - w * fx)), int(round(y * s - h * fy)))
        if spr.mode == "RGBA":
            self.img.paste(spr, pos, spr)
        else:
            self.img.paste(spr, pos)

    def paste_bg(self, spr):
        self.img.paste(spr, (0, 0))

    def tile_h(self, spr, offset, y, anchor="tl"):
        """Blit a horizontally seamless sprite scrolled by `offset` logical px, wrapping around."""
        w = spr.width / self.s
        off = offset % w
        x = -off
        while x < LW:
            self.blit(spr, x, y, anchor)
            x += w

    def glow(self, x, y, r, color, strength=1.0, power=2.0):
        key = ("glow", r, col(color), round(strength, 2), power)
        spr = self.sprite(key, 2 * r, 2 * r, lambda p: p.glow(r, r, r, color, strength, power), ss=1)
        self.blit(spr, x, y, "c")

    # ---- text
    def font(self, size):
        px = max(8, int(size * self.s))
        if px not in self._fonts:
            f = None
            for p in FONT_PATHS:
                if p:
                    try:
                        f = ImageFont.truetype(p, px)
                        break
                    except Exception:
                        pass
            if f is None:
                try:
                    f = ImageFont.load_default(size=px)
                except TypeError:
                    f = ImageFont.load_default()
            self._fonts[px] = f
        return self._fonts[px]

    def text_w(self, s, size):
        try:
            return self.font(size).getlength(str(s)) / self.s
        except AttributeError:
            return len(str(s)) * size * 0.6

    def text(self, x, y, s, size, fill="#ffffff", anchor="l", shadow=2, stroke=0):
        f, sc = self.font(size), self.s
        a = {"l": "ls", "m": "ms", "r": "rs"}[anchor]
        try:
            if shadow:
                self.d.text((x * sc + shadow * sc, y * sc + shadow * sc), str(s), font=f, fill=(0, 0, 0, 140), anchor=a)
            self.d.text((x * sc, y * sc), str(s), font=f, fill=col(fill), anchor=a, stroke_width=int(stroke * sc),
                        stroke_fill=(0, 0, 0, 255))
        except (ValueError, TypeError):
            self.d.text((x * sc, (y - size) * sc), str(s), font=f, fill=col(fill))

    def fit(self, s, size, maxw, minsize=16):
        """Largest font size <= size so that text s fits in maxw logical px."""
        w = self.text_w(s, size)
        return size if w <= maxw else max(minsize, size * maxw / w)

    def wrap(self, s, size, maxw):
        lines, cur = [], ""
        for word in str(s).split():
            trial = (cur + " " + word).strip()
            if cur and self.text_w(trial, size) > maxw:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        return lines + ([cur] if cur else [])

    def rich(self, x, y, segs, size, anchor="m"):
        """segs = [(text, colour), ...] laid out in a row (anchor l or m)."""
        total = sum(self.text_w(t, size) for t, _ in segs)
        cx = x - total / 2 if anchor == "m" else x
        for t, c in segs:
            self.text(cx, y, t, size, c, "l")
            cx += self.text_w(t, size)
        return total

    # ---- widgets
    def panel(self, x, y, w, h, r=18, alpha=170, accent=None):
        key = ("panel", int(w), int(h), r, alpha, accent)

        def paint(p):
            p.rrect(0, 0, w, h, r, fill=(8, 10, 30, alpha))
            lay = p.layer()
            lay.rrect_grad(1, 1, w - 2, h * 0.5, r, [(0, (255, 255, 255, 34)), (1, (255, 255, 255, 0))])
            lay.rrect(0.5, 0.5, w - 1, h - 1, r, outline=(255, 255, 255, 50), width=1.5)
            if accent:
                lay.rrect(0, 0, 5, h, 2, fill=col(accent, 230))
            p.commit(lay)

        self.blit(self.sprite(key, int(w), int(h), paint, ss=2), x, y)

    def bar(self, x, y, w, h, frac, color="#35e0a1"):
        pct = int(max(0.0, min(1.0, frac)) * 100)
        key = ("bar", int(w), int(h), pct, col(color))

        def paint(p):
            p.rrect(0, 0, w, h, h / 2, fill=(255, 255, 255, 40))
            fw = max(h, w * pct / 100) if pct > 0 else 0
            if fw:
                p.rrect_grad(0, 0, fw, h, h / 2, [(0, lighten(color, .35)), (1, darken(color, .1))])
                lay = p.layer()
                lay.rrect(2, 1, max(1, fw - 4), h * 0.35, h / 4, fill=(255, 255, 255, 70))
                p.commit(lay)

        self.blit(self.sprite(key, int(w), int(h), paint, ss=2), x, y)

    def overlay(self, color, alpha):
        self.d.rectangle([0, 0, self.w, self.h], fill=col(color)[:3] + (int(alpha),))

    def vignette(self, strength=0.5):
        if self._vig is None:
            m = Image.radial_gradient("L").resize((self.w, self.h), Image.BILINEAR)
            m = m.point(lambda v: int(strength * 255 * max(0.0, (v - 95) / 160) ** 1.5))
            lay = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 255))
            lay.putalpha(m)
            self._vig = lay
        self.img.paste(self._vig, (0, 0), self._vig)
