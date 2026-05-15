from __future__ import annotations

from pathlib import Path

from .ffmpeg import ffprobe


def detect_scenes(video_path: Path) -> list[tuple[float, float]]:
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector

        video = open_video(str(video_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        scene_manager.detect_scenes(video=video)
        scenes = scene_manager.get_scene_list()
        return [(start.get_seconds(), end.get_seconds()) for start, end in scenes]
    except Exception:
        duration = media_duration(video_path)
        return [(0.0, duration)]


def media_duration(video_path: Path) -> float:
    data = ffprobe(video_path)
    return float(data.get("format", {}).get("duration", 0.0))

