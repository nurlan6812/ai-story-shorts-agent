"""유머/썰/사연 YouTube Shorts 자동 생성 파이프라인 (스타일 시스템 + Director/Critic)"""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from config.settings import (
    OUTPUT_DIR,
    UPLOAD_QUEUE_DIR,
    MAX_CRITIC_REVISIONS,
    IMAGE_WORKERS,
    YOUTUBE_DEFAULT_PRIVACY,
)
from agents.researcher import research
from agents.director import create_full_plan, create_production_plan, revise_plan
from agents.imager import generate_image_queries
from agents.narrator import generate_narration_plan, generate_series_narration_plan
from agents.speech_planner import plan_speech
from agents.critic import review_production
from src.image_source import source_image
from src.tts import run_tts
from src.image_proc import fit_to_shorts_file, create_subtitle_overlay, create_teaser_overlay
from src.video import get_bgm_for_mood
from src.effects import get_effect_path
from tools.style_manager import load_style, list_styles
from tools.scene_reference_selector import (
    select_reference_scenes,
    select_references_unified,
)
from tools.video_composer import (
    build_scene_clip,
    build_silent_scene_clip,
    add_effect_to_clip,
    concat_with_transitions,
    add_bgm as compose_bgm,
    normalize_audio,
)

# --compare 모드에서 사용할 스타일
COMPARE_STYLES = ["casual", "storytelling", "darkcomedy", "absurdist"]
SERIES_TAG_RE = re.compile(r"\[\s*\d+\s*/\s*\d+\s*\]")
SERIES_PART_RE = re.compile(r"\b\d+\s*편\b")
COMMUNITY_SOURCE_RE = re.compile(
    r"(?:네이트\s*판|네이트판|블라인드|팀블라인드|디시인사이드|디시|더쿠|에브리타임|에타|"
    r"루리웹|웃긴대학|웃대|보배드림|인스티즈|맘카페|다음카페|dcinside|dc)",
    re.IGNORECASE,
)
GENERIC_SOURCE_TITLE_RE = re.compile(
    r"^(?:레전드|(?:레전드\s*)?(?:썰|사연|후기|실화|모음))(?:\s*모음)?$"
)
AUTO_PUBLISH_HOURS = (6, 12, 18)
AUTO_PUBLISH_MINUTE = 30
KST = timezone(timedelta(hours=9))


