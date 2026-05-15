from __future__ import annotations

import re
from dataclasses import dataclass

from cliplab_shared import (
    ClipCandidate,
    ClipCandidateSet,
    ClipMechanism,
    ClipScorecard,
    NormalizedTranscript,
    Platform,
)

from .llm import ClipModelProvider
from .model_output import repair_candidate_payload
from .prompts import CANDIDATE_MINING_PROMPT


HOOK_TERMS = {
    "nobody",
    "mistake",
    "wrong",
    "secret",
    "problem",
    "truth",
    "never",
    "always",
    "stop",
    "start",
    "why",
    "how",
    "but",
    "actually",
    "realized",
    "learned",
}
TACTICAL_TERMS = {"framework", "steps", "playbook", "workflow", "system", "template", "process"}
CONFLICT_TERMS = {"fight", "conflict", "against", "failed", "failure", "risk", "hard", "broken"}
CONTRARIAN_TERMS = {"everyone", "most people", "opposite", "counterintuitive", "myth"}
EMOTION_TERMS = {"love", "hate", "afraid", "excited", "angry", "pain", "regret", "proud"}
SPONSOR_TERMS = {"sponsor", "discount code", "promo code", "brought to you by"}
INTRO_TERMS = {"welcome back", "today we're", "in this episode", "thanks for watching"}


@dataclass(frozen=True)
class ClipGenerationConfig:
    min_duration: float = 5.0
    max_duration: float = 60.0
    target_duration: float = 42.0
    max_candidates: int = 8


