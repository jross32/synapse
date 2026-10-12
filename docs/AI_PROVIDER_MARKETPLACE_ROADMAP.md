# Synapse AI Provider Marketplace — researched implementation plan (2026-10-10)

## Product requirements
ChatGPT is primary orchestrator. Existing ChatGPT/Codex, Claude, Copilot subscriptions are tracked separately from API spending. Plan presets: $0, $15, $30, $60, $100 additional API budget per calendar month. Never enable paid APIs without user consent. Free tiers first, then subscriptions where automation is supported, then approved metered API, then local. Route by capability/quality, not just price. No guaranteed equivalence between provider accounts, subscriptions and API access.

## Verified official provider data (pricing and limits change; recheck on connection)
- Gemini API: some models have free token usage, model-dependent limits and data-use conditions; paid tier requires billing. https://ai.google.dev/gemini-api/docs/pricing.md
- Groq free API: per-model limits; GPT OSS 120B shown at 1,000 requests/day and 30 RPM on free plan; actual account limits in dashboard. https://console.groq.com/docs/rate-limits
- OpenRouter free: 25+ free models, 50 requests/day; paid standard has 5.5% platform fee. https://openrouter.ai/pricing/
- Cloudflare Workers AI free: 10,000 neurons/day; beyond free on paid plan $0.011/1,000 neurons; certain models require billing. https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cerebras: one-time $5 promotional credit requiring payment method, expires in 30 days; not permanent free usage. https://www.cerebras.ai/pricing
- Replicate sample images: FLUX schnell $3/1,000 images; FLUX 1.1 pro $0.04/image. https://replicate.com/pricing
- fal.ai sample images: FLUX schnell $0.003/megapixel; Z Image Turbo $0.005/megapixel; Nano Banana $0.0398/image. https://fal.ai/pricing
- GitHub Copilot Pro $10/mo and Pro+ $39/mo listed; plan credits are not equivalent to API cash budget. https://docs.github.com/en/copilot/get-started/plans

## Plan presets (API-only hard ceilings, not bundles)
A=0, B=15, C=30, D=60, E=100 USD/month. Proposed split for B-E: 45% reasoning/coding, 35% creative generation, 20% reserve. Per-provider and per-capability caps should also apply; pending requests reserve estimated maximum charge atomically, then reconcile actual usage. When telemetry is missing or stale, block metered requests or require explicit approval; never interpret missing data as zero cost. Set provider-native caps too where available; note that native dashboards can lag.

## Architecture / phases
1. Provider registry: adapter id, auth method, supported tasks, pricing model, free quota, reset timezone, eligibility, capabilities, concurrency, account status and official pricing source; separate connection and authorization.
2. Budget ledger: append-only events (request reserved/settled/failed/refunded), daily/weekly/monthly totals, atomic hard-stop enforcement across devices, per-provider/model ceilings, notifications at 50/75/90/100%, monthly reset and audit.
3. Router: first-party ChatGPT coordination where available, then existing subscriptions via their supported CLIs, then verified free cloud API pools, then approved paid API, then local. Never use consumer websites as unapproved automation/API substitutes. Preserve quality and privacy constraints.
4. Provider onboarding in stages: existing Codex/Claude/Copilot/Gemini/local; Groq, OpenRouter, Cloudflare, Cerebras; image providers Replicate/fal; then others via adapter contracts. Include sandboxed write tests for agents.
5. UI: Provider Marketplace, connection state, usage, free quota, price sources, plan simulator, real-time ledger, capability and fallback order, monthly hard cap, spend approval, image batch queue.
6. Tests: concurrent reservation race, budget boundary, stale telemetry, provider 429, provider 402, retry idempotency, user revoke, free-tier exhaustion, no-cost failover, isolated filesystem permissions, end-to-end batch image generation and uploads.

## Status
Research and implementation plan created. Not yet connected: most candidate providers. Hard caps, provider billing connectors, and marketplace UI not implemented/verified. Codex can write files in an isolated folder with full access; Synapse delegate workspace sandbox still needs repair.
