import shutil
import subprocess
from unittest.mock import patch

import pytest

from moonstar_music import visualizer


def test_cmd_without_cover_uses_solid_colour_source():
    cmd = visualizer.build_visualizer_cmd("in.mp3", "out.mp4", None)
    assert cmd[0] == "ffmpeg" and cmd[-1] == "out.mp4"
    joined = " ".join(cmd)
    assert "color=c=" in joined and "lavfi" in cmd
    assert "showwaves" in cmd[cmd.index("-filter_complex") + 1]
    assert "-shortest" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd.index("in.mp3") < cmd.index("-filter_complex") < cmd.index("-c:v")


def test_cmd_with_cover_loops_image():
    cmd = visualizer.build_visualizer_cmd("in.mp3", "out.mp4", "cover.png")
    assert "cover.png" in cmd and "-loop" in cmd
    assert cmd.index("-loop") < cmd.index("cover.png") < cmd.index("-filter_complex")
    assert "color=c=" not in " ".join(cmd)
    assert "showwaves" in cmd[cmd.index("-filter_complex") + 1]
    assert "-shortest" in cmd and cmd[-1] == "out.mp4"


def test_render_runs_cmd_and_returns_out_path(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    out = str(tmp_path / "o.mp4")
    with patch.object(visualizer.subprocess, "run") as run:
        assert visualizer.render_visualizer(str(src), out) == out
    assert run.call_args.args[0][-1] == out


def test_render_error_raises(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    err = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom")
    with patch.object(visualizer.subprocess, "run", side_effect=err):
        with pytest.raises(RuntimeError, match="boom"):
            visualizer.render_visualizer(str(src), str(tmp_path / "o.mp4"))


def test_render_missing_input_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        visualizer.render_visualizer(str(tmp_path / "nope.mp3"), str(tmp_path / "o.mp4"))


def test_render_visualizer_makes_mp4(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    mp3 = tmp_path / "sine.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:a", "libmp3lame", str(mp3)], check=True, capture_output=True)
    out = visualizer.render_visualizer(str(mp3), str(tmp_path / "v.mp4"))
    assert (tmp_path / "v.mp4").stat().st_size > 0 and out.endswith("v.mp4")
