import argparse
import asyncio
from prometheus_client import start_http_server
from config import load_config
from binary.version import report_binary_version_daily
from collector import cosmos  # For now, only Cosmos is supported

def run():
    parser = argparse.ArgumentParser(description="Multi-Protocol Prometheus Exporter")
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to config TOML file (default: config.toml)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    protocol = config["protocol"]

    if protocol == "cosmos":
        collector = cosmos
    else:
        raise ValueError(f"Unsupported protocol: {protocol}")

    print(f"Exporter running on :{config['metrics_port']}/metrics using config: {args.config}")
    start_http_server(config["metrics_port"])

    asyncio.run(asyncio.gather(
        collector.metric_updater(config),
        report_binary_version_daily(config)
    ))

if __name__ == "__main__":
    run()
