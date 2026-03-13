"""스케줄러 상태 조회 및 제어."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from settings import (
    CAFFEINATE_BIN,
    PROJECT_ROOT,
    RECOVERY_SCHEDULER_LOG_PATH,
    RECOVERY_SCHEDULER_SCRIPT,
    SCHEDULER_LOG_PATH,
    SCHEDULER_SCRIPT,
    VENV_PYTHON,
)

router = APIRouter()

KST = timezone(timedelta(hours=9))
MAIN_SLOTS = [(6, 30), (12, 30), (18, 30)]
RECOVERY_SLOTS = [
    (7, 30),
    (8, 30),
    (9, 30),
    (13, 30),
    (14, 30),
    (15, 30),
    (19, 30),
    (20, 30),
    (21, 30),
]

TARGETS = {
    "main": {
        "label": "메인 스케줄러",
        "script": SCHEDULER_SCRIPT,
        "log_path": SCHEDULER_LOG_PATH,
        "schedule_slots": MAIN_SLOTS,
    },
    "recovery": {
        "label": "복구 스케줄러",
        "script": RECOVERY_SCHEDULER_SCRIPT,
        "log_path": RECOVERY_SCHEDULER_LOG_PATH,
        "schedule_slots": RECOVERY_SLOTS,
    },
}


def _target_config(target: str) -> dict:
    config = TARGETS.get(target)
    if config is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 target: {target}")
    return config


def _find_processes_for_target(target: str) -> list[dict]:
    config = _target_config(target)
    log_path = config["log_path"]

    try:
        out = subprocess.check_output(
            ["lsof", "-Fpcfan", "--", str(log_path)],
            text=True,
        )
    except subprocess.CalledProcessError:
        return []

    processes = []
    current_pid = None
    current_command = ""
    current_access = ""

    def flush_current():
        nonlocal current_pid, current_command, current_access
        if current_pid is None:
            return
        if "w" not in current_access:
            return
        processes.append({"pid": current_pid, "command": current_command})

    for raw_line in out.splitlines():
        if not raw_line:
            continue
        field = raw_line[0]
        value = raw_line[1:]

        if field == "p":
            flush_current()
            current_pid = int(value) if value.isdigit() else None
            current_command = ""
            current_access = ""
        elif field == "c":
            current_command = value
        elif field == "a":
            current_access = value

    flush_current()

    unique = {}
    for proc in processes:
        unique[proc["pid"]] = proc
    return list(unique.values())


def _primary_pid(processes: list[dict]) -> int | None:
    if not processes:
        return None
    for proc in processes:
        if "python" in proc["command"].lower():
            return proc["pid"]
    return processes[0]["pid"]


def _next_run_for_target(target: str) -> str | None:
    now = datetime.now(KST)
    slots = _target_config(target)["schedule_slots"]

    for hour, minute in slots:
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled > now:
            return scheduled.isoformat()

    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0
    ).isoformat()


def _last_log_timestamp(log_path: Path) -> str | None:
    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        if len(line) >= 19 and line[4] == "-" and line[7] == "-":
            return line[:19]
    return None


def _last_log_line(log_path: Path) -> str | None:
    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _build_status(target: str) -> dict:
    config = _target_config(target)
    processes = _find_processes_for_target(target)
    pids = sorted(proc["pid"] for proc in processes)

    return {
        "target": target,
        "label": config["label"],
        "running": bool(processes),
        "pid": _primary_pid(processes),
        "pids": pids,
        "next_run": _next_run_for_target(target),
        "last_log_at": _last_log_timestamp(config["log_path"]),
        "log_path": str(config["log_path"]),
    }


def _start_command(target: str) -> list[str]:
    config = _target_config(target)
    if CAFFEINATE_BIN:
        return [
            CAFFEINATE_BIN,
            "-s",
            "-i",
            str(VENV_PYTHON),
            str(config["script"]),
        ]
    return [str(VENV_PYTHON), str(config["script"])]


def _start_target(target: str) -> dict:
    config = _target_config(target)
    processes = _find_processes_for_target(target)
    if processes:
        raise HTTPException(
            status_code=409,
            detail=f"{config['label']}가 이미 실행 중입니다 (PID: {_primary_pid(processes)})",
        )

    config["log_path"].parent.mkdir(parents=True, exist_ok=True)
    with config["log_path"].open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            _start_command(target),
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    time.sleep(0.6)
    if proc.poll() is not None:
        error_line = _last_log_line(config["log_path"])
        detail = f"{config['label']}가 시작 직후 종료되었습니다."
        if error_line:
            detail = f"{detail} {error_line}"
        raise HTTPException(status_code=500, detail=detail)

    return {"started": True, "pid": proc.pid, "target": target}


def _stop_target(target: str) -> dict:
    config = _target_config(target)
    processes = _find_processes_for_target(target)
    if not processes:
        raise HTTPException(status_code=404, detail=f"실행 중인 {config['label']}가 없습니다")

    stopped = []
    for proc in sorted(processes, key=lambda item: item["pid"], reverse=True):
        try:
            os.kill(proc["pid"], signal.SIGTERM)
            stopped.append(proc["pid"])
        except ProcessLookupError:
            continue

    return {"stopped": True, "target": target, "pids": stopped}


def _parse_recovery_activity(message: str) -> dict | None:
    if "[slot_check]" not in message:
        return None

    try:
        slot, rest = message.split("][slot_check] ", 1)
        slot = slot.lstrip("[")
    except ValueError:
        return None

    status = "info"
    title = None
    if rest.startswith("결과 확인됨:"):
        status = "verified"
        title = rest.split(":", 1)[1].strip()
    elif rest.startswith("결과 누락 감지"):
        status = "retry_triggered"
    elif rest.startswith("완료:"):
        status = "completed"
        title = rest.split(":", 1)[1].strip()
    elif "생성+업로드 실패" in rest:
        status = "failed"
    elif rest.startswith("결과 조회 불가"):
        status = "skipped"

    return {
        "slot": slot,
        "status": status,
        "message": rest,
        "title": title,
    }


@router.get("/status")
async def scheduler_overview():
    return {
        "main": _build_status("main"),
        "recovery": _build_status("recovery"),
    }


@router.get("/status/{target}")
async def scheduler_status(target: str):
    return _build_status(target)


@router.post("/start/{target}")
async def scheduler_start(target: str):
    return _start_target(target)


@router.post("/stop/{target}")
async def scheduler_stop(target: str):
    return _stop_target(target)


@router.get("/recovery-activity")
async def recovery_activity(limit: int = Query(default=20, ge=1, le=100)):
    if not RECOVERY_SCHEDULER_LOG_PATH.exists():
        return {"activities": [], "total": 0}

    try:
        lines = RECOVERY_SCHEDULER_LOG_PATH.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    activities = []
    for line in lines:
        if len(line) < 20 or line[4] != "-" or line[7] != "-":
            continue
        timestamp = line[:19]
        if "] " not in line:
            continue
        message = line.split("] ", 1)[1]
        parsed = _parse_recovery_activity(message)
        if not parsed:
            continue
        activities.append({"timestamp": timestamp, **parsed})

    return {"activities": activities[-limit:][::-1], "total": len(activities)}
