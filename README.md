# youtube_humor

`youtube_humor`는 한국형 사이다/반전/웃긴 썰을 자동으로 리서치하고, 9:16 쇼츠 영상으로 생성하고, 업로드 후 성과를 다시 분석하는 **멀티 에이전트 YouTube Shorts 자동화 시스템**입니다.

이 저장소는 단순한 "영상 생성 스크립트"가 아니라 아래를 모두 포함하는 **AI 개발자 포트폴리오용 시스템 프로젝트**입니다.

- 툴 사용형 리서치 에이전트
- 서사 설계용 planning agent 조합
- 이미지 생성 후 품질 검수와 선택적 재생성
- TTS, 자막/레이아웃, FFmpeg 합성
- YouTube 업로드 및 애널리틱스 수집
- 메인/복구 스케줄러와 운영 대시보드

## 한눈에 보는 핵심 워크플로우

```text
Researcher
  -> Narrator
  -> Director
  -> Critic
  -> Imager
  -> Speech Planner
  -> Character Sheet / Reference Selection / Image Generation
  -> Image Critic / Selective Regeneration
  -> TTS
  -> Image Processing
  -> Video Compose
  -> Upload
  -> Analytics / Pattern Feedback
```

## 프로젝트가 다루는 문제

보통 쇼츠 자동화는 아래 중 하나만 잘하는 경우가 많습니다.

- 주제 수집
- 대본 생성
- 이미지 생성
- 업로드 자동화

이 프로젝트는 이걸 **한 파이프라인으로 묶고**, 실제 운영을 위한 요소까지 포함합니다.

- 같은 인물이 장면마다 유지되도록 캐릭터 시트/레퍼런스 사용
- 단편과 시리즈를 다른 planning 전략으로 분리
- 화자 분리와 보이스 매핑
- 생성 이미지의 텍스트 오류/연속성 오류를 잡는 image critic
- 업로드 후 조회수/CTR/패턴 분석
- 실패 슬롯 복구 스케줄러
- FastAPI + Next.js 기반 운영 대시보드

## 시스템 아키텍처

### 1. 생성 레이어

이 레이어는 실제 콘텐츠를 만듭니다.

- `Researcher`
  - 웹 검색과 본문 확인을 통해 리서치 브리프 생성
- `Narrator`
  - 스타일/BGM/장면 흐름/나레이션 생성
- `Director`
  - 제목, 설명, 태그, cast, continuity, shot plan, visual metadata 확장
- `Critic`
  - story structure와 scene plan 품질 점검 후 수정 루프 수행
- `Imager`
  - 장면 메타를 이미지 모델용 `image_query`로 변환
- `Speech Planner`
  - narration을 speech segment로 분리하고 speaker/voice mapping 생성
- `Image Critic`
  - 생성된 장면 이미지를 보고 텍스트 불일치, continuity, composition, readability 문제를 찾고 필요한 장면만 재생성

### 2. 렌더 레이어

이 레이어는 planning 결과를 실제 쇼츠 영상으로 바꿉니다.

- 캐릭터 시트 생성
- 장면별 reference image 선택
- Gemini 이미지 생성
- Gemini TTS 음성 생성
- Pillow 기반 오버레이/배경 처리
- FFmpeg 기반 클립 연결, 전환, BGM, 효과음, 최종 MP4 렌더

### 3. 운영 레이어

이 레이어는 "한 번 만들어보는 데모"가 아니라, 실제 운영 가능한 자동화 시스템을 만듭니다.

- 메인 스케줄러
- 복구 스케줄러
- 업로드 후 YouTube Analytics 수집
- Supabase 기반 영상/실행/패턴/애널리틱스 저장
- FastAPI + Next.js 대시보드

## End-to-End 워크플로우 상세

### 1. Researcher

파일: `agents/researcher.py`

역할:
- Tavily 검색
- 본문 크롤링
- 실제 읽을 만한 원문 2개 이상 비교
- 최근 업로드/중복 주제 회피

출력:
- `topic`
- `original_title`
- `original_story`
- `story_type`
- `source_region`
- `style_suggestion`
- `series_potential`
- `emotion`

특징:
- 단순 키워드 리라이트가 아니라, 검색과 본문 읽기를 반복하는 ReAct형 리서처입니다.
- 툴 호출은 `search_web`, `crawl_article` 중심으로 구성됩니다.

### 2. Narrator

파일: `agents/narrator.py`

역할:
- 이야기 밀도에 맞춰 scene 수 결정
- 스타일/BGM 선택
- scene seed와 narration 생성

현재 규칙:
- 장면 수: `6~10`
- 장면당 나레이션: `1~2문장`, `65자 이내`
- 자연스러운 구어체 한국어
- 서사 흐름 안에서 어색하게 튀지 않는 구어체 사용

단편:
- 하나의 standalone episode를 만듭니다.

시리즈:
- `2~3` 파트 구조를 한 번에 설계합니다.
- `characters`, `parts`, `cliffhanger`까지 생성합니다.

### 3. Director

파일: `agents/director.py`

역할:
- Narrator seed를 production plan으로 확장
- 시각화에 필요한 메타를 구체화

