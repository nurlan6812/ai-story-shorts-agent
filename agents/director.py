"""Director Agent - Gemini 기반 크리에이티브 디렉터 (구조/씬 설계 전용)"""

import json
from google import genai
from config.settings import GEMINI_API_KEY
from tools.performance_feedback import build_director_feedback_block
from tools.style_manager import load_style, list_styles

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-pro-preview"

# BGM 설명 (assets/bgm/ 파일 기반)
BGM_CATALOG = {
    "funny": "슬랩스틱 코미디 BGM (브금대통령 'Black Comedy') — 웃긴 썰, 황당한 실수, 바보같은 상황에 적합",
    "emotional": "아련한 감성 피아노 BGM (브금대통령 '그때의 우리') — 감동 사연, 이별, 추억 이야기에 적합",
    "tension": "긴장감 고조 BGM (브금대통령 'Keep The Tension') — 위기 상황, 반전 직전, 심각한 장면에 적합",
    "chill": "잔잔한 어쿠스틱 기타 BGM (브금대통령 'Paesaggio Italiano') — 일상 수다, 따뜻한 이야기에 적합",
    "quirky": "엉뚱한 분위기 BGM (브금대통령 '조별과제') — 황당/엉뚱한 상황, 말도 안 되는 실화에 적합",
    "dramatic": "시네마틱 웅장한 BGM — 레전드 사건, 서사적 복수극에 적합",
}


def _part_number(part: dict, fallback: int) -> int:
    value = part.get("part") if isinstance(part, dict) else None
    if isinstance(value, int) and value >= 1:
        return value
    return fallback


def _series_part_focus(part: dict) -> str:
    if not isinstance(part, dict):
        return ""
    focus = str(part.get("part_focus", "")).strip()
    if focus:
        return focus

    # 이전 포맷 호환: story_points가 남아있으면 요약으로 변환
    points = part.get("story_points")
    if isinstance(points, list):
        cleaned = [str(p).strip() for p in points if str(p).strip()]
        if cleaned:
            return " / ".join(cleaned[:3])
    return ""


def _is_series_mode(
    series_parts: list[dict] | None,
    current_part: int | None,
) -> bool:
    return bool(series_parts and current_part)


def _single_character_guide_block() -> str:
    return """
## 캐릭터 추출 가이드 (중요)
- characters에는 narration_seed/original_story에서 반복 등장하거나 사건 전개에 중요한 사람을 빠짐없이 포함
- 주인공 외에도 연인, 상간남/상대방, 약혼자/배우자, 부모, 상사처럼 이야기 결과에 영향을 주는 인물은 각각 별도 character로 작성
- 초반 scene이 신발, 속옷, 휴대폰 같은 흔적만 보여주더라도, 이후에 정체가 드러나는 핵심 인물이라면 characters 배열에는 미리 포함
- 여러 사람을 protagonist 한 명으로 뭉개지 말고, 서로 다른 사람은 서로 다른 character name으로 분리
- cast는 해당 scene에 실제로 보이거나 존재감이 강하게 암시되는 인물만 넣되, recurring 핵심 인물이 characters에서 누락되면 안 됨
- characters.description은 이야기 전반에 통하는 안정적 외형을 구체적으로 쓰세요
- 각 description에는 보통 nationality/cultural context, approximate age, gender, hair, face or build cues, a baseline outfit style, and one or two distinctive traits를 포함하세요
- 장면 전용 복장/상태 변화는 continuity_state.wardrobe_state와 장면 메타로 내리세요
"""


def _series_character_guide_block() -> str:
    return """
## 캐릭터 보존/캐스트 설계 가이드 (중요)
- 누가 중요한 인물인지 다시 발굴/재판정하기보다, 이번 편 각 scene에서 누가 실제로 보이거나 강하게 암시되는지를 cast로 정확히 배치하세요
- narration_seed에 이름 대신 관계나 흔적만 보여도, 이미 정의된 핵심 인물 중 누구를 가리키는지 scene 메타에서 일관되게 연결하세요
- 특정 scene에 직접 안 나오는 핵심 인물도 시리즈 일관성을 위해 characters 배열에는 유지할 수 있지만, cast에는 실제 등장/암시 인물만 넣으세요
- 장면 전용 복장/상태 변화는 continuity_state.wardrobe_state와 장면 메타로 내리세요
"""


