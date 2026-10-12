# Synapse: image-to-project playbook

When an AI needs to save artwork into a project, do not paste PNG/JPEG/WebP bytes into synapse_write_file. For SVG, write UTF-8 SVG source directly via synapse_write_file to an absolute project path and verify by reading it back. For binary images use synapse_import_image_file (local machine), synapse_generate_image/edit_image (provider configured), or begin_image_upload + append_image_upload + finish_image_upload (external AI base64 chunks). The binary image tools require a registered project ID and automatically validate and record provenance. Register an existing project directory rather than creating a duplicate.

WhatAPC example: C:\Users\justi\WhatAPC\public\media\whatapc-hero-emblem.svg was saved by synapse_write_file and served HTTP 200. Project handoff: C:\Users\justi\WhatAPC\docs\SYNAPSE_ASSET_HANDOFF.md. WhatAPC was registered in Synapse as project_id=whatapc. An existing PNG was imported through synapse_import_image_file with dimensions and SHA-256 provenance recorded. Synapse image generation was unconfigured at last check; don't claim otherwise.

For public sites with asset allowlists, permit the file explicitly, check Content-Type, then run browser tests and HTTP smoke tests. Approved asset manifest controls published generated images.

