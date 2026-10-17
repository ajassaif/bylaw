"""Command line: bylaw compile | make-heldout | bench | serve."""

from __future__ import annotations

from pathlib import Path

import typer

from bylaw import config

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Compile a policy into a Decider policy pack.")


@app.command()
def compile(
    policy: Path = typer.Argument(..., exists=True, help="Policy markdown file."),
    out: Path = typer.Option(..., help="Where to write pack.json (pack.md goes alongside)."),
    dev_out: Path = typer.Option(None, help="Where to write the generated dev cases (jsonl)."),
    decider_url: str = typer.Option(config.DECIDER_URL),
    region: str = typer.Option(config.REGION),
    model: str = typer.Option(config.COMPILER_MODEL, help="Bedrock model that reads the policy."),
    case_model: str = typer.Option(config.CASE_MODEL, help="Bedrock model that writes dev cases."),
    per_rule: int = typer.Option(8),
    rounds: int = typer.Option(2),
) -> None:
    """Read a policy, write a tuned policy pack and its report."""
    from bylaw.agent.tools import TOOL_DESCRIPTIONS
    from bylaw.cases import save_cases
    from bylaw.compiler.pipeline import CompileConfig, compile_policy
    from bylaw.decider import DeciderClient
    from bylaw.llm import BedrockLLM
    from bylaw.pack import pack_hash, save_pack

    decider = DeciderClient(decider_url, timeout=120)
    typer.echo(f"decider: {decider.health()}")
    cfg = CompileConfig(model_id=model, case_model_id=case_model, region=region, per_rule=per_rule, rounds=rounds)
    pack, cases, report = compile_policy(policy.read_text(encoding="utf-8"), BedrockLLM(region), decider, cfg,
                                         TOOL_DESCRIPTIONS)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_pack(pack, out)
    out.with_suffix(".md").write_text(report, encoding="utf-8")
    if dev_out:
        save_cases(cases, dev_out)
    typer.echo(f"wrote {out} (pack {pack_hash(pack)}): {len(pack.rules)} rules, {len(pack.checks)} checks, "
               f"{len(pack.questions)} questions, {len(cases)} dev cases")


@app.command("make-heldout")
def make_heldout(
    policy: Path = typer.Argument(..., exists=True),
    out: Path = typer.Option(...),
    model: str = typer.Option(config.HELDOUT_MODEL, help="Must be a different family from the dev-case model."),
    n: int = typer.Option(160),
    region: str = typer.Option(config.REGION),
) -> None:
    """Write held-out cases from the policy text alone."""
    from bylaw.bench.heldout import generate_heldout
    from bylaw.cases import save_cases
    from bylaw.llm import BedrockLLM

    if model.split(".")[1:2] == config.CASE_MODEL.split(".")[1:2]:
        raise typer.BadParameter(f"{model} is the same family as the dev-case model {config.CASE_MODEL}")
    cases = generate_heldout(policy.read_text(encoding="utf-8"), BedrockLLM(region), model, n)
    save_cases(cases, out)
    typer.echo(f"wrote {len(cases)} held-out cases to {out}. Review every label before benchmarking.")


@app.command()
def bench(
    pack: Path = typer.Option(..., exists=True),
    policy: Path = typer.Option(..., exists=True),
    cases: Path = typer.Option(..., exists=True),
    out: Path = typer.Option(...),
    baselines: str = typer.Option(",".join(config.BASELINES)),
    hybrid_model: str = typer.Option(config.HYBRID_MODEL),
    prices: Path = typer.Option(Path("bench/prices.json"), exists=True,
                                help='{"models": {id: [usd_per_1M_in, usd_per_1M_out]}, "gpu_usd_per_hour": x}'),
    instance: str = typer.Option("unknown", help="EC2 instance type the Decider ran on."),
    decider_url: str = typer.Option(config.DECIDER_URL),
    region: str = typer.Option(config.REGION),
) -> None:
    """Score Bylaw against Bedrock models deciding alone. Writes cases.jsonl, summary.json, report.md."""
    import json
    import subprocess
    from datetime import UTC, datetime

    from bylaw.bench.run import run_bench
    from bylaw.cases import load_cases
    from bylaw.decider import DeciderClient
    from bylaw.llm import BedrockLLM
    from bylaw.pack import load_pack

    price_data = json.loads(prices.read_text(encoding="utf-8"))
    decider = DeciderClient(decider_url, timeout=120)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    env = {"instance": instance, "decider": decider.health(), "region": region, "git_sha": sha,
           "date": datetime.now(UTC).isoformat(timespec="seconds"), "prices_retrieved": price_data.get("retrieved")}
    summary = run_bench(load_pack(pack), policy.read_text(encoding="utf-8"), load_cases(cases), decider,
                        BedrockLLM(region), [b for b in baselines.split(",") if b], hybrid_model, out,
                        {k: tuple(v) for k, v in price_data["models"].items()}, price_data["gpu_usd_per_hour"], env)
    typer.echo((out / "report.md").read_text(encoding="utf-8"))
    typer.echo(f"{summary['n_cases']} cases scored; results in {out}")


@app.command()
def serve(
    pack: Path = typer.Option(Path("packs/northwind.pack.json"), exists=True),
    policy: Path = typer.Option(Path("policies/northwind-travel.md"), exists=True),
    results: Path = typer.Option(Path("bench/results")),
    web: Path = typer.Option(Path("web/dist")),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8080),
    decider_url: str = typer.Option(config.DECIDER_URL),
    model: str = typer.Option(config.AGENT_MODEL),
    hybrid_model: str = typer.Option("", help="Escalate uncertain calls to this Bedrock model; empty = ask a person."),
    region: str = typer.Option(config.REGION),
    scripted: bool = typer.Option(False, help="No-LLM desk for previews: fixed demo requests, real gate and Decider."),
) -> None:
    """Serve the workbench UI and the gated travel desk. Passcode from BYLAW_DEMO_PASS."""
    import os

    import uvicorn

    from bylaw.agent.desk import build_desk
    from bylaw.api.app import create_app
    from bylaw.decider import DeciderClient
    from bylaw.judge import LLMJudge
    from bylaw.llm import BedrockLLM
    from bylaw.pack import load_pack

    loaded = load_pack(pack)
    decider = DeciderClient(decider_url)
    escalator = LLMJudge(BedrockLLM(region), hybrid_model, policy.read_text(encoding="utf-8")) if hybrid_model else None

    def factory(session, on_receipt):
        if scripted:
            from bylaw.agent.scripted import ScriptedDesk

            return ScriptedDesk(loaded, decider, session, on_receipt, escalator=escalator)
        return build_desk(loaded, decider, session, model, escalator=escalator, on_receipt=on_receipt, region=region)

    def text_of(result) -> str:
        text = getattr(result, "text", None)
        return text if isinstance(text, str) else str(result)

    results.mkdir(parents=True, exist_ok=True)
    api = create_app(pack, policy, results, decider, factory, passcode=os.environ.get("BYLAW_DEMO_PASS"),
                     web_dir=web, model_id="scripted (no language model)" if scripted else model, text_of=text_of)
    uvicorn.run(api, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
