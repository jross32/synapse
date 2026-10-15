# Fast Money Client Ops

## Product brief
Build a private/local-first client-ops SaaS for service businesses that turns leads into quotes, approvals, jobs, invoices, and renewals.

## Defaults
- Pricing model: hybrid
- Customer portal: yes
- Employee console: yes
- Catalog editor: no
- Project id: fast-money-client-ops
- Project path: C:\Users\justi\synapse\data\projects\fast-money-client-ops
- Launch command: python server.py
- Expected port: 8740

## Required flow
- Lead -> quote -> approval -> engagement/job -> invoice -> renewal handoff

## Non-negotiables
- Keep the app private/local-first by default.
- Keep billing/auth integrations as adapter seams with config placeholders, not hardcoded secrets.
- Preserve README.md, ARCHITECTURE.md, MONETIZATION.md, seed-data.json, and FAST_MONEY_BRIEF.md as project memory.
