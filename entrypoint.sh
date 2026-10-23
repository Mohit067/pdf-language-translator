#!/bin/sh
set -e

echo "=========================================================="
echo " Starting AI4Bharat IndicTrans2 Document Translation Studio "
echo "=========================================================="

# Start Python FastAPI backend in the background
echo "[1/2] Starting FastAPI backend on port 8000..."
cd /app
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend service to initialize..."
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" 2>/dev/null; do
    sleep 1
done
echo "Backend is live and healthy!"

# Start Next.js frontend on port 3000
echo "[2/2] Starting Next.js frontend on port 3000..."
cd /app/frontend
if [ -f "/app/frontend/server.js" ]; then
    PORT=3000 HOSTNAME=0.0.0.0 node /app/frontend/server.js &
else
    npm run start -- -p 3000 -H 0.0.0.0 &
fi
FRONTEND_PID=$!

echo "=========================================================="
echo " TransDoc is ready!"
echo " Web UI:     http://localhost:3000"
echo " Backend:    http://localhost:8000"
echo " API Docs:   http://localhost:8000/docs"
echo "=========================================================="

# Trap signals for graceful shutdown
trap "kill -TERM $BACKEND_PID $FRONTEND_PID 2>/dev/null" SIGINT SIGTERM
wait
