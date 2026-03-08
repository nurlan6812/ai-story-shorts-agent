"""로그 파일 읽기 엔드포인트"""

import re
from fastapi import APIRouter, Query

from settings import SCHEDULER_LOG_PATH

router = APIRouter()

LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+"
    r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s+"
    r"(.+)$"
)


def _parse_log_line(line: str) -> dict:
    """로그 줄을 구조화된 dict로 파싱"""
    match = LOG_PATTERN.match(line.strip())
    if match:
        return {
            "timestamp": match.group(1),
            "level": match.group(2),
            "message": match.group(3),
        }
    return {"timestamp": "", "level": "INFO", "message": line.strip()}


@router.get("/tail")
async def tail_logs(
    lines: int = Query(default=100, ge=1, le=1000),
    level: str = Query(default="INFO"),
):
    """scheduler.log 최근 N줄 반환 (레벨 필터링)"""
    if not SCHEDULER_LOG_PATH.exists():
        return {"logs": [], "total": 0}

    level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = level_order.get(level.upper(), 1)

    try:
        raw = SCHEDULER_LOG_PATH.read_text(encoding="utf-8", errors="replace")
        all_lines = raw.strip().split("\n") if raw.strip() else []
        # 최근 N줄 가져오기 (파싱 전에 넉넉하게)
        recent = all_lines[-(lines * 3) :] if len(all_lines) > lines * 3 else all_lines

        parsed = [_parse_log_line(line) for line in recent if line.strip()]
        filtered = [
            entry
            for entry in parsed
            if level_order.get(entry["level"], 1) >= min_level
        ]

        return {"logs": filtered[-lines:], "total": len(all_lines)}
    except Exception as e:
        return {"logs": [], "total": 0, "error": str(e)}
