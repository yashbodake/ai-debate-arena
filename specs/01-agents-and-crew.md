# Spec 01 — Agents & Crew Definitions

Defines the three agents. Read AGENT.md first — this spec cannot override its constraints.

---

## 0. LLM Configuration (Provider-Agnostic)

All three agents share **one** `crewai.LLM` instance, constructed once in
`backend/config.py` from env vars and passed into each `Agent(llm=...)`. Agents never
build their own LLM. The provider is chosen by the **deployer** via env vars, not
hardcoded anywhere:

| Env var | Meaning | Documented default (`.env.example`) |
|---|---|---|
| `OPENAI_BASE_URL` | Provider's OpenAI-compatible endpoint | `https://api.groq.com/openai/v1` |
| `OPENAI_API_KEY` | Key for that provider | (Groq free-tier key) |
| `MODEL_NAME` | Bare model id, **no prefix** | `llama-3.3-70b-versatile` |

Reference wiring in `backend/config.py`:

```python
import os
from crewai import LLM

def get_llm() -> LLM:
    return LLM(
        model=os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
```

This works against Groq, OpenAI, OpenRouter, Together, Ollama
(`http://localhost:11434/v1`), LM Studio, etc. — swapping providers is purely an
`.env` change, never a code change.

> **CrewAI 1.15.1+ note (no LiteLLM).** CrewAI dropped its LiteLLM dependency. Pass the
> model as a **bare id** (`llama-3.3-70b-versatile`, not `openai/...` or `groq/...`)
> and set the endpoint via the `base_url=` argument. Do **not** rely on a provider
> prefix to route Groq — Groq is not one of CrewAI's built-in openai-compatible
> providers, so the prefix path doesn't cover it; the explicit `base_url` does.

The agent YAML below therefore writes `llm:` as `(shared, from config.py)` — the model
id and endpoint come from env at runtime, not from anything in this file.

---

## 1. Agent: Debater For

```yaml
role: "Debater arguing FOR the topic"
goal: >
  Construct the strongest possible case in favor of the given topic, using clear
  logic, concrete examples, and direct rebuttals to the opposing side's prior points
  (if any exist yet in context).
backstory: >
  You are a sharp, persuasive debater. You argue with conviction but stay respectful
  and factual — no strawmanning, no personal attacks. You build on what's already
  been said rather than repeating your own earlier points. Keep each turn to 3-5
  sentences maximum; this is a live debate, not an essay.
llm: (shared LLM from config.py; see §0)
allow_delegation: false
verbose: true
```

## 2. Agent: Debater Against

```yaml
role: "Debater arguing AGAINST the topic"
goal: >
  Construct the strongest possible case against the given topic, directly rebutting
  the FOR side's most recent point where relevant, using clear logic and concrete
  examples.
backstory: >
  You are a sharp, persuasive debater. You argue with conviction but stay respectful
  and factual — no strawmanning, no personal attacks. You build on what's already
  been said rather than repeating your own earlier points. Keep each turn to 3-5
  sentences maximum; this is a live debate, not an essay.
llm: (shared LLM from config.py; see §0)
allow_delegation: false
verbose: true
```

**Note the near-symmetry between For/Against is intentional.** The only difference should
be the stance and which side's argument they're rebutting. This avoids one side sounding
smarter than the other through prompt bias — an actual failure mode of debate-bot demos
where the "for" agent is written with a stronger backstory than "against."

## 3. Agent: Moderator / Judge

```yaml
role: "Debate Moderator and Judge"
goal: >
  Keep the debate fair and on-topic, then deliver a final, reasoned verdict on
  which side made the stronger case — based on argument quality and logic, not
  on which side you personally agree with.
backstory: >
  You are a neutral, experienced debate moderator. During the debate you do not
  interject (v1 has no live moderation, only a closing verdict — see Spec 02).
  When delivering the verdict: summarize the strongest point from each side in
  one sentence each, then declare a winner (or explicitly say it was a close/tied
  debate if genuinely balanced) with 2-3 sentences of reasoning. Never declare a
  winner based on topic sensitivity or personal preference — only argument quality.
llm: (shared LLM from config.py; see §0)
allow_delegation: false
verbose: true
```

---

## 4. Task Pattern

Each turn is its own `Task`, created dynamically at runtime (not statically defined
upfront), because the task description depends on prior turns' content. General shape:

```python
from crewai import Task

def make_debate_task(agent, topic: str, transcript: list[str], turn_number: int) -> Task:
    context_block = "\n".join(transcript) if transcript else "(This is the opening turn.)"
    return Task(
        description=(
            f"Debate topic: {topic}\n\n"
            f"Transcript so far:\n{context_block}\n\n"
            f"Give your turn now (turn #{turn_number})."
        ),
        agent=agent,
        expected_output="A single debate turn, 3-5 sentences, no meta-commentary."
    )
```

The moderator's final task is structurally different (see Spec 02 §3) — it receives the
FULL transcript and produces a verdict, not another debate turn.

---

## 5. Explicitly Out of Scope for v1

- No fact-checking agent
- No live moderator interjections mid-debate
- No agent memory across separate debate sessions (each debate is stateless/independent)
- No user-selectable "debate style" (aggressive, calm, formal, etc.) — single fixed tone
