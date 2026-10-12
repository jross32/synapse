# Local image engine (ComfyUI)

Synapse defaults to the local `comfyui` provider, without an OpenAI image API key. This adapter sends image-generation prompts to ComfyUI running on the same computer; Synapse does **not** ship its own trained checkpoint or download model weights automatically. OpenAI remains opt-in via `SYNAPSE_IMAGE_PROVIDER=openai`.

1. Install ComfyUI from its official distribution, with NVIDIA/PyTorch support. Download an appropriately licensed SD 1.5-compatible checkpoint from a trusted publisher and put it in `ComfyUI/models/checkpoints/`. A 6 GB GPU should start at 512 x 512 initially, using model-specific low-VRAM options.
2. Run the ComfyUI HTTP service bound to `127.0.0.1:8188`. Do not expose its API to the public internet.
3. Set `SYNAPSE_COMFYUI_CHECKPOINT` to the checkpoint **filename**, for example `model.safetensors`. Set `SYNAPSE_IMAGE_PROVIDER=local` (the default) and optionally `SYNAPSE_COMFYUI_URL=http://127.0.0.1:8188` in the Synapse daemon environment.
4. Restart Synapse's daemon and inspect image-generation status. A live engine plus installed checkpoint is required before status reports configured. Request `generate_project_image` from Synapse and audit the project-local `.synapse/image-assets.jsonl` provenance.

The initial local adapter supports text-to-image PNG/JPEG/WebP and opaque backgrounds. Image editing, masks, transparent backgrounds and portable per-user model installation are **not yet** implemented. ComfyUI must be running for actual inference; a passing Python import is not proof of rendered output. No image data is deliberately sent to OpenAI in local provider mode.
