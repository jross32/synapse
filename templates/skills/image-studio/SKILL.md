# Synapse Image Studio

Use this skill whenever the user or the current project needs an image to be generated, edited, composited, restyled, cleaned up, or turned into a production-ready visual asset.

## Goal

Make image creation feel native to any AI connected to Synapse. The AI should not make the user translate a creative request into provider parameters. Infer the technical settings from the task, call the Synapse image tools, save the result inside the relevant registered project, and report the asset path and provenance.

## Core tool routing

1. Call `synapse_image_generation_status` when provider readiness is unknown.
2. For a new image from text, call `synapse_generate_image`.
3. For edits or reference-guided work, make the reference image project-local first using `synapse_import_image_file` or the chunked upload tools, then call `synapse_edit_image`.
4. Use `synapse_list_project_images` / `synapse_get_image_asset` to discover or inspect existing assets before creating duplicates.
5. Use `synapse_audit_image_assets` when verifying provenance or integrity matters.

## Quality defaults

Choose quality from the user's actual need:

- `max`: photorealistic people/products/environments, hero art, marketing images, precision edits, identity/garment/object consistency, or whenever the user emphasizes "realistic", "perfect", "highest quality", or equivalent.
- `xhigh`: normal production assets where excellent quality matters but absolute maximum fidelity is unnecessary.
- `high`: polished everyday production images.
- `medium`: drafts, layout exploration, thumbnails, or fast iterations.
- `low`: only when speed/cost clearly matters more than visual fidelity.
- `auto`: only when the task gives no useful quality signal.

Synapse's server-side default model is the best configured image model. Do not hard-code a provider model in normal AI workflows. The current recommended server profiles are best-quality `gpt-image-2.5-sunburst` and fast `gpt-image-2.5-flare`.

## Photorealistic prompting

For realistic photography, write a concrete production brief rather than a pile of vague quality adjectives. Include the subject, environment, camera/framing, lighting, materials/skin/fabric behavior, pose or action, depth of field when relevant, and what must remain consistent. Prefer natural physical details over phrases like "8K masterpiece".

When a reference image is present, explicitly state what must be preserved and what may change. For example: preserve the shirt artwork, garment color, pose family, and subject identity; replace only the background and lighting.

If the request is about a product or clothing listing, prioritize truthful representation of the product over dramatic stylization.

## Output paths

Save generated work inside the selected Synapse project. Prefer a predictable asset folder such as:

- `public/images/ai/...`
- `assets/generated/...`
- `art/generated/...`

Use a descriptive filename. Do not overwrite an existing image unless replacement is explicitly intended. If a name collision occurs, create a new versioned filename rather than forcing overwrite.

## Iteration behavior

Generate a strong first result, then refine from evidence. If the result needs a change, edit the existing image when preserving composition/identity/product details is important; regenerate from scratch when the direction itself is changing.

Do not create several near-identical expensive variants unless the user asked for options or comparison. Prefer one high-quality result plus targeted revisions.

## Safety and provenance

Follow the image provider's safety rules and normal Synapse permission boundaries. Keep provider credentials secret. Every provider-backed output should remain project-scoped and retain Synapse provenance/integrity metadata.

If provider generation is not configured, report that exact blocker. Native image import, transfer, listing, and auditing can still be available even when provider-backed generation is blocked.

## Completion standard

Do not claim an image was generated unless the tool returned a created asset. Report the project-relative path, selected quality, and whether the result was generated or edited. If the provider is blocked, say so directly and preserve any preparatory work without pretending a render occurred.
