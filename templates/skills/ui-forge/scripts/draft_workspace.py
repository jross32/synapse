from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "ui-forge-draft-v1"
EXCLUDED_DIRS = {
    ".git",
    ".synapse",
    "node_modules",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "__pycache__",
}
RISK_PREFIXES = (
    "server/",
    "backend/",
    "api/",
    "functions/",
    "database/",
    "db/",
    "migrations/",
    "prisma/",
    "supabase/",
    "alembic/",
)
RISK_FILENAMES = {
    "schema.sql",
    "prisma/schema.prisma",
}
EXCLUDED_FILE_SUFFIXES = {".log", ".pid", ".pyc", ".pyo"}
EXCLUDED_FILE_NAMES = {"Thumbs.db", ".DS_Store"}

TEXT_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".sass", ".less",
    ".html", ".htm", ".json", ".jsonc", ".md", ".mdx", ".txt", ".yaml", ".yml",
    ".toml", ".xml", ".svg", ".vue", ".svelte", ".astro", ".py", ".rb", ".php",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:48] or "draft"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _draft_root(project_root: Path) -> Path:
    return project_root / ".synapse" / "ui-forge" / "drafts"


def _manifest_path(project_root: Path, draft_id: str) -> Path:
    return _draft_root(project_root) / draft_id / "manifest.json"


def _safe_relative(root: Path, relative: str) -> Path:
    normalized = Path(relative.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"unsafe project-relative path: {relative}")
    target = (root / normalized).resolve()
    target.relative_to(root.resolve())
    return target


def _iter_project_files(project_root: Path):
    for current, dirs, files in os.walk(project_root):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
        for name in files:
            path = current_path / name
            if name in EXCLUDED_FILE_NAMES or path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
                continue
            relative = path.relative_to(project_root).as_posix()
            if any(part in EXCLUDED_DIRS for part in Path(relative).parts):
                continue
            if path.is_symlink():
                continue
            yield relative, path


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _snapshot(project_root: Path, target: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative, source in _iter_project_files(project_root):
        destination = target / relative
        _copy_file(source, destination)
        hashes[relative] = _sha256(source)
    return hashes


def create_draft(project_root: str | Path, title: str) -> dict[str, Any]:
    project = Path(project_root).resolve()
    if not project.is_dir():
        raise ValueError(f"project root does not exist: {project}")
    draft_id = f"{_slug(title)}-{uuid.uuid4().hex[:8]}"
    root = _draft_root(project) / draft_id
    base = root / "base"
    workspace = root / "workspace"
    root.mkdir(parents=True, exist_ok=False)
    hashes = _snapshot(project, base)
    shutil.copytree(base, workspace)
    payload = {
        "schema": SCHEMA,
        "id": draft_id,
        "title": title.strip() or "Draft",
        "project_root": str(project),
        "created_at": _now(),
        "updated_at": _now(),
        "status": "open",
        "base_file_count": len(hashes),
        "base_hashes": hashes,
        "workspace": str(workspace),
        "base": str(base),
        "accepted_at": None,
        "accepted_paths": [],
    }
    (root / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**payload, "live_untouched": True}


def _load(project_root: Path, draft_id: str) -> dict[str, Any]:
    path = _manifest_path(project_root, draft_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"unknown UI Forge draft: {draft_id}") from exc
    if payload.get("schema") != SCHEMA or payload.get("id") != draft_id:
        raise ValueError(f"invalid UI Forge draft manifest: {draft_id}")
    return payload


def _file_map(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
        for name in files:
            path = current_path / name
            if name in EXCLUDED_FILE_NAMES or path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
                continue
            if path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            out[relative] = _sha256(path)
    return out


def _changes(payload: dict[str, Any]) -> dict[str, list[str]]:
    base_root = Path(payload["base"])
    workspace_root = Path(payload["workspace"])
    base = _file_map(base_root)
    work = _file_map(workspace_root)
    base_keys = set(base)
    work_keys = set(work)
    return {
        "added": sorted(work_keys - base_keys),
        "deleted": sorted(base_keys - work_keys),
        "modified": sorted(key for key in base_keys & work_keys if base[key] != work[key]),
    }


def _risk_reason(relative: str) -> str | None:
    normalized = relative.replace("\\", "/").lstrip("/")
    lower = normalized.lower()
    name = Path(lower).name
    if name == ".env" or name.startswith(".env."):
        return "environment/secrets file"
    if lower in RISK_FILENAMES:
        return "database/schema file"
    if any(lower.startswith(prefix) or f"/{prefix}" in lower for prefix in RISK_PREFIXES):
        return "backend/database/auth-adjacent path"
    return None


def draft_status(project_root: str | Path, draft_id: str) -> dict[str, Any]:
    project = Path(project_root).resolve()
    payload = _load(project, draft_id)
    changes = _changes(payload)
    all_changed = changes["added"] + changes["deleted"] + changes["modified"]
    risky = [
        {"path": relative, "reason": reason}
        for relative in all_changed
        if (reason := _risk_reason(relative)) is not None
    ]
    return {
        "schema": SCHEMA,
        "id": draft_id,
        "title": payload["title"],
        "status": payload["status"],
        "workspace": payload["workspace"],
        "base": payload["base"],
        "changes": changes,
        "changed_count": len(all_changed),
        "risky_changes": risky,
        "accept_requires_explicit_risky_override": bool(risky),
        "live_untouched": payload["status"] == "open",
    }


def _read_text(path: Path) -> list[str] | None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (UnicodeDecodeError, OSError):
        return None


def draft_diff(project_root: str | Path, draft_id: str, max_chars: int = 60_000) -> dict[str, Any]:
    project = Path(project_root).resolve()
    payload = _load(project, draft_id)
    changes = _changes(payload)
    base = Path(payload["base"])
    workspace = Path(payload["workspace"])
    chunks: list[str] = []
    binary: list[str] = []
    for relative in changes["deleted"] + changes["modified"] + changes["added"]:
        left_path = base / relative
        right_path = workspace / relative
        left = _read_text(left_path) if left_path.exists() else []
        right = _read_text(right_path) if right_path.exists() else []
        if left is None or right is None:
            binary.append(relative)
            continue
        chunks.extend(
            difflib.unified_diff(
                left,
                right,
                fromfile=f"live-base/{relative}",
                tofile=f"draft/{relative}",
                n=3,
            )
        )
        if sum(len(item) for item in chunks) >= max_chars:
            chunks.append("\n... diff truncated ...\n")
            break
    return {
        "id": draft_id,
        "changes": changes,
        "diff": "".join(chunks)[:max_chars],
        "binary_or_nontext": binary,
        "truncated": sum(len(item) for item in chunks) > max_chars,
    }


def _live_conflicts(project: Path, payload: dict[str, Any], changes: dict[str, list[str]]) -> list[dict[str, str]]:
    base_hashes = payload.get("base_hashes", {})
    conflicts: list[dict[str, str]] = []
    for relative in changes["modified"] + changes["deleted"]:
        live = _safe_relative(project, relative)
        expected = str(base_hashes.get(relative, ""))
        if not live.is_file():
            conflicts.append({"path": relative, "reason": "live file is missing but existed when draft was created"})
            continue
        if _sha256(live) != expected:
            conflicts.append({"path": relative, "reason": "live file changed since draft creation"})
    for relative in changes["added"]:
        live = _safe_relative(project, relative)
        if live.exists():
            conflicts.append({"path": relative, "reason": "draft-added path now exists in live project"})
    return conflicts


def accept_draft(project_root: str | Path, draft_id: str, *, allow_risky: bool = False) -> dict[str, Any]:
    project = Path(project_root).resolve()
    payload = _load(project, draft_id)
    if payload.get("status") != "open":
        raise ValueError(f"draft is not open: {payload.get('status')}")
    status = draft_status(project, draft_id)
    changes = status["changes"]
    changed = changes["added"] + changes["deleted"] + changes["modified"]
    if status["risky_changes"] and not allow_risky:
        return {
            "ok": False,
            "reason": "risky changes require explicit --allow-risky",
            "risky_changes": status["risky_changes"],
            "changed_paths": changed,
        }
    conflicts = _live_conflicts(project, payload, changes)
    if conflicts:
        return {"ok": False, "reason": "live project changed since draft creation", "conflicts": conflicts}

    draft_root = _draft_root(project) / draft_id
    backup = draft_root / "accept-backup" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    workspace = Path(payload["workspace"])
    applied: list[str] = []
    for relative in changes["deleted"] + changes["modified"] + changes["added"]:
        live = _safe_relative(project, relative)
        if live.exists() and live.is_file():
            _copy_file(live, backup / relative)
        if relative in changes["deleted"]:
            live.unlink(missing_ok=True)
        else:
            source = workspace / relative
            live.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, dir=live.parent, prefix=f".{live.name}.uif-", suffix=".tmp") as handle:
                tmp = Path(handle.name)
            try:
                shutil.copy2(source, tmp)
                os.replace(tmp, live)
            finally:
                tmp.unlink(missing_ok=True)
        applied.append(relative)

    payload["status"] = "accepted"
    payload["accepted_at"] = _now()
    payload["updated_at"] = _now()
    payload["accepted_paths"] = applied
    _manifest_path(project, draft_id).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "id": draft_id,
        "applied_paths": applied,
        "backup": str(backup),
        "live_updated": bool(applied),
        "conflicts": [],
    }


