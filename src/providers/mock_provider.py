"""
MockProvider — Demo Video Recording Mode
=========================================
Returns pre-scripted, polished responses with realistic delays.
No API calls, no rate limits, no failures. Perfect for demos.

Usage:
    nexus-agent --provider mock --verbose
    nexus-agent chat "..." --provider mock --verbose
"""
import time
import uuid
from typing import Any, Dict, List

from .base import BaseProvider, ProviderResponse, Tool, ToolCall


# ---------------------------------------------------------------------------
# Artificial delay config (seconds)
# ---------------------------------------------------------------------------
THINK_DELAY   = 1.8   # pause before first response (simulates "thinking")
TOOL_DELAY    = 0.6   # pause after each tool call result (simulates execution)
WRITE_DELAY   = 0.9   # longer pause for write_file (simulates file I/O)


# ---------------------------------------------------------------------------
# Pre-scripted responses — edit these to perfect your demo script
# ---------------------------------------------------------------------------

REVIEW_TOOL_CALL = {
    "name": "read_file",
    "args": {"path": "demo_review.py"},
    "thinking": "I need to read the file first to understand its contents.",
}

REVIEW_FINAL_TEXT = """\
Here's my code review for `demo_review.py`:

**Issues Found:**

1. **No type hints** — The function signature `add(a, b)` doesn't specify types.
   Without type hints, static analysis tools like mypy can't catch bugs early.

2. **No docstring** — There's no documentation explaining what the function does,
   what its parameters are, or what it returns.

3. **No input validation** — Passing non-numeric types will raise a `TypeError`
   at runtime with no clear error message.

**Recommended Fix:**

```python
def add(a: int | float, b: int | float) -> int | float:
    \"\"\"Return the sum of two numbers.

    Args:
        a: The first number.
        b: The second number.

    Returns:
        The arithmetic sum of a and b.
    \"\"\"
    return a + b
```

**Overall:** Functionally correct, but not production-ready. The above changes
would make it pass a proper code review."""


DEBUG_TOOL_CALL_READ = {
    "name": "read_file",
    "args": {"path": "demo_bug.py"},
    "thinking": "Let me read the file to understand the bug.",
}

DEBUG_TOOL_CALL_WRITE = {
    "name": "write_file",
    "args": {
        "path": "demo_bug.py",
        "content": (
            "def calculate_average(numbers: list[float]) -> float:\n"
            "    \"\"\"Return the average of a list of numbers.\n\n"
            "    Returns 0.0 for an empty list to avoid ZeroDivisionError.\n"
            "    \"\"\"\n"
            "    if not numbers:\n"
            "        return 0.0\n"
            "    return sum(numbers) / len(numbers)\n\n\n"
            "print(calculate_average([]))\n"
        ),
    },
    "thinking": "The bug is clear — division by zero when the list is empty. I'll add a guard clause.",
}

DEBUG_FINAL_TEXT = """\
**Root Cause:** `ZeroDivisionError` on line 5.

When `calculate_average([])` is called with an empty list, `len(numbers)` is `0`,
causing `total / len(numbers)` to raise `ZeroDivisionError: division by zero`.

**Fix Applied:** Added an early return guard at the top of the function:

```python
if not numbers:
    return 0.0
```

This safely handles the empty list case and returns `0.0` instead of crashing.
The file has been updated. You can run it again to verify — no errors."""


COMMIT_FINAL_TEXT = "fix: add guard clause for empty list in calculate_average"


MENTION_FINAL_TEXT = """\
`pyproject.toml` is the **modern Python project configuration file** (PEP 517/518).

It serves three main purposes for this project:

**1. Build System** — Declares `setuptools` as the build backend:
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

**2. Package Metadata** — Defines the project name (`nexus-agent`), version
(`2.2.1`), Python requirement (`>=3.11`), and all dependencies like `typer`,
`rich`, `anthropic`, `openai`, and `google-genai`.

**3. CLI Entry Points** — Registers the terminal commands:
```toml
[project.scripts]
nexus-agent = "src.cli.app:app"
agent       = "src.cli.app:app"
```
This is why you can run `nexus-agent` directly in your terminal after
`pip install -e .`."""


FALLBACK_TEXT = """\
I'm Nexus-Agent, your autonomous AI coding assistant.

I can help you with:
- **Reviewing code** — `review <file.py>`
- **Debugging errors** — `debug <file.py> --error "..."`
- **Generating code** — `generate "..." --output file.py`
- **AI git commits** — `commit`
- **General questions** — just ask!

What would you like to work on?"""


# ---------------------------------------------------------------------------
# Scenario detection helpers
# ---------------------------------------------------------------------------

def _last_user_message(messages: List[Dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "").lower()
            if isinstance(content, str):
                return content.lower()
    return ""


def _has_tool_result(messages: List[Dict[str, Any]]) -> bool:
    """True if the last assistant turn already triggered a tool and we have the result."""
    for m in reversed(messages):
        role = m.get("role", "")
        if role == "tool":
            return True
        if role == "user":
            break
    return False


def _tool_result_count(messages: List[Dict[str, Any]]) -> int:
    """Count how many tool result messages are in the current turn."""
    count = 0
    for m in reversed(messages):
        role = m.get("role", "")
        if role == "tool":
            count += 1
        elif role == "user" and count > 0:
            break
    return count


def _make_tool_call(tc: Dict[str, Any]) -> ToolCall:
    return ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=tc["name"], args=tc["args"])