생성 항목 예시:
- `title`
- `subtitle`
- `description`
- `summary`
- `tags`
- `characters`
- 장면별 `cast`
- `continuity_state`
- `shot_plan`
- `world_context`
- `camera`
- `transition`

### 4. Critic

파일: `agents/critic.py`

역할:
- Director 결과를 검토
- 구조, 감정선, payoff, visual alignment를 점검
- 필요하면 Director revise 루프 수행

즉 이 단계는 "이미지"를 보는 critic이 아니라, **스토리/플랜 critic**입니다.

### 5. Imager

파일: `agents/imager.py`

역할:
- scene metadata를 기반으로 `image_query` 생성

입력으로 주로 보는 것:
- `scene_outline`
- `narration`
- `image_intent`
- `setting_hint`
- `cast`
- `continuity_state`
- `shot_plan`
- `world_context`

### 6. Speech Planner

파일: `agents/speech_planner.py`

역할:
- narration을 speech segment 단위로 분해
- `narration`과 `dialogue`를 구분
- speaker별 voice assignment 생성

출력:
- scene별 `segments`
- 전체 `voice_map`

특징:
- narration 자체를 다시 쓰는 게 아니라
- 어떤 문장을 누가 어떤 톤으로 읽을지 분해하는 단계입니다.

### 7. Character Sheet / Reference Selection / Image Generation

관련 파일:
- `main.py`
- `tools/scene_reference_selector.py`
- `src/image_source.py`

흐름:
1. 캐릭터 시트 생성
2. 이전 장면/전편 장면 중 필요한 레퍼런스 선택
3. `main.py`가 최종 프롬프트를 조립
4. Gemini 이미지 모델로 9:16 장면 생성

최종 이미지 프롬프트에 포함되는 것:
- 스타일 prefix / suffix
- `image_query`
- 캐릭터 identity 힌트
- continuity 힌트
- reference role 설명
- anatomy guard

### 8. Image Critic / Selective Regeneration

파일:
- `agents/image_critic.py`
- `main.py`

이 프로젝트의 현재 핵심 차별점 중 하나입니다.

역할:
- 생성된 장면 이미지 전체를 한 번에 검수
- narration/scene metadata와 실제 이미지 정합성 체크
- 문제 장면만 선택적으로 재생성

대표적으로 잡는 문제:
- note / sign / screen 텍스트 불일치
- character continuity 깨짐
- location type mismatch
- composition/readability 문제
- anatomy artifact

재생성 전략:
- 전체를 다시 그리지 않음
- 문제 장면만 재생성
- 현재 깨진 이미지 + character sheet + critic이 고른 same-episode anchor만 ref로 사용
- 원본보다 나아진 장면만 최종 파이프라인에 반영

이 구조는 단순 생성보다 한 단계 더 나아간 **multimodal evaluation + correction loop** 입니다.

### 9. TTS

파일: `src/tts.py`

역할:
- Gemini TTS로 장면별 음성 생성
- narrator/character voice 분기
- 스타일 힌트 반영
- 모델 폴백 및 재시도

현재 특징:
- narrator는 고정된 storyteller 톤을 유지하도록 설계
- 장면별 화자 voice_map 기반으로 음성 선택
- 재시도 및 모델 폴백 내장

### 10. Image Processing / Compose

관련 파일:
- `src/image_proc.py`
- `tools/video_composer.py`
- `src/video.py`
- `src/effects.py`

역할:
- 배경/오버레이 이미지 생성
- 자막/레이아웃 렌더
- 장면별 motion 적용
- 효과음, 전환, BGM 연결
- 최종 MP4 생성

### 11. Upload / Analytics / Feedback

관련 파일:
- `main.py`
- `tools/youtube_uploader.py`
- `tools/youtube_analytics.py`
- `agents/analyzer.py`

역할:
- YouTube 업로드
- `videos`, `runs`, `analytics`, `patterns` 저장
- 업로드 후 성과 수집
- pattern feedback 생성
- 다음 리서치/생성에 반영

즉 이 프로젝트는 `생성 -> 업로드`로 끝나지 않고, **성과 피드백이 다음 생성에 다시 들어가는 closed loop** 입니다.

## 단편 / 시리즈 / 비교 모드

### 단편

기본 모드입니다.

```text
Researcher -> Single Narrator -> Single Director -> Critic -> ...
```

### 시리즈

시리즈는 planning 전략이 다릅니다.

```text
Researcher
  -> Series Narrator
  -> Series Director (편별)
  -> 이후 단편과 동일
```

특징:
- `Series Narrator`가 전체 파트 구조를 한 번에 설계
- 공통 `characters`를 먼저 고정
- 후속편은 이전 편 장면과 voice map을 재사용

### 비교 모드

같은 planning 결과를 바탕으로 motion/layout만 바꿔 여러 버전을 렌더합니다.

포트폴리오 관점에서는 **creative A/B testing pipeline** 으로 볼 수 있습니다.

## 운영 자동화 구조

### 메인 스케줄러

파일: `scheduler.py`

역할:
- 정규 슬롯 생성/업로드
- 헬스 체크
- 애널리틱스 수집
- 패턴 분석

