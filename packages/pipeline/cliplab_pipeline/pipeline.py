from __future__ import annotations

import json
import os
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from cliplab_captions import build_remotion_props
from cliplab_clip_intelligence import (
    ClipCritic,
    ClipGenerator,
    ClipPackager,
    create_clip_model_provider,
    refine_candidate_boundaries,
)
from cliplab_shared import ClipExportMetadata, FinalClip, NormalizedTranscript
from cliplab_transcription import (
    TranscriptionProvider,
    TranscriptionRequest,
    create_transcription_provider,
)
from cliplab_video_processing import (
    analyze_and_reframe_to_vertical,
    detect_scenes,
    extract_audio,
    ingest_source,
    require_ffmpeg,
    require_ffprobe,
)
from cliplab_video_processing.ffmpeg import cut_clip

from .renderer_client import RemotionRendererClient


class PipelineError(RuntimeError):
    pass


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise PipelineError(f"{name} must be an integer, got: {raw}") from exc


@dataclass(frozen=True)
class PipelineConfig:
    output_root: Path = field(default_factory=lambda: _env_path("CLIP_LAB_OUTPUT_ROOT", "output"))
    max_clips: int = field(default_factory=lambda: _env_int("CLIP_LAB_MAX_CLIPS", 5))
    render: bool = True
    renderer_url: str = field(
        default_factory=lambda: os.environ.get("CLIP_LAB_RENDERER_URL", "http://localhost:3100")
    )
    use_model_provider: bool = False
    model_provider_name: str | None = None
    write_zip: bool = True


