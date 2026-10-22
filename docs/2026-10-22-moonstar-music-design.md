# moonstar-music — Design Spec

**Date**: 2026-10-22
**Status**: Draft — defaults chosen by Claude (user opted out of Q&A); every item under "Claude's calls" is open to change

## Purpose

A new sibling repo, `moonstar-music`, that auto-generates AI music on a schedule: brief → track render → master → library → (optional) publish. Direct counterpart to `moonstar-video`; same shape, same isolation rules.

## Relationship to the Workbench

Pure HTTP client of `moonstar-rs` (`POST /pipelines/run` + poll `GET /sessions/{id}`). No imports from moonstar-rs. All creative reasoning (concept, brief, prompt-writing) lives in a `music_brief` pipeline; `moonstar-music` handles only music-gen provider calls, ffmpeg mastering, the track library, and publishing. See the `moonstar-client-module` skill for the boundary pattern.

## Architecture

```
moonstar_music/loop.py (scheduled cycle)
   │
   ├─ 1. GatewayClient.get_brief(theme, mode) → music_brief pipeline
   │     returns: title, genre, mood, bpm, key, instrumental, lyrics|null,
   │              duration_sec, sections[], style_prompt
   │
   ├─ 2. MusicGenProvider.generate_track(brief) → TrackResult(path, format, duration)
   │     (retry w/ backoff; abort cycle on final failure — no partial tracks)
   │
   ├─ 3. mastering.master(path) → ffmpeg loudnorm (-14 LUFS), trim silence,
   │     fade-out, export mp3 320k + wav
   │
   ├─ 4. library.add(track, brief) → data/library/<id>/{track.mp3, track.wav, brief.json, meta.json}
   │
   ├─ 5. (optional) PublishProvider.upload(...) → URL
   │     v1: YouTube, static cover art + ffmpeg waveform visualizer video
   │
   └─ 6. sleep LOOP_INTERVAL_SECONDS
```

Each stage has its own `try/except`; one failing stage never crashes the process.

## Goals

- Unattended generation of complete, listenable tracks (instrumental or with lyrics).
- Provider swap via `providers.json` — config change, not code change.
- Cheap and bounded: per-cycle cost cap, daily track cap.
- Every track reproducible: brief + provider + params stored beside the audio.
- All tests mocked — no network or API spend.

## Non-goals (v1)

- Stem separation, remixing, or editing existing audio.
- Voice cloning / imitating named artists.
- Multi-platform publishing (Spotify/DistroKid etc.); `PublishProvider` leaves room.
- Human approval UI (a manual `--hold` flag is enough).
- Local GPU generation (MusicGen/Stable Audio Open) — possible later provider; fits the `moonstar-soup` GPU add-on pattern.

## Anti-goals (a failure even if it "works")

- Prompts naming real artists, songs, or copyrighted lyrics.
- Silent fallback to a different provider (log loudly; mirror the silent-fallback lesson from kaggle work).
- Publishing a track that failed quality gates.

## Components

### 1. `music_brief` pipeline (`moonstar_music/pipelines/music_brief.yaml`)

Two `LlmTransform`s, models via `{{MODEL_*}}` placeholders in `models.json` (never literal names):

- **concept** — theme + mode (`instrumental` | `song`) + optional genre seed + recent-titles list (avoid repeats) → direction, mood, genre, bpm, key.
- **arranger** — turns concept into the structured brief: `sections[]` (intro/verse/chorus/bridge/outro with seconds + per-section prompt), `style_prompt` (provider-agnostic descriptive text), `lyrics` (song mode only, original, with section tags), `title`.
- Hard rule in both system prompts: no artist names, no existing song titles/lyrics.
- Budget: ~30k tokens, $0.50, 180s wallclock.

Output JSON:
```json
{"title":"","genre":"","mood":"","bpm":96,"key":"A minor","instrumental":true,
 "lyrics":null,"duration_sec":120,
 "sections":[{"name":"intro","seconds":15,"prompt":"..."}],
 "style_prompt":"..."}
```

