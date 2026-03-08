"""헬스체크 엔드포인트"""

import shutil
from fastapi import APIRouter

from settings import PROJECT_ROOT

router = APIRouter()


@router.get("/status")
async def health_status():
    """YouTube 토큰 + Supabase 연결 + 디스크 + 쿼터 통합 헬스체크"""
    result = {
        "youtube_token": False,
        "supabase": False,
        "disk_free_gb": 0.0,
        "quota": {"remaining": 0, "used": 0, "limit": 3, "can_upload": False},
    }

    # YouTube 토큰 유효성
    try:
        from tools.youtube_auth import check_token_valid

        result["youtube_token"] = check_token_valid()
    except Exception:
        pass

    # Supabase 연결
    try:
        from tools.supabase_client import get_client

        client = get_client()
        result["supabase"] = client is not None
    except Exception:
        pass

    # 디스크 잔여 용량
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        result["disk_free_gb"] = round(usage.free / (1024**3), 1)
    except Exception:
        pass

    # 일일 쿼터
    try:
        from tools.youtube_uploader import check_daily_quota_remaining

        result["quota"] = check_daily_quota_remaining()
    except Exception:
        pass

    return result
