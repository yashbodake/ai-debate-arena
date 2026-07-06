"""Headless smoke test: run one full debate on a sample topic, no web server.

This is the Phase 1 acceptance check from PROGRESS.md — verify the agent + LLM
wiring produces a debate. Now (Phase 2) it consumes the same run_debate() generator
that the FastAPI/SSE layer will use, so there's exactly one source of truth for the
orchestration logic (backend/crew.py).

Run:
    .venv/bin/python smoke_test.py

Exits 0 if a clean multi-turn debate is produced, non-zero otherwise.
"""

from __future__ import annotations

import sys
import time

from backend.crew import run_debate

SAMPLE_TOPIC = "Is remote work better than office work?"


def main() -> int:
    print(f"=== Smoke test: '{SAMPLE_TOPIC}' ===\n")
    start = time.monotonic()

    turn_count = 0
    for speaker, text in run_debate(SAMPLE_TOPIC):
        turn_count += 1
        print(f"--- Turn {turn_count}: {speaker} ---")
        print(f"{text}\n")

    elapsed = time.monotonic() - start
    print(f"=== Done in {elapsed:.1f}s — {turn_count} turns total ===")

    # A healthy debate is 5 turns (For/Against/For/Against/Moderator). A System
    # error turn means the LLM failed mid-stream — surface that as a test failure
    # rather than a silent pass.
    if turn_count < 2:
        print(f"!!! expected >=2 turns, got {turn_count}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — smoke test, want a clean failure message
        print(f"\n!!! SMOKE TEST FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
