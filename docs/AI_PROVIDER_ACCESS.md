# User-owned AI provider access (initial implementation)

Synapse now has a Settings > AI providers & usage panel and a local, per-installation `provider-access.json` policy. The file contains **only user-declared access metadata**, never API keys or session cookies. Credentials must be managed by supported secure integrations. GET/PUT `/api/v1/ai-provider-access` list and update this policy.

Automatic coding-worker selection uses this policy **only after the owner saves it**. Before that, legacy routing is unchanged. Once configured, workers are eligible only when the runtime is implemented, detected, enabled, capacity-eligible, the user has declared an authorized automation method, and included/free usage is available. Extra paid usage is off by default; an explicitly enabled paid policy additionally requires a known per-request cost estimate. This is an initial guard, not yet a hard spending cap or billing authorization system.

The registry includes future API providers such as Grok, Groq, OpenRouter, DeepSeek, Mistral and Together AI, but **listing them does not implement their adapters or verify API access**. Only existing worker runtimes can be launched. Browser ChatGPT setup readiness is not proof of live authentication. User-declared account access and quotas are not independently verified. A paid chatbot subscription does not imply API credits or permission for browser automation.

Next: provider-specific authorization and quota probes, secret-vault-backed API integrations, cost estimates and explicit per-task budgets, failure-aware delegation and checkpoints, trusted test/commit evidence, and packaged desktop verification. Do not alter existing MCP URL or tokens while developing these features.
