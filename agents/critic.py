"""Critic Agent - 구조 플랜 품질 검증 (Director 산출물 전용)"""

import json
from google import genai
from config.settings import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-pro-preview"


def review_production(research_brief: dict, plan: dict) -> dict:
    """리서치 브리프 대비 구조 플랜 품질 검증.

    Returns:
        {"approved": bool, "score": int, "feedback": str, "revision_notes": list}
    """
    prompt = f"""당신은 유튜브 쇼츠(유머/썰/사연) 구조 설계 품질 검증 전문가입니다.

## 리서치 브리프 (원본 자료)
{json.dumps(research_brief, ensure_ascii=False, indent=2)}

## 구조 플랜 (검증 대상)
{json.dumps(plan, ensure_ascii=False, indent=2)}

아래 기준으로 구조 플랜을 검증하고 JSON으로 결과를 출력하세요.

## 검증 기준
1. 오프닝 몰입도 (20점): 첫 scene_outline이 자연스럽고 바로 이해되는가?
2. 이야기 구조 (20점): 도입-전개-마무리가 자연스럽게 이어지는가?
3. 흐름/리텐션 (15점): 중반부가 늘어지지 않고 전개가 유지되는가?
   - 전개가 끊기지 않고, 시청자가 흥미를 유지하며 끝까지 보기 쉬운 구성인가?
   - scene별 narration과 scene_outline/image_intent/action_beat가 같은 사건을 가리키는가?
4. 감정 유발 (15점): 웃음/감동/통쾌함 등 감정선이 분명한가?
5. 제목 퀄리티 (10점): 호기심 갭/감정 단어/길이 제약(12자 내외)을 만족하는가?
6. 기술 스펙 (10점): 씬 수(6-10), 카메라 다양성, 필수 필드 존재
7. 시각화 적합성 (5점): scene_outline + image_intent + cast + shot_plan + world_context 조합이 이미지 에이전트가 시각화하기 충분한가?
8. 메타데이터 완결성 (5점): image_intent/setting_hint/emotion_beat/action_beat/cast와 continuity_state/shot_plan/world_context/camera(type/speed)/transition/effect가 자연스럽고 누락 없이 들어있는가?

## 엔딩 체크
- 마지막 장면이 이야기 맥락상 자연스럽게 마무리되는가?

## 시리즈물 추가 체크 (series_part가 있는 경우)
- 마지막 편이 아닌 경우: 다음 편과의 연결성이 자연스러운가?
- 2편 이상인 경우: 이전편 맥락 연결이 자연스러운가?
- 마지막 편인 경우: 결말 완결성이 있는가?
- title에는 [N/M] 표기가 없고, subtitle이 "시리즈명 N편" 형식인가?
- subtitle이 "시리즈 N편" 같은 generic 문구가 아닌가?

## 출력 형식 (JSON만)
{{
  "approved": true/false,
  "score": 0~100,
  "feedback": "전체 피드백 요약 (1~2문장)",
  "revision_notes": ["수정사항1", "수정사항2"]
}}

규칙:
- score 70 이상이면 approved: true
- 혐오/차별 표현이 있으면 무조건 approved: false
- revision_notes는 구체적으로 작성

JSON만 출력:"""

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
