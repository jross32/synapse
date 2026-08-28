---
name: stock-hunter
description: Evidence-backed public-equity screening, dislocation hunting, and deep-dive ranking. Use when the user asks what stocks to buy, wants a broad screen, wants stocks down on news despite intact fundamentals, asks for valuation/growth/catalyst comparisons, or wants an investment watchlist monitored. Screen broadly first, then spend expensive research only on survivors. Use primary filings and investor-relations releases for reported fundamentals, current market sources for price/estimates, SEC Form 4 for insider activity, and the Web Scraper MCP for structured verification. Never promise guaranteed returns.
---

# Stock Hunter

Build a repeatable stock-selection funnel instead of picking famous tickers from memory. The goal is to find **high-quality, mispriced or underappreciated equities with evidence**, while making uncertainty explicit.

## Non-negotiable rules

1. **No guarantees.** Never describe a stock, return, or ranking as guaranteed, certain, risk-free, or a sure thing.
2. **Concrete as-of date.** Every screen and ranking must say exactly when price, fundamentals, estimates, and catalysts were observed.
3. **Reported vs estimated vs inferred.** Label each metric as one of: `reported`, `market_estimate`, `derived`, or `ai_assessment`.
4. **Primary sources win.** SEC filings and company investor-relations releases are the authority for reported revenue, EPS, cash flow, debt, share count, guidance, and segment results.
5. **Evidence for every material claim.** Preserve URL, publication/filing date, observed value, and source type.
6. **Do not reward missing data.** Low coverage caps a candidate at WATCH even if the partial score is high.
7. **Do not blindly buy drawdowns.** A falling stock only earns a dislocation score when the evidence supports that fundamentals are stable/improving or the selloff is plausibly non-fundamental.
8. **Event-risk gate.** Earnings, FDA decisions, court rulings, binary regulatory decisions, or other near-term events must be surfaced before a BUY label.

Read `references/scoring-model.md`, `references/data-sources.md`, and `references/candidate-schema.md` before a full screen.

## The breadth-to-depth funnel

### Pass A â€” Breadth screen (roughly 50â€“500 names)

Use cheap, machine-readable data. Do not deep-read every company.

Collect where available:
- current price and timestamp
- 52-week high/low and drawdown
- 1m / 3m / 6m / 12m total-price return
- relative strength versus SPY or the requested benchmark
- market cap / liquidity sanity check
- sector / industry
- upcoming earnings date if readily available

Use `python scripts/stock_hunter.py prices --tickers <file> --benchmark SPY --out <file>` for the public price-history lane. It uses a dependency-free public chart endpoint and is intended as a convenience source, not the authority for fundamentals.

Cheap filters should remove obvious mismatches such as:
- insufficient liquidity for the user's objective
- extreme event risk the user did not ask for
- catastrophic downtrend with no fundamental thesis
- no usable evidence path

Keep roughly the best 20â€“30% for Pass B.

### Pass B â€” Fundamental screen (roughly 20â€“60 names)

For each survivor, gather the most recent quarter and trailing/full-year context:
- revenue growth YoY and acceleration/deceleration
- EPS or operating-income growth; flag one-time gains/losses
- operating cash flow
- free cash flow and FCF margin
- capex and whether it is maintenance or growth-oriented where knowable
- cash, total debt, net debt, debt maturity/liquidity concerns
- gross/operating margin trend
- diluted share-count trend
- current guidance and changes to guidance
- forward valuation metrics where reliable

Do not use trailing EPS uncritically when investment gains, tax items, asset sales, impairments, or other unusual items distort earnings.

Run the scalable secondary-data prioritization pass when available:

`python scripts/stock_hunter.py fundamentals --tickers <file> --out <file>`

This collects quarterly revenue, diluted EPS, operating income, free cash flow, debt, cash/short-term investments, plus trailing market cap, FCF and valuation fields. Its `pass_b_quant_score` is **only a prioritization signal**; it cannot produce a BUY label and top candidates still require SEC/company-IR validation because investment gains, cyclic rebounds, restatements and provider normalization can distort raw numbers.

