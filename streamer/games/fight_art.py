"""Art for the fighting game: roster, skeleton poses, fighter drawing and stage backdrops (all drawn in code).

Every fighter is an original character. Poses are defined by joint angles (0 = pointing down, 90 = forward,
180 = up), so a new move only needs a few numbers.
"""
from __future__ import annotations

import math
import random

from ..gfx import LW, LH, col, darken, lighten, mix

SPR_W, SPR_H, OX, OY = 300, 280, 150, 250        # sprite size and where the feet touch the ground inside it
OUT = "#15121c"

ROSTER = [
    dict(name="KAITO", skin="#f1c27d", hair="#1b1b1f", style="spiky", top="#e53935", pants="#eceff1", trim="#b71c1c",
         shoes="#212121", glove="#e53935", band="#ffffff", accent="#ff5a4f", speed=3.4, dmg=1.0, hp=100, scale=1.0,
         ai=dict(aggr=0.55, zone=0.55, grab=0.25)),
    dict(name="NOVA", skin="#e0ac69", hair="#19c9ec", style="pony", top="#1e88e5", pants="#13315c", trim="#0d47a1",
         shoes="#eceff1", glove="#19c9ec", band=None, accent="#35c4ff", speed=4.1, dmg=0.92, hp=96, scale=0.97,
         ai=dict(aggr=0.8, zone=0.15, grab=0.1)),
    dict(name="BRICK", skin="#c68642", hair="#4e342e", style="beard", top="#fb8c00", pants="#4e342e", trim="#e65100",
         shoes="#3e2723", glove="#ffb300", band=None, accent="#ffa726", speed=2.7, dmg=1.22, hp=118, scale=1.12,
         ai=dict(aggr=0.5, zone=0.1, grab=0.6)),
    dict(name="ZEPHYR", skin="#f1c27d", hair="#1f3d2b", style="scarf", top="#2e7d32", pants="#1b3b2a", trim="#a5d6a7",
         shoes="#1b1b1b", glove="#66bb6a", band=None, accent="#66e08a", speed=3.7, dmg=0.95, hp=100, scale=1.0,
         ai=dict(aggr=0.4, zone=0.85, grab=0.15)),
    dict(name="LUNA", skin="#ffdbac", hair="#8e24aa", style="long", top="#7e57c2", pants="#311b92", trim="#d1c4e9",
         shoes="#ede7f6", glove="#ce93d8", band=None, accent="#c77dff", speed=3.9, dmg=1.0, hp=98, scale=0.98,
         ai=dict(aggr=0.65, zone=0.3, grab=0.15)),
    dict(name="SABLE", skin="#8d5524", hair="#000000", style="bald", top="#37474f", pants="#212121", trim="#ffd54f",
         shoes="#111111", glove="#ffd54f", band="#ffd54f", accent="#ffd54f", speed=3.2, dmg=1.05, hp=104, scale=1.04,
         ai=dict(aggr=0.5, zone=0.4, grab=0.3)),
]

DEF = dict(lean=3, head=0, tf=12, sf=4, tb=-16, sb=-6, uf=30, ff=100, ub=20, fb=115, hip=None, face="n", sag=0)

