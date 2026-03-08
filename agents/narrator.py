"""Narration Agent - Gemini 기반 장면별 내레이션 생성기"""

import json
from google import genai
from config.settings import GEMINI_API_KEY
from tools.style_manager import list_styles, load_style

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-pro-preview"
MAX_RETRIES = 5
MIN_SCENES = 8
MAX_SCENES = 10

BGM_OPTIONS = {
    "funny": "가볍고 코믹한 분위기",
    "emotional": "감성/여운 중심",
    "tension": "긴장/불안 고조",
    "chill": "잔잔하고 편안한 분위기",
    "quirky": "엉뚱하고 장난스러운 분위기",
    "dramatic": "강한 서사/결정적 장면 강조",
}

META_ENDING_MARKERS = {
    "참교육 사연",
    "참교육 썰",
    "실화였습니다",
    "실화였어요",
    "레전드였습니다",
    "레전드였어요",
    "사연이었습니다",
    "사연이었어요",
    "썰이었습니다",
    "썰이었어요",
    "여러분은 어떻게 생각하시나요",
    "여러분 생각은 어떠신가요",
    "구독과 좋아요",
    "좋아요와 구독",
}


def _build_style_and_bgm_blocks(style_names: list[str]) -> tuple[str, str]:
    style_lines = []
    for name in style_names:
        s = load_style(name)
        narration_cfg = s.get("narration", {})
        style_lines.append(
            f"- {name}: {s.get('description', '')} / narration guide: {narration_cfg.get('guide', '')}"
        )
    styles_block = "\n".join(style_lines)
    bgm_block = "\n".join(f"- {k}: {v}" for k, v in BGM_OPTIONS.items())
    return styles_block, bgm_block


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned.removeprefix("```json").strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
            return json.loads(cleaned)
        except Exception:
            return {}


def _collect_seed_scenes(data: dict) -> list[dict]:
    ordered: dict[int, dict] = {}
    if not isinstance(data, dict):
        return []
    for item in data.get("scenes", []):
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0:
            continue
        narration = str(item.get("narration", "")).strip()
        scene_outline = str(item.get("scene_outline", "")).strip()
        if not narration or not scene_outline:
            continue
        ordered[idx] = {
            "narration": narration,
            "scene_outline": scene_outline,
            "image_intent": str(item.get("image_intent", "")).strip(),
            "setting_hint": str(item.get("setting_hint", "")).strip(),
            "emotion_beat": str(item.get("emotion_beat", "")).strip(),
            "action_beat": str(item.get("action_beat", "")).strip(),
        }
    return [ordered[i] for i in sorted(ordered.keys())]


def _normalize_style_name(value: str, default: str) -> str:
    name = str(value or "").strip()
    allowed = set(list_styles())
    if name in allowed:
        return name
    return default


def _normalize_bgm_mood(value: str, default: str) -> str:
    mood = str(value or "").strip()
    if mood in BGM_OPTIONS:
        return mood
    return default


def _normalize_ending_text(text: str) -> str:
    cleaned = str(text or "").strip()
    return cleaned.rstrip(" .!?~\"'”’")


def _looks_like_meta_ending(text: str) -> bool:
    cleaned = _normalize_ending_text(text)
    if not cleaned:
        return False
    return any(marker in cleaned for marker in META_ENDING_MARKERS)


