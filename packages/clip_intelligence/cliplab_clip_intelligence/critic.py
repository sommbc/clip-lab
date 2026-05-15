from __future__ import annotations

from cliplab_shared import ClipCandidate, ClipRiskFlag, CriticVerdictSet, NormalizedTranscript

from .llm import ClipModelProvider
from .model_output import repair_critic_payload
from .prompts import CRITIC_EDITOR_PROMPT

GENERIC_OPENINGS = (
    "welcome back",
    "before we start",
    "today i want",
    "in this episode",
    "thanks for watching",
)


class ClipCritic:
    def __init__(
        self,
        model_provider: ClipModelProvider | None = None,
        min_score: int = 68,
        min_duration: float = 5,
        max_duration: float = 60,
    ) -> None:
        self.model_provider = model_provider
        self.min_score = min_score
        self.min_duration = min_duration
        self.max_duration = max_duration

    def review(
        self,
        transcript: NormalizedTranscript,
        candidates: list[ClipCandidate],
    ) -> list[ClipCandidate]:
        if self.model_provider:
            return self._review_with_model(transcript, candidates)
        return self._review_heuristically(transcript, candidates)

    def _review_with_model(
        self,
        transcript: NormalizedTranscript,
        candidates: list[ClipCandidate],
    ) -> list[ClipCandidate]:
        prompt = CRITIC_EDITOR_PROMPT.render(
            "TRANSCRIPT_JSON:\n"
            + transcript.model_dump_json(exclude_none=True)
            + "\n\nCANDIDATES_JSON:\n"
            + _candidate_json(candidates)
        )
        verdicts = CriticVerdictSet.model_validate(
            repair_critic_payload(self.model_provider.generate_json(prompt, purpose="critic_editor"))
        )
        accepted: list[ClipCandidate] = []
        for verdict in verdicts.verdicts:
            candidate = verdict.candidate
            updates = {}
            if verdict.suggested_start is not None:
                updates["start"] = verdict.suggested_start
            if verdict.suggested_end is not None:
                updates["end"] = verdict.suggested_end
            if verdict.concerns:
                updates["risk_flags"] = sorted(
                    set(candidate.risk_flags + _risk_flags_from_concerns(verdict.concerns)),
                    key=str,
                )
            if updates:
                candidate = candidate.model_copy(update=updates)
            if verdict.accepted and self._accept(candidate):
                accepted.append(candidate)
        return accepted

    def _review_heuristically(
        self,
        transcript: NormalizedTranscript,
        candidates: list[ClipCandidate],
    ) -> list[ClipCandidate]:
        accepted: list[ClipCandidate] = []
        for candidate in candidates:
            concerns = self._concerns(transcript, candidate)
            if concerns:
                candidate = candidate.model_copy(
                    update={"risk_flags": sorted(set(candidate.risk_flags + concerns), key=str)}
                )
            if self._accept(candidate):
                accepted.append(candidate)
        return accepted

    def _concerns(
        self,
        transcript: NormalizedTranscript,
        candidate: ClipCandidate,
    ) -> list[ClipRiskFlag]:
        concerns: list[ClipRiskFlag] = []
        clip_text = transcript.text_between(candidate.start, candidate.end).lower()
        opening = clip_text[:180]

        if candidate.viral_score < self.min_score:
            concerns.append(ClipRiskFlag.weak_hook)
        if candidate.duration < self.min_duration or candidate.duration > self.max_duration:
            concerns.append(ClipRiskFlag.rambling)
        if any(term in opening for term in GENERIC_OPENINGS):
            concerns.append(ClipRiskFlag.weak_hook)
        if any(term in clip_text for term in ["sponsor", "promo code", "discount code"]):
            concerns.append(ClipRiskFlag.sponsor_read)
        if not any(mark in clip_text for mark in [".", "?", "!"]) or len(clip_text.split()) < 35:
            concerns.append(ClipRiskFlag.missing_context)
        if starts_or_ends_mid_sentence(transcript, candidate):
            concerns.append(ClipRiskFlag.mid_sentence_boundary)
        return concerns

    def _accept(self, candidate: ClipCandidate) -> bool:
        hard_rejects = {
            ClipRiskFlag.missing_context,
            ClipRiskFlag.weak_hook,
            ClipRiskFlag.rambling,
        }
        if candidate.viral_score < self.min_score:
            return False
        if not (self.min_duration <= candidate.duration <= self.max_duration):
            return False
        return not any(flag in hard_rejects for flag in candidate.risk_flags)


def _candidate_json(candidates: list[ClipCandidate]) -> str:
    return "[" + ",".join(candidate.model_dump_json(exclude_none=True) for candidate in candidates) + "]"


def _risk_flags_from_concerns(concerns: list[str]) -> list[ClipRiskFlag]:
    flags: list[ClipRiskFlag] = []
    valid = {flag.value: flag for flag in ClipRiskFlag}
    for concern in concerns:
        normalized = concern.lower().strip().replace(" ", "_").replace("-", "_")
        if normalized in valid:
            flags.append(valid[normalized])
    return flags


def starts_or_ends_mid_sentence(transcript: NormalizedTranscript, candidate: ClipCandidate) -> bool:
    words = transcript.words()
    if not words:
        return False
    start_word_index = next((i for i, word in enumerate(words) if word.end >= candidate.start), None)
    next_word_index = next((i for i, word in enumerate(words) if word.start >= candidate.end), None)
    if start_word_index is None:
        return False
    start_prev = words[start_word_index - 1].word if start_word_index > 0 else ""
    end_word = words[-1].word if next_word_index is None else words[max(0, next_word_index - 1)].word
    starts_after_sentence_break = start_word_index == 0 or start_prev.endswith((".", "?", "!"))
    ends_on_sentence_break = end_word.endswith((".", "?", "!"))
    return not starts_after_sentence_break or not ends_on_sentence_break
