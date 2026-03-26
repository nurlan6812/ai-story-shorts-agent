"""유머/썰/사연 콘텐츠 수집 도구 (Reddit JSON API + Playwright 크롤링)"""

import html
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests
from google import genai
from google.genai import types
from langchain_core.tools import tool
from playwright.sync_api import sync_playwright

from src.genai_client import create_genai_client, has_genai_credentials

_INSTAGRAM_COOKIE_PATH = Path(__file__).resolve().parents[1] / "instagram_state.json"
_INSTAGRAM_MAX_IMAGES_PER_POST = 4

_EXTRACT_INSTAGRAM_POST_JS = """() => {
    const scripts = document.querySelectorAll('script[type="application/json"]');
    for (const s of scripts) {
        const text = s.textContent || "";
        if (!text.includes('image_versions2')) continue;
        try {
            const data = JSON.parse(text);
            function findItem(obj) {
                if (!obj || typeof obj !== 'object') return null;
                if (obj.items && Array.isArray(obj.items) && obj.items[0]?.image_versions2) {
                    return obj.items[0];
                }
                for (const val of Object.values(obj)) {
                    const found = findItem(val);
                    if (found) return found;
                }
                return null;
            }

            const item = findItem(data);
            if (!item) continue;

            const caption = item.caption?.text || "";
            const imageUrls = [];
            const carousel = item.carousel_media || [item];
            for (const media of carousel) {
                const candidates = media.image_versions2?.candidates || [];
                if (!candidates.length) continue;
                const best = candidates.reduce((a, b) =>
                    (a.width * a.height > b.width * b.height) ? a : b
                );
                if (best?.url) imageUrls.push(best.url);
            }
            return { caption, imageUrls };
        } catch (e) {
            continue;
        }
    }
    return null;
}"""


def _parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}


def _build_instagram_story_prompt(keyword: str) -> str:
    return f"""아래 인스타그램 포스트의 캡션과 이미지들을 보고, "{keyword}" 키워드와 연관된
썰/사연형 텍스트를 최대한 정확히 추출하세요.

중요:
- 이미지 안 텍스트(오버레이/본문/자막)를 OCR처럼 읽어 반영하세요.
- 광고/해시태그 나열/이모지 도배는 최소화하세요.
- 실제 스토리 전개가 보이는 핵심 본문으로 정리하세요.

JSON만 출력:
{{
  "title": "포스트 핵심 제목(짧게)",
  "story": "핵심 본문 3~6문장",
  "ocr_text": "이미지에서 읽은 주요 텍스트 요약(없으면 빈 문자열)"
}}"""


def _extract_story_with_gemini(keyword: str, caption: str, image_urls: list[str]) -> dict:
    if not has_genai_credentials():
        return {
            "title": "캡션 기반 추출",
            "story": caption[:600] if caption else "",
            "ocr_text": "",
        }

    client = create_genai_client()
    prompt = _build_instagram_story_prompt(keyword)

    content = [prompt]
    if caption:
        content.append(f"캡션:\n{caption[:2500]}")
    for url in image_urls[:_INSTAGRAM_MAX_IMAGES_PER_POST]:
        content.append(types.Part.from_uri(file_uri=url, mime_type="image/jpeg"))

    try:
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=content,
        )
        parsed = _parse_json_object(response.text or "")
        if parsed.get("story"):
            return parsed
    except Exception:
        pass

    # 이미지 URL 접근 실패 등을 고려한 캡션 전용 폴백
    text_only = [prompt]
    if caption:
        text_only.append(f"캡션:\n{caption[:2500]}")

    try:
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=text_only,
        )
        parsed = _parse_json_object(response.text or "")
        if parsed.get("story"):
            return parsed
    except Exception:
        pass

    return {
        "title": "캡션 기반 추출",
        "story": caption[:600] if caption else "",
        "ocr_text": "",
    }


def _collect_instagram_post_links(page, max_posts: int) -> list[str]:
    links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
                .map(a => a.href)"""
    ) or []

    seen = set()
    unique = []
    for link in links:
        short = str(link).split("?")[0]
        if not short or short in seen:
            continue
        seen.add(short)
        unique.append(short)
        if len(unique) >= max_posts:
            break
    return unique


def _collect_instagram_post_payload(page, url: str) -> dict | None:
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    try:
        page.wait_for_selector('script[type="application/json"]', timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(500)

    post_data = page.evaluate(_EXTRACT_INSTAGRAM_POST_JS)
    if not post_data:
        return None

    caption = str(post_data.get("caption", "")).strip()
    image_urls = [
        str(u) for u in (post_data.get("imageUrls", []) or [])
        if str(u).strip()
    ][: _INSTAGRAM_MAX_IMAGES_PER_POST]
    return {"url": url, "caption": caption, "image_urls": image_urls}


def _to_naver_cafe_mobile_url(url: str) -> str:
    """네이버 카페 URL을 모바일 웹 article URL로 정규화합니다."""
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        split = urlsplit(raw)
    except Exception:
        return raw

    host = (split.netloc or "").lower()
    if host == "m.cafe.naver.com":
        return raw
    if host != "cafe.naver.com":
        return raw

    path = split.path or ""
    query = parse_qs(split.query or "")
    club_id = ""
    article_id = ""

    # classic: /ArticleRead.nhn?clubid=...&articleid=...
    if path.endswith("/ArticleRead.nhn") or path == "/ArticleRead.nhn":
        club_id = ((query.get("clubid") or [""])[0] or "").strip()
        article_id = ((query.get("articleid") or [""])[0] or "").strip()

    # modern: /f-e/cafes/{club}/articles/{article} or /ca-fe/cafes/{club}/articles/{article}
    if not (club_id and article_id):
        tokens = [t for t in path.split("/") if t]
        # ["f-e","cafes","31372428","articles","7087"] 형태
        if len(tokens) >= 5 and tokens[1] == "cafes" and tokens[3] == "articles":
            club_id = tokens[2].strip()
            article_id = tokens[4].strip()

    if not (club_id and article_id):
        return raw

    mobile_path = f"/ca-fe/web/cafes/{club_id}/articles/{article_id}"
    return urlunsplit(("https", "m.cafe.naver.com", mobile_path, "", ""))


def _to_reddit_json_url(url: str) -> str | None:
    """Reddit 게시글 URL을 .json URL로 정규화합니다."""
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        split = urlsplit(raw)
    except Exception:
        return None

    host = (split.netloc or "").lower()
    if "reddit.com" not in host:
        return None

    path = (split.path or "").rstrip("/")
    if not path:
        return None
    if "/comments/" not in path:
        return None
    if not path.endswith(".json"):
        path = f"{path}.json"

    # old/new/mobile 하위도메인 이슈를 피하기 위해 www 고정
    return urlunsplit(("https", "www.reddit.com", path, "raw_json=1", ""))


def _extract_reddit_image_urls(post_data: dict) -> list[str]:
    urls: list[str] = []

    preview = post_data.get("preview") or {}
    images = preview.get("images") or []
    for image_data in images:
        source = (image_data or {}).get("source") or {}
        src = source.get("url")
        if src:
            urls.append(html.unescape(str(src)))

    media_metadata = post_data.get("media_metadata") or {}
    for meta in media_metadata.values():
        source = (meta or {}).get("s") or {}
        src = source.get("u")
        if src:
            urls.append(html.unescape(str(src)))

    seen = set()
    unique = []
    for u in urls:
        key = u.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def _crawl_reddit_json(url: str, include_images: bool) -> str | None:
    headers = {"User-Agent": "youtube-humor-bot/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            return None

        post_children = (
            (((payload[0] or {}).get("data") or {}).get("children") or [])
            if isinstance(payload[0], dict)
            else []
        )
        if not post_children:
            return None

        post_data = (post_children[0] or {}).get("data") or {}
        title = str(post_data.get("title", "")).strip()
        selftext = str(post_data.get("selftext", "")).strip()

        permalink = str(post_data.get("permalink", "")).strip()
        final_url = f"https://www.reddit.com{permalink}" if permalink else url

        text_parts = []
        if selftext:
            text_parts.append(selftext)
        elif title:
            text_parts.append(title)

        # selftext가 약하면 상위 댓글 일부를 보강 텍스트로 사용
        if len("\n".join(text_parts)) < 200 and len(payload) > 1 and isinstance(payload[1], dict):
            comment_children = ((((payload[1] or {}).get("data") or {}).get("children")) or [])
            comment_lines = []
            for child in comment_children:
                data = (child or {}).get("data") or {}
                body = str(data.get("body", "")).strip()
                if len(body) < 40:
                    continue
                comment_lines.append(f"- {body}")
                if len(comment_lines) >= 5:
                    break
            if comment_lines:
                text_parts.append("상위 댓글:")
                text_parts.extend(comment_lines)

        body_text = "\n\n".join([p for p in text_parts if p]).strip()
        if not body_text:
            return None

        output = [
            f"제목: {title}" if title else "제목: (없음)",
            f"URL: {final_url}",
            "본문 루트: reddit_json",
            "",
            body_text,
        ]

        if include_images:
            image_urls = _extract_reddit_image_urls(post_data)[:20]
            if image_urls:
                output.append("\n이미지 URL:")
                for i, img_url in enumerate(image_urls, 1):
                    output.append(f"- [{i}] {img_url}")

        return "\n".join(output)[:15000]
    except Exception:
        return None


@tool
def crawl_article(url: str, include_images: bool = False) -> str:
    """게시글/기사 URL에서 본문을 크롤링합니다.
    url: 게시글 URL
    include_images: 본문 내 이미지 URL 포함 여부 (기본 false)
    """
    try:
        raw_url = (url or "").strip()
        if not raw_url:
            return "크롤링 에러: url이 비어 있습니다."

        include_images = bool(include_images)
        target_url = _to_naver_cafe_mobile_url(raw_url)

        reddit_json_url = _to_reddit_json_url(target_url)
        if reddit_json_url:
            reddit_output = _crawl_reddit_json(reddit_json_url, include_images)
            if reddit_output:
                return reddit_output

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            })
            page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)

            extracted = page.evaluate(
                """(includeImages) => {
                    const CANDIDATE_SELECTORS = [
                        "article",
                        "[role='main'] article",
                        "main article",
                        "#articleBodyContents",
                        ".article_view",
                        ".article-content",
                        ".entry-content",
                        ".post-content",
                        ".view-content",
                        ".se-main-container",
                        ".post_view",
                        ".rd_body",
                        "main",
                        "[role='main']",
                        ".content",
                        "#content",
                        "body"
                    ];

                    const SKIP_TAGS = new Set([
                        "SCRIPT", "STYLE", "NOSCRIPT", "SVG", "PATH",
                        "NAV", "FOOTER", "HEADER", "ASIDE", "FORM",
                        "BUTTON", "INPUT", "TEXTAREA", "SELECT"
                    ]);

                    const NEGATIVE_HINTS = [
                        "comment", "reply", "cmt", "reco", "recommend", "related",
                        "ranking", "rank", "popular", "best", "hot", "sponsor",
                        "banner", "advert", "ad_", "ads", "promotion", "share",
                        "sns", "paging", "pagination", "prev", "next", "side", "aside"
                    ];

                    const NOISE_TEXT_HINTS = [
                        "로그인", "회원가입", "댓글", "답글", "공유", "광고",
                        "관련기사", "이전글", "다음글", "목록", "추천", "비추천",
                        "저작권", "무단전재", "기사제보", "쿠키", "개인정보처리방침",
                        "네이트온 보내기", "페이스북 보내기", "트위터 보내기",
                        "최근 10분간의 데이터를 기준", "nate communications"
                    ];

                    const IMAGE_ATTRS = [
                        "src", "data-src", "data-original",
                        "data-lazy-src", "data-url", "data-image"
                    ];

                    function normalizeText(t) {
                        return (t || "").replace(/\\s+/g, " ").trim();
                    }

                    function normalizeUrl(u) {
                        if (!u) return "";
                        try {
                            return new URL(u, location.href).href;
                        } catch {
                            return String(u).trim();
                        }
                    }

                    function getImgUrl(img) {
                        if (img.currentSrc) {
                            const cur = normalizeUrl(img.currentSrc);
                            if (cur) return cur;
                        }
                        for (const attr of IMAGE_ATTRS) {
                            const val = img.getAttribute(attr);
                            if (val) {
                                const resolved = normalizeUrl(val);
                                if (resolved) return resolved;
                            }
                        }
                        return "";
                    }

                    function isVisible(el) {
                        if (!el || el.nodeType !== Node.ELEMENT_NODE) return true;
                        const style = window.getComputedStyle(el);
                        if (!style) return true;
                        return !(style.display === "none" || style.visibility === "hidden");
                    }

                    function getMetaText(el) {
                        if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
                        const cls = typeof el.className === "string" ? el.className : "";
                        return [
                            el.id || "",
                            cls,
                            el.getAttribute("role") || "",
                            el.getAttribute("aria-label") || "",
                            el.getAttribute("data-testid") || ""
                        ].join(" ").toLowerCase();
                    }

                    function hasNegativeHint(el) {
                        const meta = getMetaText(el);
                        return NEGATIVE_HINTS.some((k) => meta.includes(k));
                    }

                    function hasNoiseHintInText(text) {
                        return NOISE_TEXT_HINTS.some((k) => text.includes(k));
                    }

                    function scoreNode(node) {
                        if (!node) return 0;
                        const txt = normalizeText(node.innerText || "");
                        const txtLen = txt.length;
                        if (txtLen < 120) return -10000;

                        const linkTextLen = Array.from(node.querySelectorAll("a"))
                            .map((a) => normalizeText(a.innerText || "").length)
                            .reduce((acc, n) => acc + n, 0);
                        const linkDensity = Math.min(1, linkTextLen / Math.max(1, txtLen));

                        const anchorCount = node.querySelectorAll("a").length;
                        const pCount = node.querySelectorAll("p").length;
                        const liCount = node.querySelectorAll("li").length;
                        const imgCount = node.querySelectorAll("img").length;
                        const headingCount = node.querySelectorAll("h1, h2, h3").length;
                        const negativePenalty = hasNegativeHint(node) ? 1000 : 0;

                        let score =
                            txtLen * (1 - linkDensity)
                            + pCount * 180
                            + headingCount * 120
                            + imgCount * 50
                            - liCount * 25
                            - anchorCount * 6
                            - negativePenalty;

                        if (linkDensity > 0.70) score -= 900;
                        if (linkDensity > 0.85) score -= 1400;
                        if (txtLen > 4500 && linkDensity > 0.60) score -= 1200;
                        if (pCount === 0 && liCount > 10) score -= 700;

                        return score;
                    }

                    let bestRoot = null;
                    let bestSelector = "body";
                    let bestScore = 0;
                    for (const sel of CANDIDATE_SELECTORS) {
                        const nodes = document.querySelectorAll(sel);
                        for (const n of nodes) {
                            const s = scoreNode(n);
                            if (s > bestScore) {
                                bestScore = s;
                                bestRoot = n;
                                bestSelector = sel;
                            }
                        }
                    }
                    if (!bestRoot) bestRoot = document.body;

                    // 본문 후보 내부에서도 한 번 더 세분화해 최적 서브루트 선택
                    const subCandidates = [bestRoot, ...Array.from(bestRoot.querySelectorAll(
                        "article, main, #articleBodyContents, .article_view, .article-content, .entry-content, .post-content, .view-content, .se-main-container, .post_view, .rd_body, .content, #content, .posting, .post, .post_body, .post-body, .article_body, .article_txt, .view_txt"
                    ))];
                    let refinedRoot = bestRoot;
                    let refinedScore = scoreNode(bestRoot);
                    for (const n of subCandidates) {
                        const s = scoreNode(n);
                        if (s > refinedScore) {
                            refinedRoot = n;
                            refinedScore = s;
                        }
                    }
                    bestRoot = refinedRoot;
                    bestSelector =
                        (bestRoot.tagName || "").toLowerCase()
                        + (bestRoot.id ? `#${bestRoot.id}` : "")
                        + (
                            typeof bestRoot.className === "string" && bestRoot.className.trim()
                                ? "." + bestRoot.className.trim().split(/\\s+/).slice(0, 2).join(".")
                                : ""
                        );

                    // 명백한 노이즈 블록 제거
                    const allDesc = Array.from(bestRoot.querySelectorAll("*"));
                    for (const el of allDesc) {
                        if (!isVisible(el)) {
                            el.remove();
                            continue;
                        }
                        const tag = (el.tagName || "").toUpperCase();
                        if (SKIP_TAGS.has(tag)) {
                            el.remove();
                            continue;
                        }
                        if (hasNegativeHint(el)) {
                            el.remove();
                        }
                    }

                    function keepLine(line) {
                        const t = normalizeText(line || "");
                        if (t.length < 12) return false;
                        if (hasNoiseHintInText(t) && t.length < 40) return false;
                        return true;
                    }

                    function dedupeJoin(lines) {
                        const out = [];
                        const seen = new Set();
                        for (const raw of lines) {
                            const line = normalizeText(raw || "");
                            if (!line) continue;
                            const key = line.toLowerCase();
                            if (seen.has(key)) continue;
                            seen.add(key);
                            out.push(line);
                        }
                        return out;
                    }

                    const blockTexts = [];
                    const blockNodes = bestRoot.querySelectorAll(
                        "h1, h2, h3, h4, p, li, blockquote, pre, figcaption, div"
                    );
                    for (const node of blockNodes) {
                        if (!isVisible(node)) continue;
                        if (hasNegativeHint(node)) continue;
                        if (
                            node.querySelector(
                                "h1, h2, h3, h4, p, li, blockquote, pre, figcaption, div"
                            )
                        ) {
                            // 컨테이너성 블록은 건너뜀(중복 방지)
                            continue;
                        }
                        const t = normalizeText(node.innerText || "");
                        if (!keepLine(t)) continue;
                        blockTexts.push(t);
                    }

                    let textLines = dedupeJoin(blockTexts);
                    if (textLines.length < 5) {
                        const fallbackLines = (bestRoot.innerText || "")
                            .split(/\\n+/)
                            .map((s) => normalizeText(s))
                            .filter((s) => keepLine(s));
                        textLines = dedupeJoin(fallbackLines);
                    }

                    const images = [];
                    if (includeImages) {
                        const imgNodes = bestRoot.querySelectorAll("img");
                        const seenImg = new Set();
                        for (const img of imgNodes) {
                            const imgUrl = getImgUrl(img);
                            if (!imgUrl) continue;

                            const low = imgUrl.toLowerCase();
                            if (
                                low.includes("sprite") ||
                                low.includes("icon") ||
                                low.includes("emoji") ||
                                low.includes("logo") ||
                                low.includes("blank") ||
                                low.includes("adimg")
                            ) {
                                continue;
                            }

                            const w = Number(img.naturalWidth || img.width || 0);
                            const h = Number(img.naturalHeight || img.height || 0);
                            if (w > 0 && h > 0 && (w < 120 || h < 120)) continue;

                            if (seenImg.has(imgUrl)) continue;
                            seenImg.add(imgUrl);

                            const alt = normalizeText(img.getAttribute("alt") || "");
                            images.push({ url: imgUrl, alt });
                        }
                    }

                    const bodyText = textLines.join("\\n\\n");

                    return {
                        title: document.title || "",
                        finalUrl: location.href || "",
                        rootSelector: bestSelector,
                        bodyText,
                        images: images.slice(0, 80)
                    };
                }""",
                include_images,
            )
            browser.close()

            title = str((extracted or {}).get("title", "")).strip()
            final_url = str((extracted or {}).get("finalUrl", target_url)).strip() or target_url
            root_selector = str((extracted or {}).get("rootSelector", "body")).strip()
            body_text = str((extracted or {}).get("bodyText", "")).strip()
            images = (extracted or {}).get("images", []) or []

            if not body_text:
                return "본문을 추출할 수 없습니다."

            output = [
                f"제목: {title}" if title else "제목: (없음)",
                f"URL: {final_url}",
                f"본문 루트: {root_selector}",
                "",
                body_text,
            ]

            if include_images and images:
                output.append("\n이미지 URL:")
                for i, image in enumerate(images, 1):
                    if not isinstance(image, dict):
                        continue
                    img_url = str(image.get("url", "")).strip()
                    if not img_url:
                        continue
                    alt = str(image.get("alt", "")).strip()
                    if alt:
                        output.append(f"- [{i}] {img_url} | alt={alt}")
                    else:
                        output.append(f"- [{i}] {img_url}")

            return "\n".join(output)[:15000]
    except Exception as e:
        return f"크롤링 에러: {e}"
