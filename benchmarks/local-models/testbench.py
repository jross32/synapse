"""A scorecard for local models: six skills, sixty checks, every result machine-verified.

Why this exists. "Which local model is good?" is unanswerable in the abstract and very
answerable per skill: the model that writes the best code here is not the one that follows
formatting constraints best, and the one that calls tools most reliably writes stubs. A
single blended number hides exactly the information needed to assign a model to a job, so
this reports per-skill scores and only then a total.

The six skills mirror how models are actually evaluated in public work - execution-checked
coding (HumanEval/MBPP), repair from a real error, verifiable instruction constraints
(IFEval), function calling (BFCL), structured extraction, and short-chain reasoning -
because those are the axes that turn out to predict whether a model can hold a seat in a
squad.

Nothing here is judged by another model. Code is executed, JSON is parsed, constraints are
checked with code. A model cannot talk its way to a passing score.

Every run appends to history/ so the effect of a change - a new model, a different prompt,
a quantisation - is visible as a delta rather than a vibe.

    python testbench.py                          # every installed model, all skills
    python testbench.py --models qwen2.5-coder:3b
    python testbench.py --skills coding,tool_calling
    python testbench.py --compare                # table of the last N runs
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

OLLAMA = "http://127.0.0.1:11434"
HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history"


# --------------------------------------------------------------------------- test model


@dataclass
class Check:
    """One graded item.

    ``kind`` decides how the model is called and how the answer is graded:
      * ``code``  - answer is source; run ``asserts`` against it in a subprocess
      * ``text``  - answer is prose; ``grade`` inspects the string
      * ``tools`` - model is offered ``tools``; ``grade`` inspects the emitted call
    """

    id: str
    prompt: str
    kind: str = "text"
    asserts: str = ""
    grade: Callable[[str], bool] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    grade_call: Callable[[list[dict[str, Any]]], bool] | None = None
    weight: float = 1.0


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function",
            "function": {"name": name, "description": desc,
                         "parameters": {"type": "object", "properties": props,
                                        "required": required}}}


# --------------------------------------------------------------------------- the skills

def _code(cid: str, prompt: str, asserts: str) -> Check:
    return Check(id=cid, kind="code",
                 prompt=prompt + "\n\nOutput only the code in one ```python block.",
                 asserts=asserts)


CODING = [
    _code("even_sum", "Write sum_even(nums) returning the sum of even numbers in a list.",
          "from s import sum_even\nassert sum_even([1,2,3,4])==6\nassert sum_even([])==0\nassert sum_even([-2,-3])==-2"),
    _code("fizzbuzz", "Write fizzbuzz(n) returning a list of n strings: 'Fizz' for multiples of 3, "
                      "'Buzz' for 5, 'FizzBuzz' for both, otherwise the number as a string.",
          "from s import fizzbuzz\nr=fizzbuzz(15)\nassert len(r)==15\nassert r[2]=='Fizz' and r[4]=='Buzz' and r[14]=='FizzBuzz' and r[0]=='1'"),
    _code("roman", "Write to_roman(n) converting 1..3999 to a Roman numeral, subtractive form.",
          "from s import to_roman\nassert to_roman(4)=='IV' and to_roman(9)=='IX'\nassert to_roman(1987)=='MCMLXXXVII'\nassert to_roman(3999)=='MMMCMXCIX'"),
    _code("word_count", "Write word_count(text) -> dict of lowercased word to count. Split on "
                        "whitespace and strip surrounding punctuation.",
          "from s import word_count\nr=word_count('The cat, the CAT; a dog.')\nassert r.get('the')==2 and r.get('cat')==2 and r.get('dog')==1"),
    _code("flatten", "Write flatten(nested) that flattens an arbitrarily nested list of ints.",
          "from s import flatten\nassert flatten([1,[2,[3,[4]]],5])==[1,2,3,4,5]\nassert flatten([])==[]"),
    _code("binary_search", "Write binary_search(sorted_list, target) returning the index or -1.",
          "from s import binary_search\nassert binary_search([1,3,5,7,9],7)==3\nassert binary_search([1,3,5],4)==-1\nassert binary_search([],1)==-1"),
    _code("parse_duration", "Write parse_duration(text) turning '1h30m', '45s', '2h' into total "
                            "seconds as an int. Raise ValueError on unparseable input.",
          "from s import parse_duration\nassert parse_duration('1h30m')==5400\nassert parse_duration('45s')==45\n"
          "try:\n    parse_duration('nope'); raise SystemExit(1)\nexcept ValueError: pass"),
    _code("merge_intervals", "Write merge_intervals(intervals) merging overlapping [start,end] pairs, sorted.",
          "from s import merge_intervals\nassert merge_intervals([[1,3],[2,6],[8,10]])==[[1,6],[8,10]]\nassert merge_intervals([])==[]"),
    _code("is_balanced", "Write is_balanced(s) -> bool checking (), [] and {} are balanced and nested correctly.",
          "from s import is_balanced\nassert is_balanced('{[()]}')\nassert not is_balanced('{[(])}')\nassert is_balanced('')"),
    _code("chunk", "Write chunk(items, size) splitting a list into lists of at most size. "
                   "Raise ValueError if size < 1.",
          "from s import chunk\nassert chunk([1,2,3,4,5],2)==[[1,2],[3,4],[5]]\n"
          "try:\n    chunk([1],0); raise SystemExit(1)\nexcept ValueError: pass"),
]

DEBUGGING = [
    _code("fix_off_by_one",
          "This function should return the last element but raises IndexError. Fix it:\n"
          "```python\ndef last(xs):\n    return xs[len(xs)]\n```",
          "from s import last\nassert last([1,2,3])==3"),
    _code("fix_mutable_default",
          "This accumulates across calls, which is wrong. Fix it:\n"
          "```python\ndef add(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n```",
          "from s import add\nassert add(1)==[1]\nassert add(2)==[2], 'default must not persist'"),
    _code("fix_int_div",
          "average([1,2]) should be 1.5 but returns 1. Fix it:\n"
          "```python\ndef average(xs):\n    return sum(xs) // len(xs)\n```",
          "from s import average\nassert average([1,2])==1.5"),
    _code("fix_shadowing",
          "This raises TypeError. Fix it:\n"
          "```python\ndef total(list):\n    return list(sum(list))\n```",
          "from s import total\nassert total([1,2,3])==6"),
    _code("fix_key_error",
          "count_letters should not raise KeyError. Fix it:\n"
          "```python\ndef count_letters(s):\n    d={}\n    for c in s:\n        d[c]+=1\n    return d\n```",
          "from s import count_letters\nassert count_letters('aab')=={'a':2,'b':1}"),
    _code("fix_infinite_loop",
          "This never terminates. Fix it so it counts down to 0 and returns the count of steps:\n"
          "```python\ndef countdown(n):\n    steps=0\n    while n > 0:\n        steps+=1\n    return steps\n```",
          "from s import countdown\nassert countdown(3)==3\nassert countdown(0)==0"),
    _code("fix_string_compare",
          "This should be case-insensitive. Fix it:\n"
          "```python\ndef same(a,b):\n    return a==b\n```",
          "from s import same\nassert same('Hello','hello')\nassert not same('a','b')"),
    _code("fix_none_return",
          "sorted_copy should return a new sorted list, but returns None. Fix it:\n"
          "```python\ndef sorted_copy(xs):\n    return xs.sort()\n```",
          "from s import sorted_copy\nxs=[3,1,2]\nassert sorted_copy(xs)==[1,2,3]\nassert xs==[3,1,2], 'must not mutate input'"),
    _code("fix_range_bounds",
          "This should include both endpoints. Fix it:\n"
          "```python\ndef inclusive(a,b):\n    return list(range(a,b))\n```",
          "from s import inclusive\nassert inclusive(1,3)==[1,2,3]"),
    _code("fix_zero_div",
          "safe_ratio should return 0.0 instead of raising when b is 0. Fix it:\n"
          "```python\ndef safe_ratio(a,b):\n    return a/b\n```",
          "from s import safe_ratio\nassert safe_ratio(1,0)==0.0\nassert safe_ratio(3,2)==1.5"),
]


def _has_only_json(t: str) -> bool:
    t = t.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t).strip()
    try:
        json.loads(t)
        return True
    except Exception:  # noqa: BLE001
        return False


INSTRUCTION_FOLLOWING = [
    Check("exact_word", "Reply with exactly one word: the capital of France.",
          grade=lambda t: len(t.strip().strip(".").split()) == 1 and "paris" in t.lower()),
    Check("no_punctuation", "Write a sentence about the sea using no punctuation at all.",
          grade=lambda t: not any(c in t for c in ".,!?;:")),
    Check("uppercase", "Reply with the word 'ready' in all capital letters and nothing else.",
          grade=lambda t: t.strip().strip(".") == "READY"),
    Check("json_only", 'Reply with only this JSON and nothing else: {"ok": true}',
          grade=_has_only_json),
    Check("exact_count", "List exactly three colours, one per line, nothing else.",
          grade=lambda t: len([ln for ln in t.strip().splitlines() if ln.strip()]) == 3),
    Check("starts_with", "Begin your reply with the word BANANA, then explain gravity in one sentence.",
          grade=lambda t: t.strip().upper().startswith("BANANA")),
    Check("no_word", "Describe a cat in one sentence without using the letter 'e'.",
          grade=lambda t: "e" not in t.lower().split("\n")[0]),
    Check("max_chars", "Describe the ocean in fewer than 50 characters.",
          grade=lambda t: 0 < len(t.strip()) < 50),
    Check("numbered", "Give exactly two steps to boil water, numbered '1.' and '2.'.",
          grade=lambda t: "1." in t and "2." in t and "3." not in t),
    Check("refuse_extra", "Answer with only the number: what is 12 times 12?",
          grade=lambda t: t.strip().strip(".") == "144"),
]

def _final_number(expected: float) -> Callable[[str], bool]:
    """Grade on the last number in the reply.

    Substring matching is wrong in both directions: `"32" in text` passes on "1032", and
    checking only the opening characters fails a correct answer that arrives after a
    preamble - which is exactly how these models answer. "The next number is 32." was being
    scored wrong by a first-20-characters check while being completely correct.

    Taking the final number is the convention used by GSM8K-style scoring, because a model
    that reasons aloud puts its conclusion last.
    """
    def check(text: str) -> bool:
        nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
        if not nums:
            return False
        try:
            return abs(float(nums[-1]) - expected) < 1e-6
        except ValueError:
            return False
    return check


REASONING = [
    Check("apples", "I have 5 apples, eat 2, then buy 4 more. How many now? Answer with only the number.",
          grade=_final_number(7)),
    Check("older", "Tom is older than Ann. Ann is older than Sue. Who is youngest? One word.",
          grade=lambda t: "sue" in t.lower()),
    Check("cheaper", "A shirt is $20 after a 50% discount. What was the original price? Number only.",
          grade=_final_number(40)),
    Check("odd_one", "Which does not belong: dog, cat, hammer, horse? One word.",
          grade=lambda t: "hammer" in t.lower()),
    Check("days", "If today is Friday, what day is it in 10 days? One word.",
          grade=lambda t: "monday" in t.lower()),
    Check("remainder", "What is the remainder when 47 is divided by 5? Number only.",
          grade=_final_number(2)),
    Check("sequence", "Next number in 2, 4, 8, 16, ...? Number only.",
          grade=_final_number(32)),
    Check("negation", "If all bloops are razzies and no razzies are lazzies, can a bloop be a lazzie? "
                      "Answer yes or no.",
          grade=lambda t: t.strip().lower().startswith("no")),
    Check("units", "A car travels 120 km in 2 hours. What is its speed in km/h? Number only.",
          grade=_final_number(60)),
    Check("counting", "How many times does the letter 'r' appear in 'strawberry'? Number only.",
          grade=_final_number(3)),
]

STRUCTURED_OUTPUT = [
    Check("json_person",
          'Return JSON only: {"name": ..., "age": ...} for "Maya Patel is 34 years old."',
          grade=lambda t: _has_only_json(t) and "maya" in t.lower() and "34" in t),
    Check("json_list", 'Return JSON only: a list of the three largest planets as strings.',
          grade=lambda t: _has_only_json(t)),
    Check("extract_email", "Extract only the email address from: 'Contact bob.smith@acme.co.uk today.' "
                           "Reply with just the address.",
          grade=lambda t: t.strip().strip(".") == "bob.smith@acme.co.uk"),
    Check("extract_number", "Extract only the total from: 'Subtotal 12.50, tax 2.50, total 15.00'. "
                            "Reply with just the number.",
          grade=_final_number(15.0)),
    Check("csv_row", "Convert to one CSV row, no header: name Ada, role engineer, city Rome.",
          grade=lambda t: t.strip().count(",") == 2 and "Ada" in t),
    Check("key_value", "Return exactly 'status=ok' and nothing else.",
          grade=lambda t: t.strip() == "status=ok"),
    Check("json_nested", 'Return JSON only: {"user": {"id": 7, "tags": ["a","b"]}}',
          grade=lambda t: _has_only_json(t) and '"tags"' in t.replace("'", '"')),
    Check("date_iso", "Convert 'March 3, 2024' to ISO format YYYY-MM-DD. Reply with just the date.",
          grade=lambda t: "2024-03-03" in t),
    Check("bool_json", 'Is 10 greater than 4? Return only JSON: {"answer": true} or {"answer": false}',
          grade=lambda t: _has_only_json(t) and "true" in t.lower()),
    Check("split_names", "From 'Dr. Jane Q. Doe', return only the surname.",
          grade=lambda t: t.strip().strip(".").lower() == "doe"),
]

_WEATHER = _fn("get_weather", "Get current weather for a city.",
               {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["c", "f"]}}, ["city"])
_SEARCH = _fn("search_web", "Search the web.", {"query": {"type": "string"}}, ["query"])
_MAIL = _fn("send_email", "Send an email.",
            {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            ["to", "subject", "body"])
_FILE = _fn("read_file", "Read a file from disk.", {"path": {"type": "string"}}, ["path"])
_ADD = _fn("add_numbers", "Add two numbers.", {"a": {"type": "number"}, "b": {"type": "number"}}, ["a", "b"])
ALL_TOOLS = [_WEATHER, _SEARCH, _MAIL, _FILE, _ADD]


def _called(name: str, **args: Any) -> Callable[[list[dict[str, Any]]], bool]:
    def check(calls: list[dict[str, Any]]) -> bool:
        for c in calls:
            fn = c.get("function", {})
            if fn.get("name") != name:
                continue
            got = fn.get("arguments") or {}
            if isinstance(got, str):
                try:
                    got = json.loads(got)
                except Exception:  # noqa: BLE001
                    return False
            return all(str(got.get(k, "")).lower().find(str(v).lower()) >= 0 for k, v in args.items())
        return False
    return check


def _no_call() -> Callable[[list[dict[str, Any]]], bool]:
    return lambda calls: not calls


TOOL_CALLING = [
    Check("weather_basic", "What's the weather in Paris?", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("get_weather", city="paris")),
    Check("weather_unit", "Weather in Tokyo in fahrenheit?", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("get_weather", city="tokyo", unit="f")),
    Check("search_pick", "Search the web for the tallest building.", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("search_web")),
    Check("email_all_args", "Email sam@x.com with subject Hello and body See you Tuesday.",
          kind="tools", tools=ALL_TOOLS, grade_call=_called("send_email", to="sam@x.com")),
    Check("read_file", "Read the file config.yaml.", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("read_file", path="config.yaml")),
    Check("math_tool", "Use a tool to add 21 and 21.", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("add_numbers")),
    Check("no_tool_needed", "Say hello back to me. Do not use any tool.", kind="tools",
          tools=ALL_TOOLS, grade_call=_no_call()),
    Check("pick_right_of_many", "I need the contents of notes.txt.", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("read_file", path="notes.txt")),
    Check("no_hallucinated_tool", "Delete every file on the disk.", kind="tools", tools=ALL_TOOLS,
          # There is no delete tool; inventing one is the failure being tested for.
          grade_call=lambda calls: all(
              c.get("function", {}).get("name") in {t["function"]["name"] for t in ALL_TOOLS}
              for c in calls)),
    Check("weather_then_city", "Is it raining in Berlin right now?", kind="tools", tools=ALL_TOOLS,
          grade_call=_called("get_weather", city="berlin")),
]

SKILLS: dict[str, list[Check]] = {
    "coding": CODING,
    "debugging": DEBUGGING,
    "instruction_following": INSTRUCTION_FOLLOWING,
    "reasoning": REASONING,
    "structured_output": STRUCTURED_OUTPUT,
    "tool_calling": TOOL_CALLING,
}


# --------------------------------------------------------------------------- execution


def call_model(model: str, prompt: str, tools: list[dict[str, Any]] | None = None,
               timeout: float = 180.0) -> tuple[str, list[dict[str, Any]], dict[str, int], float]:
    """Returns (text, tool_calls, token_counts, seconds). Never raises."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    if tools:
        payload["tools"] = tools
    started = time.time()
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 400 here almost always means "this model has no tools template" - a real,
        # reportable capability gap rather than a harness bug.
        return f"__HTTP_{exc.code}__", [], {}, round(time.time() - started, 2)
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__ {type(exc).__name__}", [], {}, round(time.time() - started, 2)

    msg = body.get("message", {}) or {}
    tokens = {"in": body.get("prompt_eval_count", 0) or 0,
              "out": body.get("eval_count", 0) or 0}
    return msg.get("content", "") or "", msg.get("tool_calls", []) or [], tokens, \
        round(time.time() - started, 2)


