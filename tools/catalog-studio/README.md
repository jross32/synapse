# Catalog Studio

A deterministic product-photo pipeline for resale catalogs.

## Contract

Catalog Studio does **not** ask an image model to redraw a garment. It extracts or accepts a transparent cutout of the real source photo and composites those pixels onto a versioned studio preset. The output receipt records source/output SHA-256, preset version, segmentation method, recommendation and QA state.

Automatic segmentation uses direct local ONNX inference with the lightweight `u2netp` model. No generative image model redraws the garment. A transparent PNG may also be supplied via `--subject`; the deterministic compositor and preset system remain usable independently of automatic segmentation.

Presets: Warm Gallery, Clean White, Cool Concrete, Charcoal. `auto` makes a deterministic contrast-oriented recommendation while preserving the user's ability to lock one preset for a whole storefront.

## Input robustness
Marketplace/CDN JPEGs that are structurally decodable but end a byte or two early are accepted by Pillow's tolerant decoder. Segmentation QA still fails closed: suspicious edge/border coverage is marked review_required instead of silently approved.


## Production verification

Verified in Synapse native Tools API on Catalog Studio v0.7.1:
- async single-photo launch returns immediately and completes out-of-process;
- locked `Resell Main` profile produces 1600x2000 Warm Gallery outputs;
- async batch processing emits per-item receipts plus a batch receipt;
- real web clothing input completed with `qa_status=pass`;
- adversarial CDN JPEG with a truncated tail decodes safely, then correctly fails closed as `review_required` because its inferred subject touches image borders;
- provenance records source/output hashes plus segmented subject RGB and alpha hashes.

`review_required` is intentional. Catalog Studio must not silently approve a questionable cutout merely to increase automation rate.

Catalog Studio v0.7.2 tightens automatic review for subjects touching more than 10% of the source-image perimeter, based on adversarial real-web-photo QA.

Catalog Studio v0.7.3 also keeps the async worker error-path test in-process, avoiding unnecessary subprocess startup for that unit contract.

## v0.8.0 acceptance

Catalog Studio v0.8.0 adds explicit fail-closed review reasons and a review package containing the extracted RGBA subject, grayscale alpha mask, and side-by-side source/extraction preview.

Final focused verification on 2026-10-04:
- core pipeline tests: **11/11 passed**;
- async controller tests: **5/5 passed** (4 fast contracts plus the ONNX-import worker-error contract run separately);
- native Synapse real-garment batch: **3 processed, 2 pass, 1 review_required, 0 errors**;
- the review case reported `mask_too_soft` and emitted subject/mask/preview artifacts;
- native Synapse tool discovery reports manifest version **0.8.0**.

The QA gate is intentionally conservative: questionable segmentation is surfaced for review rather than silently published.
## Focused verification on the Synapse host
The shared Synapse Python environment has many unrelated pytest plugins. For deterministic, fast Catalog Studio verification, disable global plugin autoload and limit BLAS startup threads before running this tool's focused tests:

PowerShell: $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; $env:OPENBLAS_NUM_THREADS='1'; .\\.venv\\Scripts\\python.exe -m pytest -q tools\\catalog-studio\\test_catalog_studio.py tools\\catalog-studio\\test_async_catalog.py

Final v0.8.0 acceptance on 2026-10-04: 16/16 focused tests passed; fresh three-garment async batch completed with 2 automatic passes, 1 intentional review_required, and 0 errors. The review-required case emitted subject, mask, and preview artifacts.
