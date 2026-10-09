"""Cross-viewport UI Lab smoke runner. Emulation is never native iOS Safari."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlparse

PROFILES = {
    "iphone-compact": (375, 812, True),
    "iphone-large": (430, 932, True),
    "tablet-portrait": (768, 1024, True),
    "desktop": (1440, 900, False),
}


def run_matrix(url: str, output: str, engine: str = "chromium") -> dict:
    """Visit each profile, save screenshot and evidence JSON, report real failures."""
    if engine not in {"chromium", "firefox", "webkit"}:
        raise ValueError("unsupported engine")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be http(s)")
    from playwright.sync_api import sync_playwright
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(headless=True)
        try:
            for name, (width, height, touch) in PROFILES.items():
                record = {"profile": name, "viewport": {"width": width, "height": height}, "engine": engine,
                          "platform": "desktop browser emulation", "native_safari_verified": False,
                          "url": url, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "blocked"}
                page = None
                try:
                    page = browser.new_page(viewport={"width": width, "height": height}, has_touch=touch,
                                            is_mobile=touch if engine != "firefox" else False)
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.screenshot(path=str(folder / f"{engine}-{name}.png"), full_page=True)
                    measurements = page.evaluate("""() => ({scrollWidth:document.documentElement.scrollWidth,
                      clientWidth:document.documentElement.clientWidth,
                      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
                      title:document.title})""")
                    record.update(measurements)
                    record["http_status"] = response.status if response else None
                    record["page_errors"] = errors
                    record["screenshot"] = f"{engine}-{name}.png"
                    record["status"] = "passed" if response and response.ok and not errors and not measurements["horizontalOverflow"] else "failed"
                except Exception as exc:
                    record["error"] = str(exc)
                finally:
                    if page is not None:
                        page.close()
                results.append(record)
        finally:
            browser.close()
    report = {"schema_version": 1, "engine": engine, "native_safari_verified": False,
              "results": results, "passed": sum(r["status"] == "passed" for r in results),
              "failed": sum(r["status"] == "failed" for r in results),
              "blocked": sum(r["status"] == "blocked" for r in results)}
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--output", default="artifacts/ui-lab")
    parser.add_argument("--engine", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    report = run_matrix(args.url, args.output, args.engine)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] == len(PROFILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
