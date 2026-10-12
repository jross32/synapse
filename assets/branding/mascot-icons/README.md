# Synapse mascot icon assets

The original Synapse mascot illustrations must not be regenerated, retouched, recolored, or replaced.

A reviewed icon export pack was prepared in the ChatGPT workspace as `synapse-mascot-icons-refined.zip` (download from the originating chat). It is **not yet installed** here because direct attachment transfer via Synapse is unavailable (`SYNAPSE_CHAT_ATTACHMENT_HOSTS` is not configured).

When imported, use `desktop-mascot.ico` for desktop/installer contexts, `companion-head.ico` for assistant controls at >=32 px, and verify small icons at 16/24 px visually. The existing `synapse-s-small` source contains baked-in text and **fails clean tiny-icon quality**; do not replace production icons with it until a clean original S-logo master is sourced. 'Transparent' exports mask only the exterior corners of existing rounded app-icon artwork; the character itself has NOT been isolated from the card background. Keep all original files and hashes; don't change live icons without separate approval and regression checks.
