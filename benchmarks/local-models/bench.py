"""Benchmark local Ollama models on the work Synapse actually asks agents to do.

Every task is machine-checked: generated code is executed against real asserts, JSON is
parsed, tool calls are shape-validated. No model grades itself and no result depends on
anyone's judgement.

Results stream to disk after each task so a long run survives a crash or an interrupt.

    python bench.py                     # all installed candidates
    python bench.py --models a,b        # specific models
    python bench.py --repeat 3          # average over N runs
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import urllib.error
import urllib.request

OLLAMA = "http://127.0.0.1:11434"
HERE = Path(__file__).parent
RESULTS = HERE / "results.json"
REPORT = HERE / "REPORT.md"

# Generous: a 7B on 6 GB VRAM can be slow, and a timeout would score as a failure and
# quietly libel the model.
TIMEOUT = 240.0


# ---------------------------------------------------------------- ollama transport

def _post(path: str, payload: dict[str, Any], timeout: float = TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str, timeout: float = 15.0) -> dict[str, Any]:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(model: str, messages: list[dict], tools: list | None = None,
         fmt: str | None = None, num_ctx: int = 4096) -> dict[str, Any]:
    """One non-streaming chat turn. Returns text, tool_calls and real timing counters."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        # Deterministic so re-runs are comparable; agents want determinism anyway.
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }
    if tools:
        payload["tools"] = tools
    if fmt:
        payload["format"] = fmt

    t0 = time.time()
    try:
        data = _post("/api/chat", payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "wall_s": time.time() - t0}

    msg = data.get("message", {}) or {}
    eval_count = data.get("eval_count") or 0
    eval_ns = data.get("eval_duration") or 0
    return {
        "text": (msg.get("content") or "").strip(),
        "tool_calls": msg.get("tool_calls") or [],
        "wall_s": round(time.time() - t0, 2),
        "tokens_out": eval_count,
        "tok_per_s": round(eval_count / (eval_ns / 1e9), 1) if eval_ns else None,
        "ttft_s": round((data.get("prompt_eval_duration") or 0) / 1e9, 2),
    }


# ---------------------------------------------------------------- checkers

def extract_code(text: str) -> str:
    """Pull python out of a fenced block; fall back to the raw text."""
    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if fences:
        return max(fences, key=len).strip()
    return text.strip()


def run_python(code: str, check: str) -> tuple[bool, str]:
    """Execute generated code plus assertions in a throwaway subprocess."""
    src = code + "\n\n" + check
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(src)
        path = fh.name
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=25)
        ok = proc.returncode == 0
        detail = "" if ok else (proc.stderr or proc.stdout)[-300:]
        return ok, detail
    except subprocess.TimeoutExpired:
        return False, "execution timed out (likely an infinite loop)"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        Path(path).unlink(missing_ok=True)


def check_json(text: str, required: list[str]) -> tuple[bool, str]:
    raw = text.strip()
    fences = re.findall(r"```(?:json)?\s*\n(.*?)```", raw, re.S)
    if fences:
        raw = fences[0].strip()
    # Tolerate prose wrapped around the object — extract the outermost braces.
    if not raw.startswith("{"):
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            raw = raw[i : j + 1]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, f"not valid JSON: {exc}"
    missing = [k for k in required if k not in obj]
    return (not missing), ("" if not missing else f"missing keys: {missing}")


# ---------------------------------------------------------------- the task suite

WEATHER_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current temperature for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}]

FILE_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from disk",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
]


def t_toolcall_simple(model: str) -> dict:
    r = chat(model, [{"role": "user", "content": "What's the temperature in Tokyo right now?"}],
             tools=WEATHER_TOOL)
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    calls = r["tool_calls"]
    if not calls:
        return {**r, "passed": False, "detail": "emitted no tool call"}
    fn = (calls[0].get("function") or {})
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {**r, "passed": False, "detail": "arguments were not valid JSON"}
    ok = fn.get("name") == "get_weather" and "tokyo" in str(args.get("city", "")).lower()
    return {**r, "passed": ok, "detail": "" if ok else f"wrong call: {fn.get('name')} {args}"}


