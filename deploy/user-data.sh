#!/bin/bash
# EC2 user data for the Bylaw box.
#   GPU: Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04), g6.xlarge, DEVICE=cuda
#   CPU: Ubuntu Server 24.04, c7i.4xlarge, DEVICE=cpu (same answers, slower; used while the GPU quota is pending)
# Fill the four values below before launching. The instance role needs deploy/iam-bedrock-policy.json.
set -euxo pipefail

BUCKET="__BUCKET__"     # S3 bucket holding releases/bylaw-<sha>.tar.gz
SHA="__SHA__"           # release to install
REGION="__REGION__"     # Bedrock region, e.g. us-east-1
DEVICE="__DEVICE__"     # cuda or cpu

command -v aws >/dev/null || snap install aws-cli --classic
id bylaw >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin bylaw
aws s3 cp "s3://$BUCKET/releases/bylaw-$SHA.tar.gz" /tmp/bylaw.tar.gz --region "$REGION"
rm -rf /opt/bylaw && tar -xzf /tmp/bylaw.tar.gz -C /opt

curl -LsSf https://astral.sh/uv/0.12.23/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
cd /opt/bylaw
export UV_CACHE_DIR=/opt/uv-cache UV_PYTHON_INSTALL_DIR=/opt/uv-python
uv sync --extra decider --python 3.12 --frozen
if [ "$DEVICE" = "cuda" ]; then
  # Faster Gated DeltaNet kernels on CUDA (see the Decider's docs/inference.md). Optional: the
  # reference path still works if either fails to build.
  uv pip install --python .venv "flash-linear-attention>=0.5" || true
  uv pip install --python .venv causal-conv1d --no-build-isolation || true
fi
chown -R bylaw:bylaw /opt/bylaw
[ -d /opt/uv-python ] && chown -R bylaw:bylaw /opt/uv-python

if [ ! -f /etc/bylaw.env ]; then
  umask 077
  cat > /etc/bylaw.env <<EOF
BYLAW_DEMO_PASS=$(openssl rand -hex 6)
BYLAW_REGION=$REGION
BYLAW_DEVICE=$DEVICE
BYLAW_PACK=/opt/bylaw/packs/northwind.handwritten.pack.json
HF_HOME=/opt/bylaw/.hf
EOF
  chown root:bylaw /etc/bylaw.env && chmod 640 /etc/bylaw.env
fi

cp deploy/bylaw-decider.service deploy/bylaw-app.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bylaw-decider.service bylaw-app.service
echo BYLAW-BOOT-DONE
