"""효과음 매칭 (프리셋 기반)"""

from pathlib import Path
from config.settings import EFFECTS_DIR

# 효과음 타입 → 파일 매핑
EFFECT_MAP = {
    "whoosh": "whoosh.mp3",
    "impact": "impact.mp3",
    "dramatic": "dramatic.mp3",
    "pop": "pop.mp3",
    "ding": "ding.mp3",
    "suspense": "suspense.mp3",
}


def get_effect_path(effect_type: str | None) -> Path | None:
    """효과음 타입에 맞는 파일 경로 반환"""
    if effect_type is None:
        return None

    filename = EFFECT_MAP.get(effect_type)
    if filename is None:
        return None

    path = EFFECTS_DIR / filename
    if not path.exists():
        return None

    return path
