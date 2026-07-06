# Spec 02 — Orchestration & Turn Flow

This is the most important spec in the project. Get this wrong and the "streaming debate"
experience collapses into a slow blocking call. Read AGENT.md §2 point 7 and 8 first.

---

## 1. Why Not a Single Crew.kickoff()

A naive implementation defines one Crew with all 5 turns as pre-built Tasks and calls
`crew.kickoff()` once. **Do not do this.** It blocks until the entire debate is done,
which breaks the streaming requirement and gives the user a long silent wait.

Instead: **one Crew execution PER TURN**, called sequentially from a Python generator
that yields after each turn completes. This is what makes streaming to Gradio possible.

---

## 2. Fixed Turn Sequence (v1)

```
Turn 1: Debater For       (opening statement)
Turn 2: Debater Against   (opening statement + rebuttal of Turn 1)
Turn 3: Debater For       (rebuttal of Turn 2)
Turn 4: Debater Against   (rebuttal of Turn 3)
Turn 5: Moderator         (final verdict, sees full transcript)
```

5 turns total. This is deliberately short — enough to feel like a real debate without
burning excessive LLM requests/tokens per single user session (see §4).

Turn count is a constant in `config.py` (`NUM_DEBATE_ROUNDS = 2`), not hardcoded inline,
so it can be tuned later without touching orchestration logic.

---

## 3. Orchestration Logic (Reference Implementation Shape)

```python
def run_debate(topic: str):
    """
    Generator: yields (speaker_label, text) tuples one at a time.
    Called by the Gradio layer to stream output as it's generated.
    """
    transcript = []  # list of "Speaker: text" strings, used as context for later turns

    turn_plan = [
        ("Debater For", debater_for_agent),
        ("Debater Against", debater_against_agent),
        ("Debater For", debater_for_agent),
        ("Debater Against", debater_against_agent),
    ]

    for i, (label, agent) in enumerate(turn_plan, start=1):
        task = make_debate_task(agent, topic, transcript, turn_number=i)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()
        text = str(result)
        transcript.append(f"{label}: {text}")
        yield (label, text)

    # Final turn: moderator verdict, sees everything
    verdict_task = make_verdict_task(moderator_agent, topic, transcript)
    verdict_crew = Crew(agents=[moderator_agent], tasks=[verdict_task], process=Process.sequential, verbose=False)
    verdict_result = verdict_crew.kickoff()
    transcript.append(f"Moderator: {verdict_result}")
    yield ("Moderator — Final Verdict", str(verdict_result))
```

Key points an implementing agent must not deviate from without logging it in PROGRESS.md:
- Each loop iteration creates a **fresh Crew** with a single agent and single task.
  This is intentional — it keeps each Groq call isolated and makes per-turn latency
  visible/debuggable, and avoids CrewAI's own multi-agent delegation overhead for
  what is actually a simple fixed-order sequence.
- `transcript` is plain text accumulation, not CrewAI "memory." Keep it simple.
- Process type is `Process.sequential` for each single-task crew (technically process
  type barely matters with 1 task, but keep it explicit for clarity/future-proofing).

---

## 4. Token / Request Budget Check (Provider-Agnostic)

5 turns × 1 LLM call each = 5 requests per debate. Each request's prompt grows as the
transcript grows (turn 5's moderator prompt includes all 4 prior turns). Before Phase 2
is marked done, manually verify against the **deployer's chosen provider** (see
AGENT.md §2 point 2 and Spec 01 §0 — the deployer sets `OPENAI_API_BASE` / `MODEL_NAME`):
- Total tokens for the largest single request (moderator verdict) stays comfortably
  under the chosen provider's context window and per-minute rate limits
- 5 sequential requests complete in a reasonable total wall-clock time for a live demo
  (target: under ~20-30 seconds total, adjust expectations based on actual provider
  latency at build time — always confirm empirically against the real provider, don't
  assume). With the documented Groq default this is generally fast; a local Ollama model
  on CPU will be slower and may need the turn count reduced.

---

## 5. Interface Contract With Backend/Frontend (Spec 03, 04)

`run_debate(topic: str)` is a **generator** and must have **zero FastAPI/HTTP imports or
knowledge** of how it's transported. This keeps the debate logic testable headlessly
(see Phase 1 smoke test in PROGRESS.md) independent of the web layer.

The FastAPI layer (`backend/main.py`) is responsible for:
1. Accepting the topic via an SSE endpoint (see Spec 03 §3 for the exact route contract)
2. Iterating `run_debate(topic)` and formatting each `(speaker, text)` tuple as an
   SSE `data:` event
3. Sending a final `event: done` message so the frontend knows to stop listening

Reference wiring (full detail lives in Spec 03/04, this is just the boundary contract):

```python
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from crew import run_debate

app = FastAPI()

@app.get("/debate")
def debate_stream(topic: str):
    def event_generator():
        for speaker, text in run_debate(topic):
            payload = json.dumps({"speaker": speaker, "text": text})
            yield f"data: {payload}\n\n"
        yield "event: done\ndata: {}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

Keep `run_debate` free of any `json.dumps`/SSE-formatting logic — that belongs entirely
in `main.py`, not in `crew.py`.
