"""유머/썰 YouTube Shorts 복구 점검 스케줄러.

사용법:
    python scheduler_2.py           # 데몬 시작 (정각 결과 점검)
    python scheduler_2.py --once    # 현재 시점 기준 1회 점검

스케줄:
    - 매시 정각 실행
    - 06시 슬롯 -> 07/08/09시 점검
    - 12시 슬롯 -> 13/14/15시 점검
    - 19시 슬롯 -> 20/21/22시 점검
"""

import argparse
import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler_jobs import job_check_missed_slot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler_2")


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        job_check_missed_slot,
        CronTrigger(minute=30, timezone="Asia/Seoul"),
        id="check_missed_slot",
        name="슬롯 결과 누락 감시",
        max_instances=1,
        misfire_grace_time=3600,
    )
    return scheduler


def main():
    parser = argparse.ArgumentParser(description="유머/썰 YouTube Shorts 복구 점검 스케줄러")
    parser.add_argument(
        "--once",
        action="store_true",
        help="현재 시점 기준 1회 점검 후 종료",
    )
    args = parser.parse_args()

    if args.once:
        log.info("=== 복구 점검 1회 실행 모드 ===")
        job_check_missed_slot()
        log.info("=== 복구 점검 완료 ===")
        return

    scheduler = create_scheduler()

    def shutdown(signum, frame):
        log.info("종료 시그널 수신. 복구 점검 스케줄러를 중지합니다...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("=== 썰알람 YouTube Shorts 복구 점검 스케줄러 시작 ===")
    log.info("스케줄:")
    log.info("  - 매시 30분 점검")
    log.info("  - 06:30 슬롯: 07:30/08:30/09:30")
    log.info("  - 12:30 슬롯: 13:30/14:30/15:30")
    log.info("  - 18:30 슬롯: 19:30/20:30/21:30")
    log.info("Ctrl+C로 종료")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("복구 점검 스케줄러 종료")


if __name__ == "__main__":
    main()
