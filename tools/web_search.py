"""웹서치 도구 (Tavily API) - 리서치용 검색"""

from langchain_core.tools import tool
from config.settings import TAVILY_API_KEY

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None


_tavily = TavilyClient(api_key=TAVILY_API_KEY) if TavilyClient and TAVILY_API_KEY else None


@tool
def search_web(query: str, max_results: int = 5, search_depth: str = "advanced") -> str:
    """웹에서 특정 주제를 검색해 URL 후보를 수집합니다.
    query: 검색어 (한국어 또는 영어)
    max_results: 반환할 최대 결과 수 (1~20)
    search_depth: basic 또는 advanced
    """
    if _tavily is None:
        return "웹서치 사용 불가: Tavily 설정(패키지/API 키)을 확인하세요."
    try:
        try:
            max_results = int(max_results)
        except Exception:
            max_results = 5
        max_results = max(1, min(20, max_results))

        depth = str(search_depth or "advanced").strip().lower()
        if depth not in {"basic", "advanced"}:
            depth = "advanced"

        result = _tavily.search(
            query=query,
            search_depth=depth,
            max_results=max_results,
            include_answer=True,
        )

        parts = []

        if result.get("answer"):
            parts.append(f"**요약**: {result['answer']}\n")

        for i, r in enumerate(result.get("results", []), 1):
            score = r.get("score")
            score_text = f" | score: {score:.3f}" if isinstance(score, (float, int)) else ""
            parts.append(
                f"[{i}] **{r.get('title', '')}**{score_text}\n"
                f"  URL: {r.get('url', '')}\n"
                f"  내용: {r.get('content', '')[:2000]}"
            )

        return "\n\n".join(parts) if parts else "검색 결과가 없습니다."
    except Exception as e:
        return f"웹서치 에러: {e}"


SEARCH_TOOLS = [search_web]
