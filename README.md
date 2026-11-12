# MCP from scratch — a runnable lesson

A tiny but real [Model Context Protocol](https://modelcontextprotocol.io) demo, written in
pure Python standard library (no SDK, no magic) so you can see the entire protocol on the wire.

## The one idea

MCP is just **JSON-RPC 2.0 messages between a caller and a server**. The caller connects,
asks what's available, and uses it. The novelty isn't the plumbing (it's an ordinary
client↔server pattern) — it's that:

1. the caller **discovers** capabilities at runtime (not hardcoded),
2. each capability carries a **description written for an LLM to read**, and
3. the **decider is swappable** — a dumb script, or an LLM.

## Layout

```
mcp-demo/
├── README.md          ← you are here (docs + architecture + FAQ)
├── .mcp.json          ← host config: how to launch the server
└── src/
    ├── server.py      ← the MCP server, from scratch (pure stdlib)
    ├── server_sdk.py  ← the same server, on the official MCP Python SDK
    ├── host.py        ← a host with a hardcoded decider
    └── agent.py       ← the same host, decider = a real Claude model
```

| File | What it is | Needs |
|------|-----------|-------|
| `src/server.py` | The MCP server: 3 tools, 2 resources, 1 prompt. Pure stdlib. | nothing |
| `src/server_sdk.py` | **The same server built on the official MCP Python SDK** — diff it against `server.py`. | `uv` |
| `src/host.py` | A host with a **hardcoded** decider. Prints the full JSON-RPC exchange. | nothing |
| `src/agent.py` | The same host, but the decider is a **real Claude model** (tool-use loop). | `ANTHROPIC_API_KEY` + `uv` |
| `.mcp.json` | Config telling a real host how to launch `src/server.py`. | — |

## Run it

```bash
# 1. Watch the raw protocol with a hardcoded decider (no API, no install):
python3 src/host.py

# 2. Let a real LLM be the decider (needs an API key; makes a paid call):
export ANTHROPIC_API_KEY=sk-ant-...
uv run src/agent.py "what is 128 + 256, and how many vowels are in 'elephant'?"

# 3. Let Claude Code itself be the host:
claude mcp add demo -- python3 "$(pwd)/src/server.py"
#   then restart the session and ask: "use the demo server to add 128 and 256"
```

See the original zip for the complete detailed README including architecture, FAQ, and more examples.
