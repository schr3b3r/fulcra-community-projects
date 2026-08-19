#!/bin/bash

# start_server.sh
# Installs dependencies and launches the FastAPI server.

echo "Installing Flow State dependencies..."
uv pip install fastapi uvicorn librosa scipy numpy

echo "Starting Flow State Web App on port 8000..."
cd src
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