def _safe_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자 제거 (이모지, 특수문자)"""
    cleaned = re.sub(r'[^\w\s가-힣a-zA-Z0-9\-]', '', name)
    return cleaned.strip()[:80]


def _normalize_fingerprint_text(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _strip_community_source_label(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    cleaned = COMMUNITY_SOURCE_RE.sub("", raw)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -:|/[]()")

    if COMMUNITY_SOURCE_RE.search(raw):
        cleaned = re.sub(r"^(?:레전드\s*)?(?:썰|사연|후기|실화|모음)\b", "", cleaned).strip(" -:|/[]()")
        cleaned = re.sub(r"\b(?:레전드\s*)?(?:썰|사연|후기|실화|모음)$", "", cleaned).strip(" -:|/[]()")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return cleaned


def _is_generic_source_title(text: str) -> bool:
    normalized = str(text or "").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return bool(GENERIC_SOURCE_TITLE_RE.fullmatch(normalized))


def _sanitize_public_titles(script: dict) -> dict:
    if not isinstance(script, dict):
        return script

    title_raw = str(script.get("title", "")).strip()
    subtitle_raw = str(script.get("subtitle", "")).strip()
    summary_raw = str(script.get("summary", "")).strip()

    title = _strip_community_source_label(title_raw)
    subtitle = _strip_community_source_label(subtitle_raw)
    summary = _strip_community_source_label(summary_raw)

    first_scene = ""
    scenes = script.get("scenes", [])
    if isinstance(scenes, list) and scenes:
        first = scenes[0]
        if isinstance(first, dict):
            first_scene = str(first.get("narration", "")).strip()
    first_scene = _strip_community_source_label(first_scene)

    if not title or _is_generic_source_title(title):
        fallback = summary or first_scene or "무제"
        fallback = re.sub(r"[.!?~]+$", "", fallback).strip()
        title = fallback[:12].strip() or "무제"

    if _is_generic_source_title(subtitle):
        subtitle = ""
    if _is_generic_source_title(summary):
        summary = ""

    script["title"] = title or title_raw
    script["subtitle"] = subtitle
    script["summary"] = summary
    return script


def _compute_source_fingerprint(research_brief: dict | None) -> str | None:
    if not isinstance(research_brief, dict):
        return None
    parts = [
        _normalize_fingerprint_text(research_brief.get("source_region", "")),
        _normalize_fingerprint_text(research_brief.get("original_title", "")),
        _normalize_fingerprint_text(research_brief.get("original_story", "")),
    ]
    joined = " || ".join(p for p in parts if p)
    if not joined:
        return None
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _detect_ending_type(script: dict, series_part: int | None, series_total: int | None) -> str:
    if series_part and series_total and series_part < series_total:
        return "cliffhanger"

    last_narration = ""
    scenes = script.get("scenes", []) if isinstance(script, dict) else []
    if isinstance(scenes, list) and scenes:
        last = scenes[-1]
        if isinstance(last, dict):
            last_narration = str(last.get("narration", "")).strip()

    if any(token in last_narration for token in ("그날 이후", "이후로", "결국", "그 뒤로")):
        return "aftershock"
    return "payoff"


def _next_publish_slot(after_kst: datetime, step: int = 0) -> datetime:
    slots = [
        after_kst.replace(
            hour=hour,
            minute=AUTO_PUBLISH_MINUTE,
            second=0,
            microsecond=0,
        )
        for hour in AUTO_PUBLISH_HOURS
    ]
    future = [slot for slot in slots if slot > after_kst]
    if not future:
        base = (after_kst + timedelta(days=1)).replace(
            hour=AUTO_PUBLISH_HOURS[0],
            minute=AUTO_PUBLISH_MINUTE,
            second=0,
            microsecond=0,
        )
        future = [base]
    slot = future[0]
    if step <= 0:
        return slot
    current = slot
    for _ in range(step):
        current = _next_publish_slot(current + timedelta(minutes=1))
    return current


def _build_video_record_fields(
    metadata: dict,
    publish_status: str,
    trigger_source: str,
    publish_after: str | None = None,
) -> dict:
    research_brief = metadata.get("research_brief") if isinstance(metadata, dict) else {}
    production_plan = metadata.get("production_plan") if isinstance(metadata, dict) else {}
    is_series = bool(metadata.get("series_total") and int(metadata.get("series_total") or 0) > 1)
    scene_count = None
    if isinstance(production_plan, dict):
        scenes = production_plan.get("scenes", [])
        if isinstance(scenes, list):
            scene_count = len(scenes)

    return {
        "title": metadata.get("title", "YouTube Shorts"),
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "style": metadata.get("style", ""),
        "bgm_mood": metadata.get("bgm_mood", ""),
        "summary": metadata.get("summary", ""),
        "generation_status": metadata.get("generation_status", "generated"),
        "publish_status": publish_status,
        "is_series": is_series,
        "series_group_id": metadata.get("series_group_id"),
        "series_title": metadata.get("series_title") or metadata.get("title", ""),
        "part_number": metadata.get("series_part"),
        "part_count": metadata.get("series_total"),
        "publish_after": publish_after or metadata.get("publish_after"),
        "source_fingerprint": metadata.get("source_fingerprint"),
        "story_type": research_brief.get("story_type") if isinstance(research_brief, dict) else None,
        "source_region": research_brief.get("source_region") if isinstance(research_brief, dict) else None,
        "scene_count": scene_count,
        "ending_type": metadata.get("ending_type"),
        "trigger_source": trigger_source,
        "production_plan": production_plan,
        "research_brief": research_brief,
    }


def _register_generated_video(
    metadata: dict,
    publish_status: str,
    trigger_source: str,
    publish_after: str | None = None,
) -> dict | None:
    from tools.supabase_client import insert_video, update_video

    payload = _build_video_record_fields(
        metadata=metadata,
        publish_status=publish_status,
        trigger_source=trigger_source,
        publish_after=publish_after,
    )
    video_id = str(metadata.get("video_id", "")).strip()
    if video_id:
        record = update_video(video_id, **payload)
    else:
        record = insert_video(**payload)
        if record and record.get("id"):
            metadata["video_id"] = record["id"]
    if publish_after:
        metadata["publish_after"] = publish_after
    metadata["publish_status"] = publish_status
    return record


def _find_recent_duplicate_story(research_brief: dict, days: int = 45) -> dict | None:
    from tools.supabase_client import find_recent_video_by_source_fingerprint

    fingerprint = _compute_source_fingerprint(research_brief)
    if not fingerprint:
        return None
    return find_recent_video_by_source_fingerprint(fingerprint, days=days)


def _sanitize_plan(plan: dict) -> dict:
    """프로덕션 플랜에서 실제 런타임 사용 필드만 유지"""
    allowed_top = {
        "style",
        "bgm_mood",
        "title",
        "subtitle",
        "description",
        "summary",
        "tags",
        "series_part",
        "series_total",
        "characters",
        "scenes",
    }
    allowed_scene = {
        "scene_outline",
        "image_intent",
        "setting_hint",
        "emotion_beat",
        "action_beat",
        "cast",
        "character_beats",
        "continuity_state",
        "shot_plan",
        "world_context",
        "narration",
        "image_query",
        "effect",
        "camera",
        "transition",
    }
    allowed_camera = {"type", "speed"}
    allowed_character_beat = {
        "name",
        "emotion",
        "intensity",
        "facial_expression",
        "pose",
        "gaze_target",
        "visual_cue",
    }
    allowed_continuity_state = {"location_id", "time_of_day", "wardrobe_state", "prop_state"}
    allowed_shot_plan = {"shot_type", "camera_angle", "composition"}
    allowed_world_context = {"source_region", "era_hint", "cultural_markers"}
    allowed_character = {"name", "description", "role"}

    sanitized = {k: v for k, v in plan.items() if k in allowed_top}

    scenes = sanitized.get("scenes", [])
    if isinstance(scenes, list):
        normalized_scenes = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            s = {k: v for k, v in scene.items() if k in allowed_scene}

            # Legacy compatibility: old plans may store angle under camera.angle.
            legacy_camera = scene.get("camera")
            shot_plan = s.get("shot_plan")
            if not isinstance(shot_plan, dict):
                shot_plan = {}
            if isinstance(legacy_camera, dict):
                legacy_angle = str(legacy_camera.get("angle", "")).strip()
                if legacy_angle and not str(shot_plan.get("camera_angle", "")).strip():
                    shot_plan["camera_angle"] = legacy_angle
            if shot_plan:
                s["shot_plan"] = shot_plan

            cam = s.get("camera")
            if isinstance(cam, dict):
                s["camera"] = {k: v for k, v in cam.items() if k in allowed_camera}

            character_beats = s.get("character_beats")
            if isinstance(character_beats, list):
                s["character_beats"] = [
                    {k: v for k, v in beat.items() if k in allowed_character_beat}
                    for beat in character_beats
                    if isinstance(beat, dict)
                ]

            cast = s.get("cast")
            if isinstance(cast, list):
                s["cast"] = [str(name).strip() for name in cast if str(name).strip()]

            continuity_state = s.get("continuity_state")
            if isinstance(continuity_state, dict):
                s["continuity_state"] = {
                    k: v for k, v in continuity_state.items() if k in allowed_continuity_state
                }

            shot_plan = s.get("shot_plan")
            if isinstance(shot_plan, dict):
                s["shot_plan"] = {k: v for k, v in shot_plan.items() if k in allowed_shot_plan}

            world_context = s.get("world_context")
            if isinstance(world_context, dict):
                wc = {k: v for k, v in world_context.items() if k in allowed_world_context}
                source_region = str(wc.get("source_region", "")).strip()
                if source_region and source_region not in {"한국", "외국"}:
                    wc["source_region"] = "한국"
                markers = wc.get("cultural_markers")
                if isinstance(markers, list):
                    wc["cultural_markers"] = [str(m) for m in markers if str(m).strip()]
                s["world_context"] = wc
            normalized_scenes.append(s)
        sanitized["scenes"] = normalized_scenes

    chars = sanitized.get("characters", [])
    if isinstance(chars, list):
        sanitized["characters"] = [
            {k: v for k, v in c.items() if k in allowed_character}
            for c in chars if isinstance(c, dict)
        ]

    return sanitized


def _apply_narration_seed(plan: dict, narration_seed: list[dict] | None) -> dict:
    """나레이터 선행 시드가 있으면 scene 수/순서/핵심 narration을 고정한다."""
    if not narration_seed or not isinstance(plan, dict):
        return plan

    seed_items = [s for s in narration_seed if isinstance(s, dict)]
    if not seed_items:
        return plan

    scenes = plan.get("scenes")
    if not isinstance(scenes, list):
        scenes = []

    target_len = len(seed_items)
    normalized = list(scenes[:target_len])
    while len(normalized) < target_len:
        normalized.append({})

    for i, seed in enumerate(seed_items):
        cur = normalized[i] if isinstance(normalized[i], dict) else {}
        # 나레이션은 선행 생성 결과를 최우선으로 유지
        narration = str(seed.get("narration", "")).strip()
        if narration:
            cur["narration"] = narration

        # director가 비운 필드는 시드로 보강
        for key in ("scene_outline", "image_intent", "setting_hint", "emotion_beat", "action_beat"):
            if str(cur.get(key, "")).strip():
                continue
            seeded = str(seed.get(key, "")).strip()
            if seeded:
                cur[key] = seeded
        normalized[i] = cur

    plan["scenes"] = normalized
    return plan


def _normalize_research_brief(research_brief: dict) -> dict:
    """리서치 브리프 정규화 (필드 형식 보정)"""
    if not isinstance(research_brief, dict):
        return {}

    normalized = dict(research_brief)
    region = normalized.get("source_region")
    mapping = {"domestic": "한국", "overseas": "외국", "한국": "한국", "외국": "외국"}
    normalized["source_region"] = mapping.get(region, "한국")

    # 내부 파이프라인은 원문 중심으로 동작: story_points 의존 제거
    normalized.pop("story_points", None)
    normalized.pop("summary", None)

    # 시리즈 파트 호환: 이전 포맷(story_points)도 part_focus로 변환
    raw_parts = normalized.get("series_parts")
    if isinstance(raw_parts, list):
        converted_parts = []
        for idx, part in enumerate(raw_parts, start=1):
            if not isinstance(part, dict):
                continue
            p = dict(part)
            if not str(p.get("part_focus", "")).strip():
                points = p.get("story_points")
                if isinstance(points, list):
                    cleaned = [str(x).strip() for x in points if str(x).strip()]
                    if cleaned:
                        p["part_focus"] = " / ".join(cleaned[:3])
            p.pop("story_points", None)
            if not isinstance(p.get("part"), int):
                p["part"] = idx
            converted_parts.append(p)
        normalized["series_parts"] = converted_parts

    raw_chars = normalized.get("series_characters")
    if isinstance(raw_chars, list):
        converted_chars = []
        seen_names: set[str] = set()
        for char in raw_chars:
            if not isinstance(char, dict):
                continue
            name = str(char.get("name", "")).strip()
            desc = str(char.get("description", "")).strip()
            role = str(char.get("role", "supporting")).strip().lower() or "supporting"
            if not name or not desc:
                continue
            key = name.lower()
            if key in seen_names:
                continue
            if role not in {"protagonist", "antagonist", "supporting"}:
                role = "supporting"
            converted_chars.append(
                {
                    "name": name,
                    "description": desc,
                    "role": role,
                }
            )
            seen_names.add(key)
        normalized["series_characters"] = converted_chars

    return normalized


def _merge_character_pools(
    primary: list[dict] | None,
    secondary: list[dict] | None,
) -> list[dict]:
    """primary를 우선으로 하고 secondary의 추가 인물만 뒤에 붙인다."""
    merged: list[dict] = []
    seen: set[str] = set()

    for pool in (primary or [], secondary or []):
        if not isinstance(pool, list):
            continue
        for source in pool:
            if not isinstance(source, dict):
                continue
            name = str(source.get("name", "")).strip()
            desc = str(source.get("description", "")).strip()
            role = str(source.get("role", "supporting")).strip().lower() or "supporting"
            if not name or not desc:
                continue
            key = name.lower()
            if key in seen:
                continue
            if role not in {"protagonist", "antagonist", "supporting"}:
                role = "supporting"
            merged.append(
                {
                    "name": name,
                    "description": desc,
                    "role": role,
                }
            )
            seen.add(key)

    return merged


def _normalize_series_title_subtitle(
    script: dict,
    series_part: int | None,
    series_total: int | None,
    series_title_fixed: str | None = None,
    series_subtitle_base_fixed: str | None = None,
) -> dict:
    """시리즈 표기 규칙 정규화: title은 본문만, subtitle은 '시리즈명 N편'"""
    if not isinstance(script, dict):
        return script

    title = str(script.get("title", "")).strip()
    subtitle = str(script.get("subtitle", "")).strip()

    if series_part and series_total:
        if title:
            title = SERIES_TAG_RE.sub("", title).strip()
            title = re.sub(r"\s{2,}", " ", title)
        if series_title_fixed:
            title = str(series_title_fixed).strip() or title
        script["title"] = title

        subtitle_clean = SERIES_TAG_RE.sub("", subtitle).strip()
        subtitle_clean = SERIES_PART_RE.sub("", subtitle_clean).strip()
        series_name = (
            str(series_subtitle_base_fixed).strip()
            if series_subtitle_base_fixed
            else (subtitle_clean or script.get("title", ""))
        )
        if series_name in {"시리즈", "series", "Series"}:
            series_name = script.get("title", "") or series_name
        if not series_name:
            series_name = script.get("title", "") or "무제"
        script["subtitle"] = f"{series_name} {series_part}편".strip()

    return script


def _build_youtube_upload_title(metadata: dict) -> str:
    """유튜브 업로드용 제목 구성.

    렌더 title/subtitle는 유지하고, 시리즈인 경우 업로드 제목에만 [N/M] 표기를 붙인다.
    """
    base_title = str(metadata.get("title", "")).strip() or "YouTube Shorts"
    series_part = metadata.get("series_part")
    series_total = metadata.get("series_total")

    if not (series_part and series_total and int(series_total) > 1):
        return base_title

    clean_title = SERIES_TAG_RE.sub("", base_title).strip()
    clean_title = SERIES_PART_RE.sub("", clean_title).strip()
    clean_title = clean_title or base_title
    return f"{clean_title} [{series_part}/{series_total}]".strip()


def _build_image_query(base_query: str, style: dict) -> str:
    """스타일의 image.prompt_prefix/suffix를 이미지 쿼리에 결합 (중복 방지)"""
    image_cfg = style.get("image", {})
    prefix = str(image_cfg.get("prompt_prefix", "")).strip()
    suffix = str(image_cfg.get("prompt_suffix", "")).strip()
    base = str(base_query).strip()

    parts = []
    base_l = base.lower()
    if prefix and prefix.lower() not in base_l:
        parts.append(prefix)
    parts.append(base)
    if suffix and suffix.lower() not in base_l:
        parts.append(suffix)
    parts.append("If signage or labels are needed, use only short, correct, clearly legible Korean text.")

    return ", ".join(parts)


def _build_character_profile_hint(
    characters: list[dict] | None,
    cast: list[str] | None = None,
) -> str:
    """장면 이미지 프롬프트에 덧붙일 캐릭터 프로필 힌트 생성"""
    if not characters:
        return ""

    cast_set = {str(name).strip().lower() for name in (cast or []) if str(name).strip()}

    profiles = []
    for c in characters:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        desc = str(c.get("description", "")).strip()
        if not name or not desc:
            continue
        if cast_set and name.lower() not in cast_set:
            continue
        profiles.append(f"{name}: {desc}")

    if not profiles:
        return ""

    joined = " | ".join(profiles)
    return (
        " Keep character identity consistent across scenes. "
        f"Character profiles: {joined}. "
        "If a character appears in this scene, use that exact name and profile cues."
    )


def _humanize_state_token(value: str) -> str:
    text = str(value or "").strip().replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _build_scene_continuity_hint(scene: dict) -> str:
    """scene별 복장/소품 상태를 최종 이미지 프롬프트에 다시 주입."""
    if not isinstance(scene, dict):
        return ""

    continuity = scene.get("continuity_state", {})
    if not isinstance(continuity, dict):
        return ""

    wardrobe = _humanize_state_token(continuity.get("wardrobe_state", ""))
    prop_state = _humanize_state_token(continuity.get("prop_state", ""))

    hints = []
    if wardrobe and wardrobe.lower() not in {"none", "same"}:
        hints.append(f"scene wardrobe/state: {wardrobe}")
    if prop_state and prop_state.lower() not in {"none", "same"}:
        hints.append(f"scene prop/state: {prop_state}")

    if not hints:
        return ""

    return (
        " Scene-specific continuity cues: "
        + "; ".join(hints)
        + ". Reflect these cues in visible clothing/props for this scene."
    )


def _build_reference_role_hint(
    reference_scene_indexes: list[int],
    previous_part_scene_indexes: list[int],
    has_character_sheet: bool,
) -> str:
    """참조 이미지 역할을 명시하는 힌트 생성"""
    has_prev_part_refs = bool(previous_part_scene_indexes)
    has_current_refs = bool(reference_scene_indexes)

    if not has_current_refs and not has_prev_part_refs and not has_character_sheet:
        return ""

    parts = []
    if has_character_sheet:
        parts.append("character sheet (identity anchor)")
    if has_prev_part_refs:
        prev_refs = ", ".join(str(i + 1) for i in previous_part_scene_indexes)
        parts.append(f"previous-episode scenes #{prev_refs} (cross-episode continuity)")
    if has_current_refs:
        refs = ", ".join(str(i + 1) for i in reference_scene_indexes)
        parts.append(f"previous scenes in this episode #{refs} (in-episode continuity)")

    order_desc = "; ".join(parts)
    return (
        f" Reference image order: {order_desc}. "
        "Use anchors for identity/continuity only and generate a new current-scene moment."
    )


def _build_reference_notes_hint(
    reference_scene_indexes: list[int],
    reference_notes: dict[int, str] | None,
) -> str:
    """참조 장면 요약 노트를 프롬프트에 추가"""
    if not reference_scene_indexes:
        return ""
    notes = reference_notes or {}
    lines = []
    for idx in reference_scene_indexes:
        note = str(notes.get(idx, "")).strip()
        if note:
            lines.append(f"Previous scene #{idx + 1}: {note}")
    if not lines:
        return ""
    return " " + " ".join(lines)


def _build_previous_part_notes_hint(
    reference_scene_indexes: list[int],
    reference_notes: dict[int, str] | None,
) -> str:
    """전편 참조 장면 요약 노트를 프롬프트에 추가"""
    if not reference_scene_indexes:
        return ""
    notes = reference_notes or {}
    lines = []
    for idx in reference_scene_indexes:
        note = str(notes.get(idx, "")).strip()
        if note:
            lines.append(f"Previous episode scene #{idx + 1}: {note}")
    if not lines:
        return ""
    return " " + " ".join(lines)


def _collect_scene_image_map(raw_images_dir: Path) -> dict[int, Path]:
    """scene_XX.jpg 파일을 인덱스 맵으로 수집"""
    image_map: dict[int, Path] = {}
    if not raw_images_dir.exists():
        return image_map

    for p in sorted(raw_images_dir.glob("scene_*.jpg")):
        m = re.match(r"scene_(\d+)\.jpg$", p.name)
        if not m:
            continue
        idx = int(m.group(1))
        image_map[idx] = p
    return image_map


# ============================================================
# Director + Critic 루프
# ============================================================

def _generate_plan_with_critic(
    research_brief: dict,
    style: dict | None,
    work_dir: Path,
    no_critic: bool = False,
    winning_patterns: dict | None = None,
    series_parts: list[dict] | None = None,
    current_part: int | None = None,
    narration_seed: list[dict] | None = None,
    fixed_bgm_mood: str | None = None,
) -> dict:
    """Director → Critic 검증 루프 (최대 MAX_CRITIC_REVISIONS회)

    style=None이면 create_full_plan (호환용 경로)
    style이 있으면 create_production_plan (지정 스타일로 구조/씬 생성)

    Returns:
        승인된 production plan dict
    """
    series_total = len(series_parts) if series_parts else None
    part_label = f" (Part {current_part}/{series_total})" if current_part else ""
    print(f"  [Director] 프로덕션 플랜 생성 중...{part_label}")
    if style is None:
        plan = create_full_plan(
            research_brief,
            winning_patterns=winning_patterns,
            series_parts=series_parts,
            current_part=current_part,
            narration_seed=narration_seed,
        )
    else:
        plan = create_production_plan(
            research_brief,
            style,
            winning_patterns=winning_patterns,
            series_parts=series_parts,
            current_part=current_part,
            narration_seed=narration_seed,
            fixed_bgm_mood=fixed_bgm_mood,
        )
    plan = _sanitize_plan(plan)
    plan = _apply_narration_seed(plan, narration_seed)
    if style and isinstance(style, dict):
        fixed_style_name = str(style.get("name", "")).strip()
        if fixed_style_name:
            plan["style"] = fixed_style_name
    if fixed_bgm_mood:
        plan["bgm_mood"] = fixed_bgm_mood

    (work_dir / "production_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2)
    )
    print(f"  -> 제목: {plan.get('title', '?')}")
    print(f"  -> 장면 수: {len(plan.get('scenes', []))}")

    if no_critic:
        print("  [Critic] 건너뜀 (--no-critic)")
        return plan

    for revision in range(MAX_CRITIC_REVISIONS):
        print(f"  [Critic] 리뷰 중... (라운드 {revision + 1})")
        review = review_production(research_brief, plan)
        score = review.get("score", 0)
        approved = review.get("approved", False)
        print(f"  -> 점수: {score}/100, 승인: {'✅' if approved else '❌'}")
        print(f"  -> 피드백: {review.get('feedback', '')}")

        if approved:
            return plan

        # 수정 요청
        notes = review.get("revision_notes", [])
        for note in notes:
            print(f"    - {note}")

        print(f"  [Director] 플랜 수정 중... (리비전 #{revision + 1})")
        plan = revise_plan(
            plan,
            notes,
            is_series_mode=bool(series_parts and current_part),
        )
        plan = _sanitize_plan(plan)
        plan = _apply_narration_seed(plan, narration_seed)
        if style and isinstance(style, dict):
            fixed_style_name = str(style.get("name", "")).strip()
            if fixed_style_name:
                plan["style"] = fixed_style_name
        if fixed_bgm_mood:
            plan["bgm_mood"] = fixed_bgm_mood
        (work_dir / f"production_plan_rev{revision + 1}.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2)
        )

    print("  ⚠️ 최대 수정 횟수 도달, 현재 플랜으로 진행")
    return plan


# ============================================================
# 캐릭터 시트 생성
# ============================================================

def _generate_character_sheet(characters: list[dict], style: dict, work_dir: Path):
    """캐릭터 레퍼런스 시트 생성 → PIL Image 반환 (실패 시 None)"""
    from src.image_source import generate_character_sheet
    if not characters:
        return None
    print(f"  -> 캐릭터 시트 생성 중... ({len(characters)}명)")
    sheet_path = work_dir / "character_sheet.png"
    result = generate_character_sheet(characters, style, sheet_path)
    if result and result.exists():
        print(f"  -> 캐릭터 시트 완료: {sheet_path.name}")
        return Image.open(result)
    print("  ⚠️ 캐릭터 시트 실패, 텍스트 전용 모드")
    return None


# ============================================================
# 이미지 소싱 (순차/병렬)
# ============================================================

def _source_scene_images(
    scenes: list[dict],
    raw_images_dir: Path,
    style: dict | None = None,
    styled_queries: bool = False,
    character_sheet_image: "Image.Image | None" = None,
    characters: list[dict] | None = None,
    use_prev_scene_reference: bool = False,
    reference_scene_map: dict[int, list[int]] | None = None,
    reference_scene_notes_map: dict[int, dict[int, str]] | None = None,
    previous_part_reference_map: dict[int, list[int]] | None = None,
    previous_part_reference_notes_map: dict[int, dict[int, str]] | None = None,
    previous_part_image_map: dict[int, Path] | None = None,
) -> list[Path | None]:
    """장면별 이미지 소싱.

    - use_prev_scene_reference=True: 순차 생성
    - use_prev_scene_reference=False: 병렬 생성(ThreadPoolExecutor)
    """
    raw_images_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path | None] = [None] * len(scenes)
    max_reference_images = 3

    def _fetch(i: int, scene: dict) -> tuple[int, Path | None]:
        query = scene.get("image_query") or scene.get("scene_outline", "")
        if styled_queries and style:
            query = _build_image_query(query, style)
        scene_cast = scene.get("cast", [])
        # 캐릭터 식별(누가 누구인지) 강화를 위해 cast 기반 프로필 힌트는 항상 부착
        query = query + _build_character_profile_hint(characters, cast=scene_cast)
        query = query + _build_scene_continuity_hint(scene)

        # in-episode 참조는 LLM 선택 결과만 사용
        selected_refs: list[int] = []
        if i >= 1 and reference_scene_map and i in reference_scene_map:
            selected_refs = [r for r in reference_scene_map.get(i, []) if isinstance(r, int) and r < i]

        selected_prev_part_refs: list[int] = []
        if previous_part_reference_map and i in previous_part_reference_map:
            selected_prev_part_refs = [
                r for r in previous_part_reference_map.get(i, [])
                if isinstance(r, int) and previous_part_image_map and r in previous_part_image_map
            ]

        query = query + _build_reference_role_hint(
            reference_scene_indexes=selected_refs,
            previous_part_scene_indexes=selected_prev_part_refs,
            has_character_sheet=character_sheet_image is not None,
        )
        notes_for_scene = reference_scene_notes_map.get(i, {}) if reference_scene_notes_map else {}
        query = query + _build_reference_notes_hint(
            reference_scene_indexes=selected_refs,
            reference_notes=notes_for_scene,
        )
        prev_notes_for_scene = (
            previous_part_reference_notes_map.get(i, {})
            if previous_part_reference_notes_map else {}
        )
        query = query + _build_previous_part_notes_hint(
            reference_scene_indexes=selected_prev_part_refs,
            reference_notes=prev_notes_for_scene,
        )

        refs = []
        opened_refs = []
        if character_sheet_image is not None:
            refs.append(character_sheet_image)
        for ref_idx in selected_prev_part_refs:
            if len(refs) >= max_reference_images:
                break
            try:
                if previous_part_image_map and ref_idx in previous_part_image_map:
                    prev_img = Image.open(previous_part_image_map[ref_idx])
                    refs.append(prev_img)
                    opened_refs.append(prev_img)
            except Exception:
                pass
        for ref_idx in selected_refs:
            if len(refs) >= max_reference_images:
                break
            if ref_idx < len(results) and results[ref_idx]:
                try:
                    in_episode_img = Image.open(results[ref_idx])
                    refs.append(in_episode_img)
                    opened_refs.append(in_episode_img)
                except Exception:
                    pass
        img_path = source_image(
            query,
            raw_images_dir / f"scene_{i:02d}.jpg",
            style=style,
            reference_images=refs if refs else None,
        )
        for im in opened_refs:
            try:
                im.close()
            except Exception:
                pass
        return i, img_path

    # 이전 장면 참조를 사용하면 순차 생성으로 연속성 보장
    if use_prev_scene_reference:
        for i, s in enumerate(scenes):
            i, img_path = _fetch(i, s)
            scene_label = scenes[i].get("image_query") or scenes[i].get("scene_outline", "")
            if img_path is None:
                print(f"  [!] 장면 {i + 1} 이미지 실패: '{scene_label}'")
            else:
                print(f"  -> 장면 {i + 1}: '{scene_label}' ✅")
            results[i] = img_path
    else:
        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
            futures = {pool.submit(_fetch, i, s): i for i, s in enumerate(scenes)}
            for fut in as_completed(futures):
                i, img_path = fut.result()
                scene_label = scenes[i].get("image_query") or scenes[i].get("scene_outline", "")
                if img_path is None:
                    print(f"  [!] 장면 {i + 1} 이미지 실패: '{scene_label}'")
                else:
                    print(f"  -> 장면 {i + 1}: '{scene_label}' ✅")
                results[i] = img_path

    # 실패한 장면은 직전 성공 이미지로 폴백
    for i in range(len(results)):
        if results[i] is None:
            results[i] = results[i - 1] if i > 0 and results[i - 1] else None

    return results


# ============================================================
# 이미지 가공 (배경/오버레이 분리)
# ============================================================

def _process_scenes_with_style(
    scenes: list[dict],
    raw_images: list[Path | None],
    style: dict,
    title: str,
    subtitle: str,
    date_str: str,
    processed_dir: Path,
) -> tuple[list[Path], list[Path | None]]:
    """스타일 적용: fit_to_shorts + overlay 생성 (분리 반환)"""
    bg_images: list[Path] = []
    overlay_images: list[Path | None] = []

    bg_dir = processed_dir / "bg"
    overlay_dir = processed_dir / "overlay"

    for i, (scene, raw_img) in enumerate(zip(scenes, raw_images)):
        if raw_img is None:
            continue

        # 1) 배경 이미지
        bg_path = bg_dir / f"scene_{i:02d}_bg.png"
        fit_to_shorts_file(raw_img, bg_path, style=style)
        bg_images.append(bg_path)

        # 2) 텍스트 오버레이 (투명 PNG)
        overlay_path = overlay_dir / f"scene_{i:02d}_overlay.png"
        try:
            create_subtitle_overlay(
                output_path=overlay_path,
                style=style,
                title=title,
                subtitle_text=subtitle,
                narration=scene.get("narration", ""),
                date_str=date_str,
            )
            overlay_images.append(overlay_path if overlay_path.exists() else None)
        except Exception as e:
            print(f"  ⚠️ 장면 {i + 1} 오버레이 생성 실패: {e}")
            overlay_images.append(None)

        print(f"  -> 장면 {i + 1} 가공 완료")

    return bg_images, overlay_images


# ============================================================
# 영상 합성 (카메라 효과 + 전환 + 볼륨 정규화 + BGM)
# ============================================================

def _compose_video(
    scenes: list[dict],
    bg_images: list[Path],
    overlay_images: list[Path | None],
    tts_results: list[dict],
    style: dict,
    output_path: Path,
    bgm_path: Path | None = None,
    teaser_card: dict | None = None,
) -> Path:
    """video_composer 기반 영상 합성"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clips_dir = output_path.parent / "clips"
    clips_dir.mkdir(exist_ok=True)

    scene_clips: list[Path | None] = [None] * len(scenes)

    def _build_one(i: int) -> tuple[int, Path]:
        scene = scenes[i]
        bg_path = bg_images[i]
        tts = tts_results[i]
        audio_path = Path(tts["audio_path"])

        # 1) 오디오 피크 정규화
        norm_audio = clips_dir / f"scene_{i:02d}_norm.wav"
        normalize_audio(audio_path, norm_audio)

        # 2) 장면 클립 (카메라 효과 + 오버레이 분리 합성)
        clip_path = clips_dir / f"scene_{i:02d}.mp4"
        camera = scene.get("camera", {"type": "zoom_in", "speed": "slow"})
        overlay = overlay_images[i] if i < len(overlay_images) else None

        build_scene_clip(
            image_path=bg_path,
            audio_path=norm_audio,
            output_path=clip_path,
            camera=camera,
            style=style,
            overlay_path=overlay,
        )

        # 3) 효과음 믹싱
        effect_type = scene.get("effect")
        if effect_type and effect_type != "null":
            effect_path = get_effect_path(effect_type)
            if effect_path:
                fx_clip = clips_dir / f"scene_{i:02d}_fx.mp4"
                effect_vol = style.get("audio", {}).get("effect_volume", 0.7)
                add_effect_to_clip(clip_path, effect_path, fx_clip, effect_vol)
                clip_path = fx_clip

        cam_type = camera.get("type", "static")
        print(f"  -> 장면 {i + 1}: {cam_type}" + (f" + {effect_type}" if effect_type else ""))
        return i, clip_path

    with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
        futures = {pool.submit(_build_one, i): i for i in range(len(scenes))}
        for fut in as_completed(futures):
            i, clip_path = fut.result()
            scene_clips[i] = clip_path

    ordered_clips = [clip for clip in scene_clips if clip is not None]

    if teaser_card:
        teaser_bg = teaser_card.get("bg_image")
        teaser_overlay = teaser_card.get("overlay_path")
        teaser_duration = float(teaser_card.get("duration", 1.0) or 1.0)
        if isinstance(teaser_bg, Path) and teaser_bg.exists():
            teaser_clip = clips_dir / "scene_teaser.mp4"
            build_silent_scene_clip(
                image_path=teaser_bg,
                output_path=teaser_clip,
                duration=teaser_duration,
                camera={"type": "static", "speed": "slow"},
                style=style,
                overlay_path=teaser_overlay if isinstance(teaser_overlay, Path) else None,
            )
            ordered_clips.append(teaser_clip)
            print(f"  -> 시리즈 teaser 추가: {teaser_card.get('text', '')}")

    # 4) 전환 효과와 함께 연결
    transitions = [s.get("transition", "fade") for s in scenes[:-1]]
    if teaser_card and ordered_clips:
        transitions.append("fade")
    fade_dur = style.get("motion", {}).get("fade_duration", 0.5)

    merged = output_path.parent / "_merged.mp4"
    concat_with_transitions(ordered_clips, merged, transitions, fade_dur)
    print("  -> 전환 효과 적용 완료")

    # 5) BGM 추가
    if bgm_path and bgm_path.exists():
        bgm_vol = style.get("audio", {}).get("bgm_volume", 0.15)
        compose_bgm(merged, bgm_path, output_path, bgm_vol)
        merged.unlink(missing_ok=True)
        print(f"  -> BGM: {bgm_path.name}")
    else:
        import shutil
        shutil.move(str(merged), str(output_path))
        print("  -> BGM 없이 합성")

    # 7) 임시 클립 정리
    if clips_dir.exists():
        for f in clips_dir.iterdir():
            f.unlink()
        clips_dir.rmdir()

    return output_path


