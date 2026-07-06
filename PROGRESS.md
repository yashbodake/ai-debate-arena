# PROGRESS.md — AI Debate Arena

Tracks phase-by-phase progress. Check items off as completed. Log any deviation from
spec immediately under the relevant phase's "Deviations" subsection — do not wait until
the end.

---

## Phase 0 — Setup

- [x] Repo restructured to AGENT.md §4 layout (docs at root, specs in `specs/`)
- [x] `git init` done (baseline commit: docs + Phase 0 config)
- [x] `.gitignore` includes `.env` and `.venv/`
- [x] `requirements.txt`, `.env.example` written
- [x] Python 3.13 environment created via **uv** (`uv venv --python 3.13` → `.venv/`,
      uv-managed CPython 3.13.14). uv hard-links from a global cache so multiple
      projects don't bloat disk — adopted as the standard for all projects.
- [x] `crewai` 1.15.1, `fastapi`, `uvicorn[standard]`, `python-dotenv` installed
      (`uv pip install -r requirements.txt`). Imports verified clean.
- [ ] LLM provider configured: copy `.env.example` → `.env`, fill in `OPENAI_API_KEY`
      (Groq key by default). Env vars are `OPENAI_BASE_URL`, `OPENAI_API_KEY`,
      `MODEL_NAME` — see Spec 01 §0. Never commit `.env`.

**Deviations:**
- **2026-07-06 — Python version.** AGENT.md §3 targets Python 3.11+. The build machine's
  system Python is 3.14.4, but CrewAI 1.15.1 requires `>=3.10, <3.14`. Resolved by using
  uv to install a managed CPython 3.13.14 into `.venv/` (no system Python change needed).
- **2026-07-06 — uv adopted for env management.** Original specs assumed plain
  `python -m venv` + `pip`. Switched to `uv` globally (all projects) to avoid disk
  bloat from per-project AI/ML dependency copies. `README.md` Quick Start updated.

---

## Phase 1 — Agents & Crew (Spec 01)

- [x] `Debater For` agent defined with role/goal/backstory (`backend/agents.py:debater_for`)
- [x] `Debater Against` agent defined with role/goal/backstory (`backend/agents.py:debater_against`)
- [x] `Moderator/Judge` agent defined with role/goal/backstory (`backend/agents.py:moderator`)
- [x] All three agents confirmed running against the deployer's chosen provider —
      shared `LLM` from `config.py` (built from `OPENAI_BASE_URL` / `OPENAI_API_KEY` /
      `MODEL_NAME`). Verified working against **Cerebras** (`zai-glm-4.7`), not Groq —
      see Deviations. Provider swap was .env-only, zero code change.
- [x] Manual smoke test PASSED: full 5-turn debate via `smoke_test.py` on the sample
      topic "Is remote work better than office work?" — For/Against/For/Against turns
      each rebutted prior points; moderator verdict summarized both sides and declared
      a reasoned tie. 72.3s total (~14s/turn).

**Deviations:**
- **2026-07-06 — Running on Cerebras, not Groq.** The documented default in
  `.env.example`/AGENT.md is Groq `llama-3.3-70b-versatile`, but the deployer (project
  owner) is running with a Cerebras API key against `zai-glm-4.7`. This is exactly the
  provider-agnostic path the design was built for — `.env` change only, no code change.
  Cerebras account has access to: `zai-glm-4.7`, `gpt-oss-120b`, `gemma-4-31b`.
- **2026-07-06 — Latency above Spec 02 §4 target.** 5 turns took 72.3s (~14s/turn)
  vs. the spec's ~20-30s total target (calibrated for Groq, which is faster than
  Cerebras for this model). Acceptable for a live demo (each turn streams as generated,
  so perceived wait is per-turn, not 72s upfront), but worth re-measuring on Groq
  before Phase 4 deployment.

---

## Phase 2 — Orchestration & Turn Flow (Spec 02)

- [x] Turn-order controller function written — `backend/crew.py:run_debate` is a
      generator over a fixed For/Against/For/Against/Moderator sequence (no delegation)
- [x] Each turn is a separate Task + fresh single-task Crew kickoff — yields after
      each turn completes (not one giant crew run)
- [x] Context passing confirmed — transcript accumulates as plain text and each
      later turn's prompt includes all prior turns; verified by the live test (turns
      explicitly rebut prior points)
- [x] Turn limit enforced — `NUM_DEBATE_ROUNDS=2` in `config.py` → 4 debate turns +
      1 verdict = 5 total
- [x] Per-turn streaming verified live via SSE — `curl /debate?topic=...` returns
      each turn as a separate `data:` event, ending with `event: done`. Server boots
      cleanly, empty/whitespace topics get a friendly System turn (no agent call),
      and a real 5-turn debate on "Should AI replace human teachers?" streamed
      correctly and terminated cleanly.