### 2. Provider layer (`moonstar_music/providers/`)

`Protocol`s in `base.py`, registered in `factory.py` + `providers.json`:

| Interface | v1 default | Alt (stub-ready) |
|---|---|---|
| `MusicGenProvider.generate_track(brief) -> TrackResult` | **ElevenLabs Music** (official API, structured sections, commercial-licensed) | MiniMax Music (key already in workbench), Stability Stable Audio, Google Lyria |
| `PublishProvider.upload(video_path, title, description) -> url` | YouTube | — |

Providers translate the neutral brief into their own request shape (e.g. sections → composition plan). Async submit → poll → download pattern where the API is async.

### 3. Mastering (`mastering.py`)

ffmpeg via `subprocess` (same dependency as moonstar-video): `loudnorm` to -14 LUFS, silence trim, 2s fade-out, output mp3 + wav. Plus a duration/silence sanity check as the v1 quality gate: reject if shorter than 50% of requested, or >20% silence.

### 4. Library (`library.py`)

Directory-per-track under `data/library/` with `brief.json` and `meta.json` (provider, params, cost, timestamps, published URL). Plain files; a SQLite index is out of scope. Recent titles are read back to feed the concept transform.

### 5. Publishing (optional, off by default)

`PUBLISH_ENABLED=false` by default. When on: ffmpeg renders cover image + `showwaves` visualizer to mp4, YouTube resumable upload (OAuth refresh pattern copied from moonstar-video, not imported — the repos stay independent). Description includes an "AI-generated" disclosure.

## Config (`.env.example`)

```
MOONSTAR_GATEWAY_URL=http://localhost:8000
MOONSTAR_AUTH_TOKEN=<required>
ELEVENLABS_API_KEY=<required>
MINIMAX_API_KEY=<optional>
PUBLISH_ENABLED=false
YOUTUBE_CLIENT_ID= / YOUTUBE_CLIENT_SECRET= / YOUTUBE_REFRESH_TOKEN=
LOOP_INTERVAL_SECONDS=21600
MAX_TRACKS_PER_DAY=4
CYCLE_MAX_USD=1.00
OUTPUT_DIR=./data
LOG_LEVEL=INFO
```

## Layout

```
moonstar-music/
  moonstar_music/{loop,cli,config,gateway_client,mastering,library}.py
  moonstar_music/providers/{base,factory,elevenlabs_music,minimax_music,youtube}.py
  moonstar_music/pipelines/{music_brief.yaml,models.json}
  moonstar_music/providers.json
  tests/        # one file per module, all mocked
  music.sh      # at workbench root, mirrors video.sh
  pyproject.toml, .env.example, README.md
```

## Testing

pytest, all HTTP and ffmpeg mocked; one real-ffmpeg test of `mastering` on a generated sine tone (no network). Provider tests assert request shape + poll/timeout/failure paths.

## Claude's calls (change any of these)

1. **ElevenLabs Music as default provider** — official API, licensing is clearer than Suno/Udio (no official Suno API; unofficial wrappers risk ToS/breakage). You already hold an ElevenLabs key from video.
2. **Provider API field names are unverified** — written from documented patterns; must be checked against current docs before first live run (same caveat as the Hailuo provider).
3. **Publishing off by default**, YouTube-only with a visualizer video.
4. **Full-track-per-call**, no stitching of sections; long-form (>~5 min) deferred.
5. **Gate is a simple duration/silence check**; no audio-quality model or LLM listening critic in v1.
6. **Standalone repo `moonstar-music/`** with `music.sh` at workbench root.
7. **Output target unknown** — I don't know whether this is for a channel, game/video background tracks, or personal use; it affects publishing, licensing and cadence.
8. **Could feed moonstar-video** (background score per video) — deliberately out of scope; would be a file handoff, not an import.

## Open for later

- Local GPU provider via moonstar-soup pattern.
- LLM/audio-embedding critic gate before publish.
- Soundtrack mode: accept a moonstar-video storyboard and score it.
