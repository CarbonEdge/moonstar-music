import pathlib
import uuid

import httpx

from moonstar_music.models import MusicBrief
from moonstar_music.providers.base import TrackResult

# UNVERIFIED: endpoint and field names (POST /v1/music_generation, `model`, `prompt`,
# `lyrics`, response `data.audio` as hex) come from documented patterns, not live
# responses. Check the current MiniMax Music docs before the first live run.
_URL = "https://api.minimax.io/v1/music_generation"
_MODEL = "music-2.0"


def _build_prompt(brief: MusicBrief) -> str:
    lines = [
        brief.style_prompt,
        f"Genre: {brief.genre}. Mood: {brief.mood}. {brief.bpm} BPM, key of {brief.key}.",
    ]
    lines += [f"{s.name} ({s.seconds}s): {s.prompt}" for s in brief.sections]
    if brief.instrumental:
        lines.append("Instrumental, no vocals.")
    return "\n".join(lines)


class MiniMaxMusicProvider:
    """MusicGenProvider backed by MiniMax Music (synchronous, hex-encoded audio)."""

    def __init__(self, api_key: str, output_dir: str):
        self.api_key = api_key
        self.raw_dir = pathlib.Path(output_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    async def generate_track(self, brief: MusicBrief) -> TrackResult:
        body: dict = {"model": _MODEL, "prompt": _build_prompt(brief)}
        if not brief.instrumental and brief.lyrics:
            body["lyrics"] = brief.lyrics
        resp = await self.client.post(
            _URL,
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=300.0,
        )
        resp.raise_for_status()
        audio_hex = (resp.json().get("data") or {}).get("audio")
        if not audio_hex:
            raise RuntimeError("MiniMax Music returned no audio")
        audio = bytes.fromhex(audio_hex)
        if not audio:
            raise RuntimeError("MiniMax Music returned empty audio")
        path = self.raw_dir / f"{uuid.uuid4().hex}.mp3"
        path.write_bytes(audio)
        return TrackResult(path=str(path), format="mp3", duration_sec=float(brief.duration_sec))
