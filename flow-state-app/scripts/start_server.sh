#!/usr/bin/env bash
set -euo pipefail

# start_server.sh
# Installs dependencies and launches the FastAPI server.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Installing Flow State dependencies..."
cd "$APP_ROOT"

if [ ! -d ".venv" ]; then
  uv venv .venv
fi

uv pip install --python "$APP_ROOT/.venv/bin/python" fastapi uvicorn librosa scipy numpy websockets python-multipart

echo "Starting Flow State Web App on port 8000..."
cd "$APP_ROOT/src"
"$APP_ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
