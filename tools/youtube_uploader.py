"""YouTube 영상 업로드"""

import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from config.settings import AI_DISCLOSURE, MAX_DAILY_UPLOADS
from tools.youtube_auth import get_authenticated_service

MAX_RETRIES = 3
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
HASHTAG_RE = re.compile(r"(?:^|\s)#[^\s#]+")


def _strip_inline_hashtags(text: str) -> str:
    """설명 본문 안에 섞여 있는 인라인 해시태그 제거."""
    cleaned = HASHTAG_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _build_hashtag_line(tags: list[str]) -> str:
    """중복 없이 해시태그 1줄 생성."""
    seen: set[str] = set()
    ordered: list[str] = []

    for raw in list(tags or []) + ["Shorts"]:
        tag = str(raw or "").strip().replace(" ", "")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(f"#{tag}")

    return " ".join(ordered[:10])


def build_shorts_description(plan: dict) -> str:
    """업로드용 Shorts 설명 생성

    Args:
        plan: production_plan dict (description, tags, series_part, series_total 포함)

    Returns:
        YouTube 업로드용 설명 문자열
    """
    description = _strip_inline_hashtags(plan.get("description", ""))
    tags = plan.get("tags", [])
    series_part = plan.get("series_part")
    series_total = plan.get("series_total")

    hashtag_line = _build_hashtag_line(tags)
    parts: list[str] = []
    if description:
        parts.extend([description, ""])

    # 시리즈 안내 문구
    if series_part and series_total and series_total > 1:
        parts.append(f"📺 {series_part}/{series_total}편")
        if series_part < series_total:
            parts.append("다음 편에서 결말이 이어집니다.")
        parts.append("")

    if hashtag_line:
        parts.extend([hashtag_line, ""])

    bgm_credit = ""
    if bool(plan.get("bgm_used", True)):
        bgm_credit = _get_bgm_credit(plan.get("bgm_mood", ""), plan.get("bgm_path", ""))

    parts.extend([
        bgm_credit,
        "",
        AI_DISCLOSURE,
    ])
    return "\n".join(p for p in parts if p is not None).strip()


# 브금대통령 트랙 정보 (레거시 출처 표기용)
BGM_CREDITS = {
    "funny": "Music provided by 브금대통령\nTrack : Black Comedy - https://youtu.be/gHlSF3VpB9U",
    "emotional": "Music provided by 브금대통령\nTrack : 그때의 우리 : 두번째 이야기 - https://youtu.be/7Z1RpQE4GIY",
    "tension": "Music provided by 브금대통령\nTrack : Keep The Tension - https://youtu.be/YRQhxG1O8-8",
    "chill": "Music provided by 브금대통령\nTrack : Paesaggio Italiano - https://youtu.be/9PRnPdgNhMI",
    "quirky": "Music provided by 브금대통령\nTrack : 조별과제 - https://youtu.be/wLuWmPrJkSk",
    "dramatic": "Music provided by 브금대통령",
}

FMA_CC0_CREDITS = {
    "funny": "Music: HoliznaCC0 - Bouncing (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/power-pop/bouncing/",
    "emotional": "Music: HoliznaCC0 - I Need You (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/be-happy-with-who-you-are/i-need-you/",
    "tension": "Music: HoliznaCC0 - Tension In The Air (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/beats-from-the-crypt/tension-in-the-air/",
    "chill": "Music: HoliznaCC0 - Unwind (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/kick-it-laid-back-hiphop/unwind/",
    "quirky": "Music: HoliznaCC0 - Pixel Party (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/tiny-plastic-video-games-for-long-anxious-space-travel/pixel-party/",
    "dramatic": "Music: HoliznaCC0 - Tragedy Waiting To Happen (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/horseless-headman-halloween-beats/tragedy-waiting-to-happen/",
}

YOUTUBE_AUDIO_LIBRARY_CREDITS = {
    "funny": "Music: Twinkle - The Grey Room / Density & Time (YouTube Audio Library)",
    "emotional": "Music: A Distant Call - Dan \"Lebo\" Lebowitz, Tone Seeker (YouTube Audio Library)",
    "tension": "Music: Veil of mysteries. - Patrick Patrikios (YouTube Audio Library)",
    "chill": "Music: Sample Mind - Freedom Trail Studio (YouTube Audio Library)",
    "quirky": "Music: Glass Chinchilla - The Mini Vandals (YouTube Audio Library)",
    "dramatic": "Music: Drifting Memories - The Mini Vandals (YouTube Audio Library)",
}


def _get_bgm_credit(bgm_mood: str, bgm_path: str = "") -> str:
    """BGM 소스에 맞는 출처 문자열 반환"""
    if "bgm_safe/youtube_audio_library" in str(bgm_path or ""):
        return YOUTUBE_AUDIO_LIBRARY_CREDITS.get(
            bgm_mood,
            "Music: YouTube Audio Library",
        )
    if "bgm_safe/fma_cc0" in str(bgm_path or ""):
        return FMA_CC0_CREDITS.get(bgm_mood, "Music: HoliznaCC0 (CC0 1.0)\nSource: https://freemusicarchive.org/music/holiznacc0/")
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
    """Supabase videos 테이블 기반 일일 업로드 쿼터 확인

    Returns:
        {"remaining": int, "used": int, "limit": int, "can_upload": bool}
    """
    try:
        from tools.supabase_client import list_videos

        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        today_start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        used = 0

        for video in list_videos(limit=50, publish_status="uploaded"):
            published_at = video.get("published_at") or video.get("created_at")
            if not published_at:
                continue
            try:
                published_dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            if published_dt.astimezone(kst) >= today_start_kst:
                used += 1
    except Exception:
        used = 0

    return {
        "remaining": max(0, MAX_DAILY_UPLOADS - used),
        "used": used,
        "limit": MAX_DAILY_UPLOADS,
        "can_upload": used < MAX_DAILY_UPLOADS,
    }
