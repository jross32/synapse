"""Arm B: build Trailmark with local models doing as much of the writing as possible.

The rules of this arm, so the comparison stays honest:

* Every line of application code is written by a local model. Claude writes the
  decomposition, the acceptance tests, and this orchestrator - but not the app.
* Each piece is accepted only when its own test passes. A piece that cannot be made to
  pass locally after N repairs is recorded as an escalation, and Claude writes that piece.
* Everything is logged: tokens per piece, repairs per piece, and exactly which pieces
  needed escalating. The escalation count is the real result of this experiment - it is
  the answer to "how much of this could actually be handed off?"

The decomposition is deliberate rather than incidental. The measured playbook says small
models succeed at narrow verifiable jobs and fail at broad ones, so asking for "a
full-stack app" in one shot would be testing a strawman. Each piece here is small enough
to have an obvious right answer and a test that proves it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OLLAMA = "http://127.0.0.1:11434"
CODER = "qwen2.5-coder:7b"      # 80% coding, and the pipeline repairs what it misses
MAX_REPAIRS = 4

LOG: dict[str, Any] = {"pieces": [], "tokens_in": 0, "tokens_out": 0,
                       "escalations": [], "started": time.strftime("%H:%M:%S")}


def generate(prompt: str, timeout: float = 600.0) -> tuple[str, int, int]:
    """One local completion. Returns (text, tokens_in, tokens_out)."""
    payload = {"model": CODER, "messages": [{"role": "user", "content": prompt}],
               "stream": False, "options": {"temperature": 0, "num_ctx": 8192}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return (body["message"]["content"],
            body.get("prompt_eval_count", 0) or 0,
            body.get("eval_count", 0) or 0)


def extract(text: str, lang: str = "python") -> str:
    import re
    fences = re.findall(rf"```(?:{lang}|py|html|javascript|js)?\s*\n(.*?)```", text, re.S)
    return (max(fences, key=len) if fences else text).strip()


def build_piece(name: str, spec: str, test_code: str, out_file: Path,
                lang: str = "python") -> bool:
    """Generate one piece, then repair it from real test output until it passes."""
    print(f"\n=== {name} ===", flush=True)
    started = time.time()
    tin = tout = 0
    repairs = 0

    text, a, b = generate(spec)
    tin += a; tout += b
    code = extract(text, lang)
    out_file.write_text(code, encoding="utf-8")

    test_file = HERE / f"_test_{name}.py"
    test_file.write_text(test_code, encoding="utf-8")

    passed = False
    error = ""
    for attempt in range(MAX_REPAIRS + 1):
        proc = subprocess.run([sys.executable, test_file.name], capture_output=True,
                              text=True, timeout=120, cwd=str(HERE))
        if proc.returncode == 0:
            passed = True
            break
        error = (proc.stderr or proc.stdout)[-1200:]
        if attempt == MAX_REPAIRS:
            break
        repairs += 1
        print(f"  repair {repairs}: {error.strip().splitlines()[-1][:90] if error.strip() else ''}",
              flush=True)
        text, a, b = generate(
            f"{spec}\n\nYour previous attempt:\n```python\n{code}\n```\n\n"
            f"Running the tests produced this error:\n```\n{error}\n```\n\n"
            "Fix the code so the tests pass. Output only the corrected code.")
        tin += a; tout += b
        code = extract(text, lang)
        out_file.write_text(code, encoding="utf-8")

    test_file.unlink(missing_ok=True)
    LOG["tokens_in"] += tin
    LOG["tokens_out"] += tout
    LOG["pieces"].append({"name": name, "passed": passed, "repairs": repairs,
                          "tokens_in": tin, "tokens_out": tout,
                          "seconds": round(time.time() - started, 1),
                          "chars": len(code)})
    if not passed:
        LOG["escalations"].append({"piece": name, "last_error": error[-400:]})
    print(f"  -> {'PASS' if passed else 'ESCALATE'} after {repairs} repair(s), "
          f"{tout} tokens out, {time.time() - started:.0f}s", flush=True)
    return passed


def save_log() -> None:
    LOG["finished"] = time.strftime("%H:%M:%S")
    (HERE / "build_log.json").write_text(json.dumps(LOG, indent=1), encoding="utf-8")


if __name__ == "__main__":
    print("this module is driven by build_all.py")
