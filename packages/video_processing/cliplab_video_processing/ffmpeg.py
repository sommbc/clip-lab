from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class MediaToolMissingError(RuntimeError):
    pass


class MediaProcessingError(RuntimeError):
    pass


def ffmpeg_binary() -> str:
    return os.environ.get("CLIP_LAB_FFMPEG_PATH", "ffmpeg")


def ffprobe_binary() -> str:
    return os.environ.get("CLIP_LAB_FFPROBE_PATH", "ffprobe")


def _resolve_binary(binary: str, env_var: str) -> str:
    path = Path(binary).expanduser()
    if path.parent != Path(".") or path.is_absolute():
        if path.exists():
            return str(path)
        raise MediaToolMissingError(
            f"{env_var} points to a missing executable: {path}. "
            f"Install the tool or update {env_var}."
        )
    resolved = shutil.which(binary)
    if resolved:
        return resolved
    raise MediaToolMissingError(
        f"Required media tool `{binary}` was not found on PATH. "
        f"Install FFmpeg or set {env_var} to the executable path."
    )


def require_ffmpeg() -> str:
    return _resolve_binary(ffmpeg_binary(), "CLIP_LAB_FFMPEG_PATH")


def require_ffprobe() -> str:
    return _resolve_binary(ffprobe_binary(), "CLIP_LAB_FFPROBE_PATH")


def ensure_output_file(path: Path, operation: str) -> None:
    if not path.exists():
        raise MediaProcessingError(f"{operation} completed but output file is missing: {path}")
    if path.stat().st_size <= 0:
        raise MediaProcessingError(f"{operation} completed but output file is empty: {path}")


def run_command(args: list[str], operation: str) -> None:
    process = subprocess.run(args, text=True, capture_output=True, check=False)
    if process.returncode != 0:
        raise MediaProcessingError(
            f"{operation} failed with exit code {process.returncode}: {' '.join(args)}\n"
            f"stdout: {process.stdout[-2000:]}\nstderr: {process.stderr[-4000:]}"
        )


def ffprobe(video_path: Path) -> dict:
    binary = require_ffprobe()
    process = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise MediaProcessingError(
            process.stderr.strip() or f"FFprobe failed while reading media metadata: {video_path}"
        )
    return json.loads(process.stdout)


def extract_audio(video_path: Path, output_path: Path) -> Path:
    binary = require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            binary,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        "Audio extraction",
    )
    ensure_output_file(output_path, "Audio extraction")
    return output_path


def cut_clip(input_path: Path, output_path: Path, start: float, end: float) -> Path:
    binary = require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            binary,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        "FFmpeg clip cut",
    )
    ensure_output_file(output_path, "FFmpeg clip cut")
    return output_path
