"""수동 영상 생성 및 애널리틱스 수집 트리거"""

import subprocess
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from settings import MAIN_SCRIPT, VENV_PYTHON

router = APIRouter()


class GenerateRequest(BaseModel):
    topic: str = ""
    style: str | None = None


@router.post("/trigger")
async def trigger_generate(req: GenerateRequest):
    """수동 영상 생성 트리거 (백그라운드)"""
    cmd = [str(VENV_PYTHON), str(MAIN_SCRIPT)]
    if req.topic:
        cmd.append(req.topic)
    if req.style:
        cmd.extend(["--style", req.style])
    cmd.append("--upload")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(MAIN_SCRIPT.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"triggered": True, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics")
async def trigger_analytics():
    """수동 애널리틱스 수집 트리거"""
    cmd = [str(VENV_PYTHON), str(MAIN_SCRIPT), "--analyze"]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(MAIN_SCRIPT.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"triggered": True, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
