"""기존 script.json으로 이미지 생성만 실행 (Director 안 함, Gemini 프롬프트 출력 포함)"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.style_manager import load_style
from src.image_source import source_image, get_aspect_ratio_for_style
from config.settings import IMAGE_WORKERS
from concurrent.futures import ThreadPoolExecutor, as_completed


def _build_image_query(base_query: str, style: dict) -> str:
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


def main():
    work_dir = PROJECT_ROOT / "output" / "20260303_185647"
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        if not work_dir.is_absolute():
            work_dir = PROJECT_ROOT / work_dir

    script_path = work_dir / "script.json"
    if not script_path.exists():
        print(f"script.json 없음: {script_path}")
        sys.exit(1)

    data = json.loads(script_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    style_name = data.get("style", "absurdist")
    if "style" not in data and "mood" in data:
        mood_to_style = {"quirky": "absurdist", "funny": "casual", "emotional": "storytelling", "tension": "darkcomedy", "chill": "wholesome", "dramatic": "storytelling"}
        style_name = mood_to_style.get(data["mood"], "casual")

    style = load_style(style_name)
    raw_images_dir = work_dir / "raw_images"
    raw_images_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"[이미지 생성만 실행] work_dir={work_dir}, 스타일={style_name}, aspect_ratio={get_aspect_ratio_for_style(style)}")
    print("=" * 70)

    def _fetch(i: int, scene: dict) -> tuple[int, Path | None]:
        query = _build_image_query(scene["image_query"], style)
        img_path = source_image(query, raw_images_dir / f"scene_{i:02d}.jpg", style=style)
        return i, img_path

    with ThreadPoolExecutor(max_workers=min(IMAGE_WORKERS, len(scenes))) as pool:
        futures = {pool.submit(_fetch, i, s): i for i, s in enumerate(scenes)}
        for fut in as_completed(futures):
            i, img_path = fut.result()
            status = "✅" if img_path else "❌"
            print(f"  장면 {i+1}: {status}")

    print("\n완료.")


if __name__ == "__main__":
    main()
