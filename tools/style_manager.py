"""스타일 프리셋 관리"""

import json
from pathlib import Path
from config.settings import STYLES_DIR


def load_style(name: str) -> dict:
    """스타일 프리셋 로드"""
    path = STYLES_DIR / f"{name}.json"
    if not path.exists():
        return load_style("educational")  # 기본값
    return json.loads(path.read_text())


def list_styles() -> list[str]:
    """사용 가능한 스타일 목록"""
    return [p.stem for p in STYLES_DIR.glob("*.json")]
