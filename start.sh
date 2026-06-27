#!/usr/bin/env bash
set -e

echo "============================================"
echo "  Unified Yi Character Manager"
echo "  Starting server..."
echo "============================================"
echo ""

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# ─── Kill existing server on port 8080 ───
echo "[1/3] Checking for existing server on port 8080..."

PID=$(lsof -ti :8080 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "  Found process PID $PID on port 8080, killing..."
  kill -9 "$PID" 2>/dev/null || true
  echo "  Killed PID $PID"
fi

# Also kill any uvicorn processes (extra safety)
UVID=$(pgrep -f uvicorn 2>/dev/null || true)
if [ -n "$UVID" ]; then
  echo "  Found uvicorn process, killing..."
  pkill -f uvicorn 2>/dev/null || true
fi

# Wait a moment for port to free
sleep 2
echo "  Port 8080 is clear."
echo ""

# ─── Activate venv if exists ───
if [ -f "$DIR/.venv/bin/activate" ]; then
  source "$DIR/.venv/bin/activate"
fi

# ─── Install dependencies ───
echo "[2/3] Installing Python dependencies..."
python3 -m pip install -q -r src/backend/requirements.txt 2>/dev/null || \
python  -m pip install -q -r src/backend/requirements.txt
echo "  Dependencies ready."
echo ""

# ─── Start server ───
echo "[3/3] Starting backend server at http://localhost:8080"
echo ""
echo "  Frontend:  http://localhost:8080"
echo "  Align:     http://localhost:8080/align.html"
echo "  API Docs:  http://localhost:8080/docs"
echo ""
echo "  Press Ctrl+C to stop."
echo "============================================"
echo ""

python3 src/backend/main.py 2>/dev/null || python src/backend/main.py
