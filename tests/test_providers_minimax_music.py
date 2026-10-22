import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moonstar_music.models import MusicBrief, Section
from moonstar_music.providers.minimax_music import MiniMaxMusicProvider


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


def _resp(audio_hex="6d70332d6279746573"):
    r = MagicMock(raise_for_status=lambda: None)
    r.json.return_value = {"data": {"audio": audio_hex}}
    return r


@pytest.mark.asyncio
async def test_request_shape(tmp_path):
    p = MiniMaxMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp())) as post:
        await p.generate_track(_brief())
    assert post.call_args.args[0] == "https://api.minimax.io/v1/music_generation"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer k"
    body = post.call_args.kwargs["json"]
    assert body["model"]
    assert "dreamy lofi beat" in body["prompt"]
    assert post.call_args.kwargs["timeout"] == 300.0
    await p.close()


@pytest.mark.asyncio
async def test_decodes_hex_audio(tmp_path):
    p = MiniMaxMusicProvider(api_key="k", output_dir=str(tmp_path))
    hexed = "deadbeef0102"
    with patch.object(p.client, "post", AsyncMock(return_value=_resp(hexed))):
        r = await p.generate_track(_brief())
    assert r.format == "mp3" and r.duration_sec == 30
    assert r.path.endswith(".mp3")
    assert pathlib.Path(r.path).parent == tmp_path / "raw"
    assert pathlib.Path(r.path).read_bytes() == bytes.fromhex(hexed)
    await p.close()


@pytest.mark.asyncio
async def test_empty_audio_raises(tmp_path):
    p = MiniMaxMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp(""))):
        with pytest.raises(RuntimeError):
            await p.generate_track(_brief())
    assert list((tmp_path / "raw").glob("*")) == []
    await p.close()


@pytest.mark.asyncio
async def test_http_error_raises(tmp_path):
    p = MiniMaxMusicProvider(api_key="k", output_dir=str(tmp_path))
    req = httpx.Request("POST", "https://api.minimax.io/v1/music_generation")
    bad = MagicMock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=req, response=httpx.Response(500, request=req)
    )
    with patch.object(p.client, "post", AsyncMock(return_value=bad)):
        with pytest.raises(httpx.HTTPStatusError):
            await p.generate_track(_brief())
    await p.close()


@pytest.mark.asyncio
async def test_instrumental_sends_no_lyrics(tmp_path):
    p = MiniMaxMusicProvider(api_key="k", output_dir=str(tmp_path))
    with patch.object(p.client, "post", AsyncMock(return_value=_resp())) as post:
        await p.generate_track(_brief(instrumental=True, lyrics="la la la"))
        inst = post.call_args.kwargs["json"]
        await p.generate_track(_brief(instrumental=False, lyrics="la la la"))
        song = post.call_args.kwargs["json"]
    assert "la la la" not in str(inst)
    assert "lyrics" not in inst
    assert song["lyrics"] == "la la la"
    await p.close()
