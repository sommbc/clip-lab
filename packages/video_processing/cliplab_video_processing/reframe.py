from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import ensure_output_file, require_ffmpeg, run_command
from .visual_layout import FaceBox, LayoutAnalysis, LayoutMode, VisualSample, analyze_visual_layout


ReframeMode = str


SAFE_FULL_FRAME_LAYOUTS: set[LayoutMode] = {
    "two_person_split_screen",
    "multi_speaker_wide",
    "screen_share_or_slides",
    "unknown",
}


@dataclass(frozen=True)
class ReframeResult:
    output_path: Path
    layout_mode: LayoutMode
    reframe_mode: ReframeMode
    layout_confidence: float
    face_boxes: list[FaceBox]
    visual_samples: list[VisualSample]
    visual_debug_path: Path
    reason: str


def reframe_to_vertical(
    input_path: Path,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    reframe_mode: ReframeMode = "center_crop",
) -> Path:
    """Create a vertical H.264/AAC MP4 using the requested reframing strategy."""
    binary = require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtergraph = _filtergraph(width, height, reframe_mode)
    filter_args = (
        ["-filter_complex", filtergraph, "-map", "[v]", "-map", "0:a:0?"]
        if _is_complex_filter(reframe_mode)
        else ["-map", "0:v:0", "-map", "0:a:0?", "-vf", filtergraph]
    )
    run_command(
        [
            binary,
            "-y",
            "-i",
            str(input_path),
            *filter_args,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        "Vertical reframe",
    )
    ensure_output_file(output_path, "Vertical reframe")
    return output_path


def analyze_and_reframe_to_vertical(
    input_path: Path,
    output_path: Path,
    debug_dir: Path,
    *,
    clip_id: str,
    clip_start: float | None = None,
    clip_end: float | None = None,
    width: int = 1080,
    height: int = 1920,
) -> ReframeResult:
    analysis = analyze_visual_layout(
        input_path,
        debug_dir,
        clip_start=clip_start,
        clip_end=clip_end,
    )
    reframe_mode = choose_reframe_mode(analysis.layout_mode)
    reframe_to_vertical(
        input_path,
        output_path,
        width=width,
        height=height,
        reframe_mode=reframe_mode,
    )
    visual_debug_path = _write_visual_debug(
        debug_dir,
        clip_id=clip_id,
        output_path=output_path,
        analysis=analysis,
        reframe_mode=reframe_mode,
    )
    return ReframeResult(
        output_path=output_path,
        layout_mode=analysis.layout_mode,
        reframe_mode=reframe_mode,
        layout_confidence=analysis.layout_confidence,
        face_boxes=analysis.face_boxes,
        visual_samples=analysis.visual_samples,
        visual_debug_path=visual_debug_path,
        reason=analysis.reason,
    )


def choose_reframe_mode(layout_mode: LayoutMode) -> ReframeMode:
    if layout_mode in SAFE_FULL_FRAME_LAYOUTS:
        return "blurred_background_full_frame"
    return "center_crop"


def _filtergraph(width: int, height: int, reframe_mode: ReframeMode) -> str:
    if reframe_mode == "center_crop":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,format=yuv420p"
        )
    if reframe_mode == "blurred_background_full_frame":
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase:"
            f"force_divisible_by=2,crop={width}:{height},gblur=sigma=24,"
            "eq=brightness=-0.05:saturation=0.9[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]"
        )
    raise ValueError(f"Unsupported reframe mode: {reframe_mode}")


def _is_complex_filter(reframe_mode: ReframeMode) -> bool:
    return reframe_mode == "blurred_background_full_frame"


def _write_visual_debug(
    debug_dir: Path,
    *,
    clip_id: str,
    output_path: Path,
    analysis: LayoutAnalysis,
    reframe_mode: ReframeMode,
) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_json_path = debug_dir / "layout.json"
    payload = analysis.to_debug_dict(relative_to=debug_dir)
    payload.update(
        {
            "clip_id": clip_id,
            "layout_mode": analysis.layout_mode,
            "reframe_mode": reframe_mode,
            "chosen_reframe_mode": reframe_mode,
            "output_path": output_path.name,
        }
    )
    debug_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return debug_json_path
