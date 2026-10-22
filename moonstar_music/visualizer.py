"""Render an audio-reactive waveform video (mp4) from a track, for publishing."""
import os
import subprocess

WIDTH = 1280
HEIGHT = 720
FPS = 25
BG_COLOUR = "0x101820"
WAVE_HEIGHT = 240


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")
        raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {stderr}") from e


def build_visualizer_cmd(mp3_path: str, out_path: str, cover_image: str | None = None) -> list[str]:
    """Input 0 is the background (cover image or solid colour), input 1 the audio."""
    if cover_image is not None:
        background = ["-loop", "1", "-framerate", str(FPS), "-i", cover_image]
    else:
        background = ["-f", "lavfi", "-i", f"color=c={BG_COLOUR}:s={WIDTH}x{HEIGHT}:r={FPS}"]
    graph = (
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1[bg];"
        f"[1:a]showwaves=s={WIDTH}x{WAVE_HEIGHT}:mode=cline:colors=white:r={FPS}[wave];"
        f"[bg][wave]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
    )
    return ["ffmpeg", "-y", *background, "-i", mp3_path,
            "-filter_complex", graph, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", out_path]


def render_visualizer(mp3_path: str, out_path: str, cover_image: str | None = None) -> str:
    if not os.path.isfile(mp3_path):
        raise FileNotFoundError(mp3_path)
    if cover_image is not None and not os.path.isfile(cover_image):
        raise FileNotFoundError(cover_image)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _run(build_visualizer_cmd(mp3_path, out_path, cover_image))
    return out_path
