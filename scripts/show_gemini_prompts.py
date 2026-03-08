"""실제 Gemini에 요청되는 이미지 프롬프트 전체를 출력"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.style_manager import load_style
from src.image_source import get_aspect_ratio_for_style


def build_image_query(base_query: str, style: dict) -> str:
    image_cfg = style.get("image", {})
    prefix = image_cfg.get("prompt_prefix", "")
    suffix = image_cfg.get("prompt_suffix", "")
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(base_query)
    if suffix:
        parts.append(suffix)
    return ", ".join(parts)


def get_final_gemini_prompt(combined_query: str) -> str:
    return (
        f"Generate a high-quality vertical image: {combined_query}. "
        "Vivid colors, clean composition, suitable for YouTube Shorts."
    )


def main():
    # 인자로 work_dir 지정 가능: python scripts/show_gemini_prompts.py output/20260303_185647
    work_dir = PROJECT_ROOT / "output" / "20260303_185647"
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        if not work_dir.is_absolute():
            work_dir = PROJECT_ROOT / work_dir
    script_path = work_dir / "script.json"
    if not script_path.exists():
        # 최신 output 디렉터리 찾기
        output_dir = PROJECT_ROOT / "output"
        dirs = sorted([d for d in output_dir.iterdir() if d.is_dir() and not d.name.startswith("_")], reverse=True)
        if dirs:
            for d in dirs:
                sp = d / "script.json"
                if sp.exists():
                    script_path = sp
                    work_dir = d
                    break
        if not script_path.exists():
            print("script.json을 찾을 수 없습니다. output/ 아래에 실행 결과가 있어야 합니다.")
            sys.exit(1)

    data = json.loads(script_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    style_name = data.get("style", "absurdist")  # mood: quirky → absurdist
    if "style" not in data and "mood" in data:
        mood_to_style = {"quirky": "absurdist", "funny": "casual", "emotional": "storytelling", "tension": "darkcomedy", "chill": "wholesome", "dramatic": "storytelling"}
        style_name = mood_to_style.get(data["mood"], "casual")
    characters = data.get("characters", [])

    style = load_style(style_name)
    aspect_ratio = get_aspect_ratio_for_style(style)

    print("=" * 70)
    print(f"작업 디렉터리: {work_dir}")
    print(f"스타일: {style_name} | aspect_ratio: {aspect_ratio} | 모델: gemini-3.1-flash-image-preview")
    print(f"캐릭터 시트 사용: {'예 (' + str(len(characters)) + '명)' if characters else '아니오'}")
    print("=" * 70)

    for i, scene in enumerate(scenes):
        base_query = scene.get("image_query", "")
        combined = build_image_query(base_query, style)
        final_prompt = get_final_gemini_prompt(combined)

        print(f"\n### 장면 {i + 1}")
        print(f"[Director image_query]\n  {base_query}")
        print(f"\n[스타일 적용 후 combined_query]\n  {combined}")
        print(f"\n[★ Gemini에 실제 전달되는 텍스트 프롬프트 ★]\n  {final_prompt}")
        if characters:
            print(f"\n[멀티모달] reference_image: character_sheet.png (캐릭터 {len(characters)}명)")
        print("-" * 70)

    print("\n")
    if characters:
        print("캐릭터 목록:")
        for c in characters:
            print(f"  - {c.get('name')} ({c.get('role')}): {c.get('description', '')[:60]}...")
    else:
        print("(캐릭터 시트 없음 → 프롬프트 텍스트만 전달)")


if __name__ == "__main__":
    main()
