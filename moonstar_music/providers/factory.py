import json
import pathlib

from moonstar_music.config import Settings
from moonstar_music.providers.base import MusicGenProvider, PublishProvider
from moonstar_music.providers.elevenlabs_music import ElevenLabsMusicProvider
from moonstar_music.providers.minimax_music import MiniMaxMusicProvider
from moonstar_music.providers.youtube import YouTubeProvider

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "providers.json"


def _load_provider_config() -> dict:
    return json.loads(_CONFIG_PATH.read_text())


def build_music_provider(settings: Settings) -> MusicGenProvider:
    name = _load_provider_config()["music_provider"]
    if name == "elevenlabs_music":
        return ElevenLabsMusicProvider(api_key=settings.elevenlabs_api_key, output_dir=settings.output_dir)
    if name == "minimax_music":
        if not settings.minimax_api_key:
            raise ValueError("music_provider 'minimax_music' requires MINIMAX_API_KEY to be set")
        return MiniMaxMusicProvider(api_key=settings.minimax_api_key, output_dir=settings.output_dir)
    raise ValueError(f"Unknown music_provider: {name}")


def build_publish_provider(settings: Settings) -> PublishProvider:
    name = _load_provider_config()["publish_provider"]
    if name == "youtube":
        return YouTubeProvider(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            refresh_token=settings.youtube_refresh_token,
            privacy_status=settings.publish_privacy,
        )
    raise ValueError(f"Unknown publish_provider: {name}")
