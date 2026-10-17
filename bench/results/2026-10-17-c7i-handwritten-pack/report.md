# Benchmark: 197 held-out cases, pack `7cfa2e9b1cd0`

| system | accuracy (95% CI) | false proceed | macro-F1 | ECE | p50 ms | p95 ms | $ / 1k | abstains |
|---|---|---|---|---|---|---|---|---|
| bylaw | 60.4% (53.8%–67.0%) | 0.0% | 0.57 | 0.10 | 1462 | 2949 | 0.296 | 0 |

Environment: {'instance': 'c7i.4xlarge (CPU)', 'decider': {'status': 'ok', 'model': 'strands-decider-2B-qwen3.5-v1-2610', 'checkpoint': 'StrandsAgents/strands-decider-2B-qwen3.5-v1-2610', 'base_model': 'Qwen/Qwen3.5-2B-Base', 'num_slots': 24, 'max_length': 4096, 'temperature': 1.0545210242263665, 'device': 'cpu', 'prefix_cache': True}, 'region': 'us-east-1', 'git_sha': '', 'date': '2026-10-17T14:25:22+00:00', 'prices_retrieved': '2026-10-17'}