def _build_director_header(is_series_mode: bool) -> str:
    if is_series_mode:
        return """당신은 유머/썰/사연 유튜브 쇼츠 시리즈 전문 영상 감독입니다.
당신의 역할은 현재 편의 장면 메타데이터 정리/연속성 관리입니다. narrator가 이미 정한 시리즈 핵심 인물과 현재 편 narration 흐름을 유지한 채, 이미지 생성용 시각 구조 정보를 정확하게 작성하세요."""
    return """당신은 유머/썰/사연 유튜브 쇼츠 전문 영상 감독입니다.
당신의 역할은 장면 메타데이터 정리/연속성 관리입니다. 이미지 생성용 최종 프롬프트는 Image Agent가 담당하므로, 시각 설계에 필요한 구조 정보를 정확하게 작성하세요."""


def _title_field_hint(is_series_mode: bool) -> str:
    if is_series_mode:
        return '본제목 (한국어, 12자 이내 한 줄, [N/M] 금지, 커뮤니티/출처 라벨 금지)'
    return '본제목 (한국어, 12자 이내 한 줄, 커뮤니티/출처 라벨 금지)'


def _subtitle_field_hint(is_series_mode: bool) -> str:
    if is_series_mode:
        return '영상 부제 (한국어, 12자 이내 한 줄, 시리즈면 시리즈명 N편 형식, 커뮤니티/출처 라벨 금지)'
    return '영상 부제 (한국어, 12자 이내 한 줄, 커뮤니티/출처 라벨 금지)'


def _mode_specific_rules_block(is_series_mode: bool) -> str:
    if is_series_mode:
        return ""
    return """
- 단편 영상이므로 title/subtitle에 시리즈 표기나 "N편" 문구를 넣지 마세요"""


def _revise_checklist_block(is_series_mode: bool) -> str:
    common = """
1. 수정 요청사항을 모두 반영했는가
2. 혐오/차별 표현이 없는가
3. scene_outline이 자연스러운 한국어 구어체인가
4. characters 배열이 보존되고 장면별 cast와 모순되지 않는가
5. narration과 scene_outline/image_intent/action_beat가 같은 사건을 가리키며 의미 충돌이 없는가
6. image_intent/setting_hint/emotion_beat/action_beat/cast와 continuity_state/shot_plan/world_context/camera(type/speed)/transition/effect가 각 scene에서 누락되지 않았는가
7. scene가 설명적이기만 하지 않고, 시청자가 몰입할 수 있는 행동/반응/긴장 순간을 시각적으로 잘 잡고 있는가"""
    if is_series_mode:
        return (
            common
            + """
8. 시리즈물인 경우 title은 순수 본제목이고 subtitle이 "시리즈명 N편" 형식인가
9. title/subtitle/summary에 네이트판/블라인드/디시/더쿠/에타 같은 커뮤니티·출처 라벨이 없는가"""
        )
    return (
        common
        + """
8. 단편 영상인 경우 title/subtitle에 시리즈 표기나 "N편" 문구가 없는가
9. title/subtitle/summary에 네이트판/블라인드/디시/더쿠/에타 같은 커뮤니티·출처 라벨이 없는가"""
    )


def create_full_plan(
    research_brief: dict,
    winning_patterns: dict | None = None,
    series_parts: list[dict] | None = None,
    current_part: int | None = None,
    narration_seed: list[dict] | None = None,
) -> dict:
    """호환용 엔트리포인트: style/bgm은 외부(나레이터)에서 정해진다고 가정."""
    rb = research_brief or {}
    allowed_styles = set(list_styles())
    style_name = str(rb.get("style_suggestion", "")).strip()
    if style_name not in allowed_styles:
        style_name = "casual"

    fixed_bgm_mood = str(rb.get("bgm_mood", "")).strip()
    if fixed_bgm_mood not in BGM_CATALOG:
        story_type = str(rb.get("story_type", "")).strip().lower()
        fixed_bgm_mood = "dramatic" if story_type in {"revenge", "drama", "mystery"} else "funny"

    style = load_style(style_name)
    return create_production_plan(
        research_brief=research_brief,
        style=style,
        winning_patterns=winning_patterns,
        series_parts=series_parts,
        current_part=current_part,
        narration_seed=narration_seed,
        fixed_bgm_mood=fixed_bgm_mood,
    )


