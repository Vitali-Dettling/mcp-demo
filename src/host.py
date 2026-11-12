#!/usr/bin/env python3
"""
A minimal MCP *host/client* — the thing that an AI agent would normally be.

This is the whole point of your question: an AI agent is "just a program"
that does exactly what this script does. It:
  1. launches the server as a subprocess,
  2. speaks JSON-RPC to it over stdin/stdout,
  3. discovers tools at runtime (tools/list),
  4. calls one (tools/call),
  5. feeds the result back into its "reasoning".

Here step 5 is a dumb print(). In a real host, the tool descriptions from
step 3 are shown to an LLM, and the LLM decides which tool to call in step 4.
Swap the print() for a model, and this script *is* an AI agent.
"""

import subprocess
import json
import sys
import os

# server.py lives next to this file — resolve it so we can run from any cwd.
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

# 1. Launch the server. stdio transport = we own its stdin/stdout.
proc = subprocess.Popen(
    [sys.executable, SERVER],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=sys.stderr,          # let the server's [server] logs show in our terminal
    text=True,
    bufsize=1,
)

_id = 0
def rpc(method, params=None, is_notification=False):
    """Send one JSON-RPC message; return the parsed response (or None for notifications)."""
    global _id
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not is_notification:
        _id += 1
        msg["id"] = _id
    print(f"\n[host] -> {json.dumps(msg)}")
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if is_notification:
        return None
    line = proc.stdout.readline()
    resp = json.loads(line)
    print(f"[host] <- {json.dumps(resp)}")
    return resp

# 2. Handshake.
rpc("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "demo-host", "version": "1.0.0"},
})
rpc("notifications/initialized", is_notification=True)

# 3. DISCOVERY — the key difference from a normal API call.
# We did not hardcode what tools exist. We ask at runtime.
listed = rpc("tools/list")
tools = listed["result"]["tools"]
print("\n[host] discovered tools at runtime:")
for t in tools:
    print(f"   - {t['name']}: {t['description']}")

# 4. INVOCATION — in a real host, the LLM picks this based on the descriptions above.
print("\n[host] (pretending to be the model) I'll call add(21, 21)...")
result = rpc("tools/call", {"name": "add", "arguments": {"a": 21, "b": 21}})

# 5. Feed result back (here: just print it).
answer = result["result"]["content"][0]["text"]
print(f"\n[host] tool returned: {answer}  <- this is what gets fed back into the model's context")

# 6. RESOURCES — the second primitive. Same discover-then-use shape, different verbs.
listed_res = rpc("resources/list")
resources = listed_res["result"]["resources"]
print("\n[host] discovered resources at runtime:")
for r in resources:
    print(f"   - {r['uri']}  ({r['name']}: {r['description']})")

# Read one resource by its URI (note: no model decision needed — the app/user pulls data in).
read = rpc("resources/read", {"uri": "demo://server-stats"})
contents = read["result"]["contents"][0]["text"]
print(f"\n[host] read demo://server-stats -> {contents}")

# 7. PROMPTS — the third primitive. USER-controlled templates (think slash-commands).
listed_prompts = rpc("prompts/list")
prompts = listed_prompts["result"]["prompts"]
print("\n[host] discovered prompts at runtime:")
for p in prompts:
    argnames = ", ".join(a["name"] for a in p.get("arguments", []))
    print(f"   - /{p['name']}({argnames}): {p['description']}")

# "Invoke" a prompt: the server fills the template and returns seed messages.
got = rpc("prompts/get", {"name": "explain_like_im_five", "arguments": {"topic": "MCP"}})
seed = got["result"]["messages"][0]["content"]["text"]
print(f"\n[host] prompt expanded to a ready-made user message:\n       \"{seed}\"")

proc.stdin.close()
proc.wait()
