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

Tool-calling: callers pass `tools` as our own registry format —
    {"tool_name": (callable, schema_dict), ...}
(see harness/tools/filesystem.py) — where `schema_dict` looks like:
    {"name": ..., "description": ..., "parameters": {<JSON schema>}}
This adapter translates that into Gemini's `FunctionDeclaration`/`Tool`
objects, and translates any function-call parts in the response back into
our normalized `tool_calls` list:
    [{"name": "read_file", "args": {"path": "main.py"}}, ...]
The control loop never sees Gemini's native types on either side of the call.
"""

from dataclasses import dataclass, field
import os

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.6-flash"


@dataclass
class ModelResponse:
    """Normalized result of a single call to the model.

    `tool_calls` is a list of {"name": str, "args": dict} — empty if the
    model didn't ask to call anything this turn.
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


def _to_gemini_tools(tools: dict | None) -> list[types.Tool] | None:
    """Translate our {name: (callable, schema)} registry into Gemini Tools."""
    if not tools:
        return None
    declarations = []
    for _name, (_func, schema) in tools.items():
        declarations.append(
            types.FunctionDeclaration(
                name=schema["name"],
                description=schema.get("description", ""),
                parameters=schema.get("parameters"),
            )
        )
    return [types.Tool(function_declarations=declarations)]


def call_model(
    messages: list[dict],
    system_prompt: str = "",
    model: str = DEFAULT_MODEL,
    tools: dict | None = None,
) -> ModelResponse:
    """Send a conversation to Gemini and return a normalized response.

    Args:
        messages: normalized message history, e.g.
            [{"role": "user", "content": "hello"}]
        system_prompt: optional system instruction for this call.
        model: which Gemini model to use.
        tools: optional {name: (callable, schema)} registry (see
            harness/tools/filesystem.py). If provided, the model may request
            calls to these tools instead of (or alongside) returning text.

    Returns:
        ModelResponse with the model's reply text and/or requested tool
        calls.
    """
    client = _get_client()
    contents = _to_gemini_contents(messages)
    gemini_tools = _to_gemini_tools(tools)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
        tools=gemini_tools,
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    tool_calls = []
    if response.candidates:
        for part in response.candidates[0].content.parts or []:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                tool_calls.append({"name": fc.name, "args": dict(fc.args or {})})

    return ModelResponse(
        text=response.text if not tool_calls else None,
        tool_calls=tool_calls,
        stop_reason=getattr(response.candidates[0], "finish_reason", None)
        if response.candidates else None,
    )
