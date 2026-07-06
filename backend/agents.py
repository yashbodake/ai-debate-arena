"""The three debate agents. See specs/01-agents-and-crew.md for the source of truth.

All three share one LLM built in config.get_llm() (Spec 01 §0). The For/Against
agents are deliberately near-symmetric — only the stance differs — so neither side
sounds smarter than the other through prompt bias (Spec 01 §2 note).
"""

from __future__ import annotations

from crewai import Agent

from .config import get_llm


def _debater(role: str, goal: str, backstory: str) -> Agent:
    """Construct a debater agent wired to the shared LLM, delegation disabled.

    allow_delegation=False is mandatory per AGENT.md §2 point 8 — the moderator does
    NOT autonomously delegate, turn order is fixed in code (Spec 02).
    """
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=get_llm(),
        allow_delegation=False,
        verbose=True,
    )


# Shared debater persona — the only thing that should differ between For and Against
# is the stance. Spec 01 §1 and §2 spell this out and explicitly warn against making
# one side's backstory stronger than the other.
_DEBATER_BACKSTORY = (
    "You are a sharp, persuasive debater. You argue with conviction but stay "
    "respectful and factual — no strawmanning, no personal attacks. You build on "
    "what's already been said rather than repeating your own earlier points. Keep "
    "each turn to 3-5 sentences maximum; this is a live debate, not an essay."
)


def debater_for() -> Agent:
    """The FOR-side debater."""
    return _debater(
        role="Debater arguing FOR the topic",
        goal=(
            "Construct the strongest possible case in favor of the given topic, "
            "using clear logic, concrete examples, and direct rebuttals to the "
            "opposing side's prior points (if any exist yet in context)."
        ),
        backstory=_DEBATER_BACKSTORY,
    )


def debater_against() -> Agent:
    """The AGAINST-side debater. Near-symmetric with FOR — only the stance differs."""
    return _debater(
        role="Debater arguing AGAINST the topic",
        goal=(
            "Construct the strongest possible case against the given topic, "
            "directly rebutting the FOR side's most recent point where relevant, "
            "using clear logic and concrete examples."
        ),
        backstory=_DEBATER_BACKSTORY,
    )


def moderator() -> Agent:
    """The Moderator/Judge. In v1 this agent only delivers the closing verdict —
    no live interjections (Spec 01 §3, Spec 02 §2)."""
    return Agent(
        role="Debate Moderator and Judge",
        goal=(
            "Keep the debate fair and on-topic, then deliver a final, reasoned "
            "verdict on which side made the stronger case — based on argument "
            "quality and logic, not on which side you personally agree with."
        ),
        backstory=(
            "You are a neutral, experienced debate moderator. During the debate "
            "you do not interject (v1 has no live moderation, only a closing "
            "verdict — see Spec 02). When delivering the verdict: summarize the "
            "strongest point from each side in one sentence each, then declare a "
            "winner (or explicitly say it was a close/tied debate if genuinely "
            "balanced) with 2-3 sentences of reasoning. Never declare a winner "
            "based on topic sensitivity or personal preference — only argument "
            "quality."
        ),
        llm=get_llm(),
        allow_delegation=False,
        verbose=True,
    )
