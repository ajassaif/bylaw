# Benchmark: 45 held-out cases, pack `6c12a259db57`

| system | accuracy (95% CI) | false proceed | macro-F1 | ECE | p50 ms | p95 ms | $ / 1k | abstains |
|---|---|---|---|---|---|---|---|---|
| bylaw | 62.2% (48.9%–75.6%) | 0.0% | 0.57 | 0.10 | 11123 | 28693 | 0.000 | 0 |

Environment: {'instance': 'laptop-cpu (i5-1135G7, not a benchmark machine)', 'decider': {'status': 'ok', 'model': 'strands-decider-2B-qwen3.5-v1-2610', 'checkpoint': 'StrandsAgents/strands-decider-2B-qwen3.5-v1-2610', 'base_model': 'Qwen/Qwen3.5-2B-Base', 'num_slots': 24, 'max_length': 4096, 'temperature': 1.0545210242263665, 'device': 'cpu', 'prefix_cache': True}, 'region': 'us-east-1', 'git_sha': '4afe0a4', 'date': '2026-10-17T09:43:20+00:00', 'prices_retrieved': None}
