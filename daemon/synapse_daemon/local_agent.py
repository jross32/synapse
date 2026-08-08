"""An agent loop for local Ollama models, so they can do real work instead of just chatting.

Squad workers today are CLI processes driven over a PTY (``claude``, ``codex``, ``gemini``).
A local model has no CLI and no agent loop, so it cannot be a worker without one. This
module supplies it: prompt -> tool calls -> execute -> feed results back -> repeat until
the model answers or hits a limit.

Three constraints shape the design, all of them consequences of running a 7B model on a
6 GB card:

* **Context is tiny.** These models typically run at 4k-8k tokens, so tool output is
  truncated hard and the transcript is trimmed. An overflowing context doesn't error, it
  silently drops the system prompt and the agent starts behaving bizarrely.
* **Tool-calling is the weak point.** Small models emit malformed calls, invent tool names
  and occasionally return arguments as a JSON string instead of an object. Every one of
  those is handled and fed back as a correctable error rather than crashing the run.
* **They loop.** A step budget and repeated-call detection are mandatory, not optional.

Safety: the filesystem tools are confined to a workspace root, and shell execution is
opt-in per run and refuses obviously destructive commands.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

OLLAMA_URL = "http://127.0.0.1:11434"

# Tool output is truncated to this many characters before going back into context. A 7B at
# 4k tokens is roughly 16k characters of budget for the *entire* conversation.
MAX_TOOL_CHARS = 2000
MAX_STEPS_DEFAULT = 12

_DESTRUCTIVE = re.compile(
    r"\b(rm\s+-rf\s+/|mkfs|:\(\)\{|shutdown|reboot|format\s+[a-z]:|del\s+/[sf]\s)",
    re.IGNORECASE,
)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    error: bool = False
    duration_s: float = 0.0


class AgentStep(BaseModel):
    index: int
    thought: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_out: int = 0
    duration_s: float = 0.0


class AgentRun(BaseModel):
    model: str
    task: str
    answer: str = ""
    steps: list[AgentStep] = Field(default_factory=list)
    completed: bool = False
    stop_reason: str = ""
    total_duration_s: float = 0.0
    total_tokens_out: int = 0


# ---------------------------------------------------------------- tool implementations


class Workspace:
    """Filesystem tools confined to one directory.

    Every path is resolved and checked against the root, so ``../../etc/passwd`` fails
    rather than escaping. This is a containment boundary, not a security sandbox - the
    shell tool can still do damage if enabled, which is why it is opt-in.
    """

    def __init__(self, root: str | Path, allow_shell: bool = False) -> None:
        self.root = Path(root).resolve()
        self.allow_shell = allow_shell

    def _resolve(self, rel: str) -> Path:
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"path escapes the workspace: {rel}")
        return target

    def read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"ERROR: no such file: {path}"
        if p.is_dir():
            return f"ERROR: {path} is a directory; use list_dir"
        text = p.read_text(encoding="utf-8", errors="replace")
        return text

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} characters to {path}"

    def list_dir(self, path: str = ".") -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"ERROR: no such directory: {path}"
        entries = []
        for child in sorted(p.iterdir())[:200]:
            entries.append(f"{'dir ' if child.is_dir() else 'file'} {child.name}")
        return "\n".join(entries) or "(empty)"

    def run_command(self, command: str) -> str:
        if not self.allow_shell:
            return ("ERROR: shell execution is disabled for this run. Use read_file, "
                    "write_file or list_dir instead.")
        if _DESTRUCTIVE.search(command):
            return "ERROR: refused - that command looks destructive."
        import subprocess  # noqa: PLC0415

        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True,
                                  text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out after 60s"
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return out.strip() or f"(no output, exit code {proc.returncode})"


def web_fetch(url: str) -> str:
    """Fetch a URL and return readable text.

    This is what gives a local model access to the internet. HTML is stripped to text
    because these models have very little context to spend on markup.
    """
    if not url.lower().startswith(("http://", "https://")):
        return "ERROR: url must start with http:// or https://"
    req = urllib.request.Request(url, headers={"User-Agent": "Synapse-LocalAgent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(2_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code} for {url}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"

    if "html" in ctype.lower() or raw.lstrip().startswith("<"):
        raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
        raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        raw = re.sub(r"&nbsp;?", " ", raw)
        raw = re.sub(r"&amp;", "&", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw.strip()


def web_search(query: str) -> str:
    """Search the web via DuckDuckGo's HTML endpoint.

    No API key, so it works on any machine out of the box. Returns title + snippet + URL
    so the model can then web_fetch whichever result looks right.
    """
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    # A realistic browser User-Agent is required: DuckDuckGo serves a stripped, result-less
    # page to anything that looks like a bot, which silently returns zero hits.
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read(1_500_000).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: search failed: {type(exc).__name__}: {exc}"

    results: list[str] = []
    # Attribute order varies (rel/class/href), so match the anchor then pull href out of it
    # rather than assuming a fixed layout.
    for m in re.finditer(r'<a\b([^>]*class="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>', html, re.S):
        attrs, inner = m.group(1), m.group(2)
        href_m = re.search(r'href="([^"]+)"', attrs)
        if not href_m:
            continue
        href = href_m.group(1).replace("&amp;", "&")
        title = re.sub(r"(?s)<[^>]+>", "", inner).strip()
        # Results are wrapped in a /l/?uddg= redirect; unwrap to the real destination.
        parsed = urllib.parse.urlparse(href)
        real = urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        if title:
            results.append(f"{len(results) + 1}. {title}\n   {real}")
        if len(results) >= 6:
            break
    return "\n".join(results) if results else "(no results)"


# ---------------------------------------------------------------- tool schemas

def build_tools(allow_shell: bool, allow_web: bool) -> list[dict[str, Any]]:
    def fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}

    tools = [
        fn("read_file", "Read a text file from the workspace.",
           {"path": {"type": "string", "description": "Path relative to the workspace"}},
           ["path"]),
        fn("write_file", "Create or overwrite a file in the workspace.",
           {"path": {"type": "string"}, "content": {"type": "string"}},
           ["path", "content"]),
        fn("list_dir", "List files and directories.",
           {"path": {"type": "string", "description": "Defaults to the workspace root"}},
           []),
    ]
    if allow_shell:
        tools.append(fn("run_command", "Run a shell command in the workspace.",
                        {"command": {"type": "string"}}, ["command"]))
    if allow_web:
        tools.append(fn("web_search", "Search the web and get titles, snippets and URLs.",
                        {"query": {"type": "string"}}, ["query"]))
        tools.append(fn("web_fetch", "Fetch a URL and return its text content.",
                        {"url": {"type": "string"}}, ["url"]))
    return tools


SYSTEM_PROMPT = """You are a focused worker agent. You complete one task, then stop.

