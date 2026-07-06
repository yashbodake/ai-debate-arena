"""Configuration: env loading, the shared LLM, and project constants.

Single source of truth for anything the deployer configures. Per Spec 01 §0, one
shared crewai.LLM is built here from env vars and passed to every agent — agents
never construct their own LLM.

CrewAI 1.15.1+ has no LiteLLM dependency. The model id is passed bare (no provider
prefix) and the endpoint is set via base_url=. Groq is the documented default but any
OpenAI-compatible provider works by editing .env.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from crewai import LLM

# Load .env if present (local dev). On HF Spaces the env vars come from Repository
# secrets and load_dotenv is a no-op (no .env file shipped in the image).
load_dotenv()

# --- LLM provider (OpenAI-compatible) ---
# Documented default = Groq free tier. See .env.example for swap examples.
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


def _required_env(name: str) -> str:
    """Read a required env var, raising a clear error if missing.

    OPENAI_BASE_URL and MODEL_NAME have documented defaults, so only the key is
    truly required — but we still validate it loudly rather than letting a None
    leak into the LLM call and surface as an opaque 401 far away.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required env var {name}. "
            "Copy .env.example to .env and fill in your provider key."
        )
    return value


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    """Build the one shared LLM used by all agents.

    Cached so every agent and every per-turn Crew reuses the same instance across
    a debate (and across requests in a long-lived server). Construction is cheap,
    but sharing keeps token-usage accounting in one place.
    """
    model = os.getenv("MODEL_NAME", DEFAULT_MODEL)
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    api_key = _required_env("OPENAI_API_KEY")
    return LLM(model=model, base_url=base_url, api_key=api_key)


# --- Debate orchestration constants (Spec 02 §2) ---
# 2 rounds each side + 1 moderator verdict = 5 turns. Kept here, not hardcoded in
# crew.py, so it can be tuned without touching orchestration logic.
NUM_DEBATE_ROUNDS = 2

# Input limits (Spec 05 §1). Truncation is the friendlier default over rejection.
MAX_TOPIC_LENGTH = 300
