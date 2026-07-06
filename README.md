# AI Debate Arena

Type any topic, watch two AI debaters argue it out live, get a judged verdict.

Built with CrewAI (agent orchestration) + any OpenAI-compatible LLM provider + FastAPI
(backend, SSE streaming) + plain HTML/CSS/JS with GSAP (frontend), deployed free on
Hugging Face Spaces (Docker SDK). The LLM provider is chosen by the deployer via env
vars (`OPENAI_API_BASE`, `OPENAI_API_KEY`, `MODEL_NAME`); the documented default is
Groq free tier so anyone can run it for free out of the box.

## Quick Start (Local)

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then add your Groq API key
uvicorn backend.main:app --reload --port 7860
```

Then open `http://localhost:7860` in a browser.

## Project Docs

- [`AGENT.md`](./AGENT.md) — non-negotiable constraints and tech stack, read this first
- [`PROGRESS.md`](./PROGRESS.md) — phase-by-phase build tracker
- [`specs/`](./specs) — detailed specs per phase:
  1. Agents & Crew
  2. Orchestration & Turn Flow
  3. Frontend (Plain HTML/CSS/JS + GSAP)
  4. Deployment (HF Spaces, Docker)
  5. Error Handling & Limits

## How It Works

Three CrewAI agents: **Debater For**, **Debater Against**, **Moderator/Judge**. They run
in a fixed 5-turn sequence (For → Against → For → Against → Moderator verdict), streamed
to the UI turn-by-turn as each is generated — not one big blocking call.