POSES = {
    "idle0": {},
    "idle1": dict(lean=5, tf=16, sf=8, tb=-18, sb=-8, sag=4, uf=34, ff=104, ub=24, fb=118),
    "walk0": dict(tf=34, sf=12, tb=-26, sb=-44, uf=45, ff=100, ub=15, fb=110),
    "walk1": dict(tf=12, sf=4, tb=-12, sb=-6),
    "walk2": dict(tf=-26, sf=-46, tb=34, sb=12, uf=20, ff=105, ub=40, fb=105),
    "walk3": dict(tf=10, sf=4, tb=-10, sb=-4),
    "jump": dict(lean=0, tf=62, sf=6, tb=28, sb=-24, uf=75, ff=150, ub=55, fb=140),
    "fall": dict(lean=4, tf=40, sf=10, tb=10, sb=-10, uf=60, ff=130, ub=40, fb=120),
    "crouch": dict(lean=14, head=6, tf=84, sf=-4, tb=76, sb=-30, uf=40, ff=112, ub=30, fb=122),
    "block": dict(lean=-2, tf=8, sf=0, tb=-12, sb=-2, uf=62, ff=172, ub=50, fb=160),
    "cblock": dict(lean=12, head=4, tf=84, sf=-4, tb=76, sb=-30, uf=62, ff=172, ub=50, fb=160),
    "p_su": dict(lean=2, uf=-25, ff=30, ub=35, fb=120),
    "p_ac": dict(lean=14, tf=24, tb=-22, uf=88, ff=90, ub=28, fb=118),
    "p2_su": dict(lean=2, ub=-25, fb=30, uf=35, ff=105),
    "p2_ac": dict(lean=14, tf=24, tb=-22, ub=88, fb=90, uf=30, ff=105),
    "k_su": dict(lean=-4, tf=78, sf=4, tb=-8, sb=-2, uf=45, ff=140, ub=30, fb=150),
    "k_ac": dict(lean=-12, tf=88, sf=88, tb=-8, sb=-2, uf=40, ff=150, ub=-20, fb=100),
    "sw_su": dict(lean=14, head=6, tf=84, sf=-4, tb=76, sb=-30, uf=30, ff=100),
    "sw_ac": dict(lean=8, head=4, tf=72, sf=84, tb=80, sb=-24, uf=-10, ff=80, ub=-30, fb=60),
    "ax_su": dict(lean=-10, tf=165, sf=160, tb=-6, sb=-2, uf=70, ff=150, ub=-20, fb=100),
    "ax_ac": dict(lean=8, tf=118, sf=45, tb=-6, sb=-2, uf=60, ff=120, ub=40, fb=100),
    "up_su": dict(lean=-2, tf=50, sf=10, tb=-30, sb=-30, uf=-10, ff=60, ub=30, fb=110, sag=10),
    "up_ac": dict(lean=2, tf=30, sf=4, tb=-12, sb=-2, uf=175, ff=178, ub=40, fb=120),
    "th": dict(lean=14, tf=30, tb=-24, sb=-4, uf=86, ff=92, ub=80, fb=98),
    "fire_su": dict(lean=0, tf=40, sf=4, tb=-30, sb=-10, uf=10, ff=110, ub=10, fb=110),
    "fire_ac": dict(lean=14, tf=44, sf=4, tb=-34, sb=-8, uf=88, ff=90, ub=86, fb=92),
    "sup_su": dict(lean=-6, tf=20, tb=-22, uf=150, ff=176, ub=150, fb=176),
    "sup_ac": dict(lean=16, tf=50, sf=6, tb=-36, sb=-8, uf=90, ff=90, ub=88, fb=92),
    "jk": dict(lean=-8, tf=84, sf=80, tb=30, sb=-10, uf=50, ff=130, ub=40, fb=120),
    "hit": dict(lean=-12, head=-8, tf=6, sf=2, tb=-20, sb=-10, uf=-30, ff=20, ub=-40, fb=10, face="hit"),
    "hit2": dict(lean=-20, head=-10, tf=14, tb=-8, sb=-20, uf=-40, ff=10, ub=-50, fb=0, face="hit"),
    "bhit": dict(lean=-4, tf=10, sf=2, tb=-14, sb=-4, uf=62, ff=172, ub=50, fb=160),
    "fly": dict(lean=-50, head=-8, tf=70, sf=50, tb=40, sb=20, uf=-60, ff=-30, ub=-70, fb=-20, face="hit"),
    "lie": dict(lean=-90, head=-4, tf=86, sf=88, tb=78, sb=84, uf=-80, ff=-70, ub=-60, fb=-30, hip=18, face="ko"),
    "getup": dict(lean=20, tf=84, sf=-4, tb=76, sb=-30, uf=40, ff=110, ub=30, fb=120, face="hit"),
    "win": dict(lean=0, uf=170, ff=176, ub=22, fb=112, face="win"),
    "taunt": dict(lean=-2, uf=60, ff=170, ub=62, fb=172, face="win"),
}