# ============================================================
# 카메라/전환 할당 (compare 모드용)
# ============================================================

def _assign_cameras_from_style(scenes: list[dict], style: dict) -> list[dict]:
    """스타일의 motion 설정에서 카메라/전환을 scene에 재할당"""
    camera_prefs = style.get("motion", {}).get("camera", ["zoom_in", "static"])
    transition_prefs = style.get("motion", {}).get("transitions", ["fade"])

    updated = []
    for i, scene in enumerate(scenes):
        s = dict(scene)
        cam_type = camera_prefs[i % len(camera_prefs)]
        if i > 0 and updated and updated[-1].get("camera", {}).get("type") == cam_type:
            alt_idx = (i + 1) % len(camera_prefs)
            cam_type = camera_prefs[alt_idx]
        s["camera"] = {
            "type": cam_type,
            "speed": scene.get("camera", {}).get("speed", "slow"),
        }
        s["transition"] = transition_prefs[i % len(transition_prefs)]
        updated.append(s)
    return updated


# ============================================================
# 단일 스타일 파이프라인
# ============================================================

def run_pipeline_single(
    topic: str,
    style_name: str | None = None,
    no_research: bool = False,
    no_critic: bool = False,
    winning_patterns: dict | None = None,
    trend_hints: list[str] | None = None,
    research_brief_override: dict | None = None,
    series_parts: list[dict] | None = None,
    current_part: int | None = None,
    character_sheet_path: Path | None = None,
    series_title_fixed: str | None = None,
    series_subtitle_base_fixed: str | None = None,
    previous_part_scenes: list[dict] | None = None,
    previous_part_image_map: dict[int, Path] | None = None,
    previous_part_voice_map: dict | None = None,
    narration_seed_override: list[dict] | None = None,
    narration_bgm_mood_override: str | None = None,
) -> tuple[Path, dict]:
    """단일 스타일 파이프라인 실행 (시리즈의 1편 또는 독립 영상)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    series_total = len(series_parts) if series_parts else None
    series_part = current_part
    part_suffix = f"_part{current_part}" if current_part else ""
    work_dir = OUTPUT_DIR / f"{timestamp}{part_suffix}"
    work_dir.mkdir(parents=True, exist_ok=True)

    bgm_mood = None
    date_str = datetime.now().strftime("%Y.%m.%d")

    # 0. 리서치 (외부 전달 또는 커뮤니티 크롤링)
    research_brief = research_brief_override
    if research_brief is not None:
        research_brief = _normalize_research_brief(research_brief)
        # 시리즈 파이프라인 등에서 외부 전달된 리서치
        (work_dir / "research_brief.json").write_text(
            json.dumps(research_brief, ensure_ascii=False, indent=2)
        )
        print(f"[0] 리서치 (외부 전달)")
        print(f"  -> 주제: {research_brief.get('topic', '?')}")
        if series_part:
            print(f"  -> 시리즈 {series_part}/{series_total}편")
    elif not no_research:
        hint = topic.strip()
        print(f"[0] 리서치 중... (힌트: '{hint}')" if hint else "[0] 리서치 중... (완전 자율 모드)")
        research_brief = research(hint, trend_hints=trend_hints)
        research_brief = _normalize_research_brief(research_brief)

        (work_dir / "research_brief.json").write_text(
            json.dumps(research_brief, ensure_ascii=False, indent=2)
        )
        print(f"  -> 주제: {research_brief.get('topic', '?')}")
        print(f"  -> 감정: {research_brief.get('emotion', '?')}")
        print(f"  -> 이야기 유형: {research_brief.get('story_type', '?')}")
        print(f"  -> 출처 권역: {research_brief.get('source_region', '?')}")
        print(f"  -> 원문 길이: {len(str(research_brief.get('original_story', '')).strip())}자")
    else:
        raise RuntimeError(
            "run_pipeline_single requires a research_brief when no_research=True. "
            "The legacy topic-only fallback path was removed."
        )

    series_character_pool = (
        research_brief.get("series_characters", [])
        if isinstance(research_brief, dict)
        else []
    )
    if not isinstance(series_character_pool, list):
        series_character_pool = []

    narration_seed: list[dict] = []
    if research_brief:
        if narration_seed_override is not None:
            print("[1] Narration Agent 선행 플랜 재사용 중... (시리즈 고정 시드)")
            narration_seed = [
                s for s in narration_seed_override
                if isinstance(s, dict)
            ]
            if not narration_seed:
                raise RuntimeError("narration_seed_override is empty")
            if not style_name:
                suggested = str(research_brief.get("style_suggestion", "")).strip()
                style_name = suggested if suggested in set(list_styles()) else "casual"
            if narration_bgm_mood_override:
                bgm_mood = str(narration_bgm_mood_override).strip()
            else:
                bgm_mood = (
                    "dramatic"
                    if str(research_brief.get("story_type", "")).strip() in {"revenge", "drama", "mystery"}
                    else "funny"
                )
            print(f"  -> 재사용 시드 장면 수: {len(narration_seed)}")
            print(f"  -> 고정 스타일: {style_name}")
            print(f"  -> 고정 BGM: {bgm_mood}")
        else:
            print("[1] Narration Agent 선행 플랜 생성 중... (스타일/BGM/나레이션)")
            narration_plan = generate_narration_plan(
                research_brief=research_brief,
                forced_style_name=style_name if style_name else None,
                forced_bgm_mood=None,
                winning_patterns=winning_patterns,
            )
            narration_seed = list(narration_plan.get("scenes", []))
            style_name = str(narration_plan.get("style", style_name or "casual")).strip() or "casual"
            bgm_mood = str(narration_plan.get("bgm_mood", "funny")).strip() or "funny"
            print(f"  -> 선행 시드 장면 수: {len(narration_seed)}")
            print(f"  -> Narration 선택 스타일: {style_name}")
            print(f"  -> Narration 선택 BGM: {bgm_mood}")

    # 2. 플랜 생성
    if research_brief:
        # Narration Agent가 선택한 style/BGM 기반으로 Director는 구조만 설계
        style = load_style(style_name)
        part_label = f" (시리즈 {series_part}/{series_total}편)" if series_part else ""
        print(f"[2] Director 플랜 생성 중... (스타일: {style_name}, BGM: {bgm_mood}){part_label}")
        plan = _generate_plan_with_critic(
            research_brief, style, work_dir, no_critic=no_critic,
            winning_patterns=winning_patterns,
            series_parts=series_parts,
            current_part=current_part,
            narration_seed=narration_seed,
            fixed_bgm_mood=bgm_mood,
        )
        script = plan

    if series_character_pool:
        script["characters"] = _merge_character_pools(
            series_character_pool,
            script.get("characters", []),
        )
        (work_dir / "production_plan.json").write_text(
            json.dumps(script, ensure_ascii=False, indent=2)
        )
    # 스타일 로드 (플랜에서 결정된 스타일)
    style = load_style(style_name)

    print("[2-1] Image Agent 쿼리 생성 중...")
    # Director(scene_outline) -> ImageAgent(image_query)
    scenes = generate_image_queries(
        script.get("scenes", []),
        script.get("characters", []),
        research_brief,
    )
    print("[2-2] Narration Agent 후행 생성 없음 (선행 결과 고정)")

    print("[2-3] Speech Planner 화자 분리/보이스 매핑 중...")
    scenes, voice_map = plan_speech(
        scenes=scenes,
        characters=script.get("characters", []),
        previous_voice_map=previous_part_voice_map,
    )
    script["scenes"] = scenes
    script["voice_map"] = voice_map
    script = _sanitize_public_titles(script)
    script = _normalize_series_title_subtitle(
        script,
        series_part,
        series_total,
        series_title_fixed=series_title_fixed,
        series_subtitle_base_fixed=series_subtitle_base_fixed,
    )

    script_path = work_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2))
    print(f"  -> 제목: {script['title']}")
    print(f"  -> 장면 수: {len(script['scenes'])}")

    # 1. 캐릭터 시트 (플랜에 characters 있으면 생성, 시리즈는 이전 편 재사용)
    characters = script.get("characters", [])
    character_sheet_image = None
    if character_sheet_path and character_sheet_path.exists():
        print(f"  -> 캐릭터 시트 재사용: {character_sheet_path.name}")
        character_sheet_image = Image.open(character_sheet_path)
    elif characters:
        character_sheet_image = _generate_character_sheet(
            characters, style, work_dir,
        )

    # 2. 이미지 소싱 (순차, 이전 장면/캐릭터 시트 참조 적용)
    print(f"[2] 이미지 소싱 중... (순차 생성, 스타일: {style_name})")
    raw_images_dir = work_dir / "raw_images"
    is_multi_part_series = bool(series_parts and len(series_parts) > 1)
    has_prev_context = bool(previous_part_scenes and previous_part_image_map)

    # 참조 선택 모드 분리:
    # - 단일편 모드: 현재편 내부 참조만
    # - 다편 시리즈 모드: 현재편 + 전편 참조(통합 1회 호출)
    if is_multi_part_series and has_prev_context:
        print("  -> 참조 선택 모드: 다편 시리즈 (현재편+전편)")
        unified_reference_plan = select_references_unified(
            current_scenes=scenes,
            max_in_episode_refs=2,
            previous_part_scenes=previous_part_scenes,
            max_previous_part_refs=1,
        )
        reference_scene_map = (
            unified_reference_plan.get("in_episode_refs", {})
            if isinstance(unified_reference_plan, dict) else {}
        )
        reference_scene_notes_map = (
            unified_reference_plan.get("in_episode_notes", {})
            if isinstance(unified_reference_plan, dict) else {}
        )
        previous_part_reference_scene_map = (
            unified_reference_plan.get("previous_part_refs", {})
            if isinstance(unified_reference_plan, dict) else {}
        )
        previous_part_reference_scene_notes_map = (
            unified_reference_plan.get("previous_part_notes", {})
            if isinstance(unified_reference_plan, dict) else {}
        )
    else:
        print("  -> 참조 선택 모드: 단일편 (현재편 내부)")
        reference_plan = select_reference_scenes(scenes, max_refs=2)
        reference_scene_map = (
            reference_plan.get("refs", {})
            if isinstance(reference_plan, dict) else {}
        )
        reference_scene_notes_map = (
            reference_plan.get("notes", {})
            if isinstance(reference_plan, dict) else {}
        )
        previous_part_reference_scene_map = {}
        previous_part_reference_scene_notes_map = {}

    (work_dir / "reference_scene_map.json").write_text(
        json.dumps(
            {
                "refs": reference_scene_map,
                "notes": reference_scene_notes_map,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if reference_scene_map:
        print("  -> 장면 참조 맵 적용")
        for i in range(1, len(scenes)):
            refs = reference_scene_map.get(i, [])
            if refs:
                label = ", ".join(str(r + 1) for r in refs)
                print(f"     장면 {i + 1} <= 장면 {label}")

    if is_multi_part_series and has_prev_context and previous_part_reference_scene_map:
        (work_dir / "previous_part_reference_map.json").write_text(
            json.dumps(
                {
                    "refs": previous_part_reference_scene_map,
                    "notes": previous_part_reference_scene_notes_map,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("  -> 전편 장면 참조 맵 적용")
        for i in range(len(scenes)):
            refs = previous_part_reference_scene_map.get(i, [])
            if refs:
                label = ", ".join(str(r + 1) for r in refs)
                print(f"     현재 장면 {i + 1} <= 전편 장면 {label}")

    raw_images = _source_scene_images(
        scenes, raw_images_dir, style=style, styled_queries=True,
        character_sheet_image=character_sheet_image,
        characters=characters,
        use_prev_scene_reference=True,
        reference_scene_map=reference_scene_map,
        reference_scene_notes_map=reference_scene_notes_map,
        previous_part_reference_map=previous_part_reference_scene_map,
        previous_part_reference_notes_map=previous_part_reference_scene_notes_map,
        previous_part_image_map=previous_part_image_map,
    )

    # 3. 이미지 가공 (배경/오버레이 분리)
    print(f"[3] 이미지 가공 중... (스타일: {style_name})")
    processed_dir = work_dir / "processed"
    video_subtitle = script.get("subtitle", "")
    bg_images, overlay_images = _process_scenes_with_style(
        scenes, raw_images, style, script["title"], video_subtitle, date_str, processed_dir,
    )

    teaser_card = None
    if series_part and series_total and series_part < series_total and bg_images:
        teaser_text = f"{series_part + 1}편에서 공개"
        teaser_overlay_path = processed_dir / "overlay" / "series_teaser_overlay.png"
        create_teaser_overlay(
            output_path=teaser_overlay_path,
            style=style,
            teaser_text=teaser_text,
        )
        teaser_card = {
            "text": teaser_text,
            "bg_image": bg_images[-1],
            "overlay_path": teaser_overlay_path if teaser_overlay_path.exists() else None,
            "duration": 1.0,
        }

    # 4. TTS 생성
    print("[4] TTS 나레이션 생성 중...")
    tts_dir = work_dir / "tts"
    tts_results = run_tts(scenes, tts_dir, voice_map=voice_map)
    for r in tts_results:
        print(f"  -> 장면 {r['scene_index'] + 1} 음성 생성 완료")

    # 5. 영상 합성 (피크 정규화 → 카메라 효과 → 전환 → BGM)
    print("[5] 영상 합성 중...")
    mood = bgm_mood or script.get("bgm_mood", "funny")
    bgm_path = get_bgm_for_mood(mood)
    if bgm_path:
        print(f"  -> BGM: {bgm_path.name} (mood: {mood})")
    else:
        print("  -> BGM 없이 합성")

    final_video = work_dir / f"{_safe_filename(script['title'])}.mp4"
    _compose_video(
        scenes=scenes,
        bg_images=bg_images,
        overlay_images=overlay_images,
        tts_results=tts_results,
        style=style,
        output_path=final_video,
        bgm_path=bgm_path,
        teaser_card=teaser_card,
    )

    print(f"\n[완성] {final_video}")
    print(f"  제목: {script['title']}")
    print(f"  설명: {script.get('description', '')}")
    print(f"  태그: {', '.join(script.get('tags', []))}")
    print(f"  스타일: {style_name}")
    print(f"  BGM mood: {mood}")

    # 캐릭터 시트 경로
    character_sheet_path = work_dir / "character_sheet.png"
    has_sheet = character_sheet_path.exists()

    metadata = {
        "title": script.get("title", ""),
        "subtitle": script.get("subtitle", ""),
        "description": script.get("description", ""),
        "tags": script.get("tags", []),
        "style": style_name,
        "bgm_mood": mood,
        "bgm_used": bool(bgm_path and bgm_path.exists()),
        "bgm_path": str(bgm_path) if bgm_path else "",
        "summary": script.get("summary", ""),
        "work_dir": str(work_dir),
        "production_plan": script,
        "research_brief": research_brief,
        "series_part": series_part,
        "series_total": series_total,
        "source_fingerprint": _compute_source_fingerprint(research_brief),
        "ending_type": _detect_ending_type(script, series_part, series_total),
        "generation_status": "generated",
        "character_sheet_path": str(character_sheet_path) if has_sheet else None,
        "voice_map": voice_map,
    }

    return final_video, metadata


# ============================================================
# 비교 모드 파이프라인
# ============================================================

def run_pipeline_compare(
    topic: str,
    no_research: bool = False,
    no_critic: bool = False,
) -> list[Path]:
    """전체 스타일 비교 파이프라인: Director 플랜 공유 → 스타일별 카메라/전환 재할당"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = OUTPUT_DIR / f"{timestamp}_compare"
    work_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y.%m.%d")
    total_styles = len(COMPARE_STYLES)

    # ===== 공유 단계 (1회만 실행) =====

    # 0. 리서치
    research_brief = None
    if not no_research:
        hint = topic.strip()
        print(f"[0] 리서치 중... (힌트: '{hint}')" if hint else "[0] 리서치 중... (완전 자율 모드)")
        research_brief = research(hint)
        research_brief = _normalize_research_brief(research_brief)
        (work_dir / "research_brief.json").write_text(
            json.dumps(research_brief, ensure_ascii=False, indent=2)
        )
        print(f"  -> 주제: {research_brief.get('topic', '?')}")
        print(f"  -> 원문 길이: {len(str(research_brief.get('original_story', '')).strip())}자")
    else:
        raise RuntimeError(
            "run_pipeline_compare requires research. "
            "The legacy topic-only fallback path was removed."
        )

    narration_seed: list[dict] = []
    bgm_mood = None
    selected_style_name = "casual"
    if research_brief:
        print("[1] Narration Agent 선행 플랜 생성 중... (공유용)")
        narration_plan = generate_narration_plan(
            research_brief=research_brief,
            forced_style_name=None,
            forced_bgm_mood=None,
            winning_patterns=winning_patterns,
        )
        narration_seed = list(narration_plan.get("scenes", []))
        selected_style_name = str(narration_plan.get("style", "casual")).strip() or "casual"
        bgm_mood = str(narration_plan.get("bgm_mood", "funny")).strip() or "funny"
        print(f"  -> 선행 시드 장면 수: {len(narration_seed)}")
        print(f"  -> Narration 선택 스타일: {selected_style_name}")
        print(f"  -> Narration 선택 BGM: {bgm_mood}")

    # 2. 플랜 생성 (Narration Agent 선택 style/BGM 기반)
    if bgm_mood is None:
        bgm_mood = "funny"

    if research_brief:
        selected_style = load_style(selected_style_name)
        print(f"[2] Director 플랜 생성 중... (공유 플랜, 스타일: {selected_style_name}, BGM: {bgm_mood})")
        plan = _generate_plan_with_critic(
            research_brief,
            selected_style,
            work_dir,
            no_critic=no_critic,
            winning_patterns=winning_patterns,
            narration_seed=narration_seed,
            fixed_bgm_mood=bgm_mood,
        )
        script = plan
    script_path = work_dir / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2))
    print(f"  -> 제목: {script['title']}")
    print(f"  -> 장면 수: {len(script['scenes'])}")

    print("[2-1] Image Agent 쿼리 생성 중... (공유용)")
    base_scenes = generate_image_queries(
        script.get("scenes", []),
        script.get("characters", []),
        research_brief,
    )
    print("[2-2] Narration Agent 후행 생성 없음 (선행 결과 고정)")
    print("[2-3] Speech Planner 화자 분리/보이스 매핑 중... (공유용)")
    base_scenes, voice_map = plan_speech(
        scenes=base_scenes,
        characters=script.get("characters", []),
    )
    script["scenes"] = base_scenes
    script["voice_map"] = voice_map
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2))
    characters = script.get("characters", [])

    # 2. 이미지 소싱 (중립 프롬프트, 병렬, 공유용)
    print(f"[3] 이미지 소싱 중... (병렬 {IMAGE_WORKERS} workers, 공유용)")
    raw_images_dir = work_dir / "raw_images"
    raw_images = _source_scene_images(
        base_scenes, raw_images_dir, style=None, styled_queries=False, characters=characters,
    )

    # 3. TTS 생성 (공유)
    print("[4] TTS 나레이션 생성 중... (공유용)")
    tts_dir = work_dir / "tts"
    tts_results = run_tts(base_scenes, tts_dir, voice_map=voice_map)
    for r in tts_results:
        print(f"  -> 장면 {r['scene_index'] + 1} 음성 생성 완료")

    mood = bgm_mood or script.get("bgm_mood", "funny")
    bgm_path = get_bgm_for_mood(mood)

    # ===== 스타일별 단계 =====
    final_videos: list[Path] = []

    for style_idx, style_name in enumerate(COMPARE_STYLES, start=1):
        style = load_style(style_name)

        # 스타일별 카메라/전환 재할당
        scenes = _assign_cameras_from_style(base_scenes, style)

        print(
            f"\n[4-{style_idx}] 이미지 가공 중... "
            f"(스타일 {style_idx}/{total_styles}: {style_name})"
        )

        style_dir = work_dir / style_name
        processed_dir = style_dir / "processed"
        video_subtitle = script.get("subtitle", "")
        bg_images, overlay_images = _process_scenes_with_style(
            scenes, raw_images, style, script["title"], video_subtitle, date_str, processed_dir,
        )

        # 영상 합성
        print(
            f"[5-{style_idx}] 영상 합성 중... "
            f"(스타일 {style_idx}/{total_styles}: {style_name})"
        )
        if bgm_path:
            print(f"  -> BGM: {bgm_path.name} (mood: {mood})")
        else:
            print("  -> BGM 없이 합성")

        final_video = style_dir / f"{_safe_filename(script['title'])}_{style_name}.mp4"
        _compose_video(
            scenes=scenes,
            bg_images=bg_images,
            overlay_images=overlay_images,
            tts_results=tts_results,
            style=style,
            output_path=final_video,
            bgm_path=bgm_path,
        )
        final_videos.append(final_video)
        print(f"  -> [{style_name}] 완성: {final_video}")

    print(f"\n[완성] {total_styles}개 스타일 비교 영상 생성 완료")
    print(f"  제목: {script['title']}")
    print(f"  설명: {script.get('description', '')}")
    print(f"  태그: {', '.join(script.get('tags', []))}")
    print(f"  출력 디렉토리: {work_dir}")
    for v in final_videos:
        print(f"    - {v.name}")

    return final_videos


