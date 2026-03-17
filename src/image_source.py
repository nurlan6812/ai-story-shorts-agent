"""이미지 소싱: Gemini 전용 (재시도 로직 포함)"""

import re
import time
from pathlib import Path
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY

# 재시도 설정
MAX_RETRIES = 10
RETRY_DELAY = 10  # 초
IMAGE_REQUEST_TIMEOUT_MS = 600_000  # 10분

# Gemini 클라이언트 (이미지 생성용)
_gemini_client = None

def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=IMAGE_REQUEST_TIMEOUT_MS),
        )
    return _gemini_client


def _extract_retry_seconds(err: str) -> int | None:
    m = re.search(r"Please retry in ([^.\n]+(?:\.\d+)?s)", err)
    if not m:
        return None

    text = m.group(1)
    h = re.search(r"(\d+)h", text)
    mnt = re.search(r"(\d+)m", text)
    sec = re.search(r"(\d+(?:\.\d+)?)s", text)
    total = 0.0
    if h:
        total += int(h.group(1)) * 3600
    if mnt:
        total += int(mnt.group(1)) * 60
    if sec:
        total += float(sec.group(1))
    if total <= 0:
        return None
    return int(total)


def _compute_retry_wait(attempt: int, err: str = "") -> int:
    wait = RETRY_DELAY * (2 ** max(0, attempt - 1))
    hinted = _extract_retry_seconds(err)
    if hinted:
        wait = max(wait, hinted)
    return min(wait, 1800)


def generate_gemini_image(
    query: str,
    save_path: Path,
    aspect_ratio: str = "9:16",
    image_size: str = "2K",
    reference_image: "Image.Image | None" = None,
    reference_images: "list[Image.Image] | None" = None,
) -> Path | None:
    """Gemini로 이미지 생성 (실패 시 재시도)"""
    client = _get_gemini_client()

    prompt = (
        f"Generate a high-quality vertical image: {query}. "
        "Vivid colors, clean composition, suitable for YouTube Shorts."
    )

    # 실제 Gemini에 전달되는 프롬프트 출력
    print("\n" + "=" * 70)
    print("[Gemini 이미지 생성] 실제 API 전달 프롬프트:")
    print("=" * 70)
    print(prompt)
    refs: list["Image.Image"] = []
    if reference_images:
        refs.extend(reference_images)
    elif reference_image is not None:
        refs.append(reference_image)

    if refs:
        print(f"+ 멀티모달: reference_image {len(refs)}장 포함")
    print("=" * 70 + "\n")

    if refs:
        contents = [prompt, *refs]
    else:
        contents = prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size=image_size,
                    ),
                ),
            )

            for part in response.parts:
                if part.inline_data:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    part.as_image().save(str(save_path))
                    return save_path

            if attempt < MAX_RETRIES:
                wait = _compute_retry_wait(attempt, "empty image response")
                print(
                    f"    ⚠️ Gemini 이미지 응답에 이미지가 없음 ({attempt}/{MAX_RETRIES})"
                )
                print(f"    → {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(
                    f"    ❌ Gemini 이미지 응답에 이미지가 없음 ({MAX_RETRIES}회 시도)"
                )

        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = _compute_retry_wait(attempt, str(e))
                print(f"    ⚠️ Gemini 이미지 생성 실패 ({attempt}/{MAX_RETRIES}): {e}")
                print(f"    → {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(f"    ❌ Gemini 이미지 생성 최종 실패 ({MAX_RETRIES}회 시도): {e}")

    return None


def generate_character_sheet(
    characters: list[dict],
    style: dict,
    save_path: Path,
) -> Path | None:
    """캐릭터 레퍼런스 시트 생성"""
    client = _get_gemini_client()
    image_cfg = style.get("image", {})
    prefix = image_cfg.get("prompt_prefix", "")
    suffix = image_cfg.get("prompt_suffix", "no text, no watermark")

    char_lines = []
    for i, char in enumerate(characters, 1):
        char_lines.append(
            f"{i}. {char.get('name', f'Character {i}')} "
            f"({char.get('role', '')}): {char.get('description', '')}"
        )

    prompt = (
        f"Character reference sheet. {prefix}. "
        f"Show these characters clearly, each full-body, distinct and recognizable:\n"
        f"{chr(10).join(char_lines)}\n"
        f"Each character clearly separated. Clean white background. {suffix}"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1"),
                ),
            )
            for part in response.parts:
                if part.inline_data:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    part.as_image().save(str(save_path))
                    return save_path
            if attempt < MAX_RETRIES:
                wait = _compute_retry_wait(attempt, "empty image response")
                print(f"    ⚠️ 캐릭터 시트 응답에 이미지가 없음 ({attempt}/{MAX_RETRIES})")
                print(f"    → {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(f"    ❌ 캐릭터 시트 응답에 이미지가 없음 ({MAX_RETRIES}회 시도)")
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = _compute_retry_wait(attempt, str(e))
                print(f"    ⚠️ 캐릭터 시트 생성 실패 ({attempt}/{MAX_RETRIES}): {e}")
                print(f"    → {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(f"    ❌ 캐릭터 시트 최종 실패 ({MAX_RETRIES}회 시도): {e}")

    return None


def get_aspect_ratio_for_style(style: dict | None) -> str:
    """스타일 레이아웃에 맞는 이미지 비율 결정"""
    if style:
        img_cfg = style.get("image", {})
        if "aspect_ratio" in img_cfg:
            return img_cfg["aspect_ratio"]
        layout_type = style.get("layout", {}).get("type", "overlay")
        if layout_type == "split":
            return "3:4"
        elif layout_type == "three_zone":
            return "1:1"
    return "9:16"


def source_image(
    query: str,
    save_path: Path,
    style: dict | None = None,
    reference_image: "Image.Image | None" = None,
    reference_images: "list[Image.Image] | None" = None,
) -> Path | None:
    """Gemini로 이미지 생성"""
    aspect_ratio = get_aspect_ratio_for_style(style)
    return generate_gemini_image(
        query, save_path, aspect_ratio=aspect_ratio,
        reference_image=reference_image,
        reference_images=reference_images,
    )
