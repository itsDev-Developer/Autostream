"""Persistent statistics: all-time high scores + the current "campaign" (goals, totals, start time).

The state file is written atomically, so a crash / restart / redeploy never loses records and a long
challenge (e.g. "24 hours to reach 100,000") resumes where it left off.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

log = logging.getLogger("state")


class Clock:
    """Wall clock; in --test/--shots modes `sim` replaces it so time can be fast-forwarded."""

    def __init__(self):
        self.sim = None

    def wall(self):
        return time.time() if self.sim is None else self.sim


class Stats:
    def __init__(self, path, clock):
        self.path, self.clock = path, clock
        self.dirty = False
        self._lock = threading.Lock()
        self.d = {"v": 1, "records": {}, "runs": 0,
                  "campaign": {"started": None, "best": {}, "total": {}, "done": {}, "attempts": {}, "crashes": {}},
                  "director": {"game": None}}
        self._load()
        if self.d["campaign"]["started"] is None:
            self.d["campaign"]["started"] = clock.wall()
            self.dirty = True

    # ---- persistence
    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(self.d.get(k), dict):
                    self.d[k].update(v)
                else:
                    self.d[k] = v
            log.info("state loaded from %s", self.path)
        except Exception as e:  # corrupt file: keep a copy and start clean
            log.error("state file unreadable (%s) - starting fresh", e)
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass

    def save(self, force=False):
        if not self.path or not (self.dirty or force):
            return
        with self._lock:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.d, f, indent=1)
                os.replace(tmp, self.path)
                self.dirty = False
            except OSError as e:
                log.error("cannot save state: %s", e)

    def new_campaign(self):
        self.d["campaign"] = {"started": self.clock.wall(), "best": {}, "total": {}, "done": {}, "attempts": {},
                              "crashes": {}}
        self.dirty = True

    # ---- queries
    @property
    def c(self):
        return self.d["campaign"]

    def elapsed(self):
        return max(0.0, self.clock.wall() - self.c["started"])

    def record(self, g):
        return self.d["records"].get(g, 0)

    def camp_best(self, g):
        return self.c["best"].get(g, 0)

    def camp_total(self, g):
        return self.c["total"].get(g, 0)

    def is_done(self, g):
        return g in self.c["done"]

    def goal_value(self, g, goal):
        return self.camp_total(g) if goal.mode == "total" else self.camp_best(g)

    # ---- updates
    def on_score(self, g, run_score, delta):
        c = self.c
        c["total"][g] = c["total"].get(g, 0) + delta
        if run_score > c["best"].get(g, 0):
            c["best"][g] = run_score
        if run_score > self.d["records"].get(g, 0):
            self.d["records"][g] = run_score
        self.dirty = True

    def on_attempt(self, g):
        self.c["attempts"][g] = self.c["attempts"].get(g, 0) + 1
        self.d["runs"] += 1
        self.dirty = True

    def on_crash(self, g):
        self.c["crashes"][g] = self.c["crashes"].get(g, 0) + 1
        self.dirty = True

    def mark_done(self, g):
        self.c["done"][g] = self.clock.wall()
        self.dirty = True
        self.save(force=True)