# ============================================================
# CLI
# ============================================================

def _parse_args() -> argparse.Namespace:
    """CLI 인자 파싱"""
    parser = argparse.ArgumentParser(
        description="유머/썰/사연 YouTube Shorts 자동 생성 파이프라인",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="",
        help="영상 주제 (비우면 리서처가 완전 자율 선택)",
    )
    parser.add_argument(
        "--style",
        type=str,
        default=None,
        help=f"사용할 스타일 이름 (사용 가능: {', '.join(list_styles())})",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="4가지 스타일로 비교 영상 생성 (Director 플랜 공유)",
    )
    parser.add_argument(
        "--no-critic",
        action="store_true",
        help="Critic 검증 건너뛰기 (Director 플랜 그대로 사용)",
    )
    parser.add_argument(
        "--list-styles",
        action="store_true",
        help="사용 가능한 스타일 목록 출력",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="YouTube OAuth2 인증 (최초 1회)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="영상 생성 후 YouTube 업로드",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="메타데이터만 확인 (실제 업로드 안 함)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="48시간+ 경과 영상 애널리틱스 수집",
    )
    parser.add_argument(
        "--with-feedback",
        action="store_true",
        help="과거 성과 패턴 반영하여 영상 생성",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="1회 완전 자동 실행 (생성+업로드+기록)",
    )
    return parser.parse_args()


