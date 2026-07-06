"""Headless smoke test: run one full debate on a sample topic, no web server.

This is the Phase 1 acceptance check from PROGRESS.md — verify the agent + LLM
wiring actually produces a debate before building the FastAPI/SSE layer (Phase 2+)
on top of it. It intentionally duplicates a minimal slice of the Spec 02 §3
orchestration inline rather than importing a not-yet-written crew.run_debate(); the
real generator graduates into backend/crew.py during Phase 2.

Run:
    .venv/bin/python smoke_test.py

Exits 0 on a clean 5-turn debate, non-zero otherwise.
"""

from __future__ import annotations

import sys
import time

from crewai import Crew, Process, Task

from backend.agents import debater_against, debater_for, moderator
from backend.config import NUM_DEBATE_ROUNDS

SAMPLE_TOPIC = "Is remote work better than office work?"


def make_debate_task(agent, topic: str, transcript: list[str], turn_number: int) -> Task:
    """Build a single debate-turn Task. Mirrors Spec 01 §4's shape exactly."""
    context_block = "\n".join(transcript) if transcript else "(This is the opening turn.)"
    return Task(
        description=(
            f"Debate topic: {topic}\n\n"
            f"Transcript so far:\n{context_block}\n\n"
            f"Give your turn now (turn #{turn_number})."
        ),
        agent=agent,
        expected_output="A single debate turn, 3-5 sentences, no meta-commentary.",
    )


def make_verdict_task(judge, topic: str, transcript: list[str]) -> Task:
    """The moderator's structurally-different final task (Spec 02 §3)."""
    return Task(
        description=(
            f"Debate topic: {topic}\n\n"
            f"Full transcript:\n{chr(10).join(transcript)}\n\n"
            "Deliver your final verdict now."
        ),
        agent=judge,
        expected_output=(
            "One-sentence summary of each side's strongest point, then a winner "
            "(or explicit tie) with 2-3 sentences of reasoning."
        ),
    )


def run_one_turn(agent, task) -> str:
    """Run a single-agent, single-task crew and return its text output.

    Per Spec 02 §3: each iteration creates a fresh Crew with one agent and one task.
    This keeps each LLM call isolated and per-turn latency visible.
    """
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    result = crew.kickoff()
    return str(result).strip()


def main() -> int:
    print(f"=== Smoke test: '{SAMPLE_TOPIC}' ===\n")
    start = time.monotonic()

    # Instantiate agents once; reused across turns (the shared LLM inside them is
    # the same instance via config.get_llm()'s lru_cache).
    for_agent = debater_for()
    against_agent = debater_against()
    judge = moderator()

    transcript: list[str] = []

    # Fixed turn sequence per Spec 02 §2: For, Against, For, Against, ...
    turn_plan = []
    for _ in range(NUM_DEBATE_ROUNDS):
        turn_plan.append(("Debater For", for_agent))
        turn_plan.append(("Debater Against", against_agent))

    for i, (label, agent) in enumerate(turn_plan, start=1):
        print(f"--- Turn {i}/{len(turn_plan) + 1}: {label} ---")
        task = make_debate_task(agent, SAMPLE_TOPIC, transcript, turn_number=i)
        text = run_one_turn(agent, task)
        transcript.append(f"{label}: {text}")
        print(f"{text}\n")

    # Final turn: moderator verdict, sees the full transcript.
    print(f"--- Turn {len(turn_plan) + 1}/{len(turn_plan) + 1}: Moderator — Final Verdict ---")
    verdict = run_one_turn(judge, make_verdict_task(judge, SAMPLE_TOPIC, transcript))
    transcript.append(f"Moderator: {verdict}")
    print(f"{verdict}\n")

    elapsed = time.monotonic() - start
    print(f"=== Done in {elapsed:.1f}s — {len(turn_plan) + 1} turns total ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — smoke test, want a clean failure message
        print(f"\n!!! SMOKE TEST FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