def _make_raw_tool_call(tc: ToolCall) -> Dict[str, Any]:
    import json
    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
    }


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

class MockProvider(BaseProvider):
    """Scripted demo provider. Returns pre-written responses with delays."""

    model = "mock-demo-v1"

    def complete(self, messages: List[Dict[str, Any]], tools: List[Tool], system: str) -> ProviderResponse:
        last = _last_user_message(messages)
        tool_results_so_far = _tool_result_count(messages)

        # ---- COMMIT scenario (check first — git diff may contain other keywords) -----
        # The commit command always sends a query starting with "here is the git diff:"
        if "here is the git diff" in last or (
            "generate" in last and "conventional commit" in last
        ):
            time.sleep(THINK_DELAY)
            return ProviderResponse(
                text=COMMIT_FINAL_TEXT,
                raw_assistant_message={"role": "assistant", "content": COMMIT_FINAL_TEXT},
                input_tokens=410, output_tokens=18,
            )

        # ---- REVIEW scenario ------------------------------------------------
        if "demo_review.py" in last or (
            "review" in last and "demo_review" in last
        ) or ("add(a,b)" in last or "add(a, b)" in last):

            if tool_results_so_far == 0:
                # Step 1: request read_file
                time.sleep(THINK_DELAY)
                tc = _make_tool_call(REVIEW_TOOL_CALL)
                raw_msg = {
                    "role": "assistant",
                    "content": REVIEW_TOOL_CALL["thinking"],
                    "tool_calls": [_make_raw_tool_call(tc)],
                }
                return ProviderResponse(
                    text=REVIEW_TOOL_CALL["thinking"],
                    tool_calls=[tc],
                    raw_assistant_message=raw_msg,
                    input_tokens=312, output_tokens=28,
                )
            else:
                # Step 2: return final review
                time.sleep(TOOL_DELAY)
                return ProviderResponse(
                    text=REVIEW_FINAL_TEXT,
                    raw_assistant_message={"role": "assistant", "content": REVIEW_FINAL_TEXT},
                    input_tokens=520, output_tokens=218,
                )

        # ---- DEBUG scenario -------------------------------------------------
        if "demo_bug.py" in last or "zerodivision" in last or "division by zero" in last or (
            "calculate_average" in last
        ):
            if tool_results_so_far == 0:
                # Step 1: read_file
                time.sleep(THINK_DELAY)
                tc = _make_tool_call(DEBUG_TOOL_CALL_READ)
                raw_msg = {
                    "role": "assistant",
                    "content": DEBUG_TOOL_CALL_READ["thinking"],
                    "tool_calls": [_make_raw_tool_call(tc)],
                }
                return ProviderResponse(
                    text=DEBUG_TOOL_CALL_READ["thinking"],
                    tool_calls=[tc],
                    raw_assistant_message=raw_msg,
                    input_tokens=298, output_tokens=22,
                )
            elif tool_results_so_far == 1:
                # Step 2: write_file with fix
                time.sleep(TOOL_DELAY)
                tc = _make_tool_call(DEBUG_TOOL_CALL_WRITE)
                raw_msg = {
                    "role": "assistant",
                    "content": DEBUG_TOOL_CALL_WRITE["thinking"],
                    "tool_calls": [_make_raw_tool_call(tc)],
                }
                return ProviderResponse(
                    text=DEBUG_TOOL_CALL_WRITE["thinking"],
                    tool_calls=[tc],
                    raw_assistant_message=raw_msg,
                    input_tokens=480, output_tokens=95,
                )
            else:
                # Step 3: final explanation
                time.sleep(WRITE_DELAY)
                return ProviderResponse(
                    text=DEBUG_FINAL_TEXT,
                    raw_assistant_message={"role": "assistant", "content": DEBUG_FINAL_TEXT},
                    input_tokens=590, output_tokens=165,
                )

        # ---- @mention pyproject.toml ----------------------------------------
        if "pyproject.toml" in last:
            time.sleep(THINK_DELAY)
            return ProviderResponse(
                text=MENTION_FINAL_TEXT,
                raw_assistant_message={"role": "assistant", "content": MENTION_FINAL_TEXT},
                input_tokens=380, output_tokens=142,
            )

        # ---- Fallback for any other message ---------------------------------
        time.sleep(THINK_DELAY)
        return ProviderResponse(
            text=FALLBACK_TEXT,
            raw_assistant_message={"role": "assistant", "content": FALLBACK_TEXT},
            input_tokens=210, output_tokens=88,
        )

    def stream(self, messages: List[Dict[str, Any]], tools: List[Tool], system: str) -> Any:
        """For mock mode, stream just yields the complete() response text."""
        response = self.complete(messages, tools, system)
        if response.text:
            yield response.text

    def format_tool_result_message(self, tool_call_id: str, result: str) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": str(result),
        }