def _collect_characters(data: dict) -> list[dict]:
    if not isinstance(data, dict):
        return []

    characters: list[dict] = []
    seen: set[str] = set()
    for item in data.get("characters", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        desc = str(item.get("description", "")).strip()
        role = str(item.get("role", "supporting")).strip().lower() or "supporting"
        if not name or not desc:
            continue
        key = name.lower()
        if key in seen:
            continue
        if role not in {"protagonist", "antagonist", "supporting"}:
            role = "supporting"
        characters.append(
            {
                "name": name,
                "description": desc,
                "role": role,
            }
        )
        seen.add(key)
    return characters


def _collect_seed_plan(data: dict, default_style: str, default_bgm: str) -> dict:
    if not isinstance(data, dict):
        return {"style": default_style, "bgm_mood": default_bgm, "scenes": []}
    return {
        "style": _normalize_style_name(data.get("style", ""), default_style),
        "bgm_mood": _normalize_bgm_mood(data.get("bgm_mood", ""), default_bgm),
        "scenes": _collect_seed_scenes(data),
    }


def _collect_series_seed_plan(data: dict, default_style: str, default_bgm: str) -> dict:
    if not isinstance(data, dict):
        return {
            "style": default_style,
            "bgm_mood": default_bgm,
            "series_total_parts": 0,
            "characters": [],
            "parts": [],
        }

    raw_parts = data.get("parts", [])
    parts: list[dict] = []
    if isinstance(raw_parts, list):
        for idx, part in enumerate(raw_parts, start=1):
            if not isinstance(part, dict):
                continue
            part_no = part.get("part")
            if not isinstance(part_no, int) or part_no < 1:
                part_no = idx
            parts.append(
                {
                    "part": part_no,
                    "part_focus": str(part.get("part_focus", "")).strip(),
                    "cliffhanger": part.get("cliffhanger"),
                    "scenes": _collect_seed_scenes(part),
                }
            )

    series_total_parts = data.get("series_total_parts")
    if not isinstance(series_total_parts, int) or series_total_parts < 2:
        series_total_parts = len(parts)

    return {
        "style": _normalize_style_name(data.get("style", ""), default_style),
        "bgm_mood": _normalize_bgm_mood(data.get("bgm_mood", ""), default_bgm),
        "series_total_parts": series_total_parts,
        "characters": _collect_characters(data),
        "parts": sorted(parts, key=lambda x: x.get("part", 0)),
    }


def generate_narration_plan(
    research_brief: dict,
    forced_style_name: str | None = None,
    forced_bgm_mood: str | None = None,
) -> dict:
    """단편/단일 에피소드용 선행 나레이션+씬 시드 + 스타일/BGM을 생성한다."""
    rb = research_brief or {}

    style_names = sorted(list_styles())
    default_style = (
        _normalize_style_name(rb.get("style_suggestion", ""), "casual")
        if style_names else "casual"
    )
    default_bgm = "dramatic" if str(rb.get("story_type", "")).strip() in {"revenge", "drama", "mystery"} else "funny"

    if forced_style_name:
        default_style = _normalize_style_name(forced_style_name, default_style)
    if forced_bgm_mood:
        default_bgm = _normalize_bgm_mood(forced_bgm_mood, default_bgm)

    styles_block, bgm_block = _build_style_and_bgm_blocks(style_names)

    original_story = str(rb.get("original_story", "")).strip()

    brief_context = {
        "topic": rb.get("topic", ""),
        "story_type": rb.get("story_type", ""),
        "source_region": rb.get("source_region", "한국"),
        "original_title": rb.get("original_title", ""),
        "original_story": original_story,
        "style_suggestion": rb.get("style_suggestion", ""),
    }

    prompt = f"""
You are an expert Korean YouTube Shorts creator, story planner, and narrator.
This function is for one standalone episode.
Read topic + original_title + original_story, then produce the scene flow and narration.

Core requirements:
- You specialize in building highly engaging short-form stories that maximize viewer retention and curiosity.
- Build a short-form story flow that fits this specific story and keeps viewers watching to the end.
- Create narration and story flow that make viewers curious, engaged, and willing to keep watching.
- Make the episode easy to follow, immersive, and compelling as a YouTube Shorts narrative.
- Preserve factual anchors from original_title/original_story while retelling in natural Korean.
- Research may contain exact real-world names, but public-facing narration/scene text should usually generalize overly specific station/store/school/company/place names unless that specificity is essential to understanding the story.
- Choose {MIN_SCENES}~{MAX_SCENES} scenes based on the actual story. Prefer 9~10 scenes unless the story is truly simple.
- Aim for roughly 45~58 seconds total by balancing scene count and narration density.
- Use natural spoken Korean. Avoid stiff written tone.
- Keep narration concise but not overly compressed. Let each scene breathe naturally when the story needs it.
- If you include direct quoted speech, write it as natural spoken Korean that could actually be said aloud, not dictionary-form or citation-style wording.
- If a quote is not important as a direct spoken line, prefer paraphrasing it smoothly into narration instead of preserving stiff quoted wording from the source.
- Prefer lightly generalized public wording such as "서울의 한 지하철역", "한 패스트푸드 매장", "회사" instead of exposing exact identifiable real-world place or brand names from the source.
- Choose narrative person (1인칭/3인칭) that best fits the story and keep it mostly consistent.
- Keep relationship labels consistent across scenes. Do not confuse girlfriend, fiancee, wife, husband, mother, father, boss, coworker, etc.
- Ensure each scene adds meaningful progression (new info, escalation, consequence, emotional turn, or payoff setup).
- Build pacing from this story's own tension/payoff; avoid generic boilerplate beats.
- Avoid repetitive sentence openings/patterns across scenes.
- Do not copy long phrases from original_story verbatim.

Ending rules:
- The final scene should end on story payoff and a short aftermath, aftershock, or emotional landing inside the story world.
- Do not end with a meta label, category tag, or channel-style commentary about what kind of story this was.
- The final line should feel like the story's closing moment, not an external summary or narrator sign-off.

Style candidates (choose one):
{styles_block}

BGM candidates (choose one):
{bgm_block}

Selection rules:
- Pick one style and one bgm_mood that best fit this story's tone and pacing.
- If style_suggestion is reasonable, prefer it.
- If forced style/bgm is provided below, you must use it exactly.

Forced constraints:
- forced_style_name: {json.dumps(forced_style_name, ensure_ascii=False)}
- forced_bgm_mood: {json.dumps(forced_bgm_mood, ensure_ascii=False)}

For each scene, output:
- index: 0-based
- narration: Korean 1~2 sentences
- scene_outline: Korean 1 sentence factual summary
- image_intent: Korean short visual focus
- setting_hint: Korean short place/time/era cue
- emotion_beat: Korean core emotion word/phrase
- action_beat: Korean short action phrase

Brief context:
{json.dumps(brief_context, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "style": "one of available style names",
  "bgm_mood": "one of {json.dumps(list(BGM_OPTIONS.keys()), ensure_ascii=False)}",
  "scenes": [
    {{
      "index": 0,
      "narration": "...",
      "scene_outline": "...",
      "image_intent": "...",
      "setting_hint": "...",
      "emotion_beat": "...",
      "action_beat": "..."
    }}
  ]
}}
"""

    last_error = ""
    retry_prompt = prompt
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            last_error = ""
            response = client.models.generate_content(model=MODEL, contents=retry_prompt)
            data = _parse_json(response.text)
            plan = _collect_seed_plan(
                data,
                default_style=default_style,
                default_bgm=default_bgm,
            )
            seed_scenes = plan.get("scenes", [])
            if MIN_SCENES <= len(seed_scenes) <= MAX_SCENES:
                last_scene = seed_scenes[-1] if seed_scenes else {}
                last_narration = str(last_scene.get("narration", "")).strip()
                if not last_narration:
                    last_error = "missing final-scene narration"
                elif _looks_like_meta_ending(last_narration):
                    last_error = f"final-scene narration is too meta/generic: {last_narration}"
                else:
                    return plan
            if not last_error:
                last_error = (
                    f"invalid scene count: {len(seed_scenes)} "
                    f"(need {MIN_SCENES}~{MAX_SCENES})"
                )
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous output was invalid ({last_error}). "
                f"Return strict JSON with style, bgm_mood, and {MIN_SCENES}~{MAX_SCENES} complete scenes. "
                "End the final scene on story payoff/aftershock inside the story world, not on a meta label or commentary."
            )
        except Exception as e:
            last_error = str(e)
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous output failed ({last_error}). "
                "Return strict JSON only."
            )

    raise RuntimeError(
        f"Narration plan generation failed after {MAX_RETRIES} attempts. detail={last_error or 'invalid output'}"
    )