def _v(a, l):
    r = math.radians(a)
    return math.sin(r) * l, math.cos(r) * l


def _limb(p, a, b, w, color):
    for c, ww in ((OUT, w + 5), (color, w)):
        p.line(a[0], a[1], b[0], b[1], c, ww)
        p.ellipse(a[0], a[1], ww / 2, ww / 2, fill=c)
        p.ellipse(b[0], b[1], ww / 2, ww / 2, fill=c)


def draw_fighter(p, sp, pose, S):
    d = dict(DEF)
    d.update(POSES[pose])
    rad = math.radians
    UA, FA, TH, SN, TL = 38 * S, 34 * S, 52 * S, 52 * S, 60 * S

    def ext(t, s):
        return TH * math.cos(rad(t)) + SN * math.cos(rad(s))

    hip_h = d["hip"] * S if d["hip"] is not None else max(ext(d["tf"], d["sf"]), ext(d["tb"], d["sb"])) - d["sag"] * S
    hx, hy = OX, OY - hip_h
    lean = d["lean"]
    tx, ty = math.sin(rad(lean)) * TL, math.cos(rad(lean)) * TL
    neck = (hx + tx, hy - ty)
    sh = (hx + tx * 0.86, hy - ty * 0.86)
    skin, top, pants = sp["skin"], sp["top"], sp["pants"]

    def arm(ua, fa, dark):
        e = _v(ua, UA)
        el = (sh[0] + e[0], sh[1] + e[1])
        f = _v(fa, FA)
        ha = (el[0] + f[0], el[1] + f[1])
        k = 0.28 if dark else 0.0
        _limb(p, sh, el, 14 * S, darken(top, k))
        _limb(p, el, ha, 12 * S, darken(skin, k))
        p.ellipse(ha[0], ha[1], 10.5 * S, 10.5 * S, fill=darken(sp["glove"], k), outline=OUT, width=2)

    def leg(t, s, dx, dark):
        hp = (hx + dx * S, hy)
        kn = (hp[0] + _v(t, TH)[0], hp[1] + _v(t, TH)[1])
        ft = (kn[0] + _v(s, SN)[0], kn[1] + _v(s, SN)[1])
        k = 0.28 if dark else 0.0
        _limb(p, hp, kn, 20 * S, darken(pants, k))
        _limb(p, kn, ft, 16 * S, darken(pants, k))
        p.ellipse(ft[0] + 6 * S, ft[1] - 3 * S, 15 * S, 8.5 * S, fill=darken(sp["shoes"], k), outline=OUT, width=2)

    # long hair sits behind everything
    hc = (neck[0] + tx / TL * 14 * S + d["head"] * S, neck[1] - ty / TL * 14 * S - 5 * S)
    HR = 18 * S
    if sp["style"] == "long":
        p.ellipse(hc[0] - 10 * S, hc[1] + 18 * S, 18 * S, 32 * S, fill=sp["hair"], outline=OUT, width=2)
    if sp["style"] == "pony":
        sw = -6 * S if lean > 0 else 4 * S
        p.ellipse(hc[0] - 26 * S, hc[1] + 2 * S + sw, 16 * S, 8 * S, fill=sp["hair"], outline=OUT, width=2)
        p.ellipse(hc[0] - 38 * S, hc[1] + 10 * S + sw, 9 * S, 6 * S, fill=sp["hair"], outline=OUT, width=2)

    arm(d["ub"], d["fb"], True)
    leg(d["tb"], d["sb"], -4, True)

    # torso, belt
    _limb(p, (hx, hy), neck, 38 * S, top)
    bc = (hx + tx * 0.1, hy - ty * 0.1)
    p.line(bc[0] - 17 * S, bc[1] + 1 * S, bc[0] + 17 * S, bc[1] - 1 * S, sp["trim"], 9 * S)
    mid = (hx + tx * 0.55, hy - ty * 0.55)
    p.line(mid[0] - 3 * S, mid[1] - 20 * S, mid[0] + 3 * S, mid[1] + 18 * S, darken(top, 0.18), 4 * S)

    # head
    p.ellipse(hc[0], hc[1], HR, HR, fill=skin, outline=OUT, width=2.5)
    st = sp["style"]
    if st == "spiky":
        for a in (-75, -40, -5, 30, 62):
            ca, sa = math.sin(rad(a)), -math.cos(rad(a))
            b1 = (hc[0] + math.sin(rad(a - 16)) * HR * 0.95, hc[1] - math.cos(rad(a - 16)) * HR * 0.95)
            b2 = (hc[0] + math.sin(rad(a + 16)) * HR * 0.95, hc[1] - math.cos(rad(a + 16)) * HR * 0.95)
            tip = (hc[0] + ca * HR * 1.7 - 4 * S, hc[1] + sa * HR * 1.7 + 2 * S)
            p.poly([b1, tip, b2], fill=sp["hair"], outline=OUT)
        p.ellipse(hc[0] - 1 * S, hc[1] - 10 * S, HR * 1.02, HR * 0.5, fill=sp["hair"])
    elif st in ("pony", "long", "scarf"):
        p.ellipse(hc[0] - 1 * S, hc[1] - 10 * S, HR * 1.04, HR * 0.52, fill=sp["hair"], outline=OUT, width=1.5)
        p.ellipse(hc[0] + 6 * S, hc[1] - 13 * S, HR * 0.5, HR * 0.28, fill=lighten(sp["hair"], 0.25))
    elif st == "beard":
        p.ellipse(hc[0] + 1 * S, hc[1] - 12 * S, HR * 0.95, HR * 0.5, fill=sp["hair"])
        p.ellipse(hc[0] + 4 * S, hc[1] + 12 * S, 13 * S, 9 * S, fill=sp["hair"], outline=OUT, width=1.5)
    if st == "scarf":
        p.line(neck[0] - 2 * S, neck[1] + 2 * S, neck[0] + 10 * S, neck[1] + 2 * S, sp["trim"], 10 * S)
        tailx = neck[0] - 12 * S
        p.poly([(neck[0] - 2 * S, neck[1] - 3 * S), (tailx - 26 * S, neck[1] + 8 * S + (3 * S if lean > 8 else 12 * S)),
                (tailx - 18 * S, neck[1] + 16 * S), (neck[0] - 2 * S, neck[1] + 7 * S)], fill=sp["trim"], outline=OUT)
    if sp["band"]:
        by = hc[1] - 11 * S
        p.line(hc[0] - HR * 0.98, by, hc[0] + HR * 0.98, by, sp["band"], 5 * S)
        p.poly([(hc[0] - HR, by - 2 * S), (hc[0] - HR - 15 * S, by - 6 * S), (hc[0] - HR - 12 * S, by + 6 * S)], fill=sp["band"], outline=OUT)

    # face
    ex, ey = hc[0] + 8 * S, hc[1] - 1 * S
    face = d["face"]
    if face in ("hit", "ko"):
        for dx in (0, -10 * S):
            p.line(ex + dx - 3 * S, ey - 3 * S, ex + dx + 3 * S, ey + 3 * S, OUT, 2 * S)
            p.line(ex + dx - 3 * S, ey + 3 * S, ex + dx + 3 * S, ey - 3 * S, OUT, 2 * S)
        p.ellipse(hc[0] + 9 * S, hc[1] + 9 * S, 4 * S, 5 * S, fill="#4a1218", outline=OUT, width=1.2)
    elif face == "win":
        p.line(ex - 4 * S, ey + 1 * S, ex, ey - 3 * S, OUT, 2 * S)
        p.line(ex, ey - 3 * S, ex + 4 * S, ey + 1 * S, OUT, 2 * S)
        p.ellipse(hc[0] + 9 * S, hc[1] + 8 * S, 6 * S, 4.5 * S, fill="#ffffff", outline=OUT, width=1.2)
    else:
        p.ellipse(ex, ey, 4.6 * S, 4 * S, fill="#ffffff", outline=OUT, width=1.2)
        p.ellipse(ex + 1.5 * S, ey, 2.2 * S, 2.4 * S, fill=OUT)
        p.line(ex - 5 * S, ey - 6 * S, ex + 5 * S, ey - 4 * S, OUT, 2.2 * S)
        p.line(hc[0] + 5 * S, hc[1] + 10 * S, hc[0] + 13 * S, hc[1] + 10 * S, OUT, 2 * S)

    leg(d["tf"], d["sf"], 4, False)
    arm(d["uf"], d["ff"], False)


