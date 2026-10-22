from unittest.mock import AsyncMock, patch

import pytest

from moonstar_music import gateway_client as gc
from moonstar_music.config import Settings
from moonstar_music.gateway_client import GatewayClient
from moonstar_music.models import MusicBrief

BRIEF_JSON = (
    '{"title": "Night Tide", "genre": "ambient", "mood": "calm", "bpm": 70, "key": "A minor", '
    '"instrumental": true, "lyrics": null, "duration_sec": 120, '
    '"sections": [{"name": "intro", "seconds": 120, "prompt": "soft pads"}], '
    '"style_prompt": "slow ambient pads"}'
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        moonstar_gateway_url="http://localhost:8000",
        moonstar_auth_token="tok",
        elevenlabs_api_key="el",
    )


def _resp(data):
    return AsyncMock(raise_for_status=lambda: None, json=lambda: data)


async def _run(client, status_data, transform="arranger"):
    mock_post = AsyncMock(return_value=_resp({"session_id": "s-1"}))
    mock_get = AsyncMock(return_value=_resp(status_data))
    with patch("asyncio.sleep", AsyncMock()), patch.object(
        client.client, "post", mock_post
    ), patch.object(client.client, "get", mock_get):
        return await client.run_pipeline("yaml", {"theme": "x"}, transform)


def _completed(response, spend=0.42):
    return {
        "status": "completed",
        "spend_usd": spend,
        "artifacts": [{"transform_name": "arranger", "data": {"response": response}}],
    }


async def test_run_pipeline_completed_returns_result_and_cost():
    client = GatewayClient(_settings())
    result, cost = await _run(client, _completed('{"title": "x"}'))
    assert result == '{"title": "x"}'
    assert abs(cost - 0.42) < 1e-9
    await client.close()


async def test_failed_status_returns_none():
    client = GatewayClient(_settings())
    result, cost = await _run(client, {"status": "failed"})
    assert result is None and cost == 0.0
    await client.close()


async def test_rejected_status_returns_none():
    client = GatewayClient(_settings())
    result, cost = await _run(client, {"status": "rejected"})
    assert result is None and cost == 0.0
    await client.close()


async def test_fenced_json_is_stripped():
    client = GatewayClient(_settings())
    result, _ = await _run(client, _completed("```json\n" + BRIEF_JSON + "\n```"))
    assert result == BRIEF_JSON
    assert MusicBrief.model_validate_json(result).title == "Night Tide"
    await client.close()


async def test_get_brief_parses_valid_brief():
    client = GatewayClient(_settings())
    with patch.object(client, "run_pipeline", AsyncMock(return_value=(BRIEF_JSON, 0.05))):
        brief, spend = await client.get_brief("rain", "instrumental", [])
    assert isinstance(brief, MusicBrief)
    assert brief.title == "Night Tide"
    assert brief.lyrics is None
    assert spend == 0.05
    await client.close()


async def test_get_brief_invalid_json_returns_none():
    client = GatewayClient(_settings())
    with patch.object(client, "run_pipeline", AsyncMock(return_value=("not json", 0.05))):
        brief, spend = await client.get_brief("rain", "song", [])
    assert brief is None
    assert spend == 0.05
    await client.close()


def test_yaml_has_no_unresolved_placeholders():
    assert "{{" not in gc._MUSIC_BRIEF_YAML
    assert "LlmTransform" in gc._MUSIC_BRIEF_YAML


async def test_initial_input_carries_theme_mode_recent_titles():
    client = GatewayClient(_settings())
    mock = AsyncMock(return_value=(BRIEF_JSON, 0.0))
    with patch.object(client, "run_pipeline", mock):
        await client.get_brief("rain", "song", ["A", "B"])
    yaml_spec, initial_input, transform = mock.call_args.args
    assert initial_input == {"theme": "rain", "mode": "song", "recent_titles": ["A", "B"]}
    assert transform == "arranger"
    assert yaml_spec == gc._MUSIC_BRIEF_YAML
    await client.close()
