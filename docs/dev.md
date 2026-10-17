# Developing Bylaw

## Tests

```bash
uv sync
uv run pytest            # fast suite: fake Decider, fake Bedrock, no network
cd web && npm test       # UI helpers
```

Live tests are marked `live` and skipped by default. They need a running Decider server and,
for the agent test, Bedrock credentials:

```bash
uv sync --extra decider
uv run --extra decider strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device cpu --port 8099
uv run --extra decider pytest -m live -v
```

`uv run` without `--extra decider` syncs the environment back to the default set and removes
the Decider package. Use `--extra decider` every time once it is installed.

## Running the Decider on a laptop

The first `serve` downloads `Qwen/Qwen3.5-2B-Base` (about 4.5 GB) into the Hugging Face cache.
On Windows the cache warns that symlinks are unavailable; it still works.

Observed on the development laptop (Intel i5-1135G7, 16 GB RAM, Windows 11, CPU only, fp32):
one request with six questions over a ~650-token state took about 20–30 s. That is a laptop
CPU and not a benchmark. Every latency number Bylaw reports comes from `bench/results/` on the
GPU instance.

## Previewing the UI without Bedrock

```bash
uv run --extra decider python scripts/write_handwritten_pack.py
uv run --extra decider bylaw serve --pack packs/northwind.handwritten.pack.json --scripted
cd web && npm run dev      # http://localhost:5173, proxies /api to :8080
```

`--scripted` swaps the language model for a fixed set of demo requests. The policy gate and the
Decider are real, so the receipts are real; only the conversation is scripted, and the UI says so.
