from __future__ import annotations

import re
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


class IngestError(RuntimeError):
    pass


def ingest_source(source: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return download_video(source, output_dir)

    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise IngestError(f"Input video path does not exist: {source_path}")
    if not source_path.is_file():
        raise IngestError(f"Input video path is not a file: {source_path}")
    destination = output_dir / sanitize_filename(source_path.name)
    if source_path != destination:
        shutil.copy2(source_path, destination)
    if not destination.exists() or destination.stat().st_size <= 0:
        raise IngestError(f"Local video ingest did not produce a usable file: {destination}")
    return destination


def download_video(url: str, output_dir: Path) -> Path:
    try:
        import yt_dlp
    except ImportError as exc:
        raise IngestError(
            "URL ingest requires yt-dlp. Install Clip Lab with `pip install -e .`."
        ) from exc

    output_template = str(output_dir / "%(title).120B.%(ext)s")
    options = {
        "format": "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "restrictfilenames": True,
    }
    cookies = os.environ.get("CLIP_LAB_YOUTUBE_COOKIES")
    if cookies:
        cookie_path = Path(cookies).expanduser()
        if not cookie_path.is_file():
            raise IngestError(f"CLIP_LAB_YOUTUBE_COOKIES does not point to a file: {cookies}")
        options["cookiefile"] = str(cookie_path)
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            filename = downloader.prepare_filename(info)
    except Exception as exc:
        raise IngestError(f"Failed to download video from URL: {url}. {exc}") from exc

    path = Path(filename)
    if path.suffix != ".mp4":
        mp4 = path.with_suffix(".mp4")
        if mp4.exists():
            return mp4
    if not path.exists() or path.stat().st_size <= 0:
        raise IngestError(f"YouTube download finished without a usable output file: {path}")
    return path


def sanitize_filename(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return safe or "input.mp4"
