#!/bin/bash
# Compile the Northwind policy, then benchmark the compiled pack (with Bedrock baselines) and the
# hand-written pack (Decider only) on the reviewed held-out cases, and copy everything to S3.
# Run as root:  nohup bash deploy/jobs/compile_and_bench.sh <bucket> <label> <instance-desc> <usd-per-hour> &
set -uo pipefail
BUCKET="$1"; LABEL="$2"; INSTANCE="$3"; HOURLY="$4"
cd /opt/bylaw
set -a; . /etc/bylaw.env; set +a
as_bylaw() { sudo -u bylaw -E "$@"; }
log() { echo "[chain $(date -u +%H:%M:%S)] $*" | tee -a logs/chain.log; }

until curl -sf 127.0.0.1:8099/health >/dev/null; do sleep 10; done
aws s3 cp "s3://$BUCKET/results/review/reviewed.jsonl" data/heldout/reviewed.jsonl --region "$BYLAW_REGION" \
  && chown bylaw:bylaw data/heldout/reviewed.jsonl
python3 - "$INSTANCE" "$HOURLY" <<'PY'
import json, sys
p = json.load(open("bench/prices.json"))
p["gpu_instance"], p["gpu_usd_per_hour"] = sys.argv[1], float(sys.argv[2])
json.dump(p, open("/tmp/prices-run.json", "w"))
PY

log "compile"
as_bylaw .venv/bin/bylaw compile policies/northwind-travel.md --out packs/northwind.pack.json \
  --dev-out data/dev/northwind.dev.jsonl > "logs/compile-$LABEL.log" 2>&1 || log "compile FAILED"
tar -czf "/tmp/bylaw-compile-$LABEL.tar.gz" packs/northwind.pack.json packs/northwind.pack.md \
  data/dev/northwind.dev.jsonl "logs/compile-$LABEL.log"
aws s3 cp "/tmp/bylaw-compile-$LABEL.tar.gz" "s3://$BUCKET/results/" --region "$BYLAW_REGION"

log "bench compiled pack"
as_bylaw .venv/bin/bylaw bench --pack packs/northwind.pack.json --policy policies/northwind-travel.md \
  --cases data/heldout/reviewed.jsonl --out "bench/results/$LABEL" --instance "$INSTANCE" \
  --prices /tmp/prices-run.json > "logs/bench-$LABEL.log" 2>&1 || log "bench FAILED"
log "bench hand-written pack"
as_bylaw .venv/bin/bylaw bench --pack packs/northwind.handwritten.pack.json --policy policies/northwind-travel.md \
  --cases data/heldout/reviewed.jsonl --out "bench/results/$LABEL-handwritten-pack" --instance "$INSTANCE" \
  --prices /tmp/prices-run.json --baselines "" --hybrid-model "" >> "logs/bench-$LABEL.log" 2>&1 || log "bench2 FAILED"
tar -czf "/tmp/bylaw-bench-$LABEL.tar.gz" "bench/results/$LABEL" "bench/results/$LABEL-handwritten-pack" \
  "logs/bench-$LABEL.log" logs/chain.log
aws s3 cp "/tmp/bylaw-bench-$LABEL.tar.gz" "s3://$BUCKET/results/" --region "$BYLAW_REGION"
log "ALL-DONE $LABEL"
