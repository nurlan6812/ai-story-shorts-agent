"""Director까지만 실행하여 중간 결과물 확인 (테스트용)"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import OUTPUT_DIR
from agents.researcher import research
from agents.director import create_full_plan
from agents.critic import review_production

MAX_CRITIC_REVISIONS = 2


def main():
    work_dir = OUTPUT_DIR / "director_test"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 0. Researcher
    print("[0] Researcher 실행 중...")
    research_brief = research(hint="에어팟 도둑 썰", trend_hints=None)
    (work_dir / "research_brief.json").write_text(
        json.dumps(research_brief, ensure_ascii=False, indent=2)
    )
    print(f"  -> 주제: {research_brief.get('topic', '?')}")
    print(f"  -> 훅: {research_brief.get('hook', '?')}")
    print(f"  -> 스토리 포인트: {len(research_brief.get('story_points', []))}개")

    # 1. Director + Critic
    print("\n[1] Director 플랜 생성 중...")
    plan = create_full_plan(research_brief, winning_patterns=None)
    (work_dir / "production_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2)
    )
    print(f"  -> 제목: {plan.get('title', '?')}")
    print(f"  -> 스타일: {plan.get('style', '?')}")
    print(f"  -> 장면 수: {len(plan.get('scenes', []))}")
    print(f"  -> 캐릭터 수: {len(plan.get('characters', []))}")

    # Critic 검증
    print("\n[2] Critic 검증 중...")
    for revision in range(MAX_CRITIC_REVISIONS):
        review = review_production(research_brief, plan)
        score = review.get("score", 0)
        approved = review.get("approved", False)
        print(f"  -> 점수: {score}/100, 승인: {'✅' if approved else '❌'}")
        print(f"  -> 피드백: {review.get('feedback', '')}")

        if approved:
            break

        notes = review.get("revision_notes", [])
        if notes:
            from agents.director import revise_plan
            print(f"  -> 수정 요청: {notes}")
            plan = revise_plan(plan, notes)
            (work_dir / f"production_plan_rev{revision + 1}.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2)
            )

    print(f"\n✅ 완료. 결과물: {work_dir}")
    print(f"  - research_brief.json")
    print(f"  - production_plan.json")


if __name__ == "__main__":
    main()
