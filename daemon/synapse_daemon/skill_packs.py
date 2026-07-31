"""Portable AI skill packs installed through Synapse AI Bundles.

Skill packs use the familiar SKILL.md layout, but Synapse owns their lifecycle:
bundled packages are validated, copied into a versioned data directory, exposed
through REST/MCP, and may seed an existing benchmark spec. The daemon never
imports or executes Python from a skill package.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from . import benchmarks
from .errors import invalid, not_found
from .runtime_paths import bundled_templates_dir
from .time_utils import to_iso, utc_now

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_TEXT_RESOURCE_BYTES = 256 * 1024


class SkillPackBaseline(BaseModel):
    name: str = ""
    version: str = ""
    comparison_policy: str = "same-model-same-tools-same-network"


class SkillPackManifest(BaseModel):
    id: str
    name: str
    publisher: str
    version: str
    description: str = ""
    entrypoint: str = "SKILL.md"
    tags: list[str] = Field(default_factory=list)
    implicit_invocation: bool = True
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_capabilities: list[str] = Field(default_factory=list)
    optional_capabilities: list[str] = Field(default_factory=list)
    benchmark_spec: str | None = None
    baseline: SkillPackBaseline | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("Skill pack id must be kebab-case.")
        return value

    @field_validator("entrypoint", "benchmark_spec")
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _validate_resource_path(value)
        return value


class SkillPackResource(BaseModel):
    path: str
    size_bytes: int
    sha256: str


class SkillPackCatalogItem(BaseModel):
    manifest: SkillPackManifest
    installed: bool = False
    installed_path: str | None = None
    package_sha256: str
    resources: list[SkillPackResource] = Field(default_factory=list)


class InstalledSkillPack(BaseModel):
    manifest: SkillPackManifest
    path: str
    package_sha256: str
    installed_at: datetime
    benchmark_spec_id: str | None = None
    resources: list[SkillPackResource] = Field(default_factory=list)


def bundled_skill_packs_dir() -> Path:
    return bundled_templates_dir() / "skills"


def installed_skill_packs_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "skill-packs"


def load_catalog(data_dir: Path | None = None) -> list[SkillPackCatalogItem]:
    installed_ids = set(list_installed_ids(data_dir)) if data_dir is not None else set()
    items: list[SkillPackCatalogItem] = []
    root = bundled_skill_packs_dir()
    if not root.exists():
        return []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest, package_root = _load_manifest_path(manifest_path)
        installed_path = _current_package_path(data_dir, manifest.id) if data_dir is not None else None
        items.append(
            SkillPackCatalogItem(
                manifest=manifest,
                installed=manifest.id in installed_ids,
                installed_path=str(installed_path) if installed_path is not None else None,
                package_sha256=_package_hash(package_root),
                resources=_resource_inventory(package_root),
            )
        )
    return sorted(items, key=lambda item: item.manifest.name.lower())


def get_catalog_item(skill_id: str, data_dir: Path | None = None) -> SkillPackCatalogItem:
    for item in load_catalog(data_dir):
        if item.manifest.id == skill_id:
            return item
    raise not_found("skill_pack", skill_id)


def list_installed_ids(data_dir: Path | None) -> list[str]:
    if data_dir is None:
        return []
    root = installed_skill_packs_dir(data_dir)
    if not root.exists():
        return []
    installed: list[str] = []
    for marker in root.glob("*/current.json"):
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            skill_id = str(payload.get("id", ""))
            package_path = _current_package_path(data_dir, skill_id)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if skill_id and package_path is not None and package_path.exists():
            installed.append(skill_id)
    return sorted(set(installed))


def list_installed(data_dir: Path) -> list[InstalledSkillPack]:
    out: list[InstalledSkillPack] = []
    for skill_id in list_installed_ids(data_dir):
        out.append(get_installed(data_dir, skill_id))
    return out


def install(data_dir: Path, skill_id: str) -> InstalledSkillPack:
    catalog = get_catalog_item(skill_id)
    source_root = bundled_skill_packs_dir() / skill_id
    if catalog.manifest.benchmark_spec is not None:
        load_benchmark_spec(source_root, catalog.manifest)
    target_root = installed_skill_packs_dir(data_dir) / skill_id
    version_root = target_root / "versions" / catalog.manifest.version
    target_root.mkdir(parents=True, exist_ok=True)
    version_root.parent.mkdir(parents=True, exist_ok=True)

    if not version_root.exists():
        staging = target_root / f".install-{catalog.manifest.version}"
        if staging.exists():
            _safe_remove_tree(staging, target_root)
        shutil.copytree(source_root, staging)
        installed_manifest, _ = _load_manifest_path(staging / "manifest.json")
        if installed_manifest.id != skill_id or installed_manifest.version != catalog.manifest.version:
            _safe_remove_tree(staging, target_root)
            raise invalid("skill_pack", "Installed package identity did not match the catalog.")
        if _package_hash(staging) != catalog.package_sha256:
            _safe_remove_tree(staging, target_root)
            raise invalid("skill_pack", "Installed package bytes did not match the validated catalog hash.")
        staging.rename(version_root)
    elif _package_hash(version_root) != catalog.package_sha256:
        raise invalid(
            "skill_pack",
            (
                f"Installed skill pack '{skill_id}' changed without a version bump. "
                "Skill versions are immutable; publish a new version before reinstalling."
            ),
        )

    marker = {
        "id": catalog.manifest.id,
        "version": catalog.manifest.version,
        "package_sha256": catalog.package_sha256,
        "installed_at": to_iso(utc_now()),
    }
    marker_path = target_root / "current.json"
    marker_tmp = target_root / "current.json.tmp"
    marker_tmp.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    marker_tmp.replace(marker_path)
    return get_installed(data_dir, skill_id)


def uninstall(data_dir: Path, skill_id: str) -> bool:
    root = installed_skill_packs_dir(data_dir) / skill_id
    if not root.exists():
        return False
    _safe_remove_tree(root, installed_skill_packs_dir(data_dir))
    return True


def get_installed(data_dir: Path, skill_id: str) -> InstalledSkillPack:
    marker_path = installed_skill_packs_dir(data_dir) / skill_id / "current.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise not_found("skill_pack_install", skill_id) from exc
    except json.JSONDecodeError as exc:
        raise invalid("skill_pack", f"Installed marker is malformed: {exc}") from exc
    package_root = _current_package_path(data_dir, skill_id)
    if package_root is None or not package_root.exists():
        raise invalid("skill_pack", f"Installed package files are missing for '{skill_id}'.")
    manifest, _ = _load_manifest_path(package_root / "manifest.json")
    marker_version = str(marker.get("version", ""))
    if manifest.id != skill_id or manifest.version != marker_version:
        raise invalid("skill_pack", f"Installed package identity is inconsistent for '{skill_id}'.")
    actual_hash = _package_hash(package_root)
    expected_hash = str(marker.get("package_sha256", ""))
    if expected_hash and actual_hash != expected_hash:
        raise invalid("skill_pack", f"Installed package integrity check failed for '{skill_id}'.")
    installed_at_raw = marker.get("installed_at")
    try:
        installed_at = datetime.fromisoformat(str(installed_at_raw).replace("Z", "+00:00"))
    except ValueError:
        installed_at = utc_now()
    benchmark_spec_id = None
    if manifest.benchmark_spec:
        benchmark_spec_id = load_benchmark_spec(package_root, manifest).id
    return InstalledSkillPack(
        manifest=manifest,
        path=str(package_root),
        package_sha256=expected_hash or actual_hash,
        installed_at=installed_at,
        benchmark_spec_id=benchmark_spec_id,
        resources=_resource_inventory(package_root),
    )


def read_instructions(data_dir: Path, skill_id: str) -> dict[str, Any]:
    installed = get_installed(data_dir, skill_id)
    package_root = Path(installed.path)
    entrypoint = _resolve_resource(package_root, installed.manifest.entrypoint)
    return {
        "skill": installed.model_dump(mode="json"),
        "instructions_md": _read_text_resource(entrypoint),
        "hint": "Read only the referenced resources required for the current task; use bundled scripts without copying them into the prompt.",
    }


def read_resource(data_dir: Path, skill_id: str, resource_path: str) -> dict[str, Any]:
    installed = get_installed(data_dir, skill_id)
    package_root = Path(installed.path)
    target = _resolve_resource(package_root, resource_path)
    return {
        "skill_id": skill_id,
        "path": resource_path,
        "content": _read_text_resource(target),
        "sha256": _file_hash(target),
    }


def load_benchmark_spec(package_root: Path, manifest: SkillPackManifest) -> benchmarks.BenchmarkSpecCreate:
    if not manifest.benchmark_spec:
        raise invalid("skill_pack", f"Skill pack '{manifest.id}' has no benchmark spec.")
    path = _resolve_resource(package_root, manifest.benchmark_spec)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise invalid("skill_pack", f"Benchmark spec is malformed: {exc}") from exc
    try:
        return benchmarks.BenchmarkSpecCreate.model_validate(payload)
    except ValidationError as exc:
        raise invalid("skill_pack", f"Benchmark spec is invalid: {exc}") from exc


def ensure_benchmark_spec(conn: sqlite3.Connection, installed: InstalledSkillPack) -> str | None:
    if installed.manifest.benchmark_spec is None:
        return None
    payload = load_benchmark_spec(Path(installed.path), installed.manifest)
    row = conn.execute("SELECT id FROM benchmark_specs WHERE id = ?", (payload.id,)).fetchone()
    if row is None:
        benchmarks.create_spec(conn, payload)
    return payload.id


def _load_manifest_path(path: Path) -> tuple[SkillPackManifest, Path]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise invalid("skill_pack", f"Manifest is missing at {path}.") from exc
    except json.JSONDecodeError as exc:
        raise invalid("skill_pack", f"Manifest is malformed at {path}: {exc}") from exc
    try:
        manifest = SkillPackManifest.model_validate(raw)
    except ValidationError as exc:
        raise invalid("skill_pack", f"Manifest is invalid at {path}: {exc}") from exc
    package_root = path.parent.resolve()
    _assert_no_symlinks(package_root)
    entrypoint = _resolve_resource(package_root, manifest.entrypoint)
    if not entrypoint.is_file():
        raise invalid("skill_pack", f"Entrypoint '{manifest.entrypoint}' is missing.")
    if manifest.benchmark_spec:
        benchmark_path = _resolve_resource(package_root, manifest.benchmark_spec)
        if not benchmark_path.is_file():
            raise invalid("skill_pack", f"Benchmark spec '{manifest.benchmark_spec}' is missing.")
    return manifest, package_root


def _assert_no_symlinks(package_root: Path) -> None:
    if package_root.is_symlink():
        raise invalid("skill_pack", "Skill package roots cannot be symbolic links.")
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise invalid("skill_pack", f"Skill packages cannot contain symbolic links: {path.name}")
        if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            raise invalid("skill_pack", f"Skill packages cannot contain generated bytecode: {path.name}")


def _validate_resource_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("Skill resource paths must be relative and cannot contain '..'.")
    return path


def _resolve_resource(package_root: Path, value: str) -> Path:
    try:
        relative = _validate_resource_path(value)
    except ValueError as exc:
        raise invalid("skill_pack", str(exc)) from exc
    root = package_root.resolve()
    target = root.joinpath(*relative.parts).resolve()
    if target != root and root not in target.parents:
        raise invalid("skill_pack", "Resource path escapes the skill package.")
    return target


def _read_text_resource(path: Path) -> str:
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise not_found("skill_pack_resource", str(path)) from exc
    if size > _MAX_TEXT_RESOURCE_BYTES:
        raise invalid("skill_pack_resource", f"Text resource exceeds {_MAX_TEXT_RESOURCE_BYTES} bytes.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise invalid("skill_pack_resource", "Requested resource is not UTF-8 text.") from exc


def _current_package_path(data_dir: Path | None, skill_id: str) -> Path | None:
    if data_dir is None or not _ID_RE.fullmatch(skill_id):
        return None
    marker_path = installed_skill_packs_dir(data_dir) / skill_id / "current.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        version = str(marker["version"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None
    if not version or any(part in version for part in ("/", "\\", "..")):
        return None
    return installed_skill_packs_dir(data_dir) / skill_id / "versions" / version


def _resource_inventory(root: Path) -> list[SkillPackResource]:
    out: list[SkillPackResource] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        out.append(SkillPackResource(path=relative, size_bytes=path.stat().st_size, sha256=_file_hash(path)))
    return out


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for resource in _resource_inventory(root):
        digest.update(resource.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(resource.sha256.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_remove_tree(target: Path, expected_parent: Path) -> None:
    resolved_target = target.resolve()
    resolved_parent = expected_parent.resolve()
    if resolved_target == resolved_parent or resolved_parent not in resolved_target.parents:
        raise invalid("skill_pack", f"Refusing to remove unsafe path: {resolved_target}")
    shutil.rmtree(resolved_target)
