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
import time
from enum import Enum
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


class PermissionMode(str, Enum):
    """How much the agent may do without a human saying yes.

    Enforced at the tool layer. Asking a model to police itself does not work — a small
    model will cheerfully ignore "do not write files" the moment it decides a file needs
    writing — so unavailable tools are simply not offered, and mutating calls are refused
    even if the model invents them.
    """

    PLAN = "plan"
    """Read-only. Investigate and produce a plan; no writes, no shell."""

    MANUAL = "manual"
    """Every mutating action needs explicit approval before it runs."""

    ACCEPT_EDITS = "accept_edits"
    """File edits happen freely; shell commands still need approval."""

    AUTO = "auto"
    """Acts freely inside the workspace, including the shell. Destructive commands still refused."""

    BYPASS = "bypass"
    """No gates at all, including the destructive-command guard. Use deliberately."""


# Which tools each mode may even see. A tool that isn't offered can't be misused.
MODE_TOOLS: dict[PermissionMode, set[str]] = {
    PermissionMode.PLAN: {"read_file", "list_dir", "web_search", "web_fetch"},
    PermissionMode.MANUAL: {"read_file", "list_dir", "web_search", "web_fetch",
                            "write_file", "write_code", "run_command"},
    PermissionMode.ACCEPT_EDITS: {"read_file", "list_dir", "web_search", "web_fetch",
                                  "write_file", "write_code"},
    PermissionMode.AUTO: {"read_file", "list_dir", "web_search", "web_fetch",
                          "write_file", "write_code", "run_command"},
    PermissionMode.BYPASS: {"read_file", "list_dir", "web_search", "web_fetch",
                            "write_file", "write_code", "run_command"},
}

MUTATING_TOOLS = {"write_file", "run_command", "write_code"}

# Required arguments per tool, used to turn a raw TypeError into a correction the model
# can act on. Small models frequently call write_file with only a path, and "missing 1
# required positional argument" tells them nothing useful.
TOOL_REQUIRED_ARGS: dict[str, list[str]] = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "list_dir": [],
    "run_command": ["command"],
    "web_search": ["query"],
    "web_fetch": ["url"],
    "write_code": ["path", "spec"],
}


def missing_args(name: str, args: dict[str, Any]) -> list[str]:
    return [a for a in TOOL_REQUIRED_ARGS.get(name, []) if a not in args or args[a] in (None, "")]


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
    mode: str = PermissionMode.AUTO.value
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

    def __init__(self, root: str | Path, allow_shell: bool = False,
                 allow_destructive: bool = False, task_context: str = "") -> None:
        self.root = Path(root).resolve()
        self.allow_shell = allow_shell
        self.allow_destructive = allow_destructive
        # The original request, replayed into every write_code call so the coding model
        # sees the real requirement rather than the agent's paraphrase of it.
        self.task_context = task_context

    def _resolve(self, rel: str) -> Path:
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            # Say what to do instead. Models routinely invent absolute paths like
            # /home/user/workspace/x.py, and a bare refusal sends them into a loop of
            # inventing different absolute paths.
            raise ValueError(
                f"path escapes the workspace: {rel!r}. Use a path relative to the "
                f"workspace root, e.g. 'greet.py' or 'src/greet.py' - never an absolute path.")
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

    def write_code(self, path: str, spec: str, coder_model: str = "") -> str:
        """Delegate the writing to a coding model, then store the result.

        Split deliberately: the coder model never gets filesystem access, and the agent
        never has to produce correct code itself. Each does only what it is good at.

        The original task is prepended to the spec automatically. Measured: a 1.5B agent
        summarises the requirement when relaying it, and the coder - which cannot see the
        conversation - then writes something subtly wrong. The same coder passes the same
        task when handed the full brief. Instructing the agent to copy the spec verbatim
        made things *worse*, because a longer system prompt crowds out a small model's
        context. Doing it structurally removes the failure mode instead of asking a weak
        model to avoid it.
        """
        full_spec = f"{self.task_context}\n\n{spec}" if self.task_context else spec
        code = generate_code(full_spec, model=coder_model or DEFAULT_CODER_MODEL)
        if code.startswith("ERROR:"):
            return code
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")
        # Echo the code back: the agent needs to see what was written to decide whether it
        # satisfies the task, and it has no other way to inspect it without another read.
        preview = code if len(code) < 700 else code[:700] + "\n...[truncated]"
        return f"wrote {len(code)} characters to {path}:\n{preview}"

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
        if _DESTRUCTIVE.search(command) and not self.allow_destructive:
            return "ERROR: refused - that command looks destructive."
        import subprocess  # noqa: PLC0415

        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True,
                                  text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out after 60s"
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return out.strip() or f"(no output, exit code {proc.returncode})"