### 복구 스케줄러

파일: `scheduler_2.py`

역할:
- 최근 슬롯에 누락된 업로드 결과가 있는지 점검
- 필요하면 `scheduler_jobs.py`를 통해 해당 슬롯 재실행

### 공통 작업 로직

파일: `scheduler_jobs.py`

역할:
- slot lock
- 중복 실행 방지
- `job_generate_and_upload`
- 누락 슬롯 복구

즉 이 프로젝트는 "AI 영상 생성기"를 넘어 **운영 가능한 autonomous content pipeline** 형태를 갖고 있습니다.

## 운영 대시보드

디렉토리: `dashboard/`

구성:
- `dashboard/api`: FastAPI
- `dashboard/web`: Next.js

할 수 있는 것:
- 메인/복구 스케줄러 상태 확인
- 시작/정지
- 최신 실행 기록 조회
- 영상 목록/상세 조회
- 성과 지표/패턴 보기
- 시스템 로그 확인

## 기술 스택

| 영역 | 스택 |
|---|---|
| LLM / planning | Gemini |
| Search | Tavily |
| Crawling / parsing | custom fetchers + content extraction |
| Image generation | Gemini image generation path |
| Image evaluation | custom image critic + selective regeneration |
| TTS | Gemini TTS |
| Image processing | Pillow |
| Final rendering | FFmpeg |
| Storage / metadata | Supabase |
| Upload / analytics | YouTube Data API, YouTube Analytics API |
| Scheduling | APScheduler |
| Dashboard backend | FastAPI |
| Dashboard frontend | Next.js |

## 저장소 구조

```text
youtube_humor/
├── main.py
├── scheduler.py
├── scheduler_2.py
├── scheduler_jobs.py
├── agents/
├── tools/
├── src/
├── config/
├── styles/
├── assets/
├── dashboard/
├── docs/
├── supabase/
└── output/
```

### 핵심 디렉토리 설명

- `agents/`
  - LLM 기반 planning / evaluation 계층
- `tools/`
  - 검색, 업로드, 분석, reference selection, style loading 등 서비스 유틸
- `src/`
  - 이미지 소싱, TTS, 렌더링 등 실행 계층
- `config/`
  - 모델, TTS, scene gap, critic 옵션 등 설정
- `styles/`
  - motion/layout/BGM/style preset
- `dashboard/`
  - 운영 대시보드
- `output/`
  - 1회 실행 결과물 저장

## 실행 예시

```bash
# 기본: 리서처가 주제 자동 선정
python main.py

# 주제 힌트 제공
python main.py "불륜 복수 썰"

# 스타일 강제
python main.py --style storytelling

# 업로드 포함
python main.py --upload

# 업로드 없이 확인
python main.py --upload --dry-run

# 피드백 반영
python main.py --with-feedback

# 비교 렌더
python main.py --compare

# 자동 모드
python main.py --auto

# 애널리틱스 수집
python main.py --analyze

# OAuth 인증
python main.py --auth
```

스케줄러:

```bash
python scheduler.py
python scheduler.py --once
python scheduler_2.py
python scheduler_2.py --once
```

## 실행 결과물 구조

기본 출력 경로:
- `output/YYYYMMDD_HHMMSS[_partN]/`

대표 산출물:

```text
output/YYYYMMDD_HHMMSS[_partN]/
├── research_brief.json
├── production_plan.json
├── script.json
├── reference_scene_map.json
├── previous_part_reference_map.json   # 시리즈 후속편일 때만
├── character_sheet.png
├── image_critic_review.json
├── image_critic_applied.json
├── raw_images/
├── raw_images_critic/
├── processed/
│   ├── bg/
│   └── overlay/
├── tts/
├── clips/
└── [title].mp4
```

이 구조 덕분에 한 번의 실행이:
- 어떤 리서치에서 시작됐는지
- 어떤 장면 계획이 나왔는지
- 어떤 이미지가 critic에서 교체됐는지
- 최종 영상이 무엇인지

를 나중에 재현 가능하게 남깁니다.

## 이 프로젝트에서 보여주고 싶은 엔지니어링 포인트

포트폴리오 관점에서 이 저장소가 보여주는 건 아래입니다.

- **멀티 에이전트 오케스트레이션**
  - research / narration / directing / evaluation / speech planning
- **툴 사용형 리서치 자동화**
  - 검색 + 본문 확인 + 필터링
- **멀티모달 생성 파이프라인**
  - text -> plan -> image -> speech -> video
- **LLM 결과물 검수 루프**
  - plan critic
  - image critic
- **선택적 재생성 전략**
  - 전체 재생성이 아니라 문제 장면만 수정
- **운영 자동화**
  - main scheduler + recovery scheduler + dashboard
- **closed-loop optimization**
  - 업로드 후 analytics/patterns가 다음 생성에 다시 반영

## 참고 문서

- `docs/architecture.md`
- `docs/shorts_market_plan_2026.md`

이 README는 포트폴리오용 개요 중심입니다. 더 세부적인 구현 메모는 `docs/` 아래 문서로 확장할 수 있습니다.
