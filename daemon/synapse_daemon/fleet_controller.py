"""Durable, bounded ChatGPT UI fleet lifecycle (ADR-0038).

One controller per daemon data directory. No work is dispatched at import time.
Browser calls and git commands are injectable for deterministic unit tests.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

UTC = timezone.utc
NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_WORKERS = 12
MAX_DEPTH = 2
STALE_AFTER = timedelta(minutes=120)


def now_utc() -> datetime:
    return datetime.now(UTC)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _safe_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ("chatgpt.com", "chat.openai.com"):
        raise ValueError("project_url must be an https://chatgpt.com project URL")
    if not parsed.path.startswith("/g/") and not parsed.path.startswith("/project/"):
        raise ValueError("project_url must refer to a ChatGPT project")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("project_url must not contain credentials, query or fragment")
    return value.rstrip("/")


def _safe_lanes(*, workers: int | None, lanes: list[dict] | None) -> list[dict]:
    if (workers is None) == (lanes is None):
        raise ValueError("Supply either workers or lanes, not both")
    if workers is not None:
        if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= MAX_WORKERS:
            raise ValueError("workers must be an integer between 1 and 12")
        lanes = [{"name": "worker-" + str(i + 1), "task": "Complete the assigned lane task", "files": []}
                 for i in range(workers)]
    if not isinstance(lanes, list) or not lanes or len(lanes) > MAX_WORKERS:
        raise ValueError("lanes must contain 1 to 12 entries")
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    valid = []
    for item in lanes:
        if not isinstance(item, dict):
            raise ValueError("each lane must be an object")
        name = item.get("name", "")
        task = item.get("task", "")
        files = item.get("files", [])
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen_names:
            raise ValueError("lane names must be unique lowercase slugs")
        if not isinstance(task, str) or not task.strip() or len(task) > 20000:
            raise ValueError("lane task must contain instructions")
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            raise ValueError("files must be a list of relative paths")
        for path in files:
            clean = path.replace("\\", "/")
            if not clean or clean.startswith("/") or ":" in clean or any(p in ("", ".", "..") for p in clean.split("/")):
                raise ValueError("file ownership must be relative paths without traversal")
            if clean.lower() in seen_paths:
                raise ValueError("file ownership overlaps between lanes: " + clean)
            seen_paths.add(clean.lower())
        power = item.get("power", "High")
        if power not in ("Instant", "Medium", "High"):
            raise ValueError("power must be Instant, Medium or High")
        seen_names.add(name)
        valid.append({"name": name, "task": task, "files": files, "power": power})
    return valid


def dispatch_code(project_url: str, prompt: str, plugins: list[str], power: str) -> str:
    """Browser-scoped code, never controlling tabs that the fleet did not create."""
    data = json.dumps({"project": project_url, "prompt": prompt, "plugins": plugins,
                       "power": power}, ensure_ascii=True)
    return """
