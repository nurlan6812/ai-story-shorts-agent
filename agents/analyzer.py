"""Analyzer Agent - 영상 성과 분석 및 패턴 추출 (유머/썰 특화)

stats_engine이 수학적 계산을 사전 처리하고,
Gemini는 계산된 통계를 해석/판단만 합니다.
"""

import json
from src.genai_client import create_genai_client
from tools.stats_engine import precompute_stats

client = create_genai_client()
MODEL = "gemini-3.1-pro-preview"


def analyze_performance(videos_with_analytics: list[dict]) -> dict:
    """영상 성과 데이터를 분석하여 승자/패자 분류 및 패턴 추출

    유머/썰 채널 특화: 조회수, 공유수, 댓글수, 시청시간 기반 바이럴 성과 분석

    Args:
        videos_with_analytics: Supabase에서 가져온 영상+애널리틱스 데이터 리스트

    Returns:
        {winners, losers, patterns, recommendations, avoid}
    """
    if not videos_with_analytics:
        return _empty_result("데이터가 부족합니다. 더 많은 영상을 업로드하세요.")

    # 1단계: 통계 사전 계산 (Python이 수학 처리)
    stats = precompute_stats(videos_with_analytics)

    if stats["total_videos"] == 0:
        return _empty_result("애널리틱스 데이터가 있는 영상이 없습니다.")

    # 2단계: Gemini에게 해석 요청 (계산 결과만 전달)
    stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

    prompt = f"""당신은 유튜브 쇼츠(유머/썰/사연) 성과 분석 전문가입니다.

아래는 **이미 계산이 완료된 통계 데이터**입니다.
수치를 다시 계산하지 말고, 주어진 숫자를 그대로 인용하여 해석하세요.

## 사전 계산된 통계

{stats_json}

## 데이터 설명
- **thresholds**: views 기준 상위 30%(winner), 하위 30%(loser) 임계값
- **summary**: 전체 영상의 기술통계 (평균, 중앙값, 표준편차, 최소, 최대)
- **winners/losers**: 조회수 상위/하위 30% 영상 목록
- **by_style**: 스타일별 평균 조회수, 좋아요, CTR, 시청률
- **by_bgm**: BGM별 동일 집계
- **by_story_type**: story_type별 집계
- **by_source_region**: source_region별 집계
- **by_series_format**: single/series별 집계
- **by_ending_type**: payoff/cliffhanger/aftershock 등 ending별 집계
- **by_scene_density**: low/medium/high scene density별 집계
- **correlations**: 지표 간 상관계수
- **engagement_rates**: 영상별 좋아요율, 댓글율

## 유머/썰 채널 특화 분석 포인트
- **바이럴 성과**: 조회수뿐 아니라 공유수, 댓글수가 중요 (댓글 = 참여도)
- **story_type별 성과**: funny, touching, revenge, absurd 등 어떤 유형이 잘 되는지
- **emotion별 성과**: humor, heartwarming, satisfying 등 감정 유형별 분석
- **스타일별 성과**: casual, storytelling, darkcomedy 등 어떤 톤이 좋은지
- **시리즈/단편 성과**: single vs series, part progression
- **마무리 방식 성과**: payoff, aftershock, cliffhanger 등 ending_type별 차이
- **장면 밀도 성과**: low/medium/high scene density 차이

## 해석 요청

위 데이터를 바탕으로 아래 JSON을 작성하세요.
**수치는 stats에서 직접 인용하고, 추측하지 마세요.**

```json
{{
  "winners": [
    {{"video_id": "...", "title": "...", "reason": "성공 요인 해석 (데이터 인용)"}}
  ],
  "losers": [
    {{"video_id": "...", "title": "...", "reason": "부진 원인 해석 (데이터 인용)"}}
  ],
  "patterns": {{
    "styles": [
      {{"style": "스타일명", "avg_views": 숫자, "avg_likes": 숫자, "verdict": "추천/보류/비추"}}
    ],
    "story_types": [
      {{"story_type": "유형명", "performance": "high/medium/low"}}
    ],
    "source_regions": [
      {{"source_region": "한국|외국", "performance": "high/medium/low"}}
    ],
    "series_formats": [
      {{"series_format": "single|series", "performance": "high/medium/low"}}
    ],
    "emotions": [
      {{"emotion": "감정유형", "performance": "high/medium/low"}}
    ],
    "ending_types": [
      {{"ending_type": "payoff|aftershock|cliffhanger|unknown", "performance": "high/medium/low"}}
    ],
    "scene_density": [
      {{"scene_density": "low|medium|high", "performance": "high/medium/low"}}
    ],
    "topics": [
      {{"topic_keyword": "키워드", "performance": "high/medium/low"}}
    ],
    "timing": [
      {{"observation": "시간대/요일 관련 관찰 (데이터가 없으면 빈 배열)"}}
    ]
  }},
  "recommendations": [
    "다음 영상에서 시도할 구체적 제안 (데이터 근거 포함)"
  ],
  "avoid": [
    "피해야 할 구체적 항목 (데이터 근거 포함)"
  ],
  "confidence": "high/medium/low",
  "confidence_reason": "신뢰도 판단 이유 (sample_size, 데이터 일관성 등)"
}}
```

## 해석 가이드라인
1. **correlations 해석**: 0.5 이상 = 강한 양의 상관, 0.3~0.5 = 중간, 0.3 미만 = 약함
2. **by_style 해석**: winner_count가 높고 avg_views가 높은 스타일 = 추천
3. **sample_size 주의**: {stats['total_videos']}개 데이터 — 5개 미만이면 confidence = "low"
4. **추측 금지**: 데이터에 없는 패턴을 만들어내지 마세요

JSON만 출력:"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return _parse_json(response.text)


def _empty_result(message: str) -> dict:
    return {
        "winners": [],
        "losers": [],
        "patterns": {
            "styles": [],
            "story_types": [],
            "source_regions": [],
            "series_formats": [],
            "emotions": [],
            "ending_types": [],
            "scene_density": [],
            "topics": [],
            "timing": [],
        },
        "recommendations": [message],
        "avoid": [],
        "confidence": "low",
        "confidence_reason": message,
    }


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text.strip())
