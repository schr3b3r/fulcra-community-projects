"""
Gemini provider adapter.

This module is the ONLY place in the harness that should know anything about
Google's SDK shapes (message roles, response objects, etc.). Everything else
in the harness — the control loop, tools, prompts — talks to the normalized
`ModelResponse` / message-dict interface defined here, not to the Gemini SDK
directly.

Normalized message format (what callers pass in):
    [{"role": "user", "content": "..."},
     {"role": "assistant", "content": "..."}, ...]

Gemini's SDK uses "user" / "model" instead of "user" / "assistant", and
expects `Content` objects rather than plain dicts — that translation happens
entirely inside `call_model`.

No tool-calling yet — this is deliberately the smallest possible slice: plain
text in, plain text out, but already speaking in the shape the rest of the
harness will use once tools are added.
"""

from dataclasses import dataclass, field
import os

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.6-flash"


@dataclass
class ModelResponse:
    """Normalized result of a single call to the model.

    `tool_calls` is unused for now (always empty) — it's here so the shape
    doesn't need to change again once we add tool support later.
    """
    text: str | None
    tool_calls: list = field(default_factory=list)
    stop_reason: str | None = None


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Load it from .env before calling "
            "the harness (see harness/providers/gemini.py docstring)."
        )
    return genai.Client(api_key=api_key)


def _to_gemini_contents(messages: list[dict]) -> list[types.Content]:
    """Translate our normalized message list into Gemini's Content objects."""
    role_map = {"user": "user", "assistant": "model"}
    contents = []
    for msg in messages:
        role = role_map.get(msg["role"])
        if role is None:
            raise ValueError(f"Unsupported message role: {msg['role']!r}")
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg["content"])])
        )
    return contents


def call_model(
    messages: list[dict],
    system_prompt: str = "",
    model: str = DEFAULT_MODEL,
) -> ModelResponse:
    """Send a conversation to Gemini and return a normalized response.

    Args:
        messages: normalized message history, e.g.
            [{"role": "user", "content": "hello"}]
        system_prompt: optional system instruction for this call.
        model: which Gemini model to use.

    Returns:
        ModelResponse with the model's reply text.
    """
    client = _get_client()
    contents = _to_gemini_contents(messages)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    return ModelResponse(
        text=response.text,
        tool_calls=[],
        stop_reason=getattr(response.candidates[0], "finish_reason", None)
        if response.candidates else None,
    )
