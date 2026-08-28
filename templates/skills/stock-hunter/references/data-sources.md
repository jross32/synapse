# Data sources and evidence policy

## Source priority

### Tier 1 — primary / authoritative
Use these for reported company facts whenever possible:
- SEC 10-K, 10-Q, 8-K, Form 4, proxy filings and XBRL/companyfacts
- company investor-relations earnings releases and presentations
- official regulator decisions and government releases
- exchange/company announcements for corporate actions

### Tier 2 — high-quality market data / consensus
Use for values that companies do not report themselves:
- licensed or reputable market-data feeds
- current quote/history providers
- analyst-consensus/revision services
- exchange calendars and earnings-date services

Always date-stamp estimates. Consensus is not a fact about future results.

### Tier 3 — reputable reporting / discovery
Use current financial press and ordinary web search for:
- identifying the event behind a price move
- analyst commentary
- catalyst discovery
- competitive context

Cross-check material claims against primary sources where feasible.

### Tier 4 — community / social signals
May be used to discover a thesis, never as sole evidence for reported financial facts.

## Web Scraper MCP routing

Useful direct tools include:
- `research_url`: earnings/IR page question answering with evidence
- `scrape_url` + `get_page_text`: full capture when the summary is insufficient
- `get_tables`: financial/segment tables
- `extract_structured_data`: machine-readable article/organization metadata
- `search_scrape_text`: find guidance, revenue, cash flow, debt, capex, margins
- `monitor_page`: re-check a known IR/catalyst page for changes
- browser-session tools: only when JS interaction is required

Do not probe hidden endpoints or bypass site controls merely to obtain stock data. Public research does not require security-testing behavior.

## SEC details

For insider activity, prefer Form 4 and identify transaction code/type. Distinguish:
- open-market purchases
- open-market sales
- option exercises
- grants/awards
- tax withholding
- 10b5-1/planned transactions when disclosed

For reported fundamentals, note fiscal period and filing/release date. Be careful with XBRL tag variation and amended filings.

## Analyst revisions

Record at minimum:
- source/provider
- observation date/time
- estimate period (current quarter, FY, next FY)
- old estimate if available
- new estimate
- percent revision
- number of analysts where available

If only a price target is available, do not substitute it for estimate revisions.

## Evidence record

Every material evidence item should preserve:
```json
{
  "url": "https://...",
  "source_type": "sec|company_ir|market_data|analyst_consensus|news|other",
  "published_at": "2026-08-24",
  "observed_at": "2026-08-24T14:30:00-05:00",
  "fact": "Azure and other cloud services revenue increased 43% YoY.",
  "metric": "azure_growth_yoy_pct",
  "value": 43,
  "value_type": "reported|market_estimate|derived|ai_assessment"
}
```

## Freshness

- price: same trading day when possible
- analyst estimates/revisions: preferably <= 7 days old for active screens
- insider filings: query through the screen date
- reported fundamentals: latest available quarter plus prior comparison
- catalysts: current scheduled date, rechecked before final ranking

If freshness is weaker, explicitly lower confidence rather than silently presenting old data as current.
