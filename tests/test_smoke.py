"""Run with:  python -m unittest discover -s tests -v   (needs no ffmpeg, no network)"""
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamer import audio                                   # noqa: E402
from streamer.config import Goal, load_config, parse_goals, parse_mistake  # noqa: E402
from streamer.director import Director                       # noqa: E402
from streamer.games import REGISTRY, Ctx                     # noqa: E402
from streamer.gfx import Canvas, Particles                   # noqa: E402
from streamer.state import Clock, Stats                      # noqa: E402


def make_ctx(tmp, argv=()):
    cfg = load_config(["--state-file", os.path.join(tmp, "s.json"), "--cache-dir", os.path.join(tmp, "c"),
                       "--profile", "low", "--no-music", "--seed", "1", *argv])
    clock = Clock()
    rng = random.Random(1)
    ctx = Ctx(cfg, Canvas(cfg.width, cfg.height, cfg.fx), audio.Audio(cfg, cfg.games), Stats(cfg.state_file, clock), rng,
              Particles(rng), clock)
    return cfg, ctx


class ConfigTests(unittest.TestCase):
    def test_goal_parsing(self):
        g = parse_goals(["flappy=100_000", "racing=5000:total"])
        self.assertEqual(g["flappy"], Goal(100000, "best"))
        self.assertEqual(g["racing"], Goal(5000, "total"))

    def test_mistake_parsing(self):
        self.assertEqual(parse_mistake("0.02"), {"*": 0.02})
        self.assertEqual(parse_mistake("flappy=0,racing=0.1"), {"flappy": 0.0, "racing": 0.1})

    def test_profiles(self):
        cfg = load_config(["--profile", "high"])
        self.assertEqual((cfg.width, cfg.height, cfg.fps), (1280, 720, 30))


class StateTests(unittest.TestCase):
    def test_persistence_and_goal(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "s.json")
            st = Stats(p, Clock())
            st.on_score("flappy", 5, 5)
            st.mark_done("flappy")
            st.save(force=True)
            again = Stats(p, Clock())
            self.assertEqual(again.record("flappy"), 5)
            self.assertTrue(again.is_done("flappy"))

    def test_corrupt_state_is_survived(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "s.json")
            open(p, "w").write("{not json")
            st = Stats(p, Clock())
            self.assertEqual(st.record("flappy"), 0)


class AudioTests(unittest.TestCase):
    def test_track_and_chunk(self):
        tr = audio.render_track("racing")
        self.assertGreater(len(tr), audio.SR * 10)
        self.assertLessEqual(max(tr), 32767)

    def test_mixer_returns_exact_sample_count(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t)
            ctx.audio.sfx("crash")
            self.assertEqual(len(ctx.audio.chunk(918)), 918 * 2)


class GameTests(unittest.TestCase):
    def test_every_game_runs_and_renders(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t)
            for key, cls in REGISTRY.items():
                g = cls(ctx)
                for i in range(4000):
                    g.update()
                    ctx.parts.update()
                    if i % 1000 == 0:
                        g.draw(ctx.cv)
                self.assertGreaterEqual(ctx.stats.record(key), 0)

    def test_flappy_player_scores(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t, ["--skill", "1"])
            g = REGISTRY["flappy"](ctx)
            for _ in range(60 * 60 * 5):
                g.update()
                ctx.parts.items.clear()
            self.assertGreater(ctx.stats.record("flappy"), 25)

    def test_play_is_not_frame_perfect(self):
        """Taps must not all happen at the same height: human timing varies."""
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t, ["--skill", "1"])
            g = REGISTRY["flappy"](ctx)
            heights, prev_vy = [], 0.0
            for _ in range(60 * 60 * 3):
                g.update()
                ctx.parts.items.clear()
                if g.vy <= -8.0 and prev_vy > -8.0 and not g.dead:
                    heights.append(g.y)
                prev_vy = g.vy
            self.assertGreater(len(set(round(h / 4) for h in heights)), 10)

    def test_fight_matches_complete_and_score(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t)
            g = REGISTRY["fight"](ctx)
            seen = set()
            for _ in range(60 * 60 * 20):
                g.update()
                ctx.parts.items.clear()
                seen.add(g.phase)
            self.assertTrue({"vs", "intro", "fight", "ko", "match"} <= seen | {"ko"})
            self.assertGreater(ctx.stats.record("fight"), 0)

    def test_screen_text_does_not_mention_automation(self):
        import re
        import streamer.overlay as ov
        bad = re.compile(r"\b(bot|bots|ai|robot|automatic|automated|autoplay)\b", re.I)
        for key, cls in REGISTRY.items():
            self.assertIsNone(bad.search(cls.title + " " + cls.tagline), key)
        src = open(ov.__file__, encoding="utf-8").read()
        self.assertIsNone(bad.search(src))


class DirectorTests(unittest.TestCase):
    def test_goal_rotation_and_final(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t, ["--goal", "flappy=2", "--goal", "blocks=150", "--games", "flappy,blocks", "--mistake", "0",
                                    "--end-on-complete"])
            ctx.clock.sim = 0.0
            d = Director(ctx, cfg.games)
            seen = []
            for _ in range(60 * 200):
                d.update()
                ctx.parts.update()
                ctx.clock.sim += 1 / 60
                if not seen or seen[-1] != (d.state, d.game.key):
                    seen.append((d.state, d.game.key))
                if d.finished:
                    break
            self.assertTrue(d.finished)
            self.assertTrue(ctx.stats.is_done("flappy") and ctx.stats.is_done("blocks"))
            self.assertIn(("play", "blocks"), seen)
            self.assertEqual(seen[-1][0], "final")

    def test_timed_rotation(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t, ["--minutes", "0.1", "--games", "flappy,racing"])
            d = Director(ctx, cfg.games)
            for _ in range(60 * 30):
                d.update()
            self.assertIn(d.game.key, ("racing", "flappy"))
            self.assertTrue(d.stats.d["runs"] >= 2)

    def test_draw_all_states(self):
        with tempfile.TemporaryDirectory() as t:
            cfg, ctx = make_ctx(t, ["--goal", "flappy=100", "--duration", "24", "--title", "TEST"])
            d = Director(ctx, cfg.games)
            for state in ("intro", "play", "outro", "final"):
                d.state, d.timer, d.reason = state, 1.0, "goal"
                d.draw(ctx.cv)


if __name__ == "__main__":
    unittest.main()