def t_toolcall_select(model: str) -> dict:
    """Two tools available — pick the right one. Agents fail here constantly."""
    r = chat(model, [{"role": "user",
                      "content": "Show me what's inside /etc/hosts"}], tools=FILE_TOOLS)
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    calls = r["tool_calls"]
    if not calls:
        return {**r, "passed": False, "detail": "emitted no tool call"}
    name = (calls[0].get("function") or {}).get("name")
    ok = name == "read_file"
    return {**r, "passed": ok, "detail": "" if ok else f"chose {name}, expected read_file"}


def t_json_output(model: str) -> dict:
    r = chat(model, [{"role": "user", "content":
             "Return ONLY a JSON object describing a code review finding, with keys: "
             "file, line, severity, summary. Use any plausible values. No prose."}],
             fmt="json")
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    ok, detail = check_json(r["text"], ["file", "line", "severity", "summary"])
    return {**r, "passed": ok, "detail": detail}


def t_code_generate(model: str) -> dict:
    r = chat(model, [{"role": "user", "content":
             "Write a Python function `merge_intervals(intervals)` that merges overlapping "
             "intervals. Input is a list of [start, end] pairs, not necessarily sorted. "
             "Return the merged list sorted by start. Output only the function in a "
             "```python code block."}])
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    check = (
        "assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]\n"
        "assert merge_intervals([[1,4],[4,5]]) == [[1,5]]\n"
        "assert merge_intervals([]) == []\n"
        "assert merge_intervals([[5,6],[1,2]]) == [[1,2],[5,6]]\n"
    )
    ok, detail = run_python(extract_code(r["text"]), check)
    return {**r, "passed": ok, "detail": detail}


def t_code_repair(model: str) -> dict:
    buggy = (
        "def average(nums):\n"
        "    total = 0\n"
        "    for n in nums:\n"
        "        total += n\n"
        "    return total / len(nums)\n"
    )
    r = chat(model, [{"role": "user", "content":
             f"This function crashes with ZeroDivisionError on an empty list:\n\n"
             f"```python\n{buggy}```\n\n"
             "Fix it so an empty list returns 0. Keep the same name and behaviour "
             "otherwise. Output only the corrected function in a ```python block."}])
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    check = (
        "assert average([]) == 0\n"
        "assert average([2,4]) == 3\n"
        "assert average([5]) == 5\n"
    )
    ok, detail = run_python(extract_code(r["text"]), check)
    return {**r, "passed": ok, "detail": detail}


def t_instruction_adherence(model: str) -> dict:
    """Chatty models bolt on explanations and break machine parsing downstream."""
    r = chat(model, [{"role": "user", "content":
             "Reply with exactly the single word DONE. No punctuation, no explanation, "
             "no preamble."}])
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    ok = r["text"].strip().strip(".").upper() == "DONE"
    return {**r, "passed": ok, "detail": "" if ok else f"got: {r['text'][:80]!r}"}


def t_diff_reasoning(model: str) -> dict:
    """Read a diff and answer about it — the core of any review worker."""
    diff = (
        "--- a/auth.py\n+++ b/auth.py\n@@\n"
        "-def check(token):\n-    return token == SECRET\n"
        "+def check(token):\n+    return hmac.compare_digest(token, SECRET)\n"
    )
    r = chat(model, [{"role": "user", "content":
             f"Here is a diff:\n```\n{diff}```\n"
             "In one word, what class of vulnerability does this fix? "
             "Answer with only the word."}])
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    ans = r["text"].lower()
    ok = "timing" in ans or "side-channel" in ans or "side channel" in ans
    return {**r, "passed": ok, "detail": "" if ok else f"got: {r['text'][:80]!r}"}


