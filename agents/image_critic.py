"""Image Critic - 생성된 장면 이미지 정합성 검증 및 재생성 피드백"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from PIL import Image
from google import genai

from config.settings import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-pro-preview"
MAX_RETRIES = 3
BASE_RETRY_DELAY = 5
PREVIEW_MAX_SIZE = 1024
ALLOWED_SEVERITIES = {"low", "medium", "high"}
ALLOWED_ISSUE_TYPES = {
    "text_mismatch",
    "missing_key_detail",
    "character_identity",
    "continuity",
    "emotion_mismatch",
    "composition",
    "readability",
    "style_drift",
    "other",
}


def _extract_retry_seconds(err: str) -> int | None:
    m = re.search(r"Please retry in ([^.\n]+(?:\.\d+)?s)", err)
    if not m:
        return None

    text = m.group(1)
    h = re.search(r"(\d+)h", text)
    mnt = re.search(r"(\d+)m", text)
    sec = re.search(r"(\d+(?:\.\d+)?)s", text)
    total = 0.0
    if h:
        total += int(h.group(1)) * 3600
    if mnt:
        total += int(mnt.group(1)) * 60
    if sec:
        total += float(sec.group(1))
    if total <= 0:
        return None
    return int(total)


def _compute_retry_wait(attempt: int, err: str = "") -> int:
    wait = BASE_RETRY_DELAY * (2 ** max(0, attempt - 1))
    hinted = _extract_retry_seconds(err)
    if hinted:
        wait = max(wait, hinted)
    return min(wait, 600)


def _parse_json(text: str) -> dict:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return json.loads(cleaned)


def _build_scene_payload(scenes: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        payload.append(
            {
                "scene_index": idx,
                "narration": str(scene.get("narration", "")).strip(),
                "scene_outline": str(scene.get("scene_outline", "")).strip(),
                "image_intent": str(scene.get("image_intent", "")).strip(),
                "setting_hint": str(scene.get("setting_hint", "")).strip(),
                "emotion_beat": str(scene.get("emotion_beat", "")).strip(),
                "action_beat": str(scene.get("action_beat", "")).strip(),
                "cast": scene.get("cast", []),
                "continuity_state": scene.get("continuity_state", {}),
                "shot_plan": scene.get("shot_plan", {}),
                "world_context": scene.get("world_context", {}),
                "image_query": str(scene.get("image_query", "")).strip(),
            }
        )
    return payload


def _build_preview_images(image_paths: list[Path | None]) -> list[Image.Image]:
    previews: list[Image.Image] = []
    for path in image_paths:
        if path is None or not path.exists():
            raise FileNotFoundError(f"image critic input image missing: {path}")
        img = Image.open(path).convert("RGB")
        preview = img.copy()
        preview.thumbnail((PREVIEW_MAX_SIZE, PREVIEW_MAX_SIZE), Image.LANCZOS)
        img.close()
        previews.append(preview)
    return previews


def _normalize_issue_type(value: str) -> str:
    issue = str(value or "").strip().lower()
    return issue if issue in ALLOWED_ISSUE_TYPES else "other"


def _normalize_severity(value: str) -> str:
    severity = str(value or "").strip().lower()
    return severity if severity in ALLOWED_SEVERITIES else "low"


def _normalize_focus_texts(item: dict) -> list[dict]:
    raw_focus_texts = item.get("focus_texts", [])
    if not isinstance(raw_focus_texts, list):
        raw_focus_texts = []

    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw_focus_texts:
        target = ""
        text = ""
        if isinstance(entry, dict):
            target = str(entry.get("target", "")).strip()
            text = str(entry.get("text", "")).strip()
        else:
            text = str(entry).strip()
        if not text:
            continue
        key = (target, text)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"target": target, "text": text})

    return normalized


def _validate_reviews(data: dict, expected_scene_count: int) -> tuple[dict, str | None]:
    overall_feedback = str(data.get("overall_feedback", "") or data.get("overall", "")).strip()
    raw_reviews = data.get("scene_reviews")
    if not isinstance(raw_reviews, list):
        return {}, "scene_reviews is not a list"

    by_index: dict[int, dict] = {}
    for item in raw_reviews:
        if not isinstance(item, dict):
            continue
        try:
            scene_index = int(item.get("scene_index"))
        except Exception:
            scene_number = item.get("scene_number")
            if scene_number is None:
                continue
            scene_index = int(scene_number) - 1

        if scene_index < 0 or scene_index >= expected_scene_count:
            continue

        has_issue = bool(item.get("has_issue", False))
        severity = _normalize_severity(item.get("severity", "low"))
        raw_issue_types = item.get("issue_types", [])
        if not isinstance(raw_issue_types, list):
            raw_issue_types = []
        issue_types = [_normalize_issue_type(v) for v in raw_issue_types]
        if not issue_types and has_issue:
            issue_types = ["other"]

        reason = str(item.get("reason", "")).strip()
        fix_prompt = str(item.get("fix_prompt", "") or item.get("regen_prompt", "")).strip()
        focus_texts = _normalize_focus_texts(item)
        continuity_prompt = str(item.get("continuity_prompt", "")).strip()
        raw_reference_scene_indexes = item.get("reference_scene_indexes", [])
        if not isinstance(raw_reference_scene_indexes, list):
            raw_reference_scene_indexes = []
        reference_scene_indexes: list[int] = []
        for value in raw_reference_scene_indexes:
            try:
                ref_idx = int(value)
            except Exception:
                continue
            if ref_idx < 0 or ref_idx >= expected_scene_count or ref_idx == scene_index:
                continue
            if ref_idx not in reference_scene_indexes:
                reference_scene_indexes.append(ref_idx)
        needs_regen = bool(item.get("needs_regen", False))

        by_index[scene_index] = {
            "scene_index": scene_index,
            "has_issue": has_issue,
            "severity": severity,
            "issue_types": issue_types,
            "reason": reason,
            "fix_prompt": fix_prompt,
            "focus_texts": focus_texts,
            "continuity_prompt": continuity_prompt,
            "reference_scene_indexes": reference_scene_indexes,
            "needs_regen": needs_regen,
        }

    missing = [str(i) for i in range(expected_scene_count) if i not in by_index]
    if missing:
        return {}, f"missing scene reviews: {', '.join(missing)}"

    return {
        "overall_feedback": overall_feedback,
        "scene_reviews": [by_index[i] for i in range(expected_scene_count)],
    }, None


def review_scene_images(
    scenes: list[dict],
    image_paths: list[Path | None],
    research_brief: dict | None = None,
) -> dict:
    """전체 장면 이미지를 한 번에 점검하고 장면별 재생성 피드백을 반환한다."""
    if not scenes:
        return {"overall_feedback": "", "scene_reviews": []}
    if len(scenes) != len(image_paths):
        raise ValueError("image critic requires matching scenes and image_paths length")

    scene_payload = _build_scene_payload(scenes)
    previews = _build_preview_images(image_paths)
    research_context = {
        "topic": str((research_brief or {}).get("topic", "")).strip(),
        "summary": str((research_brief or {}).get("summary", "")).strip(),
        "story_type": str((research_brief or {}).get("story_type", "")).strip(),
        "source_region": str((research_brief or {}).get("source_region", "")).strip(),
        "original_title": str((research_brief or {}).get("original_title", "")).strip(),
    }

    prompt = f"""You are an image critic for Korean YouTube Shorts.
