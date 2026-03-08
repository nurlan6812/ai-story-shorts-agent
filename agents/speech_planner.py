"""Speech Planner - 나레이션/대사 분리 + 화자별 보이스 매핑"""

import json
import re
from typing import Any

from google import genai
from config.settings import (
    GEMINI_API_KEY,
    TTS_NARRATOR_VOICE,
    TTS_MALE_VOICE,
    TTS_FEMALE_VOICE,
    TTS_BOY_VOICE,
    TTS_GIRL_VOICE,
    TTS_ELDER_MALE_VOICE,
    TTS_ELDER_FEMALE_VOICE,
)

MODEL = "gemini-3.1-pro-preview"
MAX_LLM_RETRIES = 4
client = genai.Client(api_key=GEMINI_API_KEY)

# 보이스 정책
VOICE_NARRATOR = TTS_NARRATOR_VOICE
VOICE_MALE = TTS_MALE_VOICE
VOICE_FEMALE = TTS_FEMALE_VOICE
VOICE_BOY = TTS_BOY_VOICE
VOICE_GIRL = TTS_GIRL_VOICE
VOICE_ELDER_MALE = TTS_ELDER_MALE_VOICE
VOICE_ELDER_FEMALE = TTS_ELDER_FEMALE_VOICE
VOICE_NEUTRAL = TTS_NARRATOR_VOICE

MALE_HINTS = [
    " male", " man", " boy", "father", "dad", "husband", "brother", "son",
    "남성", "남자", "아빠", "아버지", "남편", "형", "오빠", "아들",
]
FEMALE_HINTS = [
    " female", " woman", " girl", "mother", "mom", "wife", "sister", "daughter",
    "여성", "여자", "엄마", "어머니", "아내", "누나", "언니", "딸",
]
CHILD_HINTS = [
    " child", " kid", " teen", " teenage", "학생", "초등", "중학생", "고등학생", "10대", "어린", "유아",
]
SENIOR_HINTS = [
    " elderly", " senior", " old man", " old woman", " grandfather", " grandmother",
    "할아버지", "할머니", "노인", "어르신", "장년", "중년",
]

def _parse_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {}


def _infer_gender(text: str) -> str:
    low = f" {text.lower()} "
    male = any(h in low for h in MALE_HINTS)
    female = any(h in low for h in FEMALE_HINTS)
    if male and not female:
        return "male"
    if female and not male:
        return "female"
    return "neutral"


def _infer_age_bucket(text: str) -> str:
    low = f" {text.lower()} "
    if any(h in low for h in CHILD_HINTS):
        return "child"
    if any(h in low for h in SENIOR_HINTS):
        return "senior"

    ages: list[int] = []
    for m in re.finditer(r"\b(\d{1,2})\s*s\b", low):
        try:
            ages.append(int(m.group(1)))
        except Exception:
            pass
    for m in re.finditer(r"(\d{1,2})\s*(?:살|대)", text):
        try:
            ages.append(int(m.group(1)))
        except Exception:
            pass
    if not ages:
        return "adult"

    age = min(ages)
    if age <= 19:
        return "child"
    if age >= 60:
        return "senior"
    return "adult"


def _normalize_name(value: Any) -> str:
    return str(value or "").strip()


def _build_character_index(characters: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}

    for char in characters:
        if not isinstance(char, dict):
            continue
        name = _normalize_name(char.get("name"))
        if not name:
            continue
        desc = _normalize_name(char.get("description"))
        low_name = name.lower()
        low_desc = desc.lower()

        gender = _infer_gender(f"{low_name} {low_desc}")
        age_bucket = _infer_age_bucket(f"{low_name} {low_desc}")
        index[name] = {
            "name": name,
            "gender": gender,
            "age_bucket": age_bucket,
            "description": desc,
            "role": _normalize_name(char.get("role")).lower(),
        }

    return index


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _normalize_for_equivalence(text: str) -> str:
    """세그먼트 병합 텍스트와 원문 narration의 동치 비교용 정규화."""
    t = _clean_text(text).lower()
    # 따옴표/문장부호/공백 제거 후 비교 (의미 재작성 탐지 목적)
    t = re.sub(r"[\"'“”‘’「」『』]", "", t)
    t = re.sub(r"[\s\.,!?~…:;·\-_()/\[\]{}]", "", t)
    return t


def _segments_equivalent_to_narration(segments: list[dict], narration: str) -> bool:
    merged = " ".join(
        _normalize_name(seg.get("text"))
        for seg in segments
        if isinstance(seg, dict)
    )
    return _normalize_for_equivalence(merged) == _normalize_for_equivalence(narration)


