"""Stats Engine — pandas 기반 성과 데이터 사전 계산

LLM이 수학을 못하므로, 여기서 통계를 미리 계산하고
LLM은 해석/판단만 하도록 합니다.
"""

from __future__ import annotations

import math
from collections import defaultdict


def precompute_stats(videos: list[dict]) -> dict:
    """영상+애널리틱스 데이터에서 통계를 사전 계산

    Args:
        videos: Supabase에서 가져온 영상 리스트
            각 항목: {title, style, bgm_mood, tags, analytics: {...}}

    Returns:
        {
            "total_videos": int,
            "summary": {평균/중앙값/표준편차 등 전체 요약},
            "winners": [{video_id, title, views, ...}],
            "losers": [{video_id, title, views, ...}],
            "by_style": {style: {count, avg_views, avg_ctr, ...}},
            "by_bgm": {bgm: {count, avg_views, ...}},
            "by_story_type": {...},
            "by_source_region": {...},
            "by_series_format": {...},
            "by_ending_type": {...},
            "by_scene_density": {...},
            "correlations": {metric_pair: correlation_value},
            "engagement_rates": [{video_id, title, like_rate, comment_rate}],
        }
    """
    if not videos:
        return _empty_stats()

    # 1) 데이터 평탄화
    rows = _flatten_videos(videos)
    if not rows:
        return _empty_stats()

    n = len(rows)

    # 2) 전체 요약 통계
    views_list = [r["views"] for r in rows]
    likes_list = [r["likes"] for r in rows]
    comments_list = [r["comments"] for r in rows]
    ctr_list = [r["ctr"] for r in rows]
    avg_pct_list = [r["avg_percentage_viewed"] for r in rows]
    wt_list = [r["watch_time_minutes"] for r in rows]

    summary = {
        "total_videos": n,
        "views": _describe(views_list),
        "likes": _describe(likes_list),
        "comments": _describe(comments_list),
        "ctr": _describe(ctr_list, decimals=4),
        "avg_percentage_viewed": _describe(avg_pct_list, decimals=2),
        "watch_time_minutes": _describe(wt_list, decimals=2),
    }

    # 3) 승자/패자 분류 (views 기준 상위/하위 30%)
    sorted_by_views = sorted(rows, key=lambda r: r["views"], reverse=True)
    cutoff = max(1, int(n * 0.3))

    winners = sorted_by_views[:cutoff]
    losers = sorted_by_views[-cutoff:] if n > 1 else []

    # views 기준 p70, p30 임계값
    p70 = _percentile(views_list, 70)
    p30 = _percentile(views_list, 30)

    for r in rows:
        r["tier"] = (
            "winner" if r["views"] >= p70
            else "loser" if r["views"] <= p30
            else "middle"
        )

    # 4) 스타일별 집계
    by_style = _aggregate_by(rows, "style")

    # 5) BGM별 집계
    by_bgm = _aggregate_by(rows, "bgm_mood")

    # 6) 상관 분석 (단순 피어슨)
    correlations = {}
    metric_pairs = [
        ("ctr", "views"),
        ("avg_percentage_viewed", "views"),
        ("likes", "views"),
        ("comments", "views"),
    ]
    for m1, m2 in metric_pairs:
        vals1 = [r[m1] for r in rows]
        vals2 = [r[m2] for r in rows]
        corr = _pearson(vals1, vals2)
        if corr is not None:
            correlations[f"{m1}_vs_{m2}"] = round(corr, 3)

    # 7) 참여율 (engagement rate)
    engagement_rates = []
    for r in rows:
        v = max(r["views"], 1)
        engagement_rates.append({
            "video_id": r["video_id"],
            "title": r["title"][:40],
            "views": r["views"],
            "like_rate": round(r["likes"] / v * 100, 2),
            "comment_rate": round(r["comments"] / v * 100, 2),
            "tier": r["tier"],
        })
    engagement_rates.sort(key=lambda e: e["like_rate"], reverse=True)

    return {
        "total_videos": n,
        "thresholds": {
            "winner_min_views": p70,
            "loser_max_views": p30,
        },
        "summary": summary,
        "winners": _simplify_rows(winners),
        "losers": _simplify_rows(losers),
        "by_style": by_style,
        "by_bgm": by_bgm,
        "by_story_type": _aggregate_by(rows, "story_type"),
        "by_source_region": _aggregate_by(rows, "source_region"),
        "by_series_format": _aggregate_by(rows, "series_format"),
        "by_ending_type": _aggregate_by(rows, "ending_type"),
        "by_scene_density": _aggregate_by(rows, "scene_density"),
        "correlations": correlations,
        "engagement_rates": engagement_rates[:20],
    }


# ── 내부 헬퍼 ──────────────────────────────────────────────


