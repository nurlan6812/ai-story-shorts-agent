import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"
EFFECTS_DIR = ASSETS_DIR / "effects"
BGM_DIR = ASSETS_DIR / "bgm"
FONTS_DIR = ASSETS_DIR / "fonts"
STYLES_DIR = BASE_DIR / "styles"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_QUEUE_DIR = OUTPUT_DIR / "upload_queue"

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Video settings (YouTube Shorts)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# TTS settings (Gemini TTS)
TTS_VOICE = "Schedar"  # Voice 07
TTS_SPEED = 1.2  # 나레이션 배속 (유머/썰은 좀 더 자연스러운 속도)
TTS_MODEL_PRIMARY = os.getenv("TTS_MODEL_PRIMARY", "gemini-2.5-flash-preview-tts")
TTS_MODEL_FALLBACK = os.getenv("TTS_MODEL_FALLBACK", "gemini-2.5-pro-preview-tts")

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
SCENE_GAP = 1.0  # 장면 전환 시 무음 갭 (초)

# BGM settings
BGM_VOLUME = 0.22
EFFECT_VOLUME = 0.8

# Pipeline settings
MAX_CRITIC_REVISIONS = 2
IMAGE_WORKERS = 3
MAX_DAILY_UPLOADS = 3
AI_DISCLOSURE = "이 영상은 AI 도구를 활용하여 제작되었습니다."
