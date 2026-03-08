"""썰알람 관제 대시보드 — FastAPI 백엔드"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import health, scheduler, generate, logs

app = FastAPI(
    title="썰알람 관제 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(generate.router, prefix="/api/generate", tags=["generate"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
