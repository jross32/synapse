"""Safe, read-only local machine inventory for Synapse Mesh."""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from pathlib import Path

TOOL_NAMES = ("git", "node", "npm", "python", "py", "code", "docker", "winget", "pwsh")
TOOL_ARGS = {"git": ("--version",), "node": ("--version",), "npm": ("--version",),
             "python": ("--version",), "py": ("--version",), "code": ("--version",),
             "docker": ("--version",), "winget": ("--version",), "pwsh": ("--version",)}

def development_tools() -> list[dict]:
    result=[]
    for tool in TOOL_NAMES:
        executable=shutil.which(tool)
        version=None
        if executable:
            try:
                result_run=subprocess.run([executable, *TOOL_ARGS[tool]], capture_output=True,
                                          text=True, timeout=3, shell=False, check=False)
                output=(result_run.stdout or result_run.stderr).strip().splitlines()
                version=output[0][:160] if output and result_run.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                pass
        result.append({"name":tool, "available":bool(executable), "version":version})
    return result

def disk_inventory() -> list[dict]:
    if os.name=="nt":
        roots=[f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               if Path(f"{letter}:\\").exists()]
    else:
        roots=["/"]
    result=[]
    for root in roots:
        try:
            disk=shutil.disk_usage(root)
        except OSError:
            continue
        result.append({"mount":root,"total_bytes":disk.total,
                       "used_bytes":disk.used,"free_bytes":disk.free})
    return result

def optional_hardware() -> dict:
    try:
        import psutil
    except ImportError:
        return {"memory_total_bytes": None, "battery_percent": None, "on_ac_power": None}
    memory=psutil.virtual_memory()
    battery=psutil.sensors_battery()
    return {"memory_total_bytes": int(memory.total),
            "battery_percent": float(battery.percent) if battery else None,
            "on_ac_power": bool(battery.power_plugged) if battery else None}

def hardware_inventory() -> dict:
    return {"hostname":platform.node(), "platform":platform.system().lower(),
            "architecture":platform.machine(), "cpu_logical":os.cpu_count(),
            "tools":development_tools(), "disks":disk_inventory(), **optional_hardware()}
