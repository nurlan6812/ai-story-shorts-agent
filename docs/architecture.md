# Architecture

이 문서는 현재 `youtube_humor` 코드베이스의 실제 파이프라인 구조를 정리한 문서입니다.

기준 시점:
- 저장소 루트: [youtube_humor](/Users/seogjaegwang/personal/youtube_humor)
- 엔트리 포인트: [main.py](/Users/seogjaegwang/personal/youtube_humor/main.py)

## 1. 전체 구조

현재 메인 파이프라인은 아래처럼 동작합니다.

```text
Researcher
  -> Narrator (single or series)
  -> Director (single or series)
  -> Critic loop
  -> Imager
  -> Speech Planner
  -> Character Sheet / Reference Selection / Image Generation
  -> TTS
  -> Image Processing
  -> Video Compose
  -> Upload / Analytics
```

핵심 차이:
- `단편`: `single narrator -> single director`
- `시리즈`: `series narrator -> series director`

## 2. 엔트리 포인트

### [main.py](/Users/seogjaegwang/personal/youtube_humor/main.py)

중요 함수:
- `run_pipeline_single()`
  - 단편 1편 또는 시리즈의 현재 편 1개 생성
- `_run_series_pipeline()`
  - 리서치 1회 + 시리즈 narrator 1회 + 편별 `run_pipeline_single()` 반복
- `run_pipeline_compare()`
  - 비교 모드
- `_handle_auto()`
  - 자동 생성/업로드/대기열 처리

### [scheduler.py](/Users/seogjaegwang/personal/youtube_humor/scheduler.py)

스케줄 작업:
- 생성 + 업로드
- 애널리틱스 수집
- 패턴 분석
- 헬스 체크

## 3. 단편 파이프라인

### 3.1 Researcher
파일: [agents/researcher.py](/Users/seogjaegwang/personal/youtube_humor/agents/researcher.py)

역할:
- 웹 검색
- 원문 확인
- `research_brief` 생성

출력 핵심:
- `topic`
- `story_type`
- `source_region`
- `original_title`
- `original_story`
- `emotion`
- `style_suggestion`
- `series_potential`

### 3.2 Single Narrator
파일: [agents/narrator.py](/Users/seogjaegwang/personal/youtube_humor/agents/narrator.py)

역할:
- 스타일/BGM 선택
- 8~10 scene narration seed 생성

출력 핵심:
- `style`
- `bgm_mood`
- `scenes[]`
  - `narration`
  - `scene_outline`
  - `image_intent`
  - `setting_hint`
  - `emotion_beat`
  - `action_beat`

중요:
- 단편 narrator는 아직 `characters`를 만들지 않음

### 3.3 Single Director
파일: [agents/director.py](/Users/seogjaegwang/personal/youtube_humor/agents/director.py)

역할:
- narrator seed를 유지하면서 production metadata 확장
- 단편에서는 `characters`를 직접 생성

출력 핵심:
- `title`
- `subtitle`
- `description`
- `summary`
- `tags`
- `characters[]`
- `scenes[]`
  - `cast`
  - `continuity_state`
  - `shot_plan`
  - `world_context`
  - `camera`
  - `transition`

## 4. 시리즈 파이프라인

### 4.1 Researcher
- `series_potential`만 판단
- 실제 파트 분할은 하지 않음

### 4.2 Series Narrator
파일: [agents/narrator.py](/Users/seogjaegwang/personal/youtube_humor/agents/narrator.py)

역할:
- 전체 시리즈 구조를 한 번에 생성
- 공통 캐릭터 풀을 먼저 고정

출력 핵심:
- `style`
- `bgm_mood`
- `series_total_parts`
- `characters[]`  ← 시리즈 공통 캐릭터 풀
- `parts[]`
  - `part`
  - `part_focus`
  - `cliffhanger`
  - `scenes[]`

### 4.3 Series Director
파일: [agents/director.py](/Users/seogjaegwang/personal/youtube_humor/agents/director.py)

역할:
- 현재 편의 scene metadata 정리
- narrator가 만든 `series_characters`를 유지
- 새 인물을 발굴하기보다 `cast/continuity/shot_plan` 정리에 집중

중요:
- 시리즈 director는 `characters`를 새로 invent하는 역할이 아님
- 현재 편의 `cast`와 장면 메타가 핵심

### 4.4 시리즈 후속편 공유 컨텍스트
`_run_series_pipeline()`에서 편 사이에 공유되는 것:
- `series_title_fixed`
- `series_subtitle_base_fixed`
- `character_sheet_path`
- `previous_part_scenes`
- `previous_part_image_map`
- `previous_part_voice_map`

즉:
- 1편 캐릭터 시트 재사용
- 전편 장면 이미지 참조
- 전편 voice map 재사용

## 5. Critic 루프

파일: [agents/critic.py](/Users/seogjaegwang/personal/youtube_humor/agents/critic.py)

흐름:
- Director 결과를 평가
- 필요 시 [agents/director.py](/Users/seogjaegwang/personal/youtube_humor/agents/director.py)의 `revise_plan()` 호출
- 단편/시리즈에 따라 revise 체크리스트도 다름

