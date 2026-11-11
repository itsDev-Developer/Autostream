"""Shared game plumbing."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..gfx import LW, LH  # noqa: F401
from ..human import Human


@dataclass
class Ctx:
    cfg: object
    cv: object          # gfx.Canvas
    audio: object
    stats: object
    rng: object
    parts: object       # gfx.Particles
    clock: object
    toasts: list = field(default_factory=list)

    def toast(self, text, color="#ffd93d", ttl=3.2):
        self.toasts.append([text, color, ttl, ttl])
        del self.toasts[:-3]


class Game:
    key = ""
    title = ""
    tagline = ""
    accent = "#ffffff"
    rate_per_hour = 0       # measured points/hour at steady play (used for goal feasibility warnings)
    run_typical = 0         # typical best single run before an accidental crash (0 = unlimited)

    def __init__(self, ctx):
        self.ctx = ctx
        self.rng = ctx.rng
        self.h = Human(ctx.rng, getattr(ctx.cfg, "skill", 0.85))
        self.score = 0
        self.attempt = 0
        self.total_pts = 0
        self.rec_base = 0
        self.rec_hit = False

    # --- scoring / records
    def begin_run(self):
        st = self.ctx.stats
        self.attempt += 1
        self.score = 0
        self.rec_base = st.record(self.key)
        self.rec_hit = False
        st.on_attempt(self.key)

    def gain(self, n=1):
        self.score += n
        self.total_pts += n
        self.ctx.stats.on_score(self.key, self.score, n)
        if not self.rec_hit and self.rec_base > 0 and self.score > self.rec_base:
            self.rec_hit = True
            self.ctx.audio.sfx("record")
            self.ctx.toast("NEW HIGH SCORE!", "#ffd93d")

    def crashed(self):
        self.ctx.stats.on_crash(self.key)

    def mistake(self, default):
        return self.ctx.cfg.mistake_for(self.key, default)

    # --- interface
    def hud_extra(self):
        return []

    def update(self):
        raise NotImplementedError

    def draw(self, cv):
        raise NotImplementedError

    def icon(self, cv, size=96):
        raise NotImplementedError
