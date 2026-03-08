"""Supabase CRUD 클라이언트

Supabase 미설정 시 기존 파이프라인에 영향 없이 None 반환.
"""

import uuid
from datetime import datetime, timezone, timedelta

from config.settings import SUPABASE_URL, SUPABASE_KEY

_client = None
_initialized = False


def get_client():
    """Supabase 클라이언트 lazy init

    SUPABASE_URL, SUPABASE_KEY가 없으면 None 반환 (기존 파이프라인 영향 없음).
    """
    global _client, _initialized
    if _initialized:
        return _client

    _initialized = True
    if not SUPABASE_URL or not SUPABASE_KEY:
        _client = None
        return None

    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"  [Supabase] 연결 실패: {e}")
        _client = None

    return _client


# ============================================================
# Videos CRUD
# ============================================================

def insert_video(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    style: str = "",
    bgm_mood: str = "",
    summary: str = "",
    upload_status: str = "pending",
    production_plan: dict | None = None,
    research_brief: dict | None = None,
) -> dict | None:
    """videos 테이블에 영상 레코드 삽입"""
    client = get_client()
    if client is None:
        return None

    data = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "tags": tags or [],
        "style": style,
        "bgm_mood": bgm_mood,
        "summary": summary,
        "upload_status": upload_status,
        "production_plan": production_plan,
        "research_brief": research_brief,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = client.table("videos").insert(data).execute()
    return result.data[0] if result.data else data


def update_video_status(
    video_id: str,
    upload_status: str | None = None,
    youtube_id: str | None = None,
    published_at: str | None = None,
) -> dict | None:
    """영상 업로드 상태 업데이트"""
    client = get_client()
    if client is None:
        return None

    updates = {}
    if upload_status is not None:
        updates["upload_status"] = upload_status
    if youtube_id is not None:
        updates["youtube_id"] = youtube_id
    if published_at is not None:
        updates["published_at"] = published_at

    if not updates:
        return None

    result = client.table("videos").update(updates).eq("id", video_id).execute()
    return result.data[0] if result.data else None


def list_videos(limit: int = 50, upload_status: str | None = None) -> list[dict]:
    """영상 목록 조회"""
    client = get_client()
    if client is None:
        return []

    query = client.table("videos").select("*").order("created_at", desc=True).limit(limit)
    if upload_status:
        query = query.eq("upload_status", upload_status)

    result = query.execute()
    return result.data or []


def get_recent_topics(days: int = 7, limit: int = 20) -> list[str]:
    """최근 N일간 업로드된 영상의 주제(제목+요약) 목록 조회 (중복 방지용)"""
    client = get_client()
    if client is None:
        return []

    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    result = (
        client.table("videos")
        .select("title, summary, description")
        .eq("upload_status", "uploaded")
        .gte("published_at", threshold)
        .order("published_at", desc=True)
        .limit(limit)
        .execute()
    )

    topics = []
    for r in result.data or []:
        title = r.get("title", "")
        if not title:
            continue
        summary = r.get("summary", "")
        if summary:
            topics.append(f"{title} — {summary}")
        else:
            desc = r.get("description", "")
            # 설명에서 해시태그 제거 후 앞 80자만 요약으로 사용
            if desc:
                desc_clean = desc.split("#")[0].strip()
                if len(desc_clean) > 80:
                    desc_clean = desc_clean[:80] + "…"
                topics.append(f"{title} — {desc_clean}")
            else:
                topics.append(title)
    return topics


def get_last_upload_time() -> str | None:
    """업로드 완료된 최신 영상의 published_at 반환 (없으면 None)"""
    client = get_client()
    if client is None:
        return None

    result = (
        client.table("videos")
        .select("published_at")
        .eq("upload_status", "uploaded")
        .not_.is_("published_at", "null")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0].get("published_at")
    return None


# ============================================================
# Runs CRUD
# ============================================================

def insert_run(
    run_type: str = "generate",
    video_id: str | None = None,
) -> dict | None:
    """runs 테이블에 실행 기록 삽입"""
    client = get_client()
    if client is None:
        return None

    data = {
        "id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "run_type": run_type,
        "video_id": video_id,
    }

    result = client.table("runs").insert(data).execute()
    return result.data[0] if result.data else data


