from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class ClipLabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TranscriptWord(ClipLabModel):
    word: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    speaker: str | None = None

    @model_validator(mode="after")
    def validate_time_order(self) -> "TranscriptWord":
        if self.end <= self.start:
            raise ValueError("word end must be greater than start")
        return self


class TranscriptSegment(ClipLabModel):
    text: str = ""
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    speaker: str | None = None
    words: list[TranscriptWord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segment(self) -> "TranscriptSegment":
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        last_start = -1.0
        for word in self.words:
            if word.start < last_start:
                raise ValueError("segment words must be sorted by start time")
            if word.start < self.start - 0.05 or word.end > self.end + 0.05:
                raise ValueError("word timestamps must stay inside segment bounds")
            last_start = word.start
        return self


class NormalizedTranscript(ClipLabModel):
    text: str
    language: str = Field(min_length=2, max_length=16)
    duration: float = Field(gt=0)
    segments: list[TranscriptSegment] = Field(min_length=1)

    @field_validator("segments")
    @classmethod
    def validate_sorted_segments(
        cls, segments: list[TranscriptSegment]
    ) -> list[TranscriptSegment]:
        last_end = -1.0
        for segment in segments:
            if segment.start < last_end - 0.05:
                raise ValueError("segments must be sorted by start time")
            last_end = segment.end
        return segments

    @model_validator(mode="after")
    def validate_duration_bounds(self) -> "NormalizedTranscript":
        for segment in self.segments:
            if segment.end > self.duration + 0.05:
                raise ValueError("segment end cannot exceed transcript duration")
        return self

    def words(self) -> list[TranscriptWord]:
        return [word for segment in self.segments for word in segment.words]

    def text_between(self, start: float, end: float) -> str:
        chunks = [
            segment.text.strip()
            for segment in self.segments
            if segment.end > start and segment.start < end and segment.text.strip()
        ]
        return " ".join(chunks)


class ClipMechanism(str, Enum):
    conflict = "conflict"
    surprise = "surprise"
    tactical = "tactical"
    story = "story"
    contrarian = "contrarian"
    emotion = "emotion"
    quote = "quote"


class Platform(str, Enum):
    tiktok = "tiktok"
    reels = "reels"
    shorts = "shorts"
    x = "x"
    linkedin = "linkedin"


class ClipRiskFlag(str, Enum):
    sponsor_read = "sponsor_read"
    missing_context = "missing_context"
    weak_hook = "weak_hook"
    rambling = "rambling"
    mid_sentence_boundary = "mid_sentence_boundary"
    sensitive_claim = "sensitive_claim"
    profanity = "profanity"
    possible_copyright = "possible_copyright"


class ClipScorecard(ClipLabModel):
    hook_strength: int = Field(ge=0, le=100)
    self_contained_context: int = Field(ge=0, le=100)
    payoff_strength: int = Field(ge=0, le=100)
    novelty_or_surprise: int = Field(ge=0, le=100)
    conflict_or_tension: int = Field(ge=0, le=100)
    emotional_charge: int = Field(ge=0, le=100)
    tactical_value: int = Field(ge=0, le=100)
    quotability: int = Field(ge=0, le=100)
    retention_likelihood: int = Field(ge=0, le=100)
    platform_suitability: int = Field(ge=0, le=100)
    clean_boundaries: int = Field(ge=0, le=100)

    @property
    def weighted_total(self) -> int:
        weighted = (
            self.hook_strength * 0.18
            + self.self_contained_context * 0.10
            + self.payoff_strength * 0.13
            + self.novelty_or_surprise * 0.10
            + self.conflict_or_tension * 0.09
            + self.emotional_charge * 0.08
            + self.tactical_value * 0.08
            + self.quotability * 0.08
            + self.retention_likelihood * 0.10
            + self.platform_suitability * 0.04
            + self.clean_boundaries * 0.02
        )
        return max(0, min(100, round(weighted)))


class ClipCandidate(ClipLabModel):
    title: str = Field(min_length=1, max_length=120)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    viral_score: int = Field(ge=0, le=100)
    hook_text: str = Field(min_length=1, max_length=120)
    hook_sentence: str = Field(min_length=1, max_length=260)
    viral_reason: str = Field(min_length=1, max_length=800)
    dominant_mechanism: ClipMechanism
    platform_fit: list[Platform] = Field(min_length=1)
    suggested_caption: str = Field(min_length=1, max_length=500)
    risk_flags: list[ClipRiskFlag] = Field(default_factory=list)
    scorecard: ClipScorecard | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "ClipCandidate":
        if self.end <= self.start:
            raise ValueError("clip end must be greater than start")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class ClipCandidateSet(ClipLabModel):
    candidates: list[ClipCandidate] = Field(default_factory=list)


class CriticVerdict(ClipLabModel):
    accepted: bool
    candidate: ClipCandidate
    concerns: list[str] = Field(default_factory=list)
    suggested_start: float | None = None
    suggested_end: float | None = None


class CriticVerdictSet(ClipLabModel):
    verdicts: list[CriticVerdict] = Field(default_factory=list)


class ClipPackaging(ClipLabModel):
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=120)
    hook_text: str = Field(min_length=1, max_length=120)
    hook_sentence: str = Field(min_length=1, max_length=260)
    suggested_caption: str = Field(min_length=1, max_length=500)
    viral_reason: str = Field(min_length=1, max_length=800)
    platform_fit: list[Platform] = Field(min_length=1)
    risk_flags: list[ClipRiskFlag] = Field(default_factory=list)


