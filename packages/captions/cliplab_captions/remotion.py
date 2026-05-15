from __future__ import annotations

from pathlib import Path

from cliplab_shared import (
    ClipCandidate,
    FaceBoxSpec,
    LayoutMode,
    NormalizedTranscript,
    ReframeMode,
    RenderJobSpec,
    VisualSampleSpec,
)


def build_remotion_props(
    video_url: str,
    transcript: NormalizedTranscript,
    clip: ClipCandidate,
    fps: float = 30,
    width: int = 1080,
    height: int = 1920,
    layout_mode: LayoutMode | None = None,
    reframe_mode: ReframeMode | None = None,
    face_boxes: list[FaceBoxSpec | dict] | None = None,
    layout_confidence: float | None = None,
    visual_samples: list[VisualSampleSpec | dict] | None = None,
) -> RenderJobSpec:
    captions = []
    for word in transcript.words():
        if word.end < clip.start or word.start > clip.end:
            continue
        captions.append(
            {
                "text": word.word,
                "startMs": max(0, round((word.start - clip.start) * 1000)),
                "endMs": max(1, round((word.end - clip.start) * 1000)),
            }
        )

    duration_sec = max(0.1, clip.end - clip.start)
    safe_full_frame = reframe_mode == "blurred_background_full_frame"
    return RenderJobSpec(
        video_url=video_url,
        duration_in_frames=round(duration_sec * fps),
        fps=fps,
        width=width,
        height=height,
        subtitles={
            "captions": captions,
            "position": "bottom",
            "style": {
                "fontFamily": "Arial",
                "fontSize": 58,
                "fontColor": "#FFFFFF",
                "highlightColor": "#FFDD00",
                "borderColor": "#000000",
                "borderWidth": 4,
                "bgColor": "#000000",
                "bgOpacity": 0,
                "animation": "pop",
            },
        },
        hook={
            "text": clip.hook_text,
            "position": "top",
            "size": "M",
            "entranceAnimation": "spring",
            "displayDurationSec": min(5, duration_sec),
        },
        effects={
            "segments": [
                {
                    "startSec": 0,
                    "endSec": min(3, duration_sec),
                    "zoom": 1.0 if safe_full_frame else 1.08,
                    "zoomCenterX": 0.5,
                    "zoomCenterY": 0.5 if safe_full_frame else 0.38,
                    "brightness": 1,
                    "contrast": 1 if safe_full_frame else 1.08,
                    "saturate": 1 if safe_full_frame else 1.08,
                },
                {
                    "startSec": min(3, duration_sec),
                    "endSec": duration_sec,
                    "zoom": 1.0,
                    "zoomCenterX": 0.5,
                    "zoomCenterY": 0.5 if safe_full_frame else 0.45,
                    "brightness": 1,
                    "contrast": 1,
                    "saturate": 1,
                },
            ]
        },
        layout_mode=layout_mode,
        reframe_mode=reframe_mode,
        face_boxes=face_boxes or [],
        layout_confidence=layout_confidence,
        visual_samples=visual_samples or [],
    )


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
