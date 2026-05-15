from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cliplab_pipeline import ClipLabPipeline, PipelineConfig
from cliplab_transcription import TranscriptJsonError, load_normalized_transcript_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TRANSCRIPT = ROOT / "fixtures" / "sample.transcript.json"
FIXTURE_VIDEO = ROOT / "fixtures" / "sample.mp4"


def test_fixture_pipeline_runs_through_media_steps_without_render(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are required for the media smoke test.")

    source_video = FIXTURE_VIDEO
    if not source_video.exists():
        source_video = tmp_path / "sample.mp4"
        _generate_sample_video(source_video)

    metadata = ClipLabPipeline(
        config=PipelineConfig(output_root=tmp_path / "output", max_clips=2, render=False)
    ).run(
        source=str(source_video),
        job_id="smoke_fixture",
        transcript=load_normalized_transcript_json(FIXTURE_TRANSCRIPT),
    )

    job_dir = tmp_path / "output" / "smoke_fixture"
    expected_dirs = [
        "source",
        "audio",
        "clips/raw",
        "clips/vertical",
        "clips/rendered",
        "render_props",
        "visual_debug",
    ]
    for relative_dir in expected_dirs:
        assert (job_dir / relative_dir).is_dir()

    assert metadata.status == "completed"
    assert metadata.clips
    assert (job_dir / "source" / "sample.mp4").is_file()
    assert (job_dir / "audio" / "source.wav").is_file()
    assert (job_dir / "transcript.json").is_file()
    assert (job_dir / "scenes.json").is_file()
    assert (job_dir / "metadata.json").is_file()
    assert (job_dir / "export.zip").is_file()

    expected_tree = [
        "source/sample.mp4",
        "audio/source.wav",
        "clips/raw/clip_01.mp4",
        "clips/vertical/clip_01.mp4",
        "render_props/clip_01.json",
        "visual_debug/clip_01/layout.json",
        "metadata.json",
        "transcript.json",
        "scenes.json",
        "export.zip",
    ]
    for relative_path in expected_tree:
        assert (job_dir / relative_path).is_file()

    first_clip = metadata.clips[0]
    assert first_clip.id == "clip_01"
    assert first_clip.duration == pytest.approx(first_clip.end - first_clip.start)
    assert first_clip.source_clip_path == Path("clips/raw/clip_01.mp4")
    assert first_clip.vertical_clip_path == Path("clips/vertical/clip_01.mp4")
    assert first_clip.render_props_path == Path("render_props/clip_01.json")
    assert first_clip.rendered_clip_path is None
    assert first_clip.layout_mode in {
        "single_speaker",
        "two_person_split_screen",
        "multi_speaker_wide",
        "screen_share_or_slides",
        "unknown",
    }
    assert first_clip.reframe_mode in {"center_crop", "blurred_background_full_frame"}

    assert (job_dir / first_clip.source_clip_path).is_file()
    assert (job_dir / first_clip.vertical_clip_path).is_file()
    assert (job_dir / first_clip.render_props_path).is_file()
    assert (job_dir / first_clip.visual_debug_path / "layout.json").is_file()
    assert not any((job_dir / "clips/rendered").iterdir())

    metadata_json = json.loads((job_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata_json["scenes_path"] == "scenes.json"
    assert metadata_json["zip_export_path"] == "export.zip"
    clip_json = metadata_json["clips"][0]
    for key in [
        "id",
        "title",
        "start",
        "end",
        "duration",
        "viral_score",
        "hook_text",
        "hook_sentence",
        "viral_reason",
        "dominant_mechanism",
        "platform_fit",
        "suggested_caption",
        "risk_flags",
        "source_clip_path",
        "vertical_clip_path",
        "render_props_path",
        "layout_mode",
        "reframe_mode",
        "layout_confidence",
        "visual_samples",
        "visual_debug_path",
    ]:
        assert key in clip_json
    assert "rendered_clip_path" not in clip_json


def test_transcript_json_loader_reports_invalid_fixture(tmp_path):
    invalid = tmp_path / "bad.transcript.json"
    invalid.write_text('{"segments": []}', encoding="utf-8")

    with pytest.raises(TranscriptJsonError, match="normalized transcript validation"):
        load_normalized_transcript_json(invalid)


def _generate_sample_video(output_path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1280x720:rate=30:duration=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000:duration=8",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert output_path.is_file()
