from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moonstar_music.providers.youtube import YouTubeProvider


def _ok(json=None, headers=None):
    return MagicMock(raise_for_status=lambda: None, json=lambda: json or {}, headers=headers or {})


def _video(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"fake-video")
    return str(f)


@pytest.mark.asyncio
async def test_refreshes_token_then_uploads(tmp_path):
    p = YouTubeProvider("cid", "sec", "refresh")
    order = []

    async def post(url, **kw):
        order.append(("post", url))
        if "oauth2" in url:
            return _ok({"access_token": "tok"})
        return _ok(headers={"Location": "https://upload.example/session1"})

    async def put(url, **kw):
        order.append(("put", url))
        return _ok({"id": "abc123"})

    with patch.object(p.client, "post", AsyncMock(side_effect=post)) as mpost, \
            patch.object(p.client, "put", AsyncMock(side_effect=put)) as mput:
        url = await p.upload(_video(tmp_path), "Title", "Desc")
    assert url == "https://youtu.be/abc123"
    assert [o[0] for o in order] == ["post", "post", "put"]
    assert order[0][1] == "https://oauth2.googleapis.com/token"
    assert mpost.call_args_list[0].kwargs["data"]["refresh_token"] == "refresh"
    assert mpost.call_args_list[0].kwargs["data"]["grant_type"] == "refresh_token"
    assert "uploadType=resumable" in order[1][1]
    assert mpost.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer tok"
    assert order[2][1] == "https://upload.example/session1"
    assert mput.call_args.kwargs["content"] == b"fake-video"
    await p.close()


@pytest.mark.asyncio
async def test_description_has_ai_disclosure(tmp_path):
    p = YouTubeProvider("cid", "sec", "refresh")
    posts = AsyncMock(side_effect=[_ok({"access_token": "t"}), _ok(headers={"Location": "https://u/x"})])
    with patch.object(p.client, "post", posts), \
            patch.object(p.client, "put", AsyncMock(return_value=_ok({"id": "i"}))):
        await p.upload(_video(tmp_path), "T", "My description")
    desc = posts.call_args_list[1].kwargs["json"]["snippet"]["description"]
    assert desc.startswith("My description")
    assert desc.splitlines()[-1] == "AI-generated music."
    await p.close()


@pytest.mark.asyncio
async def test_upload_failure_raises(tmp_path):
    p = YouTubeProvider("cid", "sec", "refresh")
    req = httpx.Request("PUT", "https://u/x")
    bad = MagicMock(headers={})
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=req, response=httpx.Response(500, request=req))
    posts = AsyncMock(side_effect=[_ok({"access_token": "t"}), _ok(headers={"Location": "https://u/x"})])
    with patch.object(p.client, "post", posts), patch.object(p.client, "put", AsyncMock(return_value=bad)):
        with pytest.raises(httpx.HTTPStatusError):
            await p.upload(_video(tmp_path), "T", "D")
    await p.close()


@pytest.mark.asyncio
async def test_missing_session_location_raises(tmp_path):
    p = YouTubeProvider("cid", "sec", "refresh")
    posts = AsyncMock(side_effect=[_ok({"access_token": "t"}), _ok(headers={})])
    with patch.object(p.client, "post", posts):
        with pytest.raises(RuntimeError):
            await p.upload(_video(tmp_path), "T", "D")
    await p.close()


async def _body(tmp_path, **kw):
    p = YouTubeProvider("cid", "sec", "refresh", **kw)
    posts = AsyncMock(side_effect=[_ok({"access_token": "t"}), _ok(headers={"Location": "https://u/x"})])
    with patch.object(p.client, "post", posts),             patch.object(p.client, "put", AsyncMock(return_value=_ok({"id": "i"}))):
        await p.upload(_video(tmp_path), "T", "D")
    await p.close()
    return posts.call_args_list[1].kwargs["json"]


@pytest.mark.asyncio
async def test_privacy_defaults_to_private(tmp_path):
    assert (await _body(tmp_path))["status"]["privacyStatus"] == "private"


@pytest.mark.asyncio
async def test_privacy_public_passes_through(tmp_path):
    assert (await _body(tmp_path, privacy_status="public"))["status"]["privacyStatus"] == "public"


def test_invalid_privacy_raises():
    with pytest.raises(ValueError):
        YouTubeProvider("c", "s", "r", privacy_status="everyone")


@pytest.mark.asyncio
async def test_close_closes_client():
    p = YouTubeProvider("c", "s", "r")
    await p.close()
    assert p.client.is_closed
