"""HTTP API for the workbench UI: the policy, the pack, a gated travel-desk chat, and benchmark results.

Chat and approve stream Server-Sent Events: a `receipt` for every gated tool call as it happens,
an `approval` when the gate asks a person to sign off, the agent's `reply`, then `done`.
"""

from __future__ import annotations

import hmac
import json
import queue
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bylaw.agent import fixtures
from bylaw.agent.session import Session
from bylaw.decider import DeciderUnavailable
from bylaw.engine import Receipt
from bylaw.pack import load_pack, pack_hash

MAX_SESSIONS = 200
DONE = object()


class NewSession(BaseModel):
    employee_id: str


class ChatIn(BaseModel):
    session_id: str
    message: str


class ApproveIn(BaseModel):
    session_id: str
    interrupt_id: str
    approved: bool


class _Live:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.events: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.agent: Any = None


def _sse(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def create_app(pack_path: Path, policy_path: Path, results_dir: Path, decider,
               agent_factory: Callable[[Session, Callable[[Receipt], None]], Any], passcode: str | None = None,
               rate_per_minute: int = 30, text_of: Callable[[Any], str] = str, web_dir: Path | None = None,
               model_id: str = "") -> FastAPI:
    pack = load_pack(pack_path)
    policy_md = Path(policy_path).read_text(encoding="utf-8")
    title = next((line.lstrip("# ").strip() for line in policy_md.splitlines() if line.startswith("#")), "Policy")
    sessions: OrderedDict[str, _Live] = OrderedDict()
    hits: dict[str, deque] = defaultdict(deque)

    app = FastAPI(title="Bylaw", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def require_pass(request: Request) -> None:
        if passcode and not hmac.compare_digest(request.headers.get("x-demo-pass", ""), passcode):
            raise HTTPException(401, "passcode required")

    def rate_limit(request: Request) -> None:
        ip = request.client.host if request.client else "?"
        now, window = time.monotonic(), hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= rate_per_minute:
            raise HTTPException(429, "slow down: too many requests this minute")
        window.append(now)

    def live(session_id: str) -> _Live:
        if session_id not in sessions:
            raise HTTPException(404, "unknown session; start a new one")
        return sessions[session_id]

    def stream(state: _Live, prompt: Any) -> Iterator[str]:
        def run() -> None:
            try:
                result = state.agent(prompt)
                interrupts = list(getattr(result, "interrupts", None) or [])
                if getattr(result, "stop_reason", None) == "interrupt" and interrupts:
                    for it in interrupts:
                        state.events.put(("approval", {"interrupt_id": it.id, "prompt": str(it.reason)}))
                else:
                    state.events.put(("reply", {"text": text_of(result)}))
            except Exception as exc:  # surfaced to the UI; the server keeps running
                state.events.put(("error", {"message": f"{type(exc).__name__}: {exc}"[:300]}))
            finally:
                state.events.put(DONE)

        with state.lock:  # one turn at a time per session
            threading.Thread(target=run, daemon=True).start()
            while (item := state.events.get()) is not DONE:
                yield _sse(*item)
            yield _sse("done", {})

    @app.get("/api/health")
    def health() -> dict:
        try:
            decider_state = decider.health()
        except DeciderUnavailable:
            decider_state = {"status": "down"}
        return {"decider": decider_state, "pack_hash": pack_hash(pack), "model": model_id}

    guarded = [Depends(require_pass)]

    @app.get("/api/policy", dependencies=guarded)
    def policy() -> dict:
        return {"title": title, "markdown": policy_md}

    @app.get("/api/pack", dependencies=guarded)
    def get_pack() -> dict:
        return {**pack.model_dump(mode="json"), "hash": pack_hash(pack)}

    @app.get("/api/employees", dependencies=guarded)
    def employees() -> list[dict]:
        return list(fixtures.EMPLOYEES.values())

    @app.get("/api/bench", dependencies=guarded)
    def bench() -> dict:
        runs = sorted(p for p in Path(results_dir).glob("*/summary.json"))
        if not runs:
            raise HTTPException(404, "no benchmark results yet")
        return json.loads(runs[-1].read_text(encoding="utf-8"))

    @app.post("/api/sessions", dependencies=guarded)
    def new_session(body: NewSession) -> dict:
        if body.employee_id not in fixtures.EMPLOYEES:
            raise HTTPException(404, "unknown employee")
        state = _Live(Session(body.employee_id))
        state.agent = agent_factory(state.session, lambda r: state.events.put(("receipt", r.to_dict())))
        session_id = uuid.uuid4().hex
        sessions[session_id] = state
        while len(sessions) > MAX_SESSIONS:
            sessions.popitem(last=False)
        return {"session_id": session_id}

    @app.post("/api/chat", dependencies=[*guarded, Depends(rate_limit)])
    def chat(body: ChatIn) -> StreamingResponse:
        state = live(body.session_id)
        return StreamingResponse(stream(state, body.message[:2000]), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/approve", dependencies=[*guarded, Depends(rate_limit)])
    def approve(body: ApproveIn) -> StreamingResponse:
        state = live(body.session_id)
        responses = [{"interruptResponse": {"interruptId": body.interrupt_id,
                                            "response": "yes" if body.approved else "no"}}]
        return StreamingResponse(stream(state, responses), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if web_dir is not None and Path(web_dir).exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