# Measured on this machine: qwen2.5-coder:3b writes correct code for every benchmark task
# AND fits entirely in 6 GB of VRAM at ~15 tok/s. The 7B is no more correct and spills to CPU.
DEFAULT_CODER_MODEL = "qwen2.5-coder:3b"


def generate_code(spec: str, model: str = DEFAULT_CODER_MODEL, timeout: float = 900.0,
                  num_ctx: int = 8192, temperature: float = 0.0) -> str:
    """Ask a coding-tuned model to write code, with no tools involved.

    This exists because of a hard split measured on real runs: the coder-tuned models write
    correct code but **cannot call tools at all** (Ollama returns HTTP 400 - they ship with
    no tools template), while the small general models call tools flawlessly but produce
    stubs like ``# Your code here``. Neither can do the job alone.

    So the tool-using agent keeps the hands, and delegates the actual writing here. The
    coder never touches the filesystem; it just returns source, which the agent then writes.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content":
                      f"{spec}\n\nOutput ONLY the code in a single ```python block. "
                      f"No explanation before or after."}],
        "stream": False,
        # num_ctx covers the prompt AND the generation. At 4096 a piece that receives an
        # exemplar plus its dependencies' interfaces has no room left to emit a full module,
        # which surfaces as a timeout rather than as an obvious "context exhausted" error -
        # measured: the pages piece failed this way at 300s having produced nothing.
        # temperature defaults to 0 because a first draft wants the model's best guess, not
        # a lottery ticket. The repair loop raises it deliberately: greedy decoding is
        # deterministic, so re-asking with a near-identical prompt returns near-identical
        # code, and "it stopped changing the code" would describe the sampler rather than
        # the model. Measured: `storage` was declared stuck after two repairs having never
        # reached its scenario.
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = json.loads(resp.read().decode("utf-8"))["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: the code model failed: {type(exc).__name__}: {exc}"

    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (max(fences, key=len) if fences else text).strip()


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

def build_tools(mode: PermissionMode, allow_web: bool) -> list[dict[str, Any]]:
    """Offer only the tools this mode permits.

    Network access is orthogonal to the permission mode: a plan-mode agent may still need
    to read documentation, while an auto-mode agent may be deliberately kept offline.
    """

    def fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}

    allowed = MODE_TOOLS[mode]
    catalog = {
        "read_file": fn("read_file", "Read a text file from the workspace.",
                        {"path": {"type": "string",
                                  "description": "Path relative to the workspace"}}, ["path"]),
        "write_file": fn("write_file", "Create or overwrite a file in the workspace.",
                         {"path": {"type": "string"}, "content": {"type": "string"}},
                         ["path", "content"]),
        "list_dir": fn("list_dir", "List files and directories.",
                       {"path": {"type": "string",
                                 "description": "Defaults to the workspace root"}}, []),
        "run_command": fn("run_command", "Run a shell command in the workspace.",
                          {"command": {"type": "string"}}, ["command"]),
        "web_search": fn("web_search", "Search the web and get titles, snippets and URLs.",
                         {"query": {"type": "string"}}, ["query"]),
        "web_fetch": fn("web_fetch", "Fetch a URL and return its text content.",
                        {"url": {"type": "string"}}, ["url"]),
        "write_code": fn(
            "write_code",
            "Write source code to a file. Describe what the code must do in `spec` and a "
            "specialised coding model writes it for you. Prefer this over write_file for "
            "anything non-trivial.",
            {"path": {"type": "string", "description": "Relative path, e.g. solution.py"},
             "spec": {"type": "string",
                      "description": "What the code must do, including function names and "
                                     "expected behaviour."}},
            ["path", "spec"]),
    }
    web = {"web_search", "web_fetch"}
    return [spec for name, spec in catalog.items()
            if name in allowed and (allow_web or name not in web)]


SYSTEM_PROMPT = """You are a focused worker agent. You complete one task, then stop.

