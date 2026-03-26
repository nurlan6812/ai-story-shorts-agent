"""Researcher Agent - 유머/썰/사연 전문 리서처 (웹 검색 + 본문 크롤링)"""

import json
from urllib.parse import urldefrag
from google.genai import types
from src.genai_client import create_genai_client
from tools.content_fetcher import crawl_article
from tools.web_search import search_web

client = create_genai_client()
MODEL = "gemini-3.1-pro-preview"

ALL_TOOLS = [search_web, crawl_article]


def _to_gemini_func_decl(lc_tool):
    """LangChain tool을 Gemini FunctionDeclaration으로 변환"""
    schema = lc_tool.args_schema.model_json_schema() if lc_tool.args_schema else {}
    properties = {}
    required = []

    for name, prop in schema.get("properties", {}).items():
        prop_type = prop.get("type", "string")
        type_map = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
        }
        properties[name] = {
            "type": type_map.get(prop_type, "STRING"),
            "description": prop.get("description", prop.get("title", "")),
        }
        if "default" not in prop:
            required.append(name)

    return {
        "name": lc_tool.name,
        "description": lc_tool.description,
        "parameters": {
            "type": "OBJECT",
            "properties": properties,
            "required": required,
        },
    }


TOOL_MAP = {t.name: t for t in ALL_TOOLS}

GEMINI_TOOLS = types.Tool(
    function_declarations=[_to_gemini_func_decl(t) for t in ALL_TOOLS]
)

SYSTEM_PROMPT = """당신은 유머/썰/사연 전문 리서처입니다.
목표는 웹에서 조회수 잠재력이 높은 스토리 1개를 찾아, 후속 에이전트가 바로 쓸 수 있는 리서치 브리프(JSON)로 정리하는 것입니다.

## 사용 가능한 도구 (딱 2개)
- search_web(query, max_results, search_depth): 웹 검색으로 후보 URL을 수집
- crawl_article(url): 선택한 URL 본문을 실제로 읽어 핵심 내용 추출

## ReAct 운영 원칙 (중요)
- 고정 순서가 아니라, 필요한 만큼 도구를 자율적으로 호출하세요.
- 한 번 검색해 결과가 빈약하면 멈추지 말고 재검색하세요.
- 최종 JSON 출력 전에는 crawl_article로 원문 본문을 반드시 확인하고, 가능하면 서로 다른 후보 URL 2개 이상을 읽고 비교한 뒤 선정하세요.
- 같은 URL을 include_images=true로 다시 읽는 것은 동일 후보 재확인일 뿐, 새 후보 비교로 간주하지 마세요.
- 웹에는 본문이 텍스트가 아니라 이미지(짤/캡처)로 올라온 글이 많습니다. 텍스트가 빈약하면 image 기반 가능성을 반드시 점검하세요.
- 재검색 시에는 아래를 LLM이 판단해 조정하세요:
  1) 검색어 재작성 (동의어/상황 키워드/갈등 키워드/결말 키워드 추가)
  2) max_results 확장 (예: 5 → 10 → 15 → 20)
  3) search_depth 조정 (basic/advanced)
- 원하는 품질의 후보를 못 찾았으면, 충분히 반복 탐색한 뒤에만 결론을 내리세요.

## 조사 전략
1) 넓은 검색어로 후보군 확보
2) 상위 URL 중 흥미도가 높은 2~5개 후보를 골라 crawl_article로 본문 확인
   - 본문 텍스트가 짧거나 비어 보이면 crawl_article(url, include_images=true)로 이미지 URL까지 확인
   - 이미지 중심 게시물은 "텍스트 추출 한계가 있을 수 있음"을 인지하고, 과도한 추론을 피한 상태로 근거를 정리
3) 내용이 뻔하거나 빈약하면 폐기하고, 검색어를 바꿔 다시 search_web
4) 최종적으로 가장 강한 1개를 선정
   - 검색 결과가 극도로 빈약할 때만, 검색어/결과 수/깊이를 충분히 넓혀 다시 탐색한 뒤 1개 후보로 종료할 수 있습니다
5) 선정한 원문의 핵심 사건 흐름/감정선을 original_story에 충실히 정리

## Shorts 주제 선정 원칙
- 공개 조회수보다 시청자가 계속 보게 만드는 힘(retention, viewed vs swiped away, replay 가능성)을 더 중요하게 보세요.
- 아래 요소를 맥락에 따라 균형 있게 보고 자율 판단하세요 (고정 순위/공식 강제 금지).
- 즉시 이해되는 상황인지
- 감정 몰입과 공감이 가능한지
- 반전/결말 임팩트가 있는지
- 장면으로 시각화하기 쉬운지
- 60초 내 압축 전달이 가능한지

## 시리즈 판단 기준
원칙: 단편(1편 완결) 우선입니다.
가능하면 반드시 단편으로 끝내세요. 60초 내 핵심 전달이 가능하면 series_potential은 false로 두세요.

이야기가 다음 중 하나에 해당하면 series_potential을 true로 판단하세요:
- 이야기가 60초에 다 담기엔 전개가 풍부한 경우 (핵심 사건/감정 전환이 많음)
- 뚜렷한 중간 클리프행어(반전/위기)가 있어서 "다음편이 궁금해!" 를 유발할 수 있는 경우
- 원본 이야기가 한 편으로 압축하기 어려울 만큼 길고 여러 에피소드/국면으로 나뉘는 경우
Narrator가 필요하면 2~3편 구조로 설계합니다. 1편만으로 충분하면 series_potential은 false로 두세요.

## 출력 형식
조사가 끝나면 반드시 아래 JSON 형식으로 리서치 브리프를 출력하세요:

```json
{
  "topic": "쇼츠 주제 (한국어, 흥미유발, 짧게)",
  "story_type": "funny|touching|revenge|absurd|scary|wholesome",
  "source_region": "한국|외국",
  "original_title": "원문 게시글 제목 (가능한 원문 그대로)",
  "original_story": "원문 핵심 본문",
  "emotion": "humor|heartwarming|satisfying|shocking|relatable",
  "style_suggestion": "casual|storytelling|darkcomedy|wholesome|absurdist",
  "series_potential": true|false
}
```

시리즈 작성 규칙:
- researcher는 시리즈 여부(series_potential)만 판단하세요.
- part_focus/cliffhanger/편 분할 구조는 Narrator가 설계합니다.

주의:
- 반드시 crawl_article로 원문을 읽고 브리프를 작성하세요
- crawl_article 호출 없이 추론만으로 브리프를 작성하지 마세요
- 확인한 원문 근거를 바탕으로 구체적인 상황/대사를 original_story에 반영하세요
- 텍스트 본문이 약한 경우 image 기반 게시물 가능성을 명시하고, 확인한 이미지 URL/텍스트 근거 범위 안에서만 요약하세요
- source_region은 반드시 분류하세요: 국내면 한국, 해외면 외국
- source_region이 외국이면 topic/original_story에서 한국 밈/은어 사용 금지
- source_region이 외국이면 중립 표현을 사용하고 원문 문화권 맥락을 유지하세요
- original_title은 가능한 원문 제목 그대로 적으세요
- original_story에는 원문 핵심 본문을 충실히 담으세요
- 혐오/차별/정치적 논란이 될 수 있는 이야기는 반드시 피하세요
- JSON 블록 외에 다른 텍스트를 추가하지 마세요"""


