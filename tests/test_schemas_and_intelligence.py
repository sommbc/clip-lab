from pathlib import Path

import pytest
from pydantic import ValidationError

from cliplab_captions import build_remotion_props
from cliplab_clip_intelligence import (
    ClipCritic,
    ClipGenerator,
    ClipPackager,
    FakeClipModelProvider,
    refine_candidate_boundaries,
)
from cliplab_shared import (
    ClipCandidate,
    ClipExportMetadata,
    ClipMechanism,
    FinalClip,
    NormalizedTranscript,
    Platform,
    TranscriptSegment,
    TranscriptWord,
)


def sample_transcript() -> NormalizedTranscript:
    words = []
    text = (
        "Nobody talks about the real mistake founders make. "
        "They build the workflow before they understand the customer pain. "
        "That means the product looks impressive but nobody shares it because there is no payoff. "
        "The simple fix is to write the painful sentence first, test whether people repeat it, "
        "and only then build the product around that exact demand."
    )
    t = 0.0
    for raw in text.split():
        words.append(TranscriptWord(word=raw, start=t, end=t + 0.35, speaker="SPEAKER_00"))
        t += 0.42
    return NormalizedTranscript(
        text=text,
        language="en",
        duration=max(30.0, t),
        segments=[
            TranscriptSegment(
                text=text,
                start=0.0,
                end=max(30.0, t),
                speaker="SPEAKER_00",
                words=words,
            )
        ],
    )


def strong_candidate(start: float = 0.0, end: float = 24.0) -> ClipCandidate:
    return ClipCandidate(
        title="The real founder mistake",
        start=start,
        end=end,
        viral_score=88,
        hook_text="NOBODY TALKS ABOUT THIS MISTAKE",
        hook_sentence="Nobody talks about the real mistake founders make.",
        viral_reason="Strong hook with tactical payoff.",
        dominant_mechanism=ClipMechanism.tactical,
        platform_fit=[Platform.tiktok, Platform.reels, Platform.shorts],
        suggested_caption="Save this before you build the wrong thing.",
        risk_flags=[],
    )


def test_normalized_transcript_contract_accepts_expected_payload():
    transcript = sample_transcript()
    payload = transcript.model_dump(mode="json")

    parsed = NormalizedTranscript.model_validate(payload)

    assert parsed.language == "en"
    assert parsed.words()[0].word == "Nobody"
    assert parsed.words()[0].speaker == "SPEAKER_00"


def test_normalized_transcript_rejects_raw_or_unsorted_word_payloads():
    payload = sample_transcript().model_dump(mode="json")
    payload["segments"][0]["words"][2]["start"] = 0.01

    with pytest.raises(ValidationError):
        NormalizedTranscript.model_validate(payload)

    payload = sample_transcript().model_dump(mode="json")
    payload["segments"][0]["raw_whisperx"] = {"segments": []}

    with pytest.raises(ValidationError):
        NormalizedTranscript.model_validate(payload)


def test_clip_candidate_and_final_clip_contracts_require_metadata():
    candidate = strong_candidate()
    assert candidate.viral_score == 88
    assert candidate.platform_fit == [Platform.tiktok, Platform.reels, Platform.shorts]

    with pytest.raises(ValidationError):
        ClipCandidate.model_validate(
            {
                "title": "Missing metadata",
                "start": 1,
                "end": 2,
                "viral_score": 50,
                "hook_text": "HOOK",
                "hook_sentence": "Hook.",
                "viral_reason": "Reason.",
                "dominant_mechanism": "quote",
                "platform_fit": [],
                "suggested_caption": "Caption.",
                "risk_flags": [],
            }
        )

    final_clip = FinalClip(
        **candidate.model_dump(exclude={"scorecard"}),
        id="clip_01",
        source_clip_path=Path("raw.mp4"),
        vertical_clip_path=Path("vertical.mp4"),
        render_props_path=Path("render_props/clip_01.json"),
    )
    export = ClipExportMetadata(
        source="input.mp4",
        source_video_path=Path("input.mp4"),
        transcript_path=Path("transcript.json"),
        output_dir=Path("output/job"),
        clips=[final_clip],
    )
    assert export.clips[0].hook_text == candidate.hook_text
    assert export.clips[0].duration == pytest.approx(candidate.duration)


def test_generator_and_critic_return_valid_candidates():
    transcript = sample_transcript()
    candidates = ClipGenerator().generate(transcript).candidates
    assert candidates
    refined = [refine_candidate_boundaries(transcript, candidate) for candidate in candidates]
    accepted = ClipCritic(min_score=50).review(transcript, refined)
    assert accepted
    assert accepted[0].viral_score >= 50
    assert accepted[0].hook_text