class ClipGenerator:
    def __init__(
        self,
        model_provider: ClipModelProvider | None = None,
        config: ClipGenerationConfig | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.config = config or ClipGenerationConfig()

    def generate(self, transcript: NormalizedTranscript) -> ClipCandidateSet:
        if self.model_provider:
            candidates = self._generate_with_model(transcript)
        else:
            candidates = self._generate_heuristically(transcript)
        return ClipCandidateSet(candidates=candidates[: self.config.max_candidates])

    def _generate_with_model(self, transcript: NormalizedTranscript) -> list[ClipCandidate]:
        prompt = CANDIDATE_MINING_PROMPT.render(
            "TRANSCRIPT_JSON:\n" + transcript.model_dump_json(exclude_none=True)
        )
        raw = self.model_provider.generate_json(prompt, purpose="candidate_mining")
        candidate_set = ClipCandidateSet.model_validate(repair_candidate_payload(raw))
        return sorted(candidate_set.candidates, key=lambda candidate: candidate.viral_score, reverse=True)

    def _generate_heuristically(self, transcript: NormalizedTranscript) -> list[ClipCandidate]:
        windows = self._build_windows(transcript)
        candidates = []
        for start, end, text in windows:
            if any(term in text.lower() for term in INTRO_TERMS):
                continue
            scorecard, mechanism = score_text(text, duration=end - start)
            viral_score = scorecard.weighted_total
            if viral_score < 55:
                continue
            hook_sentence = trim_text(first_sentence(text) or text, 260)
            candidates.append(
                ClipCandidate(
                    title=make_title(hook_sentence),
                    start=start,
                    end=end,
                    viral_score=viral_score,
                    hook_text=make_hook_text(hook_sentence),
                    hook_sentence=hook_sentence,
                    viral_reason=make_reason(scorecard, mechanism),
                    dominant_mechanism=mechanism,
                    platform_fit=platform_fit_for(mechanism),
                    suggested_caption=make_caption(hook_sentence),
                    risk_flags=[],
                    scorecard=scorecard,
                )
            )
        return sorted(candidates, key=lambda candidate: candidate.viral_score, reverse=True)

    def _build_windows(self, transcript: NormalizedTranscript) -> list[tuple[float, float, str]]:
        windows: list[tuple[float, float, str]] = []
        segments = transcript.segments
        for index, segment in enumerate(segments):
            start = segment.start
            end = segment.end
            texts = [segment.text]
            cursor = index + 1
            while cursor < len(segments) and end - start < self.config.target_duration:
                end = segments[cursor].end
                texts.append(segments[cursor].text)
                cursor += 1
            duration = end - start
            if self.config.min_duration <= duration <= self.config.max_duration:
                windows.append((start, end, " ".join(texts).strip()))
        return dedupe_windows(windows)


def score_text(text: str, duration: float) -> tuple[ClipScorecard, ClipMechanism]:
    lower = text.lower()
    first_20_words = " ".join(re.findall(r"\w+", lower)[:20])
    hook_hits = sum(1 for term in HOOK_TERMS if term in first_20_words)
    tactical_hits = sum(1 for term in TACTICAL_TERMS if term in lower)
    conflict_hits = sum(1 for term in CONFLICT_TERMS if term in lower)
    contrarian_hits = sum(1 for term in CONTRARIAN_TERMS if term in lower)
    emotion_hits = sum(1 for term in EMOTION_TERMS if term in lower)
    question_bonus = 12 if "?" in text[:180] else 0
    quote_bonus = 12 if any(mark in text for mark in ["'", '"']) else 0
    payoff_bonus = 15 if any(term in lower for term in ["because", "so", "therefore", "that means"]) else 0
    duration_score = 85 if 20 <= duration <= 50 else 65

    mechanism_scores = {
        ClipMechanism.tactical: tactical_hits * 22,
        ClipMechanism.conflict: conflict_hits * 20,
        ClipMechanism.contrarian: contrarian_hits * 24,
        ClipMechanism.emotion: emotion_hits * 18,
        ClipMechanism.surprise: hook_hits * 14 + question_bonus,
        ClipMechanism.quote: quote_bonus,
        ClipMechanism.story: 18 if any(term in lower for term in ["then", "when i", "we were"]) else 0,
    }
    mechanism = max(mechanism_scores, key=mechanism_scores.get)

    sponsor_penalty = 25 if any(term in lower for term in SPONSOR_TERMS) else 0
    scorecard = ClipScorecard(
        hook_strength=min(100, 50 + hook_hits * 12 + question_bonus - sponsor_penalty),
        self_contained_context=min(100, 62 + payoff_bonus),
        payoff_strength=min(100, 55 + payoff_bonus + tactical_hits * 8),
        novelty_or_surprise=min(100, 45 + hook_hits * 9 + contrarian_hits * 18),
        conflict_or_tension=min(100, 40 + conflict_hits * 18 + contrarian_hits * 10),
        emotional_charge=min(100, 40 + emotion_hits * 18),
        tactical_value=min(100, 40 + tactical_hits * 20),
        quotability=min(100, 45 + quote_bonus + hook_hits * 8),
        retention_likelihood=min(100, duration_score + hook_hits * 3 + payoff_bonus // 2),
        platform_suitability=82,
        clean_boundaries=75,
    )
    return scorecard, mechanism


def first_sentence(text: str) -> str:
    match = re.search(r"(.{20,260}?[.!?])(?:\s|$)", text.strip())
    return match.group(1).strip() if match else text.strip()[:220]


def trim_text(text: str, limit: int) -> str:
    return text.strip()[:limit].rstrip()


def make_title(sentence: str) -> str:
    words = re.findall(r"\w+['\w]*", sentence)
    title = " ".join(words[:10])
    return title[:1].upper() + title[1:] if title else "Clip Lab Short"


def make_hook_text(sentence: str) -> str:
    words = re.findall(r"\w+['\w]*", sentence)
    hook = " ".join(words[:9])
    return hook.upper() if hook else "WATCH THIS"


def make_reason(scorecard: ClipScorecard, mechanism: ClipMechanism) -> str:
    return (
        f"Selected for {mechanism.value} with hook strength {scorecard.hook_strength}, "
        f"payoff {scorecard.payoff_strength}, and retention likelihood "
        f"{scorecard.retention_likelihood}."
    )


def platform_fit_for(mechanism: ClipMechanism) -> list[Platform]:
    if mechanism in {ClipMechanism.tactical, ClipMechanism.contrarian}:
        return [Platform.tiktok, Platform.reels, Platform.shorts, Platform.x, Platform.linkedin]
    return [Platform.tiktok, Platform.reels, Platform.shorts, Platform.x]


def make_caption(sentence: str) -> str:
    clean = sentence.strip().rstrip(".")
    return f"{clean}. Save this and follow for the full breakdown."


def dedupe_windows(windows: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    kept: list[tuple[float, float, str]] = []
    for start, end, text in windows:
        if any(abs(start - prior_start) < 5 for prior_start, _, _ in kept):
            continue
        kept.append((start, end, text))
    return kept
