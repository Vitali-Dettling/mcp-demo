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
#   remove later with:  claude mcp remove demo

# 4. The SAME server, but built on the official MCP Python SDK:
uv run src/server_sdk.py            # runs over stdio, like server.py
uv run mcp dev src/server_sdk.py    # opens the MCP Inspector UI to poke at it
```

---

## Architecture

The dashed arrow is the whole point: **only the DECIDER box changes between `host.py` and
`agent.py` — everything else is identical.**

### Roles and primitives

```
┌───────────────────────────────────────────────┐         ┌───────────────────────────────┐
│                  HOST  (the caller)             │         │   SERVER  ("an MCP service")  │
│                                                 │         │        src/server.py          │
│   ┌─────────────┐        ┌───────────────────┐  │         │                               │
│   │  DECIDER    │        │   CLIENT         │  │         │   TOOLS (verbs, model picks): │
│   │             │        │  (one per server)│  │ JSON-RPC│     • add                     │
│   │ host.py  →  │ picks  │                  │◄─┼─────────┼─►   • vowel_count              │
│   │  hardcoded  │───────►│ speaks the       │  │  over   │     • current_time            │
│   │  (NOT an    │  tool  │ protocol:        │  │  stdio  │                               │
│   │   agent)    │        │  initialize      │  │  pipes  │   RESOURCES (nouns, app reads):│
│   │             │        │  tools/list      │  │         │     • demo://readme           │
│   │ agent.py →  │        │  tools/call      │  │         │     • demo://server-stats     │
│   │  the MODEL  │        │  resources/list  │  │         │                               │
│   │  (an agent) │        │  resources/read  │  │         │   PROMPTS (templates, user):  │
│   │             │        │  prompts/list    │  │         │     • explain_like_im_five    │
│   └─────────────┘        │  prompts/get     │  │         │                               │
│                          └───────────────────┘  │         │                               │
└───────────────────────────────────────────────────┘         └─────────────────────────────────┘
        ^                                                              ^
        │ the ONLY thing that differs between host.py and agent.py     │ identical in both runs —
        │ is the DECIDER box. Everything else is the same plumbing.    │ one server, any host.
```

- **Host** = the caller application `host.py`, `agent.py`, or Claude Code). Contains the decider + client.
- **Client** = the connector inside the host that speaks the protocol (the `rpc()` helper), one per server.
- **Server** = the program exposing capabilities ("an MCP"), here `src/server.py`.
- The **LLM lives on the host side** and **never talks to the server directly** — the host is the middleman.
- A host is only an **agent** when its decider is an autonomous LLM: `host.py` is a host but not an agent; `agent.py` is both.

### Message sequence (what `host.py` prints)

```
   HOST                                 SERVER
    │   ── initialize ───────────────►   │   "hi, who are you?" / "I offer tools+resources+prompts"
    │   ◄────────── capabilities ──────   │
    │   ── notifications/initialized ─►   │   (notification: no id, no reply)
    │   ── tools/list ───────────────►   │   DISCOVERY  ── "what can you do?"
    │   ◄────────── tool schemas ──────   │
    │   ── tools/call {add, 21,21} ──►   │   INVOCATION ── decider chose this
    │   ◄────────── "42" ──────────────   │
    │   ── resources/list ───────────►   │   DISCOVERY (data side)
    │   ◄────────── resource URIs ─────   │
    │   ── resources/read {stats} ───►   │
    │   ◄────────── "tools=3 ..." ─────   │
    │   ── prompts/list ─────────────►   │   DISCOVERY (template side)
    │   ◄────────── prompt list ───────   │
    │   ── prompts/get {elif5,MCP} ──►   │
    │   ◄────────── seed messages ─────   │
```

### Who decides (the key difference from a plain API call)

```
            tools/list                    "here's the task +
             (schemas)                      these available tools"
  SERVER  ────────────────►  HOST  ───────────────────────────►  LLM
    ▲                        │                                    │
    │                        │  ◄──── "call add with {a,b}" ──────┘
    │     tools/call         │              (decision = DATA:
    └───────────────────────┘               a tool name + JSON args)
          (host runs it, feeds result back to the LLM)