def generate_series_narration_plan(
    research_brief: dict,
    forced_style_name: str | None = None,
    forced_bgm_mood: str | None = None,
) -> dict:
    """시리즈(다편)용: part 구조(part_focus/cliffhanger) + 전편 시드를 한 번에 생성한다."""
    rb = research_brief or {}
    original_story = str(rb.get("original_story", "")).strip()
    if not original_story:
        raise ValueError("series narration requires non-empty original_story")

    source_len_total = len(original_story)
    recommended_parts = 3 if source_len_total >= 2200 else 2

    style_names = sorted(list_styles())
    default_style = (
        _normalize_style_name(rb.get("style_suggestion", ""), "casual")
        if style_names else "casual"
    )
    default_bgm = (
        "dramatic"
        if str(rb.get("story_type", "")).strip() in {"revenge", "drama", "mystery"}
        else "funny"
    )

    if forced_style_name:
        default_style = _normalize_style_name(forced_style_name, default_style)
    if forced_bgm_mood:
        default_bgm = _normalize_bgm_mood(forced_bgm_mood, default_bgm)

    styles_block, bgm_block = _build_style_and_bgm_blocks(style_names)

    parts_hint = rb.get("series_parts", [])
    if not isinstance(parts_hint, list):
        parts_hint = []
    normalized_parts_hint = []
    for idx, p in enumerate(parts_hint, start=1):
        if not isinstance(p, dict):
            continue
        normalized_parts_hint.append(
            {
                "part": idx,
                "part_focus": str(p.get("part_focus", "")).strip(),
                "cliffhanger": p.get("cliffhanger"),
            }
        )

    brief_context = {
        "topic": rb.get("topic", ""),
        "story_type": rb.get("story_type", ""),
        "source_region": rb.get("source_region", "한국"),
        "original_title": rb.get("original_title", ""),
        "original_story": original_story,
        "style_suggestion": rb.get("style_suggestion", ""),
        "series_potential": rb.get("series_potential", True),
        "recommended_series_total_parts": recommended_parts,
        "series_parts_hint_from_researcher": normalized_parts_hint,
    }

    prompt = f"""
You are an expert Korean YouTube Shorts creator, series planner, and narrator.
Create the series structure and narration plans for all parts in one pass.

Core requirements:
- You specialize in designing short-form series that maximize viewer retention, immersion, and next-part intent.
- Keep cross-part story continuity stable.
- Make each part easy to follow and worth watching on its own.
- Make non-final part endings strong enough that viewers want the next part.
- Design the series as short-form storytelling, so each part feels immersive and compelling to watch through.
- Create narration and story flow that make viewers curious, engaged, and eager to continue watching the series.
- Research may contain exact real-world names, but public-facing narration/scene text should usually generalize overly specific station/store/school/company/place names unless that specificity is essential to understanding the story.

Global rules:
- Decide series_total_parts as 2 or 3 based on story density (recommended: {recommended_parts}).
- Output exactly series_total_parts parts, numbered 1..series_total_parts.
- For each part, choose {MIN_SCENES}~{MAX_SCENES} scenes based on that part's actual event density and pacing. Prefer 8~9 scenes unless the part is clearly event-dense.
- Aim for roughly 40~55 seconds per part by balancing scene count and narration density.
- Use natural spoken Korean (not stiff written tone).
- Keep narration concise but not overly compressed. Let each scene breathe naturally when the story needs it.
- If you include direct quoted speech, write it as natural spoken Korean that could actually be said aloud, not dictionary-form or citation-style wording.
- If a quote is not important as a direct spoken line, prefer paraphrasing it smoothly into narration instead of preserving stiff quoted wording from the source.
- Prefer lightly generalized public wording such as "서울의 한 지하철역", "한 패스트푸드 매장", "회사" instead of exposing exact identifiable real-world place or brand names from the source.
- Keep factual anchors aligned with original_title/original_story.
- Keep relationship labels consistent across parts and scenes. Do not confuse girlfriend, fiancee, wife, husband, mother, father, boss, coworker, etc.
- Avoid repetitive sentence openings/patterns.
- Do not copy long phrases from original_story verbatim.
- You are an expert Shorts storyteller. Design each part to maximize viewer retention and next-part intent for this specific story.
- Ensure every scene contributes meaningful progress (information, tension, consequence, emotional shift, or payoff setup).

Character pool rules:
- Identify the core recurring characters across the whole series before planning parts.
- Output only story-critical recurring characters, not background extras or unnamed crowd members.
- Use stable English ASCII names that can be reused across all parts.
- Character descriptions must be concrete and visually specific enough for character sheet generation and cross-scene identity consistency.
- Each character description should usually include cultural context/nationality, approximate age, gender, hair, face or build cues, a typical baseline outfit style, and one or two distinctive traits.
- Character descriptions must focus on stable identity/appearance, not temporary scene-specific states.
- Do not lock one-scene outfits or conditions into global character descriptions (for example: wedding dress, naked, soaked, injured, covering body) unless that look is iconic across most of the series.
- Scene-specific wardrobe changes still belong in per-scene cues, so global description should support recognition without overriding scene wardrobe.
- Relationship distinctions matter. Do not conflate girlfriend, fiancee, wife, mother, father, boss, coworker, etc.

Structure rules:
- You must generate for each part:
  - part_focus: what this part covers (short Korean text)
  - cliffhanger: non-final parts only, final part is null
- part_focus/cliffhanger is determined by Narrator, not Researcher.

Part-ending rules (very important):
- For non-final parts: do NOT fully resolve the core conflict.
- For non-final parts: the last scene narration itself must function as the cliffhanger.
- For non-final parts: last scene must end with unresolved tension and a concrete curiosity hook.
- The `cliffhanger` field should summarize the unresolved question or reveal promised by that final scene.
- The cliffhanger must make viewers wonder "what happens next?" with specific unresolved info/stakes.
- Avoid generic weak endings like only "다음 편에서 계속" or flat summary endings that just say a setup was completed.
- Final part should end on clear payoff and a short aftershock or callback, not on a category label or channel-style commentary.
- For final part: set cliffhanger to null.

Style candidates (choose one):
{styles_block}

BGM candidates (choose one):
{bgm_block}

Selection rules:
- Pick one style and one bgm_mood for the whole series.
- If style_suggestion is reasonable, prefer it.
- If forced style/bgm is provided below, you must use it exactly.

Forced constraints:
- forced_style_name: {json.dumps(forced_style_name, ensure_ascii=False)}
- forced_bgm_mood: {json.dumps(forced_bgm_mood, ensure_ascii=False)}

For each scene in each part, output:
- index: 0-based
- narration: Korean 1~2 sentences
- scene_outline: Korean 1 sentence factual summary
- image_intent: Korean short visual focus
- setting_hint: Korean short place/time/era cue
- emotion_beat: Korean core emotion word/phrase
- action_beat: Korean short action phrase

Brief context:
{json.dumps(brief_context, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "style": "one of available style names",
  "bgm_mood": "one of {json.dumps(list(BGM_OPTIONS.keys()), ensure_ascii=False)}",
  "series_total_parts": 2,
  "characters": [
    {{
      "name": "stable English ASCII character name",
      "description": "English stable identity/appearance description",
      "role": "protagonist|antagonist|supporting"
    }}
  ],
  "parts": [
    {{
      "part": 1,
      "part_focus": "part focus text",
      "cliffhanger": "next-part hook or null",
      "scenes": [
        {{
          "index": 0,
          "narration": "...",
          "scene_outline": "...",
          "image_intent": "...",
          "setting_hint": "...",
          "emotion_beat": "...",
          "action_beat": "..."
        }}
      ]
    }}
  ]
}}
"""

    last_error = ""
    retry_prompt = prompt
    banned_generic_cliffhangers = {
        "다음 편에서 계속",
        "다음편에서 계속",
        "다음 편에서",
        "다음편에서",
        "계속",
    }
    banned_generic_last_lines = {
        "다음 편에서 계속.",
        "다음편에서 계속.",
        "다음 편에서 계속",
        "다음편에서 계속",
        "계속.",
        "계속",
    }
    for _attempt in range(1, MAX_RETRIES + 1):
        try:
            last_error = ""
            response = client.models.generate_content(model=MODEL, contents=retry_prompt)
            data = _parse_json(response.text)
            plan = _collect_series_seed_plan(
                data,
                default_style=default_style,
                default_bgm=default_bgm,
            )
            total_parts = plan.get("series_total_parts")
            parts = plan.get("parts", [])
            characters = plan.get("characters", [])
            if not isinstance(total_parts, int) or total_parts not in {2, 3}:
                last_error = f"series_total_parts must be 2 or 3 (got {repr(total_parts)})"
            elif not isinstance(characters, list) or not characters:
                last_error = "missing series characters"
            elif len(parts) != total_parts:
                last_error = f"invalid part count: {len(parts)} (need {total_parts})"
            else:
                valid = True
                for idx, part in enumerate(parts, start=1):
                    if part.get("part") != idx:
                        valid = False
                        last_error = f"invalid part numbering at idx={idx}, got={part.get('part')}"
                        break
                    if not str(part.get("part_focus", "")).strip():
                        valid = False
                        last_error = f"missing part_focus for part {idx}"
                        break
                    scene_count = len(part.get("scenes", []))
                    if not (MIN_SCENES <= scene_count <= MAX_SCENES):
                        valid = False
                        last_error = f"invalid scene count for part {idx}: {scene_count}"
                        break
                    cliffhanger = part.get("cliffhanger")
                    if idx < total_parts:
                        cliff_text = str(cliffhanger or "").strip()
                        if not cliff_text:
                            valid = False
                            last_error = f"missing cliffhanger for non-final part {idx}"
                            break
                        if cliff_text in banned_generic_cliffhangers:
                            valid = False
                            last_error = (
                                f"cliffhanger too generic for part {idx}: {cliff_text}"
                            )
                            break
                        scenes = part.get("scenes", [])
                        last_scene = scenes[-1] if scenes else {}
                        last_narration = str(last_scene.get("narration", "")).strip()
                        if not last_narration:
                            valid = False
                            last_error = f"missing last-scene narration for non-final part {idx}"
                            break
                        if last_narration in banned_generic_last_lines:
                            valid = False
                            last_error = (
                                f"last-scene narration too generic for non-final part {idx}: "
                                f"{last_narration}"
                            )
                            break
                    else:
                        if cliffhanger not in (None, "", "null"):
                            valid = False
                            last_error = (
                                f"final part cliffhanger must be null/empty, got {repr(cliffhanger)}"
                            )
                            break
                        scenes = part.get("scenes", [])
                        last_scene = scenes[-1] if scenes else {}
                        last_narration = str(last_scene.get("narration", "")).strip()
                        if not last_narration:
                            valid = False
                            last_error = "missing last-scene narration for final part"
                            break
                        if _looks_like_meta_ending(last_narration):
                            valid = False
                            last_error = (
                                "final part ending is too meta/generic: "
                                f"{last_narration}"
                            )
                            break
                if valid:
                    return plan

            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous output was invalid ({last_error}). "
                "Return strict JSON only. Keep part numbering 1..N, "
                f"{MIN_SCENES}~{MAX_SCENES} scenes per part, make non-final cliffhangers specific/curiosity-driven, "
                "ensure the last narration of each non-final part itself ends on the cliffhanger beat, "
                "and ensure the final part ends on payoff/aftershock inside the story world rather than a meta label or commentary."
            )
        except Exception as e:
            last_error = str(e)
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous output failed ({last_error}). "
                "Return strict JSON only."
            )

    raise RuntimeError(
        "Series narration plan generation failed after "
        f"{MAX_RETRIES} attempts. detail={last_error or 'invalid output'}"
    )