# ---------------------------------------------------------------- vision

def _png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """Minimal PNG encoder.

    Written by hand rather than pulling in Pillow: this benchmark ships inside Synapse and
    has to run on any user's machine without an install step.
    """
    import struct
    import zlib

    h, w = len(pixels), len(pixels[0])
    raw = b"".join(
        b"\x00" + b"".join(struct.pack("3B", *px) for px in row) for row in pixels
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _quadrant_image() -> str:
    """224x224, four solid quadrants: red TL, green TR, blue BL, yellow BR."""
    import base64

    n = 224
    half = n // 2
    red, green, blue, yellow = (220, 20, 20), (20, 200, 20), (20, 20, 220), (240, 230, 30)
    rows = []
    for y in range(n):
        row = []
        for x in range(n):
            if y < half:
                row.append(red if x < half else green)
            else:
                row.append(blue if x < half else yellow)
        rows.append(row)
    return base64.b64encode(_png(rows)).decode("ascii")


def _count_image(count: int = 3) -> str:
    """White canvas with `count` black squares in a row."""
    import base64

    n = 224
    rows = [[(255, 255, 255)] * n for _ in range(n)]
    for i in range(count):
        x0 = 20 + i * 60
        for y in range(90, 140):
            for x in range(x0, x0 + 40):
                rows[y][x] = (0, 0, 0)
    return base64.b64encode(_png(rows)).decode("ascii")


def _vision_chat(model: str, prompt: str, image_b64: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        "options": {"temperature": 0},
    }
    t0 = time.time()
    try:
        data = _post("/api/chat", payload)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "wall_s": round(time.time() - t0, 2)}
    msg = data.get("message", {}) or {}
    ec, ed = data.get("eval_count") or 0, data.get("eval_duration") or 0
    return {
        "text": (msg.get("content") or "").strip(),
        "wall_s": round(time.time() - t0, 2),
        "tokens_out": ec,
        "tok_per_s": round(ec / (ed / 1e9), 1) if ed else None,
    }


def t_vision_color(model: str) -> dict:
    r = _vision_chat(model, "What colour is the top-left quarter of this image? "
                            "Answer with only the colour name.", _quadrant_image())
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    ok = "red" in r["text"].lower()
    return {**r, "passed": ok, "detail": "" if ok else f"got: {r['text'][:80]!r}"}


def t_vision_count(model: str) -> dict:
    r = _vision_chat(model, "How many black squares are in this image? "
                            "Answer with only the digit.", _count_image(3))
    if "error" in r:
        return {**r, "passed": False, "detail": r["error"]}
    ok = "3" in r["text"] or "three" in r["text"].lower()
    return {**r, "passed": ok, "detail": "" if ok else f"got: {r['text'][:80]!r}"}


VISION_TASKS: list[tuple[str, str, Callable[[str], dict]]] = [
    ("vision_color", "vision", t_vision_color),
    ("vision_count", "vision", t_vision_count),
]

# Models that accept images. Text-only models are not penalised for failing vision.
VISION_HINTS = ("llava", "vision", "moondream", "vl", "gemma3", "minicpm")


def is_vision_model(name: str) -> bool:
    return any(h in name.lower() for h in VISION_HINTS)


TASKS: list[tuple[str, str, Callable[[str], dict]]] = [
    ("tool_call_simple", "tool-calling", t_toolcall_simple),
    ("tool_call_select", "tool-calling", t_toolcall_select),
    ("json_output", "structured-output", t_json_output),
    ("code_generate", "coding", t_code_generate),
    ("code_repair", "coding", t_code_repair),
    ("instruction_adherence", "control", t_instruction_adherence),
    ("diff_reasoning", "review", t_diff_reasoning),
]


# ---------------------------------------------------------------- vram fit

