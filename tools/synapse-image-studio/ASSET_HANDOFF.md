# Synapse image creation and asset handoff runbook

## Capabilities available now
- The Image Studio daemon API supports provider generation, editing, project-scoped imports, and a three-step chunked upload protocol (`/image-generation/uploads/begin`, `/{id}/append`, `/{id}/finish`).
- Project asset import validates image headers/dimensions, restricts project-relative destination paths, records provenance and SHA-256, and respects overwrite controls.
- Focused verification: `.venv\\Scripts\\python.exe -m pytest daemon/tests/test_image_uploads.py daemon/tests/test_image_imports.py -q` (10 passed on 2026-10-09).
- Local image-generation provider is **not configured** (credential status reports missing API key). Do not imply a ChatGPT account subscription grants an OpenAI API credential.

## Required bridge for ChatGPT-generated assets
1. Obtain an actual `png/jpeg/webp` byte stream from the originating runtime; **a sandbox file path or ChatGPT image file ID is not a remotely accessible URL**.
2. If originating runtime can call the authenticated image upload service, upload chunks with SHA-256 and finish the session. Otherwise, use a supported user-controlled file upload (e.g., download the generated image and import via Synapse app UI), or send to an explicitly authorized asset mailbox/storage integration.
3. Never copy a sensitive local path or token to public `download.whatapc.com`. Keep the upload endpoint authenticated, project-confined, and private.
4. Import into the selected project (for the Synapse download site, the project ID is `synapse`, destination `download-site/assets/brain.webp`), then update site markup and responsive CSS.
5. Verify SHA-256 and production HTTPS image content, desktop/iPhone Chromium and WebKit screenshots, and download/navigation flows.
6. Record image provenance, site commit, checks, and deployed SHA.

## Current blocker on the brain artwork
The ChatGPT image `/mnt/data/luminous_neon_ai_brain_network.png` is stored in the assistant sandbox, not in the Windows Synapse host. Neither `synapse_run_command` nor `synapse_write_file` accepts an attachment or reads assistant sandbox paths. No supported automatic byte transfer between those environments has been demonstrated. Until a real transfer succeeds, the live download site continues to use its SVG hero and the generated PNG is **not installed**. Do not claim otherwise.

## API-first host workflow (once image exists on Windows)
Use the authenticated image-generation import API or local `synapse_daemon.image_imports.import_image_file` with `project_root`, `source_path`, and `relative_path`, then audit and deploy. The existing source is `daemon/synapse_daemon/image_imports.py`; the chunked protocol is `daemon/synapse_daemon/image_uploads.py`.