class ClipLabPipeline:
    def __init__(
        self,
        transcription_provider: TranscriptionProvider | None = None,
        generator: ClipGenerator | None = None,
        critic: ClipCritic | None = None,
        packager: ClipPackager | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        model_provider = (
            create_clip_model_provider(self.config.model_provider_name)
            if self.config.use_model_provider
            else None
        )
        self.transcription_provider = transcription_provider
        self.generator = generator or ClipGenerator(model_provider=model_provider)
        self.critic = critic or ClipCritic(model_provider=model_provider)
        self.packager = packager or ClipPackager(model_provider=model_provider)

    def run(
        self,
        source: str,
        job_id: str | None = None,
        transcript: NormalizedTranscript | None = None,
    ) -> ClipExportMetadata:
        job_id = job_id or str(uuid.uuid4())
        output_dir = self.config.output_root / job_id
        source_dir = output_dir / "source"
        audio_dir = output_dir / "audio"
        raw_clips_dir = output_dir / "clips" / "raw"
        vertical_clips_dir = output_dir / "clips" / "vertical"
        rendered_clips_dir = output_dir / "clips" / "rendered"
        render_props_dir = output_dir / "render_props"
        visual_debug_dir = output_dir / "visual_debug"
        for directory in (
            source_dir,
            audio_dir,
            raw_clips_dir,
            vertical_clips_dir,
            rendered_clips_dir,
            render_props_dir,
            visual_debug_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        require_ffmpeg()
        require_ffprobe()

        source_video = ingest_source(source, source_dir)
        audio_path = extract_audio(source_video, audio_dir / "source.wav")

        if transcript is None:
            transcription_provider = self.transcription_provider or create_transcription_provider()
            transcript = transcription_provider.transcribe(TranscriptionRequest(audio_path=audio_path))
        transcript_path = output_dir / "transcript.json"
        transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")

        scenes = detect_scenes(source_video)
        scenes_path = output_dir / "scenes.json"
        scenes_path.write_text(json.dumps(scenes, indent=2), encoding="utf-8")

        candidates = self.generator.generate(transcript).candidates
        refined = [refine_candidate_boundaries(transcript, candidate) for candidate in candidates]
        accepted = self.critic.review(transcript, refined)[: self.config.max_clips]
        accepted = self.packager.package(transcript, accepted)
        if not accepted:
            raise PipelineError(
                "No clip candidates survived critic pass. Try a longer transcript, lower the "
                "critic threshold in development, or inspect transcript/candidate quality."
            )

        renderer = RemotionRendererClient(self.config.renderer_url) if self.config.render else None
        if renderer:
            renderer.ensure_available()

        final_clips: list[FinalClip] = []

        for index, candidate in enumerate(accepted, start=1):
            clip_id = f"clip_{index:02d}"
            raw_clip = cut_clip(
                source_video,
                raw_clips_dir / f"{clip_id}.mp4",
                candidate.start,
                candidate.end,
            )
            reframe_result = analyze_and_reframe_to_vertical(
                raw_clip,
                vertical_clips_dir / f"{clip_id}.mp4",
                visual_debug_dir / clip_id,
                clip_id=clip_id,
                clip_start=candidate.start,
                clip_end=candidate.end,
            )
            vertical_clip = reframe_result.output_path
            visual_samples = self._visual_samples_for_metadata(reframe_result, output_dir)
            face_boxes = self._face_boxes_for_metadata(reframe_result)
            video_url = vertical_clip.resolve().as_uri()
            if renderer:
                relative_video = vertical_clip.relative_to(self.config.output_root / job_id)
                video_url = (
                    f"{self.config.renderer_url.rstrip('/')}/output/"
                    f"{job_id}/{relative_video.as_posix()}"
                )
            render_props = build_remotion_props(
                video_url=video_url,
                transcript=transcript,
                clip=candidate,
                layout_mode=reframe_result.layout_mode,
                reframe_mode=reframe_result.reframe_mode,
                face_boxes=face_boxes,
                layout_confidence=reframe_result.layout_confidence,
                visual_samples=visual_samples,
            )
            render_props_path = render_props_dir / f"{clip_id}.json"
            render_props_path.write_text(render_props.model_dump_json(indent=2), encoding="utf-8")

            rendered_path = None
            if renderer:
                rendered_path = rendered_clips_dir / f"{clip_id}.mp4"
                renderer.render(
                    job_id=job_id,
                    clip_index=index,
                    props=render_props,
                    output_relative_path=rendered_path.relative_to(output_dir),
                )
                self._require_output_file(rendered_path, "Remotion render")

            final_clips.append(
                FinalClip(
                    id=clip_id,
                    title=candidate.title,
                    start=candidate.start,
                    end=candidate.end,
                    viral_score=candidate.viral_score,
                    hook_text=candidate.hook_text,
                    hook_sentence=candidate.hook_sentence,
                    viral_reason=candidate.viral_reason,
                    dominant_mechanism=candidate.dominant_mechanism,
                    platform_fit=candidate.platform_fit,
                    suggested_caption=candidate.suggested_caption,
                    risk_flags=candidate.risk_flags,
                    source_clip_path=self._relative_to_job(raw_clip, output_dir),
                    vertical_clip_path=self._relative_to_job(vertical_clip, output_dir),
                    rendered_clip_path=(
                        self._relative_to_job(rendered_path, output_dir) if rendered_path else None
                    ),
                    render_props_path=self._relative_to_job(render_props_path, output_dir),
                    render_job=render_props,
                    layout_mode=reframe_result.layout_mode,
                    reframe_mode=reframe_result.reframe_mode,
                    face_boxes=face_boxes,
                    layout_confidence=reframe_result.layout_confidence,
                    visual_samples=visual_samples,
                    visual_debug_path=self._relative_to_job(
                        reframe_result.visual_debug_path.parent,
                        output_dir,
                    ),
                )
            )

        metadata = ClipExportMetadata(
            source=source,
            source_video_path=self._relative_to_job(source_video, output_dir),
            transcript_path=self._relative_to_job(transcript_path, output_dir),
            scenes_path=self._relative_to_job(scenes_path, output_dir),
            zip_export_path=Path("export.zip") if self.config.write_zip else None,
            output_dir=Path("."),
            clips=final_clips,
            status="completed",
            errors=[],
        )
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata.model_dump(mode="json", exclude_none=True), indent=2),
            encoding="utf-8",
        )
        if self.config.write_zip:
            self._write_zip_export(output_dir, output_dir / "export.zip")
        return metadata

    @staticmethod
    def _relative_to_job(path: Path, output_dir: Path) -> Path:
        try:
            return path.relative_to(output_dir)
        except ValueError:
            return path

    @staticmethod
    def _require_output_file(path: Path, operation: str) -> None:
        if not path.exists():
            raise PipelineError(f"{operation} completed but output file is missing: {path}")
        if path.stat().st_size <= 0:
            raise PipelineError(f"{operation} completed but output file is empty: {path}")

    @staticmethod
    def _visual_samples_for_metadata(reframe_result, output_dir: Path) -> list[dict]:
        samples = []
        for sample in reframe_result.visual_samples:
            payload = sample.to_dict()
            if sample.path is not None:
                payload["path"] = ClipLabPipeline._relative_to_job(sample.path, output_dir)
            samples.append(payload)
        return samples

    @staticmethod
    def _face_boxes_for_metadata(reframe_result) -> list[dict]:
        return [face.to_dict() for face in reframe_result.face_boxes]

    @staticmethod
    def _write_zip_export(output_dir: Path, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output_dir.rglob("*")):
                if not path.is_file() or path == zip_path:
                    continue
                archive.write(path, path.relative_to(output_dir).as_posix())
