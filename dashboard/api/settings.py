"""FastAPI 설정."""

import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

RUNTIME_DIR = PROJECT_ROOT / "runtime"
SCHEDULER_LOG_PATH = RUNTIME_DIR / "scheduler.log"
RECOVERY_SCHEDULER_LOG_PATH = RUNTIME_DIR / "scheduler_2.log"
SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler.py"
RECOVERY_SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler_2.py"
MAIN_SCRIPT = PROJECT_ROOT / "main.py"
CAFFEINATE_BIN = shutil.which("caffeinate")


def _resolve_python() -> Path:
    candidates = [
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / "venv" / "bin" / "python",
    ]

    system_python = shutil.which("python3") or shutil.which("python")
    if system_python:
        candidates.append(Path(system_python))

    existing = [candidate for candidate in candidates if candidate.exists()]

    # 스케줄러가 실제로 뜨는 인터프리터를 우선 선택한다.
    for candidate in existing:
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import apscheduler"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3,
            )
            if result.returncode == 0:
                return candidate
        except Exception:
            continue

    if existing:
        return existing[0]

    return Path(system_python or "python3")


VENV_PYTHON = _resolve_python()
