# ChatGPT original attachment transport — shared Synapse AI integration guidance

## Verified architecture (2026-10-08)
- ResellTogether has a direct MCP tool `ingest_chat_attachment(workspace_id, filename, mime, data_base64, batch_id?)` in `C:\Users\justi\ResellTogether\mcp_server.py`. It validates image bytes, stores canonical originals in ResellTogether media, and creates private pending batch photos. It does **not** require the user to stage images manually in Windows.
- The Synapse daemon separately has `synapse_begin_image_upload`, `synapse_append_image_upload`, and `synapse_finish_image_upload` in `daemon/synapse_daemon/mcp_connector.py` and `image_uploads.py`; however, these are NOT exposed in the ChatGPT-facing Synapse connector tool list as of this check.
- `daemon/synapse_daemon/chat_attachment_handoff.py` is a tested local original-byte handoff adapter (commit a10737d), not an attachment-reference resolver. Do not confuse it with a completed bridge.
- A ChatGPT-uploaded `/mnt/data/...` path is in the ChatGPT sandbox, NOT on the user's Windows computer or Synapse daemon. Do not send that path to Windows and claim the file was found.
- The older `ResellTogether/incoming/justin-test-2026-10-06/manifest.txt` records a planned 9-photo/3-garment batch but no actual original files in that folder. It does not prove that original bytes transferred successfully.
- The navy U.S. Polo Assn. Large shirt, four photos IMG_1151–1154, is NOT imported: `list_pending_batches` for private workspace `g6bp4Ge7yC32h9NXRhxHEUCT` returned [] and Windows import inspection found 0/4 original files.

## Required behavior for ALL AI workers
1. Prefer the existing direct ResellTogether MCP image-ingestion path rather than inventing new Windows-folder staging workflows.
2. The missing integration is an AUTHENTICATED attachment-aware ChatGPT-facing connector tool that can receive real file bytes or supported file references. Verify the platform can actually supply those bytes; exposing base64-only methods alone does not solve access to ChatGPT attachments.
3. If supported file input exists, stream bounded bytes to ResellTogether/Synapse; validate magic type, size, SHA-256, authenticated workspace ownership; prevent duplicate item creation. Never fabricate a transfer from a filename, manifest, generated thumbnail, or text description.
4. AI should identify garments, group photos, write title/description/attributes; Synapse should transport and persist; ResellTogether should store original photos and closet drafts.
5. End-to-end acceptance: real user-uploaded photos appear in the correct private workspace, hashes and order verified, one closet item created, duplicate replay idempotent, browser UI verified, second-chat test successful. Until then, explicitly report incomplete.
6. Preserve unrelated dirty files and avoid daemon restarts without coordinated worker notification.

## Discovery pointers
`C:\Users\justi\ResellTogether\mcp_server.py`, `chat_attachment_ingest.py`, `chat_memory_import.py`, `CHAT_IMAGE_BRIDGE_FINDINGS.md`, `CHAT_TO_CLOSET_RUNBOOK.md`.
`C:\Users\justi\synapse\daemon\synapse_daemon\image_uploads.py`, `mcp_connector.py`, `chat_attachment_handoff.py`.
