"""BGM 선택 유틸리티"""

from pathlib import Path
from config.settings import BGM_DIR


def get_default_bgm() -> Path | None:
    """기본 BGM 파일 반환"""
    if not BGM_DIR.exists():
        return None
    bgm_files = list(BGM_DIR.glob("*.mp3")) + list(BGM_DIR.glob("*.wav"))
    return bgm_files[0] if bgm_files else None


def get_bgm_for_mood(mood: str) -> Path | None:
    """분위기에 맞는 BGM 파일 반환 — BGM 디렉토리에서 직접 매칭"""
    bgm_path = BGM_DIR / f"{mood}.mp3"
    if bgm_path.exists():
        return bgm_path
    bgm_path = BGM_DIR / f"{mood}.wav"
    if bgm_path.exists():
        return bgm_path
    return get_default_bgm()
