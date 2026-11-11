"""Director: decides which game is on screen (rotation + goals), runs intro/outro cards, triggers music."""
from __future__ import annotations

import logging

from .games import REGISTRY
from .gfx import fmt_time
from .overlay import Overlay

log = logging.getLogger("director")
UPS = 60


class Director:
    INTRO, OUTRO = 4.5, 5.5

    def __init__(self, ctx, names):
        self.ctx, self.cfg, self.stats, self.audio = ctx, ctx.cfg, ctx.stats, ctx.audio
        self.minutes = self.cfg.minutes
        self.games = [REGISTRY[n](ctx) for n in names]
        self.by_key = {g.key: g for g in self.games}
        self.overlay = Overlay(ctx, self)
        self._check_feasibility()
        self.state, self.timer, self.seg_ticks, self.reason = "intro", 0.0, 0, None
        self.final_t = 0.0
        self.finished = False
        self.idx = 0
        start = self.stats.d["director"].get("game")
        order = [i for i, g in enumerate(self.games) if self._active(g)]
        if start in self.by_key and self._active(self.by_key[start]):
            self.idx = self.games.index(self.by_key[start])
        elif order:
            self.idx = order[0]
        if not order and self.cfg.goals:
            self.state = "final"
        else:
            self._begin(self.idx)

    def _check_feasibility(self):
        """Warn when a goal cannot realistically be reached in the chosen duration."""
        for key, goal in self.cfg.goals.items():
            g = self.by_key.get(key)
            if g is None:
                log.warning("goal for '%s' ignored: that game is not in --games", key)
                continue
            hours = self.cfg.duration
            if hours and g.rate_per_hour and goal.target > g.rate_per_hour * hours:
                log.warning("goal %s=%s needs about %.1f h of steady play (max ~%s points/hour) - more than --duration %gh",
                            key, f"{goal.target:,}", goal.target / g.rate_per_hour, f"{g.rate_per_hour:,}", hours)
            if goal.mode == "best" and g.run_typical and goal.target > g.run_typical:
                log.warning("goal %s=%s (single run): the player normally crashes before ~%s points - use ':total' or lower it",
                            key, f"{goal.target:,}", f"{g.run_typical:,}")

    # ------------------------------------------------------------------ helpers
    @property
    def game(self):
        return self.games[self.idx]

    def _active(self, g):
        return not (g.key in self.cfg.goals and self.stats.is_done(g.key))

    def peek_next(self):
        n = len(self.games)
        for off in range(1, n + 1):
            g = self.games[(self.idx + off) % n]
            if self._active(g):
                return g
        return None

    def _begin(self, idx):
        self.idx = idx
        self.state, self.timer, self.seg_ticks, self.reason = "intro", 0.0, 0, None
        self.stats.d["director"]["game"] = self.game.key
        self.stats.dirty = True
        self.audio.play(self.game.key)
        self.audio.sfx("whoosh")
        self.audio.set_duck(0.55)
        log.info("now playing: %s", self.game.title)

    def _final(self, why):
        self.state, self.final_t = "final", 0.0
        self.audio.set_duck(0.6)
        self.audio.sfx("goal")
        self.ctx.parts.confetti(150, ["#ffd93d", "#35e0a1", "#35c4ff", "#ff6b9d", "#ffffff"])
        log.info("challenge finished (%s) after %s", why, fmt_time(self.stats.elapsed()))

    # ------------------------------------------------------------------ simulation tick (60/s)
    def update(self):
        dt = 1.0 / UPS
        cfg, g = self.cfg, self.game
        if self.state == "final":
            self.final_t += dt
            if cfg.end_on_complete and self.final_t > 25:
                self.finished = True
            return
        if cfg.duration and self.stats.elapsed() >= cfg.duration * 3600:
            self._final("time limit")
            return
        if self.state == "intro":
            self.timer += dt
            if self.timer >= self.INTRO:
                self.state = "play"
                self.audio.set_duck(1.0)
        elif self.state == "play":
            g.update()
            self.seg_ticks += 1
            goal = cfg.goals.get(g.key)
            if goal and self.stats.goal_value(g.key, goal) >= goal.target:
                self.stats.mark_done(g.key)
                self._end_segment("goal")
                self.audio.sfx("goal")
                self.ctx.parts.confetti(130, ["#ffd93d", "#35e0a1", "#35c4ff", "#ff6b9d", "#ffffff"])
            elif not goal and self.seg_ticks / UPS >= self.minutes * 60 and self.peek_next() not in (None, g):
                self._end_segment("time")
        elif self.state == "outro":
            self.timer += dt
            if self.timer >= self.OUTRO:
                nxt = self.peek_next()
                if nxt is None:
                    self._final("all goals reached")
                else:
                    self._begin(self.games.index(nxt))

    def _end_segment(self, reason):
        self.state, self.timer, self.reason = "outro", 0.0, reason
        self.audio.set_duck(0.5)
        log.info("segment over (%s): %s", reason, self.game.title)

    # ------------------------------------------------------------------ rendering
    def draw(self, cv):
        self.game.draw(cv)
        self.ctx.parts.draw(cv)
        if cv.fx >= 2:
            cv.vignette()
        ov = self.overlay
        ov.draw_hud(cv)
        ov.draw_ticker(cv)
        ov.draw_banner(cv)
        ov.draw_toasts(cv)
        if self.state == "intro":
            ov.draw_intro(cv)
        elif self.state == "outro":
            ov.draw_outro(cv)
        elif self.state == "final":
            ov.draw_final(cv)

    def snapshot(self):
        g = self.game
        return {"state": self.state, "game": g.key, "score": g.score, "records": dict(self.stats.d["records"]),
                "campaign": self.stats.c, "elapsed": round(self.stats.elapsed())}
