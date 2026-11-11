"""Human-like input model shared by all games.

Real players are not frame-perfect: they react after ~100-200 ms, press keys at uneven intervals, their
attention drifts over minutes, and every now and then they fumble an input. This module provides those
ingredients; each game uses them when it decides what to press.

skill 1.0 -> calm, precise player (still has reaction time and uneven timing)
skill 0.6 -> casual player, visibly makes more mistakes
"""
from __future__ import annotations

UPS = 60


class Human:
    def __init__(self, rng, skill=0.85):
        self.rng = rng
        self.skill = min(1.0, max(0.0, float(skill)))
        self.focus = 1.0
        self._goal = 1.0
        self._left = 0

    def tick(self):
        """Attention wanders slowly (cycles of 40-120 s): sharper stretches, then a slightly sloppy one."""
        self._left -= 1
        if self._left <= 0:
            self._goal = self.rng.uniform(0.82, 1.1)
            self._left = self.rng.randint(UPS * 40, UPS * 120)
        self.focus += (self._goal - self.focus) * 0.002

    def scale(self):
        """How noisy the player is right now (smaller = more precise)."""
        return (0.4 + 1.6 * (1.0 - self.skill)) / max(0.6, self.focus)

    def noise(self, base, limit=None):
        v = self.rng.gauss(0.0, base * self.scale())
        if limit is not None:
            v = max(-limit, min(limit, v))
        return v

    def reaction(self, base=5, spread=6):
        """Reaction / motor delay in frames (60 fps): about 80-180 ms, varying every time."""
        return max(2, round(self.rng.gauss(base + spread * (1.0 - self.skill), 1.5)))

    def chance(self, p_at_perfect, p_at_casual):
        """Probability that interpolates with skill (e.g. chance of a fumbled input)."""
        return p_at_perfect + (p_at_casual - p_at_perfect) * (1.0 - self.skill)
