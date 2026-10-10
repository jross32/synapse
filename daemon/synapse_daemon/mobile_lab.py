"""Read-only, install-free iOS-first mobile capability assessment.

No simulator is downloaded, no phones are modified, and no user identifiers are exposed.
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone


def _available_memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                ("available_extended", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.available_physical)
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as file:
            for line in file:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _safe_version(executable: str, *arguments: str) -> str | None:
    path = shutil.which(executable)
    if not path:
        return None
    try:
        result = subprocess.run([path, *arguments], capture_output=True,
                                text=True, timeout=4, check=False)
        return (result.stdout or result.stderr).strip()[:200] or "installed"
    except (OSError, subprocess.TimeoutExpired):
        return "installed (version unavailable)"


def system_capabilities() -> dict:
    """Current host state and safe iOS provider options (no privileged operations)."""
    system = platform.system()
    mac = system == "Darwin"
    available = _available_memory_bytes()
    disk = shutil.disk_usage(os.path.expanduser("~"))
    xcode = _safe_version("xcrun", "--version") if mac else None
    appium = _safe_version("appium", "--version")
    adb = _safe_version("adb", "version")
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "os": system,
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "available_ram_bytes": available,
        "home_disk_free_bytes": disk.free,
        "installed_tools": {"xcrun": bool(xcode), "appium": bool(appium), "adb": bool(adb)},
        "ios": {
            "native_simulator_supported": mac,
            "native_simulator_ready": mac and bool(xcode),
            "remote_mac_bridge": "not_configured",
            "physical_iphone_bridge": "not_configured",
            "can_run_iphone_simulator_on_this_host": mac and bool(xcode),
            "next_step": ("Check Xcode simulator runtimes; do not download automatically."
                          if mac and xcode else
                          "Connect a Mac running Xcode or a supported physical iPhone bridge."),
        },
        "policy": {
            "install_performed": False,
            "automatic_downloads": False,
            "low_memory_warning": available is not None and available < 3 * 1024**3,
            "secrets_and_device_identifiers_excluded": True,
        },
    }


def device_plan(capabilities: dict) -> dict:
    """Choose genuine iOS paths, never mislabel browser emulation as native iOS."""
    ios = capabilities["ios"]
    if ios["native_simulator_ready"]:
        provider = "local-macos-xcode"
    elif ios["remote_mac_bridge"] == "configured":
        provider = "remote-macos-xcode"
    elif ios["physical_iphone_bridge"] == "configured":
        provider = "physical-iphone"
    else:
        provider = "unavailable"
    return {
        "platform": "ios",
        "selected_provider": provider,
        "ready": provider != "unavailable",
        "fallback": "browser-mobile-viewport-only",
        "fallback_is_native_ios": False,
        "installation_required_now": False,
        "reason": ios["next_step"] if provider == "unavailable" else "iOS provider available",
    }
