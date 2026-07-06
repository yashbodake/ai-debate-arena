# Spec 05 — Error Handling & Limits

---

## 1. Input Validation

| Case | Handling |
|---|---|
| Empty/whitespace-only topic | Show inline message "Please enter a topic to start the debate." Do not call any agent. |
| Extremely long topic (e.g. >500 chars) | Truncate to a reasonable length (e.g. 300 chars) before passing to agents, or reject with a message asking for a shorter topic. Pick one approach and document the choice in PROGRESS.md — truncation is the friendlier default. |
| Topic that's just gibberish/random chars | No special handling needed — let the agents attempt it naturally; LLMs handle this reasonably on their own. |

## 2. LLM API Failures

Wrap each `crew.kickoff()` call in a try/except. On failure (rate limit, timeout, network
error, bad API key, unknown model name — i.e. anything raised by the underlying
OpenAI-compatible provider the deployer configured via `OPENAI_BASE_URL` /
`OPENAI_API_KEY` / `MODEL_NAME`):
- Catch the exception at the orchestration layer (`run_debate` generator)
- Yield a clear error message as that turn's "text" instead of crashing the generator,
  e.g.: `("System", "The debate hit a temporary error and couldn't continue. Please try again in a moment.")`
- Stop the generator after yielding the error — don't attempt subsequent turns on a
  broken state
- The FastAPI SSE layer (`main.py`) should also wrap its event loop in a try/except so
  a mid-stream exception sends a final `event: done` rather than leaving the browser's
  `EventSource` hanging indefinitely
- Do not let a raw stack trace reach the frontend — the browser should only ever see
  the friendly `{"speaker": "System", "text": "..."}` payload, never a 500 with a traceback

Reference pattern:

```python
try:
    result = crew.kickoff()
except Exception as e:
    yield ("System", "The debate hit a temporary error and couldn't continue. Please try again in a moment.")
    return
```

## 3. Unsafe/Harmful Topic Guardrails

This app lets users type ANY topic, which means it could be pointed at genuinely harmful
subjects (e.g. asking agents to "debate" something that normalizes violence, hate, or
similar). Handling approach for v1:

- **Do not build a custom safety classifier from scratch** — that's out of scope and
  unreliable to DIY well.
- **Rely primarily on the underlying LLM's own refusal behavior.** Groq-hosted models
  generally refuse clearly harmful requests on their own. If an agent's response comes
  back as a refusal/declining message, just display it as that agent's turn rather than
  trying to detect and intercept it — don't build fragile keyword-blocklist logic.
- If time allows in a later phase, a lightweight pre-check (e.g. a short LLM call asking
  "is this topic safe to debate publicly? yes/no") could be added as a v2 improvement,
  but this is explicitly NOT required for v1 completion per AGENT.md's Definition of Done.

## 4. Concurrent Users

Free HF CPU Spaces are single-instance. If two users submit debates simultaneously,
FastAPI/uvicorn can handle multiple SSE connections concurrently (async), but both
debates will be making LLM API calls at the same time, competing for the same
provider rate limit (whether that's the Groq free tier, an OpenAI quota, or a local
Ollama instance's capacity — all depends on what the deployer configured).
- No special queuing logic is required for v1 — let both run concurrently and rely on
  the LLM failure handling in §2 if a rate limit is hit under simultaneous load.
- If this proves to be a real problem in testing (not just theoretical), a simple
  in-memory semaphore limiting to N concurrent debates could be added as a v2 fix —
  not required for v1 completion.

## 5. Explicitly Out of Scope for v1

- No CAPTCHA/rate-limiting per user (free tier + queue is sufficient protection against
  casual abuse for a demo project)
- No content moderation API integration (e.g. OpenAI moderation endpoint) — relying on
  underlying LLM refusal behavior only, per §3
- No logging/analytics of what topics users submit (also keeps this GDPR-simple since
  there's no data retention at all, consistent with AGENT.md §2 point 5)
