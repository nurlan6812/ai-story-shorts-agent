"""Image Agent - Director 구조 플랜을 이미지 생성 질의로 변환"""

import json
from google import genai
from config.settings import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-pro-preview"


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {}


def generate_image_queries(
    scenes: list[dict],
    characters: list[dict] | None = None,
    research_brief: dict | None = None,
) -> list[dict]:
    """scene_outline 기반으로 image_query를 생성해 scenes에 주입."""
    if not scenes:
        return scenes

    source_region = (research_brief or {}).get("source_region", "한국")
    original_title = (research_brief or {}).get("original_title", "")
    original_story = (research_brief or {}).get("original_story", "")

    scene_payload = []
    for i, s in enumerate(scenes):
        outline = s.get("scene_outline") or s.get("narration") or s.get("summary") or ""
        world_context = s.get("world_context", {})
        if not isinstance(world_context, dict):
            world_context = {}
        if not str(world_context.get("source_region", "")).strip():
            world_context["source_region"] = source_region

        scene_payload.append(
            {
                "index": i,
                "narration": s.get("narration", ""),
                "scene_outline": outline,
                "image_intent": s.get("image_intent", ""),
                "setting_hint": s.get("setting_hint", ""),
                "emotion_beat": s.get("emotion_beat", ""),
                "action_beat": s.get("action_beat", ""),
                "cast": s.get("cast", []),
                "character_beats": s.get("character_beats", []),
                "continuity_state": s.get("continuity_state", {}),
                "shot_plan": s.get("shot_plan", {}),
                "world_context": world_context,
                "camera": s.get("camera", {}),
            }
        )

    prompt = f"""
You are an image prompt designer for a short-form story pipeline.
Write one English image_query per scene. Keep scene order unchanged.

Rules:
- Use only English for image_query.
- Include era/background cues when possible (e.g. 1990s, present day, historical Korea).
- Reflect source region context: {source_region}.
- Scene priority: scene_outline + narration define the event meaning; cast, continuity_state, shot_plan, world_context, setting_hint, and image_intent define the visual ground truth; original_title/original_story are supporting context only and must not override scene metadata chosen by narrator/director.
- If image_intent/setting_hint/emotion_beat/action_beat/character_beats are missing or weak, infer and fill them.
- Use cast as the primary character set for the scene. Do not introduce unrelated named characters.
- If characters appear, use exact English names from character list.
- Avoid narration/script language; keep it visual.
- Output concise but specific prompts.
- Keep visuals clear and easy to follow.
- Use setting_hint/emotion_beat/action_beat and character_beats to keep scene intent, expression, pose, and gaze explicit.
- Follow continuity_state for location/outfit/props continuity unless the timeline clearly changes. If continuity_state.wardrobe_state exists, translate it into natural visible clothing/state cues; if it conflicts with a stable profile, preserve the same identity but follow the scene-specific wardrobe.
- Reflect shot_plan (shot_type, camera_angle, composition), world_context (source_region, era_hint, cultural_markers), and camera.type/speed as visual framing or motion cues.
- Do not invent or reintroduce exact real-world station/store/school/company/place names in image_query unless they are absolutely essential; prefer generic visual phrasing like "a Korean subway station" or "a fast-food restaurant".
- Do not add global style wrapper text (prefix/suffix are attached later by runtime).
- Do not add watermark/text/logo instructions.

Original title context: "{original_title}"
Original story context: "{original_story}"

Characters:
{json.dumps(characters or [], ensure_ascii=False, indent=2)}

Scenes:
{json.dumps(scene_payload, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "scenes": [
    {{
      "index": <int>,
      "image_query": "...",
      "image_intent": "Korean short visual focus",
      "setting_hint": "Korean short place/time/era cue",
      "emotion_beat": "Korean core emotion",
      "action_beat": "Korean short action",
      "cast": ["character name from list"],
      "character_beats": [
        {{
          "name": "character name from list",
          "emotion": "English emotion keyword",
          "intensity": "low|medium|high",
          "facial_expression": "English expression cue",
          "pose": "English pose cue",
          "gaze_target": "character/object/background"
        }}
      ]
    }}
  ]
}}
"""

    updates: dict[int, dict] = {}
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        data = _parse_json(response.text)
        for item in data.get("scenes", []):
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            q = str(item.get("image_query", "")).strip()
            if not isinstance(idx, int):
                continue
            updates[idx] = {
                "image_query": q,
                "image_intent": str(item.get("image_intent", "")).strip(),
                "setting_hint": str(item.get("setting_hint", "")).strip(),
                "emotion_beat": str(item.get("emotion_beat", "")).strip(),
                "action_beat": str(item.get("action_beat", "")).strip(),
                "cast": item.get("cast", []),
                "character_beats": item.get("character_beats", []),
            }
    except Exception:
        updates = {}

    new_scenes = []
    for i, s in enumerate(scenes):
        new_s = dict(s)
        item = updates.get(i, {})
        updated_query = str(item.get("image_query", "")).strip() if isinstance(item, dict) else ""
        if updated_query:
            new_s["image_query"] = updated_query
        else:
            fallback = str(new_s.get("image_query", "")).strip()
            if not fallback:
                parts = [
                    str(new_s.get("scene_outline", "")).strip(),
                    str(new_s.get("image_intent", "")).strip(),
                    str(new_s.get("setting_hint", "")).strip(),
                    str(new_s.get("emotion_beat", "")).strip(),
                    str(new_s.get("action_beat", "")).strip(),
                ]
                fallback = ", ".join([p for p in parts if p])
            new_s["image_query"] = fallback

        # Director-lite를 지원하기 위해 이미지 관련 힌트는 Image Agent가 보강한다.
        for key in ("image_intent", "setting_hint", "emotion_beat", "action_beat"):
            if str(new_s.get(key, "")).strip():
                continue
            if isinstance(item, dict):
                val = str(item.get(key, "")).strip()
                if val:
                    new_s[key] = val

        cast = new_s.get("cast")
        if (not isinstance(cast, list) or not cast) and isinstance(item, dict):
            inferred_cast = item.get("cast")
            if isinstance(inferred_cast, list) and inferred_cast:
                new_s["cast"] = [str(name).strip() for name in inferred_cast if str(name).strip()]

        beats = new_s.get("character_beats")
        if (not isinstance(beats, list) or not beats) and isinstance(item, dict):
            inferred_beats = item.get("character_beats")
            if isinstance(inferred_beats, list) and inferred_beats:
                new_s["character_beats"] = inferred_beats
        new_scenes.append(new_s)

    return new_scenes
