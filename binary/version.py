import asyncio
import os
import re
import subprocess
import psutil
from typing import Dict
from prometheus_client import Gauge

binary_version_metric = Gauge("binary_version_info", "Node binary version", ["version", "binary"])

def extract_binary_path_from_unit(unit_path: str) -> str | None:
    try:
        with open(unit_path, 'r') as f:
            content = f.read()
        match = re.search(r'^ExecStart=(\S+)', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"[!] Failed to extract binary path from {unit_path}: {e}")
    return None

def find_actual_binary(parent_bin="cosmovisor") -> str | None:
    try:
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            if not proc.info.get("cmdline"):
                continue
            if parent_bin in proc.info["cmdline"][0]:
                children = proc.children()
                for child in children:
                    try:
                        exe_path = os.readlink(f"/proc/{child.pid}/exe")
                        return exe_path
                    except Exception:
                        continue
    except Exception as e:
        print(f"[!] Error inspecting processes: {e}")
    return None

def get_binary_version(binary_path: str) -> str | None:
    version_cmds = [
        [binary_path, "version"],
        [binary_path, "--version"]
    ]
    for cmd in version_cmds:
        try:
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
            match = re.search(r"\b\d+\.\d+\.\d+([\-+a-zA-Z0-9]*)?\b", output)
            if match:
                return match.group(0)
            return output
        except subprocess.CalledProcessError:
            continue
    return None

async def report_binary_version_daily(config: Dict):
    binaries = config.get("binaries", {})
    if not binaries:
        print("[!] No binaries specified in config.")
        return

    while True:
        for name, unit_path in binaries.items():
            print(f"[~] Checking binary for: {name}")
            initial_path = extract_binary_path_from_unit(unit_path)

            binary_path = find_actual_binary() if (initial_path and "cosmovisor" in initial_path) else initial_path

            if not binary_path:
                print(f"[!] No valid binary path for {name} (unit: {unit_path})")
                continue

            version = get_binary_version(binary_path)
            if version:
                binary_version_metric.labels(version=version, binary=name).set(1)
                print(f"[✓] {name} version: {version}")
            else:
                print(f"[!] Could not determine version for {name}")

        await asyncio.sleep(86400)  # every 24h
