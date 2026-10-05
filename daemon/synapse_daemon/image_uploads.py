"""Chunked image transfer for Synapse-connected AI runtimes.

Some AI runtimes can generate images but cannot write directly to the user's filesystem.
This module lets them stream the finished image into Synapse in bounded base64 chunks, then
finalize it through the normal project-scoped image import service.

Upload state is short-lived and stored under Synapse's data directory. Generation prompts
are encrypted at rest using the existing Synapse secrets crypto layer.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import image_imports
from .secrets import decrypt, encrypt

_UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{24}$")
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_BYTES = 50 * 1024 * 1024
_MAX_CHUNK_BYTES = 768 * 1024
_MAX_BASE64_CHARS = 1_100_000
_UPLOAD_TTL = timedelta(hours=2)


class ImageUploadError(ValueError):
    """Safe, user-facing chunked-upload error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "image_upload.invalid",
        status: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _staging_dir(storage: Any) -> Path:
    path = Path(storage.data_dir) / "image-upload-staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(storage: Any, upload_id: str) -> Path:
    return _staging_dir(storage) / f"{upload_id}.json"


def _validate_upload_id(upload_id: str) -> str:
    value = str(upload_id or "").strip().lower()
    if not _UPLOAD_ID_RE.fullmatch(value):
        raise ImageUploadError("invalid upload_id", code="image_upload.not_found", status=404)
    return value


def _load_meta(storage: Any, upload_id: str) -> dict[str, Any]:
    upload_id = _validate_upload_id(upload_id)
    path = _meta_path(storage, upload_id)
    if not path.is_file():
        raise ImageUploadError("image upload session was not found", code="image_upload.not_found", status=404)
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ImageUploadError(
            "image upload session metadata is unreadable",
            code="image_upload.corrupt",
            status=500,
        ) from exc
    if not isinstance(meta, dict) or meta.get("upload_id") != upload_id:
        raise ImageUploadError(
            "image upload session metadata is invalid",
            code="image_upload.corrupt",
            status=500,
        )
    created = datetime.fromisoformat(str(meta["created_at"]).replace("Z", "+00:00"))
    if datetime.now(UTC) - created > _UPLOAD_TTL:
        _delete_upload_files(storage, meta)
        raise ImageUploadError(
            "image upload session expired",
            code="image_upload.expired",
            status=410,
        )
    return meta


def _part_path(storage: Any, meta: dict[str, Any]) -> Path:
    filename = str(meta.get("staging_filename") or "")
    path = (_staging_dir(storage) / filename).resolve()
    try:
        path.relative_to(_staging_dir(storage).resolve())
    except ValueError as exc:
        raise ImageUploadError(
            "image upload staging path is invalid",
            code="image_upload.corrupt",
            status=500,
        ) from exc
    return path


def _delete_upload_files(storage: Any, meta: dict[str, Any]) -> None:
    upload_id = str(meta.get("upload_id") or "")
    try:
        _part_path(storage, meta).unlink(missing_ok=True)
    except Exception:
        pass
    if _UPLOAD_ID_RE.fullmatch(upload_id):
        try:
            _meta_path(storage, upload_id).unlink(missing_ok=True)
        except Exception:
            pass


def _cleanup_expired(storage: Any) -> None:
    now = datetime.now(UTC)
    for meta_path in _staging_dir(storage).glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(str(meta["created_at"]).replace("Z", "+00:00"))
            if now - created > _UPLOAD_TTL:
                _delete_upload_files(storage, meta)
        except Exception:
            # Do not let stale/corrupt staging state block a new upload.
            try:
                meta_path.unlink(missing_ok=True)
            except Exception:
                pass


def _encrypted_prompt(storage: Any, prompt: str | None) -> str | None:
    clean = str(prompt or "").strip()
    if not clean:
        return None
    if len(clean) > 32_000:
        raise ImageUploadError("prompt is too long (maximum 32,000 characters)")
    cipher = encrypt(clean, data_dir=storage.data_dir)
    return base64.b64encode(cipher).decode("ascii")


def _decrypted_prompt(storage: Any, encoded: str | None) -> str | None:
    if not encoded:
        return None
    try:
        cipher = base64.b64decode(encoded, validate=True)
        return decrypt(cipher, data_dir=storage.data_dir)
    except Exception as exc:
        raise ImageUploadError(
            "image upload prompt metadata could not be decrypted",
            code="image_upload.corrupt",
            status=500,
        ) from exc


