#!/bin/bash
# EC2 user data for the Bylaw box: Ubuntu Deep Learning Base GPU AMI (NVIDIA driver + CUDA), g6.xlarge.
# Fill the three values below before launching. The instance role needs deploy/iam-bedrock-policy.json.
set -euxo pipefail

BUCKET="__BUCKET__"     # S3 bucket holding releases/bylaw-<sha>.tar.gz
SHA="__SHA__"           # release to install
REGION="__REGION__"     # Bedrock region, e.g. us-east-1

id bylaw >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin bylaw
mkdir -p /opt
aws s3 cp "s3://$BUCKET/releases/bylaw-$SHA.tar.gz" /tmp/bylaw.tar.gz --region "$REGION"
rm -rf /opt/bylaw && tar -xzf /tmp/bylaw.tar.gz -C /opt

curl -LsSf https://astral.sh/uv/0.12.23/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
cd /opt/bylaw
uv sync --extra decider --python 3.12 --frozen
# Faster Gated DeltaNet kernels on CUDA (see the Decider's docs/inference.md). Optional: the
# reference path still works if either fails to build.
uv pip install --python .venv "flash-linear-attention>=0.5" || true
uv pip install --python .venv causal-conv1d --no-build-isolation || true
chown -R bylaw:bylaw /opt/bylaw

if [ ! -f /etc/bylaw.env ]; then
  umask 077
  cat > /etc/bylaw.env <<EOF
BYLAW_DEMO_PASS=$(openssl rand -hex 6)
BYLAW_REGION=$REGION
BYLAW_PACK=/opt/bylaw/packs/northwind.handwritten.pack.json
HF_HOME=/opt/bylaw/.hf
EOF
  chown root:bylaw /etc/bylaw.env && chmod 640 /etc/bylaw.env
fi

cp deploy/bylaw-decider.service deploy/bylaw-app.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bylaw-decider.service bylaw-app.service