def _handle_upload(
    final_video: Path,
    metadata: dict,
    dry_run: bool = False,
    trigger_source: str = "manual",
    retry_count: int = 0,
    slot_key: str | None = None,
):
    """영상 업로드 + Supabase 기록"""
    from tools.youtube_uploader import upload_video, build_shorts_description, check_daily_quota_remaining
    from tools.supabase_client import update_video_status, insert_run, update_run

    # 쿼터 확인
    quota = check_daily_quota_remaining()
    print(f"\n[쿼터] 오늘 {quota['used']}/{quota['limit']}회 사용 (남은: {quota['remaining']})")
    if not quota["can_upload"]:
        print("  [!] 일일 업로드 쿼터 초과. 내일 다시 시도하세요.")
        return

    # 설명 생성
    description = build_shorts_description(metadata.get("production_plan", metadata))
    render_title = metadata.get("title", "YouTube Shorts")
    upload_title = _build_youtube_upload_title(metadata)
    tags = metadata.get("tags", [])

    print(f"\n[업로드 정보]")
    print(f"  렌더 제목: {render_title}")
    print(f"  업로드 제목: {upload_title}")
    print(f"  태그: {', '.join(tags)}")
    print(f"  파일: {final_video}")
    print(f"  공개 상태: {YOUTUBE_DEFAULT_PRIVACY}")
    print(f"  설명:\n{description[:200]}...")

    metadata["description"] = description

    if dry_run:
        print("\n[Dry Run] 실제 업로드를 건너뜁니다.")
        return

    # Supabase 기록 (생성 완료 레코드 보장)
    video_record = _register_generated_video(
        metadata=metadata,
        publish_status=metadata.get("publish_status", "ready") or "ready",
        trigger_source=trigger_source,
    )
    video_id = video_record["id"] if video_record else None
    if video_id:
        update_video_status(
            video_id,
            publish_status="uploading",
        )

    # 실행 기록
    run_record = insert_run(
        run_type="publish",
        video_id=video_id,
        trigger_source=trigger_source,
        retry_count=retry_count,
        slot_key=slot_key,
        run_meta={
            "title": render_title,
            "upload_title": upload_title,
            "series_part": metadata.get("series_part"),
            "series_total": metadata.get("series_total"),
        },
    )
    run_id = run_record["id"] if run_record else None

    try:
        # YouTube 업로드
        print(f"\n[6] YouTube 업로드 중...")
        result = upload_video(
            video_path=final_video,
            title=upload_title,
            description=description,
            tags=tags,
            privacy_status=YOUTUBE_DEFAULT_PRIVACY,
        )

        print(f"  -> YouTube ID: {result['youtube_id']}")
        print(f"  -> URL: {result['url']}")

        # Supabase 업데이트
        if video_id:
            update_video_status(
                video_id,
                publish_status="uploaded",
                youtube_id=result["youtube_id"],
                published_at=result["published_at"],
            )
        if run_id:
            update_run(run_id, status="completed")

    except Exception as e:
        print(f"  [!] 업로드 실패: {e}")
        if video_id:
            update_video_status(video_id, publish_status="failed")
        if run_id:
            update_run(run_id, status="failed", error_message=str(e), failure_stage="publish")
        raise


