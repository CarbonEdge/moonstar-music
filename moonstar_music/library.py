"""Plain-file track library: <root>/library/<id>/{track.mp3,track.wav,brief.json,meta.json}."""
import json
import os
import re
import shutil
from datetime import datetime, timezone

from moonstar_music.mastering import MasteredTrack
from moonstar_music.models import MusicBrief

MAX_SLUG_LEN = 50


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:MAX_SLUG_LEN].strip("-")
    return slug or "untitled"


class Library:
    def __init__(self, root: str):
        self.dir = os.path.join(root, "library")

    def _read_json(self, track_id: str, name: str) -> dict:
        with open(os.path.join(self.dir, track_id, name), encoding="utf-8") as f:
            return json.load(f)

    def _track_ids(self) -> list[str]:
        if not os.path.isdir(self.dir):
            return []
        return [d for d in os.listdir(self.dir)
                if os.path.isfile(os.path.join(self.dir, d, "meta.json"))]

    def add(self, brief: MusicBrief, mastered: MasteredTrack, provider: str, cost_usd: float) -> str:
        now = datetime.now(timezone.utc)
        base = f"{now:%Y%m%d-%H%M%S}-{_slugify(brief.title)}"
        os.makedirs(self.dir, exist_ok=True)
        track_id, n = base, 1
        while True:
            try:
                os.mkdir(os.path.join(self.dir, track_id))
                break
            except FileExistsError:
                n += 1
                track_id = f"{base}-{n}"
        d = os.path.join(self.dir, track_id)
        shutil.copyfile(mastered.mp3_path, os.path.join(d, "track.mp3"))
        shutil.copyfile(mastered.wav_path, os.path.join(d, "track.wav"))
        with open(os.path.join(d, "brief.json"), "w", encoding="utf-8") as f:
            f.write(brief.model_dump_json(indent=2))
        meta = {"provider": provider, "cost_usd": cost_usd,
                "created_at": now.isoformat(), "published_url": None}
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return track_id

    def recent_titles(self, n: int = 20) -> list[str]:
        rows = [(self._read_json(t, "meta.json")["created_at"], t) for t in self._track_ids()]
        rows.sort(reverse=True)
        return [self._read_json(t, "brief.json")["title"] for _, t in rows[:n]]

    def count_today(self) -> int:
        today = datetime.now(timezone.utc).date()
        return sum(
            1 for t in self._track_ids()
            if datetime.fromisoformat(self._read_json(t, "meta.json")["created_at"])
            .astimezone(timezone.utc).date() == today
        )

    def set_published_url(self, track_id: str, url: str) -> None:
        meta = self._read_json(track_id, "meta.json")
        meta["published_url"] = url
        with open(os.path.join(self.dir, track_id, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
