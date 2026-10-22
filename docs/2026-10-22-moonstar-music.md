# moonstar-music Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new sibling repo `moonstar-music/` that auto-generates AI music on a schedule (brief → render → master → library → optional publish).

**Architecture:** Python async loop, pure HTTP client of moonstar-rs (`POST /pipelines/run` + poll `GET /sessions/{id}`). Provider `Protocol`s selected via `providers.json`. ffmpeg via `subprocess` for mastering. Mirrors `moonstar-video` file-for-file where possible — read it as the style reference.

**Tech Stack:** Python >=3.11, httpx, pydantic / pydantic-settings, pytest + pytest-asyncio, hatchling, ffmpeg on PATH.

**Spec:** `docs/superpowers/specs/2026-10-22-moonstar-music-design.md`

**Style reference:** `moonstar-video/moonstar_video/{config,gateway_client,loop}.py`, `providers/factory.py`, `tests/test_gateway_client.py` (same mock style: `AsyncMock` for `post`/`get`, `Settings(_env_file=None, ...)`).

## Global Constraints

- New standalone git repo at `D:\dev\Moonstar-Workbench\moonstar-music\`; **no imports from moonstar-rs, moonstar-video or any sibling** (copy code, never import).
- Package name `moonstar_music`; CLI `moonstar-music = moonstar_music.cli:main`.
- Never hardcode model names in YAML — `{{MODEL_*}}` placeholders resolved from `pipelines/models.json`.
- Pipeline transform type is `LlmTransform` (not `llm_call`). Budget: `max_total_tokens: 30000`, `max_usd: 0.50`, `max_wallclock_seconds: 180`.
- Gateway terminal statuses: `completed`, `failed`, `rejected` — all handled; poll every 2s, max 90 iterations.
- Mastering target: **-14 LUFS** loudnorm, 2s fade-out, output mp3 320k + wav.
- Quality gate: reject if duration < 50% of requested or > 20% silence.
- Defaults: `LOOP_INTERVAL_SECONDS=21600`, `MAX_TRACKS_PER_DAY=4`, `CYCLE_MAX_USD=1.00`, `PUBLISH_ENABLED=false`, `OUTPUT_DIR=./data`.
- Prompts must forbid artist names, existing song titles and copyrighted lyrics.
- Provider failure → abort cycle; **no silent fallback to another provider**. Log loudly.
- Never commit `.env`. Conventional commits (`feat`, `test`, `fix`, `docs`, `chore`). All tests mocked — no network, no API spend.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Review Focus

- Gateway returns JSON wrapped in ```` ```json ```` fences → still parsed (Task 5).
- Brief with `instrumental: true` but non-null `lyrics` → lyrics dropped before provider call (Task 2/3).
- Provider returns empty/zero-byte audio → treated as failure, not saved (Tasks 3, 4).
- Daily cap already reached → cycle skips generation and spends nothing (Task 9).
- Two tracks with identical titles → distinct library dirs, no overwrite (Task 7).

---

## Task 1: Repo scaffold, config, test harness

**Files:**
- Create: `moonstar-music/{pyproject.toml,.gitignore,.env.example}`, `moonstar_music/{__init__.py,config.py}`, `tests/{conftest.py,test_config.py}`

**Interfaces:**
- Produces: `Settings` (pydantic-settings, `.env`, `extra="ignore"`) with fields `moonstar_gateway_url: str`, `moonstar_auth_token: str`, `elevenlabs_api_key: str`, `minimax_api_key: str = ""`, `publish_enabled: bool = False`, `youtube_client_id/youtube_client_secret/youtube_refresh_token: str = ""`, `loop_interval_seconds: int = 21600`, `max_tracks_per_day: int = 4`, `cycle_max_usd: float = 1.00`, `output_dir: str = "./data"`, `log_level: str = "INFO"`; `get_settings() -> Settings` (`lru_cache`).

- [ ] **Step 1:** `git init` in `moonstar-music/`; add `.gitignore` (`.env`, `data/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info`). Copy `pyproject.toml` shape from moonstar-video (name `moonstar-music`, dev extra `pytest`, `pytest-asyncio`; add `[tool.pytest.ini_options] asyncio_mode = "auto"`). `pip install -e ".[dev]"`.
- [ ] **Step 2: Failing tests** in `tests/test_config.py`: `test_defaults` (build `Settings(_env_file=None, moonstar_gateway_url="u", moonstar_auth_token="t", elevenlabs_api_key="k")` → asserts `publish_enabled is False`, `loop_interval_seconds == 21600`, `max_tracks_per_day == 4`, `output_dir == "./data"`); `test_missing_required_raises` (no gateway url → `ValidationError`). `conftest.py` pops `MOONSTAR_AUTH_TOKEN` from env like moonstar-video's.
- [ ] **Step 3:** Run `python -m pytest tests/test_config.py -q` → FAIL (no module).
- [ ] **Step 4:** Implement `config.py` per Interfaces; write `.env.example` from the spec's Config block.
- [ ] **Step 5:** Run tests → PASS. Commit `chore: scaffold moonstar-music`.