class ClipPackagingSet(ClipLabModel):
    packages: list[ClipPackaging] = Field(default_factory=list)


class CaptionWordSpec(ClipLabModel):
    text: str = Field(min_length=1)
    startMs: int = Field(ge=0)
    endMs: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_caption_time_order(self) -> "CaptionWordSpec":
        if self.endMs <= self.startMs:
            raise ValueError("caption word endMs must be greater than startMs")
        return self


class SubtitleStyleSpec(ClipLabModel):
    fontFamily: str = Field(min_length=1)
    fontSize: int = Field(gt=0)
    fontColor: str = Field(min_length=1)
    highlightColor: str = Field(min_length=1)
    borderColor: str = Field(min_length=1)
    borderWidth: int = Field(ge=0)
    bgColor: str = Field(min_length=1)
    bgOpacity: float = Field(ge=0, le=1)
    animation: Literal["none", "word-highlight", "pop", "karaoke"]


class SubtitleConfigSpec(ClipLabModel):
    captions: list[CaptionWordSpec] = Field(default_factory=list)
    position: Literal["top", "middle", "bottom"]
    style: SubtitleStyleSpec


class HookConfigSpec(ClipLabModel):
    text: str = Field(min_length=1, max_length=120)
    position: Literal["top", "center", "bottom"]
    size: Literal["S", "M", "L"]
    entranceAnimation: Literal["spring", "fade", "slide-up", "none"]
    displayDurationSec: float = Field(gt=0)


class EffectSegmentSpec(ClipLabModel):
    startSec: float = Field(ge=0)
    endSec: float = Field(gt=0)
    zoom: float = Field(ge=0.5, le=3)
    zoomCenterX: float = Field(ge=0, le=1)
    zoomCenterY: float = Field(ge=0, le=1)
    brightness: float = Field(ge=0, le=3)
    contrast: float = Field(ge=0, le=3)
    saturate: float = Field(ge=0, le=3)

    @model_validator(mode="after")
    def validate_effect_time_order(self) -> "EffectSegmentSpec":
        if self.endSec <= self.startSec:
            raise ValueError("effect segment endSec must be greater than startSec")
        return self


class EffectsConfigSpec(ClipLabModel):
    segments: list[EffectSegmentSpec] = Field(default_factory=list)


LayoutMode = Literal[
    "single_speaker",
    "two_person_split_screen",
    "multi_speaker_wide",
    "screen_share_or_slides",
    "unknown",
]
ReframeMode = Literal["center_crop", "blurred_background_full_frame"]


class FaceBoxSpec(ClipLabModel):
    sample_index: int = Field(ge=1)
    timestamp: float = Field(ge=0)
    source_timestamp: float | None = Field(default=None, ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class VisualSampleSpec(ClipLabModel):
    sample_index: int = Field(ge=1)
    timestamp: float = Field(ge=0)
    source_timestamp: float | None = Field(default=None, ge=0)
    path: Path | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class RenderJobSpec(ClipLabModel):
    video_url: str
    duration_in_frames: int = Field(gt=0)
    fps: float = Field(gt=0)
    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)
    subtitles: SubtitleConfigSpec | None = None
    hook: HookConfigSpec | None = None
    effects: EffectsConfigSpec | None = None
    layout_mode: LayoutMode | None = None
    reframe_mode: ReframeMode | None = None
    face_boxes: list[FaceBoxSpec] = Field(default_factory=list)
    layout_confidence: float | None = Field(default=None, ge=0, le=1)
    visual_samples: list[VisualSampleSpec] = Field(default_factory=list)


class FinalClip(ClipLabModel):
    id: str = Field(min_length=1)
    title: str
    start: float
    end: float
    viral_score: int = Field(ge=0, le=100)
    hook_text: str
    hook_sentence: str
    viral_reason: str
    dominant_mechanism: ClipMechanism
    platform_fit: list[Platform] = Field(min_length=1)
    suggested_caption: str
    risk_flags: list[ClipRiskFlag] = Field(default_factory=list)
    source_clip_path: Path
    vertical_clip_path: Path
    rendered_clip_path: Path | None = None
    render_props_path: Path | None = None
    render_job: RenderJobSpec | None = Field(default=None, exclude=True)
    layout_mode: LayoutMode | None = None
    reframe_mode: ReframeMode | None = None
    face_boxes: list[FaceBoxSpec] = Field(default_factory=list)
    layout_confidence: float | None = Field(default=None, ge=0, le=1)
    visual_samples: list[VisualSampleSpec] = Field(default_factory=list)
    visual_debug_path: Path | None = None

    @model_validator(mode="after")
    def validate_final_clip(self) -> "FinalClip":
        if self.end <= self.start:
            raise ValueError("final clip end must be greater than start")
        return self

    @computed_field
    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


class ClipExportMetadata(ClipLabModel):
    source: str
    source_video_path: Path
    transcript_path: Path
    output_dir: Path
    scenes_path: Path = Path("scenes.json")
    zip_export_path: Path | None = None
    clips: list[FinalClip] = Field(default_factory=list)
    status: Literal["completed", "partial", "failed"] = "completed"
    errors: list[str] = Field(default_factory=list)