def _handle_analyze():
    """48시간+ 경과 영상 애널리틱스 수집"""
    from tools.youtube_analytics import fetch_video_analytics, is_analytics_ready
    from tools.supabase_client import list_videos_pending_analytics, insert_analytics, insert_run, update_run

    run_record = insert_run(run_type="collect_analytics")
    run_id = run_record["id"] if run_record else None

    try:
        pending = list_videos_pending_analytics()
        if not pending:
            print("[Analytics] 수집 대상 영상이 없습니다.")
            if run_id:
                update_run(run_id, status="completed")
            return

        print(f"[Analytics] {len(pending)}개 영상 애널리틱스 수집 중...")
        for video in pending:
            youtube_id = video.get("youtube_id")
            published_at = video.get("published_at", "")

            if not youtube_id:
                continue

            if not is_analytics_ready(published_at):
                print(f"  -> {youtube_id}: 아직 48시간 미경과, 건너뜀")
                continue

            print(f"  -> {youtube_id}: 수집 중...")
            try:
                metrics = fetch_video_analytics(youtube_id)
                insert_analytics(video_id=video["id"], **metrics)
                print(f"     views={metrics.get('views', 0)}, ctr={metrics.get('ctr', 0):.1%}")
            except Exception as e:
                print(f"     수집 실패: {e}")

        if run_id:
            update_run(run_id, status="completed")
        print("[Analytics] 수집 완료")

    except Exception as e:
        print(f"[Analytics] 오류: {e}")
        if run_id:
            update_run(run_id, status="failed", error_message=str(e), failure_stage="collect_analytics")


