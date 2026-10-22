from dataclasses import dataclass
from typing import Protocol

from moonstar_music.models import MusicBrief


@dataclass
class TrackResult:
    path: str
    format: str
    duration_sec: float


class MusicGenProvider(Protocol):
    async def generate_track(self, brief: MusicBrief) -> TrackResult:
        ...


class PublishProvider(Protocol):
    async def upload(self, video_path: str, title: str, description: str) -> str:
        ...