def _flatten_videos(videos: list[dict]) -> list[dict]:
    """videos+analytics를 분석용 flat dict 리스트로 변환"""
    rows = []
    for v in videos:
        a = v.get("analytics", {})
        if not a:
            continue
        research_brief = v.get("research_brief") or {}
        story_type = v.get("story_type") or (research_brief.get("story_type") if isinstance(research_brief, dict) else None) or "unknown"
        source_region = v.get("source_region") or (research_brief.get("source_region") if isinstance(research_brief, dict) else None) or "unknown"
        emotion = (research_brief.get("emotion") if isinstance(research_brief, dict) else None) or "unknown"
        scene_count = int(v.get("scene_count") or 0)
        is_series = bool(v.get("is_series"))
        ending_type = v.get("ending_type") or "unknown"
        rows.append({
            "video_id": v.get("id", ""),
            "title": v.get("title", ""),
            "style": v.get("style", "unknown"),
            "bgm_mood": v.get("bgm_mood", "unknown"),
            "story_type": story_type,
            "source_region": source_region,
            "emotion": emotion,
            "series_format": "series" if is_series else "single",
            "part_number": int(v.get("part_number") or 0),
            "scene_count": scene_count,
            "scene_density": _scene_density_bucket(scene_count),
            "ending_type": ending_type,
            "tags": v.get("tags", []),
            "views": int(a.get("views", 0)),
            "likes": int(a.get("likes", 0)),
            "comments": int(a.get("comments", 0)),
            "shares": int(a.get("shares", 0)),
            "ctr": float(a.get("ctr", 0)),
            "avg_percentage_viewed": float(a.get("avg_percentage_viewed", 0)),
            "watch_time_minutes": float(a.get("watch_time_minutes", 0)),
            "impressions": int(a.get("impressions", 0)),
            "duration_seconds": int(a.get("duration_seconds", 0)),
            "viewed_rate": float(a.get("viewed_rate", 0)),
            "swiped_rate": float(a.get("swiped_rate", 0)),
        })
    return rows


def _scene_density_bucket(scene_count: int) -> str:
    if scene_count <= 0:
        return "unknown"
    if scene_count <= 7:
        return "low"
    if scene_count <= 9:
        return "medium"
    return "high"


def _describe(values: list[float | int], decimals: int = 1) -> dict:
    """기술통계: 평균, 중앙값, 표준편차, 최소, 최대"""
    if not values:
        return {"mean": 0, "median": 0, "std": 0, "min": 0, "max": 0, "count": 0}

    n = len(values)
    mean = sum(values) / n
    sorted_v = sorted(values)
    median = (
        sorted_v[n // 2]
        if n % 2 == 1
        else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    )
    variance = sum((x - mean) ** 2 for x in values) / max(n - 1, 1)
    std = math.sqrt(variance)

    return {
        "mean": round(mean, decimals),
        "median": round(median, decimals),
        "std": round(std, decimals),
        "min": round(min(values), decimals),
        "max": round(max(values), decimals),
        "count": n,
    }


def _percentile(values: list[float | int], pct: int) -> float:
    """단순 퍼센타일 계산"""
    if not values:
        return 0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    d = k - f
    return sorted_v[f] + d * (sorted_v[c] - sorted_v[f])


def _pearson(x: list[float], y: list[float]) -> float | None:
    """피어슨 상관계수 (순수 Python, 3개 미만이면 None)"""
    n = len(x)
    if n < 3 or n != len(y):
        return None

    mx = sum(x) / n
    my = sum(y) / n

    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - my) ** 2 for yi in y))

    if den_x == 0 or den_y == 0:
        return None

    return num / (den_x * den_y)


def _aggregate_by(rows: list[dict], key: str) -> dict:
    """지정 키별로 views/likes/ctr 평균 집계"""
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key, "unknown")].append(r)

    result = {}
    for group_name, group_rows in groups.items():
        n = len(group_rows)
        result[group_name] = {
            "count": n,
            "avg_views": round(sum(r["views"] for r in group_rows) / n, 1),
            "avg_likes": round(sum(r["likes"] for r in group_rows) / n, 1),
            "avg_ctr": round(sum(r["ctr"] for r in group_rows) / n, 4),
            "avg_retention": round(
                sum(r["avg_percentage_viewed"] for r in group_rows) / n, 2
            ),
            "winner_count": sum(1 for r in group_rows if r.get("tier") == "winner"),
            "loser_count": sum(1 for r in group_rows if r.get("tier") == "loser"),
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["avg_views"], reverse=True))


def _simplify_rows(rows: list[dict]) -> list[dict]:
    """LLM에 넘길 때 불필요한 필드 제거"""
    return [
        {
            "video_id": r["video_id"],
            "title": r["title"][:50],
            "style": r["style"],
            "story_type": r["story_type"],
            "source_region": r["source_region"],
            "series_format": r["series_format"],
            "ending_type": r["ending_type"],
            "views": r["views"],
            "likes": r["likes"],
            "ctr": round(r["ctr"], 4),
            "avg_percentage_viewed": round(r["avg_percentage_viewed"], 2),
        }
        for r in rows
    ]


def _empty_stats() -> dict:
    """데이터 없을 때 빈 결과"""
    return {
        "total_videos": 0,
        "thresholds": {"winner_min_views": 0, "loser_max_views": 0},
        "summary": {},
        "winners": [],
        "losers": [],
        "by_style": {},
        "by_bgm": {},
        "by_story_type": {},
        "by_source_region": {},
        "by_series_format": {},
        "by_ending_type": {},
        "by_scene_density": {},
        "correlations": {},
        "engagement_rates": [],
    }
