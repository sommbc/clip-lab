from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cliplab_captions import build_remotion_props
from cliplab_shared import (
    ClipCandidate,
    ClipMechanism,
    NormalizedTranscript,
    Platform,
    TranscriptSegment,
    TranscriptWord,
)
from cliplab_video_processing.reframe import analyze_and_reframe_to_vertical


def test_split_screen_layout_selects_blurred_full_frame_mode(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for reframe tests.")

    source = _write_split_screen_video(tmp_path / "split.mp4")
    debug_dir = tmp_path / "visual_debug" / "clip_01"

    result = analyze_and_reframe_to_vertical(
        source,
        tmp_path / "vertical.mp4",
        debug_dir,
        clip_id="clip_01",
        clip_start=100.0,
        clip_end=103.0,
    )

    assert result.output_path.is_file()
    assert result.layout_mode == "two_person_split_screen"
    assert result.reframe_mode == "blurred_background_full_frame"


def test_unknown_layout_does_not_center_crop_aggressively(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for reframe tests.")

    source = _write_unknown_video(tmp_path / "unknown.mp4")

    result = analyze_and_reframe_to_vertical(
        source,
        tmp_path / "vertical.mp4",
        tmp_path / "visual_debug" / "clip_01",
        clip_id="clip_01",
        clip_start=0.0,
        clip_end=3.0,
    )

    assert result.layout_mode == "unknown"
    assert result.reframe_mode == "blurred_background_full_frame"


def test_render_props_include_layout_reframe_metadata():
    props = build_remotion_props(
        "file:///tmp/clip.mp4",
        _transcript(),
        _candidate(),
        layout_mode="two_person_split_screen",
        reframe_mode="blurred_background_full_frame",
        layout_confidence=0.91,
        face_boxes=[
            {
                "sample_index": 1,
                "timestamp": 1.0,
                "source_timestamp": 101.0,
                "x": 20,
                "y": 30,
                "width": 100,
                "height": 110,
            }
        ],
        visual_samples=[
            {
                "sample_index": 1,
                "timestamp": 1.0,
                "source_timestamp": 101.0,
                "path": Path("visual_debug/clip_01/sample_01_t001.000.jpg"),
                "width": 1920,
                "height": 1080,
            }
        ],
    )

    payload = props.model_dump(mode="json")
    assert payload["layout_mode"] == "two_person_split_screen"
    assert payload["reframe_mode"] == "blurred_background_full_frame"
    assert payload["layout_confidence"] == pytest.approx(0.91)
    assert payload["face_boxes"][0]["x"] == 20
    assert payload["visual_samples"][0]["path"] == "visual_debug/clip_01/sample_01_t001.000.jpg"
    assert payload["effects"]["segments"][0]["zoom"] == 1.0


def test_visual_debug_json_is_written(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for reframe tests.")

    source = _write_split_screen_video(tmp_path / "split.mp4")
    debug_dir = tmp_path / "visual_debug" / "clip_01"

    result = analyze_and_reframe_to_vertical(
        source,
        tmp_path / "vertical.mp4",
        debug_dir,
        clip_id="clip_01",
        clip_start=10.0,
        clip_end=13.0,
    )

    debug = json.loads(result.visual_debug_path.read_text(encoding="utf-8"))
    assert debug["clip_id"] == "clip_01"
    assert debug["layout_mode"] == "two_person_split_screen"
    assert debug["reframe_mode"] == "blurred_background_full_frame"
    assert debug["sampled_frame_timestamps"]
    assert (debug_dir / debug["sampled_frame_timestamps"][0]["path"]).is_file()


def _write_split_screen_video(path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    assert writer.isOpened()
    for index in range(90):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :320] = (86, 128, 190)
        frame[:, 320:] = (58, 62, 82)
        frame[:, 318:322] = (0, 0, 0)
        _draw_face_like_region(cv2, frame, 160, 160, (170, 205, 230))
        _draw_face_like_region(cv2, frame, 480, 160, (120, 160, 210))
        cv2.rectangle(frame, (40, 290), (280, 335), (18, 18, 18), -1)
        cv2.rectangle(frame, (360, 290), (600, 335), (18, 18, 18), -1)
        cv2.putText(frame, f"L{index}", (70, 322), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, f"R{index}", (390, 322), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    assert path.is_file()
    return path


def _write_unknown_video(path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    assert writer.isOpened()
    for _ in range(90):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        for y in range(360):
            frame[y, :] = (60 + y // 8, 70 + y // 10, 90 + y // 12)
        writer.write(frame)
    writer.release()
    assert path.is_file()
    return path


def _draw_face_like_region(cv2, frame, center_x: int, center_y: int, color: tuple[int, int, int]) -> None:
    cv2.circle(frame, (center_x, center_y), 72, color, -1)
    cv2.circle(frame, (center_x - 25, center_y - 16), 8, (20, 20, 20), -1)
    cv2.circle(frame, (center_x + 25, center_y - 16), 8, (20, 20, 20), -1)
    cv2.ellipse(frame, (center_x, center_y + 28), (28, 12), 0, 0, 180, (35, 35, 35), 4)
    cv2.rectangle(frame, (center_x - 78, center_y + 70), (center_x + 78, center_y + 150), color, -1)


def _transcript() -> NormalizedTranscript:
    words = [
        TranscriptWord(word="Both", start=0.0, end=0.3),
        TranscriptWord(word="speakers", start=0.35, end=0.75),
        TranscriptWord(word="stay", start=0.8, end=1.0),
        TranscriptWord(word="visible.", start=1.05, end=1.4),
    ]
    return NormalizedTranscript(
        text="Both speakers stay visible.",
        language="en",
        duration=4.0,
        segments=[
            TranscriptSegment(
                text="Both speakers stay visible.",
                start=0.0,
                end=4.0,
                words=words,
            )
        ],
    )


def _candidate() -> ClipCandidate:
    return ClipCandidate(
        title="Both speakers stay visible",
        start=0.0,
        end=4.0,
        viral_score=80,
        hook_text="BOTH SPEAKERS STAY VISIBLE",
        hook_sentence="Both speakers stay visible.",
        viral_reason="The clip has a clear visual layout requirement.",
        dominant_mechanism=ClipMechanism.tactical,
        platform_fit=[Platform.tiktok, Platform.reels, Platform.shorts],
        suggested_caption="Both speakers stay visible.",
        risk_flags=[],
    )
