"""Configuration: CLI flags > environment variables > --config JSON file > defaults."""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

GAME_KEYS = ("flappy", "racing", "blocks", "fight")
PROFILES = {  # width, height, fps, bitrate
    "low": (640, 360, 20, "800k"),
    "medium": (854, 480, 24, "1200k"),
    "high": (1280, 720, 30, "2500k"),
    "ultra": (1920, 1080, 30, "4500k"),
}


@dataclass
class Goal:
    target: int
    mode: str = "best"          # best = one single run must reach it; total = cumulative over all runs


@dataclass
class Config:
    urls: list = field(default_factory=list)
    games: list = field(default_factory=lambda: list(GAME_KEYS))
    minutes: float = 10.0
    goals: dict = field(default_factory=dict)        # game -> Goal
    mistake: dict = field(default_factory=dict)      # game or "*" -> chance of a deliberate slip per obstacle
    skill: float = 0.85                              # 0..1, how precise the on-screen player is
    duration: float = 0.0                            # hours; 0 = unlimited
    end_on_complete: bool = False
    title: str = ""
    width: int = 854
    height: int = 480
    fps: int = 24
    bitrate: str = "1200k"
    preset: str = "veryfast"
    music: bool = True
    sfx: bool = True
    volume: float = 0.55
    music_dir: str = ""
    cache_dir: str = "cache"
    state_file: str = "state/state.json"
    reset_campaign: bool = False
    seed: int | None = None
    fx: int = 2
    port: int = 0
    log_level: str = "INFO"
    test: float = 0.0
    shots: str = ""

    def mistake_for(self, game, default):
        return self.mistake.get(game, self.mistake.get("*", default))


def parse_goals(items):
    out = {}
    for item in items:
        for part in str(item).split(","):
            part = part.strip()
            if not part:
                continue
            game, _, rest = part.partition("=")
            target, _, mode = rest.partition(":")
            game = game.strip().lower()
            if game not in GAME_KEYS:
                sys.exit(f"--goal: unknown game '{game}' (choose from {', '.join(GAME_KEYS)})")
            mode = (mode or "best").strip().lower()
            if mode not in ("best", "total"):
                sys.exit("--goal mode must be 'best' or 'total'  (example: flappy=100000:total)")
            out[game] = Goal(int(target.replace("_", "")), mode)
    return out


def parse_mistake(text):
    out = {}
    if not text:
        return out
    for part in str(text).split(","):
        if "=" in part:
            g, v = part.split("=", 1)
            out[g.strip().lower()] = float(v)
        elif part.strip():
            out["*"] = float(part)
    return out


def _bool(v):
    return str(v).lower() in ("1", "true", "yes", "on")


