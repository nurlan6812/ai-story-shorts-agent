"""스케줄러 상태 조회 및 제어"""

import os
import signal
import subprocess
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from settings import SCHEDULER_SCRIPT, VENV_PYTHON

router = APIRouter()

KST = timezone(timedelta(hours=9))
SCHEDULE_HOURS = [6, 12, 19]  # KST


def _find_scheduler_pid() -> int | None:
    """실행 중인 scheduler.py 프로세스 PID 찾기"""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "scheduler.py"],
            text=True,
        ).strip()
        pids = [int(p) for p in out.split("\n") if p]
        # 자기 자신(FastAPI) 제외
        my_pid = os.getpid()
        pids = [p for p in pids if p != my_pid]
        return pids[0] if pids else None
    except (subprocess.CalledProcessError, ValueError):
        return None


def _next_schedule_time() -> str | None:
    """다음 스케줄 실행 시간 (KST) 반환"""
    now = datetime.now(KST)
    for hour in SCHEDULE_HOURS:
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if scheduled > now:
            return scheduled.isoformat()
    # 내일 첫 스케줄
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=SCHEDULE_HOURS[0], minute=0, second=0, microsecond=0
    ).isoformat()


@router.get("/status")
async def scheduler_status():
    """스케줄러 프로세스 상태 + 다음 실행 시간"""
    pid = _find_scheduler_pid()
    return {
        "running": pid is not None,
        "pid": pid,
        "next_run": _next_schedule_time(),
    }


@router.post("/start")
async def scheduler_start():
    """스케줄러 백그라운드 시작"""
    pid = _find_scheduler_pid()
    if pid:
        raise HTTPException(status_code=409, detail=f"스케줄러가 이미 실행 중입니다 (PID: {pid})")

    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(SCHEDULER_SCRIPT)],
        cwd=str(SCHEDULER_SCRIPT.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"started": True, "pid": proc.pid}


@router.post("/stop")
async def scheduler_stop():
    """스케줄러 프로세스 정지"""
    pid = _find_scheduler_pid()
    if not pid:
        raise HTTPException(status_code=404, detail="실행 중인 스케줄러가 없습니다")

    try:
        os.kill(pid, signal.SIGTERM)
        return {"stopped": True, "pid": pid}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail="프로세스를 찾을 수 없습니다")
