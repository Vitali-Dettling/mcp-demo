#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic>=0.40"]
# ///
"""
The REAL agent: host.py with the print() swapped for an actual Claude model.

Run it with uv (handles the modern Python + the anthropic SDK automatically):
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run agent.py "what is 123 + 456, and how many vowels are in 'elephant'?"

What changed vs host.py — ONLY the decision-maker:
    host.py : a hardcoded line decided to call add(21, 21).
    agent.py: the MODEL reads the tool descriptions (from tools/list) and
              decides which tools to call, with what arguments, and when to stop.

Everything about the SERVER is identical. That's the whole point of MCP:
one server, swappable hosts. The agent is just an adapter sitting between
the MCP server (speaks MCP / JSON-RPC) and the model (speaks the Messages API).
"""

import subprocess
import json
import sys
import os
import anthropic

MODEL = "claude-opus-5-5"  # the skill's default model

# server.py lives next to this file — resolve it so we can run from any cwd.
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

# ---- The MCP client half (identical plumbing to host.py) -------------------
proc = subprocess.Popen(
    ["python3", SERVER],   # the server is stdlib-only, so any python3 runs it
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1,
)
_id = 0
def rpc(method, params=None, notify=False):
    global _id
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        _id += 1
        msg["id"] = _id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    return json.loads(proc.stdout.readline())

rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}})
rpc("notifications/initialized", notify=True)

# Discover tools from the MCP server, then TRANSLATE them into the shape the
# Messages API wants. Note the one rename: MCP says "inputSchema", the Anthropic
# API says "input_schema". The agent is the adapter between the two vocabularies.
mcp_tools = rpc("tools/list")["result"]["tools"]
claude_tools = [
    {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
    for t in mcp_tools
]
print(f"[agent] discovered {len(claude_tools)} tools from the MCP server; handing them to {MODEL}\n")

# ---- The model half: the tool-use loop -------------------------------------
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
user_question = " ".join(sys.argv[1:]) or "What is 21 + 21? Then tell me how many vowels are in the word 'mississippi'."
messages = [{"role": "user", "content": user_question}]
print(f"[user] {user_question}\n")

while True:
    resp = client.messages.create(
        model=MODEL, max_tokens=16000, tools=claude_tools, messages=messages,
    )
    # Preserve the full assistant turn (incl. any thinking blocks) in history.
    messages.append({"role": "assistant", "content": resp.content})

    # Print whatever text the model produced this turn.
    for block in resp.content:
        if block.type == "text":
            print(f"[claude] {block.text}")

    if resp.stop_reason != "tool_use":
        break  # model is done — no more tools to call

    # The model asked for one or more tools. Run each via the MCP server,
    # collect ALL results into a single user message (parallel-tool-use rule).
    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            print(f"[claude->mcp] calling {block.name}({json.dumps(block.input)})")
            out = rpc("tools/call", {"name": block.name, "arguments": block.input})
            text = out["result"]["content"][0]["text"]
            print(f"[mcp->claude] {text}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": text,
            })
    messages.append({"role": "user", "content": tool_results})

proc.stdin.close()
proc.wait()
