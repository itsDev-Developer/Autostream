"""Block Stacker - neon synthwave look, glossy blocks, line-clear animation."""
from __future__ import annotations

import math

from ..gfx import LW, LH, col, darken, fmt, lighten
from .base import Game

COLS, ROWS, CELL = 10, 20, 34
BX0, BY0 = (LW - COLS * CELL) // 2, 20
SHAPES = {
    "I": [[1, 1, 1, 1]], "O": [[1, 1], [1, 1]], "T": [[0, 1, 0], [1, 1, 1]], "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]], "J": [[1, 0, 0], [1, 1, 1]], "L": [[0, 0, 1], [1, 1, 1]],
}
BCOL = {"I": "#19d9f0", "O": "#ffd91a", "T": "#b44cf5", "S": "#3fe05a", "Z": "#ff4757", "J": "#4a76ff", "L": "#ff9f1a"}
CLEAR_FRAMES = 26


def rotate(m):
    r, c = len(m), len(m[0])
    return [[m[r - 1 - j][i] for j in range(r)] for i in range(c)]


def collides(g, m, x, y):
    for i, row in enumerate(m):
        for j, v in enumerate(row):
            if v:
                gx, gy = x + j, y + i
                if gx < 0 or gx >= COLS or gy >= ROWS or (gy >= 0 and g[gy][gx]):
                    return True
    return False


def lock(g, m, x, y, color):
    n = [r[:] for r in g]
    for i, row in enumerate(m):
        for j, v in enumerate(row):
            if v and y + i >= 0:
                n[y + i][x + j] = color
    full = [i for i, r in enumerate(n) if all(r)]
    return n, full


def remove_rows(g, rows):
    kept = [r for i, r in enumerate(g) if i not in rows]
    return [[0] * COLS for _ in rows] + kept


def evaluate(g, cleared):
    heights, holes = [0] * COLS, 0
    for c in range(COLS):
        seen = False
        for r in range(ROWS):
            if g[r][c]:
                if not seen:
                    heights[c], seen = ROWS - r, True
            elif seen:
                holes += 1
    bump = sum(abs(heights[i] - heights[i + 1]) for i in range(COLS - 1))
    return -0.51 * sum(heights) + 0.76 * cleared - 0.36 * holes - 0.18 * bump


