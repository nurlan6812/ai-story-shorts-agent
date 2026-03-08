"""YouTube Analytics — Data API v3 + Analytics API v2 통합 수집"""

import re
from datetime import datetime, timedelta, timezone

from tools.youtube_auth import get_authenticated_service


def is_analytics_ready(published_at: str) -> bool:
    """영상 게시 후 48시간 경과 여부 확인"""
    if not published_at:
        return False
    try:
        pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - pub_time >= timedelta(hours=48)
    except (ValueError, TypeError):
        return False


def fetch_video_analytics(
    youtube_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """영상 성과 통합 수집: Data API v3 (기본) + Analytics API v2 (심층)

    1단계: Data API v3로 조회수/좋아요/댓글/영상길이 가져옴 (항상 성공)
    2단계: Analytics API v2로 CTR/시청률/노출수 가져옴 (실패 시 0으로 폴백)

    Returns:
        {views, likes, comments, shares, watch_time_minutes,
         ctr, avg_percentage_viewed, impressions,
         subscribers_gained, subscribers_lost, duration_seconds}
    """
    # ── 1단계: Data API v3 (기본 통계, 항상 동작) ──
    youtube = get_authenticated_service("youtube", "v3")

    response = youtube.videos().list(
        part="statistics,contentDetails",
        id=youtube_id,
    ).execute()

    items = response.get("items", [])
    if not items:
        raise ValueError(f"영상을 찾을 수 없습니다: {youtube_id}")

    stats = items[0].get("statistics", {})
    content = items[0].get("contentDetails", {})

    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    comments = int(stats.get("commentCount", 0))
    duration_seconds = _parse_duration(content.get("duration", "PT0S"))

    result = {
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": 0,
        "watch_time_minutes": 0.0,
        "ctr": 0.0,
        "avg_percentage_viewed": 0.0,
        "impressions": 0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
        "duration_seconds": duration_seconds,
        "viewed_rate": 0.0,
        "swiped_rate": 0.0,
    }

    # ── 2단계: Analytics API v2 (심층 지표, 실패 시 폴백) ──
    analytics_data = _fetch_analytics_api(youtube_id, start_date, end_date)
    result.update(analytics_data)

    # watch_time이 아직 0이면 Data API 기반 추정
    if result["watch_time_minutes"] == 0.0 and views > 0:
        avg_pct = result["avg_percentage_viewed"] or 50.0
        result["watch_time_minutes"] = round(
            views * duration_seconds / 60 * (avg_pct / 100), 2
        )

    return result


def _fetch_analytics_api(
    youtube_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """YouTube Analytics API v2로 심층 지표 수집

    가져오는 것: CTR, 시청률, 노출수, 공유, 구독자 변화, 시청시간
    실패 시 빈 dict 반환 (Data API 결과에 영향 없음)
    """
    if not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        analytics = get_authenticated_service("youtubeAnalytics", "v2")

        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=",".join([
                "views",
                "estimatedMinutesWatched",
                "averageViewDuration",
                "averageViewPercentage",
                "likes",
                "shares",
                "subscribersGained",
                "subscribersLost",
            ]),
            dimensions="video",
            filters=f"video=={youtube_id}",
        ).execute()

        rows = response.get("rows", [])
        if not rows:
            return {}

        # row: [video, views, estMinWatched, avgViewDur, avgViewPct, likes, shares, subsGained, subsLost]
        row = rows[0]

        result = {
            "watch_time_minutes": float(row[2]) if len(row) > 2 else 0.0,
            "avg_percentage_viewed": float(row[4]) if len(row) > 4 else 0.0,
            "shares": int(row[6]) if len(row) > 6 else 0,
            "subscribers_gained": int(row[7]) if len(row) > 7 else 0,
            "subscribers_lost": int(row[8]) if len(row) > 8 else 0,
        }

        # CTR + 노출수는 별도 쿼리 (다른 metric 그룹)
        ctr_data = _fetch_ctr_metrics(analytics, youtube_id, start_date, end_date)
        result.update(ctr_data)

        return result

    except Exception as e:
        print(f"  [Analytics API] 심층 지표 수집 실패 (Data API 폴백): {e}")
        return {}


def _fetch_ctr_metrics(
    analytics,
    youtube_id: str,
    start_date: str,
    end_date: str,
) -> dict:
    """CTR + 노출수 수집 (별도 쿼리 필요)"""
    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,videoThumbnailImpressions,videoThumbnailImpressionsClickRate",
            dimensions="video",
            filters=f"video=={youtube_id}",
        ).execute()

        rows = response.get("rows", [])
        if not rows:
            return {}

        row = rows[0]
        return {
            "impressions": int(row[2]) if len(row) > 2 else 0,
            "ctr": float(row[3]) if len(row) > 3 else 0.0,
        }

    except Exception as e:
        # CTR 메트릭은 일부 채널에서 사용 불가할 수 있음
        print(f"  [Analytics API] CTR 수집 실패: {e}")
        return {}


def _parse_duration(duration: str) -> int:
    """ISO 8601 Duration → 초 변환 (PT1M30S → 90)"""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds
