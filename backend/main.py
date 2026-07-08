"""FastAPI app: SSE endpoint that streams a debate, plus static frontend mount.

Boundary contract (Spec 02 §5): all transport/SSE/json concerns live HERE, never in
crew.py. run_debate() yields plain (speaker, text) tuples; this module formats them
as SSE data events and sends a final `event: done`.

Routes:
- GET /debate?topic=<url-encoded>  → text/event-stream of debate turns
- GET /                            → static frontend (index.html, style.css, script.js)

Per Spec 04 §4, the static mount is added AFTER the /debate route so the SSE endpoint
isn't shadowed by the catch-all.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import MAX_TOPIC_LENGTH, get_available_models
from .crew import run_debate, run_single_turn, run_verdict
from .sessions import (
    MAX_DEBATE_TURNS,
    Session,
    create_session,
    drop_session,
    get_session,
)

app = FastAPI(title="AI Debate Arena")

# Resolve frontend/ relative to repo root (this file is at backend/main.py).
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/models")
def list_models():
    """Return the model ids the deployer's provider exposes, for the frontend
    dropdowns. Proxies config.get_available_models() (which calls the provider's
    GET /v1/models). Returns [] if the provider can't be reached — the frontend
    treats an empty list as "hide the dropdowns, default only".

    Registered before the static mount so it isn't shadowed by the catch-all.
    """
    return {"models": get_available_models()}


def _format_sse_event(data: dict, event: str | None = None) -> str:
    """Format one SSE message. Per the SSE spec, each event is terminated by \n\n."""
    payload = json.dumps(data)
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


# --- v1.3: open-ended mode (user chooses when to judge) -----------------------
# Stateful sessions — see backend/sessions.py. Classic mode (/debate below) is
# untouched and remains the path the smoke test + existing E2E tests exercise.

@app.post("/debate/start")
def debate_start(payload: dict):
    """Begin an open-ended debate. Returns a session id the frontend uses for the
    subsequent /stream, /next, /verdict calls. Validates topic + model overrides
    the same way classic /debate does, before creating the session."""
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        return JSONResponse({"error": "Please enter a topic to start the debate."}, status_code=400)
    if len(topic) > MAX_TOPIC_LENGTH:
        topic = topic[:MAX_TOPIC_LENGTH]
    model_for = payload.get("model_for") or None
    model_against = payload.get("model_against") or None
    session = create_session(topic, model_for, model_against)
    return {"session_id": session.session_id}


def _stream_session_turns(session: Session, sides: list[str]) -> Iterator[str]:
    """Yield one SSE event per turn for the requested sides, then `event: paused`.

    Enforces the MAX_DEBATE_TURNS cap: if the transcript is full, yields an
    auto-verdict instead of more turns. Wraps each turn in try/except so a single
    LLM failure becomes a friendly System event rather than a crashed stream.
    """
    with session.lock:
        for side in sides:
            # Cap check — auto-judge instead of exceeding the turn budget.
            if len(session.transcript) >= MAX_DEBATE_TURNS:
                verdict = run_verdict(session.topic, session.transcript)
                session.transcript.append(f"Moderator: {verdict}")
                session.judged = True
                yield _format_sse_event(
                    {"speaker": "Moderator — Final Verdict", "text": verdict},
                    event="verdict",
                )
                yield _format_sse_event({}, event="done")
                return
            if session.judged:
                # User judged while we were running; stop immediately.
                yield _format_sse_event({}, event="done")
                return
            turn_number = len(session.transcript) + 1
            override = session.model_for if side == "for" else session.model_against
            try:
                entry = run_single_turn(side, session.topic, session.transcript, turn_number, override)
            except Exception:
                yield _format_sse_event(
                    {"speaker": "System", "text": "The debate hit a temporary error and couldn't continue. Please try again in a moment."},
                    event="turn",
                )
                yield _format_sse_event({}, event="done")
                return
            session.transcript.append(entry)
            label, _, text = entry.partition(": ")
            yield _format_sse_event({"speaker": label, "text": text}, event="turn")
            session.next_side = "against" if side == "for" else "for"
        # Round complete — pause and wait for the user (next/judge).
        yield _format_sse_event({}, event="paused")


@app.get("/debate/{session_id}/stream")
def debate_stream_session(session_id: str):
    """Initial stream for an open-ended debate: runs the first For+Against round,
    then pauses (closes the stream) waiting for /next or /verdict."""
    session = get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Unknown or expired session."}, status_code=404)
    # First round is always For then Against (matches classic mode's opening).
    return StreamingResponse(
        _stream_session_turns(session, ["for", "against"]),
        media_type="text/event-stream",
    )


@app.get("/debate/{session_id}/next")
def debate_next(session_id: str):
    """Stream one more For+Against round for an open-ended debate. GET (not POST)
    so the frontend can use EventSource — there's no body to send."""
    session = get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Unknown or expired session."}, status_code=404)
    if session.judged:
        return JSONResponse({"error": "This debate has already been judged."}, status_code=409)
    # Continue alternating from wherever the last round left off.
    sides = [session.next_side, "against" if session.next_side == "for" else "for"]
    return StreamingResponse(
        _stream_session_turns(session, sides),
        media_type="text/event-stream",
    )


@app.post("/debate/{session_id}/verdict")
def debate_verdict(session_id: str):
    """User said 'judge it now'. Run the moderator on the accumulated transcript
    and return the verdict. Marks the session judged so further /next calls 409."""
    session = get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Unknown or expired session."}, status_code=404)
    with session.lock:
        if session.judged:
            return JSONResponse({"error": "This debate has already been judged."}, status_code=409)
        if not session.transcript:
            # Nothing to judge yet — friendly message, no moderator call.
            return {"speaker": "System", "text": "No debate to judge yet — let at least one round play first."}
        try:
            verdict = run_verdict(session.topic, session.transcript)
        except Exception:
            return JSONResponse(
                {"speaker": "System", "text": "The verdict couldn't be generated. Please try again in a moment."},
                status_code=500,
            )
        session.transcript.append(f"Moderator: {verdict}")
        session.judged = True
        return {"speaker": "Moderator — Final Verdict", "text": verdict}


@app.delete("/debate/{session_id}")
def debate_stop(session_id: str):
    """User aborted. Drop the session so it stops consuming memory."""
    drop_session(session_id)
    return {"ok": True}


# --- Classic mode (unchanged, Spec 02 §5 boundary intact) ---------------------

@app.get("/debate")
def debate_stream(
    topic: str = Query(default="", description="The debate topic"),
    model_for: str | None = Query(default=None, description="Model id for the FOR debater (default if omitted)"),
    model_against: str | None = Query(default=None, description="Model id for the AGAINST debater (default if omitted)"),
):
    """Stream a debate turn-by-turn as SSE.

    Per Spec 03 §3, the topic comes in as a query param (EventSource only supports
    GET). Each turn arrives as `data: {"speaker":..., "text":...}`; the stream ends
    with `event: done`.

    model_for / model_against (v1.1): optional model ids for the per-side selection
    feature. Passed straight to run_debate; validation lives there (keeps the
    Spec 02 §5 boundary intact — transport passes values through, orchestration
    validates). Empty string is normalized to None so the default path is identical
    whether the param is absent or blank.

    Input validation (Spec 05 §1):
    - empty/whitespace topic → single System turn, then done (no agent calls)
    - overlong topic → truncated to MAX_TOPIC_LENGTH (friendlier than rejecting)
    """
    # Empty-string query params (e.g. ?model_for=) normalize to None = use default.
    model_for = model_for or None
    model_against = model_against or None

    cleaned = topic.strip()
    if not cleaned:
        # Friendly inline message, no agents called (Spec 05 §1 row 1).
        def _empty() -> Iterator[str]:
            yield _format_sse_event(
                {"speaker": "System", "text": "Please enter a topic to start the debate."}
            )
            yield _format_sse_event({}, event="done")

        return StreamingResponse(_empty(), media_type="text/event-stream")

    # Truncate overlong topics (Spec 05 §1 row 2 — truncation is the friendlier default).
    if len(cleaned) > MAX_TOPIC_LENGTH:
        cleaned = cleaned[:MAX_TOPIC_LENGTH]

    def event_generator() -> Iterator[str]:
        # Spec 05 §2: wrap the whole stream so a mid-stream exception still sends a
        # final `event: done` rather than leaving the browser's EventSource hanging.
        try:
            for speaker, text in run_debate(cleaned, model_for, model_against):
                yield _format_sse_event({"speaker": speaker, "text": text})
        except Exception:
            # run_debate already converts per-turn LLM failures to a System turn and
            # returns cleanly, so an exception escaping to here is unexpected (e.g.
            # import-time or config failure). Don't leak a traceback to the browser.
            yield _format_sse_event(
                {
                    "speaker": "System",
                    "text": "The debate hit a temporary error and couldn't continue. "
                    "Please try again in a moment.",
                }
            )
        finally:
            yield _format_sse_event({}, event="done")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Static frontend mount — MUST come after /debate so it doesn't shadow the route.
# html=True makes GET / serve index.html (Spec 04 §4).
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
