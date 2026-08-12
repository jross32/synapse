"""Assertions that explain themselves, because a repair loop can only act on what it is told.

Measured, not assumed. In the build-off a password module failed five times in a row. The
bug was that ``hash_password`` emitted five ``$``-separated fields while ``verify_password``
unpacked four, so every verification failed - and the model's own ``try/except: return False``
swallowed the ValueError that would have explained it. The repair loop saw the string
``AssertionError`` and nothing else, and repeated the same mistake four times.

Rewriting one test to print what it got, what it expected, and a hint about the likely cause
fixed it in **one** repair. That is the entire justification for this module: a bare
``assert x == y`` throws away exactly the information the next attempt needs.

Every helper here renders got-versus-expected, and takes an optional ``hint`` for the failure
mode that is actually likely - which is usually worth more than the comparison itself.
"""

from __future__ import annotations

from typing import Any


def _render(got: Any, want: Any, hint: str = "") -> str:
    got_repr, want_repr = repr(got), repr(want)
    if len(got_repr) > 400:
        got_repr = got_repr[:400] + "...[truncated]"
    lines = [f"  expected: {want_repr}", f"  actually got: {got_repr}"]
    if hint:
        lines.append(f"  likely cause: {hint}")
    return "\n".join(lines)


def equals(got: Any, want: Any, what: str, hint: str = "") -> None:
    if got != want:
        raise AssertionError(f"{what} is wrong.\n{_render(got, want, hint)}")


def is_true(got: Any, what: str, hint: str = "") -> None:
    if not got:
        raise AssertionError(f"{what} should be true.\n{_render(got, True, hint)}")


def is_false(got: Any, what: str, hint: str = "") -> None:
    if got:
        raise AssertionError(f"{what} should be false.\n{_render(got, False, hint)}")


def contains(haystack: Any, needle: Any, what: str, hint: str = "") -> None:
    if needle not in haystack:
        preview = repr(haystack)
        if len(preview) > 300:
            preview = preview[:300] + "...[truncated]"
        raise AssertionError(
            f"{what} does not contain {needle!r}.\n  searched: {preview}"
            + (f"\n  likely cause: {hint}" if hint else ""))


def status_is(got: int, want: int, what: str, hint: str = "") -> None:
    """HTTP status with the meaning spelled out, since the number alone teaches nothing."""
    if got != want:
        meaning = {
            200: "OK", 201: "Created", 204: "No Content",
            400: "Bad Request", 401: "Unauthorized - no or invalid credentials",
            403: "Forbidden - authenticated but not allowed",
            404: "Not Found", 409: "Conflict - already exists",
            422: "Unprocessable - request body failed validation",
            500: "Internal Server Error - the handler raised",
        }
        extra = hint
        if got >= 500 and not hint:
            extra = ("a 5xx means the handler raised an exception. Bad input should be "
                     "rejected with a 4xx by validation, never crash the endpoint.")
        raise AssertionError(
            f"{what} returned {got} ({meaning.get(got, '?')}) but should return "
            f"{want} ({meaning.get(want, '?')})."
            + (f"\n  likely cause: {extra}" if extra else ""))


def does_not_raise(fn: Any, *args: Any, what: str = "call", hint: str = "") -> Any:
    """Prove a function degrades instead of exploding - the malformed-input contract."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"{what} raised {type(exc).__name__}: {exc}\n"
            f"  it must handle this input and return a value instead of raising."
            + (f"\n  likely cause: {hint}" if hint else "")) from exc


def fields_match(got: dict[str, Any], want_keys: list[str], what: str) -> None:
    """Catch the exact failure that broke the build-off dashboard.

    One module returned ``distance_km`` and its consumer read ``distance``. Naming the missing
    key *and* listing what was actually present turns a silent ``undefined`` into a one-line
    fix.
    """
    missing = [k for k in want_keys if k not in got]
    if missing:
        raise AssertionError(
            f"{what} is missing {missing}.\n"
            f"  it returned these keys: {sorted(got)}\n"
            f"  likely cause: the producer and the consumer disagree about field names. "
            f"Whatever the contract says is correct - change this to match it.")
