"""Second pass at the two escalated pieces, after fixing two faults in the harness.

Both first-round failures were partly my doing, and it would be dishonest to score them as
model limitations without correcting them first:

1. **The api piece was never told what `storage` actually exposes.** It invented
   `storage.user_exists()` and then re-invented it four times, because the repair prompt
   carried the error but not the interface. A human handed the same error with no module
   reference would guess too. The real interface is now extracted from the file on disk and
   included.

2. **The password test reported a bare `AssertionError`.** The bug was that
   `hash_password` emitted five `$`-separated fields while `verify_password` unpacked four,
   so every verification failed - and the model's own `try/except: return False` swallowed
   the ValueError that would have said so. The repair loop saw no signal at all. The tests
   now print what they got versus what they expected, so a repair has something to act on.

What this cannot fix is a model that ignores an explicit error. That part, if it recurs, is
a genuine limit and gets escalated.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

from build import HERE, LOG, build_piece, save_log
from build_all import API_SPEC, API_TEST, PW_SPEC


def public_interface(path: Path) -> str:
    """The signatures a caller can actually rely on, read from the file rather than assumed."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            args = ", ".join(a.arg for a in node.args.args)
            out.append(f"    {node.name}({args})")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append(f"    {t.id}")
    return "\n".join(out)


# ---- piece 1 again: the same spec, but a test that explains itself ------------------

PW_TEST_LOUD = """
from passwords import hash_password, verify_password

h = hash_password("correct horse battery")
assert isinstance(h, str) and "$" in h, f"hash_password returned {h!r}"
assert "correct horse battery" not in h, "the password appears in the hash"

parts = h.split("$")
ok = verify_password("correct horse battery", h)
assert ok is True, (
    f"verify_password returned {ok!r} for the CORRECT password.\\n"
    f"hash_password produced {len(parts)} fields separated by '$': {parts[:3]}...\\n"
    f"verify_password must unpack exactly that many fields. If it unpacks a different\\n"
    f"number, split() raises ValueError, your except clause returns False, and every\\n"
    f"login fails. Make the two functions agree on the format."
)
assert verify_password("wrong", h) is False, "a wrong password was accepted"
assert hash_password("x") != hash_password("x"), "salt is not random"

for junk in ["", "garbage", "a$b$c$d", "pbkdf2$sha256$notanint$aa$bb", None]:
    try:
        got = verify_password("x", junk)
    except Exception as e:
        raise AssertionError(f"verify_password({junk!r}) raised {type(e).__name__}: {e}. "
                             f"It must return False for malformed input, including None.")
    assert got is False, f"verify_password({junk!r}) returned {got!r}, expected False"
print("OK")
"""

if __name__ == "__main__":
    started = time.time()
    LOG["pieces"] = []
    LOG["escalations"] = []
    LOG["tokens_in"] = LOG["tokens_out"] = 0

    build_piece("passwords", PW_SPEC, PW_TEST_LOUD, HERE / "passwords.py")

    # Hand the api piece the interfaces it is expected to call, read off the real files.
    deps = "\n\n".join(
        f"Module `{name}` exposes exactly these, and nothing else:\n{public_interface(HERE / f'{name}.py')}"
        for name in ("passwords", "storage", "pages")
    )
    api_spec = (
        f"{API_SPEC}\n\n"
        f"IMPORTANT - the modules you import already exist. Call ONLY these functions. Do "
        f"not invent others; if something you want is missing, compose it from what is here.\n\n"
        f"{deps}"
    )
    build_piece("api", api_spec, API_TEST, HERE / "api.py")

    LOG["total_seconds"] = round(time.time() - started, 1)
    LOG["round"] = 2
    (HERE / "build_log_round2.json").write_text(
        __import__("json").dumps(LOG, indent=1), encoding="utf-8")
    ok = sum(1 for p in LOG["pieces"] if p["passed"])
    print(f"\nround 2: {ok}/2 passed, {LOG['tokens_out']} tokens out, {LOG['total_seconds']}s")