## 6. Image 경로

### 6.1 Imager
파일: [agents/imager.py](/Users/seogjaegwang/personal/youtube_humor/agents/imager.py)

역할:
- scene metadata를 읽고 `image_query` 생성

우선순위:
- `scene_outline + narration` = 사건 의미
- `cast, continuity_state, shot_plan, world_context, setting_hint, image_intent` = 시각 ground truth
- `original_title/original_story` = 보조 참고

### 6.2 최종 이미지 생성 프롬프트 조립
파일: [main.py](/Users/seogjaegwang/personal/youtube_humor/main.py)

최종 프롬프트 구성:
1. style `prompt_prefix`
2. `image_query`
3. style `prompt_suffix`
4. 한글 간판/표지 규칙
5. character profile hint
6. scene continuity hint
7. reference role hint
8. reference notes

관련 함수:
- `_build_image_query()`
- `_build_character_profile_hint()`
- `_build_scene_continuity_hint()`
- `_build_reference_role_hint()`
- `_build_reference_notes_hint()`
- `_build_previous_part_notes_hint()`

### 6.3 Character sheet
현재 편/시리즈 공통 인물 풀을 바탕으로 캐릭터 시트를 생성합니다.

### 6.4 Reference selection
파일: [tools/scene_reference_selector.py](/Users/seogjaegwang/personal/youtube_humor/tools/scene_reference_selector.py)

역할:
- 이전 scene 중 어떤 이미지 ref를 붙일지 선택
- 시리즈 후속편은 전편 장면까지 고려 가능

## 7. Speech Planner

파일: [agents/speech_planner.py](/Users/seogjaegwang/personal/youtube_humor/agents/speech_planner.py)

역할:
- scene narration을 `segments[]`로 나눔
- `narration` / `dialogue`
- `speaker`

입력:
- `characters`
- `scenes`
- `previous_voice_map`

출력:
- scene별 `segments`
- `voice_map`

현재 원칙:
- quote가 있어도 설명문 안 인용이면 narration 유지 가능
- scene context상 직접 발화일 때만 dialogue
- 애매하면 narration 우선

## 8. TTS / Render / Compose

### TTS
파일: [src/tts.py](/Users/seogjaegwang/personal/youtube_humor/src/tts.py)

역할:
- scene별 TTS 생성
- `voice_map` 반영

### 이미지 가공 / 자막
파일: [src/image_proc.py](/Users/seogjaegwang/personal/youtube_humor/src/image_proc.py)

역할:
- title/subtitle/top label 렌더
- narration 자막 렌더
- teaser overlay 렌더

### 영상 합성
파일: [tools/video_composer.py](/Users/seogjaegwang/personal/youtube_humor/tools/video_composer.py)

역할:
- scene clip 생성
- camera motion
- transition
- teaser clip
- BGM 합성
- 최종 MP4 출력

## 9. 업로드 / 분석 / 자동화

### 업로드
파일: [tools/youtube_uploader.py](/Users/seogjaegwang/personal/youtube_humor/tools/youtube_uploader.py)

역할:
- 업로드
- 쿼터 체크
- 업로드 대기열 처리

### 애널리틱스
파일: [tools/youtube_analytics.py](/Users/seogjaegwang/personal/youtube_humor/tools/youtube_analytics.py)

### 성과 분석
파일: [agents/analyzer.py](/Users/seogjaegwang/personal/youtube_humor/agents/analyzer.py)

역할:
- 업로드 후 성과 패턴 추출
- 이후 생성 시 `with-feedback` 입력에 활용

### 자동 모드
- `scheduler.py` 또는 `main.py --auto`
- 대기열 우선 업로드
- 패턴 로드
- 리서치
- 단편/시리즈 분기
- 생성 및 업로드

## 10. 산출물

실행 폴더 예:
- [output/20260309_015522_part1](/Users/seogjaegwang/personal/youtube_humor/output/20260309_015522_part1)

주요 파일:
- `research_brief.json`
- `production_plan.json`
- `script.json`
- `reference_scene_map.json`
- `previous_part_reference_map.json`
- `character_sheet.png`
- `raw_images/`
- `processed/`
- `tts/`
- `clips/`
- `[title].mp4`

## 11. 현재 구조상 중요한 점

1. 단편과 시리즈는 narrator/director가 분리되어 있음
2. 시리즈에서는 narrator가 전역 캐릭터 풀을 먼저 고정함
3. 단편에서는 director가 아직 캐릭터 생성 책임을 가짐
4. image prompt는 `Imager -> main.py wrapper -> image model` 2단 구조
5. speech planner는 narration을 rewrite하지 않고 segmentation만 담당
6. 비최종편은 teaser card를 자동으로 붙일 수 있음

## 12. 유지보수 포인트

우선순위가 높은 포인트:
- 단편 narrator도 `characters`를 생성하게 바꿀지 여부
- 이미지 모델의 readable Korean signage 정확도 개선
- speech planner quote/discourse 분리 품질 개선
- README와 dashboard 문서를 계속 현재 구조에 맞추는 것
