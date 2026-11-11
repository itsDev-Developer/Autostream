"""Streaming runtime: render loop -> ffmpeg (video+audio pipes) -> RTMP, with supervision and monitoring."""
from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .audio import SR, Audio
from .director import Director
from .games import Ctx
from .gfx import Canvas, Particles
from .state import Clock, Stats

log = logging.getLogger("engine")
UPS = 60


def mask(url):
    """Hide stream keys in logs."""
    return re.sub(r"(://[^/]+/[^/]+/).+", r"\1****", url)


class Telemetry:
    def __init__(self):
        self.started = time.time()
        self.frames = 0
        self.last_frame = 0.0
        self.restarts = 0
        self.dropped = 0
        self.render_ms = 0.0
        self.status = {}
        self.connected = False


class Streamer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.stop = threading.Event()
        self.tele = Telemetry()
        self.clock = Clock()
        self.cv = Canvas(cfg.width, cfg.height, cfg.fx)
        self.rng = random.Random(cfg.seed)
        self.stats = Stats(cfg.state_file, self.clock)
        if cfg.reset_campaign:
            self.stats.new_campaign()
        self.audio = Audio(cfg, cfg.games)
        self.ctx = Ctx(cfg, self.cv, self.audio, self.stats, self.rng, Particles(self.rng), self.clock)
        self.director = Director(self.ctx, cfg.games)
        self._acc = 0.0        # fractional audio samples carried between frames

    # ------------------------------------------------------------------ one simulation + render step
    def step(self, draw=True):
        steps = max(1, round(UPS / self.cfg.fps))
        for _ in range(steps):
            self.director.update()
            self.ctx.parts.update()
            if self.clock.sim is not None:
                self.clock.sim += 1.0 / UPS
            for t in self.ctx.toasts:
                t[2] -= 1.0 / UPS
            self.ctx.toasts[:] = [t for t in self.ctx.toasts if t[2] > 0]
        if draw:
            self.director.draw(self.cv)

    def audio_bytes(self):
        self._acc += SR / self.cfg.fps
        n = int(self._acc)
        self._acc -= n
        return self.audio.chunk(n)

    # ------------------------------------------------------------------ ffmpeg
    def ffmpeg_cmd(self, audio_fd, out_file=None):
        c = self.cfg
        kbps = int(c.bitrate.lower().rstrip("k"))
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{c.width}x{c.height}", "-framerate", str(c.fps),
               "-probesize", "32", "-analyzeduration", "0", "-thread_queue_size", "64", "-i", "pipe:0",
               "-f", "s16le", "-ar", str(SR), "-ac", "1", "-probesize", "32", "-analyzeduration", "0",
               "-thread_queue_size", "512", "-i", f"pipe:{audio_fd}",
               "-map", "0:v", "-map", "1:a",
               "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-preset", c.preset, "-profile:v", "high", "-b:v", c.bitrate,
               "-maxrate", c.bitrate, "-bufsize", f"{kbps * 2}k", "-g", str(c.fps * 2), "-keyint_min", str(c.fps * 2),
               "-sc_threshold", "0", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
        if out_file:
            return cmd + ["-tune", "animation", "-movflags", "+faststart", out_file]
        tee = "|".join(f"[f=flv:flvflags=no_duration_filesize:onfail=ignore]{u}" for u in c.urls)
        return cmd + ["-tune", "zerolatency", "-f", "tee", tee]

    def _spawn(self, out_file=None):
        ar, aw = os.pipe()
        proc = subprocess.Popen(self.ffmpeg_cmd(ar, out_file), stdin=subprocess.PIPE, pass_fds=(ar,))
        os.close(ar)
        return proc, os.fdopen(aw, "wb", buffering=0)

    # ------------------------------------------------------------------ live loop
    def run_live(self):
        cfg, backoff = self.cfg, 5
        log.info("outputs: %s", ", ".join(mask(u) for u in cfg.urls))
        while not self.stop.is_set() and not self.director.finished:
            began = time.time()
            self._session()
            if self.stop.is_set() or self.director.finished:
                break
            self.tele.restarts += 1
            self.tele.connected = False
            backoff = 5 if time.time() - began > 90 else min(backoff * 2, 60)
            log.warning("ffmpeg stopped - restarting in %ds (restart #%d)", backoff, self.tele.restarts)
            self.stop.wait(backoff)
        self.stats.save(force=True)
        log.info("stream ended")

    def _session(self):
        proc, aud = self._spawn()
        dt, nxt, last_bytes, last_save, win = 1.0 / self.cfg.fps, time.time(), None, time.time(), []
        self.tele.connected = True
        try:
            while not self.stop.is_set() and not self.director.finished and proc.poll() is None:
                now = time.time()
                late = now - nxt
                t0 = time.time()
                if late > dt * 1.5 and last_bytes is not None:     # behind schedule: keep clock, repeat last frame
                    self.step(draw=False)
                    frame = last_bytes
                    self.tele.dropped += 1
                else:
                    self.step()
                    frame = last_bytes = self.cv.img.tobytes()
                aud.write(self.audio_bytes())
                proc.stdin.write(frame)
                self.tele.frames += 1
                self.tele.last_frame = time.time()
                win = (win + [(time.time() - t0) * 1000])[-60:]
                self.tele.render_ms = sum(win) / len(win)
                nxt += dt
                if nxt - time.time() > 0:
                    time.sleep(nxt - time.time())
                elif late > 2:
                    nxt = time.time()                              # way behind (e.g. network stall): resync
                if time.time() - last_save > 15:
                    self.stats.save()
                    last_save = time.time()
        except (BrokenPipeError, OSError):
            pass
        finally:
            for f in (aud, proc.stdin):
                try:
                    f.close()
                except Exception:
                    pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()

    # ------------------------------------------------------------------ offline test clip
    def run_test(self, seconds):
        self.clock.sim = time.time()
        self.cfg.minutes = min(self.cfg.minutes, max(0.1, seconds / len(self.cfg.games) / 60 - 0.2))
        self.director.minutes = self.cfg.minutes
        proc, aud = self._spawn("test.mp4")
        t0 = time.time()
        try:
            for _ in range(int(seconds * self.cfg.fps)):
                self.step()
                aud.write(self.audio_bytes())
                proc.stdin.write(self.cv.img.tobytes())
        finally:
            aud.close()
            proc.stdin.close()
            proc.wait()
        log.info("wrote test.mp4 (%.0fs video in %.1fs; render speed x%.1f realtime)", seconds, time.time() - t0, seconds / (time.time() - t0))

    # ------------------------------------------------------------------ preview PNGs
    def run_shots(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.clock.sim = time.time()
        d, cv = self.director, self.cv

        def save(name):
            self.ctx.toasts.clear() if name.endswith("intro.png") else None
            d.draw(cv)
            cv.img.save(os.path.join(folder, name))
            log.info("saved %s", name)

        for i, g in enumerate(d.games):
            d._begin(i)
            for _ in range(60 * 70):                       # play ~70 s of game time
                g.update()
                self.ctx.parts.update()
            d.state, d.timer = "intro", 1.6
            save(f"{g.key}_1_intro.png")
            d.state = "play"
            d.seg_ticks = 60 * 40
            save(f"{g.key}_2_gameplay.png")
        d.state, d.timer, d.reason = "outro", 1.2, "goal"
        self.ctx.cfg.goals.setdefault(d.game.key, __import__("streamer.config", fromlist=["Goal"]).Goal(100))
        self.ctx.parts.confetti(100, ["#ffd93d", "#35e0a1", "#35c4ff", "#ff6b9d"])
        for _ in range(40):
            self.ctx.parts.update()
        save("outro_goal_reached.png")
        d.state, d.timer, d.reason = "outro", 1.2, "time"
        save("outro_round_complete.png")
        d.state = "final"
        save("final_results.png")

    # ------------------------------------------------------------------ monitoring
    def start_http(self):
        port, me = self.cfg.port, self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body.encode())

            def do_GET(self):
                t = me.tele
                healthy = me.stop.is_set() or time.time() - t.last_frame < 15 or time.time() - t.started < 60
                if self.path.startswith("/health"):
                    self._send(200 if healthy else 503, "ok" if healthy else "stalled", "text/plain")
                elif self.path.startswith("/metrics"):
                    ex = me.director.snapshot()
                    lines = [f"autostream_frames_total {t.frames}", f"autostream_frames_dropped_total {t.dropped}",
                             f"autostream_ffmpeg_restarts_total {t.restarts}", f"autostream_render_ms {t.render_ms:.2f}",
                             f"autostream_uptime_seconds {time.time() - t.started:.0f}",
                             f"autostream_campaign_seconds {ex['elapsed']}"]
                    lines += [f'autostream_record{{game="{k}"}} {v}' for k, v in ex["records"].items()]
                    self._send(200, "\n".join(lines) + "\n", "text/plain")
                else:
                    ex = me.director.snapshot()
                    ex.update(frames=t.frames, restarts=t.restarts, dropped=t.dropped, render_ms=round(t.render_ms, 2),
                              connected=t.connected, healthy=healthy)
                    self._send(200, json.dumps(ex))

        srv = ThreadingHTTPServer(("0.0.0.0", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("status endpoint on :%d  (/health /metrics /)", port)