class Blocks(Game):
    key, title, accent = "blocks", "Block Stacker", "#b44cf5"
    rate_per_hour, run_typical = 550000, 100000
    tagline = "Stack, rotate and clear lines. Don't reach the top."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.mist = self.mistake(0.0)
        self.bag, self.lines_total, self.t = [], 0, 0
        self.bg_blocks = [[self.rng.uniform(0, LW), self.rng.uniform(0, LH), self.rng.uniform(0.2, 0.7), self.rng.choice(list(BCOL)),
                           self.rng.randrange(4)] for _ in range(16)]
        self.reset()

    def reset(self):
        self.begin_run()
        self.grid = [[0] * COLS for _ in range(ROWS)]
        self.next = None
        self.lines, self.level, self.over, self.over_t = 0, 1, False, 0
        self.clearing, self.clear_t, self.combo_txt = [], 0, ""
        self.spawn()

    def hud_extra(self):
        return [("LINES", fmt(self.lines)), ("LEVEL", str(self.level)), ("ATTEMPT", f"#{self.attempt}")]

    # ------------------------------------------------------------------ logic
    def draw7(self):
        if not self.bag:
            self.bag = list(SHAPES)
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def make(self, t):
        m = [r[:] for r in SHAPES[t]]
        return {"t": t, "m": m, "x": (COLS - len(m[0])) // 2, "y": -1}

    def choose(self, p):
        options, m = [], p["m"]
        for rot in range(4):
            for x in range(-2, COLS):
                if collides(self.grid, m, x, 0):
                    continue
                y = 0
                while not collides(self.grid, m, x, y + 1):
                    y += 1
                g, full = lock(self.grid, m, x, y, 1)
                options.append((evaluate(remove_rows(g, full), len(full)), rot, x))
            m = rotate(m)
        if not options:
            return {"rot": 0, "x": p["x"]}
        options.sort(reverse=True)
        if self.rng.random() < self.mist:
            s, rot, x = self.rng.choice(options)
        else:                                                    # usually the best spot, sometimes the 2nd/3rd best
            i = min(len(options) - 1, int(abs(self.h.noise(1.0))))
            s, rot, x = options[i]
        return {"rot": rot, "x": x}

    def spawn(self):
        self.piece = self.next or self.make(self.draw7())
        self.next = self.make(self.draw7())
        if collides(self.grid, self.piece["m"], self.piece["x"], self.piece["y"]):
            self.over, self.over_t = True, 0
            self.crashed()
            self.ctx.audio.sfx("crash")
            self.ctx.parts.burst(LW / 2, LH / 2, 40, [BCOL[k] for k in BCOL], speed=(1, 7), life=(30, 70), size=(3, 6), grav=0.15)
            return
        self.plan = self.choose(self.piece)
        h = self.h
        self.rots, self.act, self.grav = self.plan["rot"], 0, 0
        # a person studies the board for a moment before moving, presses keys at uneven intervals,
        # drops pieces either instantly or by holding down, and now and then fumbles one input
        think = h.rng.lognormvariate(math.log(24), 0.45) * max(0.45, 1 - 0.035 * self.level)
        self.think = max(5, int(think))
        self.gap = h.rng.randint(3, 7)
        self.hard = h.rng.random() < 0.4
        self.slip = h.rng.random() < h.chance(0.02, 0.14)

    def update(self):
        self.t += 1
        for b in self.bg_blocks:
            b[1] -= b[2]
            if b[1] < -60:
                b[0], b[1] = self.rng.uniform(0, LW), LH + 40
        if self.over:
            self.over_t += 1
            if self.over_t > 150:
                self.reset()
            return
        if self.clearing:
            self.clear_t += 1
            if self.clear_t >= CLEAR_FRAMES:
                self.grid = remove_rows(self.grid, self.clearing)
                self.clearing = []
                self.spawn()
            return
        p = self.piece
        h = self.h
        h.tick()
        self.level = self.lines // 10 + 1
        if self.think > 0:
            self.think -= 1                                       # studying the board
        else:
            self.act += 1
            if self.act >= self.gap:
                self.act, self.gap = 0, h.rng.randint(3, 7)
                want_x = p["x"] != self.plan["x"]
                step = 1 if self.plan["x"] > p["x"] else -1
                rot = rotate(p["m"]) if self.rots > 0 else None
                rot_ok = rot is not None and not collides(self.grid, rot, p["x"], p["y"])
                if self.slip and want_x:                          # fumble: tap the wrong direction once, then correct
                    self.slip = False
                    if not collides(self.grid, p["m"], p["x"] - step, p["y"]):
                        p["x"] -= step
                elif rot_ok and (not want_x or h.rng.random() < 0.5):
                    p["m"] = rot
                    self.rots -= 1
                elif want_x:                                      # (also used when a rotation is blocked at this spot)
                    if not collides(self.grid, p["m"], p["x"] + step, p["y"]):
                        p["x"] += step
                    else:
                        self.plan["x"] = p["x"]
                elif rot is not None:
                    self.rots -= 1                                # cannot rotate here: give up on it
        aligned = self.think <= 0 and self.rots == 0 and p["x"] == self.plan["x"]
        normal = max(5, 28 - self.level * 2)
        self.grav += 1
        if self.grav >= ((1 if self.hard else 2) if aligned else normal):
            self.grav = 0
            if not collides(self.grid, p["m"], p["x"], p["y"] + 1):
                p["y"] += 1
                return
            g, full = lock(self.grid, p["m"], p["x"], p["y"], p["t"])
            self.grid = g
            self.ctx.audio.sfx("lock")
            for i, row in enumerate(p["m"]):
                for j, v in enumerate(row):
                    if v:
                        self.ctx.parts.burst(BX0 + (p["x"] + j + .5) * CELL, BY0 + (p["y"] + i + 1) * CELL, 1, ["#ffffff"],
                                             speed=(0.3, 1.2), life=(10, 18), size=(1.5, 3), grav=0.02)
            if full:
                n = len(full)
                self.lines += n
                self.lines_total += n
                self.gain([0, 100, 300, 500, 800][n] * self.level + 4)
                self.ctx.audio.sfx(f"clear{min(4, n)}")
                self.combo_txt = ("", "", "DOUBLE!", "TRIPLE!", "BLOCK BLAST!")[min(4, n)]
                for r in full:
                    self.ctx.parts.burst(BX0 + COLS * CELL / 2, BY0 + (r + .5) * CELL, 14,
                                         ["#ffffff", "#19d9f0", "#ffd91a", "#b44cf5"], speed=(1, 6), life=(25, 45), size=(2, 4), grav=0.1)
                if self.lines // 10 + 1 > self.level:
                    self.ctx.toast(f"LEVEL {self.lines // 10 + 1}", "#19d9f0")
                    self.ctx.audio.sfx("levelup")
                self.clearing, self.clear_t = full, 0
            else:
                self.gain(4)
                self.spawn()

    # ------------------------------------------------------------------ sprites
    def cell_spr(self, cv, k, size=CELL, alpha=False):
        c = BCOL[k]

        def paint(p):
            s = size - 1
            p.rrect_grad(0, 0, s, s, 5, [(0, lighten(c, .38)), (.45, c), (1, darken(c, .32))])
            p.rrect(0, 0, s, s, 5, outline=darken(c, .45), width=1.2)
            lay = p.layer()
            lay.rrect(2.5, 2.5, s - 5, s * 0.28, 3, fill=(255, 255, 255, 105))
            lay.rrect(s * 0.18, s * 0.38, s * 0.64, s * 0.4, 3, fill=(255, 255, 255, 28))
            lay.rect(2, s - 5, s - 4, 3, fill=(0, 0, 0, 55))
            p.commit(lay)

        return cv.sprite(("blk_cell", k, size), size - 1, size - 1, paint, ss=3)

    def backdrop(self, cv):
        def paint(p):
            p.rrect_grad(0, 0, LW, LH, 0, [(0, "#06031a"), (.55, "#1a0a40"), (.78, "#4b0f63"), (1, "#14062c")])
            rnd = __import__("random").Random(9)
            for _ in range(120):
                x, y, r = rnd.uniform(0, LW), rnd.uniform(0, 400), rnd.choice([1, 1, 1.4, 2])
                p.ellipse(x, y, r, r, fill=(255, 255, 255, 255))

        return cv.sprite("blk_bg", LW, LH, paint, ss=1, mode="RGB")

    def sun(self, cv):
        def paint(p):
            p.glow(300, 300, 300, "#ff3caa", .55, 2)
            p.ellipse_grad(300, 300, 190, 190, [(0, "#ffe45e"), (.5, "#ff6aa8"), (1, "#b43cff")])
            for i in range(9):                                         # retro stripes cut into the sun
                y = 300 + i * 20
                p.rect(100, y, 400, 2 + i * 2.2, fill=(0, 0, 0, 0))

        return cv.sprite("blk_sun", 600, 600, paint, ss=1)

    def board(self, cv):
        w, h = COLS * CELL, ROWS * CELL

        def paint(p):
            p.rrect(0, 0, w + 24, h + 24, 10, fill=(5, 6, 24, 225))
            lay = p.layer()
            for i in range(COLS + 1):
                lay.line(12 + i * CELL, 12, 12 + i * CELL, 12 + h, (130, 120, 255, 28), 1)
            for i in range(ROWS + 1):
                lay.line(12, 12 + i * CELL, 12 + w, 12 + i * CELL, (130, 120, 255, 28), 1)
            lay.rrect(1, 1, w + 22, h + 22, 10, outline=(150, 200, 255, 210), width=2.5)
            p.commit(lay)

        return cv.sprite("blk_board", w + 24, h + 24, paint, ss=2)

    def neon(self, cv):
        from PIL import ImageFilter
        w, h = COLS * CELL + 24, ROWS * CELL + 24

        def paint(p):
            p.rrect(30, 30, w, h, 12, outline=(80, 200, 255, 255), width=8)
            return p.im.filter(ImageFilter.GaussianBlur(p.k * 9))

        return cv.sprite("blk_neon", w + 60, h + 60, paint, ss=1)

    # ------------------------------------------------------------------ drawing
    def draw(self, cv):
        s = cv.s
        cv.paste_bg(self.backdrop(cv))
        cv.blit(self.sun(cv), LW / 2, 470, "c")
        d = cv.d
        hor = 470                                                      # synthwave floor grid
        d.rectangle([0, hor * s, cv.w, cv.h], fill=(16, 4, 40, 235))
        for i in range(-14, 15):
            d.line([((LW / 2 + i * 22) * s, hor * s), ((LW / 2 + i * 190) * s, cv.h)], fill=(255, 60, 200, 110), width=max(1, int(1.5 * s)))
        for i in range(10):
            f = ((i + (self.t % 60) / 60) / 10) ** 2.2
            y = hor + f * (LH - hor)
            d.line([(0, y * s), (cv.w, y * s)], fill=(255, 60, 200, int(60 + 120 * f)), width=max(1, int(1.5 * s)))
        for x, y, v, k, rot in self.bg_blocks:
            cv.blit(self.cell_spr(cv, k, 26), x, y)
        if cv.fx >= 1:
            cv.blit(self.neon(cv), BX0 - 12 + (COLS * CELL + 24) / 2, BY0 - 12 + (ROWS * CELL + 24) / 2, "c")
        cv.blit(self.board(cv), BX0 - 12, BY0 - 12)

        for r in range(ROWS):
            for c in range(COLS):
                v = self.grid[r][c]
                if v:
                    cv.blit(self.cell_spr(cv, v), BX0 + c * CELL, BY0 + r * CELL)
        if self.clearing:
            a = int(230 * abs(math.sin(self.clear_t * 0.45)))
            for r in self.clearing:
                d.rectangle([BX0 * s, (BY0 + r * CELL) * s, (BX0 + COLS * CELL) * s, (BY0 + (r + 1) * CELL) * s], fill=(255, 255, 255, a))
            if self.combo_txt:
                cv.text(LW / 2, BY0 + self.clearing[0] * CELL - 6 - self.clear_t * 0.8, self.combo_txt, 36, "#ffe45e", "m", stroke=3)
        elif not self.over:
            p = self.piece
            gy = p["y"]
            while not collides(self.grid, p["m"], p["x"], gy + 1):
                gy += 1
            cs = self.cell_spr(cv, p["t"])
            for i, row in enumerate(p["m"]):
                for j, v in enumerate(row):
                    if v:
                        d.rounded_rectangle([(BX0 + (p["x"] + j) * CELL + 3) * s, (BY0 + (gy + i) * CELL + 3) * s,
                                             (BX0 + (p["x"] + j + 1) * CELL - 3) * s, (BY0 + (gy + i + 1) * CELL - 3) * s],
                                            radius=4 * s, outline=col(BCOL[p["t"]], 150), width=max(1, int(2 * s)))
                        if p["y"] + i >= 0:
                            cv.blit(cs, BX0 + (p["x"] + j) * CELL, BY0 + (p["y"] + i) * CELL)
        if self.next:                                                  # next-piece window
            cv.panel(828, 20, 134, 118, r=14, alpha=190)
            cv.text(895, 46, "NEXT", 18, "#9aa4d8", "m", shadow=1)
            m = self.next["m"]
            cs = self.cell_spr(cv, self.next["t"], 28)
            ox = 895 - len(m[0]) * 28 / 2
            oy = 58 + (66 - len(m) * 28) / 2
            for i, row in enumerate(m):
                for j, v in enumerate(row):
                    if v:
                        cv.blit(cs, ox + j * 28, oy + i * 28)
        if self.over:
            cv.d.rectangle([BX0 * s, BY0 * s, (BX0 + COLS * CELL) * s, (BY0 + ROWS * CELL) * s], fill=(0, 0, 0, 150))
            cv.text(LW / 2, LH / 2, "GAME OVER", 58, "#ff4757", "m", shadow=4, stroke=3)

    def icon(self, cv, size=96):
        return self.cell_spr(cv, "T", 60)
