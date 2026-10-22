"""ffmpeg mastering (loudnorm, trim, fade) and a duration/silence quality gate."""
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

FADE_SEC = 2
TARGET_LUFS = -14
SILENCE_DB = "-50dB"
MIN_DURATION_RATIO = 0.5
MAX_SILENCE_RATIO = 0.20


@dataclass
class Probe:
    duration_sec: float
    silence_ratio: float


@dataclass
class MasteredTrack:
    mp3_path: str
    wav_path: str
    duration_sec: float


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")
        raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {stderr}") from e


def build_duration_cmd(path: str) -> list[str]:
    return ["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path]


def build_silencedetect_cmd(path: str) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
            "-af", f"silencedetect=noise={SILENCE_DB}:d=0.5", "-f", "null", "-"]


def parse_duration(stdout: str) -> float:
    return float(stdout.strip())


def parse_silence_ratio(stderr: str, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    total = sum(float(m) for m in re.findall(r"silence_duration:\s*([\d.]+)", stderr))
    # A silence that starts but never ends runs to end of file.
    starts = re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)
    ends = re.findall(r"silence_end:", stderr)
    if len(starts) > len(ends):
        total += max(0.0, duration_sec - float(starts[-1]))
    return min(1.0, total / duration_sec)


def build_normalize_cmd(src: str, dst: str) -> list[str]:
    trim = f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}"
    af = f"{trim},areverse,{trim},areverse,loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11"
    return ["ffmpeg", "-y", "-i", src, "-af", af, dst]


def build_fade_cmd(src: str, dst: str, duration_sec: float) -> list[str]:
    start = max(0.0, duration_sec - FADE_SEC)
    cmd = ["ffmpeg", "-y", "-i", src, "-af", f"afade=t=out:st={start:.3f}:d={FADE_SEC}"]
    if dst.lower().endswith(".mp3"):
        cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]
    return cmd + [dst]


def probe(path: str) -> Probe:
    duration = parse_duration(_run(build_duration_cmd(path)).stdout)
    silence = parse_silence_ratio(_run(build_silencedetect_cmd(path)).stderr, duration)
    return Probe(duration_sec=duration, silence_ratio=silence)


def master(raw_path: str, out_dir: str) -> MasteredTrack:
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(raw_path)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(raw_path))[0]
    mp3_path = os.path.join(out_dir, f"{stem}.mp3")
    wav_path = os.path.join(out_dir, f"{stem}.wav")
    with tempfile.TemporaryDirectory() as tmp:
        mid = os.path.join(tmp, "normalized.wav")
        _run(build_normalize_cmd(raw_path, mid))
        duration = parse_duration(_run(build_duration_cmd(mid)).stdout)
        _run(build_fade_cmd(mid, wav_path, duration))
        _run(build_fade_cmd(mid, mp3_path, duration))
    return MasteredTrack(mp3_path=mp3_path, wav_path=wav_path, duration_sec=duration)


def check_quality(p: Probe, requested_sec: int) -> str | None:
    if p.duration_sec < MIN_DURATION_RATIO * requested_sec:
        return f"too short: {p.duration_sec:.1f}s < 50% of requested {requested_sec}s"
    if p.silence_ratio > MAX_SILENCE_RATIO:
        return f"too much silence: {p.silence_ratio:.0%} > 20%"
    return None
