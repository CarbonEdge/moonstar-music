"""Test configuration: ensure a clean env for every test."""
import pytest

_ENV_VARS = (
    "MOONSTAR_GATEWAY_URL", "MOONSTAR_AUTH_TOKEN", "ELEVENLABS_API_KEY", "MINIMAX_API_KEY",
    "PUBLISH_ENABLED", "PUBLISH_PRIVACY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN", "LOOP_INTERVAL_SECONDS", "MAX_TRACKS_PER_DAY", "CYCLE_MAX_USD",
    "OUTPUT_DIR", "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ENV_VARS:
        monkeypatch.delenv(k, raising=False)
