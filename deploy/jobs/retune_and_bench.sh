#!/bin/bash
# Hand-written pack: (1) why it asks a person, (2) with Bedrock deciding the unsure calls, (3) thresholds
# retuned on the compiler's practice cases (never the test cases), benched once.  Results to S3.
#   sudo -u bylaw bash deploy/jobs/retune_and_bench.sh <bucket> <instance-type>
set -euo pipefail
BUCKET="$1"; INSTANCE="$2"
cd /opt/bylaw
set -a; . /etc/bylaw.env; set +a
until curl -sf 127.0.0.1:8099/health >/dev/null; do sleep 10; done
stamp=$(date -u +%Y-%m-%d)-$INSTANCE
P=policies/northwind-travel.md; C=data/heldout/reviewed.jsonl; H=packs/northwind.handwritten.pack.json; T=packs/northwind.handwritten.tuned.pack.json
.venv/bin/python -m scripts.explain_confirms --pack $H --cases $C --out "bench/results/$stamp-explain-handwritten.jsonl"
.venv/bin/bylaw bench --pack $H --policy $P --cases $C --out "bench/results/$stamp-handwritten-hybrid" \
  --instance "$INSTANCE" --baselines "" --hybrid-model us.amazon.nova-pro-v1:0 --region "$BYLAW_REGION"
.venv/bin/bylaw retune --pack $H --cases data/dev/northwind.dev.jsonl --rule-map data/dev/rule-map.handwritten.json --out $T
.venv/bin/python -m scripts.explain_confirms --pack $T --cases $C --out "bench/results/$stamp-explain-tuned.jsonl"
.venv/bin/bylaw bench --pack $T --policy $P --cases $C --out "bench/results/$stamp-handwritten-tuned" \
  --instance "$INSTANCE" --baselines "" --hybrid-model us.amazon.nova-pro-v1:0 --region "$BYLAW_REGION"
aws s3 cp --recursive bench/results "s3://$BUCKET/results/bench2/" --region "$BYLAW_REGION"
aws s3 cp $T "s3://$BUCKET/results/bench2/" --region "$BYLAW_REGION"
aws s3 cp ${T%.json}.retune.json "s3://$BUCKET/results/bench2/" --region "$BYLAW_REGION"
echo "RETUNE-BENCH-DONE $stamp"
