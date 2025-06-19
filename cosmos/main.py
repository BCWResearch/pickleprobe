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
    asyncio.run(metric_updater())

if __name__ == "__main__":
    run()
