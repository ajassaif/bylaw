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


if __name__ == "__main__":
    app()