def build_fighter(p, sp, pose):
    draw_fighter(p, sp, pose, sp["scale"])


# ---------------------------------------------------------------------------------------------- stages
STAGE_NAMES = ["ROOFTOP DUSK", "DOJO NIGHT", "HARBOR DAWN"]
HORIZON = 470


def _windows(p, rnd, x, y, w, h, lit):
    cols = int(w // 16)
    rows = int(h // 20)
    for i in range(cols):
        for j in range(rows):
            if rnd.random() < 0.45:
                p.rect(x + 6 + i * 16, y + 8 + j * 20, 8, 10, fill=lit if rnd.random() < 0.8 else "#ffe9a8")


def _floor_lines(p, base, hi, lines_col, vx=640):
    p.rrect_grad(0, HORIZON, LW, LH - HORIZON, 0, [(0, base), (1, hi)])
    for i in range(-14, 15):
        p.line(vx + i * 26, HORIZON, vx + i * 210, LH, lines_col, 2)
    for j in range(1, 9):
        y = HORIZON + ((j / 8) ** 1.8) * (LH - HORIZON)
        p.line(0, y, LW, y, lines_col, 2)


def stage_rooftop(p):
    p.rrect_grad(0, 0, LW, LH, 0, [(0, "#2b1055"), (0.3, "#7a2d7e"), (0.5, "#e8587a"), (0.66, "#ffb36b"), (1, "#ffcf9a")])
    p.glow(900, 340, 340, "#ffd9a0", 0.65, 1.8)
    p.ellipse(900, 340, 74, 74, fill="#fff1c9")
    rnd = random.Random(3)
    for color, lit, hmin, hmax, wmin, wmax in (("#6a3470", "#8a5a8e", 140, 320, 50, 110), ("#3a1d4d", "#ffcf6b", 90, 250, 60, 130)):
        x = -30
        while x < LW:
            w, h = rnd.uniform(wmin, wmax), rnd.uniform(hmin, hmax)
            p.rect(x, HORIZON - h, w, h + 4, fill=color)
            _windows(p, rnd, x, HORIZON - h, w, h, lit)
            x += w + rnd.uniform(0, 8)
    p.rect(0, HORIZON - 16, LW, 30, fill="#2a2433")
    p.rect(0, HORIZON - 16, LW, 5, fill="#4b4258")
    _floor_lines(p, "#7a7388", "#34303f", "#625b73")
    for x in range(30, LW, 110):                     # railing posts
        p.rect(x, HORIZON - 52, 7, 40, fill="#1d1824")
    p.rect(0, HORIZON - 54, LW, 6, fill="#1d1824")


def stage_dojo(p):
    p.rrect_grad(0, 0, LW, HORIZON, 0, [(0, "#1a0f14"), (1, "#3a2218")])
    for x in range(0, LW, 64):                       # wall planks
        p.rect(x, 0, 3, HORIZON, fill="#120a0e")
    for cx in (200, 640, 1080):                      # shoji windows with moon light
        p.glow(cx, 240, 230, "#ffd9a0", 0.35, 1.6)
        p.rrect(cx - 150, 70, 300, 330, 8, fill="#f3e3c3", outline="#2a1810", width=8)
        for i in range(1, 4):
            p.rect(cx - 150 + i * 75 - 2, 70, 4, 330, fill="#2a1810")
        for j in range(1, 5):
            p.rect(cx - 150, 70 + j * 66 - 2, 300, 4, fill="#2a1810")
    p.ellipse(640, 200, 46, 46, fill="#fff7d8")
    for cx in (80, 420, 860, 1200):                  # lanterns
        p.line(cx, 0, cx, 90, "#2a1810", 3)
        p.glow(cx, 125, 90, "#ff6a3d", 0.8, 1.7)
        p.rrect(cx - 26, 90, 52, 70, 22, fill="#d6362a", outline="#7a1410", width=3)
        p.rect(cx - 14, 88, 28, 8, fill="#2a1810")
        p.rect(cx - 14, 156, 28, 8, fill="#2a1810")
    p.rect(0, HORIZON - 22, LW, 30, fill="#24130d")
    p.rrect_grad(0, HORIZON, LW, LH - HORIZON, 0, [(0, "#7a4a2a"), (1, "#3d2315")])
    for j in range(1, 14):                           # floor planks
        y = HORIZON + ((j / 14) ** 1.7) * (LH - HORIZON)
        p.line(0, y, LW, y, "#2c180d", 2)
    for i in range(-16, 17):
        p.line(640 + i * 24, HORIZON, 640 + i * 150, LH, "#33200f", 2)
    lay = p.layer()
    lay.rrect_grad(0, HORIZON + 6, LW, 70, 0, [(0, (255, 220, 160, 60)), (1, (255, 220, 160, 0))])
    p.commit(lay)


def stage_harbor(p):
    p.rrect_grad(0, 0, LW, 400, 0, [(0, "#1b2a5e"), (0.45, "#8a5a9e"), (0.8, "#ff9a7a"), (1, "#ffd9a0")])
    p.glow(640, 400, 380, "#ffe2a8", 0.75, 1.7)
    p.ellipse(640, 400, 90, 90, fill="#fff2cf")
    p.rrect_grad(0, 400, LW, 120, 0, [(0, "#f0a98a"), (1, "#27415f")])
    rnd = random.Random(8)
    lay = p.layer()
    for _ in range(70):
        y = rnd.uniform(404, 515)
        w = rnd.uniform(40, 220) * (0.4 + (y - 400) / 140)
        cx = 640 + rnd.uniform(-1, 1) * (160 + (y - 400) * 1.4)
        lay.rrect(cx - w / 2, y, w, 3, 1.5, fill=(255, 235, 190, 90))
    p.commit(lay)
    for cx in (120, 1130):                           # cranes
        p.rect(cx, 150, 14, 330, fill="#232a3d")
        p.rect(cx - 150, 150, 330, 12, fill="#232a3d")
        p.line(cx + 7, 150, cx - 140, 162, "#232a3d", 4)
        p.line(cx - 140, 162, cx - 140, 250, "#232a3d", 3)
    for i, (x, c) in enumerate(((20, "#c0392b"), (150, "#2980b9"), (1040, "#27ae60"), (1160, "#e67e22"))):
        p.rect(x, 360, 120, 110, fill=c)
        for k in range(1, 8):
            p.line(x + k * 15, 360, x + k * 15, 470, darken(c, 0.25), 3)
        p.rect(x, 360, 120, 6, fill=darken(c, 0.3))
    p.rect(0, 500, LW, 20, fill="#1a2236")
    _floor_lines(p, "#6c7384", "#2a3040", "#59607a", vx=640)
    for x in range(120, LW, 260):                    # bollards
        p.rrect(x, 530, 22, 20, 6, fill="#222633")


STAGE_FUNCS = [stage_rooftop, stage_dojo, stage_harbor]


def icon(p):
    p.glow(45, 45, 45, "#ff5a4f", 0.7, 2)
    p.rrect_grad(14, 14, 56, 54, 20, [(0, "#ff8a7a"), (0.5, "#e53935"), (1, "#a31f1c")])
    p.rrect(14, 14, 56, 54, 20, outline="#5a0f0d", width=3)
    p.rrect(18, 62, 48, 18, 6, fill="#f5f5f5", outline="#5a0f0d", width=3)
    for x in (30, 42, 54):
        p.line(x, 30, x, 46, "#5a0f0d", 2.5)
    lay = p.layer()
    lay.rrect(22, 20, 14, 22, 6, fill=(255, 255, 255, 110))
    p.commit(lay)
