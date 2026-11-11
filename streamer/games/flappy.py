"""Flappy Bird - day/sunset/night/dawn cycle, parallax hills, animated bird, particles."""
from __future__ import annotations

import math

from PIL import Image

from ..gfx import LW, LH, col, darken, fmt, lighten, mix
from .base import Game

PW, CAP_H, CAP_W, GROUND_H = 96, 34, 112, 70
MAX_STEP = 140
THEMES = [
    dict(top="#2f9bff", mid="#8fd8ff", bot="#d8f6ff", sun=("#fff7b8", 1010, 150, 44), cloud="#ffffff",
         hills=("#9fd9d0", "#6cbfae", "#3f9a86")),
    dict(top="#33256b", mid="#d4577f", bot="#ffb36b", sun=("#ffd98a", 330, 470, 62), cloud="#ffd1bd",
         hills=("#c26a95", "#8f4a86", "#5b2f6e")),
    dict(top="#040817", mid="#12214d", bot="#2c4a8c", moon=True, cloud="#5f6ba5",
         hills=("#1e2f63", "#16224c", "#0d1634")),
    dict(top="#7d8cff", mid="#e8a8d8", bot="#ffe3ec", sun=("#fff2d0", 1080, 410, 52), cloud="#fff0f6",
         hills=("#c9b8f0", "#a592e0", "#7a6bc4")),
]
BIRD_ANGLES = list(range(-80, 33, 8))


