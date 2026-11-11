# AutoStream v2 - self-playing games for 24/7 live streams

The games play themselves with human-style input (reaction time, uneven timing, small slips) - **Flappy Bird**, **Car Racing** and **Block Stacker** and **Street Clash** (an original fighting game: 6 fighters, 3 stages, best-of-three rounds, super meter, combos) with HD graphics, music and sound effects,
and the video is streamed straight to YouTube / Kick / any RTMP server. Pure Python (+ Pillow) and ffmpeg. No browser.

## Quick start

**Termux (Android)**
```
pkg update -y && pkg upgrade -y
pkg install -y python python-pillow ffmpeg
python stream.py --test 20            # makes test.mp4 so you can check video + music first
termux-wake-lock
python stream.py --url rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY --profile low --fx 1
```
Use `pkg install python-pillow`, never `pip install` in Termux. Set Termux battery use to *Unrestricted*, keep the phone charging, run inside `tmux`.

**Linux / VPS / Docker**
```
pip install -r requirements.txt && sudo apt install ffmpeg
python stream.py --url rtmp://a.rtmp.youtube.com/live2/YOUR_KEY

docker compose up -d --build         # edit docker-compose.yml first (keys, goals)
```
Render / Koyeb: deploy as a **Docker** service, add a persistent disk at `/data`, set env vars (see below), health path `/health`.

## The challenge feature (goals)

Give a game a goal and it **stays on screen until that score is reached**, then celebrates and switches to the next game.
Games without a goal rotate every `--minutes`. When every goal is done the final results card is shown
(`--end-on-complete` then ends the stream).

```
python stream.py --url ... --skill 1 --duration 24 --title "24H CHALLENGE" \
   --goal flappy=60000:total --goal racing=200000:total --goal blocks=2000000:total
```
* `game=N` - one single run must reach N points. `game=N:total` - points of all runs added together.
* `--duration H` - stream length in hours (shows a TIME LEFT countdown, then the results card).
* `--skill 0..1` (default 0.85) - how steady the on-screen player is. 1 = calm and precise, 0.6 = casual with visible mistakes. Mistakes come from reaction time and timing, so crashes look natural.
* `--mistake 0.02` - optional extra chance of a deliberate slip per obstacle (per game: `--mistake flappy=0,racing=0.02`). Default 0.
* Progress is saved to `state.json`, so a restart / redeploy **resumes the challenge** (all-time high scores are kept forever).
  `--reset-campaign` starts a new challenge.

