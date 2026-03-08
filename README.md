# youtube_humor

AI 에이전트가 리서치부터 쇼츠 영상 생성, 업로드, 성과 수집까지 처리하는 9:16 YouTube Shorts 파이프라인입니다.

현재 기준 핵심 구조는 아래입니다.

`Researcher -> Narrator -> Director -> Critic -> Imager -> Speech Planner -> Image/TTS/Compose -> Upload/Analytics`

상세 구조 문서:
- [Architecture](/Users/seogjaegwang/personal/youtube_humor/docs/architecture.md)
- [Shorts Market Plan 2026](/Users/seogjaegwang/personal/youtube_humor/docs/shorts_market_plan_2026.md)

## 현재 파이프라인

### 단편
1. `Researcher`
   - 웹 검색 + 본문 확인
   - `research_brief.json` 생성
2. `Narrator`
   - 스타일/BGM/장면 흐름/나레이션 생성
3. `Director`
   - 단편용 characters + scene metadata 생성
4. `Critic`
   - 점검 후 필요 시 `Director` 수정
5. `Imager`
   - scene별 `image_query` 생성
6. `Speech Planner`
   - narration/dialogue 분리 + 화자/보이스 매핑
7. `Image / Character Sheet / Ref selection`
   - 캐릭터 시트 생성
   - 장면 참조 선택
   - 이미지 생성
8. `TTS / Process / Compose`
   - 장면별 음성 생성
   - 오버레이/자막 렌더
   - 최종 영상 합성

### 시리즈
1. `Researcher`
   - `series_potential`만 판단
2. `Series Narrator`
   - 전편 구조를 한 번에 생성
   - `parts`, `cliffhanger`, `series_characters` 생성
3. `Series Director`
   - 현재 편 scene meta만 정리
   - `series_characters`를 유지하고 `cast/continuity/shot_plan` 중심으로 설계
4. 이후 단계는 단편과 동일
5. 비최종편은 마지막 teaser card `N편에서 공개`를 자동 추가

### 비교 모드
- `Narrator/Director/Image/TTS` 공유 결과를 만든 뒤
- 스타일별 motion/layout만 달리 적용해 여러 개의 비교 영상을 렌더합니다.

## 핵심 디렉토리

```text
youtube_humor/
├── main.py
├── scheduler.py
├── agents/
├── tools/
├── src/
├── config/
├── styles/
├── assets/
├── dashboard/
├── docs/
└── output/
```

### `agents/`
- [researcher.py](/Users/seogjaegwang/personal/youtube_humor/agents/researcher.py)
  - 웹 검색 + 본문 확인 기반 리서치 브리프 생성
- [narrator.py](/Users/seogjaegwang/personal/youtube_humor/agents/narrator.py)
  - 단편/시리즈 narrator
  - 스타일/BGM/scene seed/시리즈 구조 생성
- [director.py](/Users/seogjaegwang/personal/youtube_humor/agents/director.py)
  - 단편/시리즈 director
  - scene metadata, continuity, title/subtitle, character layout
- [critic.py](/Users/seogjaegwang/personal/youtube_humor/agents/critic.py)
  - 플랜 품질 검증 및 수정 루프
- [imager.py](/Users/seogjaegwang/personal/youtube_humor/agents/imager.py)
  - scene metadata -> `image_query`
- [speech_planner.py](/Users/seogjaegwang/personal/youtube_humor/agents/speech_planner.py)
  - 장면별 narration/dialogue segment + 화자 매핑
- [analyzer.py](/Users/seogjaegwang/personal/youtube_humor/agents/analyzer.py)
  - 업로드 후 성과 분석/패턴 추출

### `tools/`
- [content_fetcher.py](/Users/seogjaegwang/personal/youtube_humor/tools/content_fetcher.py)
  - 본문 추출/크롤링 보조
- [web_search.py](/Users/seogjaegwang/personal/youtube_humor/tools/web_search.py)
  - Tavily 검색
- [scene_reference_selector.py](/Users/seogjaegwang/personal/youtube_humor/tools/scene_reference_selector.py)
  - 이전 장면/전편 장면 참조 선택
