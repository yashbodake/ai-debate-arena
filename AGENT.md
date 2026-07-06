# AGENT.md — AI Debate Arena

This file is the single source of truth for any AI coding agent working on this project.
Read this FIRST, before touching any code. If a decision here conflicts with something
in a spec file, THIS FILE WINS.

---

## 1. What This Project Is

A web app where a user types any debate topic, and three CrewAI agents perform a live,
structured debate: one arguing FOR, one arguing AGAINST, and one moderating and judging.
The user watches the exchange stream in turn-by-turn and gets a final verdict with reasoning.

Zero login. Zero setup. Type a topic → watch a debate → get a verdict. That's the entire
product. Do not add scope beyond this without explicit sign-off.

---

## 2. Non-Negotiable Constraints

1. **Free hosting only.** Target platform is Hugging Face Spaces, Docker SDK, free CPU
   tier. No paid infra of any kind is acceptable at any phase.
2. **LLM = any OpenAI-compatible provider, chosen by the deployer.** The code is
   provider-agnostic. `backend/config.py` constructs **one shared `crewai.LLM`** at
   startup from three env vars and passes it to every agent — agents never construct
   their own LLM. The deployer sets (in `.env` locally, or HF Spaces "Repository
   secrets" in prod): `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`. This works
   with Groq, OpenAI, OpenRouter, Together, Ollama, LM Studio, etc. — anything that
   speaks the OpenAI Chat Completions API. The **documented default in `.env.example`
   is Groq free tier** (`OPENAI_BASE_URL=https://api.groq.com/openai/v1` +
   `MODEL_NAME=llama-3.3-70b-versatile`) so a deployer can run end-to-end for free;
   swapping providers is an env change, not a code change. Cost is the deployer's
   responsibility — the app itself imposes no paid-API requirement, but a deployer
   pointing at a paid provider will incur costs.

   > **Implementation note (CrewAI 1.15.1+).** CrewAI no longer depends on LiteLLM.
   > The model string is passed *without* a provider prefix (just the bare model id,
   > e.g. `llama-3.3-70b-versatile`), and the endpoint is set via the `base_url`
   argument to `LLM(...)`. Do **not** use `openai/<MODEL_NAME>` or `groq/...` prefixes
   > — those route through CrewAI's prefix-based provider lookup and Groq is not a
   > built-in provider there. The single shared `LLM` is the only correct entry
   > point; see Spec 01 §0.
3. **Frontend = plain HTML/CSS/JS, no framework.** No Vue, no React. GSAP is used
   directly via `<script>` tag for animation. No build step, no bundler, no npm
   install required to run the frontend — it's static files served as-is.
4. **Backend = FastAPI.** Wraps the CrewAI orchestration logic and exposes it to the
   frontend over Server-Sent Events (SSE), so the browser can receive turns as they're
   generated without polling.
5. **No vector DB, no embeddings, no RAG.** This project is pure LLM reasoning/dialogue.
   Do not introduce pgvector, Supabase, or any embedding model. If a future version needs
   fact-checking/citations, that is a new spec phase, not a silent addition to this one.
6. **No user accounts, no persistence of user data.** Debates are ephemeral — generated,
   shown, done. No database of past debates in v1.
7. **Three agents only in v1**: Debater For, Debater Against, Moderator/Judge.
   Do not add a 4th agent (e.g. "fact-checker") without a new spec phase.
8. **CrewAI process type: sequential with manual turn control**, not hierarchical.
   The moderator does NOT autonomously delegate — turn order is fixed and orchestrated
   in code (see Spec 02). This keeps behavior predictable and debuggable.
9. **Streaming is a hard requirement**, not a nice-to-have. Users must see each turn
   appear as it's generated, not wait for the whole debate then get a dump of text.
   Backend streams via SSE; frontend appends/animates each turn as its event arrives.
   Never a single blocking request that returns the whole debate at once.

---

## 3. Tech Stack (Locked)

| Layer | Choice | Why |
|---|---|---|
| Agent orchestration | CrewAI (latest stable) | Multi-agent framework, this is the whole point of the project |
| LLM | Any OpenAI-compatible provider via one shared `crewai.LLM` built in `config.py` from env (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`). Documented default: Groq `llama-3.3-70b-versatile` free tier | Provider-agnostic = deployer picks Groq / OpenAI / OpenRouter / Ollama / etc. without code changes; Groq remains the free default so anyone can run it for free out of the box. CrewAI 1.15.1+ has no LiteLLM dependency — bare model id + `base_url` arg, no provider prefix |
| Backend | FastAPI | Wraps orchestration logic, exposes SSE endpoint for streaming turns to the browser |
| Frontend | Plain HTML/CSS/JS + GSAP | No build step, GSAP handles turn-reveal/entrance animations, styling done via a UI/UX skill in the code assistant |
| Hosting | Hugging Face Spaces (Docker SDK, CPU basic) | Free, runs a real FastAPI app instead of being limited to the Gradio SDK template |
| Language | Python 3.11+ (backend), vanilla JS (frontend) | CrewAI/FastAPI are Python-native; frontend deliberately framework-free |
| Env/secrets | `.env` locally (see `.env.example`), HF Spaces "Repository secrets" in prod | Never commit API keys. Env holds `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME` |

Do not substitute any of these without updating this file first.

**Note:** GSAP and any UI/UX design skill are applied at the code-assistant/IDE level
during frontend implementation (developer's own tooling) — they are not part of this
spec suite's build steps, but the frontend spec (03) defines the HTML structure and
animation hook points they should target.

---

## 4. Project Structure (Target)

```
debate-arena/
├── AGENT.md                  # this file
├── PROGRESS.md                # phase tracker, updated as work completes
├── specs/
│   ├── 01-agents-and-crew.md
│   ├── 02-orchestration-and-flow.md
│   ├── 03-frontend-html-gsap.md
│   ├── 04-deployment-hf-spaces-docker.md
│   └── 05-error-handling-and-limits.md
├── backend/
│   ├── agents.py               # Agent + Task definitions
│   ├── crew.py                 # Crew wiring, per-turn execution logic (generator)
│   ├── main.py                 # FastAPI app, SSE endpoint, serves static frontend
│   └── config.py                # env loading, model name, constants
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js                # EventSource client, GSAP animation hooks
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

---

## 5. Deviation Log Rules

Any time an implementing agent (human or AI) deviates from a spec — different library
version, different prompt structure, different turn limit, whatever — it MUST be logged
in `PROGRESS.md` under the phase it happened in, with: what changed, why, and what spec
file is now stale. Do not silently drift from spec.

---

## 6. Definition of Done (v1)

- [ ] User can type any topic into the topic input field and hit submit
- [ ] Debate streams turn-by-turn: For → Against → For → Against → Moderator verdict
- [ ] Runs entirely on Groq free tier without hitting rate limits on a single debate
- [ ] Deployed and publicly reachable on a free HF Space
- [ ] No crashes on empty input, extremely long input, or offensive/unsafe topics
  (see Spec 05 for exact handling)