def extract_code(text: str) -> str:
    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (max(fences, key=len) if fences else text).strip()


def run_code_check(code: str, asserts: str) -> bool:
    d = Path(tempfile.mkdtemp())
    (d / "s.py").write_text(code, encoding="utf-8")
    (d / "t.py").write_text(asserts + "\nprint('OK')\n", encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, "t.py"], capture_output=True, text=True,
                              timeout=25, cwd=str(d))
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def grade(model: str, check: Check) -> dict[str, Any]:
    text, calls, tokens, secs = call_model(
        model, check.prompt, check.tools if check.kind == "tools" else None)

    unsupported = text.startswith("__HTTP_400")
    if check.kind == "code":
        passed = run_code_check(extract_code(text), check.asserts)
    elif check.kind == "tools":
        passed = bool(check.grade_call and check.grade_call(calls))
    else:
        passed = bool(check.grade and check.grade(text))

    return {"id": check.id, "passed": passed, "seconds": secs,
            "tokens_in": tokens.get("in", 0), "tokens_out": tokens.get("out", 0),
            "unsupported": unsupported}


def run_model(model: str, skills: list[str]) -> dict[str, Any]:
    per_skill: dict[str, Any] = {}
    for skill in skills:
        results = []
        for check in SKILLS[skill]:
            r = grade(model, check)
            results.append(r)
            mark = "PASS" if r["passed"] else ("N/A " if r["unsupported"] else "FAIL")
            print(f"    {skill:22s} {check.id:20s} {mark} {r['seconds']:6.1f}s "
                  f"{r['tokens_out']:5d} tok", flush=True)
        graded = [r for r in results if not r["unsupported"]]
        per_skill[skill] = {
            "score": round(sum(r["passed"] for r in graded) / len(graded), 3) if graded else None,
            "unsupported": len(graded) != len(results),
            "seconds": round(sum(r["seconds"] for r in results), 1),
            "tokens_out": sum(r["tokens_out"] for r in results),
            "results": results,
        }
    scored = [v["score"] for v in per_skill.values() if v["score"] is not None]
    return {
        "model": model,
        "skills": per_skill,
        "total_score": round(statistics.mean(scored), 3) if scored else None,
        "total_seconds": round(sum(v["seconds"] for v in per_skill.values()), 1),
        "total_tokens_out": sum(v["tokens_out"] for v in per_skill.values()),
    }


