from __future__ import annotations

import logging
import shutil
import signal
import sys

from .config import load_config


def main(argv=None):
    cfg = load_config(argv)
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("main")
    from .engine import Streamer

    if not cfg.shots and not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found.  Termux: pkg install ffmpeg   |   Debian/Ubuntu: apt install ffmpeg")
    if not cfg.shots and not cfg.test and not cfg.urls:
        sys.exit("No stream URL.  Example:\n  python stream.py --url rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY")

    s = Streamer(cfg)
    if cfg.shots:
        return s.run_shots(cfg.shots)
    if cfg.test:
        return s.run_test(cfg.test)

    def stop(*_):
        log.info("shutdown requested")
        s.stop.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if cfg.port:
        s.start_http()
    for g, goal in cfg.goals.items():
        log.info("goal: %s -> %s (%s)", g, f"{goal.target:,}", goal.mode)
    s.run_live()


if __name__ == "__main__":
    main()
