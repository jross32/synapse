"""Connector-side attachment handoff contract for ResellTogether.

The ChatGPT connector must resolve an authorized attachment reference to real bytes
before invoking this module. File IDs or ChatGPT /mnt/data paths are NOT Windows paths.
"""
from __future__ import annotations
import base64
import hashlib
import io
from pathlib import Path
from typing import Any, Callable

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}

class AttachmentBridgeError(ValueError):
    pass

def prepare_attachment(*, filename: str, mime: str, original_bytes: bytes, expected_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(original_bytes, bytes) or not 0 < len(original_bytes) <= MAX_BYTES:
        raise AttachmentBridgeError("Attachment missing or outside permitted size")
    if not filename or filename != Path(filename).name or "\\" in filename or "/" in filename or filename in (".", ".."):
        raise AttachmentBridgeError("Unsafe filename")
    if mime not in ALLOWED_MIME or not original_bytes.startswith(ALLOWED_MIME[mime]):
        raise AttachmentBridgeError("Image type/signature mismatch")
    if mime == "image/webp" and original_bytes[8:12] != b"WEBP":
        raise AttachmentBridgeError("Invalid WebP signature")
    digest = hashlib.sha256(original_bytes).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise AttachmentBridgeError("Original SHA-256 mismatch")
    return {"filename": filename, "mime": mime, "data_base64": base64.b64encode(original_bytes).decode("ascii"), "sha256": digest, "size_bytes": len(original_bytes)}

def ingest_reselltogether_attachment(*, filename: str, mime: str, original_bytes: bytes,
                                     workspace_id: str, invoke_mcp: Callable[[str, dict], dict],
                                     batch_id: str | None = None,
                                     expected_sha256: str | None = None) -> dict:
    """Use only with connector-provided authenticated bytes and authorized workspace.

    invoke_mcp(tool_name, arguments) must be the authenticated MCP transport.
    This module does not resolve ChatGPT file IDs or fetch arbitrary URLs.
    """
    if not workspace_id or not isinstance(workspace_id, str):
        raise AttachmentBridgeError("Workspace required")
    payload = prepare_attachment(filename=filename, mime=mime, original_bytes=original_bytes,
                                 expected_sha256=expected_sha256)
    args = {k: payload[k] for k in ("filename", "mime", "data_base64")}
    args["workspace_id"] = workspace_id
    if batch_id:
        args["batch_id"] = batch_id
    response = invoke_mcp("ingest_chat_attachment", args)
    if not isinstance(response, dict) or response.get("error") or response.get("ok") is False:
        raise AttachmentBridgeError("ResellTogether ingestion failed")
    return {"result": response, "source_sha256": payload["sha256"], "source_size_bytes": payload["size_bytes"]}
