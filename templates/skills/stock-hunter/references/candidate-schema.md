# Candidate schema

A full scoring input is a JSON object with `as_of` and `candidates`.

```json
{
  "as_of": "2026-08-24T14:30:00-05:00",
  "benchmark": "SPY",
  "candidates": [
    {
      "ticker": "MSFT",
      "company": "Microsoft Corp.",
      "sector": "Technology",
      "primary_fundamentals_validated": true,
      "metrics": {
        "price": 488.89,
        "revenue_growth_yoy_pct": 18,
        "eps_growth_yoy_pct": 23,
        "fcf_ttm_usd": null,
        "forward_pe": 24.4,
        "drawdown_52w_pct": -11.7,
        "relative_return_6m_pct": null
      },
      "components": {
        "fundamental_growth": {"score": 90, "evidence": ["https://..."]},
        "quality": {"score": 91, "evidence": ["https://..."]},
        "valuation": {"score": 76, "evidence": ["https://..."]},
        "revisions": {"score": 78, "evidence": ["https://..."]},
        "dislocation": {"score": 80, "evidence": ["https://..."]},
        "catalysts": {"score": 84, "evidence": ["https://..."]},
        "insiders": {"score": null, "evidence": []},
        "technical": {"score": 60, "evidence": ["https://..."]}
      },
      "risk": {
        "leverage_liquidity": 0,
        "event_binary": 1,
        "regulatory_legal_geopolitical": 2,
        "concentration_cyclicality": 1,
        "accounting_quality": 0,
        "valuation_fragility": 1
      },
      "hard_red_flags": [],
      "thesis": "Optional concise thesis.",
      "invalidation": ["Specific fact that would break the thesis."],
      "evidence": []
    }
  ]
}
```

## Component keys

Exactly these positive component keys are recognized:
- `fundamental_growth`
- `quality`
- `valuation`
- `revisions`
- `dislocation`
- `catalysts`
- `insiders`
- `technical`

Each score is 0–100 or null. A component counts toward coverage only when it has a numeric score and at least one evidence reference.

## Risk keys and maxima

- `leverage_liquidity`: 0–4
- `event_binary`: 0–4
- `regulatory_legal_geopolitical`: 0–3
- `concentration_cyclicality`: 0–3
- `accounting_quality`: 0–3
- `valuation_fragility`: 0–3

The values are penalty points, not 0–100 scores.

## Hard red flags

Use sparingly for thesis-invalidating conditions, for example:
- unreliable/qualified financial reporting that prevents analysis
- insolvency/liquidity crisis inconsistent with the intended strategy
- evidence the central thesis is factually false
- unavailable current primary evidence after a material restatement

A hard red flag forces `AVOID` regardless of arithmetic score.

## Breadth price output

`stock_hunter.py prices` emits a separate lightweight JSON format. It is not sufficient for a BUY label. It is a funnel input that future AIs use to choose which names deserve the full candidate schema.
