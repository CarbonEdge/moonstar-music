import pytest
from pydantic import ValidationError

from moonstar_music.config import Settings


def test_defaults():
    s = Settings(_env_file=None, moonstar_gateway_url="u", moonstar_auth_token="t", elevenlabs_api_key="k")
    assert s.publish_enabled is False
    assert s.loop_interval_seconds == 21600
    assert s.max_tracks_per_day == 4
    assert s.output_dir == "./data"


def test_missing_required_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, moonstar_auth_token="t", elevenlabs_api_key="k")
