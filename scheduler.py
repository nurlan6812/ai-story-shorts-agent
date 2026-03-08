"""유머/썰 YouTube Shorts 완전 자동화 스케줄러 (APScheduler 기반)

사용법:
    python scheduler.py           # 데몬 시작 (3회/일 자동 생성)
    python scheduler.py --once    # 1회 실행 후 종료

스케줄:
    - 06:00, 12:00, 19:00 KST: 영상 생성 + 업로드
    - 6시간마다: 48시간+ 영상 애널리틱스 수집
    - 00:00 KST: 전체 성과 분석 + 패턴 업데이트
    - 1시간마다: 헬스 체크
"""

import argparse
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")

KST = timezone(timedelta(hours=9))


# ============================================================
# 작업 함수들
# ============================================================

def job_generate_and_upload():
    """영상 생성 + 업로드 (1회) — 대기열 우선 처리"""
    log.info("=== 영상 생성+업로드 시작 ===")

    try:
        from tools.youtube_uploader import check_daily_quota_remaining
        quota = check_daily_quota_remaining()
        if not quota["can_upload"]:
            log.info(f"일일 쿼터 초과 ({quota['used']}/{quota['limit']}). 건너뜁니다.")
            return

        log.info(f"남은 쿼터: {quota['remaining']}/{quota['limit']}")

        # 1) 대기열 우선 처리
        from main import _process_upload_queue
        if _process_upload_queue():
            log.info("대기열 영상 1편 업로드 완료")
            quota = check_daily_quota_remaining()
            if not quota["can_upload"]:
                log.info("대기열 업로드 후 쿼터 소진. 새 영상 생성 건너뜁니다.")
                return

        # 2) 피드백 패턴 로드
        winning_patterns = None
        trend_hints = None
        try:
            from tools.supabase_client import get_active_patterns
            patterns = get_active_patterns()
            if patterns:
                from main import _build_winning_patterns, _build_trend_hints
                winning_patterns = _build_winning_patterns(patterns)
                trend_hints = _build_trend_hints(patterns)
                log.info(f"활성 패턴 {len(patterns)}개 로드")
        except Exception as e:
            log.warning(f"패턴 로드 실패: {e}")

        # 3) 리서치 먼저 실행 (시리즈 판단 필요)
        from agents.researcher import research
        from main import run_pipeline_single, _run_series_pipeline, _handle_upload, _enqueue_upload

        research_brief = research("", trend_hints=trend_hints)
        if research_brief.get("source_region") not in {"한국", "외국"}:
            research_brief["source_region"] = "한국"
        log.info(f"리서치 완료: {research_brief.get('topic', '?')}")

        is_series = research_brief.get("series_potential", False)
        series_parts_data = research_brief.get("series_parts", []) if is_series else []

        if is_series and len(series_parts_data) > 1:
            total_parts = len(series_parts_data)
            log.info(f"시리즈 {total_parts}편 생성 시작")

            # 전편 생성
            results = _run_series_pipeline(
                research_brief=research_brief,
                no_critic=False,
                winning_patterns=winning_patterns,
            )

            # 1편 즉시 업로드, 나머지 대기열
            if results:
                log.info(f"시리즈 1/{len(results)}편 즉시 업로드")
                try:
                    _handle_upload(results[0][0], results[0][1])
                except Exception as e:
                    log.warning(f"1편 업로드 실패, 대기열로 이동: {e}")
                    _enqueue_upload(results[0][0], results[0][1])

                for i, (video, meta) in enumerate(results[1:], 2):
                    log.info(f"시리즈 {i}/{len(results)}편 대기열 저장")
                    _enqueue_upload(video, meta)
        else:
            # 단일 영상
            final_video, metadata = run_pipeline_single(
                topic=str(research_brief.get("topic", "") or ""),
                no_research=True,
                no_critic=False,
                winning_patterns=winning_patterns,
                research_brief_override=research_brief,
            )
            _handle_upload(final_video, metadata)
            log.info(f"완료: {metadata.get('title', '?')}")

    except Exception as e:
        log.error(f"생성+업로드 실패: {e}", exc_info=True)


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

        run_record = insert_run(run_type="analyze")
        run_id = run_record["id"] if run_record else None

        client = get_client()
        if client is None:
            log.warning("Supabase 미설정. 분석 건너뜁니다.")
            return

        # 업로드된 영상 + 애널리틱스 조인
        videos = list_videos(limit=100, upload_status="uploaded")
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

        for emotion in result.get("patterns", {}).get("emotions", []):
            perf = emotion.get("performance", "medium")
            upsert_pattern(
                pattern_type="emotion",
                pattern_key=emotion.get("emotion", ""),
                pattern_data=emotion,
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
                update_run(run_id, status="failed", error_message=str(e))
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

    # 영상 생성+업로드: 06:00, 12:00, 19:00 KST
    scheduler.add_job(
        job_generate_and_upload,
        CronTrigger(hour="6,12,19", minute=0, timezone="Asia/Seoul"),
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
    parser = argparse.ArgumentParser(description="유머/썰 YouTube Shorts 자동화 스케줄러")
    parser.add_argument(
        "--once",
        action="store_true",
        help="1회 실행 후 종료 (전체 사이클)",
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

    log.info("=== 썰알람 YouTube Shorts 자동화 스케줄러 시작 ===")
    log.info("스케줄:")
    log.info("  - 영상 생성+업로드: 06:00, 12:00, 19:00 KST")
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