def _choose_voice(gender: str, age_bucket: str) -> str:
    if age_bucket == "child":
        if gender == "male":
            return VOICE_BOY
        if gender == "female":
            return VOICE_GIRL
        return VOICE_GIRL
    if age_bucket == "senior":
        if gender == "male":
            return VOICE_ELDER_MALE
        if gender == "female":
            return VOICE_ELDER_FEMALE
        return VOICE_ELDER_FEMALE
    if gender == "male":
        return VOICE_MALE
    if gender == "female":
        return VOICE_FEMALE
    return VOICE_NEUTRAL


def _build_voice_map(
    character_index: dict[str, dict],
    previous_voice_map: dict | None = None,
) -> dict[str, str]:
    voice_map: dict[str, str] = {}
    prev = previous_voice_map if isinstance(previous_voice_map, dict) else {}

    narrator_default = VOICE_NARRATOR
    protagonist_metas = [
        meta
        for _, meta in sorted(character_index.items(), key=lambda x: x[0])
        if str(meta.get("role", "")).lower() == "protagonist"
    ]
    if protagonist_metas:
        pm = protagonist_metas[0]
        narrator_default = _choose_voice(
            gender=str(pm.get("gender", "neutral")),
            age_bucket=str(pm.get("age_bucket", "adult")),
        )

    # narrator 기본 보이스: 이전 편 유지 > protagonist 기반 자동 선택 > 설정값
    voice_map["narrator"] = str(prev.get("narrator", narrator_default))

    for name, meta in character_index.items():
        if name in prev and str(prev[name]).strip():
            voice_map[name] = str(prev[name]).strip()
            continue
        gender = str(meta.get("gender", "neutral"))
        age_bucket = str(meta.get("age_bucket", "adult"))
        voice_map[name] = _choose_voice(gender, age_bucket)

    return voice_map


def _build_delivery_hint(
    speaker: str,
    seg_type: str,
    character_index: dict[str, dict],
) -> str:
    if speaker == "narrator":
        return (
            "Speak in natural Korean narration style. "
            "Clear pacing, conversational tone, no exaggerated acting."
        )

    meta = character_index.get(speaker, {})
    gender = str(meta.get("gender", "neutral"))
    age_bucket = str(meta.get("age_bucket", "adult"))

    age_desc = "adult"
    if age_bucket == "child":
        age_desc = "young"
    elif age_bucket == "senior":
        age_desc = "elderly"

    gender_desc = "neutral"
    if gender == "male":
        gender_desc = "male"
    elif gender == "female":
        gender_desc = "female"

    base = (
        f"Speak this as a {age_desc} {gender_desc} Korean character voice. "
        "Keep pronunciation clear and emotionally natural."
    )
    if seg_type == "dialogue":
        return base + " Dialogue should feel direct and in-character."
    return base + " Keep it concise and flowing with scene narration."


