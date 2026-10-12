# AI provider cost benchmark

This benchmark is append-only and intentionally separates **provider-reported costs** from unknown subscription billing. Initial baseline: `baseline-2026-10-12.json`.

Run `python benchmarks/ai-provider-costs/check_drift.py` after appending a comparable new JSON record with `samples` entries. Each sample should retain provider, model, task, input/output/cache tokens where available, wall time, cost and source. Do not infer $0 from an absent cost. Image cost stays unknown until a billable image is actually generated and its cost verified.

Recommended future checks: small advice task, targeted patch, full feature, single image (model, resolution, quality), image edit, repeat with warm cache, and successful-tests-per-dollar. Record daily counters separately because other projects may consume them.

## Automatic Synapse monitoring (installed 2026-10-12)

`watch_ledger.py` reads Synapse's **existing** `data/runtime-ledger.jsonl` (does not modify it), and optional `data/image-usage.jsonl` (explicit provider-reported image charges). It writes `latest-report.json` and flags cost-per-image changes >=20% and comparable unchanged-call-count aggregate cost changes >=20%. It never converts missing prices into zero. The Windows Scheduled Task `Synapse-AI-Cost-Monitor` runs hourly, starting approximately five minutes after installation. This is a **report/alert-file monitor**, not push notifications; open `latest-report.json` to see `alerts`. It runs only while Windows Task Scheduler and the computer are available. Usage capture itself depends on existing Synapse runtime instrumentation; direct CLI calls not logged there remain untracked.

Run `python benchmarks/ai-provider-costs/test_watch_ledger.py` to validate unknown-price and image-unit-cost handling. New image providers should append entries to `data/image-usage.jsonl` with `provider`, `model`, `operation`, `image_count`, and `reported_cost_usd` (null when unknown). Do not store API keys, prompts, or images in that ledger.