def update_run(
    run_id: str,
    status: str | None = None,
    error_message: str | None = None,
    video_id: str | None = None,
) -> dict | None:
    """실행 기록 업데이트"""
    client = get_client()
    if client is None:
        return None

    updates = {}
    if status is not None:
        updates["status"] = status
        if status in ("completed", "failed"):
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    if error_message is not None:
        updates["error_message"] = error_message
    if video_id is not None:
        updates["video_id"] = video_id

    if not updates:
        return None

    result = client.table("runs").update(updates).eq("id", run_id).execute()
    return result.data[0] if result.data else None


def get_runs_today(run_type: str | None = None) -> list[dict]:
    """오늘 실행된 run 목록 조회"""
    client = get_client()
    if client is None:
        return []

    # UTC 기준 오늘 시작 시각 (KST-9)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_kst.astimezone(timezone.utc).isoformat()

    query = (
        client.table("runs")
        .select("*")
        .gte("started_at", today_start_utc)
    )
    if run_type:
        query = query.eq("run_type", run_type)

    result = query.execute()
    return result.data or []


# ============================================================
# Analytics CRUD
# ============================================================

def insert_analytics(
    video_id: str,
    views: int = 0,
    watch_time_minutes: float = 0.0,
    ctr: float = 0.0,
    avg_percentage_viewed: float = 0.0,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    impressions: int = 0,
    subscribers_gained: int = 0,
    subscribers_lost: int = 0,
    duration_seconds: int = 0,
    viewed_rate: float = 0.0,
    swiped_rate: float = 0.0,
) -> dict | None:
    """analytics 테이블에 성과 데이터 삽입"""
    client = get_client()
    if client is None:
        return None

    data = {
        "id": str(uuid.uuid4()),
        "video_id": video_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "views": views,
        "watch_time_minutes": watch_time_minutes,
        "ctr": ctr,
        "avg_percentage_viewed": avg_percentage_viewed,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "impressions": impressions,
        "subscribers_gained": subscribers_gained,
        "subscribers_lost": subscribers_lost,
        "duration_seconds": duration_seconds,
        "viewed_rate": viewed_rate,
        "swiped_rate": swiped_rate,
    }

    result = client.table("analytics").insert(data).execute()
    return result.data[0] if result.data else data


def list_videos_pending_analytics() -> list[dict]:
    """48시간 이상 경과했지만 아직 analytics가 없는 영상 목록"""
    client = get_client()
    if client is None:
        return []

    threshold = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

    # 업로드 완료된 영상 중 48시간 이상 경과한 것
    videos = (
        client.table("videos")
        .select("*")
        .eq("upload_status", "uploaded")
        .not_.is_("youtube_id", "null")
        .lte("published_at", threshold)
        .execute()
    )

    if not videos.data:
        return []

    # analytics에 이미 기록된 video_id 목록
    video_ids = [v["id"] for v in videos.data]
    existing = (
        client.table("analytics")
        .select("video_id")
        .in_("video_id", video_ids)
        .execute()
    )
    existing_ids = {r["video_id"] for r in (existing.data or [])}

    return [v for v in videos.data if v["id"] not in existing_ids]


# ============================================================
# Patterns CRUD
# ============================================================

def upsert_pattern(
    pattern_type: str,
    pattern_key: str,
    pattern_data: dict,
    win_rate: float = 0.0,
    sample_size: int = 0,
    is_active: bool = True,
) -> dict | None:
    """patterns 테이블에 패턴 upsert"""
    client = get_client()
    if client is None:
        return None

    data = {
        "pattern_type": pattern_type,
        "pattern_key": pattern_key,
        "pattern_data": pattern_data,
        "win_rate": win_rate,
        "sample_size": sample_size,
        "is_active": is_active,
    }

    # 기존 패턴 확인
    existing = (
        client.table("patterns")
        .select("id")
        .eq("pattern_type", pattern_type)
        .eq("pattern_key", pattern_key)
        .execute()
    )

    if existing.data:
        result = (
            client.table("patterns")
            .update(data)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        data["id"] = str(uuid.uuid4())
        result = client.table("patterns").insert(data).execute()

    return result.data[0] if result.data else data


def get_active_patterns() -> list[dict]:
    """활성화된 패턴 목록 조회"""
    client = get_client()
    if client is None:
        return []

    result = (
        client.table("patterns")
        .select("*")
        .eq("is_active", True)
        .order("win_rate", desc=True)
        .execute()
    )
    return result.data or []
