"""Plain-file track library: <root>/library/<id>/{track.mp3,track.wav,brief.json,meta.json}."""
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

from moonstar_music.mastering import MasteredTrack
from moonstar_music.models import MusicBrief

MAX_SLUG_LEN = 50

logger = logging.getLogger(__name__)


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

    def _load(self, track_id: str) -> tuple[datetime, str] | None:
        """(created_at, title) for a track, or None (with a warning) if its files are unreadable."""
        try:
            created = datetime.fromisoformat(self._read_json(track_id, "meta.json")["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            title = self._read_json(track_id, "brief.json")["title"]
            if not isinstance(title, str):
                raise TypeError("title is not a string")
            return created, title
        except Exception as e:
            logger.warning("Skipping unreadable library entry %s: %s", track_id, e)
            return None

    def _entries(self) -> list[tuple[datetime, str]]:
        return [e for e in (self._load(t) for t in self._track_ids()) if e is not None]

    def recent_titles(self, n: int = 20) -> list[str]:
        rows = sorted(self._entries(), reverse=True)
        return [title for _, title in rows[:n]]

    def count_today(self) -> int:
        today = datetime.now(timezone.utc).date()
        return sum(1 for created, _ in self._entries() if created.astimezone(timezone.utc).date() == today)

    def set_published_url(self, track_id: str, url: str) -> None:
        if (not track_id or os.path.basename(track_id) != track_id or track_id in (".", "..")
                or not os.path.isdir(os.path.join(self.dir, track_id))):
            raise ValueError(f"Unknown track id: {track_id!r}")
        meta = self._read_json(track_id, "meta.json")
        meta["published_url"] = url
        d = os.path.join(self.dir, track_id)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            os.replace(tmp, os.path.join(d, "meta.json"))
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
