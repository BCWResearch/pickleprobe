import asyncio
import os
import re
import subprocess
import psutil
from prometheus_client import Gauge

# Prometheus metric
binary_version_metric = Gauge("binary_version_info", "Node binary version", ["version"])

# -----------------------------------
# Extract binary path from unit file
# -----------------------------------
def extract_binary_path_from_unit(unit_path):
    try:
        with open(unit_path, 'r') as f:
            content = f.read()
        match = re.search(r'^ExecStart=(\S+)', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"[!] Failed to extract binary path from {unit_path}: {e}")
    return None

# -----------------------------------
# Detect real binary under Cosmovisor
# -----------------------------------
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

# -----------------------------------
# Run version command on binary
# -----------------------------------
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
            print(f"[~] Trying: {' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
            print(f"[✓] Raw version output: {output}")
            return output
        except subprocess.CalledProcessError:
            continue
        except Exception as e:
            print(f"[!] Error running {cmd}: {e}")
    return None

# -----------------------------------
# Extract semver-like version using regex
# -----------------------------------
def extract_version_string(output: str) -> str:
    match = re.search(r"\b\d+\.\d+\.\d+([\-+a-zA-Z0-9]*)?\b", output)
    if match:
        return match.group(0)
    return "unknown"

# -----------------------------------
# Daily metric reporter
# -----------------------------------
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

        version_output = get_binary_version(binary_path)
        if version_output:
            safe_version = extract_version_string(version_output)
            binary_version_metric.labels(version=safe_version).set(1)
            print(f"[✓] binary_version_info metric set to version={safe_version}")
        else:
            print(f"[!] Could not determine binary version for: {binary_path}")

        await asyncio.sleep(86400)  # Run once per day