def test_fake_model_provider_runs_three_pass_intelligence():
    transcript = sample_transcript()
    provider = FakeClipModelProvider()

    candidates = ClipGenerator(model_provider=provider).generate(transcript).candidates
    accepted = ClipCritic(model_provider=provider, min_score=50).review(transcript, candidates)
    packaged = ClipPackager(model_provider=provider).package(transcript, accepted)

    assert packaged
    assert packaged[0].viral_score >= 50
    assert packaged[0].suggested_caption


def test_model_generated_display_text_is_trimmed_before_validation():
    transcript = sample_transcript()
    provider = OverlongTextModelProvider()

    generated = ClipGenerator(model_provider=provider).generate(transcript).candidates
    reviewed = ClipCritic(model_provider=provider, min_score=50).review(
        transcript, [strong_candidate()]
    )
    packaged = ClipPackager(model_provider=provider).package(transcript, [strong_candidate()])

    assert len(generated[0].hook_text) == 120
    assert len(reviewed[0].hook_text) == 120
    assert len(packaged[0].hook_text) == 120
    assert len(packaged[0].suggested_caption) == 500


def test_model_generated_extra_fields_are_dropped_and_missing_caption_is_repaired():
    transcript = sample_transcript()
    provider = ExtraFieldModelProvider()

    generated = ClipGenerator(model_provider=provider).generate(transcript).candidates
    reviewed = ClipCritic(model_provider=provider, min_score=50).review(
        transcript, [strong_candidate()]
    )
    packaged = ClipPackager(model_provider=provider).package(transcript, [strong_candidate()])

    assert generated[0].suggested_caption == "Generated hook sentence."
    assert reviewed[0].suggested_caption == "Generated hook sentence."
    assert packaged[0].suggested_caption == "Packaged hook sentence."


def test_model_generated_invalid_risk_flags_are_dropped_before_validation():
    transcript = sample_transcript()
    provider = InvalidRiskFlagModelProvider()

    generated = ClipGenerator(model_provider=provider).generate(transcript).candidates
    reviewed = ClipCritic(model_provider=provider, min_score=50).review(
        transcript, [strong_candidate()]
    )
    packaged = ClipPackager(model_provider=provider).package(transcript, [strong_candidate()])

    assert generated[0].risk_flags == []
    assert reviewed[0].risk_flags == []
    assert packaged[0].risk_flags == []


def test_packaging_model_failure_uses_deterministic_local_fallback():
    transcript = sample_transcript()
    candidate = strong_candidate().model_copy(update={"hook_text": "keep this hook"})

    packaged = ClipPackager(model_provider=FailingPackagingModelProvider()).package(
        transcript, [candidate]
    )

    assert packaged[0].hook_text == "KEEP THIS HOOK"
    assert packaged[0].suggested_caption.startswith("Watch this:")
    assert packaged[0].platform_fit == [
        Platform.tiktok,
        Platform.reels,
        Platform.shorts,
        Platform.x,
    ]
    assert packaged[0].dominant_mechanism == candidate.dominant_mechanism


def test_boundary_refinement_never_cuts_inside_word_when_words_exist():
    transcript = NormalizedTranscript(
        text="Setup. Hook starts strong. Payoff lands. Outro.",
        language="en",
        duration=4.0,
        segments=[
            TranscriptSegment(
                text="Setup. Hook starts strong. Payoff lands. Outro.",
                start=0.0,
                end=4.0,
                words=[
                    TranscriptWord(word="Setup.", start=0.82, end=1.10),
                    TranscriptWord(word="Hook", start=1.25, end=1.50),
                    TranscriptWord(word="starts", start=1.55, end=1.80),
                    TranscriptWord(word="strong.", start=1.85, end=2.10),
                    TranscriptWord(word="Payoff", start=2.20, end=2.50),
                    TranscriptWord(word="lands.", start=2.55, end=2.82),
                    TranscriptWord(word="Outro.", start=3.05, end=3.45),
                ],
            )
        ],
    )

    refined = refine_candidate_boundaries(transcript, strong_candidate(start=1.25, end=2.82))

    assert refined.start == pytest.approx(0.82)
    assert refined.end == pytest.approx(3.45)
    assert not _inside_any_word(transcript, refined.start)
    assert not _inside_any_word(transcript, refined.end)


def test_critic_rejects_weak_candidates():
    transcript = sample_transcript()
    weak = strong_candidate(end=8.0).model_copy(
        update={
            "viral_score": 40,
            "hook_text": "WELCOME BACK",
            "hook_sentence": "Welcome back.",
            "viral_reason": "Generic intro.",
        }
    )

    assert ClipCritic(min_score=68).review(transcript, [weak]) == []


