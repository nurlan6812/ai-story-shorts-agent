"""YouTube OAuth2 토큰 관리"""

import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config.settings import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_TOKEN_PATH,
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube",  # 업로드 + 수정 + 삭제
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _build_client_config() -> dict:
    """OAuth2 클라이언트 설정을 환경변수에서 구성"""
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
        raise RuntimeError(
            "YOUTUBE_CLIENT_ID와 YOUTUBE_CLIENT_SECRET이 .env에 설정되어 있지 않습니다."
        )
    return {
        "installed": {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def run_auth_flow() -> Credentials:
    """최초 1회 브라우저 인증 → refresh token 저장

    Returns:
        인증된 Credentials 객체
    """
    client_config = _build_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent")

    # 토큰 저장
    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes and list(credentials.scopes),
    }
    YOUTUBE_TOKEN_PATH.write_text(json.dumps(token_data, indent=2))
    print(f"[Auth] 토큰 저장 완료: {YOUTUBE_TOKEN_PATH}")
    return credentials


def _load_credentials() -> Credentials | None:
    """저장된 토큰 파일에서 Credentials 로드 + 자동 갱신"""
    if not YOUTUBE_TOKEN_PATH.exists():
        return None

    token_data = json.loads(YOUTUBE_TOKEN_PATH.read_text())
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id") or YOUTUBE_CLIENT_ID,
        client_secret=token_data.get("client_secret") or YOUTUBE_CLIENT_SECRET,
        scopes=token_data.get("scopes"),
    )

    # 토큰 만료 시 자동 갱신
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data["token"] = creds.token
        YOUTUBE_TOKEN_PATH.write_text(json.dumps(token_data, indent=2))

    return creds


def check_token_valid() -> bool:
    """토큰 유효성 확인"""
    creds = _load_credentials()
    if creds is None:
        return False
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            return True
        except Exception:
            return False
    return creds.valid


def get_authenticated_service(api_name: str = "youtube", api_version: str = "v3"):
    """인증된 Google API 서비스 반환 (자동 refresh)

    Args:
        api_name: API 이름 (youtube, youtubeAnalytics 등)
        api_version: API 버전

    Returns:
        인증된 API 서비스 객체

    Raises:
        RuntimeError: 토큰이 없거나 유효하지 않은 경우
    """
    creds = _load_credentials()
    if creds is None:
        raise RuntimeError(
            "YouTube 인증이 필요합니다. 먼저 `python main.py --auth`를 실행하세요."
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build(api_name, api_version, credentials=creds)
