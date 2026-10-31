import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonstar_music.models import MusicBrief, Section
from moonstar_music.providers.acestep_music import AceStepMusicProvider


def _brief(instrumental=True, lyrics=None, duration=30):
    return MusicBrief(
        title="T",
        genre="lofi",
        mood="calm",
        bpm=80,
        key="C Major",
        instrumental=instrumental,
        lyrics=lyrics,
        duration_sec=duration,
        sections=[Section(name="intro", seconds=10, prompt="soft keys")],
        style_prompt="dreamy lofi beat",
    )


def _json(payload):
    return MagicMock(json=lambda: payload, raise_for_status=lambda: None)


def _submit():
    return _json({"data": {"task_id": "t1", "status": "queued"}, "code": 200})


def _status(status, items=None):
    result = json.dumps(items) if items is not None else ""
    return _json({"data": [{"task_id": "t1", "status": status, "result": result}], "code": 200})


def _done():
    return _status(1, [{"file": "/v1/audio?path=%2Ftmp%2Fa.wav", "metas": {"duration": 31.5}}])


def _audio(content=b"wav-bytes"):
    return MagicMock(content=content, raise_for_status=lambda: None)


def _provider(tmp_path, **kw):
    return AceStepMusicProvider(base_url="http://x:8001/", output_dir=str(tmp_path), poll_interval=0, **kw)


@pytest.mark.asyncio
async def test_request_shape_and_download(tmp_path):
    p = _provider(tmp_path)
    post = AsyncMock(side_effect=[_submit(), _done()])
    with patch.object(p.client, "post", post), patch.object(p.client, "get", AsyncMock(return_value=_audio())) as get:
        r = await p.generate_track(_brief())
    submit = post.call_args_list[0]
    assert submit.args[0] == "http://x:8001/release_task"
    body = submit.kwargs["json"]
    assert "dreamy lofi beat" in body["prompt"] and "soft keys" in body["prompt"]
    assert body["lyrics"] == "[Instrumental]"
    assert body["audio_duration"] == 30 and body["bpm"] == 80 and body["key_scale"] == "C Major"
    assert body["batch_size"] == 1 and body["audio_format"] == "wav"
    assert post.call_args_list[1].args[0] == "http://x:8001/query_result"
    assert post.call_args_list[1].kwargs["json"] == {"task_id_list": ["t1"]}
    assert get.call_args.args[0] == "http://x:8001/v1/audio?path=%2Ftmp%2Fa.wav"
    assert r.format == "wav" and r.duration_sec == 31.5 and r.path.endswith(".wav")
    await p.close()


@pytest.mark.asyncio
async def test_song_sends_lyrics_and_clamps_duration(tmp_path):
    p = _provider(tmp_path)
    post = AsyncMock(side_effect=[_submit(), _done()])
    with patch.object(p.client, "post", post), patch.object(p.client, "get", AsyncMock(return_value=_audio())):
        await p.generate_track(_brief(instrumental=False, lyrics="[verse]\nla la", duration=900))
    body = post.call_args_list[0].kwargs["json"]
    assert body["lyrics"] == "[verse]\nla la"
    assert body["audio_duration"] == 600
    await p.close()


@pytest.mark.asyncio
async def test_polls_until_done(tmp_path):
    p = _provider(tmp_path)
    post = AsyncMock(side_effect=[_submit(), _status(0), _status(0), _done()])
    with patch.object(p.client, "post", post), patch.object(p.client, "get", AsyncMock(return_value=_audio())):
        await p.generate_track(_brief())
    assert post.call_count == 4
    await p.close()


@pytest.mark.asyncio
async def test_failed_task_raises(tmp_path):
    p = _provider(tmp_path)
    with patch.object(p.client, "post", AsyncMock(side_effect=[_submit(), _status(2)])):
        with pytest.raises(RuntimeError, match="failed"):
            await p.generate_track(_brief())
    await p.close()


@pytest.mark.asyncio
async def test_timeout_raises(tmp_path):
    p = _provider(tmp_path, timeout_sec=0)
    with patch.object(p.client, "post", AsyncMock(side_effect=[_submit(), _status(0)])):
        with pytest.raises(TimeoutError):
            await p.generate_track(_brief())
    await p.close()


@pytest.mark.asyncio
async def test_empty_audio_raises(tmp_path):
    p = _provider(tmp_path)
    with patch.object(p.client, "post", AsyncMock(side_effect=[_submit(), _done()])), \
            patch.object(p.client, "get", AsyncMock(return_value=_audio(b""))):
        with pytest.raises(RuntimeError, match="empty"):
            await p.generate_track(_brief())
    await p.close()


@pytest.mark.asyncio
async def test_api_key_sent_as_bearer(tmp_path):
    p = _provider(tmp_path, api_key="secret")
    post = AsyncMock(side_effect=[_submit(), _done()])
    with patch.object(p.client, "post", post), patch.object(p.client, "get", AsyncMock(return_value=_audio())):
        await p.generate_track(_brief())
    assert post.call_args_list[0].kwargs["headers"] == {"Authorization": "Bearer secret"}
    await p.close()


@pytest.mark.asyncio
async def test_cover_uploads_multipart(tmp_path):
    src = tmp_path / "sketch.wav"
    src.write_bytes(b"RIFFsrc")
    p = _provider(tmp_path)
    post = AsyncMock(side_effect=[_submit(), _done()])
    brief = _brief(instrumental=False, lyrics="la la").model_copy(
        update={"source_audio": str(src), "cover_strength": 0.4})
    with patch.object(p.client, "post", post), patch.object(p.client, "get", AsyncMock(return_value=_audio())):
        await p.generate_track(brief)
    kw = post.call_args_list[0].kwargs
    assert "json" not in kw
    assert kw["data"]["task_type"] == "cover" and kw["data"]["audio_cover_strength"] == "0.4"
    assert kw["data"]["lyrics"] == "la la" and kw["data"]["thinking"] == "false"
    assert kw["files"]["src_audio"] == ("sketch.wav", b"RIFFsrc", "audio/wav")
    await p.close()
