import asyncio
import os
import re
import subprocess
import psutil
from prometheus_client import Gauge

binary_version_metric = Gauge("binary_version_info", "Node binary version", ["version"])

def extract_binary_path_from_unit(unit_path):
    try:
        with open(unit_path, 'r') as f:
            content = f.read()
        match = re.search(r'^ExecStart=(\\S+)', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"[!] Failed to extract binary path from {unit_path}: {e}")
    return None

def find_actual_cosmos_binary_from_parent(parent_bin="cosmovisor"):
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

def get_binary_version(binary_path):
    if not binary_path:
        print("[!] No binary path provided for version check")
        return None

    version_cmds = [
        [binary_path, "version"],
        [binary_path, "--version"]
    ]

    for cmd in version_cmds:
        try:
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
            return output
        except subprocess.CalledProcessError:
            continue
    return None

async def report_binary_version_daily(config):
    unit_path = config.get("systemd_unit_path", "")
    initial_path = extract_binary_path_from_unit(unit_path)

    if initial_path and "cosmovisor" in initial_path:
        binary_path = find_actual_cosmos_binary_from_parent()
    else:
        binary_path = initial_path

    while True:
        if not binary_path:
            print(f"[!] No valid binary path found (unit: {unit_path})")
            return

        version = get_binary_version(binary_path)
        if version:
            binary_version_metric.labels(version=version).set(1)
            print(f"[✓] Binary version: {version}")
        else:
            print(f"[!] Could not determine binary version for: {binary_path}")

        await asyncio.sleep(86400)
