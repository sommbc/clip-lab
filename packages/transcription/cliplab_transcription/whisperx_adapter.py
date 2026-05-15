from __future__ import annotations

import importlib
import os
from typing import Any

from cliplab_shared import NormalizedTranscript, TranscriptSegment, TranscriptWord

from .base import TranscriptionRequest


class WhisperXTranscriptionProvider:
    name = "whisperx"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        batch_size: int | None = None,
        align: bool | None = None,
        hf_token: str | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("CLIP_LAB_WHISPERX_MODEL", "large-v3")
        self.device = device or os.environ.get("CLIP_LAB_WHISPERX_DEVICE", "cpu")
        compute_type = compute_type or os.environ.get("CLIP_LAB_WHISPERX_COMPUTE_TYPE", "float16")
        if self.device == "cpu" and compute_type == "float16":
            compute_type = "int8"
        self.compute_type = compute_type
        self.batch_size = batch_size or int(os.environ.get("CLIP_LAB_WHISPERX_BATCH_SIZE", "16"))
        self.align = (
            align
            if align is not None
            else os.environ.get("CLIP_LAB_WHISPERX_ALIGN", "true").lower()
            not in {"0", "false", "no"}
        )
        self.hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN")

    def transcribe(self, request: TranscriptionRequest) -> NormalizedTranscript:
        whisperx = self._load_whisperx()
        audio_path = str(request.audio_path)
        audio = whisperx.load_audio(audio_path)

        model = whisperx.load_model(
            self.model_name,
            self.device,
            compute_type=self.compute_type,
            language=request.language,
        )
        result = model.transcribe(audio, batch_size=self.batch_size)

        language = result.get("language") or request.language or "und"

        if self.align:
            align_model, metadata = whisperx.load_align_model(
                language_code=language,
                device=self.device,
            )
            result = whisperx.align(
                result["segments"],
                align_model,
                metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )

        if request.diarize:
            if not self.hf_token:
                raise RuntimeError("WhisperX diarization requires HUGGINGFACE_TOKEN.")
            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=self.hf_token,
                device=self.device,
            )
            diarize_segments = diarize_model(
                audio,
                min_speakers=request.min_speakers,
                max_speakers=request.max_speakers,
            )
            result = whisperx.assign_word_speakers(diarize_segments, result)

        return self._normalize_result(result, language=language)

    def _load_whisperx(self) -> Any:
        try:
            return importlib.import_module("whisperx")
        except ImportError:
            raise RuntimeError(
                "WhisperX is not installed. Install with `pip install -e .[whisperx]` "
                "or build the API image with `INSTALL_WHISPERX=true`."
            )

    @staticmethod
    def _normalize_result(result: dict[str, Any], language: str) -> NormalizedTranscript:
        segments: list[TranscriptSegment] = []
        full_text: list[str] = []
        duration = 0.0

        for raw_segment in result.get("segments", []):
            words = []
            segment_speaker = raw_segment.get("speaker")
            for raw_word in raw_segment.get("words", []) or []:
                start = raw_word.get("start")
                end = raw_word.get("end")
                token = (raw_word.get("word") or raw_word.get("text") or "").strip()
                if start is None or end is None or not token:
                    continue
                words.append(
                    TranscriptWord(
                        word=token,
                        start=float(start),
                        end=float(end),
                        speaker=raw_word.get("speaker") or segment_speaker,
                    )
                )

            text = (raw_segment.get("text") or " ".join(word.word for word in words)).strip()
            start = float(raw_segment.get("start", words[0].start if words else 0.0))
            end = float(raw_segment.get("end", words[-1].end if words else start + 0.01))
            duration = max(duration, end)
            full_text.append(text)
            segments.append(
                TranscriptSegment(
                    text=text,
                    start=start,
                    end=end,
                    speaker=segment_speaker,
                    words=words,
                )
            )

        if not segments:
            raise RuntimeError("WhisperX returned no transcript segments.")

        return NormalizedTranscript(
            text=" ".join(chunk for chunk in full_text if chunk),
            language=language,
            duration=duration,
            segments=segments,
        )
