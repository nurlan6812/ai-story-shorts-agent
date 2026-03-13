"""Helpers for turning stored performance patterns into short prompt hints."""

from __future__ import annotations


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _winner_phrase(item: dict) -> str:
    if not isinstance(item, dict):
        return ""

    ptype = _clean_text(item.get("type"))
    key = _clean_text(item.get("key"))
    if not key:
        return ""

    if ptype == "style":
        return f"{key} tone"
    if ptype == "story_type":
        return f"{key} stories"
    if ptype == "source_region":
        return f"{key} sources"
    if ptype == "series_format":
        return f"{key} format"
    if ptype == "emotion":
        return f"{key} emotion"
    if ptype == "ending_type":
        return f"{key} endings"
    if ptype == "scene_density":
        return f"{key} scene density"
    if ptype == "topic":
        return f"{key} topics"
    return key


def _build_feedback_lines(winning_patterns: dict | None) -> list[str]:
    if not isinstance(winning_patterns, dict):
        return []

    winner_phrases = _dedupe_keep_order(
        [_winner_phrase(item) for item in winning_patterns.get("winners", [])]
    )[:3]
    avoid_items = _dedupe_keep_order(
        [_clean_text(item) for item in winning_patterns.get("avoid", [])]
    )[:2]
    prefer_items = _dedupe_keep_order(
        [_clean_text(item) for item in winning_patterns.get("recommendations", [])]
    )[:2]

    lines: list[str] = []
    if winner_phrases:
        lines.append(f"- Strong recent signals: {', '.join(winner_phrases)}")
    if avoid_items:
        lines.append(f"- Avoid: {', '.join(avoid_items)}")
    if prefer_items:
        lines.append(f"- Prefer: {', '.join(prefer_items)}")
    return lines


def build_narrator_feedback_block(winning_patterns: dict | None) -> str:
    lines = _build_feedback_lines(winning_patterns)
    if not lines:
        return ""
    return "\nRecent performance feedback (reference only):\n" + "\n".join(lines) + "\n"


def build_director_feedback_block(winning_patterns: dict | None) -> str:
    lines = _build_feedback_lines(winning_patterns)
    if not lines:
        return ""
    return "\n## 최근 성과 피드백 (참고용)\n" + "\n".join(lines) + "\n"
