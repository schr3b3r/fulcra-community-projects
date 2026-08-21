"""
The control loop: the "agent" part of the agent harness.

This is intentionally the smallest possible version that does real work:

  1. Send the conversation so far to the model (via the provider adapter).
  2. If the model's response includes tool calls, execute each one (via the
     tool registry) and feed the results back in as new messages.
  3. Repeat until the model responds with plain text and no further tool
     calls (i.e. it considers the task done), or a stop condition is hit.

Stop conditions, deliberately explicit rather than "loop forever":
  - MAX_ITERATIONS reached (guards against runaway loops).
  - The model produces a turn with no tool calls (natural completion).

Everything here is provider-agnostic at the call_model boundary — this file
does not know Gemini exists. If you ever add a second provider, only the
`provider` argument's target module changes, not this loop.

This file is 100% project-agnostic. It has no knowledge of what app is
being built — that lives entirely in the system prompt and app/CONTEXT.md,
both of which are loaded by harness/prompts/__init__.py. You should not
need to edit this file when scaffolding a new project with this starter
kit; if you find yourself wanting to, it's a sign the change belongs in
the system prompt or a tool instead.
"""

from dataclasses import dataclass, field

from harness.providers.gemini import call_model
from harness.prompts import load_app_context, load_system_prompt
from harness.tools import ALL_TOOLS


MAX_ITERATIONS = 10


@dataclass
class RunResult:
    """What a completed (or stopped) run produced."""
    final_text: str | None
    messages: list[dict] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = "completed"  # "completed" | "max_iterations"


def run(
    task: str,
    system_prompt: str | None = None,
    tools: dict | None = None,
    max_iterations: int = MAX_ITERATIONS,
    include_app_context: bool = True,
    verbose: bool = True,
) -> RunResult:
    """Run the agent loop on a single task until it finishes or stalls out.

    Args:
        task: the user's task description, becomes the first user message.
        system_prompt: instructions for the model, sent on every call. If
            None (the default), loads harness/prompts/system_prompt.md.
        tools: a {name: (callable, schema)} registry. If None (the default),
            uses the full harness.tools.ALL_TOOLS registry. Pass an empty
            dict explicitly ({}) for plain chat mode with no tools at all.
        max_iterations: hard cap on model round-trips, to prevent runaway
            loops.
        include_app_context: if True (the default), automatically prepends
            the contents of app/CONTEXT.md (if it exists) to the task, so
            every task starts with the app's accumulated architectural
            memory without needing to be repeated by hand in every task
            prompt. Set False to opt out (e.g. for smoke tests, which
            intentionally test in isolation).
        verbose: print progress as it happens.

    Returns:
        A RunResult with the final text and the full message transcript.
    """
    if system_prompt is None:
        system_prompt = load_system_prompt()
    if tools is None:
        tools = ALL_TOOLS

    if include_app_context:
        context = load_app_context()
        if context:
            task = (
                "# App context (app/CONTEXT.md — read this first)\n\n"
                f"{context}\n\n"
                "# Your task\n\n"
                f"{task}"
            )
            if verbose:
                print("[loop] prepended app/CONTEXT.md to the task")

    messages: list[dict] = [{"role": "user", "content": task}]

    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"\n[loop] iteration {iteration}/{max_iterations}")

        response = call_model(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
        )

        if not response.tool_calls:
            # Natural completion: the model answered without asking for a
            # tool. Record its reply and stop.
            messages.append({"role": "assistant", "content": response.text or ""})
            if verbose:
                print(f"[loop] model finished (no tool calls): {response.text!r}")
            return RunResult(
                final_text=response.text,
                messages=messages,
                iterations=iteration,
                stopped_reason="completed",
            )

        # The model wants to use one or more tools. Record its turn using
        # the REAL structured shape (content + tool_calls), matching what
        # Gemini actually produced — not a narrated text summary. An earlier
        # version narrated tool calls as plain strings, and the model would
        # later imitate that literal phrasing as output text instead of
        # performing real actions, since the history didn't structurally
        # match anything it had really done.
        messages.append(
            {
                "role": "assistant",
                "content": response.text,
                "tool_calls": response.tool_calls,
            }
        )
        for call in response.tool_calls:
            name = call["name"]
            args = call.get("args", {})
            if verbose:
                print(f"[loop] tool call: {name}({args})")

            if name not in tools:
                result = f"ERROR: unknown tool {name!r}"
            else:
                func, _schema = tools[name]
                try:
                    result = func(**args)
                except Exception as exc:  # noqa: BLE001 - deliberately broad;
                    # tool failures should be fed back to the model as text,
                    # not crash the whole run.
                    result = f"ERROR: {exc}"

            if verbose:
                print(f"[loop] tool result: {result!r}")

            messages.append({"role": "tool", "name": name, "content": str(result)})

    if verbose:
        print(f"[loop] stopped: hit max_iterations ({max_iterations})")
    return RunResult(
        final_text=None,
        messages=messages,
        iterations=max_iterations,
        stopped_reason="max_iterations",
    )
