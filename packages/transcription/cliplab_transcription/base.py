from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cliplab_shared import NormalizedTranscript


@dataclass(frozen=True)
class TranscriptionRequest:
    audio_path: Path
    language: str | None = None
    diarize: bool = False
    min_speakers: int | None = None
    max_speakers: int | None = None


class TranscriptionProvider(Protocol):
    name: str

    def transcribe(self, request: TranscriptionRequest) -> NormalizedTranscript:
        """Transcribe an audio file into Clip Lab's normalized transcript contract."""