def _normalize_candidate_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    normalized = urldefrag(url)[0].strip()
    if normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def research(hint: str = "", trend_hints: list[str] | None = None) -> dict:
    """웹 검색 + 본문 크롤링으로 유머/썰 쇼츠 주제를 찾습니다.

    Args:
        hint: 선택적 힌트 (예: "황당한 썰", "감동 사연"). 빈 문자열이면 완전 자율.
        trend_hints: 과거 성과 분석에서 추출된 인기 주제 힌트 목록

    Returns:
        ResearchBrief dict
    """
    user_msg = (
        f"'{hint}' 관련 재미있는 이야기를 조사하여 유튜브 쇼츠 주제를 찾으세요."
        if hint
        else "오늘 가장 재미있거나 감동적인 썰/사연을 조사하여 유튜브 쇼츠 주제를 찾으세요."
    )

    if trend_hints:
        hints_str = ", ".join(trend_hints)
        user_msg += f"\n\n참고: 최근 시청자 반응이 좋았던 주제 키워드: {hints_str}. 관련 최신 이야기가 있다면 우선 고려하세요."

    # 마지막 업로드 시간 안내
    try:
        from tools.supabase_client import get_last_upload_time
        last_upload = get_last_upload_time()
        if last_upload:
            user_msg += (
                f"\n\n⏰ 마지막 영상 업로드: {last_upload}. "
                f"이 이후에 올라온 이야기를 우선적으로 찾으세요. "
                f"이미 다룬 이야기를 반복하지 마세요."
            )
    except Exception:
        pass

    # 중복 방지: 최근 만든 영상 주제 목록
    try:
        from tools.supabase_client import get_recent_topics
        recent = get_recent_topics(days=7, limit=20)
        if recent:
            topics_str = "\n".join(f"  - {t}" for t in recent)
            user_msg += (
                f"\n\n⚠️ 중복 금지! 아래 주제는 최근 이미 영상을 만들었으니 "
                f"같은 내용을 피하세요:\n{topics_str}"
            )
    except Exception:
        pass

    contents = [user_msg]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[GEMINI_TOOLS],
        temperature=0.7,
    )

    # ReAct 루프: 도구 호출 → 결과 → 다시 생각
    # while 기반으로 자율 반복하고, 비정상 무한 호출만 상한으로 차단한다.
    response = None
    react_steps = 0
    max_react_steps = 30
    min_required_distinct_crawls = 2
    relaxed_min_distinct_crawls = 1
    search_web_calls = 0
    crawled_candidate_urls: set[str] = set()
    crawl_enforce_prompts = 0
    max_crawl_enforce_prompts = 6
    relaxed_completion_min_search_calls = 3
    relaxed_completion_min_enforce_prompts = 4
    while True:
        react_steps += 1
        if react_steps > max_react_steps:
            raise RuntimeError(
                f"Research ReAct step overflow: {max_react_steps}회 초과"
            )

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )

        # 도구 호출이 있는지 확인
        func_calls = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                func_calls.append(part.function_call)

        if not func_calls:
            distinct_crawl_count = len(crawled_candidate_urls)
            allow_relaxed_completion = (
                distinct_crawl_count >= relaxed_min_distinct_crawls
                and search_web_calls >= relaxed_completion_min_search_calls
                and crawl_enforce_prompts >= relaxed_completion_min_enforce_prompts
            )
            # 품질 확보: 최종 브리프 전 서로 다른 후보 URL 최소 2개 비교를 우선 강제
            if distinct_crawl_count < min_required_distinct_crawls and not allow_relaxed_completion:
                crawl_enforce_prompts += 1
                if crawl_enforce_prompts > max_crawl_enforce_prompts:
                    raise RuntimeError(
                        "Research 종료 전 서로 다른 후보 URL 비교 조건을 만족하지 못했습니다."
                    )
                contents.append(response.candidates[0].content)
                if distinct_crawl_count == 0:
                    contents.append(
                        "아직 crawl_article로 읽은 후보가 없습니다. search_web 결과 URL 중 1개 이상을 선택해 "
                        "crawl_article로 원문 본문을 확인한 뒤 계속 진행하세요."
                    )
                else:
                    contents.append(
                        "현재 서로 다른 후보 본문을 1개만 확인했습니다. 최종 선정 전에는 원칙적으로 "
                        "서로 다른 URL 2개 이상을 crawl_article로 읽고 비교해야 합니다. "
                        "다른 URL을 1개 이상 더 골라 crawl_article로 확인하세요. "
                        "검색 결과가 빈약하면 search_web를 다시 호출해 검색어, max_results, search_depth를 넓혀 보세요."
                    )
                continue
            break

        # 도구 호출 실행 (같은 턴 내 병렬)
        contents.append(response.candidates[0].content)

        for fc in func_calls:
            print(f"  🔧 [{fc.name}] {dict(fc.args) if fc.args else {}}")
            if fc.name == "crawl_article":
                crawl_url = _normalize_candidate_url(dict(fc.args).get("url", "") if fc.args else "")
                if crawl_url:
                    crawled_candidate_urls.add(crawl_url)
            elif fc.name == "search_web":
                search_web_calls += 1

        def _invoke_tool(fc):
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            if tool_name in TOOL_MAP:
                try:
                    result = TOOL_MAP[tool_name].invoke(tool_args)
                except Exception as e:
                    result = f"도구 실행 에러: {e}"
            else:
                result = f"알 수 없는 도구: {tool_name}"
            return types.Part.from_function_response(
                name=tool_name,
                response={"result": str(result)[:10000]},
            )

        func_responses = [_invoke_tool(fc) for fc in func_calls]

        contents.append(types.Content(parts=func_responses, role="user"))

    # 최종 응답에서 JSON 추출
    final_text = response.text
    return _parse_research_brief(final_text)


def _parse_research_brief(text: str) -> dict:
    """응답에서 리서치 브리프 JSON 추출"""
    text = text.strip()

    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end]
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end]

    if text.startswith("json"):
        text = text[4:]

    return json.loads(text.strip())
