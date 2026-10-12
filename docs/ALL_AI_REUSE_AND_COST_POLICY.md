# Synapse global AI implementation policy

## Inspect before building

Every Synapse AI (ChatGPT, Codex, Claude, Copilot, Gemini and local agents) must read the existing Synapse architecture, active processes, workers, projects, work-in-progress, Git changes, APIs, integration points and released artifacts before proposing code. Prefer modifying or composing existing tested components to rebuilding. Coordinate file ownership, avoid overwriting other agents' work and preserve existing working releases.

## Budget-aware model routing: mandatory preflight

Before EACH external AI dispatch:
1. Query Synapse's actual runtime status and recent usage/credit ledger. Check current 5-hour/session, daily, 7-day, monthly, credit, RPM/TPM and vendor-specific windows whenever that provider exposes them. Track time to reset, credits left, reserved credits and concurrent jobs. Don't infer remaining quota from calls_today alone.
2. Estimate token/context size, requests, wall time, effective premium-request multipliers, and dollar/credit usage. Distinguish included subscription capacity, metered API spend, and unknown costs. A provider returning $0 cost is NOT proof of unlimited allowance.
3. Route smallest sufficient bounded task: first main ChatGPT directly using Synapse tools and web/public official docs where suitable; next existing free/local and low-cost viable providers; paid Claude/Codex/Copilot only when a measured quality or capability gap justifies it. Don't dispatch multiple large agents for the same work.
4. Reserve budget for retries, validation and release-critical work. Use configurable per-task, per-project, per-provider, per-day/week/month budgets. Hard-block estimated over-budget dispatch unless explicitly approved; warn before reaching soft thresholds (70%, 85%, 95%).
5. On throttling or expiration, record the exact provider, window, reset timestamp and reason; fall back safely or wait. Never bypass approvals, credential controls, or shared rate limits. Review consumption against estimates after each job.
6. Summarize cost, tokens, provider roles, elapsed time and verification provenance honestly; mark missing provider quota as unknown rather than making up percentages.

## Research before implementation

For any substantial new integration, first research official documentation/pricing/quota policies and existing Synapse capabilities. Use ChatGPT's web research as needed; delegate narrow fact-finding to an appropriate agent only when cheaper or more capable. Capture cited evidence, version/date, constraints and alternatives in an implementation brief. Plan an incremental design, validate compatibility with concurrent agents, then implement. Don't blindly research every minor change or restart an already researched project.

## Vendor-specific windows are NOT interchangeable

Codex/ChatGPT quotas can be shared and include 5-hour/weekly windows and applicable credits; provider account usage dashboards are authoritative. Claude paid plans commonly have 5-hour session and weekly quotas shared with Claude Code. Copilot premium requests have monthly budgets and variable model multipliers. API pricing and Gemini/local quotas are separate. Never hardcode exact quotas or prices as permanent facts: query up-to-date official provider data or admin-configured account limits.

## Release gates

Never call a mockup, preview app, or build production-ready without actual tested payload and end-to-end evidence. Preserve previous functional versions until replacement installation, migrations, upgrade and recovery are verified. Follow AGENTS.md, CLAUDE.md, .github/copilot-instructions.md and docs/MULTI-AI-WORKFLOW.md; this policy supplements them.