def vram_fit(model: str) -> dict[str, Any]:
    """After a load, how much of the model sits on GPU vs spilled to CPU?

    A spill is the single biggest throughput cliff on a 6 GB card, so it is measured
    rather than assumed.
    """
    try:
        ps = _get("/api/ps")
    except Exception:  # noqa: BLE001
        return {}
    for m in ps.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            total = m.get("size") or 0
            on_gpu = m.get("size_vram") or 0
            return {
                "size_gb": round(total / 1e9, 2),
                "vram_gb": round(on_gpu / 1e9, 2),
                "fully_on_gpu": bool(total and on_gpu >= total * 0.99),
                "gpu_fraction": round(on_gpu / total, 3) if total else None,
            }
    return {}


# ---------------------------------------------------------------- runner

def installed_models() -> list[str]:
    tags = _get("/api/tags")
    return [m["name"] for m in tags.get("models", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    available = installed_models()
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        missing = [m for m in models if m not in available]
        if missing:
            print(f"not installed: {missing}\navailable: {available}")
            return 1
    else:
        # Skip embedding models — they cannot chat.
        models = [m for m in available if "embed" not in m.lower()]

    results: dict[str, Any] = {}
    if RESULTS.exists():
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
    results.setdefault("runs", {})

    print(f"benchmarking {len(models)} models x {len(TASKS)} tasks x {args.repeat} repeat\n")

    for model in models:
        print(f"--- {model} ---")
        # Warm up first: the initial call pays the cold load from disk into VRAM, which on
        # a 6 GB card can take minutes for a 7B and would otherwise be charged to whichever
        # task happened to run first.
        t_warm = time.time()
        warm = chat(model, [{"role": "user", "content": "hi"}])
        print(f"  (warmup/load {time.time() - t_warm:.1f}s"
              f"{', ERROR: ' + warm['error'] if 'error' in warm else ''})")

        entry = results["runs"].setdefault(model, {"tasks": {}})
        entry["load_s"] = round(time.time() - t_warm, 1)
        # Vision tasks only for models that accept images — a text-only model shouldn't be
        # scored down for lacking a capability it never claimed.
        suite = TASKS + (VISION_TASKS if is_vision_model(model) else [])
        entry["vision_capable"] = is_vision_model(model)
        for task_id, category, fn in suite:
            attempts = []
            for i in range(args.repeat):
                try:
                    res = fn(model)
                except Exception as exc:  # noqa: BLE001 - a crash is a data point, not a stop
                    res = {"passed": False, "detail": f"harness error: {exc}", "wall_s": 0}
                attempts.append(res)
                mark = "PASS" if res.get("passed") else "FAIL"
                extra = f" {res.get('tok_per_s')} tok/s" if res.get("tok_per_s") else ""
                print(f"  {task_id:24s} {mark} {res.get('wall_s', 0):6.1f}s{extra}"
                      f"{'  ' + res['detail'][:60] if res.get('detail') else ''}")
            passes = sum(1 for a in attempts if a.get("passed"))
            entry["tasks"][task_id] = {
                "category": category,
                "pass_rate": passes / len(attempts),
                "attempts": attempts,
            }
            # Persist after every task: a long run must survive an interrupt.
            RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")

        entry["vram"] = vram_fit(model)
        speeds = [a.get("tok_per_s") for t in entry["tasks"].values()
                  for a in t["attempts"] if a.get("tok_per_s")]
        entry["median_tok_per_s"] = round(sorted(speeds)[len(speeds) // 2], 1) if speeds else None
        entry["overall_pass_rate"] = round(
            sum(t["pass_rate"] for t in entry["tasks"].values()) / len(entry["tasks"]), 3)
        RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"  => {entry['overall_pass_rate']:.0%} pass, "
              f"{entry['median_tok_per_s']} tok/s median, "
              f"vram {entry['vram'].get('vram_gb')}GB "
              f"{'(fully on GPU)' if entry['vram'].get('fully_on_gpu') else '(SPILLED TO CPU)'}\n")

    print(f"results -> {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
