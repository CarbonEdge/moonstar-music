import asyncio
import json
import pathlib
import time
import uuid

import httpx

from moonstar_music.models import MusicBrief
from moonstar_music.providers.base import TrackResult

# Talks to a locally running ACE-Step 1.5 API server (`uv run acestep-api`, default
# http://localhost:8001). Flow: POST /release_task -> poll POST /query_result -> GET /v1/audio.
_MIN_SEC, _MAX_SEC = 10, 600
_STATUS_RUNNING, _STATUS_DONE, _STATUS_FAILED = 0, 1, 2
_INSTRUMENTAL_LYRICS = "[Instrumental]"


def _build_caption(brief: MusicBrief) -> str:
    parts = [brief.style_prompt, brief.genre, brief.mood]
    parts += [s.prompt for s in brief.sections]
    return ", ".join(p for p in parts if p)


class AceStepMusicProvider:
    """MusicGenProvider backed by a local ACE-Step 1.5 server (free, runs on the local GPU)."""

    def __init__(
        self,
        base_url: str,
        output_dir: str,
        api_key: str = "",
        poll_interval: float = 3.0,
        timeout_sec: float = 900.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.timeout_sec = timeout_sec
        self.raw_dir = pathlib.Path(output_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def generate_track(self, brief: MusicBrief) -> TrackResult:
        fields = {
            "prompt": _build_caption(brief),
            "lyrics": _INSTRUMENTAL_LYRICS if brief.instrumental else (brief.lyrics or ""),
            "audio_duration": max(_MIN_SEC, min(_MAX_SEC, brief.duration_sec)),
            "bpm": brief.bpm,
            "key_scale": brief.key,
            "vocal_language": "en",
            "audio_format": "wav",
            "batch_size": 1,
            "thinking": True,
        }
        if brief.source_audio:
            # Cover: JSON paths outside ACE's temp dir are rejected, so upload as multipart.
            src = pathlib.Path(brief.source_audio)
            fields.update(task_type="cover", audio_cover_strength=brief.cover_strength, thinking=False)
            req = {
                "data": {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in fields.items()},
                "files": {"src_audio": (src.name, src.read_bytes(), "audio/wav")},
            }
        else:
            req = {"json": fields}
        resp = await self.client.post(
            f"{self.base_url}/release_task", **req, headers=self._headers(), timeout=60.0,
        )
        resp.raise_for_status()
        task_id = resp.json()["data"]["task_id"]

        item = await self._wait(task_id)
        audio = await self.client.get(f"{self.base_url}{item['file']}", headers=self._headers(), timeout=120.0)
        audio.raise_for_status()
        if not audio.content:
            raise RuntimeError("ACE-Step returned an empty audio body")
        path = self.raw_dir / f"{uuid.uuid4().hex}.wav"
        path.write_bytes(audio.content)
        duration = float((item.get("metas") or {}).get("duration") or brief.duration_sec)
        return TrackResult(path=str(path), format="wav", duration_sec=duration)

    async def _wait(self, task_id: str) -> dict:
        deadline = time.monotonic() + self.timeout_sec
        while time.monotonic() < deadline:
            resp = await self.client.post(
                f"{self.base_url}/query_result",
                json={"task_id_list": [task_id]},
                headers=self._headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            entry = resp.json()["data"][0]
            status = entry["status"]
            if status == _STATUS_DONE:
                items = json.loads(entry["result"])
                if not items or not items[0].get("file"):
                    raise RuntimeError("ACE-Step task succeeded but returned no audio file")
                return items[0]
            if status == _STATUS_FAILED:
                raise RuntimeError(f"ACE-Step task {task_id} failed")
            await asyncio.sleep(self.poll_interval)
        raise TimeoutError(f"ACE-Step task {task_id} did not finish within {self.timeout_sec}s")
