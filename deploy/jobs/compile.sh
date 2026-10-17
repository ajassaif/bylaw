#!/bin/bash
# Compile the Northwind policy and write the held-out cases, on the Bylaw box, then copy the
# results to S3. Run as the bylaw user:  sudo -u bylaw -E bash deploy/jobs/compile.sh <bucket>
set -euo pipefail
BUCKET="$1"
cd /opt/bylaw
set -a; . /etc/bylaw.env; set +a
stamp=$(date -u +%Y-%m-%dT%H%M)
mkdir -p logs data/dev data/heldout
until curl -sf 127.0.0.1:8099/health >/dev/null; do sleep 10; done
.venv/bin/bylaw compile policies/northwind-travel.md --out packs/northwind.pack.json \
  --dev-out data/dev/northwind.dev.jsonl --region "$BYLAW_REGION"
.venv/bin/bylaw make-heldout policies/northwind-travel.md --out data/heldout/generated.jsonl --n 160 \
  --region "$BYLAW_REGION"
for f in packs/northwind.pack.json packs/northwind.pack.md data/dev/northwind.dev.jsonl data/heldout/generated.jsonl; do
  aws s3 cp "$f" "s3://$BUCKET/results/compile-$stamp/$(basename "$f")" --region "$BYLAW_REGION"
done
echo "COMPILE-DONE results/compile-$stamp"
