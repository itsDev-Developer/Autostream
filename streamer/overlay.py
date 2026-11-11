"""On-screen layers: HUD, high-score panel, goal progress, ticker, toasts and the full-screen cards
(NOW PLAYING / GOAL REACHED / FINAL RESULTS)."""
from __future__ import annotations

import math

from .gfx import LW, LH, col, darken, ease_out, fmt, fmt_time, lighten

UPS = 60


class Overlay:
    def __init__(self, ctx, director):
        self.ctx, self.dir = ctx, director

    # ------------------------------------------------------------------ always-on HUD
    def draw_hud(self, cv):
        g, st, cfg = self.dir.game, self.ctx.stats, self.ctx.cfg
        extras = g.hud_extra()
        # left: score card
        h = 150 + 27 * (len(extras) + 1)
        cv.panel(20, 20, 286, h, accent=g.accent)
        cv.text(42, 52, g.title.upper(), 17, g.accent, shadow=1)
        cv.text(42, 76, "SCORE", 14, "#8e9ad0", shadow=0)
        cv.text(42, 124, fmt(g.score), 50, "#ffffff", shadow=3)
        cv.text(42, 154, "HIGH SCORE", 14, "#8e9ad0", shadow=0)
        hs = max(st.record(g.key), g.score)
        cv.text(290, 156, fmt(hs), 26, "#ffd93d", "r", shadow=2)
        y = 186
        for label, val in extras + [("LIVE FOR", fmt_time(st.elapsed()))]:
            cv.text(42, y, label, 14, "#8e9ad0", shadow=0)
            cv.text(290, y, val, 18, "#ffffff", "r", shadow=1)
            y += 27

        # right: high-score board + goal + time left
        goal = cfg.goals.get(g.key)
        names = {k: self.dir.by_key[k] for k in self.dir.by_key}
        rows = len(names)
        h2 = 58 + rows * 29 + (86 if goal else 0) + (38 if cfg.duration else 0)
        x0 = LW - 306
        cv.panel(x0, 20, 286, h2)
        cv.text(x0 + 22, 52, (cfg.title.upper()[:24] if cfg.title else "ALL-TIME HIGH SCORES"), 15, "#8e9ad0", shadow=0)
        y = 84
        for k, game in names.items():
            cur = k == g.key
            if cur:
                cv.d.rounded_rectangle([(x0 + 10) * cv.s, (y - 20) * cv.s, (x0 + 276) * cv.s, (y + 6) * cv.s], radius=8 * cv.s,
                                       fill=col(game.accent, 55))
            done = st.is_done(k) and k in cfg.goals
            cv.text(x0 + 22, y, game.title, 17, "#ffffff" if cur else "#b6bfe8", shadow=1)
            cv.text(x0 + 266, y, ("✓ " if done else "") + fmt(max(st.record(k), game.score if cur else 0)), 18,
                    "#35e0a1" if done else "#ffd93d", "r", shadow=1)
            y += 29
        if goal:
            val = st.goal_value(g.key, goal)
            frac = min(1.0, val / goal.target)
            y += 8
            label = "GOAL  (single run)" if goal.mode == "best" else "GOAL  (all runs combined)"
            cv.text(x0 + 22, y, label, 14, "#8e9ad0", shadow=0)
            cv.text(x0 + 266, y + 26, f"{fmt(val)} / {fmt(goal.target)}", 20, "#ffffff", "r", shadow=1)
            cv.bar(x0 + 22, y + 36, 242, 14, frac, "#35e0a1")
            cv.text(x0 + 22, y + 26, f"{frac * 100:.1f}%", 18, "#35e0a1", shadow=1)
            y += 76
        if cfg.duration:
            left = cfg.duration * 3600 - st.elapsed()
            cv.text(x0 + 22, y + 10, "TIME LEFT", 14, "#8e9ad0", shadow=0)
            cv.text(x0 + 266, y + 12, fmt_time(left), 22, "#ff8f6b" if left < 3600 else "#ffffff", "r", shadow=1)

    def draw_ticker(self, cv):
        d, g = self.dir, self.dir.game
        nxt = d.peek_next()
        segs = [("NOW PLAYING  ", "#8e9ad0"), (g.title.upper(), g.accent)]
        goal = self.ctx.cfg.goals.get(g.key)
        if nxt is not None and nxt is not g:
            if goal:
                segs += [("   |   NEXT  ", "#8e9ad0"), (nxt.title.upper(), nxt.accent), ("  after the goal is reached", "#8e9ad0")]
            else:
                left = max(0, d.minutes * 60 - d.seg_ticks / UPS)
                segs += [("   |   NEXT  ", "#8e9ad0"), (nxt.title.upper(), nxt.accent),
                         (f"  in {int(left // 60):02d}:{int(left % 60):02d}", "#ffffff")]
        w = sum(cv.text_w(t, 18) for t, _ in segs) + 44
        cv.panel(LW / 2 - w / 2, 674, w, 36, r=18, alpha=185)
        cv.rich(LW / 2, 698, segs, 18)

    def draw_banner(self, cv):
        """'UP NEXT' strip during the last seconds of a timed round."""
        d = self.dir
        if d.state != "play" or self.ctx.cfg.goals.get(d.game.key):
            return
        nxt = d.peek_next()
        left = d.minutes * 60 - d.seg_ticks / UPS
        if nxt is None or nxt is d.game or left > 10:
            return
        k = ease_out((10 - left) / 0.6)
        y = -60 + 100 * k
        cv.panel(LW / 2 - 230, y, 460, 54, r=16, alpha=215, accent=nxt.accent)
        cv.text(LW / 2, y + 24, "UP NEXT", 14, "#8e9ad0", "m", shadow=0)
        cv.text(LW / 2, y + 46, f"{nxt.title}  •  {max(0, math.ceil(left))}s", 24, nxt.accent, "m", shadow=2)

    def draw_toasts(self, cv):
        for i, (text, color, ttl, total) in enumerate(self.ctx.toasts):
            age = total - ttl
            k = ease_out(age / 0.35) * (1 if ttl > 0.4 else ttl / 0.4)
            w = cv.text_w(text, 34) + 70
            y = 178 + i * 62 - (1 - k) * 40
            cv.panel(LW / 2 - w / 2, y, w, 52, r=26, alpha=int(215 * k), accent=color)
            cv.text(LW / 2, y + 37, text, 34, color, "m", shadow=2)

    # ------------------------------------------------------------------ full screen cards
    def _card(self, cv, y0, h, accent):
        cv.panel(250, y0, 780, h, r=26, alpha=225, accent=accent)

    def draw_intro(self, cv):
        d, g = self.dir, self.dir.game
        t = d.timer
        k = ease_out(t / 0.5)
        fade = min(1.0, t / 0.4) * min(1.0, max(0.0, (d.INTRO - t) / 0.5) if d.INTRO - t < 0.5 else 1.0)
        cv.overlay("#000010", 175 * fade)
        y0 = 150 + (1 - k) * 70
        self._card(cv, y0, 380, g.accent)
        pulse = 0.5 + 0.5 * math.sin(t * 6)
        cv.d.ellipse([(292) * cv.s, (y0 + 38) * cv.s, (308) * cv.s, (y0 + 54) * cv.s], fill=col("#ff4d4d", 150 + 105 * pulse))
        cv.text(320, y0 + 54, "NOW PLAYING", 22, "#c9d1ff", shadow=1)
        icon = g.icon(cv)
        cv.glow(398, y0 + 168, 120, g.accent, 0.5, 2)
        cv.blit(icon, 398, y0 + 168, "c")
        cv.text(480, y0 + 172, g.title.upper(), cv.fit(g.title.upper(), 70, 520), "#ffffff", shadow=4)
        for i, line in enumerate(cv.wrap(g.tagline, 20, 520)[:2]):
            cv.text(480, y0 + 205 + i * 26, line, 20, g.accent, shadow=1)
        goal = self.ctx.cfg.goals.get(g.key)
        stats = [("ALL-TIME HIGH", fmt(self.ctx.stats.record(g.key)), "#ffd93d")]
        if goal:
            stats.append(("GOAL", fmt(goal.target) + (" total" if goal.mode == "total" else ""), "#35e0a1"))
            val = self.ctx.stats.goal_value(g.key, goal)
            stats.append(("PROGRESS", f"{min(100, val * 100 / goal.target):.1f}%", "#ffffff"))
        else:
            stats.append(("ROUND", f"{d.minutes:g} min", "#35e0a1"))
        x = 290
        for label, val, c in stats:
            cv.text(x, y0 + 276, label, 14, "#8e9ad0", shadow=0)
            cv.text(x, y0 + 312, val, 30, c, shadow=2)
            x += 235
        nxt = d.peek_next()
        if nxt is not None and nxt is not g:
            cv.d.line([(280 * cv.s, (y0 + 336) * cv.s), (1000 * cv.s, (y0 + 336) * cv.s)], fill=(255, 255, 255, 40), width=1)
            cv.rich(LW / 2, y0 + 366, [("UP NEXT  ", "#8e9ad0"), (nxt.title.upper(), nxt.accent)], 20)

    def _trophy(self, cv):
        def paint(p):
            p.glow(60, 60, 60, "#ffd93d", .7, 2)
            p.rrect_grad(36, 18, 48, 52, 12, [(0, "#fff1a8"), (.5, "#ffd93d"), (1, "#c98f00")], horizontal=True)
            p.rrect(36, 18, 48, 52, 12, outline="#9a6a00", width=2)
            p.ellipse(32, 38, 12, 14, outline="#e6b800", width=5)
            p.ellipse(88, 38, 12, 14, outline="#e6b800", width=5)
            p.rect(54, 68, 12, 18, fill="#d4a100")
            p.rrect(38, 84, 44, 12, 4, fill="#b07d00")
            p.rrect(30, 94, 60, 10, 4, fill="#8a5f00")
            lay = p.layer()
            lay.rrect(42, 24, 8, 36, 4, fill=(255, 255, 255, 120))
            p.commit(lay)

        return cv.sprite("trophy", 120, 120, paint, ss=2)

    def draw_outro(self, cv):
        d, g = self.dir, self.dir.game
        t = d.timer
        cv.overlay("#000010", 150 * min(1.0, t / 0.4))
        k = ease_out(t / 0.5)
        y0 = 190 + (1 - k) * 60
        done = d.reason == "goal"
        self._card(cv, y0, 300, "#35e0a1" if done else g.accent)
        if done:
            cv.blit(self._trophy(cv), 400, y0 + 130, "c")
            cv.text(480, y0 + 118, "GOAL REACHED!", 56, "#35e0a1", shadow=4)
            goal = self.ctx.cfg.goals[g.key]
            line = f"{g.title}: {fmt(goal.target)} {'total ' if goal.mode == 'total' else ''}points achieved"
            cv.text(480, y0 + 158, line, cv.fit(line, 24, 520), "#ffffff", shadow=2)
            cv.text(480, y0 + 192, f"Time spent on this game: {fmt_time(d.seg_ticks / UPS)}", 20, "#c9d1ff", shadow=1)
        else:
            cv.text(LW / 2, y0 + 118, "ROUND COMPLETE", 60, g.accent, "m", shadow=4)
            cv.text(LW / 2, y0 + 160, f"Best score this round: {fmt(self.ctx.stats.camp_best(g.key))}", 24, "#ffffff", "m", shadow=2)
        nxt = d.peek_next()
        if nxt is not None and nxt is not g:
            cv.rich(LW / 2, y0 + 262, [("SWITCHING TO  ", "#8e9ad0"), (nxt.title.upper(), nxt.accent)], 26)

    def draw_final(self, cv):
        d, st, cfg = self.dir, self.ctx.stats, self.ctx.cfg
        cv.overlay("#000010", 190)
        all_done = bool(cfg.goals) and all(st.is_done(k) for k in cfg.goals)
        h = 150 + 46 * len(d.games)
        y0 = (LH - h) / 2
        self._card(cv, y0, h, "#35e0a1" if all_done else "#ffd93d")
        cv.blit(self._trophy(cv), 330, y0 + 80, "c")
        cv.text(400, y0 + 78, "ALL GOALS COMPLETE!" if all_done else "STREAM COMPLETE", 50, "#35e0a1" if all_done else "#ffd93d", shadow=4)
        cv.text(400, y0 + 108, f"Total time: {fmt_time(st.elapsed())}", 20, "#c9d1ff", shadow=1)
        y = y0 + 158
        for g in d.games:
            goal = cfg.goals.get(g.key)
            ok = goal is not None and st.is_done(g.key)
            cv.text(290, y, g.title, 24, g.accent, shadow=1)
            res = f"{fmt(st.goal_value(g.key, goal))} / {fmt(goal.target)}" if goal else f"best {fmt(st.camp_best(g.key))}"
            cv.text(740, y, res, 24, "#ffffff", "r", shadow=1)
            cv.text(990, y, ("ACHIEVED" if ok else ("NOT REACHED" if goal else "")), 22, "#35e0a1" if ok else "#ff8f6b", "r", shadow=1)
            y += 46
