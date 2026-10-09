"""Synapse UI Lab: repeatable, evidence-backed cross-device browser QA.

Chromium emulation and desktop WebKit DO NOT verify native iOS Safari.
Run only against targets you are authorized to test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PROFILES = {
    "iphone-compact": (375, 812, True),
    "iphone-large": (430, 932, True),
    "tablet-portrait": (768, 1024, True),
    "desktop": (1440, 900, False),
}
ENGINES = {"chromium", "firefox", "webkit"}
MAX_FLOW_STEPS = 35
ALLOWED_ACTIONS = {"click", "fill", "press", "check", "select", "scroll", "assert_visible",
                   "assert_text", "assert_url", "wait_visible", "screenshot"}


def load_flow(path: str | None) -> list[dict]:
    if not path:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) > MAX_FLOW_STEPS:
        raise ValueError("Flow must be a JSON array of no more than 35 steps")
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or item.get("action") not in ALLOWED_ACTIONS:
            raise ValueError(f"Unknown or malformed flow step #{index + 1}")
        if item["action"] not in {"scroll", "screenshot", "assert_url"} and not isinstance(item.get("selector"), str):
            raise ValueError(f"Flow step #{index + 1} requires a selector")
    return raw


def execute_flow(page, steps: list[dict], timeout_ms: int) -> list[dict]:
    """Deterministic allowed UI interactions, no arbitrary JavaScript from flow files."""
    outcomes = []
    for index, step in enumerate(steps):
        action = step["action"]
        result = {"step": index + 1, "action": action, "selector": step.get("selector"),
                  "status": "blocked"}
        try:
            selector = step.get("selector", "")
            loc = page.locator(selector).first if selector else None
            if action == "click":
                loc.click(timeout=timeout_ms)
            elif action == "fill":
                loc.fill(str(step.get("value", "")), timeout=timeout_ms)
            elif action == "press":
                loc.press(str(step.get("key", "Enter")), timeout=timeout_ms)
            elif action == "check":
                loc.check(timeout=timeout_ms)
            elif action == "select":
                loc.select_option(str(step.get("value", "")), timeout=timeout_ms)
            elif action == "scroll":
                page.mouse.wheel(0, int(step.get("pixels", 500)))
            elif action in {"assert_visible", "wait_visible"}:
                loc.wait_for(state="visible", timeout=timeout_ms)
            elif action == "assert_text":
                actual = loc.inner_text(timeout=timeout_ms)
                if str(step.get("text", "")) not in actual:
                    raise AssertionError("Expected text not found in selected element")
            elif action == "assert_url":
                if not re.search(str(step.get("pattern", "^$")), page.url):
                    raise AssertionError("Current URL does not match expected pattern")
            elif action == "screenshot":
                page.screenshot(path=str(step["_output_path"]), timeout=timeout_ms)
            result["status"] = "passed"
        except Exception as exc:
            result["error"] = str(exc)[:350]
            result["status"] = "failed"
        outcomes.append(result)
        if result["status"] != "passed":
            break
    return outcomes


def accessibility_snapshot(page) -> dict:
    """Small deterministic accessibility smoke checks; not a WCAG certification."""
    return page.evaluate("""() => {
      const controls=[...document.querySelectorAll('button,a,input,select,textarea')];
      const visible=e=>!!(e.getClientRects().length);
      const unnamed=controls.filter(e=>visible(e) && !(
        e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') ||
        e.innerText?.trim() || e.getAttribute('title') || e.getAttribute('alt') ||
        (e.id && document.querySelector('label[for="'+CSS.escape(e.id)+'"]')) ||
        e.closest('label')
      ));
      return {visible_control_count:controls.filter(visible).length,
        unnamed_control_count:unnamed.length,
        unnamed_samples:unnamed.slice(0,8).map(e=>e.outerHTML.slice(0,150)),
        horizontal_overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
        title:document.title,
        scroll_width:document.documentElement.scrollWidth,
        client_width:document.documentElement.clientWidth};
    }""")


def compare_images(current: Path, baseline: Path, tolerance: float = 0.01) -> dict:
    """Pixel delta is evidence, not semantic AI inspection."""
    from PIL import Image, ImageChops, ImageStat
    if not baseline.is_file():
        return {"status": "blocked", "reason": "baseline not found"}
    if not current.is_file():
        return {"status": "blocked", "reason": "candidate not found"}
    with Image.open(current) as cand, Image.open(baseline) as base:
        a, b = cand.convert("RGB"), base.convert("RGB")
        if a.size != b.size:
            return {"status": "failed", "reason": "image dimensions differ",
                    "candidate_size": list(a.size), "baseline_size": list(b.size)}
        stat = ImageStat.Stat(ImageChops.difference(a, b))
        change = sum(stat.mean) / (3 * 255)
        return {"status": "passed" if change <= tolerance else "failed",
                "mean_pixel_difference": round(change, 6), "threshold": tolerance,
                "size": list(a.size)}


def write_report(output: Path, report: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    entries = []
    for item in report.get("results", []):
        title = html.escape(item["profile"])
        status = html.escape(item["status"])
        filename = html.escape(str(item.get("screenshot", "")))
        errors = html.escape("; ".join(item.get("page_errors", [])[:3]))
        image = f'<img src="{filename}" alt="{title} screenshot" loading="lazy">' if filename else ""
        entries.append(f'<article><header><h2>{title}</h2><strong class="{status}">{status}</strong></header>{image}<p>{errors}</p><details><summary>Evidence</summary><pre>{html.escape(json.dumps(item, indent=2))}</pre></details></article>')
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Synapse UI Lab — Evidence</title><style>"
            "body{margin:0;background:#0c1019;color:#e9effb;font:15px system-ui;padding:clamp(14px,3vw,42px)}"
            "header{display:flex;align-items:center;justify-content:space-between;gap:12px}"
            "h1{font-size:clamp(24px,3vw,36px)}h2{font-size:18px}small,p{color:#a1adc1}"
            "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:18px}"
            "article{background:#171e2d;border:1px solid #34405a;border-radius:18px;padding:18px;min-width:0}"
            "img{max-width:100%;height:auto;border-radius:10px;border:1px solid #3c4b68}"
            ".passed{color:#8be2b6}.failed{color:#ff8d91}.blocked{color:#ffce80}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}"
            "details{margin-top:12px}summary{cursor:pointer}</style>"
            "<h1>Synapse UI Lab</h1><p>Measured browser evidence. Emulation is not native iOS Safari.</p>"
            f"<p>{report.get('passed',0)} passed · {report.get('failed',0)} failed · {report.get('blocked',0)} blocked</p>"
            "<main>" + "".join(entries) + "</main></html>")
    (output / "index.html").write_text(page, encoding="utf-8")


def run_matrix(url: str, output: str, engine: str = "chromium", profiles=None,
               timeout_ms: int = 8000, flow_path: str | None = None,
               baseline_dir: str | None = None, diff_threshold: float = 0.01) -> dict:
    if engine not in ENGINES:
        raise ValueError("Unsupported browser engine")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use http(s) with a host")
    if timeout_ms < 100 or timeout_ms > 30000:
        raise ValueError("timeout_ms must be between 100 and 30000")
    steps = load_flow(flow_path)
    selected = PROFILES if profiles is None else {name: PROFILES[name] for name in profiles}
    out = Path(output)
    report = {"schema_version": 2, "target": url, "engine": engine,
              "native_safari_verified": False, "results": [],
              "passed": 0, "failed": 0, "blocked": 0}
    write_report(out, report)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(headless=True)
        try:
            for name, (width, height, touch) in selected.items():
                record = {
                    "profile": name, "viewport": {"width": width, "height": height},
                    "engine": engine, "platform": "desktop Playwright emulation",
                    "native_safari_verified": False,
                    "url": url, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "status": "blocked"}
                page = None
                try:
                    page = browser.new_page(viewport={"width": width, "height": height},
                                            has_touch=touch,
                                            is_mobile=touch if engine != "firefox" else False)
                    errors, network = [], []
                    page.on("pageerror", lambda exc: errors.append(str(exc)[:350]))
                    page.on("requestfailed", lambda req: network.append(req.url.split("?")[0][:200]))
                    response = page.goto(url, wait_until="commit", timeout=timeout_ms)
                    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    record["http_status"] = response.status if response else None
                    record["accessibility_smoke"] = accessibility_snapshot(page)
                    record["horizontalOverflow"] = record["accessibility_smoke"]["horizontal_overflow"]
                    record["title"] = record["accessibility_smoke"]["title"]
                    run_steps = []
                    for step_i, step in enumerate(steps):
                        step = dict(step)
                        if step["action"] == "screenshot":
                            step["_output_path"] = out / f"{engine}-{name}-step-{step_i+1}.png"
                        run_steps.append(step)
                    record["flow"] = execute_flow(page, run_steps, timeout_ms)
                    screenshot = f"{engine}-{name}.png"
                    page.screenshot(path=str(out / screenshot), full_page=False,
                                    timeout=timeout_ms, animations="disabled")
                    record["screenshot"] = screenshot
                    record["page_errors"] = errors
                    record["failed_requests"] = network[:20]
                    record["flow_status"] = ("passed" if len(record["flow"]) == len(steps) and
                                             all(x["status"] == "passed" for x in record["flow"])
                                             else "failed")
                    issues = []
                    if record["http_status"] is None or record["http_status"] >= 400:
                        issues.append("HTTP response failure")
                    if record["horizontalOverflow"]:
                        issues.append("Horizontal layout overflow")
                    if errors:
                        issues.append("Uncaught JavaScript error")
                    if network:
                        issues.append("Failed network requests")
                    if record["flow_status"] == "failed":
                        issues.append("Interaction flow failure")
                    if record["accessibility_smoke"]["unnamed_control_count"]:
                        issues.append("Unnamed visible interactive controls")
                    record["issues"] = issues
                    if baseline_dir is not None:
                        record["visual_diff"] = compare_images(
                            out / screenshot, Path(baseline_dir) / screenshot, diff_threshold)
                        if record["visual_diff"]["status"] != "passed":
                            issues.append("Visual baseline difference or missing baseline")
                    record["status"] = "failed" if issues else "passed"
                except Exception as exc:
                    record["error"] = str(exc)[:500]
                finally:
                    if page is not None:
                        page.close()
                report["results"].append(record)
                report["passed"] = sum(x["status"] == "passed" for x in report["results"])
                report["failed"] = sum(x["status"] == "failed" for x in report["results"])
                report["blocked"] = sum(x["status"] == "blocked" for x in report["results"])
                write_report(out, report)
        finally:
            browser.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--output", default="artifacts/ui-lab")
    parser.add_argument("--profile", action="append", choices=tuple(PROFILES))
    parser.add_argument("--engine", choices=sorted(ENGINES), default="chromium")
    parser.add_argument("--timeout-ms", type=int, default=8000)
    parser.add_argument("--flow", help="JSON array of approved browser interaction steps")
    parser.add_argument("--baseline", help="Directory with comparable screenshot baselines")
    parser.add_argument("--diff-threshold", type=float, default=0.01)
    args = parser.parse_args()
    report = run_matrix(args.url, args.output, args.engine, args.profile,
                        args.timeout_ms, args.flow, args.baseline, args.diff_threshold)
    print(json.dumps({"passed": report["passed"], "failed": report["failed"],
                      "blocked": report["blocked"], "output": args.output}))
    return 0 if report["passed"] == len(args.profile or PROFILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
