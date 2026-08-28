#!/usr/bin/env python3
"""Deterministic helpers for the Synapse Stock Hunter skill.

No third-party packages are required.

Commands:
  prices --tickers tickers.txt --benchmark SPY --out price-screen.json
  score candidates.json --out ranked.json

The price command is a breadth-screen convenience. It does not provide enough
fundamental evidence for a BUY label. The score command consumes the normalized
candidate schema documented in references/candidate-schema.md.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

WEIGHTS: dict[str, float] = {
    "fundamental_growth": 25.0,
    "quality": 15.0,
    "valuation": 15.0,
    "revisions": 15.0,
    "dislocation": 10.0,
    "catalysts": 10.0,
    "insiders": 5.0,
    "technical": 5.0,
}

RISK_MAX: dict[str, float] = {
    "leverage_liquidity": 4.0,
    "event_binary": 4.0,
    "regulatory_legal_geopolitical": 3.0,
    "concentration_cyclicality": 3.0,
    "accounting_quality": 3.0,
    "valuation_fragility": 3.0,
}

USER_AGENT = os.environ.get(
    "STOCK_HUNTER_USER_AGENT",
    "Mozilla/5.0 (compatible; Synapse-Stock-Hunter/1.0; public-research)",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _has_evidence(component: Any) -> bool:
    if not isinstance(component, dict):
        return False
    evidence = component.get("evidence")
    return isinstance(evidence, list) and len(evidence) > 0


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    components = candidate.get("components") if isinstance(candidate.get("components"), dict) else {}
    weighted_sum = 0.0
    covered_weight = 0.0
    component_rows: dict[str, dict[str, Any]] = {}

    for key, weight in WEIGHTS.items():
        raw_component = components.get(key) if isinstance(components, dict) else None
        score = _as_float(raw_component.get("score")) if isinstance(raw_component, dict) else None
        usable = score is not None and _has_evidence(raw_component)
        if score is not None:
            score = _clamp(score, 0.0, 100.0)
        contribution = None
        if usable and score is not None:
            weighted_sum += score * weight
            covered_weight += weight
            contribution = score * weight / 100.0
        component_rows[key] = {
            "score": score,
            "weight": weight,
            "covered": usable,
            "weighted_points": round(contribution, 2) if contribution is not None else None,
        }

    coverage = covered_weight / sum(WEIGHTS.values()) if WEIGHTS else 0.0
    normalized_positive = weighted_sum / covered_weight if covered_weight else 0.0
    # Missing data should never make a sparse record look equally certain.
    uncertainty_multiplier = 0.80 + 0.20 * coverage
    coverage_adjusted = normalized_positive * uncertainty_multiplier

    risk = candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {}
    risk_rows: dict[str, float] = {}
    risk_penalty = 0.0
    for key, max_points in RISK_MAX.items():
        value = _as_float(risk.get(key)) if isinstance(risk, dict) else None
        points = _clamp(value if value is not None else 0.0, 0.0, max_points)
        risk_rows[key] = round(points, 2)
        risk_penalty += points

    final_score = _clamp(coverage_adjusted - risk_penalty, 0.0, 100.0)
    primary_validated = bool(candidate.get("primary_fundamentals_validated"))
    red_flags = candidate.get("hard_red_flags")
    if not isinstance(red_flags, list):
        red_flags = []

    if coverage >= 0.85 and primary_validated:
        confidence = "high"
    elif coverage >= 0.70 and primary_validated:
        confidence = "medium"
    elif coverage >= 0.50:
        confidence = "low"
    else:
        confidence = "insufficient"

    gates: list[str] = []
    if red_flags:
        label = "AVOID"
        gates.append("hard_red_flag")
    elif coverage < 0.50:
        label = "AVOID"
        gates.append("coverage_below_0.50")
    elif final_score >= 75.0 and coverage >= 0.70 and primary_validated:
        label = "BUY"
    elif final_score >= 60.0 or final_score >= 75.0:
        label = "WATCH"
        if coverage < 0.70:
            gates.append("coverage_below_buy_gate")
        if not primary_validated:
            gates.append("primary_fundamentals_not_validated")
    else:
        label = "AVOID"

    event_risk = risk_rows.get("event_binary", 0.0)
    high_conviction = bool(
        label == "BUY"
        and final_score >= 85.0
        and coverage >= 0.85
        and primary_validated
        and risk_penalty <= 8.0
        and event_risk <= 1.0
        and not red_flags
    )

    ranked_components = sorted(
        (
            (key, row["weighted_points"])
            for key, row in component_rows.items()
            if row["weighted_points"] is not None
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    missing = [key for key, row in component_rows.items() if not row["covered"]]

    out = dict(candidate)
    out["stock_hunter"] = {
        "positive_score_normalized": round(normalized_positive, 2),
        "coverage": round(coverage, 4),
        "coverage_adjusted_score": round(coverage_adjusted, 2),
        "risk_penalty": round(risk_penalty, 2),
        "final_score": round(final_score, 2),
        "label": label,
        "confidence": confidence,
        "high_conviction_candidate": high_conviction,
        "primary_fundamentals_validated": primary_validated,
        "gates": gates,
        "hard_red_flags": red_flags,
        "missing_components": missing,
        "top_component_contributors": [
            {"component": key, "weighted_points": round(points, 2)}
            for key, points in ranked_components[:4]
        ],
        "component_detail": component_rows,
        "risk_detail": risk_rows,
        "method_version": "1.0.0",
    }
    return out


def score_file(input_path: Path, output_path: Path | None) -> dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        candidates = payload
        meta: dict[str, Any] = {}
    elif isinstance(payload, dict):
        candidates = payload.get("candidates")
        meta = {k: v for k, v in payload.items() if k != "candidates"}
    else:
        raise ValueError("Scoring input must be a JSON object or array.")
    if not isinstance(candidates, list):
        raise ValueError("Scoring input must contain a candidates array.")

    scored = [score_candidate(c) for c in candidates if isinstance(c, dict)]
    label_priority = {"BUY": 2, "WATCH": 1, "AVOID": 0}
    scored.sort(
        key=lambda c: (
            label_priority.get(c.get("stock_hunter", {}).get("label", "AVOID"), 0),
            c.get("stock_hunter", {}).get("final_score", 0),
            c.get("stock_hunter", {}).get("coverage", 0),
        ),
        reverse=True,
    )
    for index, candidate in enumerate(scored, 1):
        candidate["stock_hunter"]["rank"] = index

    result = {
        **meta,
        "scored_at": _utc_now(),
        "method": "Synapse Stock Hunter 1.0.0",
        "weights": WEIGHTS,
        "risk_max": RISK_MAX,
        "candidates": scored,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return result


def _load_tickers(value: str) -> list[str]:
    path = Path(value)
    if path.exists() and path.is_file():
        raw = path.read_text(encoding="utf-8-sig")
        pieces = raw.replace("\r", "\n").replace(",", "\n").split("\n")
    else:
        pieces = value.split(",")
    out: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        ticker = piece.strip().upper()
        if not ticker or ticker.startswith("#") or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _pct_return(current: float, prior: float | None) -> float | None:
    if prior is None or prior == 0:
        return None
    return (current / prior - 1.0) * 100.0


def _chart_url(ticker: str) -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?range=1y&interval=1d&events=div%2Csplits"


def fetch_price_record(ticker: str, retries: int = 3) -> dict[str, Any]:
    url = _chart_url(ticker)
    last_error: str | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                error = (payload.get("chart") or {}).get("error")
                raise RuntimeError(f"No chart result: {error}")
            chart = result[0]
            meta = chart.get("meta") or {}
            timestamps = chart.get("timestamp") or []
            indicators = chart.get("indicators") or {}
            adj = ((indicators.get("adjclose") or [{}])[0].get("adjclose") or [])
            closes = ((indicators.get("quote") or [{}])[0].get("close") or [])
            series = adj if any(v is not None for v in adj) else closes
            pairs = [(ts, float(v)) for ts, v in zip(timestamps, series) if v is not None]
            if len(pairs) < 2:
                raise RuntimeError("Not enough price history")
            ts_values = [p[0] for p in pairs]
            values = [p[1] for p in pairs]
            current = values[-1]

            def prior_by_trading_days(days: int) -> float | None:
                idx = len(values) - 1 - days
                return values[idx] if idx >= 0 else None

            high = _as_float(meta.get("fiftyTwoWeekHigh")) or max(values)
            low = _as_float(meta.get("fiftyTwoWeekLow")) or min(values)
            regular_price = _as_float(meta.get("regularMarketPrice"))
            if regular_price is not None:
                current = regular_price
            returns = {
                "1m_pct": _pct_return(current, prior_by_trading_days(21)),
                "3m_pct": _pct_return(current, prior_by_trading_days(63)),
                "6m_pct": _pct_return(current, prior_by_trading_days(126)),
                "12m_pct": _pct_return(current, values[0]),
            }
            drawdown = ((current / high) - 1.0) * 100.0 if high else None
            market_time = meta.get("regularMarketTime")
            return {
                "ticker": ticker,
                "company": meta.get("longName") or meta.get("shortName"),
                "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
                "currency": meta.get("currency"),
                "price": round(current, 6),
                "fifty_two_week_high": round(high, 6) if high is not None else None,
                "fifty_two_week_low": round(low, 6) if low is not None else None,
                "drawdown_52w_pct": round(drawdown, 4) if drawdown is not None else None,
                "returns": {k: (round(v, 4) if v is not None else None) for k, v in returns.items()},
                "market_time_utc": datetime.fromtimestamp(market_time, tz=timezone.utc).isoformat() if market_time else None,
                "history_points": len(values),
                "history_start_utc": datetime.fromtimestamp(ts_values[0], tz=timezone.utc).isoformat(),
                "source_url": url,
                "source_type": "market_data_convenience",
                "fetched_at": _utc_now(),
            }
        except Exception as exc:  # network/data error should not kill a 500-name screen
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < retries:
                time.sleep(0.6 * (2**attempt))
    return {"ticker": ticker, "error": last_error or "unknown error", "source_url": url, "fetched_at": _utc_now()}


def price_screen(tickers: list[str], benchmark: str, workers: int, output_path: Path | None) -> dict[str, Any]:
    all_tickers = list(tickers)
    benchmark = benchmark.upper().strip()
    if benchmark and benchmark not in all_tickers:
        fetch_list = [benchmark, *all_tickers]
    else:
        fetch_list = all_tickers

    records: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        future_map = {pool.submit(fetch_price_record, ticker): ticker for ticker in fetch_list}
        for future in concurrent.futures.as_completed(future_map):
            ticker = future_map[future]
            try:
                records[ticker] = future.result()
            except Exception as exc:
                records[ticker] = {"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}

    benchmark_record = records.get(benchmark) if benchmark else None
    benchmark_returns = (benchmark_record or {}).get("returns") if isinstance(benchmark_record, dict) else None

    rows: list[dict[str, Any]] = []
    for ticker in all_tickers:
        row = dict(records.get(ticker) or {"ticker": ticker, "error": "missing result"})
        if "error" not in row and isinstance(row.get("returns"), dict) and isinstance(benchmark_returns, dict):
            rel: dict[str, float | None] = {}
            for period, stock_ret in row["returns"].items():
                bench_ret = benchmark_returns.get(period)
                if stock_ret is None or bench_ret is None:
                    rel[period] = None
                else:
                    rel[period] = round(float(stock_ret) - float(bench_ret), 4)
            row["relative_return_vs_benchmark"] = rel
        rows.append(row)

    ok_count = sum(1 for row in rows if "error" not in row)
    result = {
        "as_of": _utc_now(),
        "method": "Synapse Stock Hunter price breadth screen 1.0.0",
        "benchmark": benchmark,
        "requested": len(all_tickers),
        "successful": ok_count,
        "failed": len(all_tickers) - ok_count,
        "warning": "Price-history convenience data is a breadth-screen input only; validate material values and fundamentals before investment conclusions.",
        "benchmark_record": benchmark_record,
        "stocks": rows,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return result


FUNDAMENTAL_TYPES = [
    "quarterlyTotalRevenue",
    "quarterlyDilutedEPS",
    "quarterlyOperatingIncome",
    "quarterlyFreeCashFlow",
    "quarterlyTotalDebt",
    "quarterlyCashCashEquivalentsAndShortTermInvestments",
    "trailingFreeCashFlow",
    "trailingMarketCap",
    "trailingPeRatio",
    "trailingForwardPeRatio",
    "trailingEnterprisesValueEBITDARatio",
    "trailingPsRatio",
    "trailingPegRatio",
]


def _reported_raw(item: dict[str, Any]) -> float | None:
    rv = item.get("reportedValue") if isinstance(item, dict) else None
    return _as_float(rv.get("raw")) if isinstance(rv, dict) else None


def _fetch_fundamental_series(ticker: str, retries: int = 3) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    now = int(time.time())
    start = now - 3 * 365 * 24 * 60 * 60
    types = ",".join(FUNDAMENTAL_TYPES)
    url = (
        "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
        f"{quote(ticker, safe='')}?symbol={quote(ticker, safe='')}&type={types}&period1={start}&period2={now}"
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = (payload.get("timeseries") or {}).get("result") or []
            series: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                meta_types = (row.get("meta") or {}).get("type") or []
                if not meta_types:
                    continue
                key = str(meta_types[0])
                values = row.get(key)
                if isinstance(values, list):
                    clean = [x for x in values if isinstance(x, dict) and _reported_raw(x) is not None]
                    clean.sort(key=lambda x: str(x.get("asOfDate") or ""))
                    series[key] = clean
            return url, series
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.7 * (2**attempt))
    raise RuntimeError(f"fundamentals fetch failed: {last_error}")


def _latest_value(series: dict[str, list[dict[str, Any]]], key: str) -> tuple[float | None, str | None]:
    rows = series.get(key) or []
    if not rows:
        return None, None
    item = rows[-1]
    return _reported_raw(item), item.get("asOfDate")


def _quarter_yoy(series: dict[str, list[dict[str, Any]]], key: str) -> tuple[float | None, float | None, float | None]:
    rows = series.get(key) or []
    values = [_reported_raw(x) for x in rows]
    values = [v for v in values if v is not None]
    if len(values) < 5:
        return None, None, None
    current, prior = values[-1], values[-5]
    yoy = None if prior == 0 else (current / abs(prior) - (1.0 if prior > 0 else -1.0)) * 100.0
    prior_yoy = None
    if len(values) >= 6:
        pcur, pprior = values[-2], values[-6]
        if pprior != 0:
            prior_yoy = (pcur / abs(pprior) - (1.0 if pprior > 0 else -1.0)) * 100.0
    accel = yoy - prior_yoy if yoy is not None and prior_yoy is not None else None
    return yoy, prior_yoy, accel


def _linear(value: float | None, lo: float, hi: float, points: float) -> float:
    if value is None:
        return 0.0
    if hi <= lo:
        return 0.0
    return _clamp((value - lo) / (hi - lo), 0.0, 1.0) * points


def _pass_b_quant_score(metrics: dict[str, Any]) -> tuple[float, dict[str, float]]:
    rev = _as_float(metrics.get("revenue_growth_yoy_pct"))
    eps = _as_float(metrics.get("eps_growth_yoy_pct"))
    op = _as_float(metrics.get("operating_income_growth_yoy_pct"))
    fcf_growth = _as_float(metrics.get("fcf_growth_yoy_pct"))
    fcf_yield = _as_float(metrics.get("fcf_yield_pct"))
    market_cap = _as_float(metrics.get("market_cap"))
    net_debt = _as_float(metrics.get("net_debt"))
    forward_pe = _as_float(metrics.get("forward_pe"))

    growth_points = _linear(rev, -5.0, 30.0, 25.0)
    earnings_growth = eps if eps is not None and eps > -1000 else op
    earnings_points = _linear(earnings_growth, -10.0, 40.0, 20.0)
    fcf_yield_points = _linear(fcf_yield, 0.0, 8.0, 15.0)
    fcf_growth_points = _linear(fcf_growth, -20.0, 40.0, 10.0)

    balance_points = 5.0
    if market_cap and net_debt is not None:
        ratio = net_debt / market_cap
        if ratio <= 0:
            balance_points = 10.0
        elif ratio <= 0.10:
            balance_points = 8.0
        elif ratio <= 0.30:
            balance_points = 5.0
        elif ratio <= 0.50:
            balance_points = 2.0
        else:
            balance_points = 0.0

    valuation_points = 0.0
    if forward_pe is not None and forward_pe > 0:
        growth_ref = max(5.0, earnings_growth or rev or 5.0)
        peg_like = forward_pe / growth_ref
        if peg_like <= 0.75:
            valuation_points = 20.0
        elif peg_like <= 1.0:
            valuation_points = 18.0
        elif peg_like <= 1.5:
            valuation_points = 15.0
        elif peg_like <= 2.0:
            valuation_points = 11.0
        elif peg_like <= 3.0:
            valuation_points = 7.0
        else:
            valuation_points = 3.0
    else:
        trailing_pe = _as_float(metrics.get("trailing_pe"))
        if trailing_pe is not None and trailing_pe > 0:
            if trailing_pe <= 15:
                valuation_points = 16.0
            elif trailing_pe <= 25:
                valuation_points = 13.0
            elif trailing_pe <= 35:
                valuation_points = 9.0
            elif trailing_pe <= 50:
                valuation_points = 5.0
            else:
                valuation_points = 2.0

    parts = {
        "revenue_growth": round(growth_points, 2),
        "earnings_growth": round(earnings_points, 2),
        "fcf_yield": round(fcf_yield_points, 2),
        "fcf_growth": round(fcf_growth_points, 2),
        "balance_sheet": round(balance_points, 2),
        "valuation": round(valuation_points, 2),
    }
    return round(sum(parts.values()), 2), parts


def fetch_fundamental_record(ticker: str) -> dict[str, Any]:
    try:
        url, series = _fetch_fundamental_series(ticker)
        rev, rev_date = _latest_value(series, "quarterlyTotalRevenue")
        eps, eps_date = _latest_value(series, "quarterlyDilutedEPS")
        op, op_date = _latest_value(series, "quarterlyOperatingIncome")
        fcf_q, fcf_date = _latest_value(series, "quarterlyFreeCashFlow")
        debt, debt_date = _latest_value(series, "quarterlyTotalDebt")
        cash, cash_date = _latest_value(series, "quarterlyCashCashEquivalentsAndShortTermInvestments")
        fcf_ttm, fcf_ttm_date = _latest_value(series, "trailingFreeCashFlow")
        market_cap, market_cap_date = _latest_value(series, "trailingMarketCap")
        trailing_pe, _ = _latest_value(series, "trailingPeRatio")
        forward_pe, _ = _latest_value(series, "trailingForwardPeRatio")
        ev_ebitda, _ = _latest_value(series, "trailingEnterprisesValueEBITDARatio")
        ps, _ = _latest_value(series, "trailingPsRatio")
        peg, _ = _latest_value(series, "trailingPegRatio")
        rev_yoy, rev_prev_yoy, rev_accel = _quarter_yoy(series, "quarterlyTotalRevenue")
        eps_yoy, _, _ = _quarter_yoy(series, "quarterlyDilutedEPS")
        op_yoy, _, _ = _quarter_yoy(series, "quarterlyOperatingIncome")
        fcf_yoy, _, _ = _quarter_yoy(series, "quarterlyFreeCashFlow")
        net_debt = debt - cash if debt is not None and cash is not None else None
        fcf_yield = (fcf_ttm / market_cap * 100.0) if fcf_ttm is not None and market_cap else None
        metrics = {
            "revenue_latest_q": rev,
            "revenue_latest_q_date": rev_date,
            "revenue_growth_yoy_pct": round(rev_yoy, 4) if rev_yoy is not None else None,
            "revenue_previous_q_yoy_pct": round(rev_prev_yoy, 4) if rev_prev_yoy is not None else None,
            "revenue_acceleration_pp": round(rev_accel, 4) if rev_accel is not None else None,
            "diluted_eps_latest_q": eps,
            "diluted_eps_latest_q_date": eps_date,
            "eps_growth_yoy_pct": round(eps_yoy, 4) if eps_yoy is not None else None,
            "operating_income_latest_q": op,
            "operating_income_latest_q_date": op_date,
            "operating_income_growth_yoy_pct": round(op_yoy, 4) if op_yoy is not None else None,
            "fcf_latest_q": fcf_q,
            "fcf_latest_q_date": fcf_date,
            "fcf_growth_yoy_pct": round(fcf_yoy, 4) if fcf_yoy is not None else None,
            "fcf_ttm": fcf_ttm,
            "fcf_ttm_date": fcf_ttm_date,
            "fcf_yield_pct": round(fcf_yield, 4) if fcf_yield is not None else None,
            "total_debt": debt,
            "total_debt_date": debt_date,
            "cash_and_short_term_investments": cash,
            "cash_date": cash_date,
            "net_debt": net_debt,
            "market_cap": market_cap,
            "market_cap_date": market_cap_date,
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "ev_ebitda": ev_ebitda,
            "price_to_sales": ps,
            "peg_ratio": peg,
        }
        quant_score, quant_parts = _pass_b_quant_score(metrics)
        return {
            "ticker": ticker,
            "metrics": metrics,
            "pass_b_quant_score": quant_score,
            "pass_b_quant_components": quant_parts,
            "source_url": url,
            "source_type": "market_data_secondary",
            "fetched_at": _utc_now(),
            "warning": "Secondary market-data fundamentals: use for scalable screening, then validate top candidates against SEC/company IR before BUY classification.",
        }
    except Exception as exc:
        return {"ticker": ticker, "error": f"{type(exc).__name__}: {exc}", "fetched_at": _utc_now()}


def fundamental_screen(tickers: list[str], workers: int, output_path: Path | None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
        future_map = {pool.submit(fetch_fundamental_record, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(future_map):
            rows.append(future.result())
    rows.sort(key=lambda r: r.get("pass_b_quant_score", -1), reverse=True)
    result = {
        "as_of": _utc_now(),
        "method": "Synapse Stock Hunter Pass B quantitative screen 1.1.0",
        "requested": len(tickers),
        "successful": sum(1 for r in rows if "error" not in r),
        "failed": sum(1 for r in rows if "error" in r),
        "warning": "Pass B scores prioritize which companies deserve primary-source validation; they are not BUY/WATCH/AVOID labels.",
        "stocks": rows,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return result

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synapse Stock Hunter deterministic helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prices = sub.add_parser("prices", help="Run cheap broad price/momentum screen")
    p_prices.add_argument("--tickers", required=True, help="Comma-separated tickers or a text file")
    p_prices.add_argument("--benchmark", default="SPY", help="Benchmark ticker, default SPY")
    p_prices.add_argument("--workers", type=int, default=6, help="Parallel requests, max 12")
    p_prices.add_argument("--out", type=Path, help="Write JSON output to this path")

    p_fund = sub.add_parser("fundamentals", help="Run scalable Pass B fundamentals/valuation screen")
    p_fund.add_argument("--tickers", required=True, help="Comma-separated tickers or a text file")
    p_fund.add_argument("--workers", type=int, default=6, help="Parallel requests, max 10")
    p_fund.add_argument("--out", type=Path, help="Write JSON output to this path")

    p_score = sub.add_parser("score", help="Score normalized evidence-backed candidate JSON")
    p_score.add_argument("input", type=Path, help="Candidate JSON input")
    p_score.add_argument("--out", type=Path, help="Write ranked JSON output to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prices":
        tickers = _load_tickers(args.tickers)
        if not tickers:
            raise SystemExit("No tickers supplied")
        price_screen(tickers, args.benchmark, args.workers, args.out)
        return 0
    if args.command == "fundamentals":
        tickers = _load_tickers(args.tickers)
        if not tickers:
            raise SystemExit("No tickers supplied")
        fundamental_screen(tickers, args.workers, args.out)
        return 0
    if args.command == "score":
        score_file(args.input, args.out)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
