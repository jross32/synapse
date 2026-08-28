from __future__ import annotations

import ast
from pathlib import Path


def test_async_daemon_code_never_awaits_inside_storage_transaction() -> None:
    """A route must not hold Synapse's shared SQLite lock across an await.

    PTY/process operations publish events whose subscribers may open their own
    storage transaction. Holding the outer transaction while awaiting that work
    deadlocks the subscriber and therefore the original request.
    """

    daemon_dir = Path(__file__).resolve().parents[1] / "synapse_daemon"
    violations: list[str] = []
    for path in sorted(daemon_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)):
            for block in (node for node in ast.walk(function) if isinstance(node, ast.With)):
                is_storage_transaction = any(
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(item.context_expr.func, ast.Attribute)
                    and item.context_expr.func.attr == "transaction"
                    for item in block.items
                )
                if not is_storage_transaction:
                    continue
                await_lines = [node.lineno for node in ast.walk(block) if isinstance(node, ast.Await)]
                if await_lines:
                    violations.append(
                        f"{path.name}:{function.name}: transaction line {block.lineno} contains awaits {await_lines}"
                    )

    assert violations == [], "\n".join(violations)