- [style_manager.py](/Users/seogjaegwang/personal/youtube_humor/tools/style_manager.py)
  - 스타일 JSON 로더
- [video_composer.py](/Users/seogjaegwang/personal/youtube_humor/tools/video_composer.py)
  - FFmpeg 기반 합성
- [youtube_uploader.py](/Users/seogjaegwang/personal/youtube_humor/tools/youtube_uploader.py)
  - 업로드 및 쿼터 관리
- [youtube_analytics.py](/Users/seogjaegwang/personal/youtube_humor/tools/youtube_analytics.py)
  - 업로드 후 성과 수집
- [supabase_client.py](/Users/seogjaegwang/personal/youtube_humor/tools/supabase_client.py)
  - DB 저장/조회

### `src/`
- [image_source.py](/Users/seogjaegwang/personal/youtube_humor/src/image_source.py)
  - 실제 이미지 생성/소싱
- [image_proc.py](/Users/seogjaegwang/personal/youtube_humor/src/image_proc.py)
  - 제목/부제/자막 오버레이 렌더
- [tts.py](/Users/seogjaegwang/personal/youtube_humor/src/tts.py)
  - 장면별 TTS 생성
- [video.py](/Users/seogjaegwang/personal/youtube_humor/src/video.py)
  - BGM 선택 유틸
- [effects.py](/Users/seogjaegwang/personal/youtube_humor/src/effects.py)
  - 효과음 매핑

## 현재 실행 방식

```bash
# 기본: 리서처가 주제 자동 선정
python main.py

# 힌트 제공
python main.py "불륜 복수 썰"

# 스타일 강제
python main.py --style storytelling

# Critic 생략
python main.py --no-critic

# YouTube 업로드
python main.py --upload

# 업로드 없이 메타데이터만 확인
python main.py --upload --dry-run

# 성과 패턴 반영
python main.py --with-feedback

# 여러 스타일 비교
python main.py --compare

# 자동 모드
python main.py --auto

# 애널리틱스 수집
python main.py --analyze

# 스타일 목록
python main.py --list-styles

# YouTube OAuth
python main.py --auth
```

스케줄러:

```bash
python scheduler.py
python scheduler.py --once
```

## 출력 구조

기본 출력 경로:
- [output](/Users/seogjaegwang/personal/youtube_humor/output)

실행 1회당 대략 아래 파일이 생깁니다.

```text
output/YYYYMMDD_HHMMSS[_partN]/
├── research_brief.json
├── production_plan.json
├── script.json
├── reference_scene_map.json
├── previous_part_reference_map.json        # 시리즈 후속편일 때만
├── character_sheet.png                     # 생성되면
├── raw_images/
├── processed/
│   ├── bg/
│   └── overlay/
├── tts/
├── clips/
└── [title].mp4
```

## 현재 코드 기준 특징

- `script_gen` 구형 폴백 경로는 제거됨
- 시리즈는 `Narrator`가 전체 구조를 먼저 짜고 `Director`는 편별 scene meta를 정리함
- `Speech Planner`는 narration을 그대로 두고 segment/speaker만 나눔
- 이미지 프롬프트는 `Imager`가 `image_query`를 만들고, `main.py`가 최종 wrapper를 붙여 실제 이미지 모델로 보냄
- public-facing narration/scene text는 필요 시 정확한 상호/역명/학교명/회사명을 일반화하도록 조정되어 있음

## 기술 스택

- Text / planning: Gemini
- Image generation: Gemini image path via local pipeline
- TTS: Gemini TTS
- Search: Tavily
- Rendering: Pillow + FFmpeg
- Scheduling: APScheduler
- Upload/analytics: YouTube Data API / Analytics API
- Storage/metadata: Supabase
- Dashboard: FastAPI + Next.js

## 참고

- 현재 README는 “빠른 시작 + 현재 구조 요약” 중심입니다.
- 세부 데이터 흐름, 단편/시리즈 분기, 산출물 의미, 유지보수 포인트는 [Architecture](/Users/seogjaegwang/personal/youtube_humor/docs/architecture.md)에 정리했습니다.