- [x] Boundary contract (Spec 02 §5) honored — `crew.py` has zero FastAPI/HTTP/json
      imports; all SSE formatting lives in `main.py`. `smoke_test.py` now consumes
      the same `run_debate()` generator (single source of truth).
- [x] Error handling (Spec 05 §2) wired — per-turn try/except yields a friendly
      System turn and stops; the SSE handler wraps the whole stream so a mid-stream
      exception still sends `event: done` rather than hanging the browser.
- [ ] Token/request budget: not yet re-measured (running on Cerebras, not Groq —
      see Phase 1 deviation). 5 requests/debate is structurally within any provider's
      limits; re-confirm latency + rate limits on the deployment provider in Phase 4.

**Deviations:** (none beyond the Phase 1 Cerebras-vs-Groq deviation, which carries
forward — latency still ~70s/5 turns)

---

## Phase 3 — Frontend (Spec 03)

- [x] `frontend/index.html` built: topic input, "Start Debate" button, transcript
      container — uses the exact IDs/hook points from Spec 03 §2
- [x] `script.js` wired to `/debate` SSE endpoint via `EventSource` (GET + query
      param per Spec 03 §3; EventSource's native GET-only constraint respected)
- [x] Turns rendered as they arrive via SSE `onmessage` events (not one final dump);
      `event: done` closes the stream, `onerror` shows a friendly "Connection lost"
- [x] GSAP entrance animations per speaker: For slides from left, Against from right,
      Moderator fades+scales (graceful no-op if GSAP CDN is blocked)
- [x] Basic styling: For=green, Against=red, Moderator=purple, System=amber —
      visually distinguished via `data-speaker` attribute + colored left border
- [x] Loading/status indicator: pulsing dot + "Debate in progress…" while streaming
- [ ] **Manual browser test pending (user-side).** Server-side verification done:
      all 3 files serve with correct content types (HTML/CSS/JS, HTTP 200), JS
      braces/parens balanced, and the speaker labels emitted by `crew.py` match the
      `data-speaker` CSS selectors + JS animation branches exactly. But a real
      browser test (open `http://localhost:7860`, submit a topic, watch turns
      animate in) is still needed to fully close Phase 3 — see Next action.

**Deviations:**
- **2026-07-06 — No UI/UX skill used.** Spec 03 mentions a UI/UX skill applied via
  the code-assistant for visual polish. None available in this environment, so
  styling was written directly as plain CSS (dark theme, per-speaker colors,
  responsive single breakpoint per Spec 03 §5). Functional and clean, but not
  "designed" in the polished sense — easy to iterate later.

---

## Feature v1.1 — Per-side model selection

Added after Phase 3. The end user can pick a different model for the For and
Against debaters via dropdowns (Moderator stays on the default `MODEL_NAME`).
Scope: one provider, one key (the deployer's) — only the model *id* varies per
side. Does NOT change the deployer-controls-the-key constraint (AGENT.md §2.2).

- [x] `config.get_llm(model_override=None)` — override builds a fresh LLM; None
      returns the cached default (backward compatible)
- [x] `config.get_available_models()` — calls provider's `GET /v1/models`,
      cached, returns `[]` on failure (frontend hides dropdowns)
- [x] `config.is_valid_model(name)` — None is always valid; otherwise checks
      against the provider's list
- [x] `agents.debater_for/against(model_override=None)` — moderator unchanged
- [x] `crew.run_debate(topic, model_for=None, model_against=None)` — validates
      overrides up front, yields friendly System turn on invalid id (no agent call)
- [x] `main.py`: `GET /models` route + `/debate` accepts `model_for`/`model_against`
      query params
- [x] `frontend`: two `<select>` dropdowns in a `<details>` wrapper (collapsed by
      default to preserve "just type a topic" UX), populated from `/models` on load,
      hidden if provider returns no models
- [x] E2E verified: For=`gemma-4-31b` + Against=`gpt-oss-120b` (two different models
      in one debate) → 5 turns streamed correctly. Invalid id → friendly System turn.

**Deviations:**
- **2026-07-06 — Cerebras WAF blocks `Python-urllib` User-Agent.** `GET /v1/models`
  via Python's urllib returned HTTP 403, while curl succeeded. Fixed by sending
  `User-Agent: ai-debate-arena/1.0` in `config.get_available_models()`. Other
  providers may not need this, but it's harmless and avoids a class of WAF issues.

---

## Phase 4 — Deployment (Spec 04)

- [x] HF Space created: **https://huggingface.co/spaces/yasbodake4/ai-debate-arena**
      (SDK = Docker, CPU basic free tier, public)
- [x] `Dockerfile` builds cleanly and listens on port 7860 — built and reached
      `RUNNING` in ~90s on first push, zero errors
- [x] `requirements.txt` pinned to exact versions (Spec 04 §5), installs cleanly
      in the HF Docker build
- [x] FastAPI serves both the `/debate` SSE endpoint and static frontend files —
      verified via curl against the live URL (`/`, `/style.css`, `/script.js`,
      `/models`, `/debate` all return correct content types + 200s)
- [x] Provider secrets added as HF Repository secrets (not hardcoded):
      `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME` — set to Cerebras values
- [x] **App confirmed working on the public Space URL** — real 5-turn debate on
      "Is remote work better than office work?" streamed correctly end-to-end,
      verdict declared "Winner: Debater For" with reasoning. Live URL:
      **https://yasbodake4-ai-debate-arena.hf.space**
- [ ] Cold-start behavior: not yet observed (Space just deployed). Free CPU Spaces
      sleep after inactivity — first request after sleep takes ~30s to wake.
      Frontend's `onerror` handler covers a dropped connection cleanly (Spec 03 §4).

**Deviations:**
- **2026-07-06 — Deployed via direct git push, not GitHub sync.** Spec 04 §8 step 2
  mentions connecting to GitHub; instead we cloned the HF Space repo and pushed
  directly. Same end result (HF builds from the Dockerfile); the GitHub repo
  remains the source of truth for code, HF is the deployment target.
- **2026-07-06 — HF account is `yasbodake4`, not `yashbodake`** (different from
  GitHub). Cosmetic, just noting so the URL isn't surprising.

---

## Phase 5 — Error Handling & Limits (Spec 05)

- [ ] Empty topic input handled gracefully (no crash, friendly message)
- [ ] Extremely long topic input truncated/rejected with message
- [ ] Groq rate-limit/timeout errors caught and shown as friendly UI message, not a stack trace
- [ ] Basic guardrail for clearly unsafe/harmful topics (see Spec 05 for exact approach)
- [ ] Concurrent-user behavior considered (what happens if 2 people submit at once on free tier)

**Deviations:** (none yet)

---

## Overall Status

**Current phase:** Phase 4 complete — LIVE on HF Spaces 🎉
**Live URL:** https://yasbodake4-ai-debate-arena.hf.space
**Blockers:** None
**Next action:** Phase 5 polish + rotate exposed secrets (Cerebras key, HF token)

### Logged deviation (pre-build, 2026-07-06): LLM provider made provider-agnostic

**What changed:** Originally AGENT.md §2 point 2 and §3 locked the LLM to Groq free tier
(`groq/llama-3.3-70b-versatile`). The user decided the app should support **any
OpenAI-compatible provider**, chosen by the deployer via three env vars. Groq remains
the documented default in `.env.example` so anyone can still run it for free out of the
box.

**Why:** Flexibility — a deployer can point at Groq / OpenAI / OpenRouter / Ollama /
LM Studio / etc. by editing `.env`, with zero code changes. Cost is the deployer's
responsibility; the app itself imposes no paid-API requirement.

**Note:** "Free hosting only" (AGENT.md §2 point 1) still holds — HF Spaces free CPU
tier is unchanged. Only the LLM-cost constraint is relaxed, and only to the extent the
*deployer* opts into a paid provider by their own env choice.

### Logged deviation (pre-build, 2026-07-06): CrewAI 1.15.1 has dropped LiteLLM

**What changed:** The initial provider-agnostic design (and the first revision of these
specs) assumed CrewAI uses LiteLLM and routes via an `openai/<MODEL_NAME>` prefix reading
`OPENAI_API_BASE`. On installing CrewAI 1.15.1 and inspecting it, neither is true:

- CrewAI 1.15.1 has **no LiteLLM dependency** (litellm is not in the venv).
- The model-string prefix (`openai/`, `ollama/`, `openrouter/`, `deepseek/`, `cerebras/`,
  `dashscope/`, `hosted_vllm/`) routes through CrewAI's own provider registry.
- **Groq is NOT a built-in provider** in that registry, so a `groq/...` prefix won't work.

**Corrected approach (Option A — shared LLM in `config.py`):** `backend/config.py`
constructs one `crewai.LLM(model=os.getenv("MODEL_NAME"), base_url=os.getenv("OPENAI_BASE_URL"),
api_key=os.getenv("OPENAI_API_KEY"))` and passes it to every agent. The model id is
**bare** (no prefix); the endpoint is set via `base_url=`. The env var is `OPENAI_BASE_URL`
(not `OPENAI_API_BASE`) — that's the name the OpenAI SDK reads.

**Specs updated to match (no stale files):**
- `AGENT.md` §2 point 2 (rewritten with implementation note), §3 LLM + env rows
- `01-agents-and-crew.md` §0 (rewritten with `config.py` reference wiring); all three
  agents' `llm:` lines now `(shared LLM from config.py; see §0)`
- `02-orchestration-and-flow.md` §4 (env var name)
- `04-deployment-hf-spaces-docker.md` §6 + §8 (env var name)
- `05-error-handling-and-limits.md` §2 (env var name)
- `README.md` Quick Start (uv) + stack blurb (env var name)
- `.env.example` (rewritten: `OPENAI_BASE_URL`, bare model id)
- This file's Phase 0 + Phase 1 checklists
