from __future__ import annotations

import os

from .base import TranscriptionProvider


def create_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    provider_name = (name or os.environ.get("CLIP_LAB_TRANSCRIPTION_PROVIDER") or "whisperx").lower()

    if provider_name == "whisperx":
        from .whisperx_adapter import WhisperXTranscriptionProvider

        return WhisperXTranscriptionProvider()

    raise ValueError(f"Unsupported transcription provider: {provider_name}")
