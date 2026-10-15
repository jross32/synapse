"""Public Synapse website availability and download manifest checks.

Read-only. Never registers accounts, touches MCP configuration, or downloads binaries.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://download.whatapc.com"
ROUTES = ("/", "/start/", "/download/", "/releases/", "/support/")
API_HEALTH = "https://accounts-api-production-f84a.up.railway.app/v1/health"


def request(url, method="GET", headers=None):
    command = ["curl.exe", "-sS", "-L", "--max-time", "12", "-w", "\n__HTTP_CODE__%{http_code}", "-X", method]
    for key, value in (headers or {}).items():
        command.extend(["-H", key + ": " + value])
    command.append(url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=16)
        if result.returncode == 0 and "__HTTP_CODE__" in result.stdout:
            body, code = result.stdout.rsplit("__HTTP_CODE__", 1)
            return int(code.strip()), body
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    req = urllib.request.Request(url, method=method, headers=headers or {"User-Agent": "Synapse-Site-Readiness/1"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status, response.read(100000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, ""


def main():
    report = {"routes": {}, "release_manifest": False, "account_service": False,
              "website_signup_ready": False}
    for route in ROUTES:
        code, body = request(BASE + route)
        report["routes"][route] = code == 200 and "<html" in body.lower()
    code, raw = request(BASE + "/releases.json")
    if code == 200:
        try:
            data = json.loads(raw.lstrip(chr(65279)))
            report["release_manifest"] = any(
                a.get("platform") == "windows" and a.get("url", "").startswith("https://github.com/jross32/synapse/releases/download/")
                for a in data.get("artifacts", []))
        except (ValueError, TypeError):
            pass
    report["account_service"] = request(API_HEALTH)[0] == 200
    preflight, _ = request(
        "https://accounts-api-production-f84a.up.railway.app/v1/auth/signup",
        method="OPTIONS",
        headers={"Origin": BASE, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"})
    report["website_signup_ready"] = preflight == 200 or preflight == 204
    report["ready_for_download_site"] = all(report["routes"].values()) and report["release_manifest"]
    print(json.dumps(report, indent=2))
    if not report["website_signup_ready"]:
        print("Web signup NOT READY: API preflight unavailable; desktop signup remains the supported path.", file=sys.stderr)
    return 0 if report["ready_for_download_site"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
