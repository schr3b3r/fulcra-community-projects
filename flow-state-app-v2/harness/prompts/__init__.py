"""
Loads prompt text (system prompt, and later any templated task prompts) from
the harness/prompts/ directory, so prompt content lives in plain
markdown/text files rather than being embedded as Python string literals.
This keeps prompt iteration decoupled from code changes.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def load_system_prompt() -> str:
    """Load the default system prompt for the Flow State build agent."""
    return (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