## Task 2: Provider interfaces and brief model

**Files:**
- Create: `moonstar_music/models.py`, `moonstar_music/providers/{__init__.py,base.py}`, `tests/test_models.py`

**Interfaces:**
- Produces in `models.py`: `Section(name: str, seconds: int, prompt: str)`; `MusicBrief(title: str, genre: str, mood: str, bpm: int, key: str, instrumental: bool, lyrics: str | None, duration_sec: int, sections: list[Section], style_prompt: str)` (pydantic) with a validator that sets `lyrics = None` when `instrumental` is true.
- Produces in `base.py`: `@dataclass TrackResult(path: str, format: str, duration_sec: float)`; `class MusicGenProvider(Protocol): async def generate_track(self, brief: MusicBrief) -> TrackResult`; `class PublishProvider(Protocol): async def upload(self, video_path: str, title: str, description: str) -> str`.

- [ ] **Step 1: Failing tests:** `test_instrumental_drops_lyrics` (brief with `instrumental=True, lyrics="la la"` → `.lyrics is None`); `test_song_keeps_lyrics`; `test_brief_roundtrips_json` (`MusicBrief.model_validate_json(b.model_dump_json()) == b`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: brief model and provider protocols`.

## Task 3: ElevenLabs Music provider

**Files:**
- Create: `moonstar_music/providers/elevenlabs_music.py`, `tests/test_providers_elevenlabs_music.py`

**Interfaces:**
- Consumes: `MusicBrief`, `TrackResult` (Task 2).
- Produces: `class ElevenLabsMusicProvider(api_key: str, output_dir: str)` implementing `MusicGenProvider`; writes `<output_dir>/raw/<uuid>.mp3`, returns `TrackResult(path, "mp3", duration_sec)` where `duration_sec` comes from the requested `brief.duration_sec` (mastering measures the real length).

- [ ] **Step 1: Failing tests** (mock `httpx.AsyncClient.post`): `test_request_shape` — POST to `https://api.elevenlabs.io/v1/music`, header `xi-api-key`, JSON has `prompt` containing `brief.style_prompt` and `music_length_ms == brief.duration_sec * 1000`; `test_writes_audio_file` — response bytes saved, `TrackResult.path` exists; `test_empty_body_raises` — zero-byte response → `RuntimeError`; `test_http_error_raises` — 500 → exception propagates; `test_lyrics_included_only_for_songs`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; `timeout=300.0` (synchronous generation). Sections are folded into the prompt text (one line per section with seconds) — do not rely on a composition-plan field.
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `feat: ElevenLabs music provider`.
- **Caveat to carry into code comments and README:** endpoint/field names are from documented patterns, unverified against live responses — check current ElevenLabs Music docs before the first live run.

## Task 4: MiniMax Music provider

**Files:**
- Create: `moonstar_music/providers/minimax_music.py`, `tests/test_providers_minimax_music.py`

**Interfaces:**
- Produces: `class MiniMaxMusicProvider(api_key: str, output_dir: str)` implementing `MusicGenProvider`. Same output contract as Task 3 (`raw/<uuid>.mp3`).

- [ ] **Step 1: Failing tests:** `test_request_shape` (POST `https://api.minimax.io/v1/music_generation`, `Authorization: Bearer`, body has `model` and `prompt`); `test_decodes_hex_audio` (response `{"data":{"audio":"<hex>"}}` → file bytes equal `bytes.fromhex`); `test_empty_audio_raises`; `test_instrumental_sends_no_lyrics`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** Commit `feat: MiniMax music provider`. Same unverified-API caveat as Task 3.

## Task 5: Gateway client and `music_brief` pipeline

**Files:**
- Create: `moonstar_music/gateway_client.py`, `moonstar_music/pipelines/{music_brief.yaml,models.json}`, `tests/test_gateway_client.py`

**Interfaces:**
- Consumes: `Settings`, `MusicBrief`.
- Produces: `class GatewayClient(settings)` with `close()`, `run_pipeline(yaml_spec, initial_input, transform_name) -> tuple[str | None, float]` (copy moonstar-video's implementation, incl. fence stripping and `spend_usd`), and `get_brief(theme: str, mode: str, recent_titles: list[str]) -> tuple[MusicBrief | None, float]` (`mode` is `"instrumental"` or `"song"`; returns the brief plus spend).
- `models.json`: `{"MODEL_CONCEPT": "deepseek/deepseek-v4-flash", "MODEL_ARRANGER": "deepseek/deepseek-v4-pro"}`.
- `music_brief.yaml`: transforms `concept` (`LlmTransform`, `{{MODEL_CONCEPT}}`) → `arranger` (`LlmTransform`, `input: [concept]`, `{{MODEL_ARRANGER}}`, outputs the MusicBrief JSON only); both system prompts carry the no-artists/no-existing-lyrics rule and instruct "OUTPUT ONLY JSON, no fences"; arranger prompt includes the `recent_titles` avoid-list instruction; budget per Global Constraints.

- [ ] **Step 1: Failing tests** (port moonstar-video's test style): `test_run_pipeline_completed_returns_result_and_cost`; `test_failed_status_returns_none`; `test_rejected_status_returns_none`; `test_fenced_json_is_stripped` (response ```` ```json\n{...}\n``` ```` parses); `test_get_brief_parses_valid_brief`; `test_get_brief_invalid_json_returns_none`; `test_yaml_has_no_unresolved_placeholders` (loaded YAML contains no `{{`); `test_initial_input_carries_theme_mode_recent_titles`. Patch `asyncio.sleep` so tests are instant.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** Commit `feat: gateway client and music_brief pipeline`.

## Task 6: Mastering and quality gate

**Files:**
- Create: `moonstar_music/mastering.py`, `tests/test_mastering.py`

**Interfaces:**
- Produces: `probe(path: str) -> Probe` where `Probe(duration_sec: float, silence_ratio: float)` (ffprobe for duration, ffmpeg `silencedetect` for silence); `master(raw_path: str, out_dir: str) -> MasteredTrack` where `MasteredTrack(mp3_path: str, wav_path: str, duration_sec: float)` (loudnorm I=-14, trim leading/trailing silence, 2s `afade` out, mp3 320k + wav); `check_quality(p: Probe, requested_sec: int) -> str | None` returning a rejection reason or `None`.

- [ ] **Step 1: Failing tests:** `test_check_quality_rejects_short` (`Probe(50, 0.0)` vs requested 120 → reason string); `test_check_quality_rejects_silent` (`Probe(120, 0.25)` → reason); `test_check_quality_accepts` (`Probe(118, 0.02)` → `None`); `test_master_produces_files` — **real ffmpeg**: generate a 6s 440Hz sine wav in `tmp_path` via `ffmpeg -f lavfi -i sine=...`, call `master`, assert mp3 and wav exist and `duration_sec` within 1s of 6 (skip with `pytest.skip` if `shutil.which("ffmpeg")` is None); `test_master_raises_on_missing_input`.
- [ ] **Step 2–4:** fail → implement via `subprocess.run(..., check=True)` → pass. **Step 5:** Commit `feat: ffmpeg mastering and quality gate`.

## Task 7: Track library

**Files:**
- Create: `moonstar_music/library.py`, `tests/test_library.py`

**Interfaces:**
- Consumes: `MusicBrief`, `MasteredTrack`.
- Produces: `class Library(root: str)` with `add(brief, mastered, provider: str, cost_usd: float) -> str` (returns track id; creates `<root>/library/<id>/{track.mp3,track.wav,brief.json,meta.json}`; id = `YYYYMMDD-HHMMSS-<slug>` with a numeric suffix on collision), `recent_titles(n: int = 20) -> list[str]`, `count_today() -> int`, `set_published_url(track_id: str, url: str) -> None`. `meta.json` holds provider, cost_usd, created_at (UTC ISO), published_url (null).

- [ ] **Step 1: Failing tests:** `test_add_creates_all_files`; `test_same_title_twice_gets_distinct_dirs`; `test_recent_titles_newest_first_and_limited`; `test_count_today_counts_only_today` (backdate one `created_at` in meta.json); `test_set_published_url_updates_meta`; `test_empty_library_ok` (`recent_titles() == []`, `count_today() == 0`).
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** Commit `feat: track library`.

## Task 8: YouTube publisher with visualizer video

**Files:**
- Create: `moonstar_music/providers/youtube.py`, `moonstar_music/visualizer.py`, `tests/{test_providers_youtube.py,test_visualizer.py}`

**Interfaces:**
- Produces: `render_visualizer(mp3_path: str, out_path: str, cover_image: str | None = None) -> str` (ffmpeg `showwaves` over a solid/cover background → mp4, returns `out_path`); `class YouTubeProvider(client_id, client_secret, refresh_token)` implementing `PublishProvider` — OAuth token refresh (`https://oauth2.googleapis.com/token`) then resumable upload; description is `description` plus the line `AI-generated music.` Port logic from `moonstar-video/moonstar_video/providers/youtube.py` (copy, don't import).

- [ ] **Step 1: Failing tests:** `test_refreshes_token_then_uploads` (mock calls in order, returns `https://youtu.be/<id>`); `test_description_has_ai_disclosure`; `test_upload_failure_raises`; `test_render_visualizer_makes_mp4` (real ffmpeg on a 3s sine; skip if no ffmpeg).
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** Commit `feat: YouTube publisher and visualizer`.

## Task 9: Factory, loop, CLI, music.sh, README

**Files:**
- Create: `moonstar_music/{providers/factory.py,loop.py,cli.py,providers.json}`, `music.sh`, `README.md`, `tests/{test_factory.py,test_loop.py}`

**Interfaces:**
- Consumes: everything above.
- Produces: `providers.json` = `{"music_provider": "elevenlabs_music", "publish_provider": "youtube"}`; `build_music_provider(settings) -> MusicGenProvider` and `build_publish_provider(settings) -> PublishProvider` (unknown name → `ValueError`); `async run_one_cycle(gateway, music_provider, publish_provider | None, library, theme: str, mode: str, settings) -> str | None` returning the new track id, or `None` on skip/failure; `async run_music_loop(theme_provider: Callable[[], tuple[str, str]], settings=None)`; `main()`.
- Cycle order: if `library.count_today() >= max_tracks_per_day` → log and return `None` **before any gateway call** → `get_brief` (pass `library.recent_titles()`) → `generate_track` with up to 3 attempts → `probe` + `check_quality` (reject → log reason, return `None`, do not add to library) → `master` → `library.add` → if `settings.publish_enabled` and publisher given: `render_visualizer` then `upload` then `set_published_url`. Track cumulative spend; if gateway spend alone exceeds `cycle_max_usd`, abort before rendering. Loop wraps each cycle in try/except and sleeps `loop_interval_seconds`.
- `music.sh`: mirrors `moonstar-video/video.sh` (gateway → worker → loop; Ctrl+C stops all). `cli.py` supports `--once` (single cycle) and `--theme TEXT --mode instrumental|song`; default theme provider rotates a small built-in list of generic themes (e.g. "rainy city lo-fi", "epic cinematic build", "upbeat synth-pop") alternating modes.

- [ ] **Step 1: Failing tests:** `test_factory_builds_known_providers`; `test_factory_unknown_provider_raises`; `test_cycle_happy_path_adds_to_library` (all collaborators mocked; assert library has 1 track, publish not called when `publish_enabled=False`); `test_cycle_publishes_when_enabled`; `test_cycle_skips_when_daily_cap_reached` (assert gateway `get_brief` never awaited); `test_cycle_aborts_when_gateway_returns_none`; `test_cycle_retries_provider_then_aborts` (3 failures → `None`, provider awaited 3 times, nothing in library); `test_cycle_rejects_failed_quality_gate` (library untouched, no publish); `test_cycle_aborts_over_budget`; `test_loop_survives_cycle_exception` (cycle raises once, loop continues; patch `asyncio.sleep` to raise `CancelledError` on second call).
- [ ] **Step 2–4:** fail → implement → full `python -m pytest tests/ -q` PASS.
- [ ] **Step 5:** README (architecture diagram from spec, install, config, running, testing, **Known Gaps** = unverified ElevenLabs/MiniMax endpoints, no live run yet). Commit `feat: loop, CLI, factory and docs`.
- [ ] **Step 6: Smoke check (no spend):** `python -m moonstar_music.cli --help` exits 0; `python -m pytest tests/ -q` all green. Report the count.

---

## Self-Review

- **Spec coverage:** pipeline (T5), providers ElevenLabs/MiniMax/YouTube (T3/4/8), mastering + gate (T6), library (T7), publish off-by-default + disclosure (T8/9), caps/budget (T9), config (T1), layout/music.sh/README (T9), tests mocked (all). Non-goals untouched.
- **Spec drift:** spec lists `music.sh` at workbench root; video.sh actually lives inside the repo, so the plan puts it in `moonstar-music/` (mirrors video).
- **Types:** `MusicBrief`/`TrackResult`/`MasteredTrack`/`Probe` names are used consistently across tasks 2–9.
