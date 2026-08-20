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
- [ ] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes. **Known debt**: this feature predates the
      "every feature has automated tests" standard and currently has none.
      Should be backfilled with a basic pytest test (e.g. via FastAPI's
      TestClient) the next time this feature is touched, rather than
      retroactively marking this criterion done without real tests.

## Dependencies
none

## Notes
Built via the harness's first real (non-smoke-test) task run. Verified by
independently installing requirements and curling both endpoints.

Status remains `done` despite the missing test criterion above — the
feature genuinely works and was verified live, but the testing standard
was introduced after this feature was built. Left as visible, honest debt
rather than silently checked off.
