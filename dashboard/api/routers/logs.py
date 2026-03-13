"""로그 파일 읽기 엔드포인트."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Query

from settings import RECOVERY_SCHEDULER_LOG_PATH, SCHEDULER_LOG_PATH

router = APIRouter()

LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+"
    r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s+"
    r"(.+)$"
)

LOG_TARGETS = {
    "main": SCHEDULER_LOG_PATH,
    "recovery": RECOVERY_SCHEDULER_LOG_PATH,
}


def _parse_log_line(line: str, source: str, seq: int) -> dict:
    match = LOG_PATTERN.match(line.strip())
    if match:
        return {
            "timestamp": match.group(1),
            "level": match.group(2),
            "message": match.group(3),
            "source": source,
            "_seq": seq,
            "_sort_timestamp": match.group(1),
        }
    return {
        "timestamp": "",
        "level": "INFO",
        "message": line.strip(),
        "source": source,
        "_seq": seq,
        "_sort_timestamp": "",
    }


def _read_log_entries(log_path: Path, source: str, lines: int) -> tuple[list[dict], int]:
    if not log_path.exists():
        return [], 0

    raw = log_path.read_text(encoding="utf-8", errors="replace")
    all_lines = raw.strip().split("\n") if raw.strip() else []
    recent = all_lines[-(lines * 3) :] if len(all_lines) > lines * 3 else all_lines

    parsed = []
    last_timestamp = ""
    for index, line in enumerate(recent):
        if not line.strip():
            continue
        entry = _parse_log_line(line, source=source, seq=index)
        if entry["timestamp"]:
            last_timestamp = entry["timestamp"]
        else:
            entry["_sort_timestamp"] = last_timestamp
        parsed.append(entry)

    return parsed, len(all_lines)


@router.get("/tail")
async def tail_logs(
    lines: int = Query(default=100, ge=1, le=1000),
    level: str = Query(default="INFO"),
    target: str = Query(default="all", pattern="^(all|main|recovery)$"),
):
    """최근 N줄 로그 반환 (타깃/레벨 필터링)."""
    level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = level_order.get(level.upper(), 1)

    selected_targets = (
        LOG_TARGETS.items() if target == "all" else [(target, LOG_TARGETS[target])]
    )

    entries: list[dict] = []
    total = 0

    try:
        for source, log_path in selected_targets:
            parsed, line_count = _read_log_entries(log_path, source, lines)
            total += line_count
            entries.extend(parsed)

        filtered = [
            entry
            for entry in entries
            if level_order.get(entry["level"], 1) >= min_level
        ]

        filtered.sort(key=lambda item: (item["_sort_timestamp"], item["_seq"]))
        response_logs = [
            {
                key: value
                for key, value in entry.items()
                if key not in {"_seq", "_sort_timestamp"}
            }
            for entry in filtered[-lines:]
        ]
        return {"logs": response_logs, "total": total, "target": target}
    except Exception as exc:
        return {"logs": [], "total": 0, "target": target, "error": str(exc)}