def create_production_plan(
    research_brief: dict,
    style: dict,
    winning_patterns: dict | None = None,
    series_parts: list[dict] | None = None,
    current_part: int | None = None,
    narration_seed: list[dict] | None = None,
    fixed_bgm_mood: str | None = None,
) -> dict:
    """스타일 지정된 경우의 구조 플랜 생성 (--style 플래그용)."""
    brief_desc = json.dumps(research_brief, ensure_ascii=False, indent=2)
    is_series_mode = _is_series_mode(series_parts, current_part)

    narration_cfg = style.get("narration", {})
    image_cfg = style.get("image", {})
    motion_cfg = style.get("motion", {})
    subtitle_cfg = style.get("subtitle", {})

    narration_guide = narration_cfg.get("guide", "자연스럽고 친근한 반말")
    image_prefix = image_cfg.get("prompt_prefix", "")
    image_suffix = image_cfg.get("prompt_suffix", "no text, no watermark")
    scene_duration = motion_cfg.get("scene_duration", "3-5초")
    camera_prefs = ", ".join(motion_cfg.get("camera", ["zoom_in", "static"]))
    transitions = ", ".join(motion_cfg.get("transitions", ["fade"]))
    show_subtitle = subtitle_cfg.get("show", True)
    feedback_block = build_director_feedback_block(winning_patterns)

    bgm_block = "\n".join(f"- {k}: {v}" for k, v in BGM_CATALOG.items())
    bgm_fixed_block = ""
    if fixed_bgm_mood:
        bgm_fixed_block = f"""

## BGM 고정값
- bgm_mood는 반드시 "{fixed_bgm_mood}" 사용 (변경 금지)
"""

    series_characters = research_brief.get("series_characters", []) if isinstance(research_brief, dict) else []
    if not isinstance(series_characters, list):
        series_characters = []
    series_characters_block = ""
    if series_characters:
        series_characters_block = f"""

## 고정 시리즈 핵심 인물 풀
아래 characters는 시리즈 전체에서 공통으로 유지할 핵심 인물입니다.
{json.dumps(series_characters, ensure_ascii=False, indent=2)}

규칙:
- 가능하면 이 인물 풀을 그대로 characters 배열에 유지하세요.
- 같은 사람을 다른 이름/다른 정체성으로 다시 만들지 마세요.
- characters.description은 안정적인 정체성/외형 중심으로 유지하세요.
- 일시적인 복장/상태(예: 웨딩드레스, 알몸, 젖은 상태, 피투성이, 결혼식 턱시도)는 global character description에 고정하지 말고 scene의 continuity_state.wardrobe_state / image_intent / character_beats로 표현하세요.
- 각 scene의 cast는 이 고정 인물 풀에서 선택하는 것을 우선하세요.
"""

    series_block = ""
    if is_series_mode:
        series_total = len(series_parts)
        current_info = series_parts[current_part - 1]
        current_focus = _series_part_focus(current_info) or "(현재 편 핵심 포커스 미지정)"
        series_block = f"""

## ★ 시리즈 영상: {current_part}편 / 총 {series_total}편

### 현재 편({current_part}편) 지정 정보
- 현재 편 핵심 포커스: {current_focus}

### 시리즈 제목/부제 규칙
- title에는 시리즈 표기([N/M])를 넣지 않음
- subtitle은 반드시 "시리즈명 {current_part}편" 형식 (예: "진상가족 참교육 {current_part}편")
- "시리즈 {current_part}편" 같은 generic 문구 금지
"""
        if current_part == 1:
            series_block += """
- 현재 편 범위 안에서 장면 정보만 정리
"""
        elif current_part < series_total:
            prev_info = series_parts[current_part - 2]
            prev_focus = _series_part_focus(prev_info) or "(요약 없음)"
            series_block += f"""
### 이전편({current_part - 1}편) 핵심 포커스
{prev_focus}

- 이전편과 충돌 없이 현재 편 장면 정보를 일관되게 구성
"""
        else:
            prev_info = series_parts[current_part - 2]
            prev_focus = _series_part_focus(prev_info) or "(요약 없음)"
            series_block += f"""
### 이전편({current_part - 1}편) 핵심 포커스
{prev_focus}

- 이전편과 충돌 없이 현재 편 장면 정보를 일관되게 구성
"""

    narration_seed_block = ""
    if narration_seed:
        narration_seed_block = f"""

## 나레이터 선행 시드 (고정 기준)
아래 scene 배열은 나레이터가 먼저 만든 초안입니다.
{json.dumps(narration_seed, ensure_ascii=False, indent=2)}

권장 기준:
- scene 개수와 순서를 동일하게 유지
- 각 scene의 narration 문장은 의미를 바꾸지 말고 그대로 유지
- director는 구조/연속성 설계 보강에 집중
"""

    character_guide_block = (
        _series_character_guide_block() if is_series_mode else _single_character_guide_block()
    )
    prompt = f"""{_build_director_header(is_series_mode)}

## 리서치 브리프
{brief_desc}
{series_block}
{series_characters_block}
{narration_seed_block}
{bgm_fixed_block}
{feedback_block}

리서치 브리프 필드 반영:
- source_region: 한국/외국
- original_title: 원문 게시글 제목
- original_story: 원문 핵심 본문

## 나레이션-시각 정합 가이드 (중요)
- 시청자는 나레이션을 들으며 장면을 보므로, 각 scene의 시각 정보는 해당 narration 이해를 직접 돕는 방향으로 설계
- scene_outline/image_intent/action_beat는 해당 scene narration의 핵심 사건(누가, 무엇을, 왜/결과)을 시각적으로 같은 의미로 반영
- narration이 구분한 관계 호칭(예: 여자친구/약혼녀/아버지/상사)은 scene 메타에서도 같은 인물을 가리키도록 일관되게 유지
- 리서치 원문에는 정확한 지명/상호/학교/회사명이 있어도, 공개용 출력(title/subtitle/description/summary/tags/scene_outline/setting_hint)에서는 꼭 필요하지 않다면 일반화하세요
- title/subtitle/summary에는 네이트판, 블라인드, 디시, 더쿠, 에타, 루리웹, 웃대 같은 커뮤니티/출처 라벨을 넣지 마세요
- "네이트판 레전드 썰", "블라인드 썰", "디시 실화" 같은 출처형 제목/부제/요약 문구를 금지합니다
- 장소감은 유지하되 특정성은 낮추세요 (예: "합정역" -> "서울의 한 지하철역", "맥도날드" -> "한 패스트푸드 매장")
- 장면 전환은 narration 순서를 유지하면서 시각적 연속성 중심으로 구성
- 같은 사건이라면 설명적인 정지 상태보다, 감정/행동/반응이 더 분명히 보이는 순간을 우선 선택
- 시청자가 상황에 몰입할 수 있도록 표정, 자세, 거리감, 대치 구도, 행동 직전/직후의 긴장감을 장면 메타에 반영
- image_intent/action_beat/shot_plan은 밋밋한 요약이 아니라 화면에서 바로 읽히는 드라마틱한 포인트를 잡도록 작성
- narration을 단순 번역하듯 옮기지 말고, 그 narration이 가장 실감나게 느껴질 시각적 순간을 고르세요

{character_guide_block}

## 영상 스타일
- style: {style.get('name', 'casual')} - {style.get('description', '')}
- narration 톤 가이드(참고용): {narration_guide}
- image prefix/suffix(참고용): {image_prefix} / {image_suffix}
- 장면당 길이: {scene_duration}
- 카메라 후보: {camera_prefs}
- 전환 후보: {transitions}
- 부제목 표시: {"예" if show_subtitle else "아니오"}

## 사용 가능한 BGM (참고)
{bgm_block}

## 출력 JSON 형식
{{
  "style": "{style.get('name', 'casual')}",
  "bgm_mood": "{fixed_bgm_mood or '선택한 BGM 이름'}",
  "title": "{_title_field_hint(is_series_mode)}",
  "subtitle": "{_subtitle_field_hint(is_series_mode)}",
  "description": "영상 설명 (한국어, 해시태그 포함)",
  "summary": "핵심 내용 1줄 요약 (한국어, 30자 이내)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "characters": [
    {{
      "name": "character name (English ASCII only)",
      "description": "English appearance description (nationality/cultural context, age, gender, hair, outfit, body type, traits)",
      "role": "protagonist|antagonist|supporting"
    }}
  ],
  "scenes": [
    {{
      "narration": "나레이터 시드 문장(동일 의미로 유지)",
      "scene_outline": "장면 요점(한국어, 1~2문장)",
      "image_intent": "이미지에서 강조할 시각 포인트(한국어, 짧게)",
      "setting_hint": "시대/장소/시간/날씨 힌트 (한국어, 짧게)",
      "emotion_beat": "핵심 감정 (예: 당황, 분노, 통쾌, 감동, 불안)",
      "action_beat": "한 컷에서 보일 핵심 행동 (한국어, 짧게)",
      "cast": ["해당 장면 등장 character name (characters[].name과 정확히 일치)"],
      "continuity_state": {{
        "location_id": "장소 식별자(예: office_lobby_01)",
        "time_of_day": "morning|day|evening|night",
        "wardrobe_state": "복장 연속성 상태(예: manager_uniform_same)",
        "prop_state": "핵심 소품 상태(예: spilled_coffee_on_table)"
      }},
      "shot_plan": {{
        "shot_type": "close_up|medium|wide|over_shoulder",
        "camera_angle": "eye_level|low_angle|high_angle",
        "composition": "구도 요약(한국어 또는 영어 짧게)"
      }},
      "world_context": {{
        "source_region": "한국|외국",
        "era_hint": "시대 힌트(예: 1990s, present day, 2010s)",
        "cultural_markers": ["문화권 단서 1", "문화권 단서 2"]
      }},
      "effect": "whoosh|impact|dramatic|pop|ding|suspense 또는 null",
      "camera": {{
        "type": "zoom_in|zoom_out|pan_left|pan_right|pan_up|static",
        "speed": "slow|medium|fast"
      }},
      "transition": "fade|slide_left|slide_up|zoom|none"
    }}
  ]
}}

규칙:
- narration_seed가 있으면 scene 개수/순서를 그대로 유지하고 narration 의미를 바꾸지 않음
- narration_seed가 없으면 6~10개 장면으로 구성
- bgm_mood는 {"고정값으로 유지" if fixed_bgm_mood else "장면 톤에 맞게 선택"}
- characters.name은 영어(ASCII)만 사용
- source_region이 외국이면 title/subtitle/summary/scene_outline에서 한국 밈/은어 사용 금지
- source_region이 외국이면 중립 표현으로 작성
- 공개용 출력에서는 exact real-world station/store/school/company/place names를 새로 만들거나 불필요하게 유지하지 마세요
- 공개용 title/subtitle/summary에는 커뮤니티 출처명(예: 네이트판/블라인드/디시/더쿠/에타)을 넣지 마세요
- image_intent는 scene_outline과 모순 없이 같은 장면을 시각적으로 강조
- scene는 시간 순서를 지키고 같은 인물 이름을 일관되게 유지
{_mode_specific_rules_block(is_series_mode)}
- scene_outline은 narration 이해를 돕는 사실 중심 요약으로 작성
- setting_hint에는 시대감(예: 1990s, present day)과 장소 힌트를 포함
- cast는 해당 장면 실제 등장인물만 넣고 characters[].name과 정확히 일치
- continuity_state는 인접 scene 사이에서 특별한 사건이 없으면 동일하게 유지
- continuity_state.wardrobe_state는 해당 장면의 실제 복장/상태를 구체적으로 적어 image prompt에 반영되게 하세요
- shot_plan은 장면 연출 의도를 요약하며, camera_angle은 여기에서만 관리
- world_context.source_region은 반드시 한국 또는 외국
- camera는 움직임(type/speed)만 담당
- characters는 story 전체 핵심 인물 풀이고, 특정 scene에서 안 보이더라도 반복/핵심 인물은 characters 배열에 유지
- 혐오/차별 표현 금지

JSON만 출력:"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return _parse_json(response.text)


def revise_plan(
    plan: dict,
    revision_notes: list[str],
    is_series_mode: bool = False,
) -> dict:
    """크리틱 피드백 반영하여 구조 플랜 수정."""
    notes_str = "\n".join(f"- {n}" for n in revision_notes)
    header = (
        "유튜브 쇼츠 시리즈 영상 감독으로서 아래 구조 플랜을 수정하세요."
        if is_series_mode
        else "유튜브 쇼츠 영상 감독으로서 아래 구조 플랜을 수정하세요."
    )
    checklist_block = _revise_checklist_block(is_series_mode)

    prompt = f"""{header}

## 현재 플랜
{json.dumps(plan, ensure_ascii=False, indent=2)}

## 수정 요청사항
{notes_str}

체크리스트:
{checklist_block}

수정된 전체 JSON만 출력:"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return _parse_json(response.text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text.strip())
