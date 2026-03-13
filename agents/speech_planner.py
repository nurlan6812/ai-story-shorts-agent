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

VOICE_PROFILE_TO_VOICE = {
    "male_adult": VOICE_MALE,
    "female_adult": VOICE_FEMALE,
    "boy": VOICE_BOY,
    "girl": VOICE_GIRL,
    "elder_male": VOICE_ELDER_MALE,
    "elder_female": VOICE_ELDER_FEMALE,
    "neutral": VOICE_NEUTRAL,
}
ALLOWED_VOICE_PROFILES = tuple(VOICE_PROFILE_TO_VOICE.keys())

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
        index[name] = {
            "name": name,
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


def _normalize_voice_profile(value: Any) -> str:
    profile = str(value or "").strip().lower()
    if profile in VOICE_PROFILE_TO_VOICE:
        return profile
    return ""


def _build_voice_map(
    scenes: list[dict],
    narrator_voice_profile: str = "neutral",
    previous_voice_map: dict | None = None,
) -> dict[str, str]:
    prev = previous_voice_map if isinstance(previous_voice_map, dict) else {}
    voice_map: dict[str, str] = {
        str(name).strip(): str(voice).strip()
        for name, voice in prev.items()
        if str(name).strip() and str(voice).strip()
    }

    speaker_profiles: dict[str, str] = {}
    for scene in scenes:
        segments = scene.get("speech_segments") if isinstance(scene, dict) else None
        if not isinstance(segments, list):
            continue
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            speaker = _normalize_name(seg.get("speaker")) or "narrator"
            voice_profile = _normalize_voice_profile(seg.get("voice_profile"))
            if speaker and voice_profile and speaker not in speaker_profiles:
                speaker_profiles[speaker] = voice_profile

    voice_map.setdefault(
        "narrator",
        VOICE_PROFILE_TO_VOICE.get(
            _normalize_voice_profile(narrator_voice_profile) or "neutral",
            VOICE_NARRATOR,
        ),
    )
    for speaker, voice_profile in speaker_profiles.items():
        if speaker in voice_map:
            continue
        voice_map[speaker] = VOICE_PROFILE_TO_VOICE.get(voice_profile, VOICE_NEUTRAL)
    return voice_map


def _default_delivery_hint(
    speaker: str,
    seg_type: str,
) -> str:
    if speaker == "narrator":
        return (
            "Speak in natural Korean narration style. "
            "Clear pacing, conversational tone, no exaggerated acting. "
            "Pronounce Korean particles and sentence endings fully and clearly."
        )

    if seg_type == "dialogue":
        return (
            "Speak this as a Korean character line. "
            "Keep pronunciation clear and emotionally natural. "
            "Pronounce Korean particles and sentence endings fully and clearly."
        )
    return (
        "Speak naturally in Korean. "
        "Keep pronunciation clear and flowing with the surrounding narration. "
        "Pronounce Korean particles and sentence endings fully and clearly."
    )


def _build_fallback_segment(text: str) -> dict[str, str]:
    return {
        "type": "narration",
        "speaker": "narrator",
        "voice_profile": "neutral",
        "text": _normalize_name(text),
        "delivery_hint": _default_delivery_hint("narrator", "narration"),
    }


def _split_all_scenes_speech_with_llm(
    scenes: list[dict],
    character_index: dict[str, dict],
) -> tuple[dict[int, list[dict]], str]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Speech Planner requires GEMINI_API_KEY for LLM-only segmentation.")

    characters = sorted(character_index.keys())
    allowed_speakers = ["narrator", *characters]
    character_profiles = [
        {
            "name": name,
            "role": str(meta.get("role", "")),
            "description": str(meta.get("description", "")),
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
- Use scene_outline/image_intent/cast/character descriptions as context to infer the most plausible speaker.
- narrator_voice_profile should describe the best overall narrator voice for this story.
- When the main subject or protagonist is clear, narrator_voice_profile should usually match that person's age/gender vibe.
- type must be either "narration" or "dialogue".
- speaker must be one of: {json.dumps(allowed_speakers, ensure_ascii=False)}.
- voice_profile must be one of: {json.dumps(ALLOWED_VOICE_PROFILES, ensure_ascii=False)}.
- If speaker is "narrator", always use voice_profile="neutral".
- Keep one consistent voice_profile per speaker across the whole response.
- delivery_hint must be 1-2 short English sentences for TTS style guidance.
- delivery_hint should describe pacing, tone, and clarity only. Do not mention JSON keys.
- If uncertain, set speaker to "narrator".
- Do not invent new speakers.
- Do not drop scenes. Keep scene_index exactly as input.
- Concatenate all segment texts in original order so they are equivalent to source narration.

Input:
{json.dumps({"characters": character_profiles, "scenes": scene_payload}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "narrator_voice_profile": "male_adult|female_adult|boy|girl|elder_male|elder_female|neutral",
  "scenes": [
    {{
      "scene_index": 0,
      "segments": [
        {{
          "type": "narration|dialogue",
          "speaker": "narrator or character name",
          "voice_profile": "male_adult|female_adult|boy|girl|elder_male|elder_female|neutral",
          "delivery_hint": "1-2 short English sentences",
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
            narrator_voice_profile = _normalize_voice_profile(
                data.get("narrator_voice_profile")
            ) or "neutral"
            raw_scenes = data.get("scenes")
            if not isinstance(raw_scenes, list):
                last_error = "scenes is not a list"
                continue

            out_map: dict[int, list[dict]] = {}
            speaker_profiles: dict[str, str] = {}
            response_valid = True
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
                    last_error = f"segments is not a list for scene {scene_index}"
                    response_valid = False
                    continue

                normalized_segments: list[dict] = []
                for seg in raw_segments:
                    if not isinstance(seg, dict):
                        last_error = f"segment is not an object for scene {scene_index}"
                        response_valid = False
                        continue
                    seg_type = str(seg.get("type", "narration")).strip().lower()
                    if seg_type not in {"narration", "dialogue"}:
                        last_error = f"invalid segment type for scene {scene_index}"
                        response_valid = False
                        break
                    speaker = _normalize_name(seg.get("speaker")) or "narrator"
                    if speaker not in allowed_speakers:
                        last_error = f"invalid speaker for scene {scene_index}"
                        response_valid = False
                        break
                    voice_profile = _normalize_voice_profile(seg.get("voice_profile"))
                    if not voice_profile:
                        last_error = f"invalid voice_profile for scene {scene_index}"
                        response_valid = False
                        break
                    if speaker == "narrator":
                        voice_profile = "neutral"
                    previous_profile = speaker_profiles.get(speaker)
                    if previous_profile and previous_profile != voice_profile:
                        last_error = f"conflicting voice_profile for speaker {speaker}"
                        response_valid = False
                        break
                    speaker_profiles.setdefault(speaker, voice_profile)
                    delivery_hint = _clean_text(seg.get("delivery_hint", ""))
                    if not delivery_hint:
                        last_error = f"missing delivery_hint for scene {scene_index}"
                        response_valid = False
                        break
                    seg_text = _clean_text(seg.get("text", ""))
                    if not seg_text:
                        continue
                    normalized_segments.append(
                        {
                            "type": seg_type,
                            "speaker": speaker,
                            "voice_profile": voice_profile,
                            "delivery_hint": delivery_hint,
                            "text": seg_text,
                        }
                    )
                if not response_valid:
                    break
                out_map[scene_index] = normalized_segments

            if response_valid and out_map:
                return out_map, narrator_voice_profile
            if response_valid:
                last_error = "no valid scenes after normalization"
        except Exception as exc:
            last_error = f"llm call or parse failed: {exc}"
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
    scene_segment_map, narrator_voice_profile = _split_all_scenes_speech_with_llm(
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
            fallback_segment = _build_fallback_segment(narration)
            if not segments:
                # 전체 호출 결과에서 빠진 장면은 narration 단일 세그먼트로 보정
                segments = [fallback_segment]
            # LLM이 재작성/환각한 경우 narration 단일 세그먼트로 강등
            if not _segments_equivalent_to_narration(segments, narration):
                segments = [fallback_segment]

        # 화자 정합: 모르는 speaker는 narrator로 폴백
        fixed = []
        for seg in segments:
            seg_type = _normalize_name(seg.get("type")) or "narration"
            if seg_type not in {"narration", "dialogue"}:
                seg_type = "narration"
            speaker = _normalize_name(seg.get("speaker")) or "narrator"
            voice_profile = _normalize_voice_profile(seg.get("voice_profile")) or "neutral"
            if speaker == "narrator":
                voice_profile = "neutral"
            if speaker != "narrator" and speaker not in character_index:
                speaker = "narrator"
                voice_profile = "neutral"
            delivery_hint = _clean_text(seg.get("delivery_hint", ""))
            if not delivery_hint:
                delivery_hint = _default_delivery_hint(speaker=speaker, seg_type=seg_type)
            fixed.append(
                {
                    "type": seg_type,
                    "speaker": speaker,
                    "voice_profile": voice_profile,
                    "text": _normalize_name(seg.get("text")),
                    "delivery_hint": delivery_hint,
                }
            )
        s["speech_segments"] = fixed
        planned_scenes.append(s)

    voice_map = _build_voice_map(
        planned_scenes,
        narrator_voice_profile=narrator_voice_profile,
        previous_voice_map=previous_voice_map,
    )
    return planned_scenes, voice_map
