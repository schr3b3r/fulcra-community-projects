"""
Gemini provider adapter.

This module is the ONLY place in the harness that should know anything about
Google's SDK shapes (message roles, response objects, etc.). Everything else
in the harness — the control loop, tools, prompts — talks to the normalized
`ModelResponse` / message-dict interface defined here, not to the Gemini SDK
directly. This isolation is what lets you swap providers later (OpenAI,
Anthropic, etc.) by adding a new adapter module with the same call_model
signature, without touching loop.py, tools/, or prompts/.

Normalized message format (what callers pass in) — three message shapes:
    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "..." | None, "tool_calls": [...]}
    {"role": "tool", "name": "read_file", "content": "..."}

The "assistant" shape's `tool_calls` (optional, list of
{"name": str, "args": dict}) and the dedicated "tool" role exist because
Gemini (like most tool-calling APIs) has a REAL structured concept of "the
model called a function" and "here is that function's result" — these are
not just text. An earlier version of this pattern flattened tool calls and
results into plain narrated strings inside ordinary text turns. That broke
down almost immediately: the model would later pattern-match and literally
imitate that narration as output text instead of performing real actions,
because the history it was shown didn't structurally match anything it had
really produced. Preserving the real structure fixes this at the root — if
you ever build a different provider adapter, preserve this same discipline.

Gemini's SDK uses "user" / "model" instead of "user" / "assistant", and
expects `Content` objects (with typed `Part`s) rather than plain dicts —
that translation happens entirely inside `call_model`.

Tool-calling: callers pass `tools` as our own registry format —
    {"tool_name": (callable, schema_dict), ...}
(see harness/tools/filesystem.py) — where `schema_dict` looks like:
    {"name": ..., "description": ..., "parameters": {<JSON schema>}}
This adapter translates that into Gemini's `FunctionDeclaration`/`Tool`
objects, and translates any function-call parts in the response back into
our normalized `tool_calls` list:
    [{"name": "read_file", "args": {"path": "main.py"}, "thought_signature": ...}, ...]
The control loop never sees Gemini's native types on either side of the call.

Note on `thought_signature`: Gemini attaches an opaque reasoning-trace
marker to function_call parts. It MUST be captured from the response and
replayed verbatim if that same function call is ever sent back as history
(e.g. in a multi-turn tool-use loop) — omitting it causes a
400 INVALID_ARGUMENT error on the next call. We carry it through our
tool_calls dicts for exactly this reason; nothing outside this file needs to
understand what it means, only pass it along.
"""

from dataclasses import dataclass, field
import os

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.6-flash"


@dataclass
class ModelResponse:
    """Normalized result of a single call to the model.

    `tool_calls` is a list of {"name": str, "args": dict,
    "thought_signature": ...} — empty if the model didn't ask to call
    anything this turn.
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
    """Translate our normalized message list into Gemini's Content objects.

    Handles all three normalized shapes (user text, assistant text/tool
    calls, tool results) by emitting the structurally-correct Gemini Part
    type for each, rather than collapsing everything to Part(text=...).
    """
    contents = []
    for msg in messages:
        role = msg["role"]

        if role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part(text=msg["content"])])
            )

        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append(types.Part(text=msg["content"]))
            for call in msg.get("tool_calls", []):
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=call["name"], args=call.get("args", {})
                        ),
                        # Must be replayed verbatim or Gemini rejects later
                        # turns in a multi-step tool-use conversation (see
                        # module docstring).
                        thought_signature=call.get("thought_signature"),
                    )
                )
            contents.append(types.Content(role="model", parts=parts))

        elif role == "tool":
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=msg["name"],
                                response={"result": msg["content"]},
                            )
                        )
                    ],
                )
            )

        else:
            raise ValueError(f"Unsupported message role: {msg['role']!r}")

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
        messages: normalized message history — see module docstring for the
            three supported shapes (user / assistant / tool).
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
                tool_calls.append(
                    {
                        "name": fc.name,
                        "args": dict(fc.args or {}),
                        "thought_signature": getattr(part, "thought_signature", None),
                    }
                )

    return ModelResponse(
        text=response.text if not tool_calls else None,
        tool_calls=tool_calls,
        stop_reason=getattr(response.candidates[0], "finish_reason", None)
        if response.candidates else None,
    )