def _split_all_scenes_speech_with_llm(
    scenes: list[dict],
    character_index: dict[str, dict],
) -> dict[int, list[dict]]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Speech Planner requires GEMINI_API_KEY for LLM-only segmentation.")

    characters = sorted(character_index.keys())
    allowed_speakers = ["narrator", *characters]
    character_profiles = [
        {
            "name": name,
            "role": str(meta.get("role", "")),
            "gender": str(meta.get("gender", "")),
            "age_bucket": str(meta.get("age_bucket", "")),
        }
        for name, meta in sorted(character_index.items(), key=lambda x: x[0])
    ]

    scene_payload = []
    for i, scene in enumerate(scenes):
        s = scene if isinstance(scene, dict) else {}
        cast = s.get("cast")
        if not isinstance(cast, list):
            cast = []
        scene_payload.append(
            {
                "scene_index": i,
                "narration": _normalize_name(s.get("narration")),
                "scene_outline": _normalize_name(s.get("scene_outline")),
                "image_intent": _normalize_name(s.get("image_intent")),
                "cast": [str(c).strip() for c in cast if str(c).strip()],
            }
        )

    prompt = f"""
You are a speech segmentation assistant for Korean Shorts TTS.
Split all scenes into ordered speech segments in one pass.

Rules:
- Process each scene independently, but return one combined JSON response.
- Preserve original meaning and order.
- Perform segmentation only. Do not rewrite, paraphrase, summarize, or add words.
- Segment text must be copied as exact spans from input narration.
- Split narrator text and dialogue only when explicit quote delimiters exist in input text.
- Allowed explicit quote delimiters: "", '', “”, ‘’, 「」, 『』.
- If explicit quote delimiters do not exist, return exactly one segment:
  type="narration", speaker="narrator", text=<full original narration>.
- Even if quote delimiters exist, keep the full line as narration unless the quoted text is clearly a directly spoken utterance in the scene.
- Treat reported or embedded expressions as narration when the sentence is describing what someone said, wrote, posted, or left behind rather than presenting live spoken dialogue.
- Treat quoted text as narration when it functions as a reported phrase, embedded wording, title, post text, or explanatory expression rather than live spoken dialogue.
- Treat quoted text as dialogue only when scene context clearly indicates the character is directly speaking that utterance in the moment.
- When in doubt, prefer one narration segment over splitting into dialogue.
- Use scene_outline/image_intent/cast as context to infer the most plausible speaker.
- type must be either "narration" or "dialogue".
- speaker must be one of: {json.dumps(allowed_speakers, ensure_ascii=False)}.
- If uncertain, set speaker to "narrator".
- Do not invent new speakers.
- Do not drop scenes. Keep scene_index exactly as input.
- Concatenate all segment texts in original order so they are equivalent to source narration.

Input:
{json.dumps({"characters": character_profiles, "scenes": scene_payload}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "scenes": [
    {{
      "scene_index": 0,
      "segments": [
        {{
          "type": "narration|dialogue",
          "speaker": "narrator or character name",
          "text": "segment text"
        }}
      ]
    }}
  ]
}}
"""

    last_error = "invalid or empty response"
    for _ in range(MAX_LLM_RETRIES):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            data = _parse_json(resp.text)
            raw_scenes = data.get("scenes")
            if not isinstance(raw_scenes, list):
                last_error = "scenes is not a list"
                continue

            out_map: dict[int, list[dict]] = {}
            for item in raw_scenes:
                if not isinstance(item, dict):
                    continue
                try:
                    scene_index = int(item.get("scene_index"))
                except Exception:
                    continue
                if scene_index < 0 or scene_index >= len(scenes):
                    continue

                raw_segments = item.get("segments")
                if not isinstance(raw_segments, list):
                    continue

                normalized_segments: list[dict] = []
                for seg in raw_segments:
                    if not isinstance(seg, dict):
                        continue
                    seg_type = str(seg.get("type", "narration")).strip().lower()
                    if seg_type not in {"narration", "dialogue"}:
                        seg_type = "narration"
                    speaker = _normalize_name(seg.get("speaker")) or "narrator"
                    if speaker not in allowed_speakers:
                        speaker = "narrator"
                    seg_text = _clean_text(seg.get("text", ""))
                    if not seg_text:
                        continue
                    normalized_segments.append(
                        {"type": seg_type, "speaker": speaker, "text": seg_text}
                    )
                out_map[scene_index] = normalized_segments

            if out_map:
                return out_map
            last_error = "no valid scenes after normalization"
        except Exception:
            last_error = "llm call or parse failed"
            continue
    raise RuntimeError(
        "Speech Planner global segmentation failed "
        f"after {MAX_LLM_RETRIES} retries: {last_error}"
    )


def plan_speech(
    scenes: list[dict],
    characters: list[dict],
    previous_voice_map: dict | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """장면 나레이션을 narration/dialogue 세그먼트로 분해하고 보이스 맵을 생성한다."""
    character_index = _build_character_index(characters)
    voice_map = _build_voice_map(character_index, previous_voice_map=previous_voice_map)
    scene_segment_map = _split_all_scenes_speech_with_llm(
        scenes=scenes,
        character_index=character_index,
    )

    planned_scenes: list[dict] = []
    for i, scene in enumerate(scenes):
        s = dict(scene) if isinstance(scene, dict) else {}
        narration = _normalize_name(s.get("narration"))
        llm_segments = scene_segment_map.get(i, [])
        segments = llm_segments

        if narration:
            if not segments:
                # 전체 호출 결과에서 빠진 장면은 narration 단일 세그먼트로 보정
                segments = [{"type": "narration", "speaker": "narrator", "text": narration}]
            # LLM이 재작성/환각한 경우 narration 단일 세그먼트로 강등
            if not _segments_equivalent_to_narration(segments, narration):
                segments = [{"type": "narration", "speaker": "narrator", "text": narration}]

        # 화자 정합: 모르는 speaker는 narrator로 폴백
        fixed = []
        for seg in segments:
            seg_type = _normalize_name(seg.get("type")) or "narration"
            speaker = _normalize_name(seg.get("speaker")) or "narrator"
            if speaker != "narrator" and speaker not in character_index:
                speaker = "narrator"
            delivery_hint = _build_delivery_hint(
                speaker=speaker,
                seg_type=seg_type,
                character_index=character_index,
            )
            fixed.append(
                {
                    "type": seg_type,
                    "speaker": speaker,
                    "text": _normalize_name(seg.get("text")),
                    "delivery_hint": delivery_hint,
                }
            )
        s["speech_segments"] = fixed
        planned_scenes.append(s)

    return planned_scenes, voice_map
