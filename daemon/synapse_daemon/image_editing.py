"""Project-scoped image editing/reference-image support for Synapse.

This module is separate from image_assets.py while that generator lane is in flight.
It targets OpenAI's Image Edit endpoint for edits, multi-reference composition, and
optional masked edits. Callers provide project-relative paths only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import httpx

from . import image_assets, image_credentials

OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"
_MAX_INPUT_BYTES = 50 * 1024 * 1024
_SUPPORTED_INPUT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ImageEditError(ValueError):
    """A safe, user-facing image-editing error with API semantics."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "image_edit.invalid",
        status: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _from_generation_error(exc: image_assets.ImageGenerationError) -> ImageEditError:
    code = exc.code
    if code.startswith("image_generation."):
        code = "image_edit." + code.removeprefix("image_generation.")
    return ImageEditError(str(exc), code=code, status=exc.status, retryable=exc.retryable)


def _image_metadata(path: Path) -> tuple[int, int, bool]:
    """Return (width, height, has_alpha) from PNG/JPEG/WebP headers only.

    Mask validation must happen before a provider call. Keep this dependency-free so the
    daemon does not need a heavyweight imaging package just to enforce provider contracts.
    """
    data = path.read_bytes()
    suffix = path.suffix.lower()

    if suffix == ".png":
        if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ImageEditError(f"invalid PNG image: {path.name}")
        width, height, _depth, color_type, _comp, _filter, _interlace = struct.unpack(
            ">IIBBBBB", data[16:29]
        )
        return width, height, color_type in {4, 6}

    if suffix in {".jpg", ".jpeg"}:
        if len(data) < 4 or data[:2] != b"\xff\xd8":
            raise ImageEditError(f"invalid JPEG image: {path.name}")
        pos = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            while pos < len(data) and data[pos] == 0xFF:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in {0x01, *range(0xD0, 0xD9)}:
                continue
            if pos + 2 > len(data):
                break
            segment_len = int.from_bytes(data[pos:pos + 2], "big")
            if segment_len < 2 or pos + segment_len > len(data):
                break
            if marker in sof_markers and segment_len >= 7:
                height = int.from_bytes(data[pos + 3:pos + 5], "big")
                width = int.from_bytes(data[pos + 5:pos + 7], "big")
                return width, height, False  # JPEG has no alpha channel.
            pos += segment_len
        raise ImageEditError(f"could not read JPEG dimensions: {path.name}")

    if suffix == ".webp":
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise ImageEditError(f"invalid WebP image: {path.name}")
        pos = 12
        width = height = None
        has_alpha = False
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos + 4]
            chunk_len = int.from_bytes(data[pos + 4:pos + 8], "little")
            chunk = data[pos + 8:pos + 8 + chunk_len]
            if len(chunk) < chunk_len:
                break
            if chunk_id == b"VP8X" and len(chunk) >= 10:
                has_alpha = has_alpha or bool(chunk[0] & 0x10)
                width = 1 + int.from_bytes(chunk[4:7], "little")
                height = 1 + int.from_bytes(chunk[7:10], "little")
            elif chunk_id == b"ALPH":
                has_alpha = True
            elif chunk_id == b"VP8 " and len(chunk) >= 10 and chunk[3:6] == b"\x9d\x01\x2a":
                width = int.from_bytes(chunk[6:8], "little") & 0x3FFF
                height = int.from_bytes(chunk[8:10], "little") & 0x3FFF
            elif chunk_id == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
                bits = int.from_bytes(chunk[1:5], "little")
                width = (bits & 0x3FFF) + 1
                height = ((bits >> 14) & 0x3FFF) + 1
                has_alpha = has_alpha or bool((bits >> 28) & 1)
            pos += 8 + chunk_len + (chunk_len & 1)
        if width is None or height is None:
            raise ImageEditError(f"could not read WebP dimensions: {path.name}")
        return width, height, has_alpha

    raise ImageEditError("input image must be PNG, JPEG, or WebP")


def _validate_mask(first_input: Path, mask: Path) -> None:
    first_width, first_height, _ = _image_metadata(first_input)
    mask_width, mask_height, mask_has_alpha = _image_metadata(mask)
    if (mask_width, mask_height) != (first_width, first_height):
        raise ImageEditError(
            "mask and first input image must use the same pixel dimensions "
            f"({first_width}x{first_height} required; got {mask_width}x{mask_height})"
        )
    if not mask_has_alpha:
        raise ImageEditError("mask must include an alpha channel")


