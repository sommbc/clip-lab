from __future__ import annotations

from typing import Any


CANDIDATE_TEXT_LIMITS = {
    "title": 120,
    "hook_text": 120,
    "hook_sentence": 260,
    "viral_reason": 800,
    "suggested_caption": 500,
}
PACKAGING_TEXT_LIMITS = {
    "title": 120,
    "hook_text": 120,
    "hook_sentence": 260,
    "viral_reason": 800,
    "suggested_caption": 500,
}
CANDIDATE_FIELDS = set(CANDIDATE_TEXT_LIMITS) | {
    "start",
    "end",
    "viral_score",
    "dominant_mechanism",
    "platform_fit",
    "risk_flags",
    "scorecard",
}
PACKAGING_FIELDS = set(PACKAGING_TEXT_LIMITS) | {
    "candidate_id",
    "platform_fit",
    "risk_flags",
}
VERDICT_FIELDS = {"accepted", "candidate", "concerns", "suggested_start", "suggested_end"}
VALID_RISK_FLAGS = {
    "sponsor_read",
    "missing_context",
    "weak_hook",
    "rambling",
    "mid_sentence_boundary",
    "sensitive_claim",
    "profanity",
    "possible_copyright",
}


def repair_candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _repair_items_payload(payload, "candidates", CANDIDATE_TEXT_LIMITS)


def repair_critic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    verdicts = payload.get("verdicts")
    if not isinstance(verdicts, list):
        return payload
    repaired = dict(payload)
    repaired["verdicts"] = [
        _repair_verdict(verdict) if isinstance(verdict, dict) else verdict for verdict in verdicts
    ]
    return repaired


def repair_packaging_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _repair_items_payload(payload, "packages", PACKAGING_TEXT_LIMITS)


def _repair_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    repaired = _filter_fields(verdict, VERDICT_FIELDS)
    candidate = verdict.get("candidate")
    if not isinstance(candidate, dict):
        return repaired
    repaired["candidate"] = _repair_candidate(candidate)
    return repaired


def _repair_items_payload(
    payload: dict[str, Any],
    key: str,
    limits: dict[str, int],
) -> dict[str, Any]:
    items = payload.get(key)
    if not isinstance(items, list):
        return payload
    fields = CANDIDATE_FIELDS if key == "candidates" else PACKAGING_FIELDS
    repaired = dict(payload)
    repaired[key] = [
        _repair_item(item, fields, limits) if isinstance(item, dict) else item for item in items
    ]
    return repaired


def _repair_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return _repair_item(candidate, CANDIDATE_FIELDS, CANDIDATE_TEXT_LIMITS)


def _repair_item(
    item: dict[str, Any],
    fields: set[str],
    limits: dict[str, int],
) -> dict[str, Any]:
    repaired = _filter_fields(item, fields)
    _fill_missing_caption(repaired)
    _filter_risk_flags(repaired)
    return _repair_text_fields(repaired, limits)


def _filter_fields(item: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {field: value for field, value in item.items() if field in allowed}


def _repair_text_fields(item: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
    repaired = dict(item)
    for field, limit in limits.items():
        value = repaired.get(field)
        if isinstance(value, str) and len(value) > limit:
            repaired[field] = value.strip()[:limit].rstrip()
    return repaired


def _fill_missing_caption(item: dict[str, Any]) -> None:
    value = item.get("suggested_caption")
    if isinstance(value, str) and value.strip():
        return
    for source_field in ("hook_sentence", "hook_text", "title"):
        source_value = item.get(source_field)
        if isinstance(source_value, str) and source_value.strip():
            item["suggested_caption"] = source_value.strip()
            return


def _filter_risk_flags(item: dict[str, Any]) -> None:
    value = item.get("risk_flags")
    if not isinstance(value, list):
        return
    item["risk_flags"] = [flag for flag in value if isinstance(flag, str) and flag in VALID_RISK_FLAGS]
