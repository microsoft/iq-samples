#!/usr/bin/env bash
set -e

# Kill both child processes on exit (Ctrl+C, SIGTERM, etc.)
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Start backend
cd "$ROOT/backend"
"$ROOT/.venv/bin/python3" -m uvicorn main:app --reload &
BACKEND_PID=$!

# Start frontend
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend  (PID $BACKEND_PID) → http://localhost:8000"
echo "Frontend (PID $FRONTEND_PID) → http://localhost:5173"
echo "Press Ctrl+C to stop both."
echo ""

# Wait for either process to exit
wait
