# UI Forge Asset Slots

Asset Slots connect generated or imported raster images to exact rendered `<img>` elements without turning image generation itself into a source-editing shortcut.

## Intended flow

1. Produce or obtain a local raster image. When generation is requested and Synapse Image Studio is available/configured, use that capability; UI Forge does not duplicate the provider.
2. Stage the file with `scripts/asset_slot.mjs stage <project-root> <asset-file>`.
3. The stage step validates PNG/JPEG/WebP bytes, size, basic dimensions, computes SHA-256, and copies the asset into the project-owned `/ui-forge-assets/` namespace with a provenance receipt. It does not change application source.
4. Inject `scripts/asset_preview_bridge.js`, select the real `<img>`, and preview only the staged root-relative `/ui-forge-assets/...` URL.
5. Require successful decode (`naturalWidth` and `naturalHeight` > 0), inspect geometry and surrounding composition, then generate the exact source commit spec.
6. Revert the browser preview before source mutation.
7. Dry-run `asset_slot.mjs commit` with the exact `data-ui-forge-source` pointer and meaningful alt text.
8. Commit only if the target is an intrinsic `<img>` with a static string `src` and JSX reparses successfully.
9. Rerender/HMR, re-probe the same UI Forge ID, verify decode/natural dimensions/alt/layout, then run desktop/mobile and console proof.

## Safety boundary

The deterministic lane accepts PNG, JPEG, and WebP only. SVG is deliberately excluded because it can contain active content and requires a different trust model. Disguised non-images, oversized assets, wrong-project receipts, integrity mismatches, dynamic `src`, non-`img` source targets, path escapes, and missing exact source ownership fail closed.

Staged assets can be discarded if they remain unreferenced. Once project source references an asset, the staging cleanup path refuses deletion. Committed assets retain provenance under `.synapse/ui-forge/assets/committed/`.

## Provider separation

Asset Slot benchmarks prove **asset integrity, preview, provenance, and exact source placement**, not image-generation quality. Keep provider/model claims separate. A generated image must still be evaluated visually for the requested composition, realism, typography, brand fit, licensing/provenance constraints, and accessibility context.