async (page) => {
 const cfg = """ + data + """;
 const p = await page.context().newPage();
 try {
   await p.goto(cfg.project, {waitUntil:'domcontentloaded'});
   await p.locator('div.ProseMirror[contenteditable=true]').waitFor({timeout:45000});
   const model = p.getByRole('button', {name:'Select ChatGPT model'}).first();
   if (!(await model.count())) throw Error('Select ChatGPT model control missing');
   await model.click();
   const label = (await p.locator('body').innerText());
   if (!label.includes('GPT-6')) throw Error('GPT-6 model not confirmed');
   const slider = p.getByRole('slider').first();
   if (!(await slider.count())) throw Error('Model effort slider unavailable');
   await slider.focus();
   await slider.press(cfg.power === 'High' ? 'End' : (cfg.power === 'Instant' ? 'Home' : 'ArrowRight'));
   await p.keyboard.press('Escape');
   for (const plugin of cfg.plugins) {
     await p.getByRole('button',{name:'Add files and more'}).first().click();
     const option = p.getByText(plugin,{exact:true}).first();
     if (!(await option.count())) throw Error('Connector unavailable: ' + plugin);
     await option.click();
     const form = p.locator('div.ProseMirror[contenteditable=true]').first().locator('xpath=ancestor::form');
     if (!(await form.innerText()).includes(plugin))
       throw Error('Connector chip not verified: ' + plugin);
   }
   const box=p.locator('div.ProseMirror[contenteditable=true]').first();
   await box.fill(cfg.prompt);
   await box.press('Control+Home');
   await p.keyboard.type('@Synapse2');
   const mention=p.getByText('Synapse2',{exact:true}).last();
   if (!(await mention.count())) throw Error('Synapse2 app mention suggestion missing');
   await p.keyboard.press('Enter');
   const present=await p.locator('[app-mention-name="synapse2"]').count();
   if (!present) throw Error('Synapse2 app mention node missing; refusing send');
   const send=p.locator('[data-testid="send-button"]');
   if (!(await send.count())) throw Error('Send button missing');
   await send.click();
   for (let i=0;i<80 && !/\\/c\\//.test(p.url());i++) await p.waitForTimeout(500);
   if (!/\\/c\\//.test(p.url())) throw Error('Chat conversation URL was not observed');
   const ownedTabs=p.context().pages().map(tab=>tab.url());
   if (!ownedTabs.includes(p.url())) throw Error('Sent chat URL missing from browser tab list');
   const result={url:p.url(), ownedTabConfirmed:true, title:await p.title(), synapse2Mention:true,
                 connectors:cfg.plugins, model:'GPT-6', power:cfg.power};
   await p.waitForTimeout(20000);
   await p.close();
   return result;
 } catch(e) {
   await p.close().catch(()=>{});
   return {error:String(e), promptSent:false};
 }
}
"""


def archive_code(chat_url: str) -> str:
    """Archive a *known owned* conversation; never delete."""
    return """
async (page) => {
 const url = """ + json.dumps(chat_url) + """;
 const p=await page.context().newPage();
 try {
   await p.goto(url, {waitUntil:'domcontentloaded'});
   const menu=p.getByRole('button',{name:/More|Options|Chat options/i}).first();
   if (!(await menu.count())) throw Error('Chat options unavailable');
   await menu.click();
   const archive=p.getByText('Archive',{exact:true}).first();
   if (!(await archive.count())) throw Error('Archive action unavailable');
   await archive.click();
   await p.close();
   return {archived:true,url};
 } catch(e) { await p.close().catch(()=>{});return {archived:false,error:String(e)}; }
}
"""


def _browser_reply(payload: Any) -> dict:
    """Normalize Playwright MCP code responses; reject uncertain receipts."""
    if isinstance(payload, dict):
        if "error" in payload:
            raise RuntimeError(str(payload["error"]))
        if any(k in payload for k in ("url", "archived")):
            return payload
        parts = payload.get("content") or []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text = part["text"].split("### Ran Playwright code", 1)[0].strip()
                decoder = json.JSONDecoder()
                for index, character in enumerate(text):
                    if character == "{":
                        try:
                            decoded, _ = decoder.raw_decode(text[index:])
                            if isinstance(decoded, dict):
                                return _browser_reply(decoded)
                        except (ValueError, RuntimeError):
                            continue
    raise RuntimeError("No verifiable browser action receipt")


def registered_browser(storage: Any) -> Callable[[str], dict]:
    """Resolve the registered Playwright MCP; never launch a different browser implicitly."""
    from . import mcp_connector, mcp_servers
    def run(code: str) -> dict:
        with storage.transaction() as conn:
            matches = [s for s in mcp_servers.list_servers(conn) if s.id == "playwright"]
        if not matches:
            raise RuntimeError("Registered Playwright MCP is unavailable")
        server = matches[0]
        if server.transport == "stdio":
            call = mcp_connector._persistent_stdio_mcp
        elif server.transport == "http":
            call = mcp_connector.http_mcp
        else:
            raise RuntimeError("Playwright MCP transport must be stdio or http")
        reply = call(server, "tools/call",
                     {"name": "browser_run_code_unsafe", "arguments": {"code": code}}, 90)
        return _browser_reply(reply)
    return run


class FleetController:
    def __init__(self, data_dir: Path, *, browser: Callable[[str], dict] | None = None,
                 runner: Callable[[list[str], Path | None], str] | None = None,
                 clock: Callable[[], datetime] = now_utc) -> None:
        self.root = Path(data_dir) / "chatgpt-fleets"
        self.root.mkdir(parents=True, exist_ok=True)
        self.browser = browser
        self.runner = runner or self._git
        self.clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _git(args: list[str], cwd: Path | None) -> str:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              timeout=35, check=False)
        if done.returncode:
            raise RuntimeError("git failed: " + done.stderr[:500])
        return done.stdout.strip()

    def _file(self, fleet_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", fleet_id):
            raise ValueError("invalid fleet id")
        return self.root / (fleet_id + ".json")

    def _load(self, fleet_id: str) -> dict:
        return json.loads(self._file(fleet_id).read_text(encoding="utf-8"))

    def _save(self, fleet: dict) -> None:
        path = self._file(fleet["id"])
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fleet-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(fleet, f, ensure_ascii=True, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _all(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in self.root.glob("*.json")]

    def _head(self, lane: dict) -> str:
        return self.runner(["rev-parse", "HEAD"], Path(lane["worktree"])).strip().lower()

    def _status(self, lane: dict) -> tuple[str, str, str]:
        path = Path(lane["status_path"])
        dispatched = _utc(lane["dispatched_at"]) if lane.get("dispatched_at") else None
        if not path.exists():
            if dispatched and self.clock() - dispatched > STALE_AFTER:
                return "stale", "", "worker never created status file"
            return ("busy" if lane.get("chat_url") else "pending", "", "status file missing")
        if (dispatched and lane.get("prior_status_mtime_ns", -1) >= 0
                and path.stat().st_mtime_ns <= lane["prior_status_mtime_ns"]):
            if self.clock() - dispatched > STALE_AFTER:
                return "stale", "", "no new status after redispatch"
            return "busy", "", "awaiting new worker status"
        words = path.read_text(encoding="utf-8-sig").strip().split(" ", 2)
        if len(words) >= 2 and words[0] == "working":
            try:
                at = _utc(words[1])
            except ValueError:
                return "blocked", "", "invalid working timestamp"
            return ("stale" if self.clock() - at > STALE_AFTER else "busy", "", "working " + words[1])
        if len(words) >= 3 and words[0] == "idle" and SHA.fullmatch(words[1]):
            sha = words[1]
            actual = self._head(lane)
            if actual != sha:
                return "blocked", actual, "idle SHA does not match lane HEAD"
            return ("done" if words[2].strip() == "DONE" else "idle", sha, words[2].strip())
        return "blocked", "", "invalid status format"

    def _prompt(self, fleet: dict, lane: dict, continuation: bool) -> str:
        lines = [
            "You are a Synapse fleet worker. Perform your own work through the attached Synapse tools.",
            "No delegation to other AIs or workers. Report only actions you actually ran.",
            "Work ONLY in " + lane["worktree"] + " on branch " + lane["branch"],
            "Do not modify the live daemon/repo, credentials, protected branches or other worktrees.",
            "Do not operate browser tabs you did not open. Never delete chats.",
            "Before doing work, write working <current UTC time> to " + lane["status_path"],
            "After committing your own branch, write idle <full SHA> <next|DONE> to that same path.",
            "You own these files: " + json.dumps(lane["files"]),
            "Task: " + lane["task"],
        ]
        if continuation:
            lines.append("CONTINUATION: resume from branch head and existing status; do not re-audit.")
        lines.extend([
            "End your response with:",
            "HANDOFF",
            "lane: " + lane["name"],
            "branch: " + lane["branch"],
            "commit: <full sha>",
            "files: <changed files>",
            "test_result: <real result>",
            "next: <next or DONE>",
        ])
        return "\n".join(lines)

    def _dispatch(self, fleet: dict, lane: dict, *, continuation: bool) -> None:
        if self.browser is None:
            raise RuntimeError("Registered Playwright backend is unavailable")
        status_file = Path(lane["status_path"])
        old_status_mtime = status_file.stat().st_mtime_ns if status_file.exists() else -1
        receipt = self.browser(dispatch_code(fleet["project_url"], self._prompt(fleet, lane, continuation),
                                            fleet["plugins"], lane["power"]))
        if (receipt.get("error") or not receipt.get("synapse2Mention")
                or not receipt.get("ownedTabConfirmed")):
            raise RuntimeError("Browser dispatch unverified: " + str(receipt.get("error") or receipt))
        url = receipt.get("url", "")
        if not isinstance(url, str) or not re.fullmatch(r"https://chatgpt\.com/c/[a-zA-Z0-9-]+", url):
            raise RuntimeError("Browser did not return a verified ChatGPT conversation URL")
        lane["chat_url"] = url
        lane["prior_status_mtime_ns"] = old_status_mtime
        lane["dispatched_at"] = self.clock().isoformat()
        lane["round"] = lane.get("round", 0) + 1

    def start(self, *, project_url: str, repo: str, base_ref: str, workers: int | None = None,
              lanes: list[dict] | None = None, interval_minutes: int = 15,
              plugins: list[str] | None = None, parent: str | None = None,
              backend: str = "chatgpt-ui") -> dict:
        project_url = _safe_url(project_url)
        choices = _safe_lanes(workers=workers, lanes=lanes)
        if not isinstance(interval_minutes, int) or not 1 <= interval_minutes <= 1440:
            raise ValueError("interval_minutes must be from 1 to 1440")
        if backend != "chatgpt-ui":
            raise ValueError("Coder runtime fallback is not yet enabled; use backend=chatgpt-ui")
        plugins = plugins or ["Connect To Synapse"]
        if not isinstance(plugins, list) or not plugins or not all(isinstance(x, str) and 0 < len(x) <= 100 for x in plugins):
            raise ValueError("plugins must be nonempty connector names")
        if "Connect To Synapse" not in plugins:
            plugins = ["Connect To Synapse", *plugins]
        repo_path = Path(repo).expanduser().resolve(strict=True)
        if not (repo_path / ".git").exists():
            # A linked git worktree is also valid, but the accepted target must be a git checkout.
            self.runner(["rev-parse", "--show-toplevel"], repo_path)
        self.runner(["rev-parse", "--verify", base_ref + "^{commit}"], repo_path)
        fleet_id = uuid.uuid4().hex[:12]
        with self._lock:
            existing = self._all()
            live = [f for f in existing if f.get("enabled")]
            if sum(len(f["lanes"]) for f in live) + len(choices) > MAX_WORKERS:
                raise ValueError("Fleet capacity exceeded (max 12 live workers)")
            depth = 1
            if parent is not None:
                match = next((f for f in live if f["id"] == parent), None)
                if match is None:
                    raise ValueError("Parent fleet is not active")
                depth = match["depth"] + 1
                if depth > MAX_DEPTH:
                    raise ValueError("Sub-fleet nesting depth exceeded")
            root = self.root / fleet_id
            root.mkdir()
            fleet = {"id": fleet_id, "project_url": project_url, "repo": str(repo_path),
                     "base_ref": base_ref, "interval_minutes": interval_minutes,
                     "plugins": list(dict.fromkeys(plugins)), "parent": parent,
                     "depth": depth, "enabled": True, "created_at": self.clock().isoformat(),
                     "last_nudge_at": None, "lanes": []}
            for choice in choices:
                name = choice["name"]
                branch = "fleet/" + fleet_id + "/" + name
                dest = root / name
                # Serialized worktree mutations prevent index.lock races.
                self.runner(["worktree", "add", "-b", branch, str(dest), base_ref], repo_path)
                lane = dict(choice, branch=branch, worktree=str(dest),
                            status_path=str(root / (name + ".status")), chat_url=None, round=0)
                fleet["lanes"].append(lane)
                self._save(fleet)
            # Preserve worktrees and a retryable error on dispatch failure; never silently lose state.
            for lane in fleet["lanes"]:
                try:
                    self._dispatch(fleet, lane, continuation=False)
                except Exception as exc:
                    lane["error"] = str(exc)
                self._save(fleet)
            return self.report(fleet_id)

    def report(self, fleet_id: str) -> dict:
        with self._lock:
            f = self._load(fleet_id)
            lanes = []
            for lane in f["lanes"]:
                try:
                    status, sha, note = self._status(lane)
                    head = self._head(lane)
                except Exception as exc:
                    status, sha, note, head = "blocked", "", str(exc), ""
                lanes.append({"name": lane["name"], "state": status, "branch": lane["branch"],
                              "head": head, "status": note, "chat_url": lane.get("chat_url"),
                              "round": lane["round"], "error": lane.get("error"),
                              "line": f"{lane['name']} {status} {head[:12]} {note}"[:220]})
            return {"id": f["id"], "enabled": f["enabled"], "parent": f["parent"],
                    "interval_minutes": f["interval_minutes"], "lanes": lanes}

    def status(self, fleet_id: str | None = None) -> list[dict]:
        with self._lock:
            return [self.report(fleet_id)] if fleet_id else [self.report(f["id"]) for f in self._all()]

    def nudge(self, fleet_id: str | None = None) -> list[dict]:
        with self._lock:
            results = []
            fleets = [self._load(fleet_id)] if fleet_id else self._all()
            for f in fleets:
                if not f["enabled"]:
                    continue
                for lane in f["lanes"]:
                    try:
                        state, sha, note = self._status(lane)
                        if state == "done":
                            if lane.get("chat_url") and not lane.get("archived"):
                                if self.browser is None:
                                    raise RuntimeError("No browser to archive completed chat")
                                receipt = self.browser(archive_code(lane["chat_url"]))
                                if receipt.get("archived"):
                                    lane["archived"] = True
                            continue
                        if state in ("idle", "stale", "pending"):
                            if state == "idle" and lane.get("chat_url") and not lane.get("archived"):
                                if self.browser is None or not self.browser(archive_code(lane["chat_url"])).get("archived"):
                                    raise RuntimeError("Could not archive previous round; retry later")
                                lane["archived"] = True
                            lane.pop("error", None)
                            self._dispatch(f, lane, continuation=True)
                            lane["archived"] = False
                    except Exception as exc:
                        lane["error"] = str(exc)
                        results.append({"fleet": f["id"], "lane": lane["name"], "error": str(exc)})
                f["last_nudge_at"] = self.clock().isoformat()
                self._save(f)
            return results

    def tick(self) -> list[dict]:
        with self._lock:
            for fleet in self._all():
                if not fleet["enabled"]:
                    continue
                last = fleet.get("last_nudge_at") or fleet["created_at"]
                if self.clock() - _utc(last) >= timedelta(minutes=fleet["interval_minutes"]):
                    self.nudge(fleet["id"])
        return self.status()

    def stop(self, fleet_id: str) -> dict:
        with self._lock:
            f = self._load(fleet_id)
            f["enabled"] = False
            self._save(f)
            for child in self._all():
                if child.get("parent") == fleet_id and child["enabled"]:
                    self.stop(child["id"])
            return self.report(fleet_id)


_controllers: dict[str, FleetController] = {}
_controllers_lock = threading.RLock()


def get_controller(storage: Any) -> FleetController:
    key = str(Path(storage.data_dir).resolve())
    with _controllers_lock:
        if key not in _controllers:
            _controllers[key] = FleetController(storage.data_dir, browser=registered_browser(storage))
        return _controllers[key]