```

The LLM's decision comes back as **data** `tool_use { name, input }`), not code. The host runs
**one generic dispatcher** — `rpc("tools/call", {"name": block.name, "arguments": block.input})` —
with no `if name == "add"`. That's why the same loop handles any tool without rewriting code.

---

## From scratch vs. the SDK — what does an SDK actually do?

A **skeleton** is the few lines of "hello world" you clone and build on. Providing one is the
*smallest* thing an SDK does — the docs' quickstart. The SDK's real job is everything it does
*under* that skeleton so you don't hand-write it. `server.py` (from scratch) and
`server_sdk.py` (SDK) expose the identical server, so the diff *is* the answer:

| What it takes | `server.py` (by hand) | `server_sdk.py` (SDK) |
|---------------|------------------------|------------------------|
| Tool schema | hand-written `inputSchema` dict per tool | **generated from type hints** `a: float` → `{"type":"number"}`) |
| Description | hand-written string | **the docstring** |
| JSON-RPC envelope, `okerr` | hand-written | SDK |
| `initialize` + capability negotiation | hand-written | SDK |
| notification rule (no `id` → no reply) | hand-written | SDK |
| `tools/call` routing + result shape | hand-written dict lookup | `@mcp.tool()` |
| stdio read/write loop | hand-written | `mcp.run()` |
| HTTP transport | would be a rewrite | `mcp.run("streamable-http")` |
| Client side, auth, lifespan, dev inspector | not implemented | included |

So an SDK (Software Development Kit) = **library + tooling that does the heavy lifting**:
schema generation, (de)serialization, validation, protocol/lifecycle handling, transports,
a client implementation, auth, and dev tools. The skeleton is just the visible tip. Our
hand-rolled `server.py` is essentially a tiny re-implementation of one slice of the SDK —
which is exactly why it's useful to see once before letting the SDK hide it.

**The SDK is a *library*, not a server.** You call it; it doesn't run on its own. The *server*
is `server_sdk.py` — the program you wrote using the SDK. "Handled by the SDK" means handled by
the code inside the installed `mcp` package when `mcp.run()` executes — not by a separate service.

---

## FAQ — the mental model (click to expand)

Everything worked out while building this demo. Each answer stands alone.

<details>
<summary><b>1. What is MCP, really?</b></summary>

**MCP (Model Context Protocol)** is an open standard for connecting AI applications to
external tools and data. It is a **protocol**, not a product: a fixed set of **JSON-RPC 2.0**
messages that a caller and a server agree to speak.

- "MCP" = the rules (the message names and shapes).
- "an MCP" / "an MCP server" / "an MCP service" = a *program that speaks those rules*.
- Analogy: **HTTP** is the rules; **a web server** is a program that speaks them.

The architecture underneath is an ordinary client↔server pattern. MCP's novelty is only:
runtime discovery, descriptions written for an LLM to read, and a swappable decider.
</details>

<details>
<summary><b>2. Host vs client vs server — and "isn't the host just the agent"?</b></summary>

| Role | What it is | In this demo |
|------|-----------|--------------|
| **Host** | the caller application | `host.py`, `agent.py`, or Claude Code |
| **Client** | connector inside the host, one per server | the `rpc()` helper |
| **Server** | program exposing capabilities ("an MCP") | `server.py` |

- The **host is the caller**; the **server is the service**. The server has **no AI** in it.
- The **LLM lives on the host side**, and the **LLM never talks to the server directly** —
  the host is always the middleman: it fetches schemas, hands them to the LLM, the LLM
  decides, the host executes against the server and feeds the result back.

**"Is the host the agent?"** — Not quite, and this demo depends on the difference. A *host*
is the role (the caller/plumbing). An *agent* is a **behaviour**: a host becomes an agent
only when its decider is an autonomous LLM in a loop. That's exactly why the files are *not*
both called "agent":
- `host.py` is a host but **not** an agent — its decider is a hardcoded line.
- `agent.py` is a host that **is** an agent — its decider is a real LLM.

Same plumbing, swap the decider, and only then is it an "agent". Renaming `host.py` to
`agent.py` would erase the one contrast the lesson is built to show.
</details>

<details>
<summary><b>3. What are the three primitives?</b></summary>

| Primitive | Who decides to use it | Analogy | Methods |
|-----------|----------------------|---------|---------|
| **Tools** | the **model** | verbs / function calls | `tools/list`, `tools/call` |
| **Resources** | the **app** | nouns / files by URI | `resources/list`, `resources/read` |
| **Prompts** | the **user** | slash-commands / templates | `prompts/list`, `prompts/get` |

A fourth concept, **capability negotiation**, happens once up front via `initialize`.
</details>

<details>
<summary><b>4. What's the message flow / lifecycle?</b></summary>

```
initialize                connect + capability negotiation ("who are you / what do you offer")
notifications/initialized acknowledgement (a NOTIFICATION — no id, no reply)
tools/list                DISCOVERY  — "what can you do?"  → returns schemas
tools/call                INVOCATION — "do this one, with these args"
```

You **must** connect and discover before you can call anything. Resources and prompts follow
the identical discover-then-use shape with their own method names.

**JSON-RPC detail that trips people up:** a message **with** an `id` is a *request* and
demands a reply; a message **without** an `id` is a *notification* and must get **no reply**.
`notifications/initialized` has no `id`, so the server answers nothing. Reply to a
notification and the host hangs or errors.
</details>

<details>
<summary><b>5. Can I rename the protocol methods (e.g. <code>init</code>, <code>program/list</code>)?</b></summary>

No. `initialize`, `tools/list`, `tools/call`, `resources/*`, `prompts/*` are **fixed by the
spec**. Rename `tools/list` → `program/list` and every standard host breaks — that's the
point of a protocol.

What's **yours to name**: tool names `add`), resource URIs `demo://readme`), prompt names.
Same as HTTP: you can't rename `GET`, but the URL after it is yours. A protocol fixes the
*envelope* (message format), the *method names*, the *result shapes*, the *ordering*, the
*error codes*, and the *transport framing* — not just the names.
</details>

<details>
<summary><b>6. When the LLM decides, how does the agent execute it without rewriting code?</b></summary>

**The agent never rewrites its code.** The LLM's decision comes back as **data**, not code:

```
tool_use { name: "add", input: {"a": 128, "b": 256} }
```

— just a string and a JSON object. The agent runs **one generic dispatcher**:

```python
out = rpc("tools/call", {"name": block.name, "arguments": block.input})
```

There is **no `if name == "add"`**. The tool name is a *lookup key*, not a branch. The same
loop handles any tool, including ones added later; the server mirrors it with `TOOLS[name]`.
So the "too many variables" worry never materialises: the variety lives in **data**, flowing
through **one** pipe. The LLM's freedom is bounded — it can only name a tool `tools/list`
advertised, with args matching that tool's schema. The loop runs until
`stop_reason != "tool_use"`. That loop *is* "being an agent".
</details>

<details>
<summary><b>7. Where does a tool like <code>write_file</code> live — in the agent? And is it also "data"?</b></summary>

A `write_file` tool does **not** live in the agent/host — it lives in the **server** (or as a
host built-in; see #10). The agent only *relays* the call. Crucially, the filename and the
file contents are both **arguments the LLM supplies**, because the tool's schema declares them:

```python
"write_file": {
  "schema": {"name": "write_file",
    "description": "Write text to a file at the given path.",
    "inputSchema": {"type": "object",
      "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
      "required": ["path", "content"]}},
  "fn": lambda args: open(args["path"], "w").write(args["content"]),
}
```

So **"how does the agent know which file?"** → it doesn't decide; the LLM tells it, as the
`path` argument, chosen from the task. Note the two directions people conflate:
- the LLM's **decision** = the `tool_use` block `name` + `input`) — this is where the code
  string and filename come from;
- the tool's **result** = `out["result"]["content"][0]["text"]` — this comes *back from the
  server* after it ran (e.g. "wrote 11 bytes"), it is **not** the LLM's instruction.
</details>

<details>
<summary><b>8. Is it stdio or could it be HTTP? Is HTTP just REST?</b></summary>

| | stdio | Streamable HTTP |
|--|-------|-----------------|
| Server location | local process on your machine | remote, at a URL |
| Pipe | the host owns its stdin/stdout | HTTP POST to one endpoint (+ SSE for streaming) |
| Config | a command to run | a URL + auth (e.g. OAuth) |

Same JSON-RPC messages either way — only the pipe changes. It's stdio here **because the
server runs locally**. **HTTP MCP is NOT REST**: there's one endpoint and the method name
lives inside the JSON body, not in the URL/verb. REST would be `GET /tools`, `POST /tools/add`;
MCP is `POST /` with `{"method":"tools/call"}`.
</details>

<details>
<summary><b>9. Where's the global registry the AI finds servers in?</b></summary>

There is **no live auto-discovery**. A human configures each server explicitly (here:
`claude mcp add demo -- python3 .../src/server.py`). The model only ever sees servers someone
already wired up. Public catalogs exist — the **official MCP Registry**
`registry.modelcontextprotocol.io`), Smithery, PulseMCP, Docker's MCP catalog — but they are
**human-facing directories**, like an app store: a person browses, picks a server, and adds it
to their host config.
</details>

<details>
<summary><b>10. How does an agent write to the filesystem — is that also MCP?</b></summary>

**Not necessarily.** "Tools" is the general concept; **MCP is one way to deliver tools, not the
only way.** An agent gets tools from either:
- **Built-in tools** hardcoded into the host (no MCP). Claude Code's `ReadWriteEdit`/
  `BashGlob` are native built-ins — that's what it uses to navigate directories.
- **MCP tools** from an external server you wired up (there's an official *filesystem* MCP
  server with `read_file`, `write_file`, `list_directory`, …).

To the LLM both look identical: "a tool with a name, description, and schema." The only
difference is *who executes it* — the host directly, or a round-trip to an MCP server. MCP is
the *extensibility mechanism*. The related **roots** capability is how the host fences a
filesystem server to allowed directories (e.g. only under your project folder).
</details>

<details>
<summary><b>11. "Claude" = the LLM?</b></summary>

Yes. Claude is Anthropic's LLM (models: Opus, Sonnet, Haiku). Wherever the demo says "the
model" or "Claude", read "the LLM doing the deciding". Registering the demo server with
Claude Code makes Claude itself the host's decider — the real version of `agent.py`, no API
key needed.
</details>

<details>
<summary><b>12. One part of an SDK is to provide a skeleton — what else does it do? And is the SDK a server?</b></summary>

**The SDK is a *library*, not a server.** You call it; it does not run on its own. The *server*
is `server_sdk.py` — the program you wrote *using* the library. Clean hierarchy: **SDK (library)
→ you use it to build → a server (a running program)**. Keep the categories apart:
- **Library / SDK** = code you import and call. Doesn't run by itself.
- **Server** = a long-running program that answers requests.
- **Service** = a server someone operates for you, usually remote.

Providing a skeleton (the quickstart "hello world") is the *smallest* thing an SDK does. The
rest — the heavy lifting — is: generating tool schemas from type hints, turning docstrings into
descriptions, parsing/validating/serializing every message, handling the whole protocol
lifecycle `initialize`, capability negotiation, notifications), offering transports behind one
argument, plus a client implementation, auth, lifespan/context, and dev tooling (the
`mcp dev` Inspector). "Handled by the SDK" = handled by the code inside the installed `mcp`
package when `mcp.run()` runs — same work `server.py` does by hand, just not in your file. See the
**From scratch vs. the SDK** table above; the diff between the two servers *is* that list.
</details>
