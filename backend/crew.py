"""Debate orchestration: the run_debate generator and its task builders.

This module has ZERO knowledge of FastAPI, HTTP, SSE, or json — per Spec 02 §5, that
keeps the debate logic testable headlessly (smoke_test.py imports it directly) and
independent of the web layer. The FastAPI layer (main.py) is responsible for all
transport/format concerns.

Design (Spec 02 §1-§3): one Crew execution PER TURN, called sequentially from a
generator that yields after each turn completes. Do NOT collapse this into a single
crew.kickoff() with all 5 tasks — that blocks until the whole debate finishes and
breaks the streaming requirement (AGENT.md §2 point 9).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

from crewai import Crew, Process, Task

from .agents import debater_against, debater_for, moderator
from .config import NUM_DEBATE_ROUNDS

# A turn is a (speaker_label, text) tuple. The label is what the UI displays and
# what the moderator's prompt uses as context; the text is the agent's output.
Turn = tuple[str, str]


def make_debate_task(agent, topic: str, transcript: list[str], turn_number: int) -> Task:
    """Build a single debate-turn Task. Mirrors Spec 01 §4's reference shape."""
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
    """The moderator's structurally-different final task (Spec 02 §3): receives the
    FULL transcript and produces a verdict, not another debate turn."""
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


def _run_one_turn(agent, task) -> str:
    """Run a single-agent, single-task crew and return its text output.

    Per Spec 02 §3: each iteration creates a fresh Crew with one agent + one task.
    This isolates each LLM call and makes per-turn latency visible/debuggable.
    """
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    result = crew.kickoff()
    return str(result).strip()


def run_debate(topic: str) -> Iterator[Turn]:
    """Generator: yields (speaker_label, text) tuples, one per turn.

    Fixed 5-turn sequence per Spec 02 §2: For → Against → For → Against → Moderator
    verdict. The transcript accumulates plain-text "Speaker: text" strings that each
    later turn's agent sees as context (Spec 02 §3 key points — plain text, not
    CrewAI "memory").

    Error handling per Spec 05 §2: a mid-stream LLM failure yields a friendly System
    message and stops the generator — does NOT crash, does NOT leak a stack trace to
    the caller.
    """
    # Instantiate agents once; the shared LLM inside each is the same instance via
    # config.get_llm()'s lru_cache.
    for_agent = debater_for()
    against_agent = debater_against()
    judge = moderator()

    transcript: list[str] = []

    # Fixed turn plan: For, Against, For, Against, ... (NUM_DEBATE_ROUNDS repetitions)
    turn_plan: list[tuple[str, Callable]] = []
    for _ in range(NUM_DEBATE_ROUNDS):
        turn_plan.append(("Debater For", for_agent))
        turn_plan.append(("Debater Against", against_agent))

    for i, (label, agent_factory) in enumerate(turn_plan, start=1):
        try:
            task = make_debate_task(agent_factory, topic, transcript, turn_number=i)
            text = _run_one_turn(agent_factory, task)
        except Exception:
            # Spec 05 §2: friendly System turn, then stop. Don't attempt subsequent
            # turns on a broken state, and don't let the raw exception reach the UI.
            yield (
                "System",
                "The debate hit a temporary error and couldn't continue. "
                "Please try again in a moment.",
            )
            return
        transcript.append(f"{label}: {text}")
        yield (label, text)

    # Final turn: moderator verdict, sees the full transcript.
    try:
        verdict = _run_one_turn(judge, make_verdict_task(judge, topic, transcript))
    except Exception:
        yield (
            "System",
            "The debate hit a temporary error and couldn't continue. "
            "Please try again in a moment.",
        )
        return
    transcript.append(f"Moderator: {verdict}")
    yield ("Moderator — Final Verdict", verdict)
