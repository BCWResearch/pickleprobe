#!/bin/bash

set -e

echo "🌐 Multi-Chain Exporter Setup Script"

# Ensure python3-venv is installed
if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "[!] python3-venv is not available. Installing..."

  if [ -f /etc/debian_version ]; then
    sudo apt update
    sudo apt install -y python3-venv
  elif [ -f /etc/redhat-release ]; then
    sudo yum install -y python3-venv
  else
    echo "[!] Unsupported OS. Please install python3-venv manually."
    exit 1
  fi
fi

# Setup Python venv
echo "📦 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install httpx prometheus_client toml psutil web3 schedule

# ---------------------------
# Gather config input
# ---------------------------
echo "🛠️  Exporter Configuration"
read -p "Enter protocol (cosmos / evm / other): " protocol
read -p "Is this a validator node? (yes/no): " is_validator
read -p "Enter Prometheus metrics port (default 3000): " metrics_port
metrics_port=${metrics_port:-3000}
read -p "Enter comma-separated binary aliases (e.g. gaiad,geth,relayer): " binary_input

# ---------------------------
# Generate config.toml
# ---------------------------
echo "📝 Writing config.toml..."
cat > config.toml <<EOF
protocol = "$protocol"
metrics_port = $metrics_port
EOF

# Add [binaries] section
echo -e "\n[binaries]" >> config.toml
IFS=',' read -ra BIN_ARRAY <<< "$binary_input"
for alias in "${BIN_ARRAY[@]}"; do
  alias_trimmed=$(echo "$alias" | xargs)
  echo "$alias_trimmed = \"/etc/systemd/system/${alias_trimmed}.service\"" >> config.toml
done

# Cosmos-specific config
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

# EVM-specific config
elif [[ "$protocol" == "evm" ]]; then
cat >> config.toml <<EOF

[default]
rpcaddress = "http://localhost:8545"

[metrics.latest_block]
description = "Latest block number of the chain"

[metrics.peer_count]
description = "Number of peers"

[metrics.syncing]
description = "Syncing status"

[metrics.blocks_to_sync]
description = "Remaining blocks to sync"

[metrics.network_name]
description = "Network chain ID or name"

[metrics.net_listening]
description = "Whether client is accepting connections"
EOF
fi

echo "✅ config.toml created."

# ---------------------------
# Create systemd service
# ---------------------------
echo "🔧 Creating systemd service: pickleprobe"

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
echo "🟢 Starting PickleProbe service..."
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
