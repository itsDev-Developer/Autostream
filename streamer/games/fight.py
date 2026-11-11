"""Street Clash - an original 2D fighting game: six invented fighters, three stages, best-of-three rounds,
60-second timer, super meter, combos, blocks, throws and projectiles.

The two fighters are controlled by human-like players (reaction time, guesses, mistakes). The champion stays
on and fights a new challenger after each match; the score is the champion's streak points.
"""
from __future__ import annotations

import math
from collections import OrderedDict, deque

from PIL import Image, ImageChops

from ..gfx import LW, LH, Painter, LANCZOS, col, darken, ease_out, fmt, lighten
from . import fight_art as art
from .base import Game

_T = getattr(Image, "Transpose", Image)
GROUND = 610
WALL_L, WALL_R = 90, 1190
GRAV = 0.9
ROUND_FRAMES = 60 * 60

ATK = {
    "punch": dict(su=5, ac=3, rc=8, dmg=6, h="high", reach=92, hs=16, bs=9, kb=4, mg=7, chain=("kick", "heavy", "fire", "super")),
    "kick": dict(su=8, ac=4, rc=12, dmg=9, h="mid", reach=120, hs=19, bs=11, kb=7, mg=9, chain=("heavy", "sweep", "fire", "super")),
    "heavy": dict(su=9, ac=5, rc=20, dmg=13, h="mid", reach=88, hs=26, bs=14, kb=5, mg=12, launch=True, chain=()),
    "sweep": dict(su=9, ac=4, rc=17, dmg=8, h="low", reach=128, hs=24, bs=12, kb=6, mg=8, launch=True, chain=()),
    "axe": dict(su=16, ac=5, rc=18, dmg=11, h="over", reach=102, hs=22, bs=14, kb=6, mg=10, chain=()),
    "throw": dict(su=6, ac=2, rc=24, dmg=13, h="throw", reach=80, hs=30, bs=0, kb=8, mg=12, launch=True, chain=()),
    "fire": dict(su=14, ac=2, rc=22, dmg=7, h="mid", reach=0, hs=20, bs=10, kb=5, mg=6, proj="wave", chain=()),
    "super": dict(su=30, ac=2, rc=30, dmg=26, h="mid", reach=0, hs=40, bs=14, kb=9, mg=0, proj="mega", launch=True, chain=()),
    "jkick": dict(su=0, ac=22, rc=0, dmg=8, h="air", reach=96, hs=18, bs=10, kb=6, mg=8, chain=()),
}
APOSE = {"punch": ("p_su", "p_ac", "p_su"), "kick": ("k_su", "k_ac", "k_su"), "heavy": ("up_su", "up_ac", "up_su"),
         "sweep": ("sw_su", "sw_ac", "sw_su"), "axe": ("ax_su", "ax_ac", "ax_su"), "throw": ("th", "th", "th"),
         "fire": ("fire_su", "fire_ac", "fire_su"), "super": ("sup_su", "sup_ac", "sup_su"), "jkick": ("jk", "jk", "jk")}


def wchoice(rng, weights):
    total = sum(weights.values())
    r = rng.random() * total
    for k, v in weights.items():
        r -= v
        if r <= 0:
            return k
    return k


def v_range(h, S, y):
    if h == "high":
        return y + 112 * S, y + 190 * S
    if h == "mid":
        return y + 55 * S, y + 150 * S
    if h == "low":
        return y, y + 45 * S
    if h == "over":
        return y + 85 * S, y + 190 * S
    if h == "air":
        return y + 10 * S, y + 100 * S
    return y, y + 170 * S


class Intent:
    __slots__ = ("move", "crouch", "block", "jump", "atk")

    def __init__(self):
        self.move, self.crouch, self.block, self.jump, self.atk = 0, False, False, False, None


