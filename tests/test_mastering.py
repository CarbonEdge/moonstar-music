import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from moonstar_music import mastering
from moonstar_music.mastering import MasteredTrack, Probe, check_quality, master, probe

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed on PATH"
)


def test_check_quality_rejects_short():
    assert isinstance(check_quality(Probe(50, 0.0), 120), str)


def test_check_quality_rejects_silent():
    assert isinstance(check_quality(Probe(120, 0.25), 120), str)


def test_check_quality_accepts():
    assert check_quality(Probe(118, 0.02), 120) is None


def test_master_raises_on_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        master(str(tmp_path / "nope.wav"), str(tmp_path / "out"))


@needs_ffmpeg
def test_master_produces_files(tmp_path):
    src = tmp_path / "sine.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(src)],
        check=True, capture_output=True,
    )
    res = master(str(src), str(tmp_path / "out"))
    assert isinstance(res, MasteredTrack)
    assert (tmp_path / "out").exists()
    assert Path(res.mp3_path).exists() and Path(res.wav_path).exists()
    assert abs(res.duration_sec - 6) <= 1



# --- pure command builders / parsers ---

def test_normalize_cmd_has_loudnorm_and_silenceremove():
    cmd = mastering.build_normalize_cmd("in.wav", "mid.wav")
    af = cmd[cmd.index("-af") + 1]
    assert "loudnorm=I=-14" in af
    assert "silenceremove" in af and "areverse" in af
    assert cmd[-1] == "mid.wav"
    assert cmd[cmd.index("-ar") + 1] == "44100"


def test_fade_cmd_wav_has_2s_afade_out_at_end():
    cmd = mastering.build_fade_cmd("mid.wav", "o.wav", 10.0)
    af = cmd[cmd.index("-af") + 1]
    assert af == "afade=t=out:st=8.000:d=2"
    assert cmd[-1] == "o.wav"
    assert "libmp3lame" not in cmd
    assert cmd[cmd.index("-ar") + 1] == "44100"


def test_fade_cmd_mp3_320k():
    cmd = mastering.build_fade_cmd("mid.wav", "o.mp3", 10.0)
    assert "libmp3lame" in cmd
    assert cmd[cmd.index("-b:a") + 1] == "320k"
    assert cmd[cmd.index("-ar") + 1] == "44100"


def test_fade_start_never_negative():
    cmd = mastering.build_fade_cmd("m.wav", "o.wav", 1.0)
    assert "st=0.000" in cmd[cmd.index("-af") + 1]


def test_parse_duration():
    assert mastering.parse_duration("123.456000\n") == pytest.approx(123.456)


def test_parse_silence_ratio():
    stderr = (
        "[silencedetect @ 0x1] silence_start: 0\n"
        "[silencedetect @ 0x1] silence_end: 5 | silence_duration: 5\n"
        "[silencedetect @ 0x1] silence_start: 90\n"
        "[silencedetect @ 0x1] silence_end: 95.5 | silence_duration: 5.5\n"
    )
    assert mastering.parse_silence_ratio(stderr, 100.0) == pytest.approx(0.105)


def test_parse_silence_ratio_none():
    assert mastering.parse_silence_ratio("nothing", 100.0) == 0.0


def test_parse_silence_ratio_trailing_open_silence():
    stderr = "[silencedetect @ 0x1] silence_start: 80\n"
    assert mastering.parse_silence_ratio(stderr, 100.0) == pytest.approx(0.2)


class _Done:
    def __init__(self, stdout="", stderr=""):
        self.stdout, self.stderr = stdout, stderr


def test_probe_runs_ffprobe_and_silencedetect(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        assert kw.get("check") is True
        if cmd[0] == "ffprobe":
            return _Done(stdout="100.0\n")
        return _Done(stderr="silence_start: 0\nsilence_end: 10 | silence_duration: 10\n")

    with patch.object(mastering.subprocess, "run", fake_run):
        p = probe(str(f))
    assert p == Probe(100.0, pytest.approx(0.1))
    assert calls[0][0] == "ffprobe" and calls[1][0] == "ffmpeg"
    assert any("silencedetect" in a for a in calls[1])


def test_subprocess_error_propagates_stderr(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, stderr="Invalid data found")

    with patch.object(mastering.subprocess, "run", boom):
        with pytest.raises(RuntimeError, match="Invalid data found"):
            probe(str(f))


def test_master_orchestrates_commands(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return _Done(stdout="9.5\n")
        return _Done()

    with patch.object(mastering.subprocess, "run", fake_run):
        res = master(str(f), str(tmp_path / "out"))
    assert res.duration_sec == 9.5
    assert res.mp3_path.endswith(".mp3") and res.wav_path.endswith(".wav")
    joined = [" ".join(c) for c in calls]
    assert any("loudnorm=I=-14" in j for j in joined)
    assert any("afade=t=out:st=7.500:d=2" in j for j in joined)
    assert any("320k" in j for j in joined)
