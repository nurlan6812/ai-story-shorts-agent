"""장면별 참조 이미지 선택기 (LLM 재시도 전용, 폴백 없음)"""

import json
import time

from google import genai

from config.settings import GEMINI_API_KEY

MODEL = "gemini-3.1-pro-preview"
MAX_RETRIES = 5
RETRY_BASE_SEC = 2


def _parse_json(text: str | None) -> dict | list:
    if text is None:
        raise ValueError("response text is empty")
    text = str(text).strip()
    if not text:
        raise ValueError("response text is empty")
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) > 1 else parts[0]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text.strip())


def select_reference_scenes(
    scenes: list[dict],
    max_refs: int = 2,
) -> dict[str, dict]:
    """장면별로 어떤 이전 장면 이미지를 참조할지 선택

    Returns:
        {
          "refs": {scene_index: [reference_scene_indexes...]},
          "notes": {scene_index: {reference_scene_index: "short note"}}
        }
    """
    if len(scenes) <= 1:
        return {"refs": {}, "notes": {}}

    max_refs = max(1, min(max_refs, 3))
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 없어 reference selector를 실행할 수 없습니다. (폴백 없음)")

    scene_lines = []
    for i, s in enumerate(scenes):
        scene_outline = s.get("scene_outline", "")
        image_intent = s.get("image_intent", "")
        setting_hint = s.get("setting_hint", "")
        character_beats = s.get("character_beats", [])
        continuity_state = s.get("continuity_state", {})
        image_query = s.get("image_query", "")
        scene_lines.append(
            f"[{i}] scene_outline: {scene_outline}\n"
            f"[{i}] image_intent: {image_intent}\n"
            f"[{i}] setting_hint: {setting_hint}\n"
            f"[{i}] character_beats: {character_beats}\n"
            f"[{i}] continuity_state: {continuity_state}\n"
            f"[{i}] image_query: {image_query}"
        )
    scene_block = "\n\n".join(scene_lines)

    prompt = f"""당신은 영상 연출 continuity 플래너입니다.
아래 장면 목록을 보고, 각 장면(i>=1)이 참조해야 할 "이전 장면 이미지 인덱스"를 골라주세요.

    규칙:
- 현재 장면 i의 참조 인덱스는 반드시 i보다 작아야 함
- 장면당 최대 {max_refs}개
- 캐릭터/장소/시간 연속성이 높은 장면을 우선
- continuity_state.location_id / wardrobe_state / prop_state가 겹치면 우선 선택
- 참조가 꼭 필요하지 않은 장면은 reference_scene_indexes를 비워도 됨
- reference_scene_notes는 영어 한 줄 요약으로 작성
- JSON만 출력

장면 목록:
{scene_block}

출력 형식:
{{
  "references": [
    {{
      "scene_index": 1,
      "reference_scene_indexes": [0],
      "reference_scene_notes": {{"0": "Brief English summary of the previous scene"}}
    }},
    {{
      "scene_index": 2,
      "reference_scene_indexes": [1, 0],
      "reference_scene_notes": {{"1": "Brief English summary of the immediate prior scene", "0": "Brief English summary from two scenes ago"}}
    }}
  ]
}}
"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    retry_prompt = prompt
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=retry_prompt)
            parsed = _parse_json(response.text)
            refs = parsed.get("references", []) if isinstance(parsed, dict) else []
            if not isinstance(refs, list):
                raise ValueError("references가 배열이 아닙니다.")

            result_refs: dict[int, list[int]] = {}
            result_notes: dict[int, dict[int, str]] = {}

            for row in refs:
                if not isinstance(row, dict):
                    continue
                idx = row.get("scene_index")
                raw_ref = row.get("reference_scene_indexes", [])
                raw_notes = row.get("reference_scene_notes", {})
                if not isinstance(idx, int) or idx <= 0 or idx >= len(scenes):
                    continue
                if not isinstance(raw_ref, list):
                    continue
                if not isinstance(raw_notes, dict):
                    continue

                cleaned: list[int] = []
                for r in raw_ref:
                    if isinstance(r, int) and 0 <= r < idx and r not in cleaned:
                        cleaned.append(r)
                    if len(cleaned) >= max_refs:
                        break
                if not cleaned:
                    continue
                cleaned = sorted(cleaned[:max_refs])

                notes_for_scene: dict[int, str] = {}
                for ref_idx in cleaned:
                    note = raw_notes.get(str(ref_idx), raw_notes.get(ref_idx, ""))
                    note_text = str(note).strip() if note is not None else ""
                    if not note_text:
                        raise ValueError(f"scene_index={idx}의 ref={ref_idx} note 누락")
                    notes_for_scene[ref_idx] = note_text[:160]

                result_refs[idx] = cleaned
                result_notes[idx] = notes_for_scene

            # 선택형: 포함된 scene_index만 검증
            for idx, ref_list in result_refs.items():
                if idx not in result_notes:
                    raise ValueError(f"scene_index={idx} 참조 노트 누락")
                for ref_idx in ref_list:
                    if ref_idx not in result_notes[idx]:
                        raise ValueError(f"scene_index={idx} ref={ref_idx} note 누락")

            return {"refs": result_refs, "notes": result_notes}
        except Exception as e:
            last_error = str(e)
            if attempt >= MAX_RETRIES:
                break
            wait_sec = min(RETRY_BASE_SEC * (2 ** (attempt - 1)), 30)
            retry_prompt = (
                f"{prompt}\n\n"
                f"이전 출력 오류: {last_error}\n"
                "참조가 필요한 scene_index만 포함해도 되지만, 포함한 각 scene_index의 "
                "reference_scene_indexes와 note는 반드시 완전하게 채운 strict JSON만 다시 출력하세요. "
                "reference_scene_notes는 영어로 작성하세요."
            )
            time.sleep(wait_sec)

    raise RuntimeError(
        f"reference selector 실패: {MAX_RETRIES}회 재시도 후에도 유효한 응답을 받지 못했습니다. detail={last_error}"
    )


def select_references_unified(
    current_scenes: list[dict],
    max_in_episode_refs: int = 2,
    previous_part_scenes: list[dict] | None = None,
    max_previous_part_refs: int = 1,
) -> dict[str, dict]:
    """현재편 내부 + 전편 참조를 한 번의 LLM 호출로 선택

    Returns:
        {
          "in_episode_refs": {current_scene_index: [current_scene_indexes...]},
          "in_episode_notes": {current_scene_index: {current_scene_index: "short note"}},
          "previous_part_refs": {current_scene_index: [previous_part_scene_indexes...]},  # 필요한 장면만 포함 가능
          "previous_part_notes": {current_scene_index: {previous_part_scene_index: "short note"}}  # 필요한 장면만 포함 가능
        }
    """
    if not current_scenes:
        return {
            "in_episode_refs": {},
            "in_episode_notes": {},
            "previous_part_refs": {},
            "previous_part_notes": {},
        }

    max_in_episode_refs = max(1, min(max_in_episode_refs, 3))
    max_previous_part_refs = max(1, min(max_previous_part_refs, 2))
    has_prev = bool(previous_part_scenes)
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 없어 unified reference selector를 실행할 수 없습니다. (폴백 없음)")

    current_lines = []
    for i, s in enumerate(current_scenes):
        current_lines.append(
            f"[C{i}] scene_outline: {s.get('scene_outline', '')}\n"
            f"[C{i}] image_intent: {s.get('image_intent', '')}\n"
            f"[C{i}] setting_hint: {s.get('setting_hint', '')}\n"
            f"[C{i}] character_beats: {s.get('character_beats', [])}\n"
            f"[C{i}] continuity_state: {s.get('continuity_state', {})}\n"
            f"[C{i}] image_query: {s.get('image_query', '')}"
        )

    prev_block = "없음"
    prev_rule = "- previous_part_references는 빈 배열로 반환"
    if has_prev:
        prev_lines = []
        for i, s in enumerate(previous_part_scenes or []):
            prev_lines.append(
                f"[P{i}] scene_outline: {s.get('scene_outline', '')}\n"
                f"[P{i}] image_intent: {s.get('image_intent', '')}\n"
                f"[P{i}] setting_hint: {s.get('setting_hint', '')}\n"
                f"[P{i}] character_beats: {s.get('character_beats', [])}\n"
                f"[P{i}] continuity_state: {s.get('continuity_state', {})}\n"
                f"[P{i}] image_query: {s.get('image_query', '')}"
            )
        prev_block = "\n".join(prev_lines)
        prev_rule = (
            f"- previous_part_references: 전편 참조가 필요한 current_scene_index만 선택해서 "
            f"previous_part_scene_indexes를 1~{max_previous_part_refs}개 반환 "
            "(필요 없는 장면은 생략 가능)"
        )

    prompt = f"""당신은 영상 continuity 플래너입니다.