Rules:
- Use the tools to gather facts. Never guess a file's contents - read it.
- Take one small step at a time. After each tool result, decide the next step.
- When you have finished the task, reply with your final answer as plain text and no
  tool call. That is how you signal completion.
- Be concise. Long replies waste the limited context you have.

- Use write_code to create code files. Pasting code into your reply saves nothing; only a
  tool call changes a file.
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
    mode: PermissionMode = PermissionMode.AUTO,
    allow_web: bool = True,
    max_steps: int = MAX_STEPS_DEFAULT,
    num_ctx: int = 8192,
    timeout: float = 240.0,
    on_step: Callable[[AgentStep], None] | None = None,
    approve: Callable[[str, dict], bool] | None = None,
) -> AgentRun:
    """Drive a local model until it answers, gives up, or exhausts its step budget.

    ``approve`` is consulted in MANUAL mode before any mutating call. With no approver
    supplied, MANUAL refuses mutations rather than silently behaving like AUTO — failing
    closed is the only safe default for a permission gate.
    """
    allowed = MODE_TOOLS[mode]
    ws = Workspace(workspace,
                   allow_shell="run_command" in allowed,
                   allow_destructive=(mode is PermissionMode.BYPASS),
                   task_context=task)
    tools = build_tools(mode, allow_web)
    run = AgentRun(model=model, task=task, mode=mode.value)
    started = time.time()

    handlers: dict[str, Callable[..., str]] = {
        "read_file": ws.read_file,
        "write_file": ws.write_file,
        "write_code": ws.write_code,
        "list_dir": ws.list_dir,
        "run_command": ws.run_command,
        "web_search": web_search,
        "web_fetch": web_fetch,
    }

    # Tell the model what it may do, in addition to enforcing it. Enforcement stops damage;
    # telling it stops the model wasting steps on calls that will be refused.
    mode_note = {
        PermissionMode.PLAN: (
            "\nYou are in PLAN mode: read-only. Investigate, then give a concrete "
            "step-by-step plan. You cannot write files or run commands."),
        PermissionMode.MANUAL: (
            "\nYou are in MANUAL mode: every file write and command needs the user's "
            "approval, so explain what you intend before you attempt it."),
        PermissionMode.ACCEPT_EDITS: (
            "\nYou are in ACCEPT-EDITS mode: you may create and edit files freely, but "
            "you cannot run shell commands."),
        PermissionMode.AUTO: (
            "\nYou are in AUTO mode: you may read, write and run commands inside the "
            "workspace. Stay inside it."),
        PermissionMode.BYPASS: (
            "\nYou are in BYPASS mode: no restrictions. Be careful."),
    }[mode]

    # State the workspace root explicitly. Without it models invent absolute paths like
    # /home/user/workspace/solution.py, get refused by the containment check, and then
    # explain the refusal back to the user instead of retrying with a relative path -
    # which reads as "the task failed" when the agent never actually attempted it.
    workspace_note = (
        f"\n\nYour workspace is: {ws.root}\n"
        "Every path you pass to a tool MUST be relative to that root - 'solution.py' or "
        "'src/app.py'. Never pass an absolute path; it will be refused."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + mode_note + workspace_note},
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
                             f"{', '.join(sorted(allowed))}.")
            elif name not in allowed:
                # The model invented a tool it was never offered. Say why, so it adapts
                # instead of retrying the same call.
                tc.error = True
                tc.result = (f"ERROR: {name} is not permitted in {mode.value} mode. "
                             f"Available here: {', '.join(sorted(allowed))}.")
            elif (mode is PermissionMode.MANUAL and name in MUTATING_TOOLS
                  and not (approve and approve(name, args))):
                tc.error = True
                tc.result = (f"ERROR: {name} was not approved. In manual mode every "
                             "file write and command needs explicit approval first.")
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