Keep roughly 10â€“20 names for Pass C.

### Pass C â€” Deep opportunity screen (roughly 5â€“20 names)

Add the expensive factors:
- analyst EPS/revenue estimate revisions over 30/60/90 days
- analyst target dispersion and target upside (secondary evidence only)
- SEC Form 4 insider activity; distinguish open-market buys from grants/options/planned sales when possible
- material institutional changes if a reliable source is available
- dated catalysts: earnings, product launches, capacity ramps, approvals, contracts, pricing changes, buybacks, cost reductions, spin-offs, regulatory decisions
- customer/supplier concentration
- competitive threats
- valuation fragility
- accounting-quality concerns
- geopolitical/regulatory exposure

For drawdown candidates, run the **Fundamental Dislocation Test**:
1. Identify the event/news associated with the selloff.
2. Measure the stock move around the event.
3. Verify whether revenue, margins, guidance, balance sheet, demand, or long-term economics actually changed.
4. Assign a dislocation score only if the evidence supports a mismatch between price reaction and business impact.

## Tool routing

Default order:
1. **SEC / official IR** for reported fundamentals and filings.
2. **Synapse Web Scraper MCP** for extracting current IR pages, tables, press releases, filings mirrored on company sites, earnings pages, and structured evidence.
3. **Current web search** for discovery, analyst-revision reporting, catalyst dates, and independent cross-checks.
4. **Browser tools** when a site requires interaction or JS rendering.
5. **Price-history endpoint** through the bundled script for broad price/momentum screening.
6. Optional authenticated/licensed market-data provider when available.

If a source blocks automation, do not bypass controls. Switch to an official alternative or ordinary web source and record the limitation.

## Deterministic scoring

Normalize each candidate to the schema in `references/candidate-schema.md`, then run:

`python scripts/stock_hunter.py score candidates.json --out ranked.json`

The scorer produces:
- component scores
- raw opportunity score
- risk penalty
- final score 0â€“100
- data coverage 0â€“1
- confidence tier
- `BUY`, `WATCH`, or `AVOID`
- reasons and missing-data warnings

The AI may assess catalysts/dislocation/risk only using the rubrics in `references/scoring-model.md` and must attach evidence. Do not simply type a high catalyst score because the narrative sounds exciting.

## Classification gates

A candidate may be labeled **BUY** only when all are true:
- final score meets the threshold in the scoring model
- coverage >= 0.70
- recent reported fundamentals were validated against a primary source
- no unresolved hard red flag
- event risk is explicitly surfaced

Coverage < 0.70 caps the label at WATCH. Coverage < 0.50 normally means AVOID/INSUFFICIENT DATA unless the task is explicitly exploratory.

A high score is a research ranking, not a prediction of guaranteed profit.

## Default output

Return a compact table with:
- rank / ticker / company
- final score / label / confidence
- price and as-of time
- revenue growth
- EPS or operating-income growth
- FCF / FCF trend
- balance-sheet note
- valuation note
- revisions note
- insider note
- catalyst(s)
- dislocation thesis if any
- top 2 risks

Then provide:
1. **Top 3â€“5 deep dives** with why they outranked the rest.
2. **What would change the rating** for each top idea.
3. **Evidence ledger** linking every material number or catalyst.
4. **Watch list** for promising names missing price or evidence confirmation.
5. **Avoid list** with the specific failing criterion, not generic negativity.

## Portfolio use

Do not convert a screen into a concentrated portfolio without considering the user's time horizon, risk tolerance, liquidity needs, diversification, and whether the money can tolerate drawdowns. If these are unknown, give research rankings first rather than pretending to know the correct allocation.

## Monitoring

For a saved shortlist, re-run the relevant parts when:
- earnings or guidance are released
- a major catalyst occurs
- analyst estimates materially revise
- an insider Form 4 appears
- price moves enough to change valuation/dislocation
- the thesis invalidation condition occurs

Preserve the prior score so future AIs can explain **what changed and why the ranking moved**.