# --------------------------------------------------------------------------- reporting


def write_scorecard(run: dict[str, Any]) -> None:
    skills = list(SKILLS)
    rows = sorted(run["models"], key=lambda m: -(m["total_score"] or -1))
    L = ["# Local model scorecard\n",
         f"_{run['started']} · {run['host']['gpu'] or 'CPU only'} · "
         f"{run['host']['vram_gb']} GB VRAM_\n",
         "Every result is machine-verified: code is executed, JSON is parsed, tool calls are",
         "inspected. No model grades another, so nothing here can be talked into a pass.\n",
         "| Model | Overall | " + " | ".join(s.replace("_", " ") for s in skills) + " | tok out | time |",
         "|---|---:|" + "---:|" * len(skills) + "---:|---:|"]
    for m in rows:
        cells = []
        for s in skills:
            v = m["skills"].get(s, {})
            cells.append("n/a" if v.get("score") is None else f"{v['score']:.0%}")
        total = "n/a" if m["total_score"] is None else f"**{m['total_score']:.0%}**"
        L.append(f"| `{m['model']}` | {total} | " + " | ".join(cells) +
                 f" | {m['total_tokens_out']} | {m['total_seconds']:.0f}s |")

    L += ["", "## Reading this\n",
          "`n/a` means the model could not be graded on that skill at all - for tool calling it",
          "means Ollama returned HTTP 400, because coder-tuned models ship without a tools",
          "template. That is a real capability gap, not a low score, and it is why the coding",
          "leader cannot hold a seat that has to call tools.\n",
          "Pick per skill, not by the overall column. The best coder here is usually not the best",
          "instruction-follower, and a squad wants the right specialist in each seat.\n"]
    (HERE / "SCORECARD.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def compare_history(limit: int = 10) -> None:
    files = sorted(HISTORY.glob("*.json"))[-limit:]
    if not files:
        print("no history yet")
        return
    print(f"{'run':<22}{'model':<26}{'total':>7}{'tok':>8}")
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for m in sorted(data["models"], key=lambda x: -(x["total_score"] or -1))[:3]:
            score = "n/a" if m["total_score"] is None else f"{m['total_score']:.0%}"
            print(f"{data['started'][:19]:<22}{m['model']:<26}{score:>7}{m['total_tokens_out']:>8}")


def installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    skip = ("embed",)  # embedding models have no chat surface to grade
    return [m["name"] for m in data.get("models", [])
            if not any(s in m["name"] for s in skip)]


def host_info() -> dict[str, Any]:
    gpu, vram = None, 0.0
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            name, mem = out.stdout.strip().splitlines()[0].split(",")
            gpu, vram = name.strip(), round(int(re.sub(r"\D", "", mem)) / 1024, 1)
    except Exception:  # noqa: BLE001
        pass
    return {"gpu": gpu, "vram_gb": vram}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="", help="comma-separated; default every installed model")
    ap.add_argument("--skills", default="", help=f"comma-separated from: {','.join(SKILLS)}")
    ap.add_argument("--compare", action="store_true", help="show recent runs and exit")
    args = ap.parse_args()

    if args.compare:
        compare_history()
        return

    skills = [s.strip() for s in args.skills.split(",") if s.strip()] or list(SKILLS)
    unknown = [s for s in skills if s not in SKILLS]
    if unknown:
        raise SystemExit(f"unknown skills: {unknown}. choose from {list(SKILLS)}")

    models = [m.strip() for m in args.models.split(",") if m.strip()] or installed_models()
    if not models:
        raise SystemExit("no models found - is Ollama running on 11434?")

    total_checks = sum(len(SKILLS[s]) for s in skills)
    print(f"{len(models)} models x {total_checks} checks across {len(skills)} skills\n")

    run = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "host": host_info(),
           "skills": skills, "models": []}
    for model in models:
        print(f"=== {model} ===", flush=True)
        result = run_model(model, skills)
        total = "n/a" if result["total_score"] is None else f"{result['total_score']:.0%}"
        print(f"  -> overall {total}, {result['total_tokens_out']} tokens, "
              f"{result['total_seconds']:.0f}s\n", flush=True)
        run["models"].append(result)

        # Persist after every model: a long sweep that dies at model nine should not lose
        # the eight already measured.
        HISTORY.mkdir(exist_ok=True)
        stamp = run["started"].replace(":", "-")
        (HISTORY / f"{stamp}.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
        write_scorecard(run)

    print(f"scorecard -> {HERE / 'SCORECARD.md'}")


if __name__ == "__main__":
    main()
