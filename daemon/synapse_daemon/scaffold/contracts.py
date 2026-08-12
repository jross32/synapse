"""Shared contracts, so independently-generated modules cannot disagree about each other.

The build-off failed this way twice. One module returned ``distance_km`` while the module
that consumed it read ``distance``; each passed its own test in isolation and the dashboard
rendered nothing. Another invented ``storage.user_exists()`` and re-invented it four times,
because the repair prompt carried the error but never the interface it was calling against.

Neither is a reasoning failure. A model writing one piece cannot see the others, so the
information simply was not there. This module supplies it:

* ``public_interface`` reads the real signatures off a generated file, so downstream prompts
  describe what exists rather than what was hoped for.
* ``check_contract`` fails a piece whose signatures drift from the declaration, *inside* the
  repair loop, where drift is cheap to fix instead of showing up in the browser.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionSpec:
    name: str
    args: list[str] = field(default_factory=list)
    returns: str = ""
    doc: str = ""

    def signature(self) -> str:
        arrow = f" -> {self.returns}" if self.returns else ""
        return f"{self.name}({', '.join(self.args)}){arrow}"


@dataclass
class ModuleContract:
    """What one module promises to expose. The single source of truth for its callers."""

    module: str
    purpose: str = ""
    functions: list[FunctionSpec] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)

    def as_prompt(self) -> str:
        lines = [f"Module `{self.module}`" + (f" - {self.purpose}" if self.purpose else ""),
                 "must expose exactly these, and nothing else is guaranteed to exist:"]
        for fn in self.functions:
            lines.append(f"    {fn.signature()}" + (f"   # {fn.doc}" if fn.doc else ""))
        for const in self.constants:
            lines.append(f"    {const}")
        return "\n".join(lines)


def public_interface(path: Path) -> ModuleContract:
    """Read the real interface off a file, rather than trusting what it was asked to be."""
    contract = ModuleContract(module=path.stem)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return contract

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            returns = ast.unparse(node.returns) if node.returns else ""
            doc = (ast.get_docstring(node) or "").splitlines()
            contract.functions.append(FunctionSpec(
                name=node.name,
                args=[a.arg for a in node.args.args],
                returns=returns,
                doc=doc[0] if doc else ""))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    contract.constants.append(target.id)
    return contract


def check_contract(path: Path, expected: ModuleContract) -> list[str]:
    """Differences between what a module promised and what it actually exposes.

    Names *and* argument lists are compared: a function that exists with the wrong parameters
    is exactly the ``distance`` / ``distance_km`` class of failure, and matching on name alone
    would wave it through.
    """
    actual = public_interface(path)
    actual_by_name = {f.name: f for f in actual.functions}
    problems: list[str] = []

    for want in expected.functions:
        got = actual_by_name.get(want.name)
        if got is None:
            close = [n for n in actual_by_name if n.lower() == want.name.lower()]
            hint = f" (found {close[0]!r} - check the spelling)" if close else ""
            problems.append(
                f"{path.name} does not define `{want.signature()}`{hint}. "
                f"It defines: {sorted(actual_by_name) or 'nothing public'}")
            continue
        if want.args and got.args != want.args:
            problems.append(
                f"{path.name}.{want.name} takes {got.args} but the contract says "
                f"{want.args}. The callers were written against the contract, so this "
                f"signature must match it exactly.")

    for const in expected.constants:
        if const not in actual.constants:
            problems.append(f"{path.name} does not define the constant `{const}`.")
    return problems


def contract_test_source(module: str, expected: ModuleContract) -> str:
    """A standalone test asserting a module matches its contract.

    Emitted as a file the pipeline runs like any other acceptance test, so contract drift
    produces the same kind of actionable failure as a wrong return value.
    """
    checks = []
    for fn in expected.functions:
        checks.append(
            f"assert hasattr(m, {fn.name!r}), "
            f"'{module}.{fn.name} is missing; the contract requires {fn.signature()}'")
        if fn.args:
            checks.append(
                f"assert list(inspect.signature(m.{fn.name}).parameters)[:{len(fn.args)}] == {fn.args!r}, \\\n"
                f"    '{module}.{fn.name} parameters are ' + str(list(inspect.signature(m.{fn.name}).parameters)) + \\\n"
                f"    ' but the contract requires {fn.args!r}'")
    for const in expected.constants:
        checks.append(f"assert hasattr(m, {const!r}), '{module} must define {const}'")

    body = "\n".join(checks)
    return f"""import inspect
import {module} as m

{body}
print('OK')
"""
