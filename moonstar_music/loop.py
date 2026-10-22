import asyncio
import logging
import os
from typing import Callable

from moonstar_music.config import Settings, get_settings
from moonstar_music.gateway_client import GatewayClient
from moonstar_music.library import Library
from moonstar_music.mastering import check_quality, master, probe
from moonstar_music.providers.base import MusicGenProvider, PublishProvider, TrackResult
from moonstar_music.providers.factory import build_music_provider, build_publish_provider
from moonstar_music.visualizer import render_visualizer

logger = logging.getLogger(__name__)

_MAX_GENERATE_ATTEMPTS = 3

DEFAULT_THEMES = ["rainy city lo-fi", "epic cinematic build", "upbeat synth-pop"]


def default_theme_provider() -> Callable[[], tuple[str, str]]:
    """Rotate generic themes, alternating instrumental/song modes."""
    state = {"i": 0}

    def _next() -> tuple[str, str]:
        i = state["i"]
        state["i"] += 1
        return DEFAULT_THEMES[i % len(DEFAULT_THEMES)], ("instrumental" if i % 2 == 0 else "song")

    return _next


async def _generate(provider: MusicGenProvider, brief) -> TrackResult | None:
    for attempt in range(1, _MAX_GENERATE_ATTEMPTS + 1):
        try:
            return await provider.generate_track(brief)
        except Exception as e:
            logger.error("Track generation failed (attempt %d/%d): %s", attempt, _MAX_GENERATE_ATTEMPTS, e)
    return None


async def run_one_cycle(
    gateway: GatewayClient,
    music_provider: MusicGenProvider,
    publish_provider: PublishProvider | None,
    library: Library,
    theme: str,
    mode: str,
    settings: Settings,
) -> str | None:
    """brief -> generate -> quality gate -> master -> library -> (publish). Returns track id or None."""
    if library.count_today() >= settings.max_tracks_per_day:
        logger.info("Daily cap of %d tracks reached; skipping cycle", settings.max_tracks_per_day)
        return None

    brief, spend = await gateway.get_brief(theme, mode, library.recent_titles())
    if brief is None:
        logger.error("Brief generation failed for theme=%r; aborting cycle", theme)
        return None
    if spend > settings.cycle_max_usd:
        logger.error("Gateway spend $%.2f exceeds cycle cap $%.2f; aborting before rendering",
                     spend, settings.cycle_max_usd)
        return None

    result = await _generate(music_provider, brief)
    if result is None:
        logger.error("Provider failed after %d attempts; aborting cycle (no fallback)", _MAX_GENERATE_ATTEMPTS)
        return None

    reason = check_quality(probe(result.path), brief.duration_sec)
    if reason is not None:
        logger.error("Quality gate rejected track %r: %s", brief.title, reason)
        return None

    mastered = master(result.path, os.path.join(settings.output_dir, "mastered"))
    track_id = library.add(brief, mastered, type(music_provider).__name__, spend)
    logger.info("Added track %s to library", track_id)

    if settings.publish_enabled and publish_provider is not None:
        try:
            video_path = render_visualizer(
                mastered.mp3_path, os.path.join(settings.output_dir, "video", f"{track_id}.mp4"))
            description = f"{brief.title} - {brief.genre}, {brief.mood}."
            url = await publish_provider.upload(video_path=video_path, title=brief.title, description=description)
            library.set_published_url(track_id, url)
            logger.info("Published %s: %s", track_id, url)
        except Exception as e:
            logger.error("Publish failed for %s (track kept in library): %s", track_id, e)
    return track_id


async def _close_all(*objs) -> None:
    for o in objs:
        close = getattr(o, "close", None)
        if close is not None:
            await close()


async def run_music_loop(theme_provider: Callable[[], tuple[str, str]], settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    gateway = GatewayClient(settings)
    music_provider = build_music_provider(settings)
    publish_provider = build_publish_provider(settings) if settings.publish_enabled else None
    library = Library(settings.output_dir)
    try:
        while True:
            try:
                theme, mode = theme_provider()
                await run_one_cycle(gateway, music_provider, publish_provider, library, theme, mode, settings)
            except Exception:
                logger.exception("Cycle failed")
            await asyncio.sleep(settings.loop_interval_seconds)
    finally:
        await _close_all(gateway, music_provider, publish_provider)