def load_config(argv=None) -> Config:
    e = os.environ.get
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=e("CONFIG_FILE", ""))
    known, _ = pre.parse_known_args(argv)
    filecfg = {}
    if known.config:
        with open(known.config, "r", encoding="utf-8") as f:
            filecfg = {k.replace("-", "_"): v for k, v in json.load(f).items()}

    def D(name, env, default):
        """default value: config file > environment > built-in"""
        if name in filecfg:
            return filecfg[name]
        return e(env, default) if env else default

    ap = argparse.ArgumentParser(
        description="Game live streamer", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--config", default=known.config, help="JSON file with any of these options")
    ap.add_argument("--url", action="append", default=[], help="RTMP(S) URL incl. stream key (repeatable)")
    ap.add_argument("--games", default=D("games", "GAMES", ",".join(GAME_KEYS)), help="comma list, in rotation order")
    ap.add_argument("--minutes", type=float, default=float(D("minutes", "MINUTES", 10)),
                    help="minutes per game (games WITHOUT a goal)")
    ap.add_argument("--goal", action="append", default=[],
                    help="score to reach before the game switches, e.g. flappy=100000 or racing=5000:total")
    ap.add_argument("--mistake", default=D("mistake", "MISTAKE", ""), help="extra chance of a deliberate slip: 0.02 or flappy=0,racing=0.01")
    ap.add_argument("--skill", type=float, default=float(D("skill", "SKILL", 0.85)),
                    help="player precision 0..1 (1 = very steady, 0.6 = casual with visible mistakes)")
    ap.add_argument("--duration", type=float, default=float(D("duration", "DURATION_HOURS", 0)),
                    help="stop the challenge after N hours (0 = never)")
    ap.add_argument("--end-on-complete", action="store_true", default=_bool(D("end_on_complete", "END_ON_COMPLETE", False)),
                    help="exit after every goal is reached / duration is over")
    ap.add_argument("--title", default=D("title", "TITLE", ""), help="challenge title shown on screen")
    ap.add_argument("--profile", choices=list(PROFILES), default=D("profile", "PROFILE", "medium"),
                    help="quality preset: low 360p, medium 480p, high 720p, ultra 1080p")
    ap.add_argument("--width", type=int, default=D("width", "WIDTH", None))
    ap.add_argument("--height", type=int, default=D("height", "HEIGHT", None))
    ap.add_argument("--fps", type=int, default=D("fps", "FPS", None))
    ap.add_argument("--bitrate", default=D("bitrate", "VIDEO_BITRATE", None))
    ap.add_argument("--preset", default=D("preset", "PRESET", "veryfast"), help="x264 preset (ultrafast for weak CPUs)")
    ap.add_argument("--no-music", action="store_true", default=not _bool(D("music", "MUSIC", True)))
    ap.add_argument("--no-sfx", action="store_true", default=not _bool(D("sfx", "SFX", True)))
    ap.add_argument("--volume", type=float, default=float(D("volume", "VOLUME", 0.55)), help="music volume 0..1")
    ap.add_argument("--music-dir", default=D("music_dir", "MUSIC_DIR", ""), help="folder of your own mp3/wav/ogg tracks")
    ap.add_argument("--cache-dir", default=D("cache_dir", "CACHE_DIR", "cache"))
    ap.add_argument("--state-file", default=D("state_file", "STATE_FILE", "state/state.json"))
    ap.add_argument("--reset-campaign", action="store_true", help="start a fresh challenge (keeps all-time records)")
    ap.add_argument("--seed", type=int, default=D("seed", "SEED", None))
    ap.add_argument("--fx", type=int, choices=(0, 1, 2), default=int(D("fx", "FX", 2)),
                    help="visual effects: 0 minimal (fastest), 1 normal, 2 full")
    ap.add_argument("--port", type=int, default=int(D("port", "PORT", 0)), help="status/health HTTP port (0 = off)")
    ap.add_argument("--log-level", default=D("log_level", "LOG_LEVEL", "INFO"))
    ap.add_argument("--test", type=float, default=0.0, metavar="SECONDS", help="write test.mp4 instead of streaming")
    ap.add_argument("--shots", default="", metavar="DIR", help="save preview PNGs of every screen and exit")
    a = ap.parse_args(argv)

    w, h, fps, br = PROFILES[a.profile]
    games = [g.strip().lower() for g in str(a.games).split(",") if g.strip()]
    for g in games:
        if g not in GAME_KEYS:
            sys.exit(f"unknown game '{g}' (choose from {', '.join(GAME_KEYS)})")
    goal_specs = a.goal or ([e("GOALS")] if e("GOALS") else []) or ([filecfg["goals"]] if "goals" in filecfg else [])
    if isinstance(goal_specs, list) and goal_specs and isinstance(goal_specs[0], dict):
        goal_specs = [",".join(f"{k}={v}" for k, v in goal_specs[0].items())]
    urls = a.url or [u.strip() for u in str(e("STREAM_URLS", "")).split(",") if u.strip()] or list(filecfg.get("urls", []))

    return Config(
        urls=urls, games=games, minutes=a.minutes, goals=parse_goals(goal_specs), mistake=parse_mistake(a.mistake), skill=min(1.0, max(0.0, a.skill)),
        duration=a.duration, end_on_complete=a.end_on_complete, title=a.title,
        width=int(a.width or w) // 2 * 2, height=int(a.height or h) // 2 * 2, fps=int(a.fps or fps),
        bitrate=a.bitrate or br, preset=a.preset, music=not a.no_music, sfx=not a.no_sfx, volume=a.volume,
        music_dir=a.music_dir, cache_dir=a.cache_dir, state_file=a.state_file, reset_campaign=a.reset_campaign,
        seed=a.seed, fx=a.fx, port=a.port, log_level=a.log_level.upper(), test=a.test, shots=a.shots,
    )
