# Flow State v2: Project Context & Architecture

This document is the durable memory for this app, maintained by the agent
itself across tasks. Read this before starting any new task. Update it
whenever you make an architectural decision, pivot, or complete a
significant milestone — so the next task (run by you or a future agent) has
accurate context without needing to re-derive it from the diff history.

This project is independent: it does not reference or depend on any other
app's code, files, or context. Record all decisions relevant to this app
here.

## The Product
A web app for musicians to record long jam sessions. Instead of clicking a
button to save an idea, they play an "audio marker" (e.g. a specific
chord). A background DSP worker finds that marker and extracts a 30-second
clip, tags it with Key and BPM, and pushes it to a data platform as a
"MusicalIdea".

## Current State
- `main.py`: minimal FastAPI app with `GET /` and `GET /health`.
- `requirements.txt`: fastapi, uvicorn.
- No audio streaming, DSP, marker detection, or data platform integration
  yet — these are all still ahead.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(initial)** Scaffolded a minimal FastAPI skeleton with health-check and
  root endpoints, deliberately deferring all audio/DSP/data-platform work.
