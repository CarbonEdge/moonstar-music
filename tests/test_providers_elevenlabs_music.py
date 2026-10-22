from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moonstar_music.models import MusicBrief, Section
from moonstar_music.providers.elevenlabs_music import ElevenLabsMusicProvider


def _brief(instrumental=True, lyrics=None):
    return MusicBrief(
        title="T",
        genre="lofi",
        mood="calm",
        bpm=80,
        key="C",
        instrumental=instrumental,
        lyrics=lyrics,
        duration_sec=30,
        sections=[Section(name="intro", seconds=10, prompt="soft keys")],
        style_prompt="dreamy lofi beat",
    )


def _resp(content=b"mp3-bytes"):
    return MagicMock(content=content, raise_for_status=lambda: None)


@pytest.mark.asyncio
async def test_request_shape(tmp_path):
    p = ElevenLabsMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp())) as post:
        await p.generate_track(_brief())
    assert post.call_args.args[0] == "https://api.elevenlabs.io/v1/music"
    assert post.call_args.kwargs["headers"]["xi-api-key"] == "k"
    body = post.call_args.kwargs["json"]
    assert "dreamy lofi beat" in body["prompt"]
    assert "intro" in body["prompt"] and "10" in body["prompt"]
    assert body["music_length_ms"] == 30000
    assert post.call_args.kwargs["timeout"] == 300.0
    await p.close()


@pytest.mark.asyncio
async def test_writes_audio_file(tmp_path):
    p = ElevenLabsMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp(b"abc"))):
        r = await p.generate_track(_brief())
    assert r.format == "mp3" and r.duration_sec == 30
    assert r.path.endswith(".mp3")
    assert (tmp_path / "raw") == __import__("pathlib").Path(r.path).parent
    assert open(r.path, "rb").read() == b"abc"
    await p.close()


@pytest.mark.asyncio
async def test_empty_body_raises(tmp_path):
    p = ElevenLabsMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp(b""))):
        with pytest.raises(RuntimeError):
            await p.generate_track(_brief())
    assert list((tmp_path / "raw").glob("*")) == []
    await p.close()


@pytest.mark.asyncio
async def test_http_error_raises(tmp_path):
    p = ElevenLabsMusicProvider(api_key="k", output_dir=str(tmp_path))
    req = httpx.Request("POST", "https://api.elevenlabs.io/v1/music")
    bad = MagicMock(content=b"x")
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=req, response=httpx.Response(500, request=req)
    )
    with patch.object(p.client, "post", AsyncMock(return_value=bad)):
        with pytest.raises(httpx.HTTPStatusError):
            await p.generate_track(_brief())
    await p.close()


@pytest.mark.asyncio
async def test_lyrics_included_only_for_songs(tmp_path):
    p = ElevenLabsMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp())) as post:
        await p.generate_track(_brief(instrumental=False, lyrics="la la la"))
        song = post.call_args.kwargs["json"]["prompt"]
        await p.generate_track(_brief(instrumental=True, lyrics="la la la"))
        inst = post.call_args.kwargs["json"]["prompt"]
    assert "la la la" in song
    assert "la la la" not in inst
    assert "instrumental" in inst.lower()
    await p.close()
