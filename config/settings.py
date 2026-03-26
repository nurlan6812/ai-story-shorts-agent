import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Paths
ASSETS_DIR = BASE_DIR / "assets"
EFFECTS_DIR = ASSETS_DIR / "effects"
SAFE_BGM_DIR = ASSETS_DIR / "bgm_safe" / "youtube_audio_library"
FALLBACK_BGM_DIR = ASSETS_DIR / "bgm_safe" / "fma_cc0"
LEGACY_BGM_DIR = ASSETS_DIR / "bgm"
BGM_DIR = Path(os.getenv("BGM_DIR", str(LEGACY_BGM_DIR))).expanduser()
if not BGM_DIR.exists() and SAFE_BGM_DIR.exists():
    BGM_DIR = SAFE_BGM_DIR
if not BGM_DIR.exists() and FALLBACK_BGM_DIR.exists():
    BGM_DIR = FALLBACK_BGM_DIR
FONTS_DIR = ASSETS_DIR / "fonts"
STYLES_DIR = BASE_DIR / "styles"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_QUEUE_DIR = OUTPUT_DIR / "upload_queue"

# Google Cloud / Vertex AI
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"

# API Keys
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
# Web Search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Reddit API
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

# YouTube API
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_TOKEN_PATH = BASE_DIR / ".youtube_token.json"
YOUTUBE_DEFAULT_PRIVACY = os.getenv("YOUTUBE_DEFAULT_PRIVACY", "public")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Video settings (YouTube Shorts)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# TTS settings (Gemini TTS)
TTS_VOICE = "Schedar"  # Voice 07
TTS_SPEED = 1.25  # 나레이션 배속 (유머/썰은 좀 더 자연스러운 속도)
TTS_LANGUAGE_CODE = os.getenv("TTS_LANGUAGE_CODE", "ko-KR").strip() or "ko-KR"
TTS_MODEL_PRIMARY = os.getenv("TTS_MODEL_PRIMARY", "gemini-2.5-flash-tts")
TTS_MODEL_FALLBACK = os.getenv("TTS_MODEL_FALLBACK", "gemini-2.5-pro-tts")
TTS_NARRATOR_TRAILING_SPACES = max(
    0, int(os.getenv("TTS_NARRATOR_TRAILING_SPACES", "0").strip() or "0")
)

# TTS voice mapping (speaker profile based)
TTS_NARRATOR_VOICE = os.getenv("TTS_NARRATOR_VOICE", TTS_VOICE)
TTS_MALE_VOICE = os.getenv("TTS_MALE_VOICE", "Puck")
TTS_FEMALE_VOICE = os.getenv("TTS_FEMALE_VOICE", "Kore")
TTS_BOY_VOICE = os.getenv("TTS_BOY_VOICE", TTS_MALE_VOICE)
TTS_GIRL_VOICE = os.getenv("TTS_GIRL_VOICE", TTS_FEMALE_VOICE)
TTS_ELDER_MALE_VOICE = os.getenv("TTS_ELDER_MALE_VOICE", TTS_MALE_VOICE)
TTS_ELDER_FEMALE_VOICE = os.getenv("TTS_ELDER_FEMALE_VOICE", TTS_FEMALE_VOICE)
TTS_ENABLE_STYLE_STEERING = os.getenv("TTS_ENABLE_STYLE_STEERING", "true").lower() == "true"

# Scene transition
SCENE_GAP = 1.15  # 장면 전환 시 무음 갭 (초)

# BGM settings
BGM_ENABLED = os.getenv("BGM_ENABLED", "true").lower() == "true"
BGM_VOLUME = 0.22
EFFECT_VOLUME = 0.8

# Pipeline settings
MAX_CRITIC_REVISIONS = 2
IMAGE_WORKERS = 3
IMAGE_CRITIC_ENABLED = os.getenv("IMAGE_CRITIC_ENABLED", "true").lower() == "true"
IMAGE_CRITIC_MAX_REGENERATIONS = int(os.getenv("IMAGE_CRITIC_MAX_REGENERATIONS", "3"))
MAX_DAILY_UPLOADS = 3
AI_DISCLOSURE = "이 영상은 AI 도구를 활용하여 제작되었습니다."