class Fighter:
    def __init__(self, spec, game):
        self.spec, self.g = spec, game
        self.wins = 0
        self.meter = 0.0
        self.reset_round(0, 1)

    @property
    def S(self):
        return self.spec["scale"]

    def reset_round(self, x, face):
        self.x, self.y, self.vy, self.vx = float(x), 0.0, 0.0, 0.0
        self.face = face
        self.hp = self.maxhp = float(self.spec["hp"])
        self.lag = self.hp
        self.state, self.t, self.sub = "ready", 0, ""
        self.atk, self.alt, self.connected, self.hit_done, self.air_atk, self.air_used = None, False, False, False, False, False
        self.stun, self.blocked_stun, self.kbx = 0, False, 0.0
        self.guard = self.crouching = False
        self.mv = 0
        self.combo_n = 0
        self.fire_cd = 0
        self.ko = False

    # ------------------------------------------------------------------ actions
    def start_attack(self, name, cancel=False):
        if name == "fire" and self.fire_cd > 0:
            return False
        if name == "super" and self.meter < 100:
            return False
        a = ATK[name]
        self.state, self.atk, self.t = "attack", name, 0
        self.connected = self.hit_done = False
        self.air_atk = False
        self.mv = 0
        if name == "punch":
            self.alt = not self.alt
        if name == "fire":
            self.fire_cd = 75
        if name == "super":
            self.meter = 0.0
            self.g.begin_freeze(self)
        return True

    def air_phys(self):
        self.y += self.vy
        self.vy -= GRAV
        self.x += self.vx
        if self.y <= 0:
            self.y, self.vy, self.vx = 0.0, 0.0, 0.0
            return True
        return False

    def update(self, opp, it, g):
        self.t += 1
        self.fire_cd = max(0, self.fire_cd - 1)
        if abs(self.kbx) > 0.15:
            self.x += self.kbx
            self.kbx *= 0.84
        else:
            self.kbx = 0.0
        s = self.state
        if s == "ready":
            self.face = 1 if opp.x >= self.x else -1
            self.guard, self.crouching, self.mv = bool(it.block), bool(it.crouch), 0
            if it.atk and self.start_attack(it.atk):
                pass
            elif it.jump and not self.crouching:
                self.state, self.t, self.vy = "air", 0, 16.0
                self.vx = it.move * self.spec["speed"] * 1.2 * self.face
                self.air_used = False
            elif not self.crouching:
                spd = self.spec["speed"] * (1.0 if it.move > 0 else 0.72) * (0.6 if self.guard else 1.0)
                self.x += self.face * it.move * spd
                self.mv = it.move
        elif s == "air":
            if self.air_phys():
                self.state, self.t = "ready", 0
            elif it.atk == "jkick" and not self.air_used and self.y > 25 and self.vy < 6:
                self.air_used = True
                self.state, self.atk, self.t = "attack", "jkick", 0
                self.connected = self.hit_done = False
                self.air_atk = True
        elif s == "attack":
            a = ATK[self.atk]
            if a.get("proj") and self.t == a["su"]:
                g.spawn_proj(self, self.atk)
            if self.air_atk:
                if self.air_phys():
                    self.state, self.t, self.air_atk, self.atk = "ready", 0, False, None
                elif self.t >= a["su"] + a["ac"]:
                    self.state, self.t, self.atk = "air", 0, None
            else:
                end = a["su"] + a["ac"] + a["rc"]
                if self.t >= end:
                    self.state, self.t, self.atk = "ready", 0, None
                elif (self.connected and a["chain"] and a["su"] + a["ac"] <= self.t < a["su"] + a["ac"] + 6
                      and it.atk in a["chain"]):
                    self.start_attack(it.atk, cancel=True)
        elif s == "hit":
            if self.t >= self.stun:
                self.state, self.t, self.blocked_stun, self.combo_n = "ready", 0, False, 0
        elif s == "down":
            if self.sub == "fly":
                if self.air_phys():
                    self.sub, self.t = "lie", 0
                    g.thud(self)
            elif self.sub == "lie":
                if not self.ko and self.t >= 34:
                    self.sub, self.t = "getup", 0
            elif self.sub == "getup" and self.t >= 18:
                self.state, self.t, self.sub, self.combo_n = "ready", 0, "", 0
        self.x = max(WALL_L, min(WALL_R, self.x))

    # ------------------------------------------------------------------ queries
    def hurt_range(self):
        S = self.S
        top = 100 * S if (self.state == "ready" and self.crouching) or self.state == "attack" and self.atk == "sweep" else 178 * S
        return self.y, self.y + top

    def hittable(self):
        return self.state in ("ready", "attack", "air", "hit")

    def pose_name(self, tick):
        s = self.state
        if s == "ready":
            if self.guard:
                return "cblock" if self.crouching else "block"
            if self.crouching:
                return "crouch"
            if self.mv != 0:
                i = (self.t // 6) % 4
                seq = ("walk0", "walk1", "walk2", "walk3")
                return seq[i] if self.mv > 0 else seq[3 - i]
            return "idle0" if (tick // 28) % 2 == 0 else "idle1"
        if s == "air":
            return "jump" if self.vy > 0 else "fall"
        if s == "attack":
            a = ATK[self.atk]
            ph = 0 if self.t < a["su"] else (1 if self.t < a["su"] + a["ac"] else 2)
            names = APOSE[self.atk]
            if self.atk == "punch" and not self.alt:
                names = ("p2_su", "p2_ac", "p2_su")
            return names[ph]
        if s == "hit":
            if self.blocked_stun:
                return "cblock" if self.crouching else "block"
            return "hit" if self.t < 8 else "hit2"
        if s == "down":
            return {"fly": "fly", "lie": "lie", "getup": "getup"}[self.sub]
        if s == "win":
            return "win"
        return "idle0"


class Brain:
    """Human-like fighter: sees the opponent a reaction-time late, guesses blocks, mixes up attacks."""

    def __init__(self, g, me):
        self.g, self.me = g, me
        self.hist = deque(maxlen=40)
        self.react = g.h.reaction(8, 12)
        self.plan, self.plan_until = "wait", 0
        self.guard_until, self.guard_crouch = 0, False
        self.seen_proj = set()

    def in_range(self, name, dist):
        return dist <= ATK[name]["reach"] * 0.95

    def think(self, op, it):
        g, me, h, rng = self.g, self.me, self.g.h, self.g.rng
        now = g.t
        self.hist.append((op.state, op.atk, op.y > 0))
        if me.state not in ("ready", "attack", "air"):
            return
        dist = abs(op.x - me.x)
        if me.state == "attack":
            self.chain(op, it, dist)
            return
        if me.state == "air":
            if me.vy < 0 and dist < 130 and not me.air_used and rng.random() < 0.2:
                it.atk = "jkick"
            return
        if now < self.guard_until:
            it.block, it.crouch = True, self.guard_crouch
            return
        st, atk, op_air = self.hist[max(0, len(self.hist) - 1 - self.react)]
        if st == "attack" and atk in ATK and ATK[atk]["h"] != "throw" and not ATK[atk].get("proj") \
                and dist < ATK[atk]["reach"] + 70:
            if rng.random() < 0.5 + 0.45 * h.skill:
                a = ATK[atk]
                crouch = a["h"] == "low" or (a["h"] != "over" and rng.random() < 0.18)
                if rng.random() < 0.04 + 0.25 * (1 - h.skill):
                    crouch = not crouch                     # guessed the wrong height
                self.guard_until = now + a["su"] + a["ac"] + a["rc"] // 2 + 6
                self.guard_crouch = crouch
                it.block, it.crouch = True, crouch
                return
        for pr in g.projs:
            if pr["owner"] is me or id(pr) in self.seen_proj:
                continue
            d = abs(pr["x"] - me.x)
            if (me.x - pr["x"]) * pr["vx"] > 0 and d < 360:
                self.seen_proj.add(id(pr))
                if pr["kind"] == "wave" and rng.random() < 0.4:
                    it.jump, it.move = True, 1
                else:
                    self.guard_until = now + int(d / abs(pr["vx"])) + 16
                    self.guard_crouch = False
                    it.block = True
                return
        if op_air and dist < 200 and rng.random() < 0.3:
            it.atk = "heavy"
            return
        if now >= self.plan_until:
            self.choose_plan(op, dist)
        self.run_plan(op, it, dist)

    def own_proj(self):
        return any(p["owner"] is self.me for p in self.g.projs)

    def choose_plan(self, op, dist):
        g, me, rng = self.g, self.me, self.g.rng
        ai = me.spec["ai"]
        can_fire = me.fire_cd <= 0 and not self.own_proj()
        if dist > 450:
            w = {"approach": 0.55, "jump_in": 0.12, "wait": 0.08}
            if can_fire:
                w["zone"] = ai["zone"] * 1.4
        elif dist > 240:
            w = {"approach": 0.35 + 0.3 * ai["aggr"], "poke": 0.25, "wait": 0.12, "retreat": 0.1 * (1 - ai["aggr"]),
                 "jump_in": 0.1}
            if can_fire:
                w["zone"] = ai["zone"] * 0.7
        else:
            w = {"mix": 0.35 + 0.5 * ai["aggr"], "poke": 0.25, "retreat": 0.2 * (1 - ai["aggr"]) + 0.05, "wait": 0.12,
                 "guard": 0.15}
        if me.meter >= 100 and dist < 560:
            w["super"] = 0.6
        self.plan = wchoice(rng, w)
        self.plan_until = g.t + rng.randint(14, 42)
        if rng.random() < 0.01:
            self.react = g.h.reaction(8, 12)

    def run_plan(self, op, it, dist):
        g, me, rng = self.g, self.me, self.g.rng
        ai, p = me.spec["ai"], self.plan
        if p == "approach":
            it.move = 1
            if dist < 150:
                self.plan_until = 0
        elif p == "retreat":
            it.move = -1
        elif p == "guard":
            it.block = True
            it.crouch = rng.random() < 0.3
            self.guard_until, self.guard_crouch = g.t + 1, it.crouch
        elif p == "zone":
            if me.fire_cd <= 0:
                it.atk = "fire"
            self.plan_until = 0
        elif p == "jump_in":
            it.jump, it.move = True, 1
            self.plan_until = g.t + 40
        elif p == "poke":
            if dist <= ATK["kick"]["reach"] - 12:
                it.atk = wchoice(rng, {"kick": 0.45, "punch": 0.35, "sweep": 0.2})
                self.plan_until = g.t + rng.randint(6, 18)
            else:
                it.move = 1
        elif p == "mix":
            if dist > 140:
                it.move = 1
            else:
                opts = {"punch": 0.35, "kick": 0.2, "sweep": 0.12, "axe": 0.1, "heavy": 0.08}
                if dist <= 74:
                    opts["throw"] = ai["grab"] * 0.9
                opts = {k: v for k, v in opts.items() if self.in_range(k, dist) or k == "throw"}
                if opts:
                    it.atk = wchoice(rng, opts)
                self.plan_until = g.t + rng.randint(8, 22)
        elif p == "super":
            if me.meter >= 100 and dist < 560:
                it.atk = "super"
            self.plan_until = 0

    def chain(self, op, it, dist):
        me, rng = self.me, self.g.rng
        a = ATK[me.atk]
        if not (me.connected and a["chain"]) or rng.random() > 0.12:
            return
        opts = {}
        for n in a["chain"]:
            if n == "super":
                if me.meter >= 100:
                    opts[n] = 0.5
            elif n == "fire":
                if me.fire_cd <= 0:
                    opts[n] = 0.3
            elif self.in_range(n, dist):
                opts[n] = 0.6
        if opts:
            it.atk = wchoice(rng, opts)


class Fight(Game):
    key, title, accent = "fight", "Street Clash", "#ff5a4f"
    tagline = "Two fighters. Best of three. Last one standing wins."
    rate_per_hour, run_typical = 2800, 400

    def __init__(self, ctx):
        super().__init__(ctx)
        self.sprites = OrderedDict()
        self.projs, self.fx = [], []
        self.t = 0
        self.stage = 0
        self.bag = []
        self.champ_idx = None
        self.last_opp = None
        self.streak = 0
        self.shake = self.hitstop = self.freeze = 0
        self.freeze_owner = None
        self.combo_pop = None
        self.reset()

    # ------------------------------------------------------------------ match flow
    def pick(self, exclude):
        if not self.bag:
            self.bag = list(range(len(art.ROSTER)))
            self.rng.shuffle(self.bag)
        for i in list(self.bag):
            if i not in exclude:
                self.bag.remove(i)
                return i
        return self.rng.choice([i for i in range(len(art.ROSTER)) if i not in exclude])

    def reset(self):
        self.begin_run()
        self.streak = 0
        self.champ_idx = self.pick([])
        self.last_opp = None
        self.new_match()

    def new_match(self):
        chall = self.pick([self.champ_idx] + ([self.last_opp] if self.last_opp is not None else []))
        self.last_opp = chall
        self.stage = (self.stage + 1) % len(art.STAGE_FUNCS) if self.rng.random() < 0.8 else self.rng.randrange(3)
        champ, other = Fighter(art.ROSTER[self.champ_idx], self), Fighter(art.ROSTER[chall], self)
        champ.is_champ, other.is_champ = True, False
        self.f = [champ, other] if self.rng.random() < 0.5 else [other, champ]
        self.champion = champ
        self.brains = [Brain(self, f) for f in self.f]
        self.round_no, self.phase, self.pt, self.winner = 1, "vs", 0, None
        self.projs.clear()
        self.fx.clear()
        for f, x, face in ((self.f[0], 440, 1), (self.f[1], 840, -1)):
            f.reset_round(x, face)
        self.timer = ROUND_FRAMES
        self.ctx.audio.sfx("whoosh", 0.7)

    def start_round(self):
        for f, x, face in ((self.f[0], 440, 1), (self.f[1], 840, -1)):
            f.reset_round(x, face)
            f.took_damage = False
        self.projs.clear()
        self.timer = ROUND_FRAMES
        self.phase, self.pt = "intro", 0

    def hud_extra(self):
        return [("CHAMPION", self.champion.spec["name"]), ("WIN STREAK", str(self.streak)), ("ROUND", f"{min(self.round_no, 5)}")]

    # ------------------------------------------------------------------ helpers used by fighters
    def begin_freeze(self, f):
        self.freeze, self.freeze_owner = 40, f
        self.ctx.audio.sfx("super")

    def thud(self, f):
        self.shake = max(self.shake, 5)
        self.ctx.audio.sfx("heavy", 0.7)
        self.ctx.parts.burst(f.x, GROUND + 4, 8, ["#d8cdb8", "#b9ad96"], speed=(0.5, 2.5), life=(14, 28), size=(3, 6), grav=-0.02, kind="smoke")

    def spawn_proj(self, f, name):
        S = f.S
        mega = ATK[name]["proj"] == "mega"
        self.projs.append(dict(x=f.x + f.face * 58 * S, y=f.y + (95 if mega else 88) * S, vx=f.face * (15.0 if mega else 8.5),
                               owner=f, kind=ATK[name]["proj"], atk=name, r=(52 if mega else 22) * S, life=150))
        self.ctx.audio.sfx("wave", 0.8)

    def spark(self, x, y, size, color):
        self.fx.append([x, y, 0, 12, size, color])
        self.ctx.parts.burst(x, y, int(4 + size / 6), [color, "#ffffff"], speed=(1.5, 5), life=(10, 22), size=(2, 4), grav=0.1, kind="spark")

    # ------------------------------------------------------------------ combat
    def apply_hit(self, A, B, name, px, py):
        a = ATK[name]
        h = a["h"]
        rng = self.rng
        in_front = (px - B.x) * B.face >= -12
        if h == "throw":
            if B.state != "ready" or B.y > 0:
                return False
            if rng.random() < 0.18:                                  # throw tech
                A.kbx, B.kbx = -A.face * 7, -B.face * 7
                A.state, A.t, A.atk = "ready", 0, None
                self.spark(px, GROUND - py, 30, "#ffffff")
                self.ctx.audio.sfx("block")
                self.hitstop = 4
                return True
            blocked = False
        else:
            guarding = B.guard and in_front and (B.state == "ready" or (B.state == "hit" and B.blocked_stun))
            if not guarding:
                blocked = False
            elif h == "low":
                blocked = B.crouching
            elif h == "over":
                blocked = not B.crouching
            else:
                blocked = True
        sx, sy = px, GROUND - py
        if blocked:
            chip = a["dmg"] * 0.15 if a.get("proj") else 0.0
            B.hp = max(1.0, B.hp - chip * A.spec["dmg"])
            B.state, B.t, B.blocked_stun, B.stun = "hit", 0, True, a["bs"]
            B.kbx = A.face * a["kb"] * 1.1
            if abs(B.x - (WALL_L if B.x < 640 else WALL_R)) < 40:
                A.kbx = -A.face * a["kb"] * 0.9
            A.connected = True
            A.meter = min(100.0, A.meter + a["mg"] * 0.5)
            B.meter = min(100.0, B.meter + 3)
            self.spark(sx, sy, 22, "#9fd8ff")
            self.ctx.audio.sfx("block")
            self.hitstop = 3
            return True
        scale = 0.85 ** B.combo_n
        dmg = a["dmg"] * A.spec["dmg"] * scale
        B.hp -= dmg
        B.took_damage = True
        B.combo_n += 1
        A.connected = True
        A.meter = min(100.0, A.meter + a["mg"])
        B.meter = min(100.0, B.meter + dmg * 0.7)
        if a.get("launch") or B.y > 0:
            B.state, B.sub, B.t, B.blocked_stun = "down", "fly", 0, False
            B.vy, B.y = 9.0 if B.y <= 0 else 6.0, max(B.y, 1.0)
            B.kbx = A.face * a["kb"] * 1.4
        else:
            B.state, B.t, B.blocked_stun, B.stun = "hit", 0, False, a["hs"]
            B.kbx = A.face * a["kb"]
        if abs(B.x - (WALL_L if B.x < 640 else WALL_R)) < 40:
            A.kbx = -A.face * a["kb"] * 0.8
        heavy = a["dmg"] >= 11
        self.spark(sx, sy, 44 if heavy else 30, "#ffd93d" if not heavy else "#ff8a3d")
        self.ctx.audio.sfx("heavy" if heavy else "hit")
        self.hitstop = 8 if heavy else 5
        self.shake = max(self.shake, 8 if heavy else 3)
        if name == "super":
            self.hitstop, self.shake = 16, 14
        if B.combo_n >= 2:
            self.combo_pop = [B.combo_n, 0, A.x]
        if B.hp <= 0:
            self.begin_ko(A, B, name)
        return True

    def begin_ko(self, A, B, name):
        B.hp, B.ko = 0.0, True
        B.state, B.sub, B.t = "down", "fly", 0
        B.vy, B.y, B.kbx = 11.0, max(B.y, 1.0), A.face * 9
        self.phase, self.pt, self.ko_by, self.ko_winner = "ko", 0, name, A
        self.hitstop, self.shake = 16, 16
        self.ctx.audio.sfx("ko")

    def try_hits(self):
        hits = []
        for A, B in ((self.f[0], self.f[1]), (self.f[1], self.f[0])):
            if A.state != "attack" or A.hit_done:
                continue
            a = ATK[A.atk]
            if a.get("proj") or not (a["su"] <= A.t < a["su"] + a["ac"]) or not B.hittable():
                continue
            lo_x, hi_x = A.x + A.face * 18 * A.S, A.x + A.face * a["reach"] * A.S
            if lo_x > hi_x:
                lo_x, hi_x = hi_x, lo_x
            bx0, bx1 = B.x - 30 * B.S, B.x + 30 * B.S
            if bx1 < lo_x or bx0 > hi_x:
                continue
            ay0, ay1 = v_range(a["h"], A.S, A.y)
            by0, by1 = B.hurt_range()
            if ay1 < by0 or ay0 > by1:
                continue
            hits.append((A, B, (max(lo_x, bx0) + min(hi_x, bx1)) / 2, (max(ay0, by0) + min(ay1, by1)) / 2))
        for A, B, px, py in hits:
            A.hit_done = True
            if self.phase != "fight":
                break
            self.apply_hit(A, B, A.atk, px, py)

    def update_projs(self):
        for p in self.projs:
            p["x"] += p["vx"]
            p["life"] -= 1
        for i, p in enumerate(self.projs):
            for q in self.projs[i + 1:]:
                if p["owner"] is not q["owner"] and p["life"] > 0 and q["life"] > 0 and abs(p["x"] - q["x"]) < p["r"] + q["r"]:
                    if p["kind"] != "mega":
                        p["life"] = 0
                    if q["kind"] != "mega":
                        q["life"] = 0
                    self.spark((p["x"] + q["x"]) / 2, GROUND - p["y"], 36, "#ffffff")
        for p in self.projs:
            if p["life"] <= 0 or self.phase != "fight":
                continue
            B = self.f[1] if p["owner"] is self.f[0] else self.f[0]
            if B.hittable() and abs(p["x"] - B.x) < p["r"] + 30 * B.S:
                y0, y1 = B.hurt_range()
                if p["y"] + p["r"] > y0 and p["y"] - p["r"] < y1:
                    if self.apply_hit(p["owner"], B, p["atk"], p["x"], p["y"]):
                        p["life"] = 0
        self.projs = [p for p in self.projs if p["life"] > 0 and -100 < p["x"] < LW + 100]

    def separate(self):
        a, b = self.f
        if a.state != "down" and b.state != "down" and a.y < 60 and b.y < 60:
            gap = 64 * (a.S + b.S) / 2
            d = b.x - a.x
            if abs(d) < gap:
                push = (gap - abs(d)) / 2
                sg = 1 if d >= 0 else -1
                a.x -= sg * push
                b.x += sg * push
        for f in (a, b):
            f.x = max(WALL_L, min(WALL_R, f.x))
        if abs(a.x - b.x) < 40:                                     # both cornered: nudge apart
            b.x = min(WALL_R, a.x + 40) if b.x >= a.x else max(WALL_L, a.x - 40)

    def finish_round(self):
        p1, p2 = self.f
        winner = None
        if self.phase == "ko":
            winner = self.ko_winner
        else:
            r1, r2 = p1.hp / p1.maxhp, p2.hp / p2.maxhp
            if abs(r1 - r2) > 0.001:
                winner = p1 if r1 > r2 else p2
        self.round_winner = winner
        if winner is None:
            p1.wins += 1
            p2.wins += 1
        else:
            winner.wins += 1
            winner.state, winner.t, winner.mv = "win", 0, 0
            if getattr(winner, "is_champ", False):
                self.gain(25)
                if winner.hp >= winner.maxhp:
                    self.gain(25)
                    self.perfect = True
                if self.phase == "ko" and self.ko_by == "super":
                    self.gain(25)
        self.phase, self.pt = "end", 0

    def end_match_or_round(self):
        p1, p2 = self.f
        if (p1.wins >= 2 or p2.wins >= 2) and p1.wins != p2.wins or self.round_no >= 5:
            W = p1 if p1.wins > p2.wins else p2 if p2.wins > p1.wins else (p1 if p1.hp >= p2.hp else p2)
            self.match_winner = W
            name = W.spec["name"]
            if W.is_champ:
                self.streak += 1
                self.gain(100)
                self.ctx.toast(f"{name} WINS!  STREAK x{self.streak}", W.spec["accent"])
                self.new_champion = False
            else:
                self.crashed()
                self.champ_idx = art.ROSTER.index(W.spec)
                self.streak = 1
                self.begin_run()
                self.gain(100)
                self.ctx.toast(f"NEW CHAMPION: {name}", W.spec["accent"])
                self.new_champion = True
            self.ctx.audio.sfx("goal", 0.6)
            self.phase, self.pt = "match", 0
        else:
            self.round_no += 1
            self.perfect = False
            self.start_round()

    # ------------------------------------------------------------------ simulation
    def update(self):
        self.t += 1
        for e in self.fx:
            e[2] += 1
        self.fx = [e for e in self.fx if e[2] < e[3]]
        self.shake = max(0, self.shake - 1)
        if self.combo_pop:
            self.combo_pop[1] += 1
            if self.combo_pop[1] > 70:
                self.combo_pop = None
        if self.freeze > 0:
            self.freeze -= 1
            return
        if self.hitstop > 0:
            self.hitstop -= 1
            return
        self.pt += 1
        ph = self.phase
        p1, p2 = self.f
        neutral = Intent()
        if ph == "vs":
            if self.pt >= 150:
                self.start_round()
        elif ph == "intro":
            if self.pt == 72:
                self.ctx.audio.sfx("bell")
            if self.pt >= 118:
                self.phase, self.pt = "fight", 0
        elif ph == "fight":
            self.timer -= 1
            its = [Intent(), Intent()]
            self.brains[0].think(p2, its[0])
            self.brains[1].think(p1, its[1])
            p1.update(p2, its[0], self)
            p2.update(p1, its[1], self)
            self.separate()
            self.try_hits()
            self.update_projs()
            for f in self.f:
                f.lag += (f.hp - f.lag) * 0.06 if f.lag > f.hp else (f.hp - f.lag)
            if self.phase == "fight" and self.timer <= 0:
                self.phase, self.pt = "time", 0
                self.ctx.audio.sfx("bell")
        elif ph in ("ko", "time"):
            if self.pt % 3 == 0:                                  # slow motion
                p1.update(p2, neutral, self)
                p2.update(p1, neutral, self)
                self.separate()
            for f in self.f:
                f.lag += (f.hp - f.lag) * 0.06 if f.lag > f.hp else (f.hp - f.lag)
            if self.pt >= (105 if ph == "ko" else 70):
                self.perfect = False
                self.finish_round()
        elif ph == "end":
            for f in self.f:
                if f.state == "down" and f.ko:
                    f.update(self.f[0] if f is self.f[1] else self.f[1], neutral, self)
            if self.pt >= 130:
                self.end_match_or_round()
        elif ph == "match":
            if self.pt >= 240:
                self.new_match()
        if ph in ("vs", "intro", "end", "match"):
            for f in self.f:
                if f.state in ("ready", "win"):
                    f.update(self.f[0] if f is self.f[1] else self.f[1], neutral, self) if f.state == "ready" else None
                    if f.state == "ready":
                        f.guard = f.crouching = False
                        f.mv = 0

    # ------------------------------------------------------------------ drawing
    def sprite(self, cv, f, pose):
        flip = f.face < 0
        key = (f.spec["name"], pose, flip)
        im = self.sprites.get(key)
        if im is None:
            k = cv.s * 2
            raw = Image.new("RGBA", (round(art.SPR_W * k), round(art.SPR_H * k)), (0, 0, 0, 0))
            art.build_fighter(Painter(raw, k), f.spec, pose)
            if flip:
                raw = raw.transpose(_T.FLIP_LEFT_RIGHT)
            im = raw.resize((round(art.SPR_W * cv.s), round(art.SPR_H * cv.s)), LANCZOS)
            self.sprites[key] = im
            while len(self.sprites) > 260:
                self.sprites.popitem(last=False)
        else:
            self.sprites.move_to_end(key)
        return im

    def draw_fighter(self, cv, f):
        s = cv.s
        S = f.S
        sh = max(0.4, 1 - f.y / 380)
        cv.d.ellipse([(f.x - 52 * S * sh) * s, (GROUND + 2) * s, (f.x + 52 * S * sh) * s, (GROUND + 16) * s], fill=(0, 0, 0, 95))
        spr = self.sprite(cv, f, f.pose_name(self.t))
        cv.blit(spr, f.x - art.OX, GROUND - f.y - art.OY)

    def draw_proj(self, cv, p):
        s = cv.s
        c = p["owner"].spec["accent"]
        x, y = p["x"], GROUND - p["y"]
        r = p["r"]
        cv.glow(x, y, r * 2.6, c, 0.85, 1.6)
        for i in range(1, 5):
            cv.d.ellipse([(x - p["vx"] * i * 1.6 - r * (1 - i * 0.18)) * s, (y - r * (1 - i * 0.18) * 0.8) * s,
                          (x - p["vx"] * i * 1.6 + r * (1 - i * 0.18)) * s, (y + r * (1 - i * 0.18) * 0.8) * s],
                         fill=col(c, 130 - i * 25))
        cv.d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=col(lighten(c, 0.3), 255))
        cv.d.ellipse([(x - r * 0.62) * s, (y - r * 0.62) * s, (x + r * 0.62) * s, (y + r * 0.62) * s], fill=(255, 255, 255, 255))

    def draw_fx(self, cv):
        s = cv.s
        for x, y, t, life, size, color in self.fx:
            k = t / life
            r = size * (0.4 + 1.1 * ease_out(k))
            pts = []
            for i in range(16):
                rr = r if i % 2 == 0 else r * 0.42
                a = i * math.pi / 8 + 0.2
                pts.append(((x + math.cos(a) * rr) * s, (y + math.sin(a) * rr) * s))
            cv.d.polygon(pts, fill=col(color, int(255 * (1 - k))))
            cv.d.ellipse([(x - r * 0.28) * s, (y - r * 0.28) * s, (x + r * 0.28) * s, (y + r * 0.28) * s], fill=(255, 255, 255, int(255 * (1 - k))))

    def rr(self, cv, x0, y0, x1, y1, r, fill, outline=None, width=1):
        s = cv.s
        cv.d.rounded_rectangle([x0 * s, y0 * s, max(x0 * s, x1 * s - 1), max(y0 * s, y1 * s - 1)], radius=r * s, fill=fill,
                               outline=outline, width=max(1, int(width * s)))

    def bar(self, cv, f, left):
        frac, lag = max(0.0, f.hp / f.maxhp), max(0.0, f.lag / f.maxhp)
        W = 270
        x0, x1 = (345, 615) if left else (665, 935)
        self.rr(cv, x0 - 4, 20, x1 + 4, 56, 10, (8, 10, 30, 215), (255, 255, 255, 70), 1.5)
        c = "#3ddc84" if frac > 0.5 else "#ffb02e" if frac > 0.25 else "#ff4d4d"
        if left:
            if lag > frac:
                self.rr(cv, x1 - W * lag, 24, x1, 52, 7, "#ffe27a")
            if frac > 0:
                self.rr(cv, x1 - W * frac, 24, x1, 52, 7, c)
                self.rr(cv, x1 - W * frac + 2, 26, x1 - 2, 33, 3, (255, 255, 255, 80))
        else:
            if lag > frac:
                self.rr(cv, x0, 24, x0 + W * lag, 52, 7, "#ffe27a")
            if frac > 0:
                self.rr(cv, x0, 24, x0 + W * frac, 52, 7, c)
                self.rr(cv, x0 + 2, 26, x0 + W * frac - 2, 33, 3, (255, 255, 255, 80))
        sp = f.spec
        cv.text(x0 if left else x1, 76, sp["name"], 18, sp["accent"], "l" if left else "r", shadow=2)
        mw = 190
        mx0, mx1 = (x1 - mw, x1) if left else (x0, x0 + mw)
        self.rr(cv, mx0, 82, mx1, 90, 4, (8, 10, 30, 200))
        mf = min(1.0, f.meter / 100)
        full = f.meter >= 100
        if mf > 0:
            cc = "#ffd93d" if full and (self.t // 8) % 2 == 0 else "#35c4ff"
            if left:
                self.rr(cv, mx1 - mw * mf, 82, mx1, 90, 4, cc)
            else:
                self.rr(cv, mx0, 82, mx0 + mw * mf, 90, 4, cc)
        if full:
            cv.text(mx0 - 6 if left else mx1 + 6, 91, "SUPER", 12, "#ffd93d", "r" if left else "l", shadow=1)
        for i in range(2):                                          # round pips
            px = (610 - i * 16) if left else (670 + i * 16)
            cv.d.ellipse([(px - 5) * cv.s, 95 * cv.s, (px + 5) * cv.s, 105 * cv.s], fill="#ffd93d" if i < f.wins else (255, 255, 255, 60))

    def banner(self, cv, text, y, size, color, k=1.0, sub=None, subcolor="#ffffff"):
        sz = size * (0.7 + 0.3 * ease_out(k))
        w = cv.text_w(text, sz) + 80
        a = int(150 * min(1, k * 2))
        self.rr(cv, LW / 2 - w / 2, y - sz * 0.92, LW / 2 + w / 2, y + 22 + (24 if sub else 0), 14, (6, 8, 24, a))
        cv.text(LW / 2, y, text, sz, color, "m", shadow=4, stroke=3)
        if sub:
            cv.text(LW / 2, y + 40, sub, 24, subcolor, "m", shadow=2)

    def draw(self, cv):
        s = cv.s
        stage = cv.sprite(("fight_stage", self.stage), LW, LH, art.STAGE_FUNCS[self.stage], ss=1, mode="RGB")
        cv.paste_bg(stage)
        order = sorted(self.f, key=lambda f: (f.state == "attack", f.state == "win", -abs(f.x - 640)))
        for f in order:
            self.draw_fighter(cv, f)
        for p in self.projs:
            self.draw_proj(cv, p)
        self.draw_fx(cv)
        if self.freeze > 0 and self.freeze_owner is not None:
            cv.overlay("#000018", 150)
            self.draw_fighter(cv, self.freeze_owner)
            o = self.freeze_owner
            cv.glow(o.x, GROUND - 100, 220, o.spec["accent"], 0.7, 1.6)
            self.banner(cv, "SUPER!", 330, 110, o.spec["accent"], 1.0, o.spec["name"])
        if self.shake > 0:
            dx = int((self.shake % 3 - 1) * self.shake * 0.8 * s)
            dy = int(((self.shake + 1) % 3 - 1) * self.shake * 0.5 * s)
            cv.img.paste(ImageChops.offset(cv.img, dx, dy))
        # HUD
        a, b = self.f
        self.bar(cv, a, True)
        self.bar(cv, b, False)
        cv.d.ellipse([609 * s, 14 * s, 671 * s, 76 * s], fill=(8, 10, 30, 230), outline=(255, 255, 255, 110), width=max(1, int(2 * s)))
        secs = max(0, math.ceil(self.timer / 60))
        cv.text(640, 58, secs, 34, "#ffffff" if secs > 10 else "#ff6b6b", "m", shadow=2)
        if self.combo_pop and self.combo_pop[0] >= 2:
            n, t, ax = self.combo_pop
            kk = ease_out(t / 8) * (1 if t < 55 else (70 - t) / 15)
            cv.text(LW / 2, 180 - (1 - kk) * 20, f"{n} HIT COMBO!", 42, "#ffd93d", "m", shadow=3, stroke=3)
        ph = self.phase
        if ph == "vs":
            k = ease_out(self.pt / 20)
            sp1, sp2 = a.spec, b.spec
            self.rr(cv, 0, 250, LW, 400, 0, (6, 8, 24, int(185 * k)))
            cv.text(640 - 70, 345, sp1["name"], 70, sp1["accent"], "r", shadow=4, stroke=3)
            cv.text(640, 345, "VS", 56, "#ffffff", "m", shadow=4, stroke=3)
            cv.text(640 + 70, 345, sp2["name"], 70, sp2["accent"], "l", shadow=4, stroke=3)
            tag = f"CHAMPION: {self.champion.spec['name']}  -  WIN STREAK x{self.streak}" if self.streak else f"CHAMPION: {self.champion.spec['name']}"
            cv.text(640, 385, tag, 24, "#ffd93d", "m", shadow=2)
            cv.text(640, 232, art.STAGE_NAMES[self.stage], 22, "#c9d1ff", "m", shadow=2)
        elif ph == "intro":
            if self.pt < 72:
                self.banner(cv, f"ROUND {self.round_no}", 340, 96, "#ffffff", self.pt / 14)
            else:
                self.banner(cv, "FIGHT!", 340, 130, "#ff5a4f", (self.pt - 72) / 10)
        elif ph in ("ko", "time", "end"):
            ko = (ph == "ko") or (ph == "end" and self.phase == "end" and getattr(self, "ko_by", None) and self.round_winner is not None and self.f[0].ko or self.f[1].ko)
            if ph == "time":
                self.banner(cv, "TIME!", 340, 130, "#ffd93d", self.pt / 10)
            elif ph == "ko" or ko:
                self.banner(cv, "K.O.!", 340, 150, "#ff5a4f", min(1, self.pt / 10), "PERFECT!" if getattr(self, "perfect", False) else None, "#ffd93d")
            else:
                self.banner(cv, "DRAW" if self.round_winner is None else "TIME!", 340, 120, "#ffd93d", 1.0)
            if ph == "end" and self.round_winner is not None and self.pt > 30:
                cv.text(LW / 2, 440, f"{self.round_winner.spec['name']} WINS THE ROUND", 30, self.round_winner.spec["accent"], "m", shadow=3, stroke=2)
        elif ph == "match":
            W = self.match_winner
            self.banner(cv, f"{W.spec['name']} WINS!", 330, 110, W.spec["accent"], min(1, self.pt / 12),
                        "NEW CHAMPION" if getattr(self, "new_champion", False) else f"WIN STREAK x{self.streak}", "#ffd93d")

    def icon(self, cv, size=96):
        return cv.sprite("fight_icon", 90, 90, art.icon, ss=3)
