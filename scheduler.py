"""유머/썰 YouTube Shorts 메인 스케줄러 (APScheduler 기반)

사용법:
    python scheduler.py           # 데몬 시작 (메인 생성/분석/헬스체크)
    python scheduler.py --once    # 1회 실행 후 종료

스케줄:
    - 06:30, 12:30, 18:30 KST: 영상 생성 + 업로드
    - 6시간마다: 48시간+ 영상 애널리틱스 수집
    - 00:00 KST: 전체 성과 분석 + 패턴 업데이트
    - 1시간마다: 헬스 체크
"""

import argparse
import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from scheduler_jobs import KST, job_generate_and_upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")


def job_collect_analytics():
    """48시간+ 영상 애널리틱스 수집"""
    log.info("=== 애널리틱스 수집 시작 ===")

    try:
        from main import _handle_analyze
        _handle_analyze()
        log.info("애널리틱스 수집 완료")
    except Exception as e:
        log.error(f"애널리틱스 수집 실패: {e}", exc_info=True)


def job_analyze_patterns():
    """전체 영상 성과 분석 → 패턴 업데이트"""
    log.info("=== 성과 분석 + 패턴 업데이트 시작 ===")

    try:
        from tools.supabase_client import (
            list_videos,
            get_client,
            upsert_pattern,
            insert_run,
            update_run,
        )
        from agents.analyzer import analyze_performance

        run_record = insert_run(run_type="analyze_patterns", trigger_source="schedule")
        run_id = run_record["id"] if run_record else None

        client = get_client()
        if client is None:
            log.warning("Supabase 미설정. 분석 건너뜁니다.")
            return

        # 업로드된 영상 + 애널리틱스 조인
        videos = list_videos(limit=100, publish_status="uploaded")
        if not videos:
            log.info("분석 대상 영상 없음")
            if run_id:
                update_run(run_id, status="completed")
            return

        # 각 영상에 analytics 데이터 붙이기
        videos_with_analytics = []
        for v in videos:
            analytics_result = (
                client.table("analytics")
                .select("*")
                .eq("video_id", v["id"])
                .order("fetched_at", desc=True)
                .limit(1)
                .execute()
            )
            analytics = analytics_result.data[0] if analytics_result.data else {}
            v["analytics"] = analytics
            if analytics:
                videos_with_analytics.append(v)

        if not videos_with_analytics:
            log.info("애널리틱스가 있는 영상 없음")
            if run_id:
                update_run(run_id, status="completed")
            return

        log.info(f"{len(videos_with_analytics)}개 영상 분석 중...")
        result = analyze_performance(videos_with_analytics)

        # 패턴 저장
        patterns_saved = 0

        for hook in result.get("patterns", {}).get("hooks", []):
            upsert_pattern(
                pattern_type="hook",
                pattern_key=hook.get("pattern", ""),
                pattern_data=hook,
                win_rate=hook.get("win_rate", 0),
                sample_size=hook.get("sample_size", 0),
            )
            patterns_saved += 1

        for style in result.get("patterns", {}).get("styles", []):
            upsert_pattern(
                pattern_type="style",
                pattern_key=style.get("style", ""),
                pattern_data=style,
                win_rate=style.get("avg_views", 0) / max(1, max(s.get("avg_views", 1) for s in result.get("patterns", {}).get("styles", []))),
                sample_size=1,
            )
            patterns_saved += 1

        for story_type in result.get("patterns", {}).get("story_types", []):
            perf = story_type.get("performance", "medium")
            upsert_pattern(
                pattern_type="story_type",
                pattern_key=story_type.get("story_type", ""),
                pattern_data=story_type,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for source_region in result.get("patterns", {}).get("source_regions", []):
            perf = source_region.get("performance", "medium")
            upsert_pattern(
                pattern_type="source_region",
                pattern_key=source_region.get("source_region", ""),
                pattern_data=source_region,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for series_format in result.get("patterns", {}).get("series_formats", []):
            perf = series_format.get("performance", "medium")
            upsert_pattern(
                pattern_type="series_format",
                pattern_key=series_format.get("series_format", ""),
                pattern_data=series_format,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for emotion in result.get("patterns", {}).get("emotions", []):
            perf = emotion.get("performance", "medium")
            upsert_pattern(
                pattern_type="emotion",
                pattern_key=emotion.get("emotion", ""),
                pattern_data=emotion,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for ending in result.get("patterns", {}).get("ending_types", []):
            perf = ending.get("performance", "medium")
            upsert_pattern(
                pattern_type="ending_type",
                pattern_key=ending.get("ending_type", ""),
                pattern_data=ending,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for density in result.get("patterns", {}).get("scene_density", []):
            perf = density.get("performance", "medium")
            upsert_pattern(
                pattern_type="scene_density",
                pattern_key=density.get("scene_density", ""),
                pattern_data=density,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for topic in result.get("patterns", {}).get("topics", []):
            perf = topic.get("performance", "medium")
            upsert_pattern(
                pattern_type="topic",
                pattern_key=topic.get("topic_keyword", ""),
                pattern_data=topic,
                win_rate={"high": 0.8, "medium": 0.5, "low": 0.2}.get(perf, 0.5),
            )
            patterns_saved += 1

        for avoid_item in result.get("avoid", []):
            upsert_pattern(
                pattern_type="avoid",
                pattern_key=avoid_item[:100],
                pattern_data={"description": avoid_item},
                win_rate=0,
                is_active=True,
            )
            patterns_saved += 1

        for rec in result.get("recommendations", []):
            upsert_pattern(
                pattern_type="recommendation",
                pattern_key=rec[:100],
                pattern_data={"recommendation": rec},
                win_rate=0.5,
                is_active=True,
            )
            patterns_saved += 1

        log.info(f"패턴 {patterns_saved}개 저장 완료")

        if run_id:
            update_run(run_id, status="completed")

    except Exception as e:
        log.error(f"성과 분석 실패: {e}", exc_info=True)
        try:
            if run_id:
                from tools.supabase_client import update_run
                update_run(run_id, status="failed", error_message=str(e), failure_stage="analyze_patterns")
        except Exception:
            pass


def job_health_check():
    """토큰/Supabase/쿼터 상태 확인"""
    status = {"time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")}

    # YouTube 토큰 확인
    try:
        from tools.youtube_auth import check_token_valid
        status["youtube_token"] = "valid" if check_token_valid() else "INVALID"
    except Exception as e:
        status["youtube_token"] = f"error: {e}"

    # Supabase 연결 확인
    try:
        from tools.supabase_client import get_client
        client = get_client()
        status["supabase"] = "connected" if client else "not configured"
    except Exception as e:
        status["supabase"] = f"error: {e}"

    # 일일 쿼터
    try:
        from tools.youtube_uploader import check_daily_quota_remaining
        quota = check_daily_quota_remaining()
        status["quota"] = f"{quota['used']}/{quota['limit']}"
    except Exception as e:
        status["quota"] = f"error: {e}"

    # 상태 출력
    issues = []
    if status.get("youtube_token") == "INVALID":
        issues.append("YouTube 토큰 만료!")
    if "error" in str(status.get("supabase", "")):
        issues.append("Supabase 연결 실패!")

    if issues:
        log.warning(f"[Health] {status} — 문제: {', '.join(issues)}")
    else:
        log.info(f"[Health] {status}")


# ============================================================
# 스케줄러 설정
# ============================================================

def create_scheduler() -> BlockingScheduler:
    """APScheduler 설정 및 작업 등록"""
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 영상 생성+업로드: 06:30, 12:30, 18:30 KST
    scheduler.add_job(
        job_generate_and_upload,
        CronTrigger(hour="6,12,18", minute=30, timezone="Asia/Seoul"),
        id="generate_and_upload",
        name="영상 생성+업로드",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 애널리틱스 수집: 6시간마다
    scheduler.add_job(
        job_collect_analytics,
        IntervalTrigger(hours=6),
        id="collect_analytics",
        name="애널리틱스 수집",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 성과 분석: 매일 00:00 KST
    scheduler.add_job(
        job_analyze_patterns,
        CronTrigger(hour=0, minute=0, timezone="Asia/Seoul"),
        id="analyze_patterns",
        name="성과 분석+패턴 업데이트",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 헬스 체크: 1시간마다
    scheduler.add_job(
        job_health_check,
        IntervalTrigger(hours=1),
        id="health_check",
        name="헬스 체크",
        max_instances=1,
    )

    return scheduler


def main():
    parser = argparse.ArgumentParser(description="유머/썰 YouTube Shorts 메인 스케줄러")
    parser.add_argument(
        "--once",
        action="store_true",
        help="1회 실행 후 종료",
    )
    args = parser.parse_args()

    if args.once:
        log.info("=== 1회 실행 모드 ===")
        job_health_check()
        job_generate_and_upload()
        job_collect_analytics()
        log.info("=== 1회 실행 완료 ===")
        return

    scheduler = create_scheduler()

    # 종료 시그널 처리
    def shutdown(signum, frame):
        log.info("종료 시그널 수신. 스케줄러를 중지합니다...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("=== 썰알람 YouTube Shorts 메인 스케줄러 시작 ===")
    log.info("스케줄:")
    log.info("  - 영상 생성+업로드: 06:30, 12:30, 18:30 KST")
    log.info("  - 애널리틱스 수집: 6시간마다")
    log.info("  - 성과 분석: 매일 00:00 KST")
    log.info("  - 헬스 체크: 1시간마다")
    log.info("Ctrl+C로 종료")

    # 시작 시 헬스 체크
    job_health_check()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("스케줄러 종료")


if __name__ == "__main__":
    main()
