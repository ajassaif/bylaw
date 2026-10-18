# Deploying Bylaw on AWS

One GPU instance runs the Decider (localhost only) and the Bylaw app. CloudFront sits in front
of it, and an S3 "sleeping" page stands in whenever the instance is stopped, at the same URL.
The GPU box runs only for benchmarking, recording and the scheduled judging windows.

The results in this repo were run on a `c7i.4xlarge` CPU instance instead: the account had no GPU
quota during the hackathon. Every step below is the same with that instance type; only the speed differs.

Steps marked **[confirm]** cost money or publish something. Each one is approved by the owner
of the AWS account before it runs.

```
viewer ──▶ CloudFront ──origin group──▶ EC2 g6.xlarge :8080 (bylaw serve) ──▶ 127.0.0.1:8099 (Decider)
                         └─ on 5xx/timeout ─▶ S3 sleeping page                └──▶ Amazon Bedrock
```

## 1. Bedrock model access

In the Bedrock console for the chosen region (default `us-east-1`), request access to:

| Role | Default model (check the console for the exact ID) |
|---|---|
| Travel-desk agent, hybrid fallback | Amazon Nova Pro |
| Compiler and dev-case writer | Mistral Large 3 |
| Held-out case writer (a different family) | DeepSeek V3.2 |
| Baselines | Nova Pro, Nova Lite, Mistral Large 3 (plus Claude Haiku, Sonnet and Opus once the account's Anthropic access opens) |

Record the exact model or inference-profile IDs in `src/bylaw/config.py` (or set `BYLAW_*`
variables in `/etc/bylaw.env`) and the on-demand prices in `bench/prices.json`, with the date
you read them.

## 2. Bucket and release

1. **[confirm]** Create a private S3 bucket (block all public access), e.g. `bylaw-<account>-<region>`.
2. `bash scripts/package.sh` → `dist/bylaw-<sha>.tar.gz`; upload it to `s3://<bucket>/releases/`.

## 3. IAM

1. Create a policy from `deploy/iam-bedrock-policy.json` with `__REGION__`, `__ACCOUNT__` and
   `__BUCKET__` filled in.
2. Create an EC2 role with that policy plus `AmazonSSMManagedInstanceCore` (shell access through
   Session Manager; no SSH key, no port 22).

## 4. Network

Security group `bylaw-app`: inbound TCP 8080 from the AWS-managed prefix list
`com.amazonaws.global.cloudfront.origin-facing` only. No other inbound rules.

## 5. Instance

1. **[confirm]** Launch `g6.xlarge` (NVIDIA L4, 24 GB) from the latest "Deep Learning Base OSS
   Nvidia Driver GPU AMI (Ubuntu 22.04)", 100 GB gp3 root volume, the role from step 3, the
   group from step 4, and `deploy/user-data.sh` with its three values filled in.
2. **[confirm]** Allocate an Elastic IP and associate it (CloudFront needs a stable origin name;
   use the IP's public DNS name).
3. Wait for first boot (dependencies plus a ~4.5 GB model download), then check through
   Session Manager:
   ```bash
   curl -s 127.0.0.1:8099/health      # "device": "cuda"
   curl -s 127.0.0.1:8080/api/health
   sudo cat /etc/bylaw.env            # the demo passcode
   ```

## 6. CloudFront

1. Upload the baked sleeping page (`python -m scripts.bake_sleeping ...`) to
   `s3://<bucket>/sleeping/index.html`.
2. **[confirm]** Create a distribution with two origins: the instance's public DNS on HTTP 8080
   (primary) and the bucket's `sleeping/` path through Origin Access Control (secondary). Put them
   in an origin group that fails over on 500, 502, 503 and 504 and on connection timeouts
   (connection attempts 1, timeout 3 s). Default behaviour: allowed methods GET/HEAD/OPTIONS/PUT/
   POST/PATCH/DELETE, caching disabled, origin request policy "AllViewer" so `x-demo-pass`
   reaches the app. Failover only applies to GET/HEAD, which is the page load; that is enough to
   show the sleeping page.
3. Check the URL with the instance on, then stop the instance and check the sleeping page appears.

## 7. Schedule

**[confirm]** EventBridge Scheduler: one schedule calling `ec2:StartInstances` and one calling
`ec2:StopInstances` for each judging window agreed with the owner, with a role allowed only those
two actions on this instance.

## Running the compiler and benchmark on the box

```bash
sudo -u bylaw -i
cd /opt/bylaw && source .venv/bin/activate
bylaw compile policies/northwind-travel.md --out packs/northwind.pack.json --dev-out data/dev/northwind.dev.jsonl
bylaw make-heldout policies/northwind-travel.md --out data/heldout/generated.jsonl
# review labels on the laptop, then:
bylaw bench --pack packs/northwind.pack.json --policy policies/northwind-travel.md \
  --cases data/heldout/reviewed.jsonl --out bench/results/$(date -u +%Y-%m-%dT%H%M)-g6 --instance g6.xlarge
aws s3 cp --recursive bench/results s3://<bucket>/results/
```

## Teardown

Delete the CloudFront distribution, terminate the instance, release the Elastic IP (it is billed
while unattached), delete the schedules, empty and delete the bucket.
