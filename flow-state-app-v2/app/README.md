# Flow State - Backend Skeleton

Flow State is a web app for musicians to record long jam sessions and automatically extract musical ideas using audio markers.

This repository contains the backend service built with Python and FastAPI.

> **Note:** Audio streaming (WebSockets), DSP processing, and marker detection are intentionally not yet implemented in this initial skeleton.

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
