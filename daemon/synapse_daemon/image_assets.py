"""Project-scoped image generation for Synapse-connected AIs.

The AI-facing contract is intentionally provider-neutral. Synapse currently defaults to OpenAI's GPT-Image-2.5 Sunburst behind that contract,
but callers ask Synapse to generate an image rather than calling a provider/model directly.

Generated files are confined to a registered project's root. A JSONL manifest is appended
inside .synapse/image-assets.jsonl so later UI/workflows can trace where an asset came from.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from . import image_credentials

DEFAULT_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = "gpt-image-2.5-sunburst"
OPENAI_GENERATIONS_URL = "https://api.openai.com/v1/images/generations"

_ALLOWED_QUALITY = {"auto", "low", "medium", "high", "xhigh", "max"}
_ALLOWED_FORMATS = {"png", "jpeg", "webp"}
_ALLOWED_BACKGROUND = {"auto", "opaque", "transparent"}
_FORMAT_SUFFIXES = {
    "png": {".png"},
    "jpeg": {".jpg", ".jpeg"},
    "webp": {".webp"},
}
_SIZE_RE = re.compile(r"^(\d{2,4})x(\d{2,4})$", re.IGNORECASE)


class ImageGenerationError(ValueError):
    """A safe, user-facing image-generation error with API semantics."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "image_generation.invalid",
        status: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _provider() -> str:
    return os.getenv("SYNAPSE_IMAGE_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER


def _openai_model() -> str:
    return os.getenv("SYNAPSE_OPENAI_IMAGE_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def image_generation_status(storage: Any | None = None) -> dict[str, Any]:
    """Return capability/configuration status without making a network request."""
    provider = _provider()
    if provider != "openai":
        return {
            "capability": "image_generation",
            "configured": False,
            "provider": provider,
            "reason": f"Unsupported image provider: {provider}",
            "supported_providers": ["openai"],
        }

    credential = image_credentials.credential_status(storage)
    configured = bool(credential["configured"])
    return {
        "capability": "image_generation",
        "configured": configured,
        "provider": "openai",
        "model": _openai_model(),
        "credential": "OpenAI image API key",
        "credential_source": credential["source"],
        "supports": {
            "generation": True,
            "editing": True,
            "importing": True,
            "chunked_upload": True,
            "formats": sorted(_ALLOWED_FORMATS),
            "quality": sorted(_ALLOWED_QUALITY),
            "recommended_quality": {
                "photorealistic": "max",
                "precision_edit": "max",
                "production": "xhigh",
                "fast_draft": "medium",
            },
            "recommended_models": {
                "best": "gpt-image-2.5-sunburst",
                "fast": "gpt-image-2.5-flare",
            },
            "background": sorted(_ALLOWED_BACKGROUND),
            "project_scoped_output": True,
            "asset_manifest": True,
        },
        "reason": (
            None
            if configured
            else "OpenAI image credentials are not configured in Synapse or OPENAI_API_KEY."
        ),
    }


def _validate_size(size: str) -> str:
    value = str(size or "auto").strip().lower()
    if value == "auto":
        return value

    match = _SIZE_RE.fullmatch(value)
    if not match:
        raise ImageGenerationError("size must be 'auto' or WIDTHxHEIGHT, for example 1536x1024")

    width, height = int(match.group(1)), int(match.group(2))
    if width > 3840 or height > 3840:
        raise ImageGenerationError("image edges must be 3840px or smaller")
    if width % 16 or height % 16:
        raise ImageGenerationError("image width and height must both be multiples of 16")
    short, long = min(width, height), max(width, height)
    if long / short > 3:
        raise ImageGenerationError("image aspect ratio cannot exceed 3:1")
    pixels = width * height
    if pixels < 655_360 or pixels > 8_294_400:
        raise ImageGenerationError("image pixel count must be between 655,360 and 8,294,400")
    return value


def _resolve_output_path(
    project_root: str | Path,
    relative_path: str,
    output_format: str,
    *,
    overwrite: bool,
) -> tuple[Path, Path]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ImageGenerationError(f"registered project path does not exist: {root}")

    raw = str(relative_path or "").strip()
    if not raw:
        raise ImageGenerationError("relative_path is required")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive:
        raise ImageGenerationError("relative_path must stay inside the registered project")

    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ImageGenerationError("relative_path escapes the registered project") from exc

    suffix = target.suffix.lower()
    if suffix not in _FORMAT_SUFFIXES[output_format]:
        expected = ", ".join(sorted(_FORMAT_SUFFIXES[output_format]))
        raise ImageGenerationError(
            f"relative_path extension must match output_format={output_format}; expected {expected}"
        )
    if target.exists() and not overwrite:
        raise ImageGenerationError(
            f"refusing to overwrite existing asset: {target.relative_to(root)}; pass overwrite=true to replace it",
            code="image_asset.conflict",
            status=409,
        )
    return root, target


def _safe_openai_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or "").strip()
            message = str(error.get("message") or "").strip()
            if code and message:
                return f"{code}: {message[:400]}"
            if message:
                return message[:400]
    except Exception:  # noqa: BLE001 - error parsing must never hide the HTTP status
        pass
    return f"OpenAI image request failed with HTTP {response.status_code}"


def _append_manifest(
    root: Path,
    *,
    target: Path,
    prompt: str,
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
        "kind": "generated_image",
        "created_at": datetime.now(UTC).isoformat(),
        "path": target.relative_to(root).as_posix(),
        "prompt": prompt,
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


def generate_image(
    *,
    project_root: str | Path,
    prompt: str,
    relative_path: str,
    size: str = "auto",
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
    overwrite: bool = False,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate one image and save it inside a registered project."""
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ImageGenerationError("prompt is required")
    if len(clean_prompt) > 32_000:
        raise ImageGenerationError("prompt is too long (maximum 32,000 characters)")

    quality = str(quality or "auto").strip().lower()
    if quality not in _ALLOWED_QUALITY:
        raise ImageGenerationError(f"quality must be one of: {', '.join(sorted(_ALLOWED_QUALITY))}")

    output_format = str(output_format or "png").strip().lower()
    if output_format == "jpg":
        output_format = "jpeg"
    if output_format not in _ALLOWED_FORMATS:
        raise ImageGenerationError(f"output_format must be one of: {', '.join(sorted(_ALLOWED_FORMATS))}")

    background = str(background or "auto").strip().lower()
    if background not in _ALLOWED_BACKGROUND:
        raise ImageGenerationError(f"background must be one of: {', '.join(sorted(_ALLOWED_BACKGROUND))}")
    if background == "transparent" and output_format == "jpeg":
        raise ImageGenerationError("transparent backgrounds require png or webp output")

    size = _validate_size(size)
    root, target = _resolve_output_path(project_root, relative_path, output_format, overwrite=overwrite)

    provider = _provider()
    if provider != "openai":
        raise ImageGenerationError(
            f"unsupported image provider: {provider}",
            code="image_generation.not_configured",
            status=503,
        )

    resolved_api_key = str(api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not resolved_api_key:
        raise ImageGenerationError(
            "Synapse image generation is not configured: no Synapse OpenAI image credential or OPENAI_API_KEY is available.",
            code="image_generation.not_configured",
            status=503,
        )

    model = _openai_model()
    payload: dict[str, Any] = {
        "model": model,
        "prompt": clean_prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "background": background,
    }
    timeout = float(os.getenv("SYNAPSE_IMAGE_TIMEOUT_SECONDS", "240") or "240")

    try:
        response = httpx.post(
            OPENAI_GENERATIONS_URL,
            headers={"Authorization": f"Bearer {resolved_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ImageGenerationError(
            f"image provider request failed: {type(exc).__name__}",
            code="image_generation.provider_unavailable",
            status=502,
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        if response.status_code == 429:
            code, status, retryable = "image_generation.rate_limited", 429, True
        elif response.status_code >= 500:
            code, status, retryable = "image_generation.provider_unavailable", 502, True
        elif response.status_code in {401, 403}:
            code, status, retryable = "image_generation.provider_auth_failed", 503, False
        else:
            code, status, retryable = "image_generation.provider_rejected", 422, False
        raise ImageGenerationError(
            _safe_openai_error(response),
            code=code,
            status=status,
            retryable=retryable,
        )

    try:
        body = response.json()
        encoded = body["data"][0]["b64_json"]
        image_bytes = base64.b64decode(encoded, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ImageGenerationError(
            "image provider returned no valid base64 image",
            code="image_generation.provider_invalid_response",
            status=502,
            retryable=True,
        ) from exc

    if not image_bytes:
        raise ImageGenerationError(
            "image provider returned an empty image",
            code="image_generation.provider_invalid_response",
            status=502,
            retryable=True,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if overwrite else "xb"
    try:
        with target.open(mode) as handle:
            handle.write(image_bytes)
    except FileExistsError as exc:
        raise ImageGenerationError(
            f"refusing to overwrite existing asset: {target.relative_to(root)}; pass overwrite=true to replace it",
            code="image_asset.conflict",
            status=409,
        ) from exc
    except OSError as exc:
        raise ImageGenerationError(
            f"could not write generated image inside project: {type(exc).__name__}",
            code="image_asset.write_failed",
            status=500,
        ) from exc

    digest = hashlib.sha256(image_bytes).hexdigest()
    manifest = _append_manifest(
        root,
        target=target,
        prompt=clean_prompt,
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
        "project_relative_path": target.relative_to(root).as_posix(),
        "absolute_path": str(target),
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


def generate_project_image(
    storage: Any,
    *,
    project_id: str,
    prompt: str,
    relative_path: str,
    size: str = "auto",
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
    overwrite: bool = False,
    audit_source: str = "auto",
) -> dict[str, Any]:
    """Generate an image for a registered project and record a non-secret audit receipt.

    Both REST and MCP call this service so project resolution, path confinement, provider
    use, provenance, and audit semantics cannot drift between AI entry points.
    """
    from . import projects as projects_module
    from .audit import AuditRecord, audit

    clean_project_id = str(project_id or "").strip()
    if not clean_project_id:
        raise ImageGenerationError("project_id is required")

    project = projects_module.get(storage.conn, clean_project_id)
    api_key, _credential_source = image_credentials.resolve_openai_api_key(storage)
    result = generate_image(
        project_root=project.path,
        prompt=prompt,
        relative_path=relative_path,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        overwrite=overwrite,
        api_key=api_key,
    )

    # Never put the prompt or provider credential into the global audit log. The project-
    # local asset manifest carries generation provenance; the audit log only records the
    # action and stable non-secret evidence needed for operator history.
    with storage.transaction() as conn:
        audit(
            conn,
            AuditRecord(
                entity_type="image_asset",
                entity_id=f"{clean_project_id}:{result['project_relative_path']}",
                action="generate",
                source=audit_source,
                result="success",
                details={
                    "project_id": clean_project_id,
                    "project_relative_path": result["project_relative_path"],
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

