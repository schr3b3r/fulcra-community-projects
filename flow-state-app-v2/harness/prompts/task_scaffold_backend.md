# Task: Scaffold the Flow State backend skeleton

## Context
Flow State is a web app for musicians to record long jam sessions. Instead
of clicking a button to save an idea, they play an "audio marker" (e.g. a
specific chord). A background DSP worker finds that marker and extracts a
30-second clip, tags it with Key and BPM, and pushes it to a data platform
as a "MusicalIdea".

The backend is Python FastAPI. Audio is streamed from the browser to the
backend over WebSockets in 2-second chunks (not buffered client-side, so a
browser crash doesn't lose the recording).

## Your task right now
Do NOT implement DSP, audio processing, or any external data platform
integration yet — this step is purely about scaffolding a minimal, runnable
backend skeleton to build on later. Specifically:

1. Create `main.py`: a minimal FastAPI app with:
   - A `GET /health` endpoint that returns a JSON object indicating the
     service is up (e.g. `{"status": "ok"}`).
   - A `GET /` endpoint that returns a short JSON description of what this
     app is (mention it's the Flow State backend).
2. Create `requirements.txt` listing the minimal dependencies needed to run
   `main.py` (at least `fastapi` and `uvicorn`).
3. Create `README.md` briefly explaining what this skeleton is, how to run
   it, and that audio streaming / DSP / marker detection are intentionally
   not yet implemented.

Keep it minimal and correct rather than elaborate. When you're done, give a
short summary of the files you created.
