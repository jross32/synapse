# Tool routing and performance

Use the smallest capable tool set. Direct tools stay available even when Warden is installed.

| Need | Preferred route | Fallback |
|---|---|---|
| Repository tags/releases/files | GitHub connector, `gh`, or Git | official release API/page |
| Unknown website structure | Web Scraper preflight/discovery | browser or ordinary web search |
| Signed-in user portal | authenticated browser/session handoff | user-provided authorized artifact URL |
| Public docs/evidence capture | Web Scraper | direct web open |
| Choose among many MCP tools | Warden if installed | select direct tool explicitly |
| Local project inspection | bundled `digger_pipeline.py inspect` | read manifests manually |

## Speed rules

- Run independent official/code/alternative lanes concurrently.
- Batch search queries and page opens when the tool supports batching.
- Use a repository API or `git ls-remote` instead of scraping repository HTML.
- Cache stable facts within the run: owner identity, license, latest tag, and official domains.
- Stop when the evidence contract is complete; more results are not automatically better.
- Retry only when the input, route, credentials, or transient condition changed.
- Deduplicate by canonical URL and immutable version before deeper inspection.

## Warden rule

Warden is an optional meta-router. It may discover or invoke an MCP tool, but:

- the workflow must still work without Warden
- HTTP MCPs and tools Warden cannot wrap stay direct
- no credential is copied into Warden configuration by the skill
- the final handoff names the underlying tool and evidence source, not merely "Warden"
