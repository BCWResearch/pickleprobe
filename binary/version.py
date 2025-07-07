# binary/version.py

import os
import re
import subprocess
import psutil
from prometheus_client import Gauge

# Define the Prometheus metric
daily_metric = Gauge("binary_version_info", "Node binary version", ["version"])

def extract_binary_path_from_unit(unit_path):
    try:
        with open(unit_path, 'r') as f:
            content = f.read()
        match = re.search(r'^ExecStart=(\S+)', content, re.MULTILINE)
        if match:
            path = match.group(1)
            print(f"[✓] Extracted ExecStart: {path}")
            return path
    except Exception as e:
        print(f"[!] Failed to extract from systemd unit {unit_path}: {e}")
    return None

def find_actual_cosmos_binary_from_parent(parent_bin="cosmovisor"):
    try:
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            if not proc.info.get("cmdline"):
                continue
            if parent_bin in proc.info["cmdline"][0]:
                print(f"[~] Found cosmovisor at PID {proc.pid}")
                for child in proc.children():
                    try:
                        exe_path = os.readlink(f"/proc/{child.pid}/exe")
                        print(f"[✓] Found child binary: {exe_path}")
                        return exe_path
                    except Exception as e:
                        print(f"[!] Could not resolve child binary: {e}")
    except Exception as e:
        print(f"[!] Error scanning processes: {e}")
    return None

def get_binary_version(binary_path):
    if not binary_path:
        print("[!] No binary path provided")
        return None

    version_cmds = [
        [binary_path, "version"],
        [binary_path, "--version"]
    ]

    for cmd in version_cmds:
        try:
            print(f"[~] Running: {' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
            print(f"[✓] Binary version output: {output}")
            return output
        except subprocess.CalledProcessError as e:
            print(f"[!] Command failed: {e}")
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
            print(f"[!] No valid binary path found from unit: {unit_path}")
            return

        version = get_binary_version(binary_path)
        if version:
            safe_version = version.strip().split()[0]  # e.g., "4.0.1"
            daily_metric.labels(version=safe_version).set(1)
            print(f"[✓] Metric binary_version_info set to version={safe_version}")
        else:
            print(f"[!] Failed to get version from binary: {binary_path}")

        import asyncio
        await asyncio.sleep(3600)