def discard_draft(project_root: str | Path, draft_id: str) -> dict[str, Any]:
    project = Path(project_root).resolve()
    payload = _load(project, draft_id)
    if payload.get("status") == "accepted":
        raise ValueError("accepted drafts are retained as audit history and cannot be discarded by this command")
    root = _draft_root(project) / draft_id
    shutil.rmtree(root)
    return {"ok": True, "id": draft_id, "discarded": True, "live_untouched": True}


def list_drafts(project_root: str | Path) -> list[dict[str, Any]]:
    project = Path(project_root).resolve()
    root = _draft_root(project)
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for manifest in sorted(root.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            out.append({
                "id": payload.get("id"),
                "title": payload.get("title"),
                "status": payload.get("status"),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "workspace": payload.get("workspace"),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated, conflict-aware UI Forge draft workspaces")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("project_root")
    create.add_argument("--title", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("project_root")

    status = sub.add_parser("status")
    status.add_argument("project_root")
    status.add_argument("draft_id")

    diff = sub.add_parser("diff")
    diff.add_argument("project_root")
    diff.add_argument("draft_id")
    diff.add_argument("--max-chars", type=int, default=60_000)

    accept = sub.add_parser("accept")
    accept.add_argument("project_root")
    accept.add_argument("draft_id")
    accept.add_argument("--allow-risky", action="store_true")

    discard = sub.add_parser("discard")
    discard.add_argument("project_root")
    discard.add_argument("draft_id")

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_draft(args.project_root, args.title)
        elif args.command == "list":
            result = {"drafts": list_drafts(args.project_root)}
        elif args.command == "status":
            result = draft_status(args.project_root, args.draft_id)
        elif args.command == "diff":
            result = draft_diff(args.project_root, args.draft_id, max(1000, min(args.max_chars, 500_000)))
        elif args.command == "accept":
            result = accept_draft(args.project_root, args.draft_id, allow_risky=args.allow_risky)
        else:
            result = discard_draft(args.project_root, args.draft_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if isinstance(result, dict) and result.get("ok") is False:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
