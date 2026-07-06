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
from urllib.error import URLError
from urllib.request import Request, urlopen

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
def _default_llm() -> LLM:
    """The default shared LLM, built once and cached for the process lifetime.

    Cached so every agent and every per-turn Crew reuses the same instance across
    a debate (and across requests in a long-lived server). Construction is cheap,
    but sharing keeps token-usage accounting in one place.
    """
    return LLM(
        model=os.getenv("MODEL_NAME", DEFAULT_MODEL),
        base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        api_key=_required_env("OPENAI_API_KEY"),
    )


def get_llm(model_override: str | None = None) -> LLM:
    """Return an LLM instance for the given model.

    - model_override=None → the cached default LLM (the fast path used by the
      moderator and by any caller that doesn't care which model runs)
    - model_override="some-model-id" → a fresh, non-cached LLM for that specific
      model, using the same base_url + api_key as the default. Used by the per-side
      model-selection feature (v1.1): both debaters share one provider/key from
      .env, only the model id varies.
    """
    if model_override is None:
        return _default_llm()
    # Override path: bypass the cache so each distinct model gets its own instance.
    return LLM(
        model=model_override,
        base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        api_key=_required_env("OPENAI_API_KEY"),
    )


@lru_cache(maxsize=1)
def get_available_models() -> list[str]:
    """Fetch the list of model ids the deployer's provider exposes.

    Calls the provider's GET {OPENAI_BASE_URL}/models (the OpenAI-compatible
    standard endpoint). Used to populate the frontend dropdowns so the deployer
    never has to hardcode model names — the provider defines what's available.

    Returns [] on any error (network, auth, malformed response) rather than
    raising; the frontend treats an empty list as "hide the dropdowns, default
    only". Caching for the process lifetime is fine — provider model lists change
    very rarely and this avoids hitting the provider on every page load.
    """
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY")  # may be None locally before .env is set
    if not api_key:
        return []
    req = Request(
        f"{base_url}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            # Some providers' WAFs (e.g. Cerebras) 403 the default Python-urllib
            # User-Agent as bot-like. Send an identifying UA instead.
            "User-Agent": "ai-debate-arena/1.0",
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(ids)
    except (URLError, OSError, ValueError, KeyError, TimeoutError):
        return []


def is_valid_model(name: str | None) -> bool:
    """True if `name` is None (use default) or in the provider's model list.

    None is always valid (it means "use MODEL_NAME from .env"). A non-None name
    is checked against the provider's actual model list so we fail fast on a
    bogus id instead of waiting for a 404 mid-stream from the provider.
    """
    if name is None:
        return True
    return name in get_available_models()


# --- Debate orchestration constants (Spec 02 §2) ---
# 2 rounds each side + 1 moderator verdict = 5 turns. Kept here, not hardcoded in
# crew.py, so it can be tuned without touching orchestration logic.
NUM_DEBATE_ROUNDS = 2

# Input limits (Spec 05 §1). Truncation is the friendlier default over rejection.
MAX_TOPIC_LENGTH = 300