아래 정보를 바탕으로 한 번에 두 가지 참조를 고르세요.

1) 현재편 내부 참조(in_episode_references)
2) 전편 참조(previous_part_references)

공통 규칙:
- JSON만 출력
- 노트는 160자 이내, 영어로 작성
- 캐릭터/장소/의상/소품/시간대 continuity를 우선

세부 규칙:
- in_episode_references: 참조가 필요한 scene_index(1 이상)만 선택해서 반환
- in_episode_references: reference_scene_indexes는 반드시 scene_index보다 작은 값
- in_episode_references: 장면당 최대 {max_in_episode_refs}개
{prev_rule}

현재 편 장면 목록:
{chr(10).join(current_lines)}

전편 장면 목록:
{prev_block}

출력 형식:
{{
  "in_episode_references": [
    {{
      "scene_index": 1,
      "reference_scene_indexes": [0],
      "reference_scene_notes": {{"0": "Brief English summary of the previous scene"}}
    }}
  ],
  "previous_part_references": [
    {{
      "current_scene_index": 0,
      "previous_part_scene_indexes": [3],
      "reference_scene_notes": {{"3": "Brief English summary of the previous-episode scene"}}
    }}
  ]
}}
"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    retry_prompt = prompt
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=retry_prompt)
            parsed = _parse_json(response.text)

            in_rows = parsed.get("in_episode_references", []) if isinstance(parsed, dict) else []
            prev_rows = parsed.get("previous_part_references", []) if isinstance(parsed, dict) else []
            if not isinstance(in_rows, list):
                raise ValueError("in_episode_references가 배열이 아닙니다.")
            if not isinstance(prev_rows, list):
                raise ValueError("previous_part_references가 배열이 아닙니다.")

            result_in_refs: dict[int, list[int]] = {}
            result_in_notes: dict[int, dict[int, str]] = {}

            for row in in_rows:
                if not isinstance(row, dict):
                    continue
                idx = row.get("scene_index")
                raw_ref = row.get("reference_scene_indexes", [])
                raw_notes = row.get("reference_scene_notes", {})
                if not isinstance(idx, int) or idx <= 0 or idx >= len(current_scenes):
                    continue
                if not isinstance(raw_ref, list) or not isinstance(raw_notes, dict):
                    continue

                cleaned: list[int] = []
                for r in raw_ref:
                    if isinstance(r, int) and 0 <= r < idx and r not in cleaned:
                        cleaned.append(r)
                    if len(cleaned) >= max_in_episode_refs:
                        break
                if not cleaned:
                    continue
                cleaned = sorted(cleaned[:max_in_episode_refs])

                notes_for_scene: dict[int, str] = {}
                for ref_idx in cleaned:
                    note = raw_notes.get(str(ref_idx), raw_notes.get(ref_idx, ""))
                    note_text = str(note).strip() if note is not None else ""
                    if not note_text:
                        raise ValueError(f"in_episode scene_index={idx} ref={ref_idx} note 누락")
                    notes_for_scene[ref_idx] = note_text[:160]

                result_in_refs[idx] = cleaned
                result_in_notes[idx] = notes_for_scene

            # in_episode는 선택형: 포함된 scene_index만 검증
            for idx, ref_list in result_in_refs.items():
                if idx not in result_in_notes:
                    raise ValueError(f"in_episode scene_index={idx} note 누락")
                for ref_idx in ref_list:
                    if ref_idx not in result_in_notes[idx]:
                        raise ValueError(f"in_episode scene_index={idx} ref={ref_idx} note 누락")

            result_prev_refs: dict[int, list[int]] = {}
            result_prev_notes: dict[int, dict[int, str]] = {}
            if has_prev:
                prev_len = len(previous_part_scenes or [])
                for row in prev_rows:
                    if not isinstance(row, dict):
                        continue
                    idx = row.get("current_scene_index")
                    raw_ref = row.get("previous_part_scene_indexes", [])
                    raw_notes = row.get("reference_scene_notes", {})
                    if not isinstance(idx, int) or idx < 0 or idx >= len(current_scenes):
                        continue
                    if not isinstance(raw_ref, list) or not isinstance(raw_notes, dict):
                        continue

                    cleaned: list[int] = []
                    for r in raw_ref:
                        if isinstance(r, int) and 0 <= r < prev_len and r not in cleaned:
                            cleaned.append(r)
                        if len(cleaned) >= max_previous_part_refs:
                            break
                    if not cleaned:
                        continue
                    cleaned = sorted(cleaned[:max_previous_part_refs])

                    notes_for_scene: dict[int, str] = {}
                    for ref_idx in cleaned:
                        note = raw_notes.get(str(ref_idx), raw_notes.get(ref_idx, ""))
                        note_text = str(note).strip() if note is not None else ""
                        if not note_text:
                            raise ValueError(f"previous_part scene_index={idx} ref={ref_idx} note 누락")
                        notes_for_scene[ref_idx] = note_text[:160]

                    result_prev_refs[idx] = cleaned
                    result_prev_notes[idx] = notes_for_scene

                # previous_part는 선택형: 필요한 current_scene_index만 포함 가능
                for idx, ref_list in result_prev_refs.items():
                    if idx not in result_prev_notes:
                        raise ValueError(f"previous_part current_scene_index={idx} note 누락")
                    for ref_idx in ref_list:
                        if ref_idx not in result_prev_notes[idx]:
                            raise ValueError(f"previous_part current_scene_index={idx} ref={ref_idx} note 누락")

            return {
                "in_episode_refs": result_in_refs,
                "in_episode_notes": result_in_notes,
                "previous_part_refs": result_prev_refs,
                "previous_part_notes": result_prev_notes,
            }
        except Exception as e:
            last_error = str(e)
            if attempt >= MAX_RETRIES:
                break
            wait_sec = min(RETRY_BASE_SEC * (2 ** (attempt - 1)), 30)
            retry_prompt = (
                f"{prompt}\n\n"
                f"이전 출력 오류: {last_error}\n"
                "strict JSON만 출력하고, in_episode/previous_part 모두 참조가 필요한 scene만 포함해도 됩니다. "
                "다만 포함한 각 ref에 대응하는 note는 반드시 채우세요. note는 영어로 작성하세요."
            )
            time.sleep(wait_sec)

    raise RuntimeError(
        f"unified reference selector 실패: {MAX_RETRIES}회 재시도 후에도 유효한 응답을 받지 못했습니다. detail={last_error}"
    )
