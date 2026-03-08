#!/bin/bash
# 썰알람 관제 대시보드 — 동시 실행 스크립트
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

cleanup() {
  echo ""
  echo "[Dashboard] 종료 중..."
  kill $FASTAPI_PID $NEXTJS_PID 2>/dev/null
  wait $FASTAPI_PID $NEXTJS_PID 2>/dev/null
  echo "[Dashboard] 종료 완료"
}
trap cleanup EXIT INT TERM

echo "============================================"
echo "  썰알람 · 관제 대시보드"
echo "============================================"

# FastAPI 백엔드 (포트 8002)
echo "[Dashboard] FastAPI 시작 (port 8002)..."
cd "$SCRIPT_DIR/api"
$VENV_PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload &
FASTAPI_PID=$!

# Next.js 프론트엔드 (포트 3002)
echo "[Dashboard] Next.js 시작 (port 3002)..."
cd "$SCRIPT_DIR/web"
npm run dev -- -p 3002 &
NEXTJS_PID=$!

echo ""
echo "[Dashboard] 프론트엔드: http://localhost:3002"
echo "[Dashboard] API 문서:   http://localhost:8002/docs"
echo ""

wait
