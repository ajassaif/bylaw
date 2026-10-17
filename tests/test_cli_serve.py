from typer.testing import CliRunner

import bylaw.decider
from bylaw.cli import app


def test_serve_passes_decider_timeout(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, url, timeout=30.0, **_):
            seen["timeout"] = timeout

    monkeypatch.setattr(bylaw.decider, "DeciderClient", FakeClient)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    result = CliRunner().invoke(app, ["serve", "--scripted", "--decider-timeout", "120",
                                      "--pack", "packs/northwind.handwritten.pack.json"])
    assert result.exit_code == 0, result.output
    assert seen["timeout"] == 120
