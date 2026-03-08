"""YouTube 영상 업로드"""

import time
import random
from pathlib import Path

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from config.settings import AI_DISCLOSURE, MAX_DAILY_UPLOADS
from tools.youtube_auth import get_authenticated_service

MAX_RETRIES = 3
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]


def build_shorts_description(plan: dict) -> str:
    """#Shorts 태그 + 해시태그 + AI 공시문 + 고정문구 포함 설명 생성

    Args:
        plan: production_plan dict (description, tags, series_part, series_total 포함)

    Returns:
        YouTube 업로드용 설명 문자열
    """
    description = plan.get("description", "")
    tags = plan.get("tags", [])
    series_part = plan.get("series_part")
    series_total = plan.get("series_total")

    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:10])

    parts = [
        description,
        "",
    ]

    # 시리즈 안내 문구
    if series_part and series_total and series_total > 1:
        parts.append(f"📺 [{series_part}/{series_total}편] 시리즈 전체는 채널에서 확인하세요!")
        if series_part < series_total:
            parts.append(f"👉 {series_part + 1}편이 궁금하다면 구독+알림 설정!")
        parts.append("")

    parts.extend([
        hashtags,
        "#Shorts #유머 #썰 #사연",
        "",
        "😂 매일 웃기고 감동적인 썰을 60초로 정리!",
        "🔔 구독과 좋아요로 매일 재미있는 이야기를 받아보세요!",
        "",
        "💬 비슷한 경험 있으면 댓글로 알려주세요!",
        "",
        _get_bgm_credit(plan.get("bgm_mood", "")),
        "",
        AI_DISCLOSURE,
    ])
    return "\n".join(parts)


# 브금대통령 트랙 정보 (출처 표기용)
BGM_CREDITS = {
    "funny": "Music provided by 브금대통령\nTrack : Black Comedy - https://youtu.be/gHlSF3VpB9U",
    "emotional": "Music provided by 브금대통령\nTrack : 그때의 우리 : 두번째 이야기 - https://youtu.be/7Z1RpQE4GIY",
    "tension": "Music provided by 브금대통령\nTrack : Keep The Tension - https://youtu.be/YRQhxG1O8-8",
    "chill": "Music provided by 브금대통령\nTrack : Paesaggio Italiano - https://youtu.be/9PRnPdgNhMI",
    "quirky": "Music provided by 브금대통령\nTrack : 조별과제 - https://youtu.be/wLuWmPrJkSk",
    "dramatic": "Music provided by 브금대통령",
}


def _get_bgm_credit(bgm_mood: str) -> str:
    """BGM 무드에 따른 브금대통령 출처 문자열 반환"""
    return BGM_CREDITS.get(bgm_mood, "Music provided by 브금대통령")


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "public",
) -> dict:
    """YouTube에 영상 업로드 (재개 가능 업로드, 3회 재시도)

    Args:
        video_path: 업로드할 영상 파일 경로
        title: 영상 제목
        description: 영상 설명
        tags: 태그 목록
        privacy_status: 공개 상태 (public/private/unlisted)

    Returns:
        {"youtube_id": str, "url": str, "published_at": str}

    Raises:
        HttpError: YouTube API 에러
        RuntimeError: 업로드 실패
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}")

    youtube = get_authenticated_service("youtube", "v3")

    body = {
        "snippet": {
            "title": title[:100],  # YouTube 제목 제한
            "description": description[:5000],
            "tags": (tags or [])[:30],
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=256 * 1024,  # 256KB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = _resumable_upload(request)
    youtube_id = response["id"]

    return {
        "youtube_id": youtube_id,
        "url": f"https://youtube.com/shorts/{youtube_id}",
        "published_at": response["snippet"].get("publishedAt", ""),
    }


def _resumable_upload(request) -> dict:
    """재개 가능 업로드 + 지수 백오프 재시도"""
    response = None
    retry = 0

    while response is None:
        try:
            print("  [Upload] 업로드 중...")
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"  [Upload] {progress}% 완료")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                retry += 1
                if retry > MAX_RETRIES:
                    raise RuntimeError(f"업로드 실패 ({MAX_RETRIES}회 재시도 초과): {e}")
                sleep_seconds = random.uniform(1, 2**retry)
                print(f"  [Upload] 재시도 {retry}/{MAX_RETRIES} ({sleep_seconds:.1f}초 후)...")
                time.sleep(sleep_seconds)
            else:
                raise
        except Exception as e:
            retry += 1
            if retry > MAX_RETRIES:
                raise RuntimeError(f"업로드 실패 ({MAX_RETRIES}회 재시도 초과): {e}")
            sleep_seconds = random.uniform(1, 2**retry)
            print(f"  [Upload] 재시도 {retry}/{MAX_RETRIES} ({sleep_seconds:.1f}초 후)...")
            time.sleep(sleep_seconds)

    print(f"  [Upload] 업로드 완료: https://youtube.com/shorts/{response['id']}")
    return response


def check_daily_quota_remaining() -> dict:
    """Supabase runs 테이블 기반 일일 쿼터 확인

    Returns:
        {"remaining": int, "used": int, "limit": int, "can_upload": bool}
    """
    try:
        from tools.supabase_client import get_runs_today
        runs = get_runs_today(run_type="generate")
        used = len(runs)
    except Exception:
        used = 0

    return {
        "remaining": max(0, MAX_DAILY_UPLOADS - used),
        "used": used,
        "limit": MAX_DAILY_UPLOADS,
        "can_upload": used < MAX_DAILY_UPLOADS,
    }
