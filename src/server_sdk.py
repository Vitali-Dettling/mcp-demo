#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.0"]
# ///
"""
The SAME server as server.py — 3 tools, 2 resources, 1 prompt — but built on the
OFFICIAL MCP Python SDK (https://py.sdk.modelcontextprotocol.io/) instead of by hand.

Run it:
    uv run server_sdk.py              # stdio (what a host launches)
    uv run mcp dev server_sdk.py      # opens the MCP Inspector UI to poke at it

Compare this file with server.py and you can SEE what the SDK does for you.
Everything server.py wrote by hand — the JSON-RPC envelope, the initialize handshake,
the notifications rule, tools/list & tools/call routing, the content-block result
shape, the stdio read/write loop, the inputSchema dicts — is GONE here. The SDK:

  - generates each tool's JSON Schema from the Python type hints (a:int, b:int),
  - turns the docstring into the tool/resource/prompt description,
  - parses, validates, (de)serializes every request and wraps every result,
  - handles the whole lifecycle (initialize, capability negotiation, notifications),
  - and gives you transports (stdio / streamable-http / sse) by flipping one argument.

So `@mcp.tool()` here == the ~15 hand-written lines per tool in server.py.
"""

import datetime
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-sdk")


# ---- TOOLS (model picks) — schema is inferred from the type hints -----------
@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


@mcp.tool()
def vowel_count(text: str) -> int:
    """Count the vowels (a,e,i,o,u) in a piece of text."""
    return sum(1 for c in text.lower() if c in "aeiou")


@mcp.tool()
def current_time(timezone_note: str = "") -> str:
    """Return the server machine's current local time (ISO 8601)."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    return f"{now} ({timezone_note})" if timezone_note else now


# ---- RESOURCES (app reads) — the URI goes in the decorator ------------------
@mcp.resource("demo://readme")
def readme() -> str:
    """A short note explaining this demo server."""
    return "This is the SDK MCP demo. It exposes 3 tools, 2 resources, and a prompt."


@mcp.resource("demo://server-stats")
def server_stats() -> str:
    """Live counts of what this server offers (computed fresh each read)."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    return f"tools=3 resources=2 prompts=1 time={now}"


# ---- PROMPTS (user picks) — returning a str becomes a user message ----------
@mcp.prompt()
def explain_like_im_five(topic: str) -> str:
    """Produce a message asking for a simple explanation of a topic."""
    return f"Explain {topic} to me like I'm five years old, in 3 sentences."


if __name__ == "__main__":
    mcp.run()  # transport="stdio" by default; pass "streamable-http" to serve remotely
