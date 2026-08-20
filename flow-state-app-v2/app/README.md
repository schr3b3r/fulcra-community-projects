# Flow State - Backend Skeleton

Flow State is a web app for musicians to record long jam sessions and automatically extract musical ideas using audio markers.

This repository contains the backend service built with Python and FastAPI, plus a minimal SvelteKit frontend under `../frontend/` (see below).

> **Note:** DSP processing, marker detection, and Fulcra publishing are intentionally not yet implemented. Audio streaming now has a working minimal slice (see below).

## Getting Started

### Prerequisites

- Python 3.9+
- pip

### Installation

1. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Server

Start the FastAPI development server with uvicorn:

```bash
uvicorn main:app --reload
```

The server will start at `http://127.0.0.1:8000`.

### Endpoints

- `GET /` - Overview of the Flow State backend service
- `GET /health` - Health check endpoint returning `{"status": "ok"}`
- `WS /ws/record/{session_id}` - Streams binary audio chunks to
  `raw/<session_id>.webm`, appended and flushed to disk as each chunk
  arrives. See `features/websocket_audio_streaming.md`.

CORS is enabled for `http://localhost:5173` (the SvelteKit/Vite dev
server's default origin).

## Running the frontend (minimal slice)

A bare-bones SvelteKit page lives in `../frontend/` (sibling to this
`app/` directory, outside the Python sandbox). It has Record/Stop buttons
that capture microphone audio and stream it to this backend's WebSocket
endpoint. To run it:

```bash
cd ../frontend
npm install   # first time only
npm run dev
```

Then open `http://localhost:5173` with the FastAPI server (above) also
running. See `features/recording_frontend.md` for the full spec and
current status of this feature.

