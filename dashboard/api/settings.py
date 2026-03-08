"""FastAPI 설정 — 기존 youtube_auto 모듈 재사용을 위한 경로 설정"""

import sys
from pathlib import Path

# 프로젝트 루트 (youtube_auto/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 기존 tools/ 모듈을 import 하기 위해 sys.path 에 프로젝트 루트 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env 로드 (기존 설정과 동일)
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

SCHEDULER_LOG_PATH = PROJECT_ROOT / "scheduler.log"
SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler.py"
MAIN_SCRIPT = PROJECT_ROOT / "main.py"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