def _resolve_project_file(project_root: str | Path, relative_path: str) -> tuple[Path, Path]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ImageEditError(f"registered project path does not exist: {root}")
    raw = str(relative_path or "").strip()
    if not raw:
        raise ImageEditError("project-relative image path is required")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive:
        raise ImageEditError("image path must stay inside the registered project")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ImageEditError("image path escapes the registered project") from exc
    if not target.is_file():
        raise ImageEditError(f"input image does not exist: {target.relative_to(root)}")
    if target.suffix.lower() not in _SUPPORTED_INPUT_SUFFIXES:
        raise ImageEditError("input image must be PNG, JPEG, or WebP")
    if target.stat().st_size >= _MAX_INPUT_BYTES:
        raise ImageEditError("input image must be smaller than 50MB")
    return root, target


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime in {"image/png", "image/jpeg", "image/webp"}:
        return mime
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def _append_edit_manifest(
    root: Path,
    *,
    target: Path,
    prompt: str,
    source_paths: list[str],
    mask_path: str | None,
    provider: str,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    sha256: str,
    byte_count: int,
    request_id: str | None,
) -> Path:
    manifest = root / ".synapse" / "image-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "edited_image",
        "created_at": datetime.now(UTC).isoformat(),
        "path": target.relative_to(root).as_posix(),
        "prompt": prompt,
        "source_paths": source_paths,
        "mask_path": mask_path,
        "provider": provider,
        "model": model,
        "size": size,
        "quality": quality,
        "format": output_format,
        "background": background,
        "sha256": sha256,
        "bytes": byte_count,
        "request_id": request_id,
    }
    with manifest.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return manifest


