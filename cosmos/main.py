import argparse
import asyncio
import httpx
import toml
import time
from prometheus_client import Gauge, start_http_server

# ---------------------------
# Argument Parsing
# ---------------------------
parser = argparse.ArgumentParser(description="Cosmos Prometheus Exporter")
parser.add_argument(
    "--config",
    type=str,
    default="config.toml",
    help="Path to config TOML file (default: config.toml)"
)
args = parser.parse_args()

# ---------------------------
# Load Config
# ---------------------------
with open(args.config) as f:
    raw_config = toml.load(f)

host = raw_config["host"]
rest_port = raw_config["rest_port"]
valcons = raw_config["valcons_address"]
valoper = raw_config["valoper_address"]
account = raw_config["account_address"]
port = raw_config["metrics_port"]
metrics_config = raw_config["metrics"]

# ---------------------------
# Gauges
# ---------------------------
gauges = {}

for name, m in metrics_config.items():
    gauges[name] = Gauge(name, m["description"])

binary_version_metric = Gauge("binary_version_info", "Node binary version", ["version"])

def extract_binary_path_from_unit(unit_path):
    import re
    try:
        with open(unit_path, 'r') as f:
            content = f.read()
        match = re.search(r'^ExecStart=(\S+)', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"[!] Failed to extract binary path from {unit_path}: {e}")
    return None

def get_binary_version(binary_path):
    import subprocess

    version_cmds = [
        [binary_path, "version"],
        [binary_path, "--version"]
    ]

    for cmd in version_cmds:
        try:
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
            return output
        except subprocess.CalledProcessError as e:
            continue
    return None

async def report_binary_version_daily():
    unit_path = raw_config.get("systemd_unit_path", "")
    binary_path = extract_binary_path_from_unit(unit_path)

    while True:
        if not binary_path:
            print(f"[!] No binary path found from unit file: {unit_path}")
            return

        version = get_binary_version(binary_path)
        if version:
            binary_version_metric.labels(version=version).set(1)
            print(f"[✓] Binary version: {version}")
        else:
            print(f"[!] Could not determine binary version for: {binary_path}")

        await asyncio.sleep(86400)


# ---------------------------
# Fetch Function
# ---------------------------
async def fetch_metric(name, client):
    cfg = metrics_config[name]
    path = cfg["path"]
    path = path.replace("${valcons_address}", valcons)
    path = path.replace("${valoper_address}", valoper)
    path = path.replace("${account_address}", account)
    url = f"{host}:{rest_port}{path}"

    try:
        response = await client.get(url, timeout=5.0)
        data = response.json()

        match name:
            case "latest_block_height":
                h = int(data["block"]["header"]["height"])
                gauges[name].set(h)
            case "validator_missed_blocks_total":
                missed = int(data["val_signing_info"]["missed_blocks_counter"])
                gauges[name].set(missed)
            case "validator_is_jailed":
                jailed = data["validator"]["jailed"]
                gauges[name].set(1 if jailed else 0)
            case "validator_is_active":
                status = data["validator"]["status"]
                gauges[name].set(1 if status == "BOND_STATUS_BONDED" else 0)
            case "validator_commission_rate":
                rate = float(data["validator"]["commission"]["commission_rates"]["rate"])
                gauges[name].set(rate)
            case "validator_commission_amount":
                amt = float(data["commission"]["commission"][0]["amount"])
                factor = cfg.get("scaling_factor", 1.0)
                gauges[name].set(amt / factor)
            case "validator_rewards_total":
                rewards = data["rewards"]
                if rewards:
                    amt = float(rewards[0]["amount"])
                    factor = cfg.get("scaling_factor", 1.0)
                    gauges[name].set(amt / factor)

        print(f"[✓] {name} updated")

    except Exception as e:
        print(f"[!] Failed to update {name}: {e}")

# ---------------------------
# Update Loop
# ---------------------------
async def metric_updater():
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.gather(*(fetch_metric(name, client) for name in gauges))
            await asyncio.sleep(10)

# ---------------------------
# Entrypoint
# ---------------------------
def run():
    print(f"Exporter running on :{port}/metrics using config: {args.config}")
    start_http_server(port)
    async def start_all_tasks():
        await asyncio.gather(
            metric_updater(),              # regular metrics every 10s
            report_binary_version_daily()  # once per day
        )

    asyncio.run(start_all_tasks())

if __name__ == "__main__":
    run()