def _enqueue_upload(
    video_path: Path,
    metadata: dict,
    trigger_source: str = "manual",
    publish_after: str | None = None,
):
    """영상을 업로드 대기열에 저장

    Args:
        video_path: 영상 파일 경로
        metadata: 업로드에 필요한 메타데이터 dict
    """
    import shutil

    UPLOAD_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    part = metadata.get("series_part", 0)
    queue_dir = UPLOAD_QUEUE_DIR / f"{timestamp}_part{part}"
    queue_dir.mkdir(parents=True, exist_ok=True)

    # 영상 복사
    dest_video = queue_dir / "video.mp4"
    shutil.copy2(str(video_path), str(dest_video))

    _register_generated_video(
        metadata=metadata,
        publish_status="queued",
        trigger_source=trigger_source,
        publish_after=publish_after,
    )

    # 메타데이터 저장 (production_plan/research_brief는 크기가 크므로 제외)
    save_meta = {k: v for k, v in metadata.items() if k not in ("production_plan", "research_brief")}
    save_meta["original_video_path"] = str(video_path)
    # Path 객체 직렬화 불가하므로 변환
    save_meta = {k: str(v) if isinstance(v, Path) else v for k, v in save_meta.items()}
    (queue_dir / "metadata.json").write_text(
        json.dumps(save_meta, ensure_ascii=False, indent=2)
    )

    print(f"  -> 대기열 저장: {queue_dir.name}")


