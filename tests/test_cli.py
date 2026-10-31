import argparse

from moonstar_music import cli


def test_mode_without_theme_overrides_rotation():
    tp = cli.build_theme_provider(argparse.Namespace(theme=None, mode="song"))
    assert [tp()[1] for _ in range(4)] == ["song"] * 4


def test_no_flags_alternates_modes():
    tp = cli.build_theme_provider(argparse.Namespace(theme=None, mode=None))
    assert [tp()[1] for _ in range(3)] == ["instrumental", "song", "instrumental"]


def test_theme_defaults_to_instrumental():
    tp = cli.build_theme_provider(argparse.Namespace(theme="x", mode=None))
    assert tp() == ("x", "instrumental")


def test_source_must_exist(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["--once", "--source", str(tmp_path / "nope.wav")])


def test_cover_strength_range():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["--once", "--cover-strength", "1.5"])