Review the generated scene images against the scene metadata and narration.
The images are provided in the same order as scene_index 0..N-1.

Goals:
- Find visual mismatches that would confuse viewers.
- Be strict about readable text in notes, signs, messages, screens, or labels when text is central to the narration.
- Also flag other weaknesses: missing key detail, wrong character/prop/location continuity, wrong emotion, weak composition, unreadable or misleading focus.
- Watch for cross-scene continuity problems where adjacent or nearby scenes no longer feel like the same person, place type, prop state, or story moment progression.
- Prefer keeping scenes unless there is a clear viewer-facing issue.

Regeneration policy:
- Set needs_regen=true only when the issue is meaningful enough to justify regenerating that scene.
- When needs_regen=true, provide fix_prompt in English for an image model.
- fix_prompt should tell the model what to correct while preserving the same story beat, character identity, key props, and location type as much as possible.
- If continuity with nearby scenes matters, include reference_scene_indexes pointing to the most useful same-episode anchor scenes.
- If continuity with nearby scenes matters, include continuity_prompt describing what should match across scenes.
- If one or more exact Korean visible texts matter, put them in focus_texts.
- Each focus_texts item should be an object with:
  - target: where the text appears (for example "reply note", "door label", "phone screen"), or empty string
  - text: exact Korean text that must appear

Research context:
{json.dumps(research_context, ensure_ascii=False, indent=2)}

Scene metadata:
{json.dumps(scene_payload, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "overall_feedback": "1-2 sentence summary",
  "scene_reviews": [
    {{
      "scene_index": 0,
      "has_issue": false,
      "severity": "low|medium|high",
      "issue_types": ["text_mismatch|missing_key_detail|character_identity|continuity|emotion_mismatch|composition|readability|style_drift|other"],
      "reason": "why this scene is fine or what is wrong",
      "fix_prompt": "English regeneration guidance for the image model, or empty string",
      "focus_texts": [
        {{
          "target": "reply note",
          "text": "저희 집은 개 안 키우는데요?"
        }}
      ],
      "continuity_prompt": "same-episode continuity instruction, or empty string",
      "reference_scene_indexes": [1, 2],
      "needs_regen": false
    }}
  ]
}}
"""

    last_error = "invalid or empty response"
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                contents = [prompt, *previews]
                response = client.models.generate_content(model=MODEL, contents=contents)
                data = _parse_json(response.text)
                validated, validation_error = _validate_reviews(data, len(scenes))
                if validation_error:
                    last_error = validation_error
                    if attempt < MAX_RETRIES:
                        wait = _compute_retry_wait(attempt, validation_error)
                        print(
                            f"  ⏳ Image Critic 재시도 대기 {wait}초 "
                            f"({attempt}/{MAX_RETRIES}) - {validation_error}"
                        )
                        time.sleep(wait)
                else:
                    return validated
            except Exception as exc:
                last_error = str(exc)
                if attempt >= MAX_RETRIES:
                    raise
                wait = _compute_retry_wait(attempt, last_error)
                print(
                    f"  ⏳ Image Critic 재시도 대기 {wait}초 "
                    f"({attempt}/{MAX_RETRIES}) - {last_error}"
                )
                time.sleep(wait)
    finally:
        for image in previews:
            try:
                image.close()
            except Exception:
                pass

    raise RuntimeError(
        f"Image critic review failed after {MAX_RETRIES} attempts. detail={last_error}"
    )
