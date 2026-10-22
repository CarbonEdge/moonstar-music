# moonstar-music

AI music generation and optional publishing loop. Pure HTTP client of the Moonstar gateway (`moonstar-rs`); no sibling-repo imports.

## Architecture

```
moonstar_music/loop.py (scheduled cycle)
   |
   |- 0. daily cap reached? -> skip (no gateway call, no spend)
   |- 1. GatewayClient.get_brief(theme, mode, recent_titles) -> music_brief pipeline
   |      (gateway spend > CYCLE_MAX_USD -> abort before any rendering)
   |- 2. MusicGenProvider.generate_track(brief)   (3 attempts; then abort - NO fallback provider)
   |- 3. probe + quality gate (too short / too much silence -> reject, library untouched)
   |- 4. mastering.master -> loudnorm -14 LUFS, fade-out, mp3 + wav
   |- 5. library.add -> data/library/<id>/{track.mp3, track.wav, brief.json, meta.json}
   |- 6. (optional) render_visualizer -> PublishProvider.upload -> meta.published_url
   '- 7. sleep LOOP_INTERVAL_SECONDS
```

A failing cycle is logged and never crashes the loop.

## Install

```bash
cd moonstar-music
pip install -e ".[dev]"
cp .env.example .env   # fill in values
```

Requires `ffmpeg` on `PATH` for mastering and the visualizer.

## Config (`.env`)

| Var | Default | Notes |
|---|---|---|
| `MOONSTAR_GATEWAY_URL` / `MOONSTAR_AUTH_TOKEN` | - | gateway + bearer token |
| `ELEVENLABS_API_KEY` | - | default music provider |
| `MINIMAX_API_KEY` | empty | only if `providers.json` selects `minimax_music` |
| `PUBLISH_ENABLED` | `false` | publishing is off by default |
| `PUBLISH_PRIVACY` | `private` | `private` / `unlisted` / `public` |
| `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` | empty | needed when publishing |
| `LOOP_INTERVAL_SECONDS` | `21600` | |
| `MAX_TRACKS_PER_DAY` | `4` | UTC day, counted from the library |
| `CYCLE_MAX_USD` | `1.00` | gateway-spend ceiling per cycle |
| `OUTPUT_DIR` | `./data` | |

Providers are chosen in `moonstar_music/providers.json` (`elevenlabs_music` or `minimax_music`; `youtube`). Pipeline models: `moonstar_music/pipelines/models.json`.

## Running

```bash
bash moonstar-music/music.sh          # from the workbench root: gateway + worker + loop
python -m moonstar_music.cli --once --theme "rainy city lo-fi" --mode instrumental
python -m moonstar_music.cli --help
```

Without `--theme`, built-in themes rotate and modes alternate instrumental/song.

## Testing

```bash
python -m pytest tests/ -q
```

All tests are mocked (no network, no spend). ffmpeg-dependent tests skip when ffmpeg is missing.

## Known Gaps

- ElevenLabs / MiniMax endpoints and model ids are unverified against live APIs.
- ffmpeg filter strings (mastering and visualizer) have never been run against a real ffmpeg.
- No live end-to-end run yet.
- Silence threshold (-50dB / 0.5s) is a guess.
