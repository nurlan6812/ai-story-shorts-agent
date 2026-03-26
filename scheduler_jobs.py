"""스케줄러 공통 작업 함수.

- 메인 스케줄러: 정규 슬롯(06:30/11:30/18:30) 생성 담당
- 복구 스케줄러: 반시 결과 점검 후 누락 슬롯 재시도 담당

같은 슬롯을 두 프로세스가 동시에 생성하지 않도록 slot_key 기반 파일 락을 사용한다.
프로세스가 종료되면 OS가 락을 자동 해제하므로, 다음 점검 시점에 복구가 가능하다.
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("scheduler.jobs")

KST = timezone(timedelta(hours=9))
GENERATE_HOURS = (6, 11, 18)
GENERATE_MINUTE = 30
SLOT_CHECK_START_HOURS = 1
SLOT_CHECK_MAX_COUNT = 3

_PROCESS_GENERATE_LOCK = threading.Lock()
_SLOT_LOCK_DIR = Path(__file__).resolve().parent / "runtime" / "slot_locks"


def build_slot_key(slot_start_kst: datetime) -> str:
    return slot_start_kst.isoformat(timespec="minutes")


def format_slot_label(slot_start_kst: datetime | None) -> str:
    if slot_start_kst is None:
        return "manual"
    return slot_start_kst.strftime("%Y-%m-%d %H:%M KST")


def resolve_generate_slot_start(now_kst: datetime) -> datetime:
    today = now_kst.date()
    yday = today - timedelta(days=1)

    slots = [
        datetime(yday.year, yday.month, yday.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ] + [
        datetime(today.year, today.month, today.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ]
    return max(slot for slot in slots if slot <= now_kst)


def current_check_slot(now_kst: datetime) -> datetime | None:
    today = now_kst.date()
    yday = today - timedelta(days=1)

    all_slots = [
        datetime(yday.year, yday.month, yday.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ] + [
        datetime(today.year, today.month, today.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ]
    all_slots.sort()

    for slot_start in reversed(all_slots):
        check_start = slot_start + timedelta(hours=SLOT_CHECK_START_HOURS)
        check_end = slot_start + timedelta(
            hours=SLOT_CHECK_START_HOURS + SLOT_CHECK_MAX_COUNT - 1
        )
        if check_start <= now_kst <= check_end:
            return slot_start
    return None


def slot_window(slot_start_kst: datetime) -> tuple[datetime, datetime]:
    today = slot_start_kst.date()
    next_day = today + timedelta(days=1)
    all_slots = [
        datetime(today.year, today.month, today.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ] + [
        datetime(next_day.year, next_day.month, next_day.day, hour, GENERATE_MINUTE, tzinfo=KST)
        for hour in GENERATE_HOURS
    ]
    next_slots = [slot for slot in all_slots if slot > slot_start_kst]
    if next_slots:
        return slot_start_kst, next_slots[0]
    return slot_start_kst, slot_start_kst + timedelta(hours=6)


@contextmanager
def slot_lock(slot_key: str):
    _SLOT_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = slot_key.replace(":", "-").replace("+", "_")
    lock_path = _SLOT_LOCK_DIR / f"{safe_name}.lock"
    handle = lock_path.open("a+", encoding="utf-8")

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return

    try:
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\nslot_key={slot_key}\n")
        handle.flush()
        yield True
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def has_uploaded_video_in_window(
    start_kst: datetime,
    end_kst: datetime,
) -> tuple[bool | None, dict | None]:
    try:
        from tools.supabase_client import get_client

        client = get_client()
        if client is None:
            return None, None

        start_utc = start_kst.astimezone(timezone.utc).isoformat()
        end_utc = end_kst.astimezone(timezone.utc).isoformat()
        result = (
            client.table("videos")
            .select("id,title,published_at,publish_status")
            .eq("publish_status", "uploaded")
            .gte("published_at", start_utc)
            .lt("published_at", end_utc)
            .order("published_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return True, result.data[0]
        return False, None
    except Exception as exc:
        log.warning("슬롯 결과 조회 실패: %s", exc)
        return None, None


def job_generate_and_upload(
    slot_start_kst: datetime | None = None,
    trigger_source: str = "schedule",
    max_retries: int = 6,
    retry_delay: int = 300,
):
    now_kst = datetime.now(KST)
    if slot_start_kst is None and trigger_source == "schedule":
        slot_start_kst = resolve_generate_slot_start(now_kst)

    slot_key = build_slot_key(slot_start_kst) if slot_start_kst else None
    slot_label = format_slot_label(slot_start_kst)

    if not _PROCESS_GENERATE_LOCK.acquire(blocking=False):
        log.warning("[%s][%s] 생성 작업이 이미 실행 중이라 이번 호출은 건너뜁니다.", slot_label, trigger_source)
        return

    try:
        lock_context = slot_lock(slot_key) if slot_key else nullcontext(True)
        with lock_context as locked:
            if not locked:
                log.info("[%s][%s] 같은 슬롯을 다른 프로세스가 이미 처리 중이라 건너뜁니다.", slot_label, trigger_source)
                return

            if slot_start_kst:
                start_kst, end_kst = slot_window(slot_start_kst)
                has_upload, video = has_uploaded_video_in_window(start_kst, end_kst)
                if has_upload is True:
                    log.info("[%s][%s] 이미 업로드된 결과가 있어 건너뜁니다: %s", slot_label, trigger_source, video.get("title", "?"))
                    return
                if has_upload is None and trigger_source != "schedule":
                    log.info("[%s][%s] 결과 조회 불가로 복구 재시도는 건너뜁니다.", slot_label, trigger_source)
                    return

            for attempt in range(1, max_retries + 1):
                log.info("=== [%s][%s] 영상 생성+업로드 시작 (시도 %s/%s) ===", slot_label, trigger_source, attempt, max_retries)

                try:
                    from tools.youtube_uploader import check_daily_quota_remaining

                    quota = check_daily_quota_remaining()
                    if not quota["can_upload"]:
                        log.info("[%s][%s] 일일 쿼터 초과 (%s/%s). 건너뜁니다.", slot_label, trigger_source, quota["used"], quota["limit"])
                        return

                    log.info("[%s][%s] 남은 쿼터: %s/%s", slot_label, trigger_source, quota["remaining"], quota["limit"])

                    from main import _process_upload_queue
                    if _process_upload_queue(trigger_source=trigger_source, slot_key=slot_key):
                        log.info("[%s][%s] 대기열 영상 1편 업로드 완료", slot_label, trigger_source)
                        log.info("[%s][%s] 이번 슬롯은 대기열 업로드를 우선 처리했으므로 새 영상 생성은 건너뜁니다.", slot_label, trigger_source)
                        return

                    winning_patterns = None
                    trend_hints = None
                    try:
                        from tools.supabase_client import get_active_patterns

                        patterns = get_active_patterns()
                        if patterns:
                            from main import _build_trend_hints, _build_winning_patterns

                            winning_patterns = _build_winning_patterns(patterns)
                            trend_hints = _build_trend_hints(patterns)
                            log.info("[%s][%s] 활성 패턴 %s개 로드", slot_label, trigger_source, len(patterns))
                    except Exception as exc:
                        log.warning("[%s][%s] 패턴 로드 실패: %s", slot_label, trigger_source, exc)

                    from agents.researcher import research
                    from main import (
                        _enqueue_upload,
                        _normalize_research_brief,
                        _handle_upload,
                        _next_publish_slot,
                        _run_series_pipeline,
                        run_pipeline_single,
                    )

                    from tools.supabase_client import insert_run, update_run

                    research_run = insert_run(
                        run_type="research",
                        trigger_source=trigger_source,
                        retry_count=attempt - 1,
                        slot_key=slot_key,
                    )
                    research_run_id = research_run["id"] if research_run else None

                    duplicate_video = None
                    research_brief = None
                    for research_attempt in range(1, 4):
                        research_brief = research("", trend_hints=trend_hints)
                        research_brief = _normalize_research_brief(research_brief)
                        from main import _find_recent_duplicate_story

                        duplicate_video = _find_recent_duplicate_story(research_brief)
                        if not duplicate_video:
                            break
                        log.info(
                            "[%s][%s] 최근 중복 source 발견 (%s), 재탐색 %s/3",
                            slot_label,
                            trigger_source,
                            duplicate_video.get("title", "?"),
                            research_attempt,
                        )
                    if research_run_id:
                        if research_brief:
                            update_run(
                                research_run_id,
                                status="completed",
                                run_meta={
                                    "topic": research_brief.get("topic"),
                                    "source_region": research_brief.get("source_region"),
                                    "series_potential": research_brief.get("series_potential"),
                                    "duplicate_candidate": duplicate_video.get("id") if duplicate_video else None,
                                },
                            )
                        else:
                            update_run(research_run_id, status="failed", failure_stage="research")
                    if research_brief.get("source_region") not in {"한국", "외국"}:
                        research_brief["source_region"] = "한국"
                    log.info("[%s][%s] 리서치 완료: %s", slot_label, trigger_source, research_brief.get("topic", "?"))

                    generate_run = insert_run(
                        run_type="generate",
                        trigger_source=trigger_source,
                        retry_count=attempt - 1,
                        slot_key=slot_key,
                        run_meta={
                            "topic": research_brief.get("topic"),
                            "series_potential": research_brief.get("series_potential"),
                        },
                    )
                    generate_run_id = generate_run["id"] if generate_run else None

                    if research_brief.get("series_potential", False):
                        results = _run_series_pipeline(
                            research_brief=research_brief,
                            no_critic=False,
                            winning_patterns=winning_patterns,
                        )
                        if results:
                            if generate_run_id:
                                update_run(
                                    generate_run_id,
                                    status="completed",
                                    run_meta={
                                        "topic": research_brief.get("topic"),
                                        "series_total": len(results),
                                    },
                                )
                            log.info("[%s][%s] 시리즈 1/%s편 즉시 업로드", slot_label, trigger_source, len(results))
                            try:
                                _handle_upload(
                                    results[0][0],
                                    results[0][1],
                                    trigger_source=trigger_source,
                                    retry_count=attempt - 1,
                                    slot_key=slot_key,
                                )
                            except Exception as exc:
                                log.warning("[%s][%s] 1편 업로드 실패, 대기열로 이동: %s", slot_label, trigger_source, exc)
                                _enqueue_upload(results[0][0], results[0][1], trigger_source=trigger_source)

                            for i, (video, meta) in enumerate(results[1:], 2):
                                log.info("[%s][%s] 시리즈 %s/%s편 대기열 저장", slot_label, trigger_source, i, len(results))
                                publish_after = _next_publish_slot(datetime.now(KST), step=i - 2).astimezone(timezone.utc).isoformat()
                                _enqueue_upload(video, meta, trigger_source=trigger_source, publish_after=publish_after)
                            return

                    final_video, metadata = run_pipeline_single(
                        topic=str(research_brief.get("topic", "") or ""),
                        no_research=True,
                        no_critic=False,
                        winning_patterns=winning_patterns,
                        research_brief_override=research_brief,
                    )
                    if generate_run_id:
                        update_run(
                            generate_run_id,
                            status="completed",
                            run_meta={"title": metadata.get("title"), "series_total": metadata.get("series_total")},
                        )
                    _handle_upload(
                        final_video,
                        metadata,
                        trigger_source=trigger_source,
                        retry_count=attempt - 1,
                        slot_key=slot_key,
                    )
                    log.info("[%s][%s] 완료: %s", slot_label, trigger_source, metadata.get("title", "?"))
                    return

                except Exception as exc:
                    log.error(
                        "[%s][%s] 생성+업로드 실패 (시도 %s/%s): %s",
                        slot_label,
                        trigger_source,
                        attempt,
                        max_retries,
                        exc,
                        exc_info=True,
                    )
                    try:
                        if 'generate_run_id' in locals() and generate_run_id:
                            from tools.supabase_client import update_run
                            update_run(generate_run_id, status="failed", error_message=str(exc), failure_stage="generate")
                    except Exception:
                        pass
                    if attempt < max_retries:
                        log.info("[%s][%s] %s분 후 재시도합니다...", slot_label, trigger_source, retry_delay // 60)
                        time.sleep(retry_delay)
                    else:
                        log.error("[%s][%s] 최대 재시도 횟수 초과 (%s회).", slot_label, trigger_source, max_retries)
    finally:
        _PROCESS_GENERATE_LOCK.release()


def job_check_missed_slot():
    now_kst = datetime.now(KST)
    slot_start_kst = current_check_slot(now_kst.replace(second=0, microsecond=0))
    if slot_start_kst is None:
        return

    start_kst, end_kst = slot_window(slot_start_kst)
    has_upload, video = has_uploaded_video_in_window(start_kst, end_kst)
    slot_label = format_slot_label(slot_start_kst)

    if has_upload is None:
        log.info("[%s][slot_check] 결과 조회 불가(Supabase 미설정/오류)로 건너뜁니다.", slot_label)
        return

    if has_upload:
        log.info("[%s][slot_check] 결과 확인됨: %s", slot_label, video.get("title", "?"))
        return

    log.warning("[%s][slot_check] 결과 누락 감지 → 보강 재시도 실행", slot_label)
    job_generate_and_upload(slot_start_kst=slot_start_kst, trigger_source="slot_check")
