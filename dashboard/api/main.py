"""썰알람 관제 대시보드 — FastAPI 백엔드"""

import settings  # noqa: F401  # sys.path/.env 초기화
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import data, generate, health, logs, scheduler

app = FastAPI(
    title="썰알람 관제 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|\[::1\]|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(generate.router, prefix="/api/generate", tags=["generate"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
