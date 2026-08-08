# Local AI agents in Synapse — build plan

Goal: run real work on local Ollama models so squads cost no API tokens, pick the right
model per job from measured evidence, and make all of it discoverable to any AI that
connects to Synapse.

## Target machine (measured 2026-08-08)

| | |
|---|---|
| GPU | NVIDIA GTX 1660 Ti Max-Q, **6144 MiB VRAM** (5966 free), driver 595.97 |
| CPU | AMD Ryzen 7 3750H, 4 cores / 8 threads |
| RAM | 15.8 GB |
| Ollama | 0.32.6, server on 11434 |

**The binding constraint is 6 GB VRAM.** A 7B Q4_K_M is ~4.7 GB, leaving ~1.2 GB for KV
cache — it fits, but context length is the tradeoff. Anything that spills to CPU collapses
throughput, so "fits in VRAM" is a first-class benchmark metric, not a footnote.

## Phases

1. **Profile the machine** — real VRAM via `nvidia-smi` (Win32_VideoController caps at 4 GB
   and lies). Done.
2. **Benchmark harness** — measure what actually matters for agent work, machine-checked.
3. **Pull candidates** — coder-tuned models sized to 6 GB.
4. **Run + record** — durable JSON + human-readable report.
5. **Integrate into Synapse**
   - hardware profile endpoint → model recommendation for *this* machine
   - local model as a real squad worker (agent loop, not a PTY CLI)
   - expose models + measured strengths in `/ai/context` so every connecting AI knows
     what is available locally and what each model is good for
6. **Internet access for local models** — web fetch/search as agent tools.
7. **Commit + push** each working increment.

## Requirements backlog (captured 2026-08-08, build in this order)

1. **AI-facing layer** — done: hardware profile, measured strengths, agent loop, REST, and a
   `local_ai` block in `/ai/context` so every connecting AI can offload work.
2. **Full tool parity.** A local agent must reach *everything* Synapse has: Reflex, the web
   scraper, Playwright, agent squads, workflows, project/file tools. Audit for gaps and add
   what's missing properly — the failure mode to avoid is discovering mid-task that there is
   no tool for something ordinary like opening a shell.
3. **Permission modes**, mirroring what users already expect from coding agents:
   *manual* (confirm every action) · *accept-edits* (files yes, shell no) · *plan* (read-only,
   produce a plan) · *auto* (act freely inside the workspace) · *bypass* (no gates).
   Modes are enforced at the tool layer, not by asking the model to behave.
4. **The local agent must use Synapse itself** — register a coordination session, heartbeat,
   and emit activity, so a local run shows up in Live View exactly like any other AI.
5. **User-facing chat UI** — a dedicated surface where the user codes with their local model
   directly, in the idiom people already know from mainstream coding chats.
6. **End-to-end proof** — drive the finished UI as a real user via Reflex/Playwright, build a
   small app with it, fix whatever breaks, repeat until it genuinely works.

**Deferred, but not forgotten:** driving the logged-in ChatGPT surface inside Synapse from a
local agent (start a chat, prompt it, read the reply back). Real work, worth doing later.

### Chat surface behaviour (requirements)

* **Nothing runs until it's wanted.** Ollama must not serve, and no model may occupy VRAM,
  merely because Synapse is open — this is a laptop with 6 GB of VRAM and 16 GB of RAM, and
  an idle 5 GB resident model is a real cost to everything else. Start the engine and load
  the model on the *first prompt*, from the user or from another AI.
* **Show the wait honestly.** A cold 7B load takes tens of seconds. Stream real progress
  (engine starting → model loading with percentage where Ollama reports it → ready), never a
  spinner that implies nothing is happening. Then a clear connected state, then the reply
  streaming token by token.
* **Fail out loud.** If the engine won't start or the model won't load, say which and why,
  in plain language, with the obvious next step. Silence or a hung spinner is the worst
  outcome.
* **Conversations persist.** Each chat is auto-titled from its opening prompt, listed in a
  sidebar, resumable, and a new chat is always one click away.

## Why a new execution path is needed

Squad workers today spawn CLI processes over PTY (`claude.cmd`, `codex`, `gemini`).
Ollama is an HTTP API with no CLI agent loop, so a local model cannot be a worker
without one. The build adds an in-daemon agent loop: prompt → tool calls → execute →
iterate → report, reporting progress the same way a PTY worker does.

## Benchmark dimensions (ranked by what breaks agents in practice)

1. **Tool calling** — emits valid, well-formed tool calls. Agents are useless without it.
2. **Structured output** — returns parseable JSON on demand.
3. **Code generation** — writes a function that passes real asserts.
4. **Code repair** — given broken code and the error, fixes it.
5. **Instruction adherence** — respects "output only X" constraints.
6. **Throughput** — tokens/sec and time-to-first-token.
7. **VRAM fit** — stays on GPU vs spills to CPU.

Scoring is machine-checked wherever possible: generated code is executed against asserts,
JSON is parsed, tool calls are shape-validated. No model grades itself.