def _process_upload_queue(
    trigger_source: str = "manual",
    slot_key: str | None = None,
) -> bool:
    """대기열에서 업로드 시각이 도달한 영상 1개를 업로드

    Returns:
        True: 업로드 성공, False: 대기열이 비었거나 실패
    """
    import shutil

    if not UPLOAD_QUEUE_DIR.exists():
        return False

    # 디렉토리 이름순 정렬 = 생성 순서
    queue_items = sorted(
        [d for d in UPLOAD_QUEUE_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    if not queue_items:
        return False

    now_utc = datetime.now(timezone.utc)
    due_items: list[tuple[datetime, Path, dict]] = []

    for queue_dir in queue_items:
        video_path = queue_dir / "video.mp4"
        meta_path = queue_dir / "metadata.json"

        if not video_path.exists() or not meta_path.exists():
            print(f"  [!] 대기열 항목 손상, 삭제: {queue_dir.name}")
            shutil.rmtree(str(queue_dir), ignore_errors=True)
            continue

        try:
            metadata = json.loads(meta_path.read_text())
        except Exception:
            print(f"  [!] 대기열 메타데이터 손상, 삭제: {queue_dir.name}")
            shutil.rmtree(str(queue_dir), ignore_errors=True)
            continue

        publish_after_raw = metadata.get("publish_after")
        publish_after = None
        if publish_after_raw:
            try:
                publish_after = datetime.fromisoformat(str(publish_after_raw).replace("Z", "+00:00"))
            except ValueError:
                publish_after = None

        if publish_after and publish_after > now_utc:
            continue

        sort_key = publish_after or datetime.min.replace(tzinfo=timezone.utc)
        due_items.append((sort_key, queue_dir, metadata))

    if not due_items:
        return False

    due_items.sort(key=lambda item: (item[0], item[1].name))
    _, queue_dir, metadata = due_items[0]
    video_path = queue_dir / "video.mp4"
    part_info = f" (시리즈 {metadata.get('series_part', '?')}/{metadata.get('series_total', '?')}편)" if metadata.get("series_part") else ""
    print(f"\n[대기열] 업로드: {metadata.get('title', '?')}{part_info}")

    try:
        _handle_upload(
            video_path,
            metadata,
            trigger_source=trigger_source if trigger_source != "manual" else "queue",
            retry_count=1,
            slot_key=slot_key,
        )
        # 업로드 성공 시 대기열에서 제거
        shutil.rmtree(str(queue_dir), ignore_errors=True)
        print(f"  -> 대기열에서 제거 완료")
        return True
    except Exception as e:
        print(f"  [!] 대기열 업로드 실패: {e} (다음 실행에서 재시도)")
        return False


def _run_series_pipeline(
    research_brief: dict,
    style_name: str | None = None,
    no_critic: bool = False,
    winning_patterns: dict | None = None,
) -> list[tuple[Path, dict]]:
    """시리즈 파이프라인: 리서치 1회 → 나레이터 1회(전편) → 파트별 생성

    Args:
        research_brief: series_potential=True인 리서치 결과 (series_parts 포함)
        style_name: 스타일 지정 (None이면 AI 자동 선택)
        no_critic: Critic 건너뛰기
        winning_patterns: 성과 패턴

    Returns:
        [(video_path, metadata), ...] 파트별 결과 리스트
    """
    research_brief = _normalize_research_brief(research_brief)
    print(f"\n{'='*50}")
    print("[시리즈] 파이프라인 시작")
    print(f"  -> 주제: {research_brief.get('topic', '?')}")
    print(f"{'='*50}\n")

    print("[시리즈] Narration Agent 전편 플랜 생성 중... (1회, 구조+나레이션)")
    series_narration_plan = generate_series_narration_plan(
        research_brief=research_brief,
        forced_style_name=style_name if style_name else None,
        forced_bgm_mood=None,
        winning_patterns=winning_patterns,
    )
    chosen_style_name = str(series_narration_plan.get("style", style_name or "casual")).strip() or "casual"
    series_bgm_mood = str(series_narration_plan.get("bgm_mood", "funny")).strip() or "funny"
    series_characters = series_narration_plan.get("characters", [])
    if not isinstance(series_characters, list):
        series_characters = []

    raw_parts = series_narration_plan.get("parts", [])
    if not isinstance(raw_parts, list):
        raise RuntimeError("series narration plan parts must be a list")

    part_seed_map: dict[int, list[dict]] = {}
    series_parts: list[dict] = []
    for idx, block in enumerate(raw_parts, start=1):
        if not isinstance(block, dict):
            continue
        part_no = block.get("part")
        if not isinstance(part_no, int):
            part_no = idx
        scenes = block.get("scenes", [])
        if isinstance(scenes, list):
            part_seed_map[part_no] = [s for s in scenes if isinstance(s, dict)]
        series_parts.append(
            {
                "part": part_no,
                "part_focus": str(block.get("part_focus", "")).strip(),
                "cliffhanger": block.get("cliffhanger"),
            }
        )

    series_parts = sorted(series_parts, key=lambda x: int(x.get("part", 0)))

    total_parts = series_narration_plan.get("series_total_parts")
    if not isinstance(total_parts, int):
        total_parts = len(series_parts)
    if total_parts != len(series_parts):
        raise RuntimeError(
            f"series narration plan mismatch: series_total_parts={total_parts}, "
            f"parts={len(series_parts)}"
        )

    expected_parts = list(range(1, total_parts + 1))
    actual_parts = sorted(part_seed_map.keys())
    if actual_parts != expected_parts:
        raise RuntimeError(
            f"series narration plan part mismatch: expected={expected_parts}, actual={actual_parts}"
        )

    if any(not str(p.get("part_focus", "")).strip() for p in series_parts):
        raise RuntimeError("series narration plan has empty part_focus")

    research_brief_for_series = dict(research_brief)
    research_brief_for_series["series_total_parts"] = total_parts
    research_brief_for_series["series_parts"] = series_parts
    if series_characters:
        research_brief_for_series["series_characters"] = series_characters

    print(f"[시리즈] 총 {total_parts}편 구성 완료")
    print(f"  -> 시리즈 스타일 고정: {chosen_style_name}")
    print(f"  -> 시리즈 BGM 고정: {series_bgm_mood}")
    if series_characters:
        print(f"  -> 시리즈 핵심 인물 풀: {len(series_characters)}명")

    results = []
    series_group_id = str(uuid.uuid4())
    shared_character_sheet_path = None  # 1편 캐릭터 시트를 이후 편에서 재사용
    fixed_series_title = None
    fixed_series_subtitle_base = None
    previous_part_scenes = None
    previous_part_image_map: dict[int, Path] | None = None
    previous_part_voice_map: dict | None = None

    for part in range(1, total_parts + 1):
        print(f"\n{'─'*40}")
        print(f"[시리즈 {part}/{total_parts}편] 생성 시작")
        print(f"{'─'*40}")

        video_path, metadata = run_pipeline_single(
            topic=research_brief.get("topic", ""),
            style_name=chosen_style_name,
            no_research=True,  # 리서치 재사용
            no_critic=no_critic,
            winning_patterns=winning_patterns,
            research_brief_override=research_brief_for_series,
            series_parts=series_parts,
            current_part=part,
            character_sheet_path=shared_character_sheet_path,
            series_title_fixed=fixed_series_title,
            series_subtitle_base_fixed=fixed_series_subtitle_base,
            previous_part_scenes=previous_part_scenes,
            previous_part_image_map=previous_part_image_map,
            previous_part_voice_map=previous_part_voice_map,
            narration_seed_override=part_seed_map.get(part),
            narration_bgm_mood_override=series_bgm_mood,
        )
        metadata["series_group_id"] = series_group_id

        # 1편에서 생성된 캐릭터 시트를 이후 편에서 재사용
        if part == 1 and metadata.get("character_sheet_path"):
            shared_character_sheet_path = Path(metadata["character_sheet_path"])
            print(f"  -> 캐릭터 시트 공유: {shared_character_sheet_path.name}")

        # 1편 제목/부제 고정: 이후 편은 부제의 N편 숫자만 변경
        if part == 1:
            t = str(metadata.get("title", "")).strip()
            s = str(metadata.get("subtitle", "")).strip()
            fixed_series_title = SERIES_TAG_RE.sub("", t).strip() or None
            subtitle_base = SERIES_TAG_RE.sub("", s).strip()
            subtitle_base = SERIES_PART_RE.sub("", subtitle_base).strip()
            if subtitle_base in {"시리즈", "series", "Series"}:
                subtitle_base = fixed_series_title or subtitle_base
            fixed_series_subtitle_base = subtitle_base or fixed_series_title or None
            if fixed_series_title:
                print(f"  -> 시리즈 제목 고정: {fixed_series_title}")
            if fixed_series_subtitle_base:
                print(f"  -> 시리즈 부제 베이스 고정: {fixed_series_subtitle_base}")
        if fixed_series_title:
            metadata["series_title"] = fixed_series_title
        else:
            metadata["series_title"] = str(metadata.get("title", "")).strip()

        # 다음 편을 위한 전편 컨텍스트(장면 텍스트/이미지) 공유
        prod_plan = metadata.get("production_plan", {}) if isinstance(metadata, dict) else {}
        if isinstance(prod_plan, dict):
            prev_scenes = prod_plan.get("scenes", [])
            previous_part_scenes = prev_scenes if isinstance(prev_scenes, list) else None
        else:
            previous_part_scenes = None

        prev_work_dir_raw = str(metadata.get("work_dir", "")).strip() if isinstance(metadata, dict) else ""
        if prev_work_dir_raw:
            previous_part_image_map = _collect_scene_image_map(Path(prev_work_dir_raw) / "raw_images")
        else:
            previous_part_image_map = None
        if previous_part_scenes and previous_part_image_map:
            print(f"  -> 전편 참조 컨텍스트 준비: 장면 {len(previous_part_scenes)}개, 이미지 {len(previous_part_image_map)}개")

        previous_part_voice_map = metadata.get("voice_map") if isinstance(metadata, dict) else None

        results.append((video_path, metadata))
        print(f"[시리즈 {part}/{total_parts}편] 완성: {video_path.name}")

    print(f"\n{'='*50}")
    print(f"[시리즈] {total_parts}편 모두 생성 완료!")
    for i, (vp, _) in enumerate(results, 1):
        print(f"  {i}편: {vp.name}")
    print(f"{'='*50}")

    return results


def _handle_auto(topic: str, style_name: str | None, no_critic: bool):
    """1회 완전 자동 실행: 대기열 우선 → 피드백 로드 → 리서치 → 시리즈 판단 → 생성 → 업로드"""
    from tools.youtube_uploader import check_daily_quota_remaining

    quota = check_daily_quota_remaining()
    if not quota["can_upload"]:
        print(f"[Auto] 일일 쿼터 초과 ({quota['used']}/{quota['limit']}). 건너뜁니다.")
        return

    print(f"[Auto] 완전 자동 실행 시작 (남은 쿼터: {quota['remaining']})")

    # 1) 대기열 우선 처리
    if _process_upload_queue():
        print("[Auto] 이번 슬롯은 대기열 업로드를 우선 처리했으므로 새 영상 생성은 건너뜁니다.")
        return

    # 2) 피드백 로드 시도
    winning_patterns = None
    trend_hints = None
    try:
        from tools.supabase_client import get_active_patterns
        patterns = get_active_patterns()
        if patterns:
            winning_patterns = _build_winning_patterns(patterns)
            trend_hints = _build_trend_hints(patterns)
            print(f"  -> 활성 패턴 {len(patterns)}개 로드")
    except Exception:
        pass

    # 3) 리서치 먼저 실행 (시리즈 판단 필요)
    hint = topic.strip()
    print(f"[0] 리서치 중... (힌트: '{hint}')" if hint else "[0] 리서치 중... (완전 자율 모드)")
    research_brief = None
    duplicate_video = None
    for attempt in range(1, 4):
        research_brief = research(hint, trend_hints=trend_hints)
        research_brief = _normalize_research_brief(research_brief)
        duplicate_video = _find_recent_duplicate_story(research_brief)
        if not duplicate_video:
            break
        print(
            f"  [중복 회피] 최근 생성 영상과 source fingerprint가 겹칩니다: "
            f"{duplicate_video.get('title', '?')} (재탐색 {attempt}/3)"
        )
    if duplicate_video:
        print("  [중복 회피] 최근 중복 소스를 피하지 못해 마지막 후보로 진행합니다.")
    print(f"  -> 주제: {research_brief.get('topic', '?')}")
    print(f"  -> 감정: {research_brief.get('emotion', '?')}")
    print(f"  -> 이야기 유형: {research_brief.get('story_type', '?')}")
    print(f"  -> 출처 권역: {research_brief.get('source_region', '?')}")
    print(f"  -> 원문 길이: {len(str(research_brief.get('original_story', '')).strip())}자")

    # 4) 시리즈 판단
    is_series = research_brief.get("series_potential", False)
    if is_series:
        print("\n[Auto] 시리즈 감지! 다편 파이프라인 실행")

        # 전편 생성
        results = _run_series_pipeline(
            research_brief=research_brief,
            style_name=style_name,
            no_critic=no_critic,
            winning_patterns=winning_patterns,
        )

        # 1편만 즉시 업로드, 나머지는 대기열
        if results:
            print(f"\n[업로드] 시리즈 1/{len(results)}편 즉시 업로드")
            try:
                _handle_upload(results[0][0], results[0][1], trigger_source="manual")
            except Exception as e:
                print(f"  [!] 1편 업로드 실패, 대기열로 이동: {e}")
                _enqueue_upload(results[0][0], results[0][1], trigger_source="manual")

            for i, (video, meta) in enumerate(results[1:], 2):
                print(f"[대기열] 시리즈 {i}/{len(results)}편 대기열 저장")
                publish_after = _next_publish_slot(datetime.now(KST), step=i - 2).astimezone(timezone.utc).isoformat()
                _enqueue_upload(video, meta, trigger_source="manual", publish_after=publish_after)
    else:
        # 단일 영상 (리서치 결과 재사용)
        final_video, metadata = run_pipeline_single(
            topic,
            style_name=style_name,
            no_research=True,  # 이미 리서치 완료
            no_critic=no_critic,
            winning_patterns=winning_patterns,
            research_brief_override=research_brief,
        )
        _handle_upload(final_video, metadata, trigger_source="manual")


def _build_winning_patterns(patterns: list[dict]) -> dict:
    """활성 패턴 → Director용 winning_patterns 딕셔너리"""
    result = {"winners": [], "avoid": [], "recommendations": []}

    for p in patterns:
        ptype = p.get("pattern_type", "")
        pdata = p.get("pattern_data", {})
        win_rate = p.get("win_rate", 0)

        if ptype == "avoid":
            result["avoid"].append(pdata.get("description", p.get("pattern_key", "")))
        elif win_rate >= 0.6:
            result["winners"].append({
                "type": ptype,
                "key": p.get("pattern_key", ""),
                "win_rate": win_rate,
                **pdata,
            })
        if pdata.get("recommendation"):
            result["recommendations"].append(pdata["recommendation"])

    return result


def _build_trend_hints(patterns: list[dict]) -> list[str]:
    """활성 패턴 → Researcher용 trend_hints 리스트"""
    hints = []
    for p in patterns:
        if p.get("pattern_type") == "topic" and p.get("win_rate", 0) >= 0.6:
            hints.append(p.get("pattern_key", ""))
    return hints[:5] if hints else None


if __name__ == "__main__":
    args = _parse_args()

    # --auth: YouTube OAuth2 인증
    if args.auth:
        from tools.youtube_auth import run_auth_flow
        run_auth_flow()
        raise SystemExit(0)

    # --list-styles: 스타일 목록 출력
    if args.list_styles:
        print("사용 가능한 스타일:")
        for name in sorted(list_styles()):
            style = load_style(name)
            desc = style.get("description", "")
            print(f"  - {name}: {desc}")
        raise SystemExit(0)

    # --analyze: 애널리틱스 수집
    if args.analyze:
        _handle_analyze()
        raise SystemExit(0)

    # --auto: 완전 자동 실행
    if args.auto:
        _handle_auto(args.topic, args.style, args.no_critic)
        raise SystemExit(0)

    # --with-feedback: 피드백 반영 생성
    winning_patterns = None
    trend_hints = None
    if args.with_feedback:
        try:
            from tools.supabase_client import get_active_patterns
            patterns = get_active_patterns()
            if patterns:
                winning_patterns = _build_winning_patterns(patterns)
                trend_hints = _build_trend_hints(patterns)
                print(f"[피드백] 활성 패턴 {len(patterns)}개 로드")
            else:
                print("[피드백] 저장된 패턴이 없습니다. 기본 모드로 진행합니다.")
        except Exception as e:
            print(f"[피드백] 패턴 로드 실패: {e}. 기본 모드로 진행합니다.")

    if args.compare:
        run_pipeline_compare(
            args.topic,
            no_critic=args.no_critic,
        )
    else:
        # 리서치 → 시리즈 판단 → 생성
        hint = args.topic.strip()
        research_brief = research(hint, trend_hints=trend_hints)
        research_brief = _normalize_research_brief(research_brief)

        is_series = research_brief.get("series_potential", False)
        if is_series:
            print("\n[시리즈] 다편 분할 생성 감지!")
            results = _run_series_pipeline(
                research_brief=research_brief,
                style_name=args.style,
                no_critic=args.no_critic,
                winning_patterns=winning_patterns,
            )
            if args.upload:
                for i, (video, meta) in enumerate(results, 1):
                    print(f"\n[업로드] 시리즈 {i}/{len(results)}편")
                    _handle_upload(video, meta, dry_run=args.dry_run)
        else:
            # 단일 영상 (리서치 결과 재사용)
            final_video, metadata = run_pipeline_single(
                args.topic,
                style_name=args.style,
                no_research=True,
                no_critic=args.no_critic,
                winning_patterns=winning_patterns,
                research_brief_override=research_brief,
            )
            if args.upload:
                _handle_upload(final_video, metadata, dry_run=args.dry_run)
