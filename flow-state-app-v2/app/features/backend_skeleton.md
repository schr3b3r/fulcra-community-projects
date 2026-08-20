# Feature: Backend Skeleton

## Status
done

## Description
A minimal, runnable FastAPI backend to build all other features on top of.
Deliberately excludes any audio, DSP, or data-platform logic — just proves
the service runs and can be health-checked.

## Acceptance Criteria
- [x] `GET /health` returns a JSON object indicating the service is up.
- [x] `GET /` returns a short JSON description identifying this as the Flow
      State backend.
- [x] `requirements.txt` lists the minimal dependencies (fastapi, uvicorn).
- [x] Server actually starts and both endpoints were verified live (not
      just claimed) via a real HTTP request.

## Dependencies
none

## Notes
Built via the harness's first real (non-smoke-test) task run. Verified by
independently installing requirements and curling both endpoints.