def edit_image(
    *,
    project_root: str | Path,
    prompt: str,
    input_paths: Iterable[str],
    relative_path: str,
    mask_path: str | None = None,
    size: str = "auto",
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
    overwrite: bool = False,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Edit/composite project images and save one result inside the same project."""

    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ImageEditError("prompt is required")
    if len(clean_prompt) > 32_000:
        raise ImageEditError("prompt is too long (maximum 32,000 characters)")

    raw_inputs = [str(value or "").strip() for value in input_paths]
    raw_inputs = [value for value in raw_inputs if value]
    if not raw_inputs:
        raise ImageEditError("at least one input image is required")

    quality = str(quality or "auto").strip().lower()
    if quality not in image_assets._ALLOWED_QUALITY:
        raise ImageEditError(f"quality must be one of: {', '.join(sorted(image_assets._ALLOWED_QUALITY))}")

    output_format = str(output_format or "png").strip().lower()
    if output_format == "jpg":
        output_format = "jpeg"
    if output_format not in image_assets._ALLOWED_FORMATS:
        raise ImageEditError(f"output_format must be one of: {', '.join(sorted(image_assets._ALLOWED_FORMATS))}")

    background = str(background or "auto").strip().lower()
    if background not in image_assets._ALLOWED_BACKGROUND:
        raise ImageEditError(f"background must be one of: {', '.join(sorted(image_assets._ALLOWED_BACKGROUND))}")
    if background == "transparent" and output_format == "jpeg":
        raise ImageEditError("transparent backgrounds require png or webp output")

    try:
        size = image_assets._validate_size(size)
    except image_assets.ImageGenerationError as exc:
        raise _from_generation_error(exc) from exc

    roots_and_inputs = [_resolve_project_file(project_root, path) for path in raw_inputs]
    root = roots_and_inputs[0][0]
    inputs = [path for _, path in roots_and_inputs]

    resolved_mask: Path | None = None
    if mask_path:
        mask_root, resolved_mask = _resolve_project_file(project_root, mask_path)
        if mask_root != root:
            raise ImageEditError("mask must belong to the same registered project")
        first_suffix = inputs[0].suffix.lower().replace(".jpg", ".jpeg")
        mask_suffix = resolved_mask.suffix.lower().replace(".jpg", ".jpeg")
        if first_suffix != mask_suffix:
            raise ImageEditError("mask and first input image must use the same file format")
        _validate_mask(inputs[0], resolved_mask)

    try:
        root, target = image_assets._resolve_output_path(
            root, relative_path, output_format, overwrite=overwrite
        )
    except image_assets.ImageGenerationError as exc:
        raise _from_generation_error(exc) from exc

    provider = image_assets._provider()
    if provider != "openai":
        raise ImageEditError(
            f"unsupported image provider: {provider}",
            code="image_edit.not_configured",
            status=503,
        )
    resolved_api_key = str(api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not resolved_api_key:
        raise ImageEditError(
            "Synapse image editing is not configured: no Synapse OpenAI image credential or OPENAI_API_KEY is available.",
            code="image_edit.not_configured",
            status=503,
        )

    model = image_assets._openai_model()
    data = {
        "model": model,
        "prompt": clean_prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "background": background,
    }
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("image[]", (path.name, path.read_bytes(), _mime_for(path))) for path in inputs
    ]
    if resolved_mask is not None:
        files.append(("mask", (resolved_mask.name, resolved_mask.read_bytes(), _mime_for(resolved_mask))))

    timeout = float(os.getenv("SYNAPSE_IMAGE_TIMEOUT_SECONDS", "240") or "240")
    try:
        response = httpx.post(
            OPENAI_EDITS_URL,
            headers={"Authorization": f"Bearer {resolved_api_key}"},
            data=data,
            files=files,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ImageEditError(
            f"image provider request failed: {type(exc).__name__}",
            code="image_edit.provider_unavailable",
            status=502,
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        if response.status_code == 429:
            code, status, retryable = "image_edit.rate_limited", 429, True
        elif response.status_code >= 500:
            code, status, retryable = "image_edit.provider_unavailable", 502, True
        elif response.status_code in {401, 403}:
            code, status, retryable = "image_edit.provider_auth_failed", 503, False
        else:
            code, status, retryable = "image_edit.provider_rejected", 422, False
        raise ImageEditError(
            image_assets._safe_openai_error(response),
            code=code,
            status=status,
            retryable=retryable,
        )

    try:
        body = response.json()
        encoded = body["data"][0]["b64_json"]
        image_bytes = base64.b64decode(encoded, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ImageEditError(
            "image provider returned no valid base64 image",
            code="image_edit.provider_invalid_response",
            status=502,
            retryable=True,
        ) from exc
    if not image_bytes:
        raise ImageEditError(
            "image provider returned an empty image",
            code="image_edit.provider_invalid_response",
            status=502,
            retryable=True,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb" if overwrite else "xb") as handle:
            handle.write(image_bytes)
    except FileExistsError as exc:
        raise ImageEditError(
            f"refusing to overwrite existing asset: {target.relative_to(root)}; pass overwrite=true to replace it",
            code="image_asset.conflict",
            status=409,
        ) from exc
    except OSError as exc:
        raise ImageEditError(
            f"could not write edited image inside project: {type(exc).__name__}",
            code="image_asset.write_failed",
            status=500,
        ) from exc

    digest = hashlib.sha256(image_bytes).hexdigest()
    source_rel = [path.relative_to(root).as_posix() for path in inputs]
    mask_rel = resolved_mask.relative_to(root).as_posix() if resolved_mask else None
    manifest = _append_edit_manifest(
        root,
        target=target,
        prompt=clean_prompt,
        source_paths=source_rel,
        mask_path=mask_rel,
        provider=provider,
        model=model,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        sha256=digest,
        byte_count=len(image_bytes),
        request_id=response.headers.get("x-request-id"),
    )
    return {
        "created": True,
        "kind": "edited_image",
        "project_relative_path": target.relative_to(root).as_posix(),
        "source_paths": source_rel,
        "mask_path": mask_rel,
        "manifest_path": str(manifest),
        "provider": provider,
        "model": model,
        "size": size,
        "quality": quality,
        "format": output_format,
        "background": background,
        "bytes": len(image_bytes),
        "sha256": digest,
        "request_id": response.headers.get("x-request-id"),
    }


def edit_project_image(
    storage: Any,
    *,
    project_id: str,
    prompt: str,
    input_paths: Iterable[str],
    relative_path: str,
    mask_path: str | None = None,
    size: str = "auto",
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
    overwrite: bool = False,
    audit_source: str = "auto",
) -> dict[str, Any]:
    """Edit project images and record a non-secret Synapse audit receipt."""
    from . import projects as projects_module
    from .audit import AuditRecord, audit

    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise ImageEditError("project_id is required")

    project = projects_module.get(storage.conn, clean_project_id)
    api_key, _credential_source = image_credentials.resolve_openai_api_key(storage)
    result = edit_image(
        project_root=project.path,
        prompt=prompt,
        input_paths=input_paths,
        relative_path=relative_path,
        mask_path=mask_path,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        overwrite=overwrite,
        api_key=api_key,
    )

    # Keep prompts out of the global audit log. Full provenance remains project-local.
    with storage.transaction() as conn:
        audit(
            conn,
            AuditRecord(
                entity_type="image_asset",
                entity_id=f"{clean_project_id}:{result['project_relative_path']}",
                action="edit",
                source=audit_source,
                result="success",
                details={
                    "project_id": clean_project_id,
                    "project_relative_path": result["project_relative_path"],
                    "source_paths": result["source_paths"],
                    "mask_path": result["mask_path"],
                    "provider": result["provider"],
                    "model": result["model"],
                    "format": result["format"],
                    "bytes": result["bytes"],
                    "sha256": result["sha256"],
                    "overwrite": overwrite,
                },
            ),
        )

    return {"project_id": clean_project_id, **result}
