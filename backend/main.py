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
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import MAX_TOPIC_LENGTH
from .crew import run_debate

app = FastAPI(title="AI Debate Arena")

# Resolve frontend/ relative to repo root (this file is at backend/main.py).
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _format_sse_event(data: dict, event: str | None = None) -> str:
    """Format one SSE message. Per the SSE spec, each event is terminated by \n\n."""
    payload = json.dumps(data)
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


@app.get("/debate")
def debate_stream(topic: str = Query(default="", description="The debate topic")):
    """Stream a debate turn-by-turn as SSE.

    Per Spec 03 §3, the topic comes in as a query param (EventSource only supports
    GET). Each turn arrives as `data: {"speaker":..., "text":...}`; the stream ends
    with `event: done`.

    Input validation (Spec 05 §1):
    - empty/whitespace topic → single System turn, then done (no agent calls)
    - overlong topic → truncated to MAX_TOPIC_LENGTH (friendlier than rejecting)
    """
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
            for speaker, text in run_debate(cleaned):
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
