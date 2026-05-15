from __future__ import annotations

import re
import sys

from cliplab_shared import (
    ClipCandidate,
    ClipMechanism,
    ClipPackagingSet,
    ClipRiskFlag,
    NormalizedTranscript,
    Platform,
)

from .llm import ClipModelProvider
from .model_output import repair_packaging_payload
from .prompts import PACKAGING_PROMPT


class ClipPackager:
    def __init__(self, model_provider: ClipModelProvider | None = None) -> None:
        self.model_provider = model_provider

    def package(
        self,
        transcript: NormalizedTranscript,
        candidates: list[ClipCandidate],
    ) -> list[ClipCandidate]:
        if not self.model_provider:
            return [self._package_heuristically(candidate, transcript) for candidate in candidates]
        return self._package_with_model(transcript, candidates)

    def _package_with_model(
        self,
        transcript: NormalizedTranscript,
        candidates: list[ClipCandidate],
    ) -> list[ClipCandidate]:
        candidates_with_ids = [
            {"id": f"clip_{index:02d}", **candidate.model_dump(mode="json", exclude_none=True)}
            for index, candidate in enumerate(candidates, start=1)
        ]
        prompt = PACKAGING_PROMPT.render(
            "TRANSCRIPT_JSON:\n"
            + transcript.model_dump_json(exclude_none=True)
            + "\n\nACCEPTED_CANDIDATES_JSON:\n"
            + _json_array(candidates_with_ids)
        )
        try:
            packaging = ClipPackagingSet.model_validate(
                repair_packaging_payload(
                    self.model_provider.generate_json(prompt, purpose="packaging")
                )
            )
        except Exception as exc:
            print(
                f"ClipPackager local fallback used: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return [self._package_heuristically(candidate, transcript) for candidate in candidates]

        packages_by_id = {package.candidate_id: package for package in packaging.packages}
        packaged: list[ClipCandidate] = []
        for index, candidate in enumerate(candidates, start=1):
            package = packages_by_id.get(f"clip_{index:02d}")
            if not package:
                print(
                    f"ClipPackager local fallback used: missing package for clip_{index:02d}",
                    file=sys.stderr,
                )
                packaged.append(self._package_heuristically(candidate, transcript))
                continue
            packaged.append(
                candidate.model_copy(
                    update={
                        "title": package.title,
                        "hook_text": package.hook_text,
                        "hook_sentence": package.hook_sentence,
                        "suggested_caption": package.suggested_caption,
                        "viral_reason": package.viral_reason,
                        "platform_fit": package.platform_fit,
                        "risk_flags": package.risk_flags,
                    }
                )
            )
        return packaged

    @staticmethod
    def _package_heuristically(
        candidate: ClipCandidate,
        transcript: NormalizedTranscript,
    ) -> ClipCandidate:
        clip_text = transcript.text_between(candidate.start, candidate.end)
        fallback_sentence = _first_sentence(clip_text) or candidate.hook_sentence or candidate.title
        title = _trim(candidate.title.strip().rstrip(".") or fallback_sentence, 120)
        hook_sentence = _trim(candidate.hook_sentence.strip() or fallback_sentence, 260)
        hook_text = _trim((candidate.hook_text.strip() or hook_sentence or title).upper(), 120)
        caption_source = hook_sentence or title
        suggested_caption = _finish_sentence(_trim(f"Watch this: {caption_source}", 499))
        viral_reason = _trim(
            candidate.viral_reason.strip()
            or "Selected as a self-contained clip with a clear hook and payoff.",
            800,
        )
        mechanism = _valid_mechanism(candidate.dominant_mechanism)
        risk_flags = [
            flag
            for flag in candidate.risk_flags
            if isinstance(flag, ClipRiskFlag)
        ]
        payload = candidate.model_dump(mode="json", exclude_none=True)
        payload.update(
            {
                "title": title or "Selected clip",
                "hook_text": hook_text or "WATCH THIS",
                "hook_sentence": hook_sentence or title or "Watch this.",
                "suggested_caption": suggested_caption,
                "viral_reason": viral_reason,
                "dominant_mechanism": mechanism.value,
                "platform_fit": [
                    Platform.tiktok.value,
                    Platform.reels.value,
                    Platform.shorts.value,
                    Platform.x.value,
                ],
                "risk_flags": [flag.value for flag in risk_flags],
            }
        )
        return ClipCandidate.model_validate(payload)


def _json_array(items: list[dict]) -> str:
    import json

    return json.dumps(items, separators=(",", ":"))


def _first_sentence(text: str) -> str:
    stripped = " ".join(text.split())
    if not stripped:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _finish_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Watch this."
    if stripped.endswith((".", "!", "?")):
        return stripped
    return f"{stripped}."


def _trim(text: str, limit: int) -> str:
    return text.strip()[:limit].rstrip()


def _valid_mechanism(value: ClipMechanism | str) -> ClipMechanism:
    try:
        return ClipMechanism(value)
    except ValueError:
        return ClipMechanism.quote
