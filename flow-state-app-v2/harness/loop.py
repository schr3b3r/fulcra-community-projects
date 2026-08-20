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
does not know Gemini exists. If we ever add a second provider, only the
`provider` argument's target module changes, not this loop.
"""

from dataclasses import dataclass, field

from harness.providers.gemini import call_model
from harness.prompts import load_system_prompt
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
        verbose: print progress as it happens.

    Returns:
        A RunResult with the final text and the full message transcript.
    """
    if system_prompt is None:
        system_prompt = load_system_prompt()
    if tools is None:
        tools = ALL_TOOLS
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

        # The model wants to use one or more tools. Execute each, then loop
        # back around so the model can see the results and continue.
        # Important: record what the model actually decided to do (not an
        # empty string) so its own history reflects the tool call it made —
        # otherwise, on the next round-trip, it sees a "tool result" with no
        # memory of having asked for it, and tends to just repeat the
        # original request from scratch.
        call_descriptions = ", ".join(
            f"{c['name']}({c.get('args', {})})" for c in response.tool_calls
        )
        messages.append(
            {
                "role": "assistant",
                "content": response.text or f"[calling tool(s): {call_descriptions}]",
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

            messages.append(
                {"role": "user", "content": f"[tool result for {name}]: {result}"}
            )

    if verbose:
        print(f"[loop] stopped: hit max_iterations ({max_iterations})")
    return RunResult(
        final_text=None,
        messages=messages,
        iterations=max_iterations,
        stopped_reason="max_iterations",
    )