Rules:
- Use the tools to gather facts. Never guess a file's contents - read it.
- Take one small step at a time. After each tool result, decide the next step.
- When you have finished the task, reply with your final answer as plain text and no
  tool call. That is how you signal completion.
- Be concise. Long replies waste the limited context you have.
"""


# ---------------------------------------------------------------- the loop

async def _chat(model: str, messages: list[dict], tools: list[dict],
                num_ctx: int, timeout: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }

    def _do() -> dict[str, Any]:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return await asyncio.to_thread(_do)


def _coerce_args(raw: Any) -> dict[str, Any]:
    """Small models sometimes return arguments as a JSON string, or as junk."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"value": raw}
    return {}


async def run_agent(
    model: str,
    task: str,
    workspace: str | Path,
    *,
    allow_shell: bool = False,
    allow_web: bool = True,
    max_steps: int = MAX_STEPS_DEFAULT,
    num_ctx: int = 8192,
    timeout: float = 240.0,
    on_step: Callable[[AgentStep], None] | None = None,
) -> AgentRun:
    """Drive a local model until it answers, gives up, or exhausts its step budget."""
    ws = Workspace(workspace, allow_shell=allow_shell)
    tools = build_tools(allow_shell, allow_web)
    run = AgentRun(model=model, task=task)
    started = time.time()

    handlers: dict[str, Callable[..., str]] = {
        "read_file": ws.read_file,
        "write_file": ws.write_file,
        "list_dir": ws.list_dir,
        "run_command": ws.run_command,
        "web_search": web_search,
        "web_fetch": web_fetch,
    }

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    seen_calls: list[str] = []

    for i in range(max_steps):
        step = AgentStep(index=i)
        t0 = time.time()
        try:
            data = await _chat(model, messages, tools, num_ctx, timeout)
        except Exception as exc:  # noqa: BLE001
            run.stop_reason = f"model call failed: {type(exc).__name__}: {exc}"
            break

        msg = data.get("message", {}) or {}
        step.thought = (msg.get("content") or "").strip()
        step.tokens_out = data.get("eval_count") or 0
        step.duration_s = round(time.time() - t0, 2)
        run.total_tokens_out += step.tokens_out

        calls = msg.get("tool_calls") or []
        if not calls:
            # No tool call means the model considers itself done.
            run.answer = step.thought
            run.completed = bool(step.thought)
            run.stop_reason = "answered" if step.thought else "empty reply"
            run.steps.append(step)
            if on_step:
                on_step(step)
            break

        messages.append({"role": "assistant", "content": step.thought,
                         "tool_calls": calls})

        for call in calls:
            fnspec = call.get("function") or {}
            name = fnspec.get("name") or ""
            args = _coerce_args(fnspec.get("arguments"))
            tc = ToolCall(name=name, arguments=args)
            c0 = time.time()

            handler = handlers.get(name)
            if handler is None:
                tc.error = True
                tc.result = (f"ERROR: no tool named {name!r}. Available: "
                             f"{', '.join(sorted(handlers))}.")
            else:
                fingerprint = f"{name}:{json.dumps(args, sort_keys=True)[:200]}"
                if seen_calls.count(fingerprint) >= 2:
                    tc.error = True
                    tc.result = ("ERROR: you have already made this exact call twice. "
                                 "Use what you learned and move on, or give your final "
                                 "answer.")
                else:
                    seen_calls.append(fingerprint)
                    try:
                        tc.result = await asyncio.to_thread(lambda: handler(**args))
                    except TypeError as exc:
                        tc.error = True
                        tc.result = f"ERROR: wrong arguments for {name}: {exc}"
                    except Exception as exc:  # noqa: BLE001
                        tc.error = True
                        tc.result = f"ERROR: {type(exc).__name__}: {exc}"

            if len(tc.result) > MAX_TOOL_CHARS:
                tc.result = (tc.result[:MAX_TOOL_CHARS]
                             + f"\n...[truncated, {len(tc.result)} chars total]")
            tc.duration_s = round(time.time() - c0, 2)
            step.tool_calls.append(tc)
            messages.append({"role": "tool", "content": tc.result})

        run.steps.append(step)
        if on_step:
            on_step(step)
    else:
        run.stop_reason = f"hit the {max_steps}-step limit without finishing"

    run.total_duration_s = round(time.time() - started, 2)
    return run
