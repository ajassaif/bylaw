#!/bin/bash
# Benchmark the compiled pack (and the hand-written pack for comparison) on the reviewed held-out
# cases, then copy results to S3.  sudo -u bylaw bash deploy/jobs/bench.sh <bucket> <instance-type> [cases-s3-key]
set -euo pipefail
BUCKET="$1"; INSTANCE="$2"; CASES_KEY="${3:-results/review/reviewed.jsonl}"
cd /opt/bylaw
set -a; . /etc/bylaw.env; set +a
until curl -sf 127.0.0.1:8099/health >/dev/null; do sleep 10; done
aws s3 cp "s3://$BUCKET/$CASES_KEY" data/heldout/reviewed.jsonl --region "$BYLAW_REGION"
stamp=$(date -u +%Y-%m-%dT%H%M)-$INSTANCE
.venv/bin/bylaw bench --pack packs/northwind.pack.json --policy policies/northwind-travel.md \
  --cases data/heldout/reviewed.jsonl --out "bench/results/$stamp" --instance "$INSTANCE" --region "$BYLAW_REGION"
# the hand-written pack, Decider rows only: what a careful person writes without the compiler
.venv/bin/bylaw bench --pack packs/northwind.handwritten.pack.json --policy policies/northwind-travel.md \
  --cases data/heldout/reviewed.jsonl --out "bench/results/$stamp-handwritten-pack" --instance "$INSTANCE" \
  --baselines "" --hybrid-model "" --region "$BYLAW_REGION"
aws s3 cp --recursive bench/results "s3://$BUCKET/results/bench/" --region "$BYLAW_REGION"
echo "BENCH-DONE $stamp"