def begin_image_upload(
    storage: Any,
    *,
    project_id: str,
    relative_path: str,
    source_name: str | None = None,
    origin: str = "ai_native_upload",
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    overwrite: bool = False,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Create a bounded upload session and return an opaque upload id."""
    from . import projects as projects_module

    _cleanup_expired(storage)

    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise ImageUploadError("project_id is required")
    projects_module.get(storage.conn, clean_project_id)

    clean_relative = str(relative_path or "").strip()
    if not clean_relative:
        raise ImageUploadError("relative_path is required")
    suffix = Path(clean_relative).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ImageUploadError("relative_path must end in .png, .jpg, .jpeg, or .webp")

    clean_source_name = Path(str(source_name or f"native-upload{suffix}")).name
    if Path(clean_source_name).suffix.lower() != suffix:
        clean_source_name = f"{Path(clean_source_name).stem or 'native-upload'}{suffix}"

    clean_origin = str(origin or "ai_native_upload").strip() or "ai_native_upload"
    if len(clean_origin) > 200:
        raise ImageUploadError("origin must be 200 characters or fewer")
    clean_provider = str(provider or "").strip() or None
    clean_model = str(model or "").strip() or None
    if clean_provider and len(clean_provider) > 200:
        raise ImageUploadError("provider must be 200 characters or fewer")
    if clean_model and len(clean_model) > 200:
        raise ImageUploadError("model must be 200 characters or fewer")

    expected = str(expected_sha256 or "").strip().lower() or None
    if expected and not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ImageUploadError("expected_sha256 must be a 64-character lowercase/uppercase hex digest")

    upload_id = secrets.token_hex(12)
    staging_filename = f"{upload_id}-{clean_source_name}"
    meta = {
        "upload_id": upload_id,
        "created_at": datetime.now(UTC).isoformat(),
        "project_id": clean_project_id,
        "relative_path": clean_relative,
        "source_name": clean_source_name,
        "staging_filename": staging_filename,
        "origin": clean_origin,
        "provider": clean_provider,
        "model": clean_model,
        "prompt_ciphertext_b64": _encrypted_prompt(storage, prompt),
        "overwrite": bool(overwrite),
        "expected_sha256": expected,
        "bytes_received": 0,
        "chunk_count": 0,
        "last_chunk_sha256": None,
    }
    part = _part_path(storage, meta)
    part.touch(exist_ok=False)
    _meta_path(storage, upload_id).write_text(
        json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "upload_id": upload_id,
        "project_id": clean_project_id,
        "relative_path": clean_relative,
        "source_name": clean_source_name,
        "max_chunk_bytes": _MAX_CHUNK_BYTES,
        "max_image_bytes": _MAX_IMAGE_BYTES,
        "expires_in_seconds": int(_UPLOAD_TTL.total_seconds()),
        "bytes_received": 0,
        "chunk_count": 0,
        "next_chunk_index": 0,
    }


def append_image_upload_chunk(
    storage: Any,
    *,
    upload_id: str,
    chunk_base64: str,
    chunk_index: int | None = None,
) -> dict[str, Any]:
    """Decode and append one bounded base64 chunk to an upload session."""
    meta = _load_meta(storage, upload_id)
    encoded = str(chunk_base64 or "").strip()
    if not encoded:
        raise ImageUploadError("chunk_base64 is required")
    if len(encoded) > _MAX_BASE64_CHARS:
        raise ImageUploadError(
            f"encoded chunk is too large; maximum decoded chunk is {_MAX_CHUNK_BYTES} bytes"
        )
    try:
        chunk = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ImageUploadError("chunk_base64 is not valid base64") from exc
    if not chunk:
        raise ImageUploadError("decoded upload chunk is empty")
    if len(chunk) > _MAX_CHUNK_BYTES:
        raise ImageUploadError(f"decoded chunk must be at most {_MAX_CHUNK_BYTES} bytes")

    import hashlib

    chunk_digest = hashlib.sha256(chunk).hexdigest()
    current_count = int(meta.get("chunk_count") or 0)
    if chunk_index is not None:
        try:
            requested_index = int(chunk_index)
        except (TypeError, ValueError) as exc:
            raise ImageUploadError("chunk_index must be a non-negative integer") from exc
        if requested_index < 0:
            raise ImageUploadError("chunk_index must be a non-negative integer")

        # If the caller lost the prior response and retries the exact most-recent chunk,
        # acknowledge it without appending the bytes again.
        if (
            current_count > 0
            and requested_index == current_count - 1
            and str(meta.get("last_chunk_sha256") or "") == chunk_digest
        ):
            return {
                "upload_id": meta["upload_id"],
                "bytes_received": int(meta.get("bytes_received") or 0),
                "chunk_count": current_count,
                "next_chunk_index": current_count,
                "duplicate": True,
            }

        if requested_index != current_count:
            raise ImageUploadError(
                f"chunk_index {requested_index} does not match next expected index {current_count}",
                code="image_upload.chunk_out_of_order",
                status=409,
            )

    received = int(meta.get("bytes_received") or 0)
    if received + len(chunk) >= _MAX_IMAGE_BYTES:
        raise ImageUploadError("image upload must be smaller than 50MB")

    part = _part_path(storage, meta)
    with part.open("ab") as handle:
        handle.write(chunk)

    meta["bytes_received"] = received + len(chunk)
    meta["chunk_count"] = current_count + 1
    meta["last_chunk_sha256"] = chunk_digest
    _meta_path(storage, meta["upload_id"]).write_text(
        json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "upload_id": meta["upload_id"],
        "bytes_received": meta["bytes_received"],
        "chunk_count": meta["chunk_count"],
        "next_chunk_index": meta["chunk_count"],
        "duplicate": False,
    }


def image_upload_status(storage: Any, *, upload_id: str) -> dict[str, Any]:
    """Return safe resumable-upload state without exposing prompt/staging internals."""
    meta = _load_meta(storage, upload_id)
    created = datetime.fromisoformat(str(meta["created_at"]).replace("Z", "+00:00"))
    expires_at = created + _UPLOAD_TTL
    return {
        "upload_id": meta["upload_id"],
        "project_id": meta["project_id"],
        "relative_path": meta["relative_path"],
        "source_name": meta["source_name"],
        "origin": meta["origin"],
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "bytes_received": int(meta.get("bytes_received") or 0),
        "chunk_count": int(meta.get("chunk_count") or 0),
        "next_chunk_index": int(meta.get("chunk_count") or 0),
        "expected_sha256_configured": bool(meta.get("expected_sha256")),
        "expires_at": expires_at.isoformat(),
    }


def finish_image_upload(storage: Any, *, upload_id: str, audit_source: str = "auto") -> dict[str, Any]:
    """Validate the complete staged image and import it into the registered project."""
    meta = _load_meta(storage, upload_id)
    if int(meta.get("bytes_received") or 0) <= 0:
        raise ImageUploadError("image upload contains no data")

    part = _part_path(storage, meta)
    expected = meta.get("expected_sha256")
    if expected:
        import hashlib

        digest = hashlib.sha256(part.read_bytes()).hexdigest()
        if digest.lower() != str(expected).lower():
            raise ImageUploadError(
                "uploaded image SHA-256 does not match expected_sha256",
                code="image_upload.hash_mismatch",
                status=422,
            )

    prompt = _decrypted_prompt(storage, meta.get("prompt_ciphertext_b64"))
    try:
        result = image_imports.import_project_image_file(
            storage,
            project_id=meta["project_id"],
            source_path=part,
            relative_path=meta["relative_path"],
            source_name=meta["source_name"],
            origin=meta["origin"],
            provider=meta.get("provider"),
            model=meta.get("model"),
            prompt=prompt,
            overwrite=bool(meta.get("overwrite", False)),
            audit_source=audit_source,
        )
    except image_imports.ImageImportError as exc:
        raise ImageUploadError(
            str(exc),
            code=exc.code.replace("image_import", "image_upload"),
            status=exc.status,
            retryable=exc.retryable,
        ) from exc

    _delete_upload_files(storage, meta)
    return {
        "upload_id": meta["upload_id"],
        "completed": True,
        **result,
    }


def cancel_image_upload(storage: Any, *, upload_id: str) -> dict[str, Any]:
    meta = _load_meta(storage, upload_id)
    _delete_upload_files(storage, meta)
    return {"upload_id": meta["upload_id"], "cancelled": True}
