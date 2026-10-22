import argparse
import asyncio
import logging

from moonstar_music.config import get_settings
from moonstar_music.gateway_client import GatewayClient
from moonstar_music.library import Library
from moonstar_music.loop import _close_all, default_theme_provider, run_music_loop, run_one_cycle
from moonstar_music.providers.factory import build_music_provider, build_publish_provider


async def _run_once(theme: str, mode: str) -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    gateway = GatewayClient(settings)
    music = build_music_provider(settings)
    publisher = build_publish_provider(settings) if settings.publish_enabled else None
    try:
        track_id = await run_one_cycle(gateway, music, publisher, Library(settings.output_dir),
                                       theme, mode, settings)
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
    args = parser.parse_args(argv)

    theme_provider = build_theme_provider(args)

    if args.once:
        asyncio.run(_run_once(*theme_provider()))
    else:
        asyncio.run(run_music_loop(theme_provider))


if __name__ == "__main__":
    main()
