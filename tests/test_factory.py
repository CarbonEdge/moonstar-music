import pytest

from moonstar_music.config import Settings
from moonstar_music.providers import factory
from moonstar_music.providers.elevenlabs_music import ElevenLabsMusicProvider
from moonstar_music.providers.minimax_music import MiniMaxMusicProvider
from moonstar_music.providers.youtube import YouTubeProvider


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, moonstar_gateway_url="u", moonstar_auth_token="t",
                    elevenlabs_api_key="k", output_dir=str(tmp_path), **kw)


def test_factory_builds_known_providers(tmp_path):
    s = _settings(tmp_path, publish_privacy="unlisted")
    assert isinstance(factory.build_music_provider(s), ElevenLabsMusicProvider)
    pub = factory.build_publish_provider(s)
    assert isinstance(pub, YouTubeProvider)
    assert pub.privacy_status == "unlisted"


def test_factory_builds_minimax(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, "_load_provider_config", lambda: {"music_provider": "minimax_music", "publish_provider": "youtube"})
    assert isinstance(factory.build_music_provider(_settings(tmp_path, minimax_api_key="m")), MiniMaxMusicProvider)
    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        factory.build_music_provider(_settings(tmp_path))


def test_factory_unknown_provider_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, "_load_provider_config", lambda: {"music_provider": "nope", "publish_provider": "nope"})
    with pytest.raises(ValueError):
        factory.build_music_provider(_settings(tmp_path))
    with pytest.raises(ValueError):
        factory.build_publish_provider(_settings(tmp_path))
