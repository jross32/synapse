"""Synapse Terminal Cloak.

Event-driven desktop guard for background-owned console windows.

Normal Synapse/Stock Hunter subprocesses use CREATE_NO_WINDOW. This component is
the last-resort safety net for third-party helpers that still ask Windows for a
console host. It hides only background-owned terminal windows; it never kills or
suspends the process behind them.

The guard uses WinEvent hooks instead of polling WMI or the process table. Process
inspection only happens when Windows reports that a terminal window appeared or
changed title, keeping steady-state CPU usage near zero.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

TERMINAL_NAMES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "openconsole.exe",
    "conhost.exe",
}

BACKGROUND_CLIENT_NAMES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "python.exe",
    "pythonw.exe",
    "node.exe",
}

BACKGROUND_MARKERS = (
    "synapse_daemon",
    "pc-watch.ps1",
    "daemon-watchdog.ps1",
    "tunnel-watchdog.ps1",
    "terminal_cloak.py",
    "launch_codex_app_tools_mcp.cmd",
    "@playwright/mcp",
    "playwright-mcp",
    "chrome.nativemessaging",
    "extension-host.exe",
    "uvicorn app:app",
    "ollama.exe serve",
    "ollama app.exe",
    "cloudflared.exe tunnel run",
    "-m http.server",
    "voidhaulersserver",
    "reflex-overlay.ps1",
    "stock_hunter.runtime_supervisor",
    "stock_hunter.research_campaign",
)

# Narrow signatures observed on brokered Windows Terminal windows known to be
# background-only. Intentionally excludes generic "PowerShell" / "cmd" titles.
BACKGROUND_TITLE_MARKERS = (
    r"\appdata\local\programs\python\python312\python.exe",
    "voidhaulersserver",
)

SW_HIDE = 0
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OBJID_WINDOW = 0
ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\SynapseTerminalCloak"

_user32 = ctypes.windll.user32 if os.name == "nt" else None
_kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None
_state_lock = threading.Lock()
_hidden_count = 0
_started_at = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    return _repo_root() / "data" / "terminal-cloak"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _state_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _claim_singleton() -> int | None:
    if os.name != "nt":
        return None
    assert _kernel32 is not None
    _kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = _kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        raise OSError("CreateMutexW failed")
    if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return None
    return int(handle)


def _release_singleton(handle: int | None) -> None:
    if handle and os.name == "nt":
        assert _kernel32 is not None
        _kernel32.ReleaseMutex(wintypes.HANDLE(handle))
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


def _window_title(hwnd: int) -> str:
    if os.name != "nt":
        return ""
    assert _user32 is not None
    length = _user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    buffer = ctypes.create_unicode_buffer(max(1, length + 1))
    _user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, len(buffer))
    return buffer.value


def _window_pid(hwnd: int) -> int:
    if os.name != "nt":
        return 0
    assert _user32 is not None
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def _visible_windows() -> list[int]:
    if os.name != "nt":
        return []
    assert _user32 is not None
    rows: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if _user32.IsWindowVisible(wintypes.HWND(hwnd)):
            rows.append(int(hwnd))
        return True

    _user32.EnumWindows(callback, 0)
    return rows


def _hide_window(hwnd: int) -> bool:
    if os.name != "nt":
        return False
    assert _user32 is not None
    if not _user32.IsWindowVisible(wintypes.HWND(hwnd)):
        return False
    return bool(_user32.ShowWindow(wintypes.HWND(hwnd), SW_HIDE))


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name().lower()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return ""


def _ancestry_text(pid: int, max_depth: int = 8) -> str:
    parts: list[str] = []
    current = int(pid)
    seen: set[int] = set()
    for _ in range(max_depth):
        if current <= 0 or current in seen:
            break
        seen.add(current)
        try:
            proc = psutil.Process(current)
            name = proc.name()
            try:
                cmdline = " ".join(proc.cmdline())
            except (psutil.AccessDenied, psutil.ZombieProcess):
                cmdline = ""
            parts.append(f"{name} {cmdline}")
            current = proc.ppid()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            break
    return " || ".join(parts).lower()


def _has_background_marker(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in BACKGROUND_MARKERS):
        return True
    return "codex.exe" in lowered and "app-server" in lowered and "chatgpt.exe" in lowered


def _known_background_title(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in BACKGROUND_TITLE_MARKERS)


def _recent_background_client(seconds: float = 3.0) -> bool:
    """Scan only when a brokered terminal appears, never on a timer."""
    cutoff = time.time() - max(0.5, seconds)
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            info = proc.info
            name = str(info.get("name") or "").lower()
            if name not in BACKGROUND_CLIENT_NAMES:
                continue
            if float(info.get("create_time") or 0.0) < cutoff:
                continue
            if _has_background_marker(_ancestry_text(int(info["pid"]))):
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, TypeError, ValueError):
            continue
    return False


def _classify_window(hwnd: int) -> tuple[bool, dict[str, Any]]:
    pid = _window_pid(hwnd)
    if pid <= 0:
        return False, {}
    name = _process_name(pid)
    if name not in TERMINAL_NAMES:
        return False, {}

    title = _window_title(hwnd)
    ancestry = _ancestry_text(pid)

    reason: str | None = None
    if _has_background_marker(ancestry):
        reason = "background-ancestry"
    elif name in {"windowsterminal.exe", "openconsole.exe"} and _known_background_title(title):
        reason = "known-background-title"
    elif name in {"windowsterminal.exe", "openconsole.exe"} and _recent_background_client():
        reason = "correlated-background-launch"

    return bool(reason), {
        "pid": pid,
        "process": name,
        "title": title[:240],
        "reason": reason,
    }


def _handle_window(hwnd: int, event_path: Path) -> None:
    global _hidden_count
    try:
        should_hide, details = _classify_window(hwnd)
        if not should_hide:
            return
        if not _hide_window(hwnd):
            return
        with _state_lock:
            _hidden_count += 1
            hidden_count = _hidden_count
        _append_event(
            event_path,
            {
                "timestamp": _now_iso(),
                "event": "window_hidden",
                "hwnd": int(hwnd),
                **details,
                "hidden_count": hidden_count,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- desktop guard must fail open
        _append_event(
            event_path,
            {
                "timestamp": _now_iso(),
                "event": "handler_error",
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            },
        )


def _heartbeat_loop(status_path: Path, stop: threading.Event) -> None:
    while not stop.wait(5.0):
        with _state_lock:
            hidden_count = _hidden_count
        _write_json_atomic(
            status_path,
            {
                "state": "running",
                "pid": os.getpid(),
                "started_at": _started_at,
                "heartbeat": _now_iso(),
                "mode": "win-event-hook",
                "hidden_count": hidden_count,
            },
        )


def run() -> int:
    global _started_at
    if os.name != "nt":
        return 0
    assert _user32 is not None

    mutex = _claim_singleton()
    if mutex is None:
        return 0

    data_dir = _data_dir()
    event_path = data_dir / "events.jsonl"
    status_path = data_dir / "status.json"
    _started_at = _now_iso()
    stop = threading.Event()

    _append_event(
        event_path,
        {
            "timestamp": _started_at,
            "event": "started",
            "pid": os.getpid(),
            "mode": "win-event-hook",
        },
    )

    # Clean up any stale background host that existed before this guard started.
    for hwnd in _visible_windows():
        _handle_window(hwnd, event_path)

    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(status_path, stop),
        name="terminal-cloak-heartbeat",
        daemon=True,
    )
    heartbeat.start()

    win_event_proc_type = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    @win_event_proc_type
    def on_win_event(
        _hook: int,
        _event: int,
        hwnd: int,
        object_id: int,
        child_id: int,
        _thread_id: int,
        _event_time: int,
    ) -> None:
        if not hwnd or object_id != OBJID_WINDOW or child_id != 0:
            return
        _handle_window(int(hwnd), event_path)

    hooks: list[int] = []
    try:
        for event_id in (EVENT_OBJECT_SHOW, EVENT_OBJECT_NAMECHANGE):
            hook = _user32.SetWinEventHook(
                event_id,
                event_id,
                0,
                on_win_event,
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            )
            if hook:
                hooks.append(int(hook))
        if not hooks:
            raise OSError("SetWinEventHook failed")

        # Standard message pump required for out-of-context WinEvent callbacks.
        message = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(message), 0, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))
        return 0
    finally:
        stop.set()
        for hook in hooks:
            _user32.UnhookWinEvent(wintypes.HANDLE(hook))
        with _state_lock:
            hidden_count = _hidden_count
        _write_json_atomic(
            status_path,
            {
                "state": "stopped",
                "pid": os.getpid(),
                "started_at": _started_at,
                "heartbeat": _now_iso(),
                "mode": "win-event-hook",
                "hidden_count": hidden_count,
            },
        )
        _release_singleton(mutex)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hide background-owned console windows.")
    # Retained for backward-compatible scheduled-task/dev-script arguments.
    parser.add_argument("--poll-ms", type=int, default=75, help=argparse.SUPPRESS)
    parser.parse_args()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
