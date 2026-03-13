"""썰알람 채널 기본 branding settings 적용"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.youtube_auth import get_authenticated_service


DESCRIPTION = (
    "한 번 들으면 끝까지 보게 되는 실화와 레전드 썰을 짧고 강하게 전합니다.\n"
    "\n"
    "반전 있는 사연, 황당한 이야기, 사이다 결말, 감동 실화를\n"
    "유튜브 쇼츠에 맞게 빠르고 몰입감 있게 정리합니다.\n"
    "\n"
    "📱 짧게 보지만 오래 기억나는 이야기\n"
    "🔥 반전, 사이다, 감동 중심 스토리 쇼츠\n"
    "\n"
    "🔔 썰알람 구독하고 매일 새로운 이야기를 받아보세요!"
)

# YouTube channel keywords는 공백 구분 문자열이다.
KEYWORDS = '썰알람 "실화 썰" "사연 쇼츠" "반전 썰" "사이다 썰" "감동 썰" "레전드 썰" 쇼츠'


def main():
    youtube = get_authenticated_service("youtube", "v3")
    current = youtube.channels().list(part="snippet,brandingSettings", mine=True).execute()
    items = current.get("items", [])
    if not items:
        raise RuntimeError("연결된 YouTube 채널을 찾지 못했습니다.")

    item = items[0]
    channel_id = item["id"]
    branding = item.get("brandingSettings", {})
    channel = dict(branding.get("channel", {}))
    channel.update(
        {
            "description": DESCRIPTION,
            "keywords": KEYWORDS,
            "country": "KR",
            "defaultLanguage": "ko",
        }
    )

    updated = youtube.channels().update(
        part="brandingSettings",
        body={
            "id": channel_id,
            "brandingSettings": {
                "channel": channel,
            },
        },
    ).execute()

    result = updated.get("brandingSettings", {}).get("channel", {})
    print("TITLE:", item.get("snippet", {}).get("title", ""))
    print("CHANNEL_ID:", channel_id)
    print("DESCRIPTION:", result.get("description", ""))
    print("KEYWORDS:", result.get("keywords", ""))
    print("COUNTRY:", result.get("country", ""))
    print("DEFAULT_LANGUAGE:", result.get("defaultLanguage", ""))


if __name__ == "__main__":
    main()
