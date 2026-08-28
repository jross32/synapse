# Stock Hunter scoring model

## Overview

Positive components total 100 points before risk. A separate risk penalty of 0–20 is subtracted.

| Component | Weight |
|---|---:|
| Fundamental growth | 25 |
| Business / balance-sheet quality | 15 |
| Valuation | 15 |
| Estimate revisions | 15 |
| Fundamental dislocation | 10 |
| Catalysts | 10 |
| Insider / ownership signal | 5 |
| Technical / relative strength | 5 |
| **Positive total** | **100** |
| Risk penalty | **0 to -20** |

The scorer normalizes available component values. Missing components reduce `coverage`; they do not automatically receive neutral or positive points.

## Component rubrics

### Fundamental growth — 25
Use reported numbers, preferably most recent quarter plus at least one prior comparison.

High scores require several of: accelerating revenue, strong organic growth, strong EPS/operating-income growth, positive and improving FCF, stable/improving margins, credible guidance.

Suggested 0–100 component anchor:
- 90–100: strong double-digit growth plus improving profitability/FCF and credible guidance
- 70–89: healthy growth with only minor weaknesses
- 50–69: mixed/moderate growth
- 25–49: stagnant or deteriorating
- 0–24: material contraction, collapsing margins, or poor cash conversion

### Quality / balance sheet — 15
Consider net cash/debt, debt service, operating margin quality, ROIC/ROE where meaningful, dilution, recurring revenue, customer concentration, and cash conversion.

Do not award a high quality score merely because a company has a large cash balance if share dilution or debt-adjusted economics are poor.

### Valuation — 15
Use several metrics appropriate to the company/sector. Prefer forward P/E, EV/EBITDA, PEG, FCF yield, price/sales for early-stage profitable transitions, and peer-relative valuation.

A cheap multiple is not automatically attractive when earnings are cyclically peaked or deteriorating. A premium multiple can still score well when growth durability and revisions justify it.

### Estimate revisions — 15
Use date-stamped market estimates.

High score requires meaningful upward EPS/revenue revisions across multiple horizons and preferably multiple analysts. Downgrades or falling forward estimates score poorly. If revision data is unavailable, mark missing rather than infer from price.

### Fundamental dislocation — 10
This is deliberately separate from momentum.

- 90–100: price fell materially because of a temporary/non-fundamental event while verified operating fundamentals and guidance remain intact or improve
- 70–89: plausible mismatch with good evidence, but some uncertainty remains
- 50–69: ordinary drawdown or valuation reset with mixed evidence
- 25–49: selloff partly reflects real fundamental damage
- 0–24: price decline is consistent with deteriorating business economics

Never score dislocation highly solely because the stock is far below its high.

### Catalysts — 10
Score evidence-backed catalysts by magnitude, probability, timing, and whether they are already reflected in expectations.

Examples: capacity ramp, new product cycle, pricing action, margin inflection, approval, major contract, buyback, deleveraging, spin-off, restructuring, new market opening.

Binary events with large downside should increase both catalyst and risk; the risk penalty prevents a lottery ticket from looking like a high-conviction BUY.

### Insider / ownership — 5
Prefer SEC Form 4 evidence. Open-market insider buying is positive. Grants/options exercises are not equivalent. Planned sales under 10b5-1 and tax-withholding transactions should not automatically be treated as bearish.

### Technical / relative strength — 5
This is a secondary factor. Prefer 3m/6m relative strength vs SPY/sector and trend stability. Do not let momentum override poor fundamentals.

## Risk penalty — 0 to 20
Assess six risks and document evidence:
- leverage/liquidity: 0–4
- event/binary risk: 0–4
- regulatory/legal/geopolitical: 0–3
- customer/supplier/cycle concentration: 0–3
- accounting/earnings-quality: 0–3
- valuation fragility/expectations: 0–3

0 means low incremental risk; maximum values indicate severe risk.

## Coverage and confidence

Coverage = weighted fraction of positive components with usable evidence.

Confidence:
- High: coverage >= 0.85 and primary-source fundamentals validated
- Medium: coverage 0.70–0.849 with primary-source validation
- Low: coverage 0.50–0.699 or key fields depend heavily on secondary sources
- Insufficient: coverage < 0.50

## Labels

After subtracting risk:
- BUY: final score >= 75, coverage >= 0.70, primary fundamentals validated, no hard red flag
- WATCH: final score 60–74, or otherwise BUY-quality score with coverage/event gate preventing BUY
- AVOID: final score < 60 or a hard red flag invalidates the thesis

`high_conviction_candidate=true` may be shown only when score >= 85, coverage >= 0.85, risk penalty <= 8, and no near-term unresolved binary event.

These are research labels, not guaranteed-return claims.
