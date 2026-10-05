"""Import already-generated local image files into registered Synapse projects.

This is the bridge for AI runtimes that already have their own image-generation capability:
produce/download a real image file locally, then ask Synapse to place it into the active
project with the same project confinement, provenance, hashing, and audit guarantees as
Synapse-native provider generation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import image_assets, image_editing

_MAX_IMPORT_BYTES = 50 * 1024 * 1024
_SUPPORTED_SUFFIXES = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}


class ImageImportError(ValueError):
    """Safe, user-facing image-import error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "image_import.invalid",
        status: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _source_image(path: str | Path) -> tuple[Path, str, int, int, bool]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImageImportError(
            f"source image does not exist: {source}",
            code="image_import.source_missing",
            status=404,
        )
    if source.stat().st_size >= _MAX_IMPORT_BYTES:
        raise ImageImportError("source image must be smaller than 50MB")
    output_format = _SUPPORTED_SUFFIXES.get(source.suffix.lower())
    if output_format is None:
        raise ImageImportError("source image must be PNG, JPEG, or WebP")
    try:
        width, height, has_alpha = image_editing._image_metadata(source)
    except image_editing.ImageEditError as exc:
        raise ImageImportError(str(exc)) from exc
    if width <= 0 or height <= 0:
        raise ImageImportError("source image has invalid pixel dimensions")
    return source, output_format, width, height, has_alpha


def _append_import_manifest(
    root: Path,
    *,
    target: Path,
    source_name: str,
    origin: str,
    provider: str | None,
    model: str | None,
    prompt: str | None,
    width: int,
    height: int,
    has_alpha: bool,
    output_format: str,
    sha256: str,
    byte_count: int,
) -> Path:
    manifest = root / ".synapse" / "image-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "imported_image",
        "created_at": datetime.now(UTC).isoformat(),
        "path": target.relative_to(root).as_posix(),
        "source_name": source_name,
        "origin": origin,
        "provider": provider,
        "model": model,
        "prompt": prompt,
        "width": width,
        "height": height,
        "has_alpha": has_alpha,
        "format": output_format,
        "sha256": sha256,
        "bytes": byte_count,
    }
    with manifest.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return manifest


def import_image_file(
    *,
    project_root: str | Path,
    source_path: str | Path,
    relative_path: str,
    source_name: str | None = None,
    origin: str = "local_file",
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate and copy one local image into a project-scoped destination."""

    source, output_format, width, height, has_alpha = _source_image(source_path)

    provenance_source_name = Path(str(source_name or source.name)).name.strip() or source.name
    if len(provenance_source_name) > 255:
        raise ImageImportError("source_name must be 255 characters or fewer")

    clean_origin = str(origin or "local_file").strip() or "local_file"
    if len(clean_origin) > 200:
        raise ImageImportError("origin must be 200 characters or fewer")
    clean_provider = str(provider or "").strip() or None
    clean_model = str(model or "").strip() or None
    if clean_provider and len(clean_provider) > 200:
        raise ImageImportError("provider must be 200 characters or fewer")
    if clean_model and len(clean_model) > 200:
        raise ImageImportError("model must be 200 characters or fewer")
    clean_prompt = str(prompt or "").strip() or None
    if clean_prompt and len(clean_prompt) > 32_000:
        raise ImageImportError("prompt is too long (maximum 32,000 characters)")

    try:
        root, target = image_assets._resolve_output_path(
            project_root,
            relative_path,
            output_format,
            overwrite=overwrite,
        )
    except image_assets.ImageGenerationError as exc:
        raise ImageImportError(
            str(exc),
            code=exc.code.replace("image_generation", "image_import"),
            status=exc.status,
            retryable=exc.retryable,
        ) from exc

    image_bytes = source.read_bytes()
    digest = hashlib.sha256(image_bytes).hexdigest()

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb" if overwrite else "xb") as handle:
            handle.write(image_bytes)
    except FileExistsError as exc:
        raise ImageImportError(
            f"refusing to overwrite existing asset: {target.relative_to(root)}; pass overwrite=true to replace it",
            code="image_import.conflict",
            status=409,
        ) from exc
    except OSError as exc:
        raise ImageImportError(
            f"could not write imported image inside project: {type(exc).__name__}",
            code="image_import.write_failed",
            status=500,
        ) from exc

    manifest = _append_import_manifest(
        root,
        target=target,
        source_name=provenance_source_name,
        origin=clean_origin,
        provider=clean_provider,
        model=clean_model,
        prompt=clean_prompt,
        width=width,
        height=height,
        has_alpha=has_alpha,
        output_format=output_format,
        sha256=digest,
        byte_count=len(image_bytes),
    )
    return {
        "created": True,
        "kind": "imported_image",
        "project_relative_path": target.relative_to(root).as_posix(),
        "absolute_path": str(target),
        "manifest_path": str(manifest),
        "source_name": provenance_source_name,
        "origin": clean_origin,
        "provider": clean_provider,
        "model": clean_model,
        "width": width,
        "height": height,
        "has_alpha": has_alpha,
        "format": output_format,
        "bytes": len(image_bytes),
        "sha256": digest,
    }


def import_project_image_file(
    storage: Any,
    *,
    project_id: str,
    source_path: str | Path,
    relative_path: str,
    source_name: str | None = None,
    origin: str = "local_file",
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    overwrite: bool = False,
    audit_source: str = "auto",
) -> dict[str, Any]:
    """Import a local image into a registered project and record a safe audit receipt."""
    from . import projects as projects_module
    from .audit import AuditRecord, audit

    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise ImageImportError("project_id is required")

    project = projects_module.get(storage.conn, clean_project_id)
    result = import_image_file(
        project_root=project.path,
        source_path=source_path,
        relative_path=relative_path,
        source_name=source_name,
        origin=origin,
        provider=provider,
        model=model,
        prompt=prompt,
        overwrite=overwrite,
    )

    # Do not store the absolute source path or prompt in the global audit log.
    with storage.transaction() as conn:
        audit(
            conn,
            AuditRecord(
                entity_type="image_asset",
                entity_id=f"{clean_project_id}:{result['project_relative_path']}",
                action="import",
                source=audit_source,
                result="success",
                details={
                    "project_id": clean_project_id,
                    "project_relative_path": result["project_relative_path"],
                    "source_name": result["source_name"],
                    "origin": result["origin"],
                    "provider": result["provider"],
                    "model": result["model"],
                    "width": result["width"],
                    "height": result["height"],
                    "format": result["format"],
                    "bytes": result["bytes"],
                    "sha256": result["sha256"],
                    "overwrite": overwrite,
                },
            ),
        )

    return {"project_id": clean_project_id, **result}
