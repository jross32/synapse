"""Inspect the top-level modules of a Python application without importing it."""

import ast
from pathlib import Path
from typing import Any


def _first_doc_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node, clean=True) or ''
    lines = doc.splitlines()
    return lines[0] if lines else ''


def _assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_assigned_names(item))
        return names
    return []


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    comparison = node.test
    if len(comparison.ops) != 1 or not isinstance(comparison.ops[0], ast.Eq):
        return False
    if len(comparison.comparators) != 1:
        return False

    left = comparison.left
    right = comparison.comparators[0]
    name_on_left = isinstance(left, ast.Name) and left.id == '__name__'
    name_on_right = isinstance(right, ast.Name) and right.id == '__name__'
    main_on_left = isinstance(left, ast.Constant) and left.value == '__main__'
    main_on_right = isinstance(right, ast.Constant) and right.value == '__main__'
    return (name_on_left and main_on_right) or (main_on_left and name_on_right)


def _local_imports(tree: ast.Module, module: str, local_modules: set[str]) -> list[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name.split('.')[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module is None:
                candidates = [alias.name.split('.')[0] for alias in node.names]
            elif node.module:
                candidates = [node.module.split('.')[0]]
            else:
                candidates = []
        else:
            continue
        imports.update(
            candidate
            for candidate in candidates
            if candidate in local_modules and candidate != module
        )
    return sorted(imports)


def _scan_module(path: Path, local_modules: set[str]) -> dict[str, Any] | None:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (OSError, UnicodeError, SyntaxError, ValueError):
        return None

    functions: list[dict[str, Any]] = []
    constants: list[str] = []
    seen_constants: set[str] = set()
    has_main = False

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == 'main':
                has_main = True
            if not node.name.startswith('_'):
                positional = [*node.args.posonlyargs, *node.args.args]
                functions.append({
                    'name': node.name,
                    'args': [arg.arg for arg in positional if arg.arg != 'self'],
                    'doc': _first_doc_line(node),
                })
        elif isinstance(node, ast.Assign):
            names: list[str] = []
            for target in node.targets:
                names.extend(_assigned_names(target))
            for name in names:
                if name.isupper() and name not in seen_constants:
                    constants.append(name)
                    seen_constants.add(name)
        elif isinstance(node, ast.AnnAssign):
            for name in _assigned_names(node.target):
                if name.isupper() and name not in seen_constants:
                    constants.append(name)
                    seen_constants.add(name)

        if _is_main_guard(node):
            has_main = True

    return {
        'module': path.stem,
        'path': path.name,
        'doc': _first_doc_line(tree),
        'functions': functions,
        'constants': constants,
        'imports_local': _local_imports(tree, path.stem, local_modules),
        'is_entrypoint': has_main,
    }


def scan_build(directory) -> list[dict]:
    """Return a structural summary of the Python modules directly in directory."""
    try:
        root = Path(directory)
        if not root.is_dir():
            return []

        all_python = [path for path in root.iterdir() if path.is_file() and path.suffix == '.py']
        local_modules = {path.stem for path in all_python}
        candidates = [
            path
            for path in all_python
            if not path.name.startswith(('_', 'test_'))
            and not path.name.endswith('_test.py')
            and path.name not in {'conftest.py', 'setup.py'}
        ]

        results = []
        for path in candidates:
            result = _scan_module(path, local_modules)
            if result is not None:
                results.append(result)
        return sorted(results, key=lambda item: item['module'])
    except Exception:
        return []
