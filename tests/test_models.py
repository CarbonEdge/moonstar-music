from moonstar_music.models import MusicBrief, Section


def make(**kw):
    base = dict(
        title="T", genre="lofi", mood="calm", bpm=80, key="C minor",
        instrumental=False, lyrics="la la", duration_sec=120,
        sections=[Section(name="intro", seconds=10, prompt="soft")],
        style_prompt="lofi calm",
    )
    base.update(kw)
    return MusicBrief(**base)


def test_instrumental_drops_lyrics():
    assert make(instrumental=True, lyrics="la la").lyrics is None


def test_song_keeps_lyrics():
    assert make(instrumental=False, lyrics="la la").lyrics == "la la"


def test_brief_roundtrips_json():
    b = make()
    assert MusicBrief.model_validate_json(b.model_dump_json()) == b
