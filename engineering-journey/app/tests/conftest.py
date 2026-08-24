"""Pytest configuration for the app/tests/ suite.

Loads the project's .env file (for GEMINI_API_KEY, and any other
runtime config tests may need) before any test module imports code that
depends on it -- e.g. rollup.py's real-LLM-call summarization path.

This matters because the harness's own git_commit test gate (see
harness/tools/git_tool.py) invokes `python -m pytest` directly, NOT
harness/run_task.py -- so run_task.py's own `load_dotenv()` call never
runs when tests execute through that gate (or when a developer runs
`pytest` directly from app/, which the ENGINEERING_STANDARDS.md testing
section explicitly recommends). Without this, any test exercising a
real Gemini call would silently hit rollup.py's `except Exception`
fallback (GEMINI_API_KEY not set) and produce boilerplate text instead
of a real summary, passing for the wrong reason -- found and fixed
during Milestone 4 when the "real data" rollup test's LLM narrative
assertion passed against fallback boilerplate instead of a real
generated summary.
"""

from dotenv import load_dotenv

load_dotenv()
