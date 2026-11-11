"""Car Racing - top-down highway, detailed cars, scrolling road with curbs, trees, neon player car."""
from __future__ import annotations

import math
import random

from ..gfx import LW, LH, darken, fmt, lighten
from .base import Game

ROAD_X, LANE_W, LANES, CW, CH, PY = 390, 125, 4, 52, 96, 590
ROAD_W = LANE_W * LANES
CAR_W, CAR_H = 68, 112
COLORS = ["#e53935", "#fdd835", "#43a047", "#8e24aa", "#fb8c00", "#00acc1", "#eceff1", "#ec407a"]


class Racing(Game):
    key, title, accent = "racing", "Car Racing", "#35c4ff"
    rate_per_hour, run_typical = 40000, 8000
    tagline = "Weave through traffic at full speed. One mistake and it's over."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.mist = self.mistake(0.0)
        self.scroll = 0.0
        self.crashes = 0
        self.dist_pts = 0.0
        self.trees = []
        r = self.rng
        for i in range(14):
            self.trees.append(self._new_tree(r.uniform(-100, LH)))
        self.reset()

    def _new_tree(self, y):
        r = self.rng
        left = r.random() < 0.5
        x = r.uniform(30, ROAD_X - 70) if left else r.uniform(ROAD_X + ROAD_W + 70, LW - 30)
        return {"x": x, "y": y, "k": r.choice([0, 0, 1, 1, 2, 3])}

    def lane_x(self, l):
        return ROAD_X + LANE_W * l + LANE_W / 2

    def reset(self):
        self.begin_run()
        self.lane = self.rng.randrange(LANES)
        self.x = self.lane_x(self.lane)
        self.tilt = 0.0
        self.traffic = []
        self.lane_speed = [self.rng.uniform(2, 4.5) for _ in range(LANES)]
        self.v, self.dist, self.passed = 6.0, 0.0, 0
        self.dead, self.dead_t, self.spawn_cd, self.flash = False, 0, 30, 0
        self.spin = 0.0
        self.react, self.steer = 20, 0.12
        self.wob, self.wob_goal, self.wob_t = 0.0, 0.0, 0

    def hud_extra(self):
        return [("SPEED", f"{round(self.v * 20)} km/h"), ("CARS PASSED", fmt(self.passed)), ("CRASHES", fmt(self.crashes))]

    # ------------------------------------------------------------------ logic
    def spawn(self):
        r = self.rng
        lane = r.randrange(LANES)
        if any(t["lane"] == lane and t["y"] < 280 for t in self.traffic):
            return
        if sum(1 for t in self.traffic if t["y"] < 220) >= 2:
            return
        self.traffic.append({"lane": lane, "y": -130.0, "blind": r.random() < self.mist, "ci": r.randrange(len(COLORS)),
                             "scored": False})

    def gap_ahead(self, l):
        g = math.inf
        for t in self.traffic:
            if t["lane"] != l or t["blind"]:
                continue
            if t["y"] - CH / 2 > PY + CH / 2:
                continue
            g = min(g, max(0, (PY - CH / 2) - (t["y"] + CH / 2)))
        return g

    def side_clear(self, l):
        return not any(t["lane"] == l and not t["blind"] and abs(t["y"] - PY) < CH + 50 for t in self.traffic)

    def decide(self):
        """Look at the road and pick a lane, the way a person does: occasionally, with imperfect judgement."""
        h, cur = self.h, self.lane
        look = max(110, 130 + self.v * 26 + h.noise(22, 45))
        if self.gap_ahead(cur) >= look:
            # clear road: now and then a driver drifts over to a faster-looking lane just because
            if h.rng.random() < 0.004:
                for l in h.rng.sample([cur - 1, cur + 1], 2):
                    if 0 <= l < LANES and self.side_clear(l) and self.gap_ahead(l) >= look * 1.3:
                        self.lane, self.steer = l, h.rng.uniform(0.07, 0.13)
                        break
            return
        pick, best = -1, self.gap_ahead(cur) + 40
        for l in (cur - 1, cur + 1):
            if 0 <= l < LANES and self.side_clear(l):
                g = self.gap_ahead(l)
                if g > best:
                    best, pick = g, l
        if pick >= 0:
            self.lane = pick
            self.steer = h.rng.uniform(0.08, 0.16)           # sometimes a lazy lane change, sometimes a snappy one

    def update(self):
        self.scroll = (self.scroll + self.v) % 160
        for t in self.trees:
            t["y"] += self.v
            if t["y"] > LH + 90:
                t.update(self._new_tree(-90 - self.rng.uniform(0, 80)))
        if self.dead:
            self.dead_t += 1
            self.v *= 0.97
            self.spin *= 0.96
            self.flash = max(0, self.flash - 5)
            if self.dead_t % 3 == 0:
                self.ctx.parts.add(self.x + self.rng.uniform(-10, 10), PY + self.rng.uniform(-10, 10), self.rng.uniform(-.4, .4),
                                   self.rng.uniform(0.5, 1.6), 55, 9, "#555555", 0.0, "smoke")
            if self.dead_t > 115:
                self.reset()
            return
        self.v = min(6 + self.dist / 6000, 14)
        self.dist += self.v
        self.dist_pts += self.v
        if self.dist_pts >= 450:
            self.dist_pts -= 450
            self.gain(1)
        self.spawn_cd -= 1
        if self.spawn_cd <= 0:
            self.spawn()
            self.spawn_cd = (300 + self.rng.random() * 350) / self.v
        for t in self.traffic:
            t["y"] += self.v - self.lane_speed[t["lane"]]
            if not t["scored"] and t["y"] > PY + CH:
                t["scored"] = True
                self.passed += 1
                self.gain(10)
                self.ctx.audio.sfx("tick", 0.6)
        self.traffic = [t for t in self.traffic if t["y"] < LH + 140]
        h = self.h
        h.tick()
        self.react -= 1
        if self.react <= 0:                                     # eyes on the road every ~0.1-0.2 s, not every frame
            self.react = max(4, h.reaction(6, 9) + h.rng.randint(0, 4))
            self.decide()
        self.wob_t -= 1
        if self.wob_t <= 0:                                     # small steering drift inside the lane
            self.wob_goal, self.wob_t = h.noise(5, 9), h.rng.randint(30, 120)
        self.wob += (self.wob_goal - self.wob) * 0.04
        tx = self.lane_x(self.lane) + self.wob
        self.tilt = (tx - self.x) * 0.18
        self.x += (tx - self.x) * self.steer
        for t in self.traffic:
            if abs(self.x - self.lane_x(t["lane"])) < CW - 6 and abs(t["y"] - PY) < CH - 8:
                self.dead, self.dead_t, self.flash = True, 0, 220
                self.spin = self.rng.choice([-1, 1]) * 9
                self.tilt = 0
                self.crashes += 1
                self.crashed()
                self.ctx.audio.sfx("crash")
                self.ctx.parts.burst(self.x, PY - 30, 36, ["#ffb300", "#ff6d00", "#ffee58", "#ffffff"], speed=(1.5, 7),
                                     life=(25, 55), size=(2, 5), grav=0.04, kind="spark" if self.rng.random() < .3 else "dot")
                break

    # ------------------------------------------------------------------ sprites
    def car(self, cv, ci, player=False, angle=0):
        c = "#1e88e5" if player else COLORS[ci]

        def paint(p):
            wheels = "#101216"
            for wx in (3, 57):
                for wy in (19, 70):
                    p.rrect(wx, wy, 8, 25, 3, fill=wheels)
            p.rrect_grad(8, 5, 52, 102, 16, [(0, darken(c, .4)), (.25, lighten(c, .05)), (.5, lighten(c, .30)), (.75, lighten(c, .05)), (1, darken(c, .4))],
                         horizontal=True)
            p.rrect(8, 5, 52, 102, 16, outline=darken(c, .55), width=1.6)
            lay = p.layer()
            lay.line(14, 36, 54, 36, (0, 0, 0, 80), 1.4)
            lay.line(14, 88, 54, 88, (0, 0, 0, 80), 1.4)
            p.commit(lay)
            p.rrect_grad(13, 34, 42, 25, 7, [(0, "#cfeaff"), (0.5, "#6f9cc7"), (1, "#2a4768")])
            p.rrect_grad(14, 58, 40, 28, 5, [(0, lighten(c, .12)), (1, darken(c, .18))])
            p.rrect_grad(14, 85, 40, 14, 4, [(0, "#2d4f73"), (1, "#16293f")])
            lay = p.layer()
            lay.poly([(17, 37), (30, 37), (22, 57), (15, 57)], fill=(255, 255, 255, 95))
            lay.ellipse(34, 20, 14, 6, fill=(255, 255, 255, 40))
            p.commit(lay)
            p.rrect(12, 6, 11, 6, 3, fill="#fffbd0")
            p.rrect(45, 6, 11, 6, 3, fill="#fffbd0")
            p.rrect(11, 102, 13, 4, 2, fill="#ff2d2d")
            p.rrect(44, 102, 13, 4, 2, fill="#ff2d2d")
            p.ellipse(6, 44, 3.6, 2.6, fill=darken(c, .2))
            p.ellipse(62, 44, 3.6, 2.6, fill=darken(c, .2))
            if player:
                for x in (29, 35):
                    p.rect(x, 8, 3, 27, fill="#ffffff")
                    p.rect(x, 59, 3, 26, fill="#ffffff")
                    p.rect(x, 86, 3, 14, fill="#ffffff")
                p.rrect(14, 99, 40, 6, 2, fill="#0d47a1")

        return cv.sprite(("race_car", ci, player, angle), CAR_W, CAR_H, paint, ss=3, shadow=(3, 5, 4, 0.38), rotate=angle or None)

    def road(self, cv):
        def paint(p):
            w, h = ROAD_W + 32, 160
            p.rect(0, 0, w, h, fill="#33363c")
            rnd = random.Random(2)
            lay = p.layer()
            for _ in range(900):
                x, y = rnd.uniform(16, w - 16), rnd.uniform(0, h)
                v = rnd.choice([(255, 255, 255, 14), (0, 0, 0, 30)])
                lay.rect(x, y, rnd.uniform(1, 3), rnd.uniform(1, 3), fill=v)
            p.commit(lay)
            for i in range(4):                                         # curbs
                c = "#e53935" if i % 2 == 0 else "#f5f5f5"
                p.rect(0, i * 40, 16, 40, fill=c)
                p.rect(w - 16, i * 40, 16, 40, fill=c)
            p.rect(16, 0, 5, h, fill="#f2f2f2")
            p.rect(w - 21, 0, 5, h, fill="#f2f2f2")
            for l in range(1, LANES):
                for y0 in (20, 100):
                    p.rect(16 + l * LANE_W - 3, y0, 6, 44, fill="#e8e8e8")
            lay = p.layer()
            lay.rect(16, 0, 3, h, fill=(0, 0, 0, 60))
            lay.rect(w - 19, 0, 3, h, fill=(0, 0, 0, 60))
            p.commit(lay)

        return cv.sprite("race_road", ROAD_W + 32, 160, paint, ss=2)

    def grass(self, cv):
        def paint(p):
            rnd = random.Random(4)
            p.rect(0, 0, LW, 80, fill="#2f9140")
            p.rect(0, 80, LW, 80, fill="#2a8639")
            lay = p.layer()
            for _ in range(700):
                x, y, r = rnd.uniform(0, LW), rnd.uniform(0, 160), rnd.uniform(1, 3.5)
                lay.ellipse(x, y, r, r * 0.7, fill=rnd.choice([(255, 255, 255, 16), (0, 40, 0, 30), (180, 255, 120, 18)]))
            p.commit(lay)

        return cv.sprite("race_grass", LW, 160, paint, ss=1, mode="RGB")

    def tree(self, cv, k):
        def paint(p):
            c = 45
            if k in (0, 1):
                r = 34 if k == 0 else 26
                p.ellipse(c, c, r, r, fill="#1c6a2b")
                p.ellipse_grad(c - 3, c - 4, r - 5, r - 5, [(0, "#58c256"), (1, "#238a3a")])
                p.ellipse(c - 9, c - 11, 8, 6, fill=(120, 220, 110, 255))
            elif k == 2:
                for i, (w, y) in enumerate(((36, 62), (30, 46), (22, 32))):
                    p.poly([(c - w / 2 - 4, y + 10), (c + w / 2 + 4, y + 10), (c, y - 22)], fill=("#18603a", "#1f7646", "#2a9158")[i])
            else:
                for dx, dy, r in ((-9, 2, 13), (8, 0, 14), (0, -8, 13), (0, 8, 11)):
                    p.ellipse(c + dx, c + dy, r, r, fill="#2c8f3f", outline="#1f6e30", width=1.2)
                for dx, dy in ((-4, -6), (6, 2)):
                    p.ellipse(c + dx, c + dy, 3, 3, fill="#ff6f91")

        return cv.sprite(("race_tree", k), 90, 90, paint, ss=2, shadow=(7, 9, 6, 0.35))

    # ------------------------------------------------------------------ drawing
    def draw(self, cv):
        g = self.grass(cv)
        y = self.scroll % 160 - 160
        while y < LH:
            cv.blit(g, 0, y)
            y += 160
        for t in self.trees:
            cv.blit(self.tree(cv, t["k"]), t["x"], t["y"], "c")
        road = self.road(cv)
        y = self.scroll % 160 - 160
        while y < LH:
            cv.blit(road, ROAD_X - 16, y)
            y += 160

        if cv.fx >= 1 and self.v > 9 and not self.dead:                 # speed streaks
            r = random.Random(int(self.scroll // 8))
            for _ in range(7):
                x = r.uniform(ROAD_X + 10, ROAD_X + ROAD_W - 10)
                y0 = r.uniform(0, LH)
                cv.d.line([(x * cv.s, y0 * cv.s), (x * cv.s, (y0 + 40 + self.v * 4) * cv.s)], fill=(255, 255, 255, 38),
                          width=max(1, int(2 * cv.s)))

        for t in self.traffic:
            cv.blit(self.car(cv, t["ci"]), self.lane_x(t["lane"]), t["y"], "c")
        if not self.dead:
            if cv.fx >= 1:
                cv.glow(self.x, PY + 6, 78, "#35c4ff", 0.55, 2)
                cv.glow(self.x, PY - 105, 60, "#fff6c0", 0.45, 2)
            cv.blit(self.car(cv, 0, True, int(max(-14, min(14, -self.tilt)) // 3 * 3)), self.x, PY, "c")
        else:
            if cv.fx >= 1:
                cv.glow(self.x, PY, 90 + self.dead_t * 0.4, "#ff7a1f", 0.55 * max(0, 1 - self.dead_t / 70), 2)
            ang = int(max(-60, min(60, self.spin * self.dead_t * 0.9))) // 6 * 6
            cv.blit(self.car(cv, 0, True, ang if ang else 6), self.x, PY, "c")
        if self.flash:
            cv.overlay("#ff6a00", self.flash * 0.25)

    def icon(self, cv, size=96):
        return self.car(cv, 0, True)
