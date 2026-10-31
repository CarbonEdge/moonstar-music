import argparse
import asyncio
import logging
import os

from moonstar_music.config import get_settings
from moonstar_music.gateway_client import GatewayClient
from moonstar_music.library import Library
from moonstar_music.loop import _close_all, default_theme_provider, run_music_loop, run_one_cycle
from moonstar_music.providers.factory import build_music_provider, build_publish_provider


async def _run_once(theme: str, mode: str, source_audio: str | None = None,
                    cover_strength: float = 0.6) -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    gateway = GatewayClient(settings)
    music = build_music_provider(settings)
    publisher = build_publish_provider(settings) if settings.publish_enabled else None
    try:
        track_id = await run_one_cycle(gateway, music, publisher, Library(settings.output_dir),
                                       theme, mode, settings, source_audio, cover_strength)
        print(f"track: {track_id}")
    finally:
        await _close_all(gateway, music, publisher)


def build_theme_provider(args: argparse.Namespace):
    if args.theme:
        theme, mode = args.theme, args.mode or "instrumental"
        return lambda: (theme, mode)
    return default_theme_provider(args.mode)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="moonstar-music", description="AI music generation loop")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--theme", help="theme text (default: rotate built-in themes)")
    parser.add_argument("--mode", choices=["instrumental", "song"], default=None,
                        help="default: instrumental with --theme, else alternate")
    parser.add_argument("--source", help="audio file to cover (ACE cover mode, e.g. a Magenta sketch)")
    parser.add_argument("--cover-strength", type=float, default=0.6,
                        help="0..1, how much of --source to keep (default 0.6)")
    args = parser.parse_args(argv)
    if not 0 <= args.cover_strength <= 1:
        parser.error("--cover-strength must be between 0 and 1")
    if args.source and not os.path.isfile(args.source):
        parser.error(f"--source not found: {args.source}")

    theme_provider = build_theme_provider(args)

    if args.once:
        asyncio.run(_run_once(*theme_provider(), args.source, args.cover_strength))
    else:
        asyncio.run(run_music_loop(theme_provider, source_audio=args.source, cover_strength=args.cover_strength))


if __name__ == "__main__":
    main()
