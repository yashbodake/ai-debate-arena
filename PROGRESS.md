# PROGRESS.md — AI Debate Arena

Tracks phase-by-phase progress. Check items off as completed. Log any deviation from
spec immediately under the relevant phase's "Deviations" subsection — do not wait until
the end.

---

## Phase 0 — Setup

- [ ] Python 3.11+ virtualenv created
- [ ] `crewai`, `fastapi`, `uvicorn[standard]`, `python-dotenv` installed (see requirements.txt in Spec 04 §5)
- [ ] LLM provider configured via `.env`: `OPENAI_API_BASE`, `OPENAI_API_KEY`, `MODEL_NAME`
      (documented default = Groq free tier; see Spec 01 §0). Never commit `.env`.
- [ ] Repo initialized, `.gitignore` includes `.env`

**Deviations:** (none yet)

---

## Phase 1 — Agents & Crew (Spec 01)

- [ ] `Debater For` agent defined with role/goal/backstory
- [ ] `Debater Against` agent defined with role/goal/backstory
- [ ] `Moderator/Judge` agent defined with role/goal/backstory
- [ ] All three agents confirmed running against the deployer's chosen provider
      (`openai/<MODEL_NAME>` prefix → `OPENAI_API_BASE` env; documented default Groq)
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

**Current phase:** Not started (pre-build; docs only)
**Blockers:** None
**Next action:** Begin Phase 0 setup (requires repo-structure decision — see note below)

### Logged deviation (pre-build, 2026-07-06): LLM provider made provider-agnostic

**What changed:** Originally AGENT.md §2 point 2 and §3 locked the LLM to Groq free tier
(`groq/llama-3.3-70b-versatile`). The user decided the app should support **any
OpenAI-compatible provider**, chosen by the deployer via three env vars:
`OPENAI_API_BASE`, `OPENAI_API_KEY`, `MODEL_NAME`. Agents reference the model via the
`openai/<MODEL_NAME>` LiteLLM prefix; LiteLLM routes to whatever base URL the deployer
set. Groq remains the documented default in `.env.example` so anyone can still run it
for free out of the box.

**Why:** Flexibility — a deployer can point at Groq / OpenAI / OpenRouter / Ollama /
LM Studio / etc. by editing `.env`, with zero code changes. Cost is the deployer's
responsibility; the app itself imposes no paid-API requirement.

**Specs updated to match (no stale files):**
- `AGENT.md` §2 point 2, §3 LLM + env rows, §6 (also fixed stale "Gradio textbox" line)
- `01-agents-and-crew.md` §0 added; all three agents' `llm:` lines
- `02-orchestration-and-flow.md` §2 + §4
- `04-deployment-hf-spaces-docker.md` §6
- `05-error-handling-and-limits.md` §2 + §4
- `README.md` stack blurb
- This file's Phase 0 checklist (removed stale `gradio` dep line)

**Note:** "Free hosting only" (AGENT.md §2 point 1) still holds — HF Spaces free CPU
tier is unchanged. Only the LLM-cost constraint is relaxed, and only to the extent the
*deployer* opts into a paid provider by their own env choice.
