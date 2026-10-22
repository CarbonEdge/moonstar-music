import pathlib
import uuid

import httpx

from moonstar_music.models import MusicBrief
from moonstar_music.providers.base import TrackResult

# UNVERIFIED: endpoint and field names (POST /v1/music, `prompt`, `music_length_ms`)
# come from documented patterns, not live responses. Check the current ElevenLabs
# Music docs before the first live run.
_URL = "https://api.elevenlabs.io/v1/music"


def _build_prompt(brief: MusicBrief) -> str:
    lines = [
        brief.style_prompt,
        f"Genre: {brief.genre}. Mood: {brief.mood}. {brief.bpm} BPM, key of {brief.key}.",
    ]
    lines += [f"{s.name} ({s.seconds}s): {s.prompt}" for s in brief.sections]
    if brief.instrumental:
        lines.append("Instrumental, no vocals.")
    elif brief.lyrics:
        lines.append(f"Lyrics:\n{brief.lyrics}")
    return "\n".join(lines)


class ElevenLabsMusicProvider:
    """MusicGenProvider backed by ElevenLabs Music (synchronous, single call)."""

    def __init__(self, api_key: str, output_dir: str):
        self.api_key = api_key
        self.raw_dir = pathlib.Path(output_dir) / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    async def generate_track(self, brief: MusicBrief) -> TrackResult:
        resp = await self.client.post(
            _URL,
            json={
                "prompt": _build_prompt(brief),
                "music_length_ms": brief.duration_sec * 1000,
            },
            headers={"xi-api-key": self.api_key},
            timeout=300.0,
        )
        resp.raise_for_status()
        if not resp.content:
            raise RuntimeError("ElevenLabs Music returned an empty audio body")
        path = self.raw_dir / f"{uuid.uuid4().hex}.mp3"
        path.write_bytes(resp.content)
        return TrackResult(path=str(path), format="mp3", duration_sec=float(brief.duration_sec))
