import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from moonstar_music import loop
from moonstar_music.config import Settings
from moonstar_music.library import Library
from moonstar_music.mastering import MasteredTrack, Probe
from moonstar_music.models import MusicBrief, Section
from moonstar_music.providers.base import TrackResult


def _brief():
    return MusicBrief(title="Rainy Night", genre="lofi", mood="calm", bpm=80, key="C",
                      instrumental=True, duration_sec=120,
                      sections=[Section(name="a", seconds=120, prompt="p")], style_prompt="s")


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, moonstar_gateway_url="u", moonstar_auth_token="t",
                    elevenlabs_api_key="k", output_dir=str(tmp_path), **kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    gateway = MagicMock()
    gateway.get_brief = AsyncMock(return_value=(_brief(), 0.10))
    music = MagicMock()
    music.generate_track = AsyncMock(return_value=TrackResult(path="raw.mp3", format="mp3", duration_sec=120))
    pub = MagicMock()
    pub.upload = AsyncMock(return_value="https://youtu.be/x")
    mp3, wav = tmp_path / "m.mp3", tmp_path / "m.wav"
    mp3.write_bytes(b"a")
    wav.write_bytes(b"b")
    monkeypatch.setattr(loop, "probe", MagicMock(return_value=Probe(duration_sec=118, silence_ratio=0.0)))
    monkeypatch.setattr(loop, "master", MagicMock(return_value=MasteredTrack(str(mp3), str(wav), 118)))
    monkeypatch.setattr(loop, "render_visualizer", MagicMock(return_value="v.mp4"))
    return settings, gateway, music, pub, Library(str(tmp_path))


async def test_cycle_happy_path_adds_to_library(env):
    settings, gateway, music, pub, lib = env
    tid = await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings)
    assert tid and lib.count_today() == 1
    pub.upload.assert_not_awaited()
    loop.render_visualizer.assert_not_called()


async def test_cycle_publishes_when_enabled(env, tmp_path):
    _, gateway, music, pub, lib = env
    settings = _settings(tmp_path, publish_enabled=True)
    tid = await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings)
    pub.upload.assert_awaited_once()
    assert lib._read_json(tid, "meta.json")["published_url"] == "https://youtu.be/x"


async def test_cycle_skips_when_daily_cap_reached(env, tmp_path):
    _, gateway, music, pub, lib = env
    settings = _settings(tmp_path, max_tracks_per_day=1)
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings)
    gateway.get_brief.reset_mock()
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings) is None
    gateway.get_brief.assert_not_awaited()
    assert lib.count_today() == 1


async def test_cycle_aborts_when_gateway_returns_none(env):
    settings, gateway, music, pub, lib = env
    gateway.get_brief.return_value = (None, 0.0)
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings) is None
    music.generate_track.assert_not_awaited()


async def test_cycle_retries_provider_then_aborts(env):
    settings, gateway, music, pub, lib = env
    music.generate_track.side_effect = RuntimeError("boom")
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings) is None
    assert music.generate_track.await_count == 3
    assert lib.count_today() == 0 and lib.recent_titles() == []


async def test_cycle_rejects_failed_quality_gate(env, tmp_path):
    _, gateway, music, pub, lib = env
    settings = _settings(tmp_path, publish_enabled=True)
    loop.probe.return_value = Probe(duration_sec=10, silence_ratio=0.0)
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings) is None
    assert lib.count_today() == 0
    loop.master.assert_not_called()
    pub.upload.assert_not_awaited()


async def test_cycle_aborts_over_budget(env, tmp_path):
    _, gateway, music, pub, lib = env
    settings = _settings(tmp_path, cycle_max_usd=0.05, publish_enabled=True)
    assert await loop.run_one_cycle(gateway, music, pub, lib, "t", "instrumental", settings) is None
    loop.render_visualizer.assert_not_called()
    pub.upload.assert_not_awaited()
    assert lib.count_today() == 0


async def test_loop_survives_cycle_exception(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    cycle = AsyncMock(side_effect=[RuntimeError("x"), "id"])
    monkeypatch.setattr(loop, "run_one_cycle", cycle)
    monkeypatch.setattr(loop, "GatewayClient", MagicMock(return_value=MagicMock(close=AsyncMock())))
    monkeypatch.setattr(loop, "build_music_provider", MagicMock(return_value=MagicMock(spec=[])))
    monkeypatch.setattr(loop, "build_publish_provider", MagicMock(return_value=MagicMock(spec=[])))
    calls = {"n": 0}

    async def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(loop.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await loop.run_music_loop(lambda: ("t", "instrumental"), settings)
    assert cycle.await_count == 2
