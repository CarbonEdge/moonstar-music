import json
import os
from datetime import datetime, timedelta, timezone

from moonstar_music.library import Library
from moonstar_music.mastering import MasteredTrack
from moonstar_music.models import MusicBrief


def _brief(title="Night Drive"):
    return MusicBrief(title=title, genre="synthwave", mood="calm", bpm=100, key="Am",
                      instrumental=True, duration_sec=60, sections=[], style_prompt="x")


def _mastered(tmp_path):
    mp3, wav = tmp_path / "in.mp3", tmp_path / "in.wav"
    mp3.write_bytes(b"mp3")
    wav.write_bytes(b"wav")
    return MasteredTrack(mp3_path=str(mp3), wav_path=str(wav), duration_sec=60.0)


def test_add_creates_all_files(tmp_path):
    lib = Library(str(tmp_path / "root"))
    m = _mastered(tmp_path)
    tid = lib.add(_brief(), m, "minimax", 0.15)
    d = tmp_path / "root" / "library" / tid
    assert sorted(os.listdir(d)) == ["brief.json", "meta.json", "track.mp3", "track.wav"]
    assert (d / "track.mp3").read_bytes() == b"mp3"
    assert os.path.exists(m.mp3_path)  # copied, not moved
    assert json.loads((d / "brief.json").read_text())["title"] == "Night Drive"
    meta = json.loads((d / "meta.json").read_text())
    assert meta["provider"] == "minimax" and meta["cost_usd"] == 0.15
    assert meta["published_url"] is None
    assert datetime.fromisoformat(meta["created_at"]).utcoffset() == timedelta(0)


def test_same_title_twice_gets_distinct_dirs(tmp_path):
    lib = Library(str(tmp_path / "root"))
    m = _mastered(tmp_path)
    a = lib.add(_brief(), m, "p", 0)
    b = lib.add(_brief(), m, "p", 0)
    assert a != b
    assert len(os.listdir(tmp_path / "root" / "library")) == 2


def test_unsafe_titles_are_slugged(tmp_path):
    lib = Library(str(tmp_path / "root"))
    m = _mastered(tmp_path)
    for t in [r"../../evil/..\x:*?", "", "日本語", "a" * 500]:
        tid = lib.add(_brief(t), m, "p", 0)
        assert len(tid) < 100
        assert not any(c in tid for c in '/\:*?"<>|.')
        assert (tmp_path / "root" / "library" / tid / "meta.json").exists()


def test_recent_titles_newest_first_and_limited(tmp_path):
    lib = Library(str(tmp_path / "root"))
    m = _mastered(tmp_path)
    ids = [lib.add(_brief(f"T{i}"), m, "p", 0) for i in range(3)]
    for i, tid in enumerate(ids):  # distinct created_at
        p = tmp_path / "root" / "library" / tid / "meta.json"
        meta = json.loads(p.read_text())
        meta["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10 - i)).isoformat()
        p.write_text(json.dumps(meta))
    assert lib.recent_titles() == ["T2", "T1", "T0"]
    assert lib.recent_titles(2) == ["T2", "T1"]


def test_count_today_counts_only_today(tmp_path):
    lib = Library(str(tmp_path / "root"))
    m = _mastered(tmp_path)
    old = lib.add(_brief("Old"), m, "p", 0)
    lib.add(_brief("New"), m, "p", 0)
    p = tmp_path / "root" / "library" / old / "meta.json"
    meta = json.loads(p.read_text())
    meta["created_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    p.write_text(json.dumps(meta))
    assert lib.count_today() == 1


def test_set_published_url_updates_meta(tmp_path):
    lib = Library(str(tmp_path / "root"))
    tid = lib.add(_brief(), _mastered(tmp_path), "p", 0)
    lib.set_published_url(tid, "https://example.com/x")
    meta = json.loads((tmp_path / "root" / "library" / tid / "meta.json").read_text())
    assert meta["published_url"] == "https://example.com/x"


def test_empty_library_ok(tmp_path):
    lib = Library(str(tmp_path / "nope"))
    assert lib.recent_titles() == []
    assert lib.count_today() == 0
