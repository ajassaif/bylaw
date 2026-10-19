# Benchmark: 197 held-out cases, pack `de454c87d702`

| system | accuracy (95% CI) | false proceed | macro-F1 | ECE | p50 ms | p95 ms | $ / 1k | abstains |
|---|---|---|---|---|---|---|---|---|
| bylaw | 66.0% (59.4%–72.6%) | 0.0% | 0.62 | 0.09 | 1066 | 2264 | 0.262 | 0 |
| bylaw+hybrid | 86.3% (81.2%–90.9%) | 0.0% | 0.86 | 0.09 | 1295 | 3383 | 0.689 | 0 |

Hybrid: Decider decided 71.6% of cases alone and escalated 56 to `us.amazon.nova-pro-v1:0`.


Environment: {'instance': 'c7i.4xlarge', 'decider': {'status': 'ok', 'model': 'strands-decider-2B-qwen3.5-v1-2610', 'checkpoint': 'StrandsAgents/strands-decider-2B-qwen3.5-v1-2610', 'base_model': 'Qwen/Qwen3.5-2B-Base', 'num_slots': 24, 'max_length': 4096, 'temperature': 1.0545210242263665, 'device': 'cpu', 'prefix_cache': True}, 'region': 'us-east-1', 'git_sha': '', 'date': '2026-10-19T15:52:33+00:00', 'prices_retrieved': '2026-10-17'}