class Flappy(Game):
    key, title, accent = "flappy", "Flappy Bird", "#ffd93d"
    rate_per_hour, run_typical = 3000, 500
    tagline = "Tap, glide, repeat. How far can it fly?"
    GRAV, FLAP, GAP, SPACING, R, BX = 0.5, -8.5, 210, 380, 18, 330

    def __init__(self, ctx):
        super().__init__(ctx)
        self.mist = self.mistake(0.0)
        self.total = 0
        self.theme = self.theme_from = 0
        self.theme_t = 1.0
        self.t = 0
        self.scroll = [0.0, 0.0, 0.0, 0.0]
        self.clouds = [[self.rng.uniform(0, LW), self.rng.uniform(40, 330), self.rng.uniform(0.18, 0.5), self.rng.randrange(3)]
                       for _ in range(7)]
        self.reset()

    # ------------------------------------------------------------------ logic
    def reset(self):
        self.begin_run()
        self.y, self.vy, self.pipes = LH / 2 - 40, 0.0, []
        self.flap_in, self.thr, self.rd = None, 14.0, self.h.reaction()
        self.speed, self.dead, self.dead_t, self.pop, self.flash = 3.2, False, 0, 0, 0
        for i in range(4):
            self.add_pipe(LW + 200 + i * self.SPACING)

    def add_pipe(self, x):
        r = self.rng
        off = r.uniform(-1, 1) * (14 + 36 * (1 - self.h.skill))            # where in the gap this player tends to aim
        if r.random() < self.mist:                               # deliberate slip
            off = r.choice([-1, 1]) * (self.GAP / 2 + 30)
        lo, hi = 170, LH - GROUND_H - 150
        prev = self.pipes[-1]["gy"] if self.pipes else (lo + hi) / 2
        gy = min(hi, max(lo, prev + r.uniform(-MAX_STEP, MAX_STEP)))     # keep consecutive gaps reachable
        self.pipes.append({"x": x, "gy": gy, "off": off, "passed": False, "aim": None})

    def hud_extra(self):
        return [("ATTEMPT", f"#{self.attempt}"), ("TOTAL PIPES", fmt(self.total_pts))]

    def update(self):
        self.t += 1
        self.pop = max(0, self.pop - 1)
        self.flash = max(0, self.flash - 4)
        if self.theme_t < 1:
            self.theme_t = min(1.0, self.theme_t + 1 / 150)
        for c in self.clouds:
            c[0] -= c[2]
            if c[0] < -200:
                c[0], c[1] = LW + 150, self.rng.uniform(40, 330)
        if self.dead:
            self.dead_t += 1
            self.vy = min(self.vy + self.GRAV, 14)
            if self.y + self.R < LH - GROUND_H:
                self.y += self.vy
            if self.dead_t > 100:
                self.reset()
            return
        sp = self.speed
        for i, f in enumerate((0.12, 0.3, 1.0, 1.0)):
            self.scroll[i] += sp * f
        nxt = next((p for p in self.pipes if p["x"] + PW > self.BX - self.R), None)
        h = self.h
        h.tick()
        if nxt is not None and nxt["aim"] is None:               # where in the gap this player happens to aim
            nxt["aim"] = h.noise(10, 22)
        target = nxt["gy"] + nxt["off"] + nxt["aim"] if nxt else LH / 2
        if self.flap_in is None:
            d = self.rd                                          # players anticipate where the bird will be
            pred = self.y + self.vy * d + 0.25 * d * d           # by the time their finger actually moves
            if pred > target + self.thr and self.vy > -1.5:
                self.flap_in = d                                 # decide now, finger moves a moment later
        else:
            self.flap_in -= 1
            if self.flap_in <= 0:
                self.flap_in = None
                self.rd = h.reaction()
                self.thr = 14 + h.noise(8, 16)                   # next tap happens at a slightly different height
                if h.rng.random() < h.chance(0.0, 0.02):     # rare fumble: tap lands late
                    self.flap_in = h.rng.randint(8, 16)
                else:
                    self.vy = self.FLAP
                    self.ctx.audio.sfx("flap")
                    self.ctx.parts.burst(self.BX - 18, self.y + 8, 3, ["#ffffff", "#fff3b0"], speed=(0.5, 1.8),
                                         life=(14, 26), size=(2, 4), grav=0.0, kind="dot")
        self.vy += self.GRAV
        self.y += self.vy
        self.speed = min(3.2 + self.score * 0.03, 6.5)
        for p in self.pipes:
            p["x"] -= sp
        if self.pipes[0]["x"] + PW < -20:
            self.pipes.pop(0)
            self.add_pipe(self.pipes[-1]["x"] + self.SPACING)
        for p in self.pipes:
            if not p["passed"] and p["x"] + PW < self.BX:
                p["passed"] = True
                self.total += 1
                self.gain(1)
                self.pop = 10
                self.ctx.audio.sfx("point", 0.7)
                self.ctx.parts.burst(self.BX, p["gy"], 8, ["#ffe066", "#ffffff", "#ffd43b"], speed=(1, 3.5),
                                     life=(20, 40), size=(2, 4), grav=0.05)
                th = (self.score // 20) % 4
                if th != self.theme:
                    self.theme_from, self.theme, self.theme_t = self.theme, th, 0.0
            hit_x = self.BX + self.R > p["x"] and self.BX - self.R < p["x"] + PW
            if hit_x and (self.y - self.R < p["gy"] - self.GAP / 2 or self.y + self.R > p["gy"] + self.GAP / 2):
                self.die()
        if self.y + self.R > LH - GROUND_H or self.y - self.R < 0:
            self.die()

    def die(self):
        if self.dead:
            return
        self.dead, self.dead_t, self.flash = True, 0, 200
        self.vy = -5
        self.crashed()
        self.ctx.audio.sfx("crash")
        self.ctx.parts.burst(self.BX, self.y, 28, ["#ffd93d", "#ff9f1c", "#ffffff", "#ff6b6b"], speed=(1.5, 6),
                             life=(30, 60), size=(2, 5), grav=0.18, kind="dot")

    # ------------------------------------------------------------------ sprites
    def sky(self, cv, i):
        th = THEMES[i]

        def paint(p):
            p.rrect_grad(0, 0, LW, LH, 0, [(0, th["top"]), (0.55, th["mid"]), (1, th["bot"])])
            if "sun" in th:
                c, sx, sy, r = th["sun"]
                p.glow(sx, sy, r * 4.2, c, 0.75, 1.8)
                p.ellipse(sx, sy, r, r, fill=c)
                p.ellipse(sx, sy, r * 0.8, r * 0.8, fill=lighten(c, 0.5))
            if th.get("moon"):
                p.glow(1000, 140, 190, "#9db7ff", 0.6, 2)
                p.ellipse(1000, 140, 42, 42, fill="#f5f2e4")
                for cx, cy, cr in ((988, 128, 9), (1015, 150, 7), (996, 156, 5)):
                    p.ellipse(cx, cy, cr, cr, fill="#d9d4bf")
                import random
                rnd = random.Random(5)
                for _ in range(110):
                    x, y, r = rnd.uniform(0, LW), rnd.uniform(0, 420), rnd.choice([1, 1, 1.5, 2])
                    p.ellipse(x, y, r, r, fill=(255, 255, 255, 255))
            return None

        return cv.sprite(("flappy_sky", i), LW, LH, paint, ss=1, mode="RGB")

    def hills(self, cv, i, layer):
        th = THEMES[i]
        h = (200, 170, 150)[layer]
        freq = (2, 3, 5)[layer]

        def paint(p):
            color = th["hills"][layer]
            pts = []
            for x in range(0, LW + 1, 6):
                y = h * 0.45 - (h * 0.30) * math.sin(2 * math.pi * freq * x / LW + layer) - (h * 0.12) * math.sin(
                    2 * math.pi * (freq * 2 + 1) * x / LW + 2 * layer)
                pts.append((x, y))
            p.poly(pts + [(LW, h), (0, h)], fill=color)
            if layer == 2:   # round bushes on the nearest layer
                import random
                rnd = random.Random(11)
                for x in range(0, LW, 46):
                    r = rnd.uniform(18, 30)
                    for ox in (-LW, 0, LW):
                        p.ellipse(x + ox, h * 0.62, r, r * 0.9, fill=darken(color, 0.1))

        return cv.sprite(("flappy_hills", i, layer), LW, h, paint, ss=2)

    def cloud(self, cv, i, k):
        color = THEMES[i]["cloud"]
        w, h = (150, 70, 160)[k] * 1.0, (70, 50, 80)[k]

        def paint(p):
            blobs = ((0.26, 0.64, 0.22), (0.46, 0.45, 0.30), (0.68, 0.55, 0.26), (0.82, 0.68, 0.19), (0.5, 0.7, 0.26),
                     (0.14, 0.72, 0.15))
            shade = darken(color, 0.16)
            for cx, cy, r in blobs:                       # soft underside first, then the white body on top
                p.ellipse(cx * w, cy * h + h * 0.07, r * h * 1.25, r * h * 1.25, fill=(*shade, 255))
            for cx, cy, r in blobs:
                p.ellipse(cx * w, cy * h, r * h * 1.25, r * h * 1.25, fill=(*col(color)[:3], 255))
            p.rrect(w * 0.1, h * 0.66, w * 0.8, h * 0.2, h * 0.1, fill=(*col(color)[:3], 255))

        return cv.sprite(("flappy_cloud", i, k), w, h, paint, ss=2)

    def pipe_parts(self, cv):
        stops = [(0, "#2e6f1f"), (0.1, "#58b82f"), (0.28, "#93e45f"), (0.5, "#63c236"), (0.85, "#3f9526"), (1, "#25601a")]

        def body(p):
            p.rrect_grad(0, 0, PW, 8, 0, stops, horizontal=True)
            p.rect(0, 0, 3, 8, fill="#1c4a12")
            p.rect(PW - 3, 0, 3, 8, fill="#1c4a12")

        def cap(p):
            p.rrect_grad(0, 0, CAP_W, CAP_H, 7, stops, horizontal=True)
            p.rrect(0, 0, CAP_W, CAP_H, 7, outline="#1c4a12", width=3)
            lay = p.layer()
            lay.rrect(10, 5, 14, CAP_H - 10, 4, fill=(255, 255, 255, 70))
            lay.rrect(2, CAP_H - 8, CAP_W - 4, 6, 3, fill=(0, 0, 0, 55))
            p.commit(lay)

        return (cv.sprite("flappy_pipe_body", PW, 8, body, ss=2), cv.sprite("flappy_pipe_cap", CAP_W, CAP_H, cap, ss=2,
                                                                          shadow=(4, 5, 4, 0.30)))

    def ground(self, cv):
        def paint(p):
            p.rrect_grad(0, 0, 96, GROUND_H, 0, [(0, "#e9d79a"), (1, "#c9a85a")])
            lay = p.layer()
            for x in range(-24, 120, 24):
                lay.poly([(x, 20), (x + 12, 20), (x + 36, GROUND_H), (x + 24, GROUND_H)], fill=(160, 120, 50, 70))
            p.commit(lay)
            p.rect(0, 0, 96, 16, fill="#7fd83f")
            p.rect(0, 10, 96, 9, fill="#4fae2c")
            p.rect(0, 0, 96, 4, fill="#a6ee63")
            for x in range(0, 96, 24):
                p.poly([(x + 2, 18), (x + 12, 18), (x + 7, 26)], fill="#4fae2c")
            p.rect(0, 19, 96, 3, fill="#3a8a20")
            return None

        return cv.sprite("flappy_ground", 96, GROUND_H, paint, ss=2)

    def bird(self, cv, wing, angle):
        def paint(p):
            cx, cy = 40, 40
            wy = (-7, 0, 7)[wing]
            p.poly([(cx - 20, cy - 2), (cx - 34, cy - 10), (cx - 31, cy + 2), (cx - 35, cy + 9), (cx - 18, cy + 8)],
                   fill="#f29b00", outline="#b86a00")
            p.ellipse(cx, cy, 25, 22, fill="#ffd93d", outline="#b8860b", width=2.5)
            p.ellipse(cx + 3, cy + 9, 17, 10, fill="#fff1a6")
            lay = p.layer()
            lay.ellipse(cx - 6, cy - 12, 13, 6, fill=(255, 255, 255, 110))
            lay.ellipse(cx + 8, cy + 4, 6, 4, fill=(255, 110, 110, 120))
            p.commit(lay)
            p.ellipse(cx - 9, cy + 4 + wy * 0.5, 14, 8 + abs(wy) * 0.2, fill="#ffa62b", outline="#c46f00", width=2)
            p.ellipse(cx - 11, cy + 2 + wy * 0.5, 7, 3.5, fill="#ffc46b")
            p.ellipse(cx + 11, cy - 8, 9, 9, fill="#ffffff", outline="#3a3a3a", width=1.6)
            p.ellipse(cx + 13.5, cy - 8, 4.4, 4.8, fill="#111111")
            p.ellipse(cx + 15, cy - 10, 1.6, 1.6, fill="#ffffff")
            p.poly([(cx + 18, cy - 4), (cx + 37, cy + 2), (cx + 18, cy + 4)], fill="#ff7a1a", outline="#b34700")
            p.poly([(cx + 18, cy + 4), (cx + 34, cy + 5), (cx + 19, cy + 11)], fill="#e85d04", outline="#b34700")
            return None

        return cv.sprite(("flappy_bird", wing, angle), 80, 80, paint, ss=4, rotate=angle, shadow=(3, 4, 4, 0.30))

    # ------------------------------------------------------------------ drawing
    def draw(self, cv):
        s = cv.s
        a = self.sky(cv, self.theme)
        if self.theme_t < 1:
            cv.paste_bg(Image.blend(self.sky(cv, self.theme_from), a, self.theme_t))
        else:
            cv.paste_bg(a)
        th = self.theme if self.theme_t > 0.5 else self.theme_from
        for c in self.clouds:
            cv.blit(self.cloud(cv, th, c[3]), c[0], c[1])
        cv.tile_h(self.hills(cv, th, 0), self.scroll[0], LH - GROUND_H - 205 + 40)
        cv.tile_h(self.hills(cv, th, 1), self.scroll[1], LH - GROUND_H - 175 + 30)
        cv.tile_h(self.hills(cv, th, 2), self.scroll[2] * 0.45, LH - GROUND_H - 150 + 20)

        body, cap = self.pipe_parts(cv)
        for p in self.pipes:
            top, bot = p["gy"] - self.GAP / 2, p["gy"] + self.GAP / 2
            hpx = int((top - CAP_H) * s)
            if hpx > 0:
                cv.img.paste(body.resize((body.width, hpx), Image.NEAREST), (int(p["x"] * s), 0))
            cv.blit(cap, p["x"] + PW / 2, top - CAP_H / 2, "c")
            hb = int((LH - (bot + CAP_H)) * s)
            if hb > 0:
                cv.img.paste(body.resize((body.width, hb), Image.NEAREST), (int(p["x"] * s), int((bot + CAP_H) * s)))
            cv.blit(cap, p["x"] + PW / 2, bot + CAP_H / 2, "c")

        g = self.ground(cv)
        cv.tile_h(g, self.scroll[3], LH - GROUND_H)

        ang = max(-80, min(32, -self.vy * 5)) if not self.dead else -80
        ang = BIRD_ANGLES[min(range(len(BIRD_ANGLES)), key=lambda i: abs(BIRD_ANGLES[i] - ang))]
        wing = [0, 1, 2, 1][(self.t // (3 if self.vy < 0 else 6)) % 4] if not self.dead else 2
        cv.blit(self.bird(cv, wing, ang), self.BX, self.y, "c")

        size = 100 + self.pop * 2.4
        cv.text(LW / 2, 130, fmt(self.score), size, "#ffffff", "m", shadow=4, stroke=3)
        if self.flash:
            cv.overlay("#ff3b30", self.flash * 0.35)

    def icon(self, cv, size=96):
        return self.bird(cv, 1, 8)