**Realistic targets** (measured over 1-2 hours of simulated play at `--skill 1`; the app warns when a goal can't fit `--duration`):

| Game | Score | Pace per hour | Longest single run |
|---|---|---|---|
| Flappy Bird | 1 per pipe | ~3,000 | ~500-900 (then it crashes, like a person would) |
| Car Racing | 10 per car passed + distance | ~40,000 | ~8,000 |
| Block Stacker | points | ~550,000 | ~100,000-140,000 |
| Street Clash | points (25/round win, +25 perfect, +100 per match; champion stays on, streak resets when beaten) | ~2,800 | ~400 |

So for a 24-hour challenge use **`:total`** goals (all runs added up): about 60,000-70,000 pipes, 900,000 racing points, 13 million block points.
Single-run goals (`game=N` without `:total`) only suit scores near the longest-run column - a person-like player crashes eventually.

## On-screen
Score + **all-time high score** per game (saved), live goal progress bar, time left, "NOW PLAYING / NEXT in mm:ss" ticker,
"UP NEXT" banner before a switch, full-screen **NOW PLAYING** card at every switch, **GOAL REACHED** celebration, new-high-score toasts.

## Music & sound
Background music for each game is composed by the program on first start (about 1-3 s on a PC, longer on a phone) and cached.
Sound effects: flap, points, crashes, line clears, level-up, records, goals, transitions.
* `--volume 0.5`, `--no-music`, `--no-sfx`
* Your own music: `--music-dir ./music` (mp3/wav/ogg/flac, plays as a looping playlist). Use only music you have the rights to - YouTube checks for copyright.

## Options (CLI flag / env var)
| Flag | Env | Default | |
|---|---|---|---|
| `--url` (repeat) | `STREAM_URLS` (comma) | | RTMP(S) URLs incl. key. One encode is sent to all of them |
| `--profile` | `PROFILE` | medium | low 360p20 / medium 480p24 / high 720p30 / ultra 1080p30 |
| `--width --height --fps --bitrate --preset` | `WIDTH HEIGHT FPS VIDEO_BITRATE PRESET` | by profile | overrides |
| `--fx 0\|1\|2` | `FX` | 2 | 0 = fastest (no glow/vignette), 2 = full |
| `--games` | `GAMES` | flappy,racing,blocks,fight | order of rotation |
| `--minutes` | `MINUTES` | 10 | per game without a goal |
| `--goal` | `GOALS` | | `flappy=100000,racing=5000:total` |
| `--skill` | `SKILL` | 0.85 | player precision 0..1 (1 = steady, 0.6 = casual) |
| `--mistake` | `MISTAKE` | 0 | extra deliberate slips per obstacle |
| `--duration` | `DURATION_HOURS` | 0 | hours; 0 = unlimited |
| `--end-on-complete` | `END_ON_COMPLETE` | off | exit when finished |
| `--title` | `TITLE` | | shown on the high-score board |
| `--state-file --cache-dir` | `STATE_FILE CACHE_DIR` | state/state.json, cache | mount a volume here in Docker |
| `--port` | `PORT` | 0 | status server |
| `--config file.json` | `CONFIG_FILE` | | same options in a file (see config.example.json) |
| `--test SEC` / `--shots DIR` | | | make test.mp4 / save PNG previews of every screen |

Priority: command line > config file > environment > defaults.

## CPU and RAM (measured)
Measured here on a 2-core 2.8 GHz Intel Xeon (Linux), streaming to a local file, 30 s average after warm-up. CPU is % of ONE core
(100 = one full core); RAM is the peak resident memory of the Python process + ffmpeg.

| Profile | Python CPU | ffmpeg CPU | Total CPU | Total RAM | Frame time |
|---|---|---|---|---|---|
| low 360p20, `--fx 0 --preset ultrafast` | 10% | 13% | ~23% | ~130 MB | 5 ms |
| low 360p20, `--fx 1` | 10% | 19% | ~29% | ~110 MB | 6 ms |
| medium 480p24 (default) | 22% | 29% | ~51% | ~125 MB | 10 ms |
| high 720p30 | 51% | 60% | ~111% | ~180 MB | 21 ms of a 33 ms budget |

Rules of thumb: medium needs about 1 vCPU and 256 MB RAM; high needs about 2 vCPU and 384 MB (it dropped 10 of 1,192 frames on a
shared core, so give it headroom); ultra 1080p was not measured but expect roughly 2x the 720p figures. Each extra platform you add
to `--url` costs almost nothing, because the video is encoded once. The first start also composes the music (a few seconds on a PC,
longer on a phone) and caches it. Phone chips vary a lot: start with `--profile low --fx 1` and raise it if `render_ms` in
`/metrics` stays well under 1000/fps.

## Production notes
* **Resilience** - if ffmpeg or the network drops, it reconnects with back-off (5 s up to 60 s); game state and scores continue. SIGTERM saves state and exits cleanly. If the machine is too slow it repeats frames instead of drifting out of sync (`dropped` in metrics).
* **Monitoring** - with `--port 8000`: `/health` (503 if frames stall), `/metrics` (Prometheus text), `/` (JSON status).
* **Security** - stream keys are masked in logs. Pass them via env vars / secrets, never commit them. The container runs as a non-root user.
* **Scaling** - one encode feeds many platforms (tee muxer), so adding Kick costs almost no extra CPU. For several channels run one container per channel (own keys, own `/data` volume). Pick the profile by CPU: ~0.5 vCPU for `low`, ~1 vCPU for `medium`, ~2 vCPU for `high`.
* **Tests** - `python -m unittest discover -s tests -v` (12 tests, no ffmpeg needed).
* **Logs** - timestamped to stdout (`--log-level DEBUG`).

## Troubleshooting
* *Choppy video* -> `--profile low --fx 0 --preset ultrafast`; check `render_ms` in `/metrics` (must stay well below 1000/fps).
* *No sound* -> check `--volume`, and that `--no-music` is not set.
* *YouTube says "no data"* -> start the stream in YouTube Studio first, check the key, try `--profile medium`.
* YouTube may limit channels with repetitive automated content; add commentary or variety.
