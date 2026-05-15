from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from cliplab_shared import NormalizedTranscript


class TranscriptJsonError(RuntimeError):
    pass


def load_normalized_transcript_json(path: str | Path) -> NormalizedTranscript:
    transcript_path = Path(path).expanduser()
    if not transcript_path.exists():
        raise TranscriptJsonError(f"Transcript JSON path does not exist: {transcript_path}")
    if not transcript_path.is_file():
        raise TranscriptJsonError(f"Transcript JSON path is not a file: {transcript_path}")

    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranscriptJsonError(
            f"Transcript JSON is not valid JSON: {transcript_path}. {exc.msg} at line "
            f"{exc.lineno}, column {exc.colno}."
        ) from exc

    try:
        return NormalizedTranscript.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first_error.get("loc", ())) or "root"
        message = first_error.get("msg", "schema validation failed")
        raise TranscriptJsonError(
            f"Transcript JSON failed normalized transcript validation at {location}: {message}."
        ) from exc
