"""In-memory session store for open-ended debates (v1.3).

Open-ended mode needs state shared across multiple HTTP requests: one connection
streams turns, a separate one triggers the verdict. We hold that state here, keyed
by an opaque session id.

NOT persistence — this is process-local memory. A server restart wipes everything,
which is fine per AGENT.md §2.6 ("debates are ephemeral"). A 30-min TTL prunes
abandoned sessions so a forgotten browser tab can't leak memory forever.

Concurrency: the dict itself is guarded by a module-level lock for insert/lookup.
Each Session has its own lock so two requests on the SAME session (e.g. the verdict
POST landing while a turn-stream is mid-flight) serialize cleanly instead of
corrupting the transcript.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

# Hard cap on turns before the open-ended mode auto-triggers the verdict.
# Prevents a forgotten tab from burning the deployer's provider quota forever.
MAX_DEBATE_TURNS = 20

# Sessions older than this (since last activity) get pruned on the next creation.
_SESSION_TTL_SECONDS = 30 * 60


@dataclass
class Session:
    """One open-ended debate's mutable state."""

    session_id: str
    topic: str
    model_for: str | None
    model_against: str | None
    transcript: list[str] = field(default_factory=list)
    # Alternates For / Against. "for" starts — matches classic mode's turn 1.
    next_side: str = "for"
    # Set true once the user judges; the turn loop checks it and stops yielding.
    judged: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)


# Module-level store. Single uvicorn worker = single dict = consistent.
# (HF Spaces free CPU tier is single-instance; this assumption holds there.)
_sessions: dict[str, Session] = {}
_store_lock = threading.Lock()


def _prune_expired() -> None:
    """Drop sessions older than the TTL. Called under _store_lock."""
    now = time.time()
    expired = [
        sid for sid, s in _sessions.items()
        if now - s.last_active > _SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del _sessions[sid]


def create_session(topic: str, model_for: str | None, model_against: str | None) -> Session:
    """Create a new session and prune any expired ones. Returns the new session."""
    with _store_lock:
        _prune_expired()
        session = Session(
            session_id=uuid.uuid4().hex,
            topic=topic,
            model_for=model_for,
            model_against=model_against,
        )
        _sessions[session.session_id] = session
        return session


def get_session(session_id: str) -> Session | None:
    """Look up a session, refreshing its last_active timestamp if found."""
    with _store_lock:
        s = _sessions.get(session_id)
        if s is not None:
            s.last_active = time.time()
        return s


def drop_session(session_id: str) -> None:
    """Remove a session (used when the user aborts). No-op if already gone."""
    with _store_lock:
        _sessions.pop(session_id, None)
