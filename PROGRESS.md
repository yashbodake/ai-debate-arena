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

- [ ] `Debater For` agent defined with role/goal/backstory
- [ ] `Debater Against` agent defined with role/goal/backstory
- [ ] `Moderator/Judge` agent defined with role/goal/backstory
- [ ] All three agents confirmed running against the deployer's chosen provider
      (shared `LLM` from `config.py` → `OPENAI_BASE_URL` env; documented default Groq)
- [ ] Manual smoke test: run one full debate on a sample topic via CLI/script (no UI yet)

**Deviations:** (none yet)

---

## Phase 2 — Orchestration & Turn Flow (Spec 02)

- [ ] Turn-order controller function written (fixed sequence, not autonomous delegation)
- [ ] Each turn is a separate Task + Crew kickoff (not one giant crew run) so it can be
      yielded incrementally to the UI
- [ ] Context passing confirmed: each new turn's agent receives prior turns as context
- [ ] Turn limit enforced (default: 2 rounds each side + 1 moderator verdict = 5 turns)
- [ ] Verified total token/request usage per debate stays well within Groq free-tier limits

**Deviations:** (none yet)

---

## Phase 3 — Frontend (Spec 03)

- [ ] `frontend/index.html` built: topic input, "Start Debate" button, transcript container
- [ ] `script.js` wired to `/debate` SSE endpoint via `EventSource`
- [ ] Turns rendered as they arrive via SSE events, not one final dump
- [ ] GSAP entrance animations applied per speaker (For/Against/Moderator) — actual
      animation polish done via code-assistant + GSAP + UI/UX skill, per AGENT.md note
- [ ] Basic styling: visually distinguish "For" vs "Against" vs "Moderator" turns
- [ ] Loading/status indicator while a turn is being generated
- [ ] Manual test: full debate visible end-to-end in local browser against local FastAPI

**Deviations:** (none yet)

---

## Phase 4 — Deployment (Spec 04)

- [ ] HF Space created (Docker SDK)
- [ ] `Dockerfile` builds cleanly and listens on port 7860
- [ ] `requirements.txt` finalized and confirmed installing cleanly in the Docker build
- [ ] FastAPI serves both the `/debate` SSE endpoint and static frontend files correctly
- [ ] Groq API key added as HF Space "Repository secret" (not hardcoded)
- [ ] App confirmed working on the actual public Space URL — full browser test, not just curl
- [ ] Cold-start behavior checked (free CPU Spaces sleep — confirm container wakes up
      cleanly and SSE doesn't hang on a mid-restart request)

**Deviations:** (none yet)

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

**Current phase:** Phase 0 nearly complete (env + deps done; only `.env` key entry remains)
**Blockers:** None (user needs to add their Groq key to `.env` to run anything)
**Next action:** Add Groq key to `.env`, then begin Phase 1 (agents & crew)

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
