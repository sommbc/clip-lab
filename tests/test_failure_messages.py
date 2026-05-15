import pytest
import httpx
from fastapi import HTTPException

from cliplab_api.main import _resolve_job_output_dir
from cliplab_clip_intelligence import ModelProviderError, OpenRouterClipModelProvider
from cliplab_pipeline import RemotionRendererClient
from cliplab_video_processing.ffmpeg import MediaToolMissingError, require_ffmpeg, require_ffprobe
from cliplab_video_processing.ingest import IngestError, ingest_source


class OpenRouterResponseProvider(OpenRouterClipModelProvider):
    def __init__(self, responses, **kwargs):
        super().__init__(**kwargs)
        self.responses = list(responses)
        self.models_seen = []

    def _post_chat_completion(self, payload, *, timeout_sec=None):
        self.models_seen.append(payload["model"])
        response = self.responses.pop(0)
        status_code = response.pop("status_code", 200)
        return httpx.Response(status_code, json=response)


def test_local_ingest_reports_invalid_input_path(tmp_path):
    with pytest.raises(IngestError, match="Input video path does not exist"):
        ingest_source(str(tmp_path / "missing.mp4"), tmp_path / "source")


def test_media_tool_errors_name_the_missing_binary(monkeypatch):
    monkeypatch.setenv("CLIP_LAB_FFMPEG_PATH", "/definitely/missing/ffmpeg")
    monkeypatch.setenv("CLIP_LAB_FFPROBE_PATH", "/definitely/missing/ffprobe")

    with pytest.raises(MediaToolMissingError, match="CLIP_LAB_FFMPEG_PATH"):
        require_ffmpeg()
    with pytest.raises(MediaToolMissingError, match="CLIP_LAB_FFPROBE_PATH"):
        require_ffprobe()


def test_renderer_unavailable_error_points_to_no_render_flag():
    client = RemotionRendererClient("http://127.0.0.1:1")

    with pytest.raises(RuntimeError, match="--no-render"):
        client.ensure_available()


def test_export_job_id_rejects_path_traversal():
    with pytest.raises(HTTPException) as excinfo:
        _resolve_job_output_dir("../private")

    assert excinfo.value.status_code == 400


def test_openrouter_missing_key_fails_only_when_provider_is_used():
    provider = OpenRouterClipModelProvider(api_key="", candidate_model="openrouter/test")

    with pytest.raises(ModelProviderError, match="OPENROUTER_API_KEY"):
        provider.generate_json("{}", purpose="candidate_mining")


def test_openrouter_missing_key_does_not_retry():
    class CountingProvider(OpenRouterClipModelProvider):
        calls = 0

        def _post_chat_completion(self, payload, *, timeout_sec=None):
            self.calls += 1
            return httpx.Response(200, json={"choices": []})

    provider = CountingProvider(api_key="", candidate_model="openrouter/test")

    with pytest.raises(ModelProviderError, match="OPENROUTER_API_KEY"):
        provider.generate_json("{}", purpose="candidate_mining")

    assert provider.calls == 0


def test_openrouter_missing_choices_fails_clearly():
    provider = OpenRouterResponseProvider(
        [{"id": "response-id"}],
        api_key="test-key",
        candidate_model="openrouter/test",
        max_json_retries=0,
    )

    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate_json("{}", purpose="candidate_mining")

    message = str(excinfo.value)
    assert "pass=candidate" in message
    assert "model=openrouter/test" in message
    assert "did not include choices" in message
    assert "response_keys=['id']" in message


def test_openrouter_empty_message_content_fails_clearly():
    provider = OpenRouterResponseProvider(
        [{"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}],
        api_key="test-key",
        packaging_model="openrouter/test",
        max_json_retries=0,
    )

    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate_json("{}", purpose="packaging")

    message = str(excinfo.value)
    assert "pass=packaging" in message
    assert "model=openrouter/test" in message
    assert "no usable text" in message
    assert "choice_keys=['finish_reason', 'message']" in message
    assert "finish_reason=stop" in message


def test_openrouter_message_reasoning_is_used_when_content_is_empty():
    provider = OpenRouterResponseProvider(
        [{"choices": [{"message": {"content": "", "reasoning": '{"ok": true}'}}]}],
        api_key="test-key",
        candidate_model="openrouter/test",
        max_json_retries=0,
    )

    assert provider.generate_json("{}", purpose="candidate_mining") == {"ok": True}


def test_openrouter_invalid_json_retries_then_fails_clearly():
    class InvalidJsonProvider(OpenRouterClipModelProvider):
        calls = 0

        def _complete(self, prompt, *, model, purpose, attempt, request_timeout_sec):
            self.calls += 1
            return "not json"

    provider = InvalidJsonProvider(
        api_key="test-key",
        candidate_model="openrouter/test",
        max_json_retries=2,
    )

    with pytest.raises(ModelProviderError, match="invalid JSON"):
        provider.generate_json("{}", purpose="candidate_mining")

    assert provider.calls == 3


def test_openrouter_primary_failure_uses_configured_fallback():
    provider = OpenRouterResponseProvider(
        [
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": '{"ok": true}'}}]},
        ],
        api_key="test-key",
        candidate_model="primary/model",
        candidate_fallback_model="fallback/model",
        max_json_retries=1,
    )

    assert provider.generate_json("{}", purpose="candidate_mining") == {"ok": True}
    assert provider.models_seen == ["primary/model", "primary/model", "fallback/model"]


def test_openrouter_comma_separated_model_chain_rotates_in_order():
    provider = OpenRouterResponseProvider(
        [
            {"id": "missing-choices"},
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": '{"ok": true}'}}]},
        ],
        api_key="test-key",
        candidate_model="primary/model, second/model",
        candidate_fallback_model="fallback/model, second/model",
        max_json_retries=0,
    )

    assert provider.generate_json("{}", purpose="candidate_mining") == {"ok": True}
    assert provider.models_seen == ["primary/model", "second/model", "fallback/model"]


def test_openrouter_pass_timeout_stops_before_request():
    provider = OpenRouterResponseProvider(
        [{"choices": [{"message": {"content": '{"ok": true}'}}]}],
        api_key="test-key",
        candidate_model="primary/model",
        pass_timeout_sec=0,
    )

    with pytest.raises(ModelProviderError, match="timed out"):
        provider.generate_json("{}", purpose="candidate_mining")

    assert provider.models_seen == []
