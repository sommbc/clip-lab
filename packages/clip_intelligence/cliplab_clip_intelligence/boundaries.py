from __future__ import annotations

from cliplab_shared import ClipCandidate, NormalizedTranscript


def refine_candidate_boundaries(
    transcript: NormalizedTranscript,
    candidate: ClipCandidate,
    start_pad: float = 0.35,
    end_pad: float = 0.35,
) -> ClipCandidate:
    words = transcript.words()
    if not words:
        return candidate

    clip_words = [word for word in words if word.end >= candidate.start and word.start <= candidate.end]
    if not clip_words:
        return candidate

    first_word = clip_words[0]
    last_word = clip_words[-1]

    clean_start_word = first_sentence_word_before(words, first_word.start, max_backtrack=4.0)
    clean_end_word = sentence_word_after(words, last_word.end, max_forward=5.0)

    refined_start = snap_before_word(words, max(0.0, clean_start_word.start - start_pad))
    refined_end = snap_after_word(words, min(transcript.duration, clean_end_word.end + end_pad))

    if refined_end <= refined_start:
        refined_start = snap_before_word(words, max(0.0, first_word.start - start_pad))
        refined_end = snap_after_word(words, min(transcript.duration, last_word.end + end_pad))

    return candidate.model_copy(update={"start": round(refined_start, 3), "end": round(refined_end, 3)})


def first_sentence_word_before(words, start: float, max_backtrack: float):
    eligible = [word for word in words if start - max_backtrack <= word.start <= start]
    if not eligible:
        return next(word for word in words if word.start >= start)
    for index in range(len(eligible) - 1, -1, -1):
        if index == 0:
            return eligible[index]
        previous = eligible[index - 1].word
        if previous.endswith((".", "?", "!")):
            return eligible[index]
    return eligible[0]


def sentence_word_after(words, end: float, max_forward: float):
    eligible = [word for word in words if end <= word.end <= end + max_forward]
    for word in eligible:
        if word.word.endswith((".", "?", "!")):
            return word
    before_end = [word for word in words if word.end <= end]
    return before_end[-1] if before_end else words[-1]


def snap_before_word(words, timestamp: float) -> float:
    for word in words:
        if word.start < timestamp < word.end:
            return word.start
    return timestamp


def snap_after_word(words, timestamp: float) -> float:
    for word in words:
        if word.start < timestamp < word.end:
            return word.end
    return timestamp
