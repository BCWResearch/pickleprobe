#!/bin/bash

set -e

echo "🌐 Multi-Chain Exporter Setup Script"

# Detect OS and install python3-venv if missing
if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "[!] python3-venv is not available. Installing..."

  if [ -f /etc/debian_version ]; then
    sudo apt update
    sudo apt install -y python3-venv
  elif [ -f /etc/redhat-release ]; then
    sudo yum install -y python3-venv
  else
    echo "[!] Unsupported OS for automatic venv setup. Please install python3-venv manually."
    exit 1
  fi
fi

# Create venv
echo "📦 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install httpx prometheus_client toml psutil

# Gather basic config
echo "🛠️  Exporter Configuration"
read -p "Enter protocol (cosmos / ethereum / other): " protocol
read -p "Is this a validator node? (yes/no): " is_validator
read -p "Enter Prometheus metrics port (default 3000): " metrics_port
metrics_port=${metrics_port:-3000}

# Ask for multiple services
echo "🔍 Enter one or more systemd service files for binaries (comma-separated):"
read -p "Example: gaiad.service,relayer.service,geth.service: " service_files

# Prepare config.toml
echo "📝 Writing config.toml..."
cat > config.toml <<EOF
protocol = "$protocol"
metrics_port = $metrics_port

[binaries]
EOF

IFS=',' read -ra services <<< "$service_files"
for svc in "${services[@]}"; do
  svc=$(echo "$svc" | xargs)  # trim
  alias=${svc%.service}
  echo "$alias = \"/etc/systemd/system/$svc\"" >> config.toml
done

# Add Cosmos metrics if selected
if [[ "$protocol" == "cosmos" ]]; then
cat >> config.toml <<EOF

host = "http://localhost"
rest_port = 1317
valcons_address = ""
valoper_address = ""
account_address = ""

[metrics.latest_block]
path = "/cosmos/base/tendermint/v1beta1/blocks/latest"
description = "Latest block height"
EOF

  if [[ "$is_validator" == "yes" ]]; then
cat >> config.toml <<EOF

[metrics.validator_missed_blocks_total]
path = "/cosmos/slashing/v1beta1/signing_infos/\${valcons_address}"
description = "Total missed blocks"

[metrics.validator_is_jailed]
path = "/cosmos/staking/v1beta1/validators/\${valoper_address}"
description = "Is validator jailed"

[metrics.validator_is_active]
path = "/cosmos/staking/v1beta1/validators/\${valoper_address}"
description = "Is validator active"

[metrics.validator_commission_rate]
path = "/cosmos/staking/v1beta1/validators/\${valoper_address}"
description = "Validator commission rate"

[metrics.validator_commission_amount]
path = "/cosmos/distribution/v1beta1/validators/\${valoper_address}/commission"
description = "Total commission amount"
scaling_factor = 1e18

[metrics.validator_rewards_total]
path = "/cosmos/distribution/v1beta1/delegators/\${account_address}/rewards"
description = "Validator total rewards"
scaling_factor = 1e18
EOF
  fi
else
  echo "⚠️ Unsupported protocol '$protocol'. Only binary version metrics will be enabled."
fi

echo "✅ config.toml created."

# ---------------------------
# Create systemd service
# ---------------------------
echo "🔧 Setting up systemd service: pickleprobe"

cat > /etc/systemd/system/pickleprobe.service <<EOF
[Unit]
Description=PickleProbe Multi-Protocol Exporter
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python $(pwd)/main.py --config config.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------
# Enable + start service
# ---------------------------
echo "🟢 Enabling and starting pickleprobe..."
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable pickleprobe
systemctl restart pickleprobe

# ---------------------------
# Done!
# ---------------------------
echo -e "\n🚀 PickleProbe is installed and running!"
echo "Check status:  sudo systemctl status pickleprobe"
echo "Logs:          journalctl -u pickleprobe -f"
echo "Metrics:       curl http://localhost:$metrics_port/metrics"
