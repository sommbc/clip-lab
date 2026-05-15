from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Literal, Protocol

import httpx


ModelPurpose = Literal["candidate_mining", "critic_editor", "packaging"]
PURPOSE_LABELS: dict[ModelPurpose, str] = {
    "candidate_mining": "candidate",
    "critic_editor": "critic",
    "packaging": "packaging",
}
PURPOSE_MODEL_ENV: dict[ModelPurpose, str] = {
    "candidate_mining": "CLIP_LAB_CANDIDATE_MODEL",
    "critic_editor": "CLIP_LAB_CRITIC_MODEL",
    "packaging": "CLIP_LAB_PACKAGING_MODEL",
}
PURPOSE_FALLBACK_MODEL_ENV: dict[ModelPurpose, str] = {
    "candidate_mining": "CLIP_LAB_CANDIDATE_FALLBACK_MODEL",
    "critic_editor": "CLIP_LAB_CRITIC_FALLBACK_MODEL",
    "packaging": "CLIP_LAB_PACKAGING_FALLBACK_MODEL",
}


class ModelProviderError(RuntimeError):
    pass


class _OpenRouterAttemptError(ModelProviderError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        fallbackable: bool = True,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.fallbackable = fallbackable


class ClipModelProvider(Protocol):
    name: str

    def generate_json(self, prompt: str, *, purpose: ModelPurpose) -> dict[str, Any]:
        """Return model output as parsed JSON. Callers must still schema-validate it."""


class OpenRouterClipModelProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        candidate_model: str | None = None,
        critic_model: str | None = None,
        packaging_model: str | None = None,
        candidate_fallback_model: str | None = None,
        critic_fallback_model: str | None = None,
        packaging_fallback_model: str | None = None,
        timeout_sec: float | None = None,
        pass_timeout_sec: float | None = None,
        packaging_timeout_sec: float | None = None,
        max_json_retries: int = 2,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.models = {
            "candidate_mining": candidate_model
            if candidate_model is not None
            else os.environ.get(PURPOSE_MODEL_ENV["candidate_mining"], ""),
            "critic_editor": critic_model
            if critic_model is not None
            else os.environ.get(PURPOSE_MODEL_ENV["critic_editor"], ""),
            "packaging": packaging_model
            if packaging_model is not None
            else os.environ.get(PURPOSE_MODEL_ENV["packaging"], ""),
        }
        self.fallback_models = {
            "candidate_mining": candidate_fallback_model
            if candidate_fallback_model is not None
            else os.environ.get(PURPOSE_FALLBACK_MODEL_ENV["candidate_mining"], ""),
            "critic_editor": critic_fallback_model
            if critic_fallback_model is not None
            else os.environ.get(PURPOSE_FALLBACK_MODEL_ENV["critic_editor"], ""),
            "packaging": packaging_fallback_model
            if packaging_fallback_model is not None
            else os.environ.get(PURPOSE_FALLBACK_MODEL_ENV["packaging"], ""),
        }
        self.timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else _env_float("CLIP_LAB_OPENROUTER_REQUEST_TIMEOUT_SEC", 45.0)
        )
        self.pass_timeout_sec = (
            pass_timeout_sec
            if pass_timeout_sec is not None
            else _env_float("CLIP_LAB_OPENROUTER_PASS_TIMEOUT_SEC", 90.0)
        )
        self.packaging_timeout_sec = (
            packaging_timeout_sec
            if packaging_timeout_sec is not None
            else _env_float("CLIP_LAB_OPENROUTER_PACKAGING_TIMEOUT_SEC", 30.0)
        )
        self.max_json_retries = max_json_retries

    def generate_json(self, prompt: str, *, purpose: ModelPurpose) -> dict[str, Any]:
        models = self._models_for_purpose(purpose)
        deadline = time.monotonic() + self._pass_timeout_for_purpose(purpose)
        failures: list[str] = []
        last_error: _OpenRouterAttemptError | None = None
        for index, model in enumerate(models):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failures.append(f"timed out before model={model}")
                break
            attempts = self.max_json_retries + 1 if index == 0 else 1
            try:
                payload = self._generate_json_with_model(
                    prompt,
                    purpose=purpose,
                    model=model,
                    attempts=attempts,
                    deadline=deadline,
                )
                print(
                    f"OpenRouter success pass={PURPOSE_LABELS[purpose]} model={model}",
                    file=sys.stderr,
                )
                return payload
            except _OpenRouterAttemptError as fallback_error:
                last_error = fallback_error
                failures.append(f"model={model}: {fallback_error}")
                if not fallback_error.fallbackable:
                    break
        label = PURPOSE_LABELS[purpose]
        attempted = ", ".join(models)
        detail = "; ".join(failures)
        raise ModelProviderError(
            f"OpenRouter failed for pass={label}; attempted_models=[{attempted}]; {detail}"
        ) from last_error

    def _pass_timeout_for_purpose(self, purpose: ModelPurpose) -> float:
        if purpose == "packaging":
            return self.packaging_timeout_sec
        return self.pass_timeout_sec

    def _generate_json_with_model(
        self,
        prompt: str,
        *,
        purpose: ModelPurpose,
        model: str,
        attempts: int,
        deadline: float,
    ) -> dict[str, Any]:
        last_error: _OpenRouterAttemptError | None = None
        for attempt in range(attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _OpenRouterAttemptError(
                    f"OpenRouter pass timed out for pass={PURPOSE_LABELS[purpose]} model={model}",
                    retryable=False,
                )
            try:
                content = self._complete(
                    prompt,
                    model=model,
                    purpose=purpose,
                    attempt=attempt,
                    request_timeout_sec=min(self.timeout_sec, remaining),
                )
                return decode_json_document(content)
            except json.JSONDecodeError as exc:
                last_error = _OpenRouterAttemptError(
                    f"OpenRouter returned invalid JSON for pass={PURPOSE_LABELS[purpose]} "
                    f"model={model} after attempt {attempt + 1}/{attempts}: {exc.msg}"
                )
            except _OpenRouterAttemptError as exc:
                last_error = exc
                if not exc.retryable:
                    break
        if last_error:
            raise last_error
        raise ModelProviderError(f"OpenRouter failed for pass={PURPOSE_LABELS[purpose]} model={model}.")

    def _models_for_purpose(self, purpose: ModelPurpose) -> list[str]:
        if not self.api_key:
            raise ModelProviderError(
                "OPENROUTER_API_KEY is required when the OpenRouter model provider is used."
            )
        models = _model_chain(self.models[purpose]) + _model_chain(self.fallback_models[purpose])
        deduped = list(dict.fromkeys(models))
        if not deduped:
            env_var = PURPOSE_MODEL_ENV[purpose]
            raise ModelProviderError(f"{env_var} is required for OpenRouter {purpose}.")
        return deduped

    def _fallback_model_for_purpose(self, purpose: ModelPurpose) -> str:
        return self.fallback_models[purpose].strip()

    def _complete(
        self,
        prompt: str,
        *,
        model: str,
        purpose: ModelPurpose,
        attempt: int,
        request_timeout_sec: float,
    ) -> str:
        payload = {
            "model": model,
            "temperature": 0.2 if attempt == 0 else 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Clip Lab's backend clip-intelligence model. "
                        "Return strict JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        response = self._post_chat_completion(payload, timeout_sec=request_timeout_sec)
        body = self._decode_response_body(response, purpose=purpose, model=model)
        provider_error = _provider_error_summary(body.get("error")) if isinstance(body, dict) else ""
        if provider_error:
            raise _OpenRouterAttemptError(
                f"OpenRouter provider error for pass={PURPOSE_LABELS[purpose]} model={model}: "
                f"{provider_error}; response_keys={_safe_keys(body)}",
                retryable=not _is_auth_error(provider_error),
                fallbackable=not _is_auth_error(provider_error),
            )

        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise _OpenRouterAttemptError(
                f"OpenRouter response for pass={PURPOSE_LABELS[purpose]} model={model} "
                f"did not include choices; response_keys={_safe_keys(body)}"
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise _OpenRouterAttemptError(
                f"OpenRouter response for pass={PURPOSE_LABELS[purpose]} model={model} "
                f"had invalid choice type={type(choice).__name__}; response_keys={_safe_keys(body)}"
            )
        text = _extract_choice_text(choice)
        if text:
            return text

        raise _OpenRouterAttemptError(
            f"OpenRouter response had no usable text for pass={PURPOSE_LABELS[purpose]} "
            f"model={model}; response_keys={_safe_keys(body)}; choice_keys={_safe_keys(choice)}; "
            f"finish_reason={choice.get('finish_reason') or 'missing'}; "
            f"provider_error={provider_error or 'none'}"
        )

    def _post_chat_completion(
        self,
        payload: dict[str, Any],
        *,
        timeout_sec: float | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Clip Lab",
        }
        try:
            return httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_sec if timeout_sec is not None else self.timeout_sec,
            )
        except httpx.RequestError as exc:
            raise _OpenRouterAttemptError(f"OpenRouter request failed: {exc}") from exc

    def _decode_response_body(
        self,
        response: httpx.Response,
        *,
        purpose: ModelPurpose,
        model: str,
    ) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            body_text = _safe_text(response.text)
            raise _OpenRouterAttemptError(
                f"OpenRouter returned non-JSON response for pass={PURPOSE_LABELS[purpose]} "
                f"model={model}; status={response.status_code}; body={body_text}"
            ) from exc

        if not 200 <= response.status_code < 300:
            summary = _safe_response_summary(body)
            auth_error = response.status_code in {401, 403} or _is_auth_error(summary)
            raise _OpenRouterAttemptError(
                f"OpenRouter HTTP error for pass={PURPOSE_LABELS[purpose]} model={model}: "
                f"status={response.status_code}; {summary}",
                retryable=response.status_code in {408, 409, 425, 429, 500, 502, 503, 504},
                fallbackable=not auth_error,
            )

        if not isinstance(body, dict):
            raise _OpenRouterAttemptError(
                f"OpenRouter returned unexpected JSON root for pass={PURPOSE_LABELS[purpose]} "
                f"model={model}; root_type={type(body).__name__}"
            )
        return body


class FakeClipModelProvider:
    name = "fake"

    def generate_json(self, prompt: str, *, purpose: ModelPurpose) -> dict[str, Any]:
        if purpose == "candidate_mining":
            return self._candidate_payload(prompt)
        if purpose == "critic_editor":
            return self._critic_payload(prompt)
        if purpose == "packaging":
            return self._packaging_payload(prompt)
        raise ModelProviderError(f"Unsupported fake model purpose: {purpose}")

    def _candidate_payload(self, prompt: str) -> dict[str, Any]:
        transcript = _json_after_marker(prompt, "TRANSCRIPT_JSON:") or {}
        duration = float(transcript.get("duration") or 8.0)
        text = str(transcript.get("text") or "This is a strong clip with a clear payoff.")
        hook_sentence = _first_sentence(text)
        end = max(5.0, min(duration, 45.0))
        return {
            "candidates": [
                {
                    "title": _title_from_sentence(hook_sentence),
                    "start": 0.0,
                    "end": end,
                    "viral_score": 86,
                    "hook_text": _hook_from_sentence(hook_sentence),
                    "hook_sentence": hook_sentence,
                    "viral_reason": "Fake provider selected a self-contained fixture clip.",
                    "dominant_mechanism": "tactical",
                    "platform_fit": ["tiktok", "reels", "shorts"],
                    "suggested_caption": "Save this clip for the full breakdown.",
                    "risk_flags": [],
                    "scorecard": {
                        "hook_strength": 86,
                        "self_contained_context": 84,
                        "payoff_strength": 84,
                        "novelty_or_surprise": 78,
                        "conflict_or_tension": 74,
                        "emotional_charge": 70,
                        "tactical_value": 88,
                        "quotability": 82,
                        "retention_likelihood": 84,
                        "platform_suitability": 90,
                        "clean_boundaries": 86,
                    },
                }
            ]
        }

    def _critic_payload(self, prompt: str) -> dict[str, Any]:
        candidates = _json_after_marker(prompt, "CANDIDATES_JSON:") or []
        verdicts = [
            {
                "accepted": candidate.get("viral_score", 0) >= 60,
                "candidate": candidate,
                "concerns": [],
                "suggested_start": None,
                "suggested_end": None,
            }
            for candidate in candidates
        ]
        return {"verdicts": verdicts}

    def _packaging_payload(self, prompt: str) -> dict[str, Any]:
        candidates = _json_after_marker(prompt, "ACCEPTED_CANDIDATES_JSON:") or []
        packages = []
        for candidate in candidates:
            packages.append(
                {
                    "candidate_id": candidate["id"],
                    "title": candidate["title"],
                    "hook_text": candidate["hook_text"],
                    "hook_sentence": candidate["hook_sentence"],
                    "suggested_caption": candidate["suggested_caption"],
                    "viral_reason": candidate["viral_reason"],
                    "platform_fit": candidate["platform_fit"],
                    "risk_flags": candidate.get("risk_flags", []),
                }
            )
        return {"packages": packages}


def create_clip_model_provider(name: str | None = None) -> ClipModelProvider:
    provider_name = (name or os.environ.get("CLIP_LAB_MODEL_PROVIDER") or "fake").lower()
    if provider_name in {"fake", "dev"}:
        return FakeClipModelProvider()
    if provider_name == "openrouter":
        return OpenRouterClipModelProvider()
    raise ModelProviderError(f"Unsupported clip model provider: {provider_name}")


def _model_chain(value: str) -> list[str]:
    return [model.strip() for model in value.split(",") if model.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ModelProviderError(f"{name} must be a number, got: {raw}") from exc


def _extract_choice_text(choice: dict[str, Any]) -> str:
    message = choice.get("message")
    if isinstance(message, dict):
        for key in ("content", "reasoning", "output_text"):
            text = _text_from_value(message.get(key))
            if text:
                return text
        text = _text_from_tool_calls(message.get("tool_calls"))
        if text:
            return text

    for key in ("text", "output_text", "content", "reasoning"):
        text = _text_from_value(choice.get(key))
        if text:
            return text

    delta = choice.get("delta")
    if isinstance(delta, dict):
        for key in ("content", "reasoning", "output_text"):
            text = _text_from_value(delta.get(key))
            if text:
                return text
    return ""


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks = [_text_from_value(item) for item in value]
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "reasoning", "output_text"):
            text = _text_from_value(value.get(key))
            if text:
                return text
    return ""


def _text_from_tool_calls(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    chunks: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if isinstance(function, dict):
            text = _text_from_value(function.get("arguments"))
            if text:
                chunks.append(text)
        text = _text_from_value(item.get("arguments"))
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _provider_error_summary(error: Any) -> str:
    if not error:
        return ""
    if isinstance(error, dict):
        code = _safe_text(error.get("code") or error.get("type") or "unknown")
        message = _safe_text(error.get("message") or error.get("error") or "")
        return f"error_code={code}; error_message={message or 'missing'}"
    return f"error_message={_safe_text(error)}"


def _safe_response_summary(body: Any) -> str:
    if isinstance(body, dict):
        error_summary = _provider_error_summary(body.get("error"))
        if error_summary:
            return f"{error_summary}; response_keys={_safe_keys(body)}"
        return f"response_keys={_safe_keys(body)}"
    return f"response_type={type(body).__name__}; response_summary={_safe_text(body)}"


def _safe_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return []


def _safe_text(value: Any, limit: int = 300) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _is_auth_error(summary: str) -> bool:
    lower = summary.lower()
    return any(term in lower for term in ("auth", "unauthorized", "forbidden", "api key"))


def decode_json_document(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("model output root must be an object", text, 0)
    return parsed


def _json_after_marker(prompt: str, marker: str) -> Any:
    index = prompt.rfind(marker)
    if index == -1:
        return None
    text = prompt[index + len(marker) :].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _first_sentence(text: str) -> str:
    match = re.search(r"(.{20,220}?[.!?])(?:\s|$)", text.strip())
    return match.group(1).strip() if match else text.strip()[:220] or "This clip has a clear hook."


def _title_from_sentence(sentence: str) -> str:
    words = re.findall(r"\w+['\w]*", sentence)
    return " ".join(words[:10]).strip().capitalize() or "Clip Lab Short"


def _hook_from_sentence(sentence: str) -> str:
    words = re.findall(r"\w+['\w]*", sentence)
    return (" ".join(words[:9]) or "WATCH THIS").upper()
