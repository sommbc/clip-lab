import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_api_import_does_not_load_whisperx_adapter_or_heavy_module():
    sys.modules.pop("whisperx", None)
    sys.modules.pop("cliplab_transcription.whisperx_adapter", None)

    importlib.import_module("cliplab_api.main")

    assert "whisperx" not in sys.modules
    assert "cliplab_transcription.whisperx_adapter" not in sys.modules


def test_transcription_package_default_import_is_provider_agnostic():
    sys.modules.pop("cliplab_transcription.whisperx_adapter", None)

    module = importlib.import_module("cliplab_transcription")

    assert hasattr(module, "TranscriptionProvider")
    assert hasattr(module, "create_transcription_provider")
    assert "cliplab_transcription.whisperx_adapter" not in sys.modules


def test_api_package_stays_orchestration_only():
    forbidden_imports = (
        "cliplab_clip_intelligence",
        "cliplab_video_processing",
        "cliplab_captions",
        "whisperx",
        "vendor.",
    )
    for path in (ROOT / "apps" / "api" / "cliplab_api").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in source, f"{path} imports business/provider logic: {forbidden}"


def test_raw_whisperx_is_confined_to_transcription_adapter():
    allowed = ROOT / "packages" / "transcription" / "cliplab_transcription" / "whisperx_adapter.py"
    for path in (ROOT / "packages").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "whisperx." not in source.lower():
            continue
        assert path == allowed, f"raw WhisperX reference outside adapter: {path}"


def test_raw_model_provider_responses_are_confined_to_provider_layer():
    allowed = ROOT / "packages" / "clip_intelligence" / "cliplab_clip_intelligence" / "llm.py"
    raw_markers = ("chat/completions", "choices", "OPENROUTER_API_KEY")
    for path in (ROOT / "packages").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if not any(marker in source for marker in raw_markers):
            continue
        assert path == allowed, f"raw model-provider handling outside provider layer: {path}"