def test_remotion_props_consume_normalized_transcript_words():
    transcript = sample_transcript()
    clip = strong_candidate(start=0.0, end=8.0)

    props = build_remotion_props("file:///tmp/clip.mp4", transcript, clip)

    assert props.video_url == "file:///tmp/clip.mp4"
    assert props.hook.text == clip.hook_text
    assert props.subtitles.captions
    assert props.subtitles.captions[0].text == "Nobody"
    assert props.subtitles.captions[0].startMs == 0


def _inside_any_word(transcript: NormalizedTranscript, timestamp: float) -> bool:
    return any(word.start < timestamp < word.end for word in transcript.words())


class OverlongTextModelProvider:
    name = "overlong"

    def generate_json(self, prompt: str, *, purpose: str) -> dict:
        candidate = {
            "title": "T" * 140,
            "start": 0.0,
            "end": 24.0,
            "viral_score": 88,
            "hook_text": "H" * 140,
            "hook_sentence": "S" * 280,
            "viral_reason": "R" * 820,
            "dominant_mechanism": "tactical",
            "platform_fit": ["tiktok", "reels", "shorts"],
            "suggested_caption": "C" * 520,
            "risk_flags": [],
        }
        if purpose == "candidate_mining":
            return {"candidates": [candidate]}
        if purpose == "critic_editor":
            return {"verdicts": [{"accepted": True, "candidate": candidate, "concerns": []}]}
        if purpose == "packaging":
            return {
                "packages": [
                    {
                        "candidate_id": "clip_01",
                        "title": "T" * 140,
                        "hook_text": "H" * 140,
                        "hook_sentence": "S" * 280,
                        "viral_reason": "R" * 820,
                        "platform_fit": ["tiktok", "reels", "shorts"],
                        "suggested_caption": "C" * 520,
                        "risk_flags": [],
                    }
                ]
            }
        raise AssertionError(f"unexpected purpose: {purpose}")


class ExtraFieldModelProvider:
    name = "extra-field"

    def generate_json(self, prompt: str, *, purpose: str) -> dict:
        candidate = {
            "title": "Generated clip",
            "start": 0.0,
            "end": 24.0,
            "viral_score": 88,
            "hook_text": "GENERATED HOOK",
            "hook_sentence": "Generated hook sentence.",
            "viral_reason": "Strong generated reason.",
            "dominant_mechanism": "tactical",
            "platform_fit": ["tiktok", "reels", "shorts"],
            "risk_flags": [],
            "suggested_critique": "Models may add this, but it is not part of the schema.",
        }
        if purpose == "candidate_mining":
            return {"candidates": [candidate]}
        if purpose == "critic_editor":
            return {"verdicts": [{"accepted": True, "candidate": candidate, "concerns": []}]}
        if purpose == "packaging":
            return {
                "packages": [
                    {
                        "candidate_id": "clip_01",
                        "title": "Packaged clip",
                        "hook_text": "PACKAGED HOOK",
                        "hook_sentence": "Packaged hook sentence.",
                        "viral_reason": "Strong packaged reason.",
                        "platform_fit": ["tiktok", "reels", "shorts"],
                        "risk_flags": [],
                        "suggested_critique": "Models may add this here too.",
                    }
                ]
            }
        raise AssertionError(f"unexpected purpose: {purpose}")


class InvalidRiskFlagModelProvider:
    name = "invalid-risk-flag"

    def generate_json(self, prompt: str, *, purpose: str) -> dict:
        candidate = {
            "title": "Generated clip",
            "start": 0.0,
            "end": 24.0,
            "viral_score": 88,
            "hook_text": "GENERATED HOOK",
            "hook_sentence": "Generated hook sentence.",
            "viral_reason": "Strong generated reason.",
            "dominant_mechanism": "tactical",
            "platform_fit": ["tiktok", "reels", "shorts"],
            "suggested_caption": "Generated caption.",
            "risk_flags": ["Requires context from earlier in the talk"],
        }
        if purpose == "candidate_mining":
            return {"candidates": [candidate]}
        if purpose == "critic_editor":
            return {"verdicts": [{"accepted": True, "candidate": candidate, "concerns": []}]}
        if purpose == "packaging":
            return {
                "packages": [
                    {
                        "candidate_id": "clip_01",
                        "title": "Packaged clip",
                        "hook_text": "PACKAGED HOOK",
                        "hook_sentence": "Packaged hook sentence.",
                        "viral_reason": "Strong packaged reason.",
                        "platform_fit": ["tiktok", "reels", "shorts"],
                        "suggested_caption": "Packaged caption.",
                        "risk_flags": ["Caption needs more context"],
                    }
                ]
            }
        raise AssertionError(f"unexpected purpose: {purpose}")


class FailingPackagingModelProvider:
    name = "failing-packaging"

    def generate_json(self, prompt: str, *, purpose: str) -> dict:
        raise RuntimeError("packaging unavailable")
