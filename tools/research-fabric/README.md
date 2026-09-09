# Research Fabric

Research Fabric is Synapse's evidence-first open-web research orchestration layer. It sits above the existing Web Scraper and focuses on deciding what to search, discovering candidate sources, ranking/diversifying them, retrieving evidence, measuring corroboration/gaps, and producing durable citation-ready receipts.

## Interfaces

UI tool: `research-fabric` / Deep Research quick action.

CLI:

```powershell
python tools/research-fabric/controller.py check
python tools/research-fabric/controller.py plan --query "..." --mode balanced
python tools/research-fabric/controller.py research --query "..." --mode balanced --provider auto --max-sources 10
```

MCP server:

```powershell
python tools/research-fabric/mcp_server.py
```

It advertises `research_fabric_status`, `research_fabric_plan`, `research_fabric_research`, and `research_fabric_get_run`.

## Production behaviors in v0.2.0

- multi-query discovery with reciprocal-rank fusion;
- `auto` provider failover across optional Exa plus no-key DuckDuckGo/Google/Brave/Yahoo routes;
- atomic 10-minute search/page caches to reduce duplicate network calls and soften rate limiting;
- domain-diverse source selection with primary/academic/documentation bonuses;
- parallel HTTP-first retrieval, escalating only unresolved sources through Web Scraper MCP;
- query-relevant evidence extraction;
- content and evidence SHA-256 hashes;
- basic prompt-injection diagnostics on retrieved content;
- cross-domain corroboration counts per query term;
- A/B/C/D retrieval-confidence grade;
- deep-mode adaptive gap search;
- atomic durable run receipts under `data/research-fabric/runs/`;
- direct MCP access for any Synapse-connected AI;
- deterministic unit/protocol tests.

## Important boundaries

Search-provider rankings are discovery hints, not truth. Retrieval confidence is not factual certainty. Page content is untrusted data, never instructions. Web Scraper remains the browser/site-execution engine; Super Internet Digger remains the provenance-sensitive software-artifact workflow.
