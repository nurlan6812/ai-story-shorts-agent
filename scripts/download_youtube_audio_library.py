#!/usr/bin/env python3
"""Download the project's curated YouTube Audio Library BGM set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

try:
    import browser_cookie3
except ImportError as exc:  # pragma: no cover - operator-facing script
    raise SystemExit(
        "browser-cookie3 is required for this script. Install it with "
        "`python3 -m pip install --user browser-cookie3`."
    ) from exc


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = BASE_DIR / "assets" / "bgm_safe" / "youtube_audio_library"
CHROME_DIR = Path.home() / "Library/Application Support" / "Google" / "Chrome"
STUDIO_ORIGIN = "https://studio.youtube.com"
STUDIO_HOME_URL = f"{STUDIO_ORIGIN}/"
API_TEMPLATE = (
    "https://studio.youtube.com/youtubei/v1/creator_music/get_tracks"
    "?alt=json&key={api_key}"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

DEFAULT_TRACKS: list[dict[str, Any]] = [
    {
        "mood": "funny",
        "filename": "funny.mp3",
        "track_id": "0Fe0x2MyKJk",
        "title": "Twinkle",
        "artist": "The Grey Room / Density & Time",
        "library_mood": "CREATOR_MUSIC_MOOD_CALM",
        "duration_seconds": 194,
    },
    {
        "mood": "quirky",
        "filename": "quirky.mp3",
        "track_id": "3Xd-wnkxGJE",
        "title": "Glass Chinchilla",
        "artist": "The Mini Vandals",
        "library_mood": "CREATOR_MUSIC_MOOD_CALM",
        "duration_seconds": 100,
    },
    {
        "mood": "chill",
        "filename": "chill.mp3",
        "track_id": "DMW03bATnYk",
        "title": "Sample Mind",
        "artist": "Freedom Trail Studio",
        "library_mood": "CREATOR_MUSIC_MOOD_CALM",
        "duration_seconds": 149,
    },
    {
        "mood": "emotional",
        "filename": "emotional.mp3",
        "track_id": "FR2IM_QJCiI",
        "title": "A Distant Call",
        "artist": "Dan \"Lebo\" Lebowitz, Tone Seeker",
        "library_mood": "CREATOR_MUSIC_MOOD_SAD",
        "duration_seconds": 174,
    },
    {
        "mood": "tension",
        "filename": "tension.mp3",
        "track_id": "RA2Qt6_4RX4",
        "title": "Veil of mysteries.",
        "artist": "Patrick Patrikios",
        "library_mood": "CREATOR_MUSIC_MOOD_CALM",
        "duration_seconds": 157,
    },
    {
        "mood": "dramatic",
        "filename": "dramatic.mp3",
        "track_id": "vWU0d804gQE",
        "title": "Drifting Memories",
        "artist": "The Mini Vandals",
        "library_mood": "CREATOR_MUSIC_MOOD_DRAMATIC",
        "duration_seconds": 182,
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Target directory for downloaded MP3s (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--profile",
        default="",
        help="Chrome profile name to use, e.g. 'Profile 3'. Default auto-detects.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload files even when the destination already exists.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Optional JSON catalog path. Supports either a list of tracks or an object with a `tracks` list.",
    )
    return parser.parse_args()


def _load_tracks(catalog_path: Path | None) -> list[dict[str, Any]]:
    if catalog_path is None:
        return list(DEFAULT_TRACKS)

    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        tracks = raw.get("tracks", [])
    else:
        tracks = raw

    if not isinstance(tracks, list) or not tracks:
        raise SystemExit(f"Track catalog is empty or invalid: {catalog_path}")
    return [dict(item) for item in tracks]


def _iter_cookie_files(profile_name: str = "") -> list[Path]:
    if profile_name:
        explicit = CHROME_DIR / profile_name / "Cookies"
        if not explicit.exists():
            raise SystemExit(f"Chrome cookie DB not found for profile: {explicit}")
        return [explicit]

    candidates: list[Path] = []
    for child in sorted(CHROME_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name != "Default" and not child.name.startswith("Profile "):
            continue
        cookie_file = child / "Cookies"
        if cookie_file.exists():
            candidates.append(cookie_file)
    if not candidates:
        raise SystemExit(f"No Chrome cookie DB found under: {CHROME_DIR}")
    return candidates


def _load_session(cookie_file: Path) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.cookies.update(browser_cookie3.chrome(cookie_file=str(cookie_file)))
    return session


def _extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _studio_context(session: requests.Session, cookie_file: Path) -> dict[str, Any] | None:
    response = session.get(STUDIO_HOME_URL, timeout=30)
    if response.status_code != 200:
        return None
    html = response.text or ""
    api_key = _extract(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    client_name = _extract(r'"INNERTUBE_CONTEXT_CLIENT_NAME":(\d+)', html)
    client_version = _extract(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', html)
    channel_id = _extract(r'"channelId":"(UC[^"]+)"', html) or _extract(
        r'"externalChannelId":"(UC[^"]+)"', html
    )
    sapisid = session.cookies.get("SAPISID", domain=".youtube.com") or session.cookies.get("SAPISID")
    if not all([api_key, client_name, client_version, channel_id, sapisid]):
        return None
    return {
        "session": session,
        "cookie_file": cookie_file,
        "profile_name": cookie_file.parent.name,
        "api_key": api_key,
        "client_name": int(client_name),
        "client_version": client_version,
        "channel_id": channel_id,
        "sapisid": sapisid,
    }


def _build_auth_headers(studio: dict[str, Any]) -> dict[str, str]:
    now = str(int(time.time()))
    digest = hashlib.sha1(f"{now} {studio['sapisid']} {STUDIO_ORIGIN}".encode()).hexdigest()
    return {
        "Authorization": f"SAPISIDHASH {now}_{digest}",
        "Content-Type": "application/json",
        "Origin": STUDIO_ORIGIN,
        "Referer": f"{STUDIO_ORIGIN}/channel/{studio['channel_id']}/music",
        "X-Goog-AuthUser": "0",
        "X-Origin": STUDIO_ORIGIN,
    }


def _find_studio_session(profile_name: str = "") -> dict[str, Any]:
    for cookie_file in _iter_cookie_files(profile_name):
        session = _load_session(cookie_file)
        studio = _studio_context(session, cookie_file)
        if studio:
            print(f"[Audio Library] Using Chrome profile: {studio['profile_name']}")
            print(f"[Audio Library] Channel: {studio['channel_id']}")
            return studio
    raise SystemExit("No signed-in YouTube Studio Chrome profile was found.")


def _fetch_track_details(studio: dict[str, Any], track_ids: list[str]) -> list[dict[str, Any]]:
    payload = {
        "context": {
            "client": {
                "clientName": studio["client_name"],
                "clientVersion": studio["client_version"],
                "hl": "ko",
                "gl": "KR",
                "utcOffsetMinutes": 540,
            },
            "request": {
                "internalExperimentFlags": [],
                "useSsl": True,
            },
        },
        "channelId": studio["channel_id"],
        "trackIds": track_ids,
        "mask": {"includeDownloadUrl": True},
    }
    url = API_TEMPLATE.format(api_key=studio["api_key"])
    response = studio["session"].post(
        url,
        headers=_build_auth_headers(studio),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    tracks = data.get("tracks", [])
    if len(tracks) != len(track_ids):
        found = {track.get("trackId") for track in tracks}
        missing = [track_id for track_id in track_ids if track_id not in found]
        raise RuntimeError(f"Audio Library track lookup incomplete. Missing: {missing}")
    return tracks


def _download_file(session: requests.Session, url: str, destination: Path) -> None:
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    handle.write(chunk)


def _write_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    manifest = {
        "generated_at": int(time.time()),
        "source": "YouTube Audio Library",
        "tracks": rows,
    }
    manifest_path = output_dir / "tracks.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tracks = _load_tracks(args.catalog)

    studio = _find_studio_session(args.profile)
    tracks_by_id = {
        track["trackId"]: track
        for track in _fetch_track_details(studio, [item["track_id"] for item in tracks])
    }

    manifest_rows: list[dict[str, Any]] = []
    for item in tracks:
        track = tracks_by_id[item["track_id"]]
        download_url = track.get("downloadAudioUrl", "")
        if not download_url:
            raise RuntimeError(f"No download URL returned for track: {item['track_id']}")

        destination = args.output_dir / item["filename"]
        if destination.exists() and not args.force:
            print(f"[Audio Library] Skipping existing file: {destination.name}")
        else:
            print(f"[Audio Library] Downloading {item['title']} -> {destination.name}")
            _download_file(studio["session"], download_url, destination)

        manifest_rows.append(
            {
                "mood": item.get("mood", ""),
                "slot": item.get("slot", ""),
                "filename": item["filename"],
                "track_id": item["track_id"],
                "title": track.get("title", item["title"]),
                "artist": (track.get("artist") or {}).get("name", item["artist"]),
                "duration_seconds": int(((track.get("duration") or {}).get("seconds")) or 0),
                "library_moods": ((track.get("attributes") or {}).get("moods", [])),
                "license_type": track.get("licenseType", ""),
                "downloaded_from": "YouTube Audio Library",
            }
        )

    _write_manifest(args.output_dir, manifest_rows)
    print(f"[Audio Library] Done: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
